"""Unit tests for the derived-variable evaluator."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from mosaic._spec import DerivedVariable
from mosaic.derive import DerivationError, apply_derived, evaluate_expression


@pytest.fixture()
def toy_ds() -> xr.Dataset:
    time = pd.date_range("2022-06-01", periods=3, freq="1D")
    lat = np.array([54.0, 55.0])
    lon = np.array([14.0, 15.0])
    sst = np.full((3, 2, 2), 290.0, dtype="float32")
    sst[1, 0, 0] = 285.0  # cold patch
    return xr.Dataset(
        {
            "sea_surface_temperature": (("time", "lat", "lon"), sst),
            "sea_surface_temperature_climatology": (
                ("time", "lat", "lon"),
                np.full((3, 2, 2), 290.0, dtype="float32"),
            ),
            "eastward_wind": (("time", "lat", "lon"), np.full((3, 2, 2), -3.0, dtype="float32")),
            "northward_wind": (("time", "lat", "lon"), np.full((3, 2, 2), 4.0, dtype="float32")),
        },
        coords={"time": time, "lat": lat, "lon": lon},
    )


def test_simple_arithmetic(toy_ds: xr.Dataset) -> None:
    result = evaluate_expression("sqrt(eastward_wind**2 + northward_wind**2)", toy_ds)
    np.testing.assert_allclose(result.values, 5.0, rtol=1e-5)


def test_chained_comparison_and_boolean(toy_ds: xr.Dataset) -> None:
    expr = (
        "(sea_surface_temperature - sea_surface_temperature_climatology < -2.0) "
        "& (sqrt(eastward_wind**2 + northward_wind**2) > 4.0)"
    )
    result = evaluate_expression(expr, toy_ds)
    # Only the cold-patch cell should be True.
    expected = np.zeros((3, 2, 2), dtype=bool)
    expected[1, 0, 0] = True
    np.testing.assert_array_equal(result.values, expected)


def test_unknown_name_raises(toy_ds: xr.Dataset) -> None:
    with pytest.raises(DerivationError, match="unknown name 'mystery'"):
        evaluate_expression("mystery + 1", toy_ds)


def test_unsupported_function_raises(toy_ds: xr.Dataset) -> None:
    with pytest.raises(DerivationError, match="not in the allowed list"):
        evaluate_expression("__import__('os')", toy_ds)


def test_apply_derived_attaches_variable_and_provenance(toy_ds: xr.Dataset) -> None:
    derived = [
        DerivedVariable(name="wind_speed", expression="sqrt(eastward_wind**2 + northward_wind**2)"),
        DerivedVariable(name="upwelling_mask", expression="(wind_speed > 4.0)"),
    ]
    out, report = apply_derived(toy_ds, derived, strict=True)
    assert "wind_speed" in out.data_vars
    assert "upwelling_mask" in out.data_vars
    assert report.derived == ["wind_speed", "upwelling_mask"]
    assert out["wind_speed"].attrs["mosaic:derived"] == "true"
    assert out["upwelling_mask"].attrs["mosaic:expression"] == "(wind_speed > 4.0)"


def test_apply_derived_strict_propagates_error(toy_ds: xr.Dataset) -> None:
    with pytest.raises(DerivationError):
        apply_derived(
            toy_ds,
            [DerivedVariable(name="bad", expression="ghost + 1")],
            strict=True,
        )


def test_apply_derived_lenient_records_failure(toy_ds: xr.Dataset) -> None:
    out, report = apply_derived(
        toy_ds,
        [DerivedVariable(name="bad", expression="ghost + 1")],
        strict=False,
    )
    assert "bad" not in out.data_vars
    assert "bad" in report.failed
    assert report.success_rate == 0.0
