"""Tests for LocalNetcdfSource — bbox/time slicing, dim autodetection."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from mosaic.sources import LocalNetcdfSource
from mosaic.sources.base import SourceQuery


def _write_synthetic(path: Path) -> None:
    time = pd.date_range("2018-07-15", periods=10, freq="1D")
    lat = np.arange(50.0, 65.0 + 0.001, 0.5, dtype="float32")
    lon = np.arange(10.0, 25.0 + 0.001, 0.5, dtype="float32")
    sst = np.broadcast_to(
        290.0 - (lat[:, None] - 54.0) * 0.5, (len(time), lat.size, lon.size)
    ).astype("float32")
    ds = xr.Dataset(
        {
            "analysed_sst": (
                ("time", "lat", "lon"),
                sst,
                {"standard_name": "sea_surface_temperature", "units": "K"},
            )
        },
        coords={
            "time": ("time", time),
            "lat": ("lat", lat, {"standard_name": "latitude"}),
            "lon": ("lon", lon, {"standard_name": "longitude"}),
        },
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    ds.to_netcdf(path, engine="h5netcdf")


def test_local_source_bbox_and_time_slice(tmp_path: Path) -> None:
    nc_path = tmp_path / "synthetic_sst.nc"
    _write_synthetic(nc_path)

    src = LocalNetcdfSource(
        source_id="local_sst",
        path=str(nc_path),
        variables=["analysed_sst"],
        engine="h5netcdf",
    )
    query = SourceQuery(
        bbox=(14.0, 54.0, 22.0, 60.0),
        time_start=datetime(2018, 7, 20),
        time_stop=datetime(2018, 7, 23),
    )
    ds = src.fetch(query)

    assert "analysed_sst" in ds.data_vars
    assert float(ds["lon"].min()) >= 14.0 - 1e-3
    assert float(ds["lon"].max()) <= 22.0 + 1e-3
    assert float(ds["lat"].min()) >= 54.0 - 1e-3
    assert float(ds["lat"].max()) <= 60.0 + 1e-3
    assert ds.sizes["time"] == 4  # 20, 21, 22, 23


def test_local_source_records_provenance_uri(tmp_path: Path) -> None:
    nc_path = tmp_path / "p.nc"
    _write_synthetic(nc_path)
    src = LocalNetcdfSource(source_id="x", path=str(nc_path))
    query = SourceQuery(
        bbox=(10.0, 50.0, 25.0, 65.0),
        time_start=datetime(2018, 7, 15),
        time_stop=datetime(2018, 7, 25),
    )
    ds = src.fetch(query)
    assert ds.attrs["mosaic_source_uri"].endswith("p.nc")
    assert ds.attrs["mosaic_source_plugin"] == "local_netcdf"


def test_describe_payload_round_trips() -> None:
    src = LocalNetcdfSource(
        source_id="abc",
        path="data/x.nc",
        variables=["sst"],
        rename={"orig_name": "sst"},
    )
    desc = src.describe()
    assert desc["plugin"] == "local_netcdf"
    assert desc["source_id"] == "abc"
    assert desc["params"]["path"] == "data/x.nc"
    assert desc["params"]["rename"] == {"orig_name": "sst"}
