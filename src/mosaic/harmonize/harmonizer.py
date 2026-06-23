"""Three-tier semantic harmonizer for MOSAIC.

The algorithm is the heart of the methods section in the paper:

    For each variable in each source dataset, attempt resolution against
    the CF Standard Name Table (Tier 1), then against the domain dictionary
    (Tier 2), then against a fuzzy heuristic over names + units (Tier 3).
    Each decision carries a confidence score; the metric reported in the
    paper is the *mapping accuracy* defined as

        mapping_accuracy = (n_CF + n_dict + n_heur_confident) / n_total

    where ``n_heur_confident`` only counts heuristic matches whose score
    exceeds ``confidence_threshold``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Literal

import xarray as xr

# ---------------------------------------------------------------------------
# data classes
# ---------------------------------------------------------------------------

Tier = Literal["cf", "dictionary", "heuristic", "override", "unresolved"]


@dataclass(slots=True)
class MappingDecision:
    """How a single variable was resolved."""

    source_var: str
    target_standard_name: str | None
    target_units: str | None
    tier: Tier
    confidence: float
    notes: str = ""


@dataclass(slots=True)
class HarmonizationResult:
    """Outcome of harmonizing one or more source datasets."""

    dataset: xr.Dataset
    decisions: list[MappingDecision] = field(default_factory=list)

    @property
    def mapping_accuracy(self) -> float:
        if not self.decisions:
            return 0.0
        good = sum(1 for d in self.decisions if d.tier != "unresolved")
        return good / len(self.decisions)

    @property
    def unresolved(self) -> list[str]:
        return [d.source_var for d in self.decisions if d.tier == "unresolved"]

    def summary(self) -> dict[str, object]:
        return {
            "mapping_accuracy": self.mapping_accuracy,
            "n_total": len(self.decisions),
            "per_tier": {
                tier: sum(1 for d in self.decisions if d.tier == tier)
                for tier in ("cf", "dictionary", "heuristic", "override", "unresolved")
            },
            "unresolved_variables": self.unresolved,
        }


# ---------------------------------------------------------------------------
# small CF base table
# ---------------------------------------------------------------------------

# Minimal stand-in for the CF Standard Name Table v85. The full table is
# loaded from ``cf-xarray`` in production; here we keep enough for the
# tutorial and the round-trip tests to exercise every tier.
_CF_BASE: dict[str, dict[str, str]] = {
    "sea_surface_temperature": {"canonical_units": "K"},
    "eastward_wind": {"canonical_units": "m s-1"},
    "northward_wind": {"canonical_units": "m s-1"},
    "wind_speed": {"canonical_units": "m s-1"},
    "air_temperature": {"canonical_units": "K"},
    "sea_water_salinity": {"canonical_units": "1e-3"},
    "sea_water_potential_temperature": {"canonical_units": "K"},
    "mass_concentration_of_chlorophyll_in_sea_water": {"canonical_units": "kg m-3"},
    "sea_ice_area_fraction": {"canonical_units": "1"},
}


# CF canonical names for spatial / temporal coordinates. The harmonizer
# renames each source's coordinates to these targets before the cross-source
# merge, so that ``xarray.merge`` aligns by physical axis rather than by
# accidental string identity.
_CF_COORD_CANONICAL: frozenset[str] = frozenset(
    {"latitude", "longitude", "time", "depth", "height"}
)

# Short-form / provider-specific aliases for coordinates. Used as a
# fallback when a coordinate does not declare an explicit ``standard_name``
# attribute. Covers the three real-world conventions we have observed in
# production data: CMEMS-style ``lat``/``lon``, CDS toolbox-2 ``valid_time``
# (instead of the CF-canonical ``time``), and the legacy ``t`` axis.
_COORD_ALIASES: dict[str, str] = {
    "lat": "latitude",
    "lon": "longitude",
    "valid_time": "time",
    "t": "time",
}


# ---------------------------------------------------------------------------
# harmonizer
# ---------------------------------------------------------------------------


class Harmonizer:
    """Three-tier semantic harmonizer.

    Parameters
    ----------
    cf_dictionary
        Optional path to a domain dictionary YAML. Schema::

            aliases:
              sst: sea_surface_temperature
              chl: mass_concentration_of_chlorophyll_in_sea_water
            units:
              degree_Celsius: K
    overrides
        Per-variable manual overrides (``"<source_id>.<var>": {standard_name, units}``).
    confidence_threshold
        Heuristic decisions below this are tagged ``unresolved``.
    """

    def __init__(
        self,
        cf_dictionary: str | Path | None = None,
        overrides: dict[str, dict[str, str]] | None = None,
        confidence_threshold: float = 0.85,
    ) -> None:
        self.cf_dictionary = Path(cf_dictionary) if cf_dictionary else None
        self.overrides = overrides or {}
        self.confidence_threshold = confidence_threshold
        self._aliases, self._unit_aliases = self._load_dictionary(self.cf_dictionary)

    # ------------------------------------------------------------------ API
    def harmonize(self, datasets: dict[str, xr.Dataset]) -> HarmonizationResult:
        """Harmonize a mapping ``source_id -> Dataset`` into a single Dataset."""
        decisions: list[MappingDecision] = []
        renamed: list[xr.Dataset] = []

        for source_id, ds in datasets.items():
            new_vars: dict[str, xr.DataArray] = {}
            for var in ds.data_vars:
                decision = self._resolve(source_id, str(var), ds[var])
                decisions.append(decision)
                if decision.target_standard_name is None:
                    new_vars[str(var)] = ds[var]
                    continue
                arr = ds[var].copy()
                if decision.target_standard_name:
                    arr.attrs["standard_name"] = decision.target_standard_name
                if decision.target_units:
                    arr.attrs["units"] = decision.target_units
                # Keep variable name = standard_name when possible (CF-friendly).
                new_vars[decision.target_standard_name] = arr
            normalised = xr.Dataset(new_vars, coords=ds.coords, attrs=ds.attrs)
            normalised = self._normalize_coords(normalised)
            renamed.append(normalised)

        # Explicit ``join='outer'`` preserves the historical semantics of the
        # merge step and silences a FutureWarning emitted by xarray >=2024.7,
        # which announces that the default will switch to ``'exact'``. We
        # cannot adopt ``'exact'`` today because sources of different native
        # resolutions (e.g. 0.02 deg CMEMS L4 SST vs. 0.25 deg ERA5 wind) have
        # distinct coordinate values; the proper resolution is grid
        # regridding, handled by ``mosaic.harmonize.grid`` in a later release.
        merged = xr.merge(
            renamed,
            compat="override",
            combine_attrs="drop_conflicts",
            join="outer",
        )
        return HarmonizationResult(dataset=merged, decisions=decisions)

    # ------------------------------------------------------------------ coords
    @staticmethod
    def _normalize_coords(ds: xr.Dataset) -> xr.Dataset:
        """Rename coordinates to their CF canonical names.

        Resolves the second class of cross-source heterogeneity that the
        harmonizer must absorb: not the *variable* identifier (handled by
        the three-tier resolver above) but the *coordinate axis* identifier.
        Sources we encountered in production disagree on axis naming in three
        recurrent ways: CMEMS toolbox 2.x emits ``latitude``/``longitude``,
        Climate Data Store toolbox 2.x emits ``valid_time`` instead of
        ``time``, and many legacy / fixture NetCDFs use the short form
        ``lat``/``lon``. Left unreconciled, these names cause
        :func:`xarray.merge` to treat physically identical axes as orthogonal
        dimensions and to broadcast the merged dataset into the cartesian
        product of every coord, blowing memory by orders of magnitude
        (observed: a 11x25x33 climatology merged against a 11x313x421 CMEMS
        slice produced a 5-D 49 GiB boolean array on the ``fuse`` step).

        Resolution proceeds in two passes per coordinate:

        1. Honour an explicit ``standard_name`` attribute that names a CF
           canonical coordinate (``latitude``, ``longitude``, ``time``,
           ``depth``, ``height``).
        2. Fall back to a short-form alias table (``lat`` -> ``latitude``,
           ``valid_time`` -> ``time``, ...).

        Renames are skipped on collision (e.g. when a dataset already
        carries both ``lat`` and ``latitude``) to preserve idempotence.
        """
        rename_map: dict[str, str] = {}
        for name in list(ds.coords):
            coord = ds.coords[name]
            target: str | None = None

            std = str(coord.attrs.get("standard_name", "")).strip()
            if std and std in _CF_COORD_CANONICAL and std != name:
                target = std
            elif name in _COORD_ALIASES:
                target = _COORD_ALIASES[str(name)]

            if target is None or target == name:
                continue
            # Avoid clobbering an existing coordinate or a previously planned
            # rename target — both situations indicate the dataset is already
            # carrying the canonical axis under another name, and ``xarray``
            # would raise on a collision.
            if target in ds.coords or target in rename_map.values():
                continue
            rename_map[str(name)] = target

        if not rename_map:
            return ds
        return ds.rename(rename_map)

    # ------------------------------------------------------------------ tiers
    def _resolve(self, source_id: str, var: str, da: xr.DataArray) -> MappingDecision:
        # 0. explicit override
        key = f"{source_id}.{var}"
        if key in self.overrides:
            ov = self.overrides[key]
            return MappingDecision(
                source_var=var,
                target_standard_name=ov.get("standard_name"),
                target_units=ov.get("units"),
                tier="override",
                confidence=1.0,
                notes="explicit override",
            )

        # 1. CF-match: if the dataarray already declares a known CF standard_name
        sname = str(da.attrs.get("standard_name", "")).strip()
        if sname and sname in _CF_BASE:
            return MappingDecision(
                source_var=var,
                target_standard_name=sname,
                target_units=str(da.attrs.get("units", _CF_BASE[sname]["canonical_units"])),
                tier="cf",
                confidence=1.0,
                notes="CF standard_name already present",
            )

        # 2. Dictionary alias on the variable name
        if var in self._aliases:
            sname = self._aliases[var]
            return MappingDecision(
                source_var=var,
                target_standard_name=sname,
                target_units=_CF_BASE.get(sname, {}).get("canonical_units"),
                tier="dictionary",
                confidence=0.95,
                notes=f"matched alias '{var}' -> '{sname}'",
            )

        # 3. Heuristic fuzzy match against CF base names
        candidates = list(_CF_BASE)
        best_name, best_score = self._best_fuzzy(var, candidates)
        if best_score >= self.confidence_threshold:
            return MappingDecision(
                source_var=var,
                target_standard_name=best_name,
                target_units=_CF_BASE[best_name]["canonical_units"],
                tier="heuristic",
                confidence=best_score,
                notes=f"fuzzy match score={best_score:.2f}",
            )

        return MappingDecision(
            source_var=var,
            target_standard_name=None,
            target_units=str(da.attrs.get("units", "")) or None,
            tier="unresolved",
            confidence=best_score,
            notes=f"best fuzzy candidate '{best_name}' ({best_score:.2f}) below threshold",
        )

    # ------------------------------------------------------------------ utils
    @staticmethod
    def _best_fuzzy(name: str, candidates: list[str]) -> tuple[str, float]:
        if not candidates:
            return "", 0.0
        best = ""
        best_score = 0.0
        # compare both raw name and a normalised form (underscores -> spaces)
        norms = (name, name.replace("_", " "))
        for cand in candidates:
            score = max(SequenceMatcher(None, n, cand).ratio() for n in norms)
            if score > best_score:
                best_score = score
                best = cand
        return best, best_score

    @staticmethod
    def _load_dictionary(path: Path | None) -> tuple[dict[str, str], dict[str, str]]:
        if path is None or not path.exists():
            return {}, {}
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        aliases = data.get("aliases", {}) or {}
        unit_aliases = data.get("units", {}) or {}
        if not isinstance(aliases, dict) or not isinstance(unit_aliases, dict):
            raise ValueError(f"malformed CF dictionary: {path}")
        return {str(k): str(v) for k, v in aliases.items()}, {
            str(k): str(v) for k, v in unit_aliases.items()
        }
