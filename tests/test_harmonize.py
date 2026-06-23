"""Tests for the three-tier semantic harmonizer."""
from __future__ import annotations

import textwrap
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from mosaic.harmonize import Harmonizer


def _ds(var: str, *, standard_name: str | None = None, units: str = "1") -> xr.Dataset:
    time = pd.date_range("2022-06-01", periods=3, freq="1D")
    arr = xr.DataArray(np.zeros((3, 2, 2), dtype="float32"), dims=("time", "lat", "lon"))
    if standard_name:
        arr.attrs["standard_name"] = standard_name
    arr.attrs["units"] = units
    return xr.Dataset({var: arr}, coords={"time": time, "lat": [54.0, 55.0], "lon": [14.0, 15.0]})


def test_cf_match_via_existing_standard_name() -> None:
    ds = _ds("temperature_at_surface", standard_name="sea_surface_temperature", units="K")
    h = Harmonizer()
    result = h.harmonize({"src": ds})
    decisions = {d.source_var: d for d in result.decisions}
    assert decisions["temperature_at_surface"].tier == "cf"
    assert decisions["temperature_at_surface"].target_standard_name == "sea_surface_temperature"


def test_dictionary_match_via_alias(tmp_path: Path) -> None:
    cf = tmp_path / "cf.yaml"
    cf.write_text(textwrap.dedent("""
    aliases:
      sst: sea_surface_temperature
    units: {}
    """), encoding="utf-8")
    h = Harmonizer(cf_dictionary=cf)
    ds = _ds("sst", units="degree_Celsius")
    result = h.harmonize({"src": ds})
    decision = result.decisions[0]
    assert decision.tier == "dictionary"
    assert decision.target_standard_name == "sea_surface_temperature"


def test_unresolved_falls_into_unresolved_bucket() -> None:
    h = Harmonizer()
    ds = _ds("totally_unknown_xyz_123_qwerty", units="?")
    result = h.harmonize({"src": ds})
    assert result.unresolved == ["totally_unknown_xyz_123_qwerty"]
    assert result.mapping_accuracy == 0.0


def test_mapping_accuracy_is_a_fraction() -> None:
    h = Harmonizer()
    ds = xr.merge([
        _ds("sst", standard_name="sea_surface_temperature"),
        _ds("garbage_name_zzzz", units="?"),
    ])
    result = h.harmonize({"src": ds})
    assert result.mapping_accuracy == pytest.approx(0.5)


def test_override_wins() -> None:
    h = Harmonizer(overrides={"src.foo": {"standard_name": "sea_water_salinity", "units": "1e-3"}})
    ds = _ds("foo")
    result = h.harmonize({"src": ds})
    assert result.decisions[0].tier == "override"
    assert result.decisions[0].target_standard_name == "sea_water_salinity"
