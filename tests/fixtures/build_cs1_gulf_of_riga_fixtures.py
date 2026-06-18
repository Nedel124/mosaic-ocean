"""Generate deterministic CS1 fixtures for Gulf of Riga upwelling, July 2021.

These fixtures emulate the small local NetCDF inputs used by the offline
CS1 Gulf of Riga pipeline. They are intentionally synthetic: their purpose is
to exercise the same MOSAIC processing path without requiring CMEMS or ERA5
credentials. The live CMEMS--ERA5 workflow remains the source of the
geophysical counts reported in the paper.

The generated files match the variable names expected by
``tests/fixtures/cs1_gulf_of_riga_offline.yaml``:

* ``sea_surface_temperature``
* ``daily_median_sst``
* ``eastward_wind``
* ``northward_wind``

Run as a script::

    python tests/fixtures/build_cs1_gulf_of_riga_fixtures.py

Or call :func:`build_all` from a pytest conftest.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

# Gulf of Riga offline fixture domain.
# This matches the compact subset used in the live CS1 notebook / cached fixture.
BBOX = (22.0, 56.5, 24.8, 58.5)  # west, south, east, north
TIME_START = pd.Timestamp("2021-07-12")
TIME_STOP = pd.Timestamp("2021-07-22")
SST_RESOLUTION_DEG = 0.02
WIND_RESOLUTION_DEG = 0.25

TARGET_DATE = pd.Timestamp("2021-07-16")
SST_THRESHOLD_K = -2.0
WIND_THRESHOLD_MS = 4.0


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _time() -> pd.DatetimeIndex:
    return pd.date_range(TIME_START, TIME_STOP, freq="1D", inclusive="both")


def _grid(resolution_deg: float) -> tuple[np.ndarray, np.ndarray, pd.DatetimeIndex]:
    west, south, east, north = BBOX
    lon = np.arange(west, east + 1e-6, resolution_deg, dtype="float32")
    lat = np.arange(south, north + 1e-6, resolution_deg, dtype="float32")
    return lon, lat, _time()


def _baseline_sst(lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    """Smooth basin-scale SST background in Kelvin."""
    # Slightly warmer south-western basin, cooler north/east background.
    base = 292.0 - 0.25 * (lat[:, None] - 56.5) - 0.08 * (lon[None, :] - 22.0)
    return np.broadcast_to(base, (lat.size, lon.size)).astype("float32")


def _cold_patch(lon: np.ndarray, lat: np.ndarray, strength: float) -> np.ndarray:
    """Synthetic cold-water patch in the southern/eastern Gulf of Riga."""
    # Centre placed toward the eastern/southern Gulf, matching the interpretation
    # in the paper: a compact SST anomaly patch rather than a basin-wide cooling.
    return (
        -3.2
        * strength
        * np.exp(-(((lat[:, None] - 57.15) ** 2) / 0.055 + ((lon[None, :] - 24.05) ** 2) / 0.18))
    )


# ---------------------------------------------------------------------------
# CMEMS-like SST fixture
# ---------------------------------------------------------------------------


def build_cmems_sst(out_path: Path) -> Path:
    """Create a daily SST fixture with a Gulf-of-Riga cold-water feature."""
    lon, lat, time = _grid(SST_RESOLUTION_DEG)
    rng = np.random.default_rng(20210716)
    base = _baseline_sst(lon, lat)

    sst = np.empty((len(time), lat.size, lon.size), dtype="float32")
    for ti, timestamp in enumerate(time):
        # The cold patch develops around 16 July and then weakens, so a time-window
        # anomaly would be a poor event detector while a spatial daily anomaly fires.
        days_from_event = abs((timestamp - TARGET_DATE).days)
        strength = max(0.0, 1.0 - 0.28 * days_from_event)
        noise = rng.standard_normal(base.shape).astype("float32") * 0.08
        sst[ti] = base + _cold_patch(lon, lat, strength).astype("float32") + noise

    da = xr.DataArray(
        sst,
        dims=("time", "latitude", "longitude"),
        coords={"time": time, "latitude": lat, "longitude": lon},
        name="sea_surface_temperature",
        attrs={
            "standard_name": "sea_surface_temperature",
            "long_name": "Synthetic analysed sea surface temperature",
            "units": "K",
            "valid_min": np.float32(270.0),
            "valid_max": np.float32(320.0),
            "source": "CMEMS-like synthetic Gulf of Riga L4 SST",
        },
    )

    # Pre-compute the daily domain-wide spatial median and broadcast it to the
    # SST grid. The offline YAML then only needs a simple subtraction expression.
    median = da.median(dim=("latitude", "longitude"), skipna=True).broadcast_like(da)
    median.name = "daily_median_sst"
    median.attrs.update(
        {
            "long_name": "Daily domain-wide median sea surface temperature",
            "units": "K",
            "mosaic_role": "spatial_reference",
        }
    )

    ds = xr.Dataset(
        data_vars={
            "sea_surface_temperature": da,
            "daily_median_sst": median,
        },
        attrs={
            "title": "MOSAIC CS1 fixture — synthetic Gulf of Riga SST",
            "Conventions": "CF-1.11",
            "institution": "MOSAIC test fixture (synthetic)",
            "history": "generated by tests/fixtures/build_cs1_gulf_of_riga_fixtures.py",
            "mosaic_synthetic": "true",
        },
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    ds.to_netcdf(out_path, engine="h5netcdf")
    return out_path


# ---------------------------------------------------------------------------
# ERA5-like wind fixture
# ---------------------------------------------------------------------------


def build_era5_wind(out_path: Path) -> Path:
    """Create a daily-mean ERA5-like 10 m wind fixture."""
    lon, lat, time = _grid(WIND_RESOLUTION_DEG)
    rng = np.random.default_rng(20210717)

    u = np.empty((len(time), lat.size, lon.size), dtype="float32")
    v = np.empty_like(u)

    for ti, timestamp in enumerate(time):
        days_from_event = abs((timestamp - TARGET_DATE).days)
        event_strength = max(0.0, 1.0 - 0.22 * days_from_event)

        # Broad basin-scale wind context. The strongest daily-mean wind is placed
        # mainly north/west of the cold SST patch, so the pixel-wise SST-wind
        # intersection remains stricter than the SST-only mask.
        wind_core = np.exp(
            -(((lat[:, None] - 58.0) ** 2) / 0.28 + ((lon[None, :] - 22.8) ** 2) / 0.55)
        )
        background = 2.2 + 2.9 * event_strength * wind_core
        direction = np.deg2rad(230.0)  # south-westerly-like flow context

        u[ti] = (background * np.cos(direction)).astype("float32")
        v[ti] = (background * np.sin(direction)).astype("float32")
        u[ti] += rng.standard_normal((lat.size, lon.size)).astype("float32") * 0.10
        v[ti] += rng.standard_normal((lat.size, lon.size)).astype("float32") * 0.10

    ds = xr.Dataset(
        data_vars={
            "eastward_wind": (
                ("time", "latitude", "longitude"),
                u,
                {
                    "standard_name": "eastward_wind",
                    "long_name": "Synthetic daily-mean 10 m eastward wind",
                    "units": "m s-1",
                },
            ),
            "northward_wind": (
                ("time", "latitude", "longitude"),
                v,
                {
                    "standard_name": "northward_wind",
                    "long_name": "Synthetic daily-mean 10 m northward wind",
                    "units": "m s-1",
                },
            ),
        },
        coords={
            "time": ("time", time, {"standard_name": "time"}),
            "latitude": ("latitude", lat, {"standard_name": "latitude", "units": "degrees_north"}),
            "longitude": (
                "longitude",
                lon,
                {"standard_name": "longitude", "units": "degrees_east"},
            ),
        },
        attrs={
            "title": "MOSAIC CS1 fixture — synthetic Gulf of Riga ERA5-like wind",
            "Conventions": "CF-1.11",
            "history": "generated by tests/fixtures/build_cs1_gulf_of_riga_fixtures.py",
            "mosaic_synthetic": "true",
        },
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    ds.to_netcdf(out_path, engine="h5netcdf")
    return out_path


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------


def build_all(fixtures_dir: Path | None = None) -> dict[str, Path]:
    """Materialise all CS1 Gulf of Riga fixtures under ``fixtures_dir``."""
    fixtures_dir = (
        Path(fixtures_dir) if fixtures_dir else Path(__file__).parent / "data" / "cs1_gulf_of_riga"
    )
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    return {
        "cmems_sst": build_cmems_sst(fixtures_dir / "cmems_gulf_of_riga_sst_2021-07.nc"),
        "era5_wind": build_era5_wind(fixtures_dir / "era5_gulf_of_riga_wind_2021-07.nc"),
    }


if __name__ == "__main__":  # pragma: no cover - manual invocation
    paths = build_all()
    for key, value in paths.items():
        print(f"{key}: {value}")
