"""QC rule engine.

The engine applies a small, deterministic set of rules per variable:

* ``range``     — flag values outside [min, max].
* ``spike``     — flag values whose absolute deviation from a rolling median
                  exceeds ``threshold_sigma`` * rolling MAD.
* ``stuck``     — flag stretches where the value is constant for ``window``
                  consecutive samples along the time axis.
* ``gradient``  — flag values whose absolute first difference exceeds
                  ``threshold_sigma`` standard deviations of all differences.
* ``gap``       — flag NaN values explicitly (does not invent data).

The result is a mask DataArray (1 = pass, 0 = flagged) attached as a CF
``ancillary_variables`` companion. Statistics are returned for provenance.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import xarray as xr

from mosaic._spec import InlineQCRule


@dataclass(slots=True)
class _RuleStat:
    rule: str
    variable: str
    flagged: int


@dataclass(slots=True)
class QCReport:
    per_rule: list[_RuleStat] = field(default_factory=list)
    n_total: int = 0

    @property
    def flagged_total(self) -> int:
        return sum(s.flagged for s in self.per_rule)

    @property
    def flagged_fraction(self) -> float:
        return 0.0 if self.n_total == 0 else self.flagged_total / self.n_total

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_total": self.n_total,
            "flagged_total": self.flagged_total,
            "flagged_fraction": self.flagged_fraction,
            "per_rule": [
                {"rule": s.rule, "variable": s.variable, "flagged": s.flagged}
                for s in self.per_rule
            ],
        }


class QCEngine:
    """Apply rule sets to an :class:`xarray.Dataset` and produce a report."""

    def __init__(self, rules: Mapping[str, InlineQCRule] | None = None) -> None:
        self.rules: dict[str, InlineQCRule] = dict(rules or {})

    # ------------------------------------------------------------------ API
    def apply(self, ds: xr.Dataset) -> tuple[xr.Dataset, QCReport]:
        report = QCReport()
        out = ds.copy()
        total = sum(int(out[v].size) for v in out.data_vars)
        report.n_total = total

        for var, rule in self.rules.items():
            if var not in out.data_vars:
                # Don't fail loudly: pipeline may legitimately drop a variable
                # earlier; record it as zero-flagged.
                report.per_rule.append(_RuleStat(rule=rule.type, variable=var, flagged=0))
                continue
            arr = out[var]
            mask = self._apply_rule(arr, rule)
            flagged = int((mask == 0).sum().values)
            report.per_rule.append(_RuleStat(rule=rule.type, variable=var, flagged=flagged))

            mask_name = f"{var}_qc"
            mask.name = mask_name
            mask.attrs["flag_meanings"] = "flagged pass"
            mask.attrs["flag_values"] = "0 1"
            mask.attrs["long_name"] = f"QC mask for {var} (rule={rule.type})"
            out[mask_name] = mask
            ancillary = arr.attrs.get("ancillary_variables", "")
            tokens = [t for t in ancillary.split() if t]
            if mask_name not in tokens:
                tokens.append(mask_name)
            out[var].attrs["ancillary_variables"] = " ".join(tokens)

        return out, report

    # ------------------------------------------------------------------ rules
    def _apply_rule(self, arr: xr.DataArray, rule: InlineQCRule) -> xr.DataArray:
        if rule.type == "range":
            lo = -np.inf if rule.min is None else rule.min
            hi = +np.inf if rule.max is None else rule.max
            mask = ((arr >= lo) & (arr <= hi)).astype("int8")
            return mask.where(~arr.isnull(), 0)
        if rule.type == "gap":
            return arr.notnull().astype("int8")
        if rule.type == "stuck":
            window = rule.window or 3
            # detect runs of equal consecutive values along the time axis
            diff = arr.diff(dim="time").fillna(1.0)
            equal = (diff == 0).astype("int8")
            run = equal.rolling(time=window, min_periods=window).sum()
            stuck = (run >= window - 1).astype("int8")
            mask = (1 - stuck).astype("int8")
            # right-align: the rolling result begins at the (window-1)-th sample;
            # earlier samples are conservatively passed.
            mask = mask.fillna(1).astype("int8")
            return mask
        if rule.type == "spike":
            sigma = rule.threshold_sigma or 5.0
            window = rule.window or 5
            roll = arr.rolling(time=window, center=True, min_periods=1)
            med = roll.median()
            mad = abs(arr - med).rolling(time=window, center=True, min_periods=1).median()
            scaled = abs(arr - med) / (mad.where(mad > 0, 1e-9))
            mask = (scaled <= sigma).astype("int8")
            return mask.fillna(1).astype("int8")
        if rule.type == "gradient":
            sigma = rule.threshold_sigma or 5.0
            diff = arr.diff(dim="time")
            std = float(diff.std().values) or 1e-9
            mask = (abs(diff) <= sigma * std).astype("int8")
            # pad the leading sample as pass
            mask = mask.reindex(time=arr["time"], fill_value=1)
            return mask
        raise ValueError(f"unknown QC rule type: {rule.type}")
