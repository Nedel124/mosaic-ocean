"""Generate synthetic CS2 (Atlantic hurricane) fixtures.

These fixtures emulate the layout of the real CMEMS Global L4 SST and
ERA5 single-levels subsets that the CS2 pipeline consumes in production,
plus an IBTrACS-style storm-track CSV used in the companion notebook.
The synthetic event is patterned after Hurricane Ida (August 2021), which
made landfall on the Louisiana coast on 2021-08-29.

Like the CS1 generator, this is deterministic (fixed seed) so the
on-disk SHA-256 of the fixture files is identical across machines.

Run as a script::

    python tests/fixtures/build_cs2_fixtures.py
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

# --- Domain --------------------------------------------------------------
# Gulf of Mexico, the path that Ida actually took.
BBOX = (-95.0, 18.0, -78.0, 32.0)
TIME_START = pd.Timestamp("2021-08-26")
TIME_STOP = pd.Timestamp("2021-09-02")
RESOLUTION_DEG = 0.5  # coarser than CS1 — Atlantic basin is wider.

# A simple synthetic storm track: starts near the Yucatán Channel, curves
# north-northwest across the central Gulf, makes "landfall" near 90.5W,29.2N
# on day 3 (2021-08-29), then continues inland (off-grid for our domain).
TRACK_LON = np.array([-83.0, -85.5, -87.5, -89.0, -90.5, -91.0, -91.0, -91.0])
TRACK_LAT = np.array([20.0, 22.5, 25.5, 27.5, 29.2, 30.5, 31.5, 32.0])
# Synthetic central-pressure trajectory in hPa: deepens before landfall,
# fills rapidly afterwards. Calibrated to give realistic looking gradients.
TRACK_MSLP = np.array([1006.0, 998.0, 985.0, 970.0, 955.0, 970.0, 990.0, 1004.0])


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _grid() -> tuple[np.ndarray, np.ndarray, pd.DatetimeIndex]:
    west, south, east, north = BBOX
    lon = np.arange(west, east + 1e-6, RESOLUTION_DEG, dtype="float32")
    lat = np.arange(south, north + 1e-6, RESOLUTION_DEG, dtype="float32")
    time = pd.date_range(TIME_START, TIME_STOP, freq="1D", inclusive="both")
    return lon, lat, time


def _great_circle_km(lat1: np.ndarray, lon1: np.ndarray, lat2: float, lon2: float) -> np.ndarray:
    """Haversine distance, broadcasting (lat1, lon1) vs scalar (lat2, lon2)."""
    R = 6371.0
    phi1 = np.deg2rad(lat1)
    phi2 = np.deg2rad(lat2)
    dphi = np.deg2rad(lat2 - lat1)
    dlam = np.deg2rad(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlam / 2) ** 2
    return R * 2 * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


# ---------------------------------------------------------------------------
# CMEMS-like SST fixture
# ---------------------------------------------------------------------------


def build_cmems_sst(out_path: Path) -> Path:
    """Daily L4 analysed_sst with a synthetic cold wake along the storm track."""
    lon, lat, time = _grid()
    rng = np.random.default_rng(20210826)

    # Warm Gulf-of-Mexico baseline ~302 K (~29 °C), gentle northward gradient.
    base = 302.0 - (lat[:, None] - 18.0) * 0.20
    base = np.broadcast_to(base, (lat.size, lon.size)).astype("float32")

    sst = np.empty((len(time), lat.size, lon.size), dtype="float32")
    LAT2D, LON2D = np.meshgrid(lat, lon, indexing="ij")
    for ti in range(len(time)):
        # Cold wake = sum of negative gaussians at all storm centroids up to ti
        # — the wake persists in the wake of the moving system.
        cold = np.zeros((lat.size, lon.size), dtype="float32")
        for k in range(min(ti + 1, len(TRACK_LON))):
            d_km = _great_circle_km(LAT2D, LON2D, TRACK_LAT[k], TRACK_LON[k])
            # Stronger cooling close to track, ~3 K dip with 150 km e-fold.
            decay = max(0.0, 1.0 - (ti - k) * 0.12)  # wake fades over a few days
            cold += -3.0 * decay * np.exp(-((d_km / 150.0) ** 2))
        noise = rng.standard_normal(base.shape).astype("float32") * 0.10
        sst[ti] = base + cold.astype("float32") + noise

    ds = xr.Dataset(
        data_vars={
            "analysed_sst": (
                ("time", "lat", "lon"),
                sst,
                {
                    "standard_name": "sea_surface_foundation_temperature",
                    "long_name": "Analysed sea surface temperature",
                    "units": "K",
                    "valid_min": np.float32(270.0),
                    "valid_max": np.float32(320.0),
                    "source": "CMEMS-like synthetic Global L4 analysed_sst",
                },
            )
        },
        coords={
            "time": ("time", time, {"standard_name": "time"}),
            "lat": ("lat", lat, {"standard_name": "latitude", "units": "degrees_north"}),
            "lon": ("lon", lon, {"standard_name": "longitude", "units": "degrees_east"}),
        },
        attrs={
            "title": "MOSAIC CS2 fixture — synthetic Gulf-of-Mexico L4 SST",
            "Conventions": "CF-1.11",
            "history": "generated by tests/fixtures/build_cs2_fixtures.py",
            "mosaic_synthetic": "true",
        },
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ds.to_netcdf(out_path, engine="h5netcdf")
    return out_path


# ---------------------------------------------------------------------------
# ERA5-like atmospheric fixture (u10, v10, mslp, tp)
# ---------------------------------------------------------------------------


def build_era5_atmos(out_path: Path) -> Path:
    """Daily-mean ERA5-like wind, MSLP, and accumulated precipitation."""
    lon, lat, time = _grid()
    rng = np.random.default_rng(20210826 + 1)

    # Mean climate-state pressure ~1013 hPa, mild north-easterly trade.
    LAT2D, LON2D = np.meshgrid(lat, lon, indexing="ij")
    p_base = 1013.0
    u_base = -3.0
    v_base = 1.0

    u = np.empty((len(time), lat.size, lon.size), dtype="float32")
    v = np.empty_like(u)
    p = np.empty_like(u)
    tp = np.empty_like(u)

    for ti in range(len(time)):
        # Storm centre at this time index (clip to track range).
        k = min(ti, len(TRACK_LON) - 1)
        cx, cy, cmin = TRACK_LON[k], TRACK_LAT[k], TRACK_MSLP[k]

        d_km = _great_circle_km(LAT2D, LON2D, cy, cx)
        # Pressure depression: gaussian with depth (p_base - cmin) and
        # ~250 km e-fold. Add small random noise.
        depth = p_base - cmin
        p_anomaly = -depth * np.exp(-((d_km / 250.0) ** 2))
        p_field = p_base + p_anomaly + rng.standard_normal(d_km.shape).astype("float32") * 0.5

        # Cyclonic (counter-clockwise) tangential winds around the centre,
        # with magnitude scaling with pressure depth and decaying with distance.
        # Tangential unit vector: rotate radial unit vector by +90°.
        dlat = LAT2D - cy
        dlon = LON2D - cx
        # convert to local east/north components scaled by latitude
        dx_km = dlon * np.cos(np.deg2rad(cy)) * 111.0
        dy_km = dlat * 111.0
        r_km = np.hypot(dx_km, dy_km)
        # Azimuthal speed profile: peak ~60 km, decay to background outside ~400 km.
        peak = 8.0 + 0.7 * depth  # m/s contribution from storm
        v_t = peak * (r_km / 60.0) * np.exp(-((r_km / 250.0) ** 2))
        # Cyclonic rotation in the Northern Hemisphere: u_r = -v_t * sin(theta),
        # v_r = v_t * cos(theta), where theta = atan2(dy, dx).
        theta = np.arctan2(dy_km, dx_km)
        u_storm = -v_t * np.sin(theta)
        v_storm = v_t * np.cos(theta)
        u[ti] = (u_base + u_storm + rng.standard_normal(d_km.shape).astype("float32") * 0.4).astype(
            "float32"
        )
        v[ti] = (v_base + v_storm + rng.standard_normal(d_km.shape).astype("float32") * 0.4).astype(
            "float32"
        )

        p[ti] = p_field.astype("float32")

        # Synthetic precipitation: localised heavy rain in the storm core,
        # daily-accumulated mm. Heavier on landfall day.
        rain_intensity = 60.0 if abs(cmin - 955.0) < 5.0 else 25.0 + 0.4 * depth
        tp_field = rain_intensity * np.exp(-((d_km / 80.0) ** 2))
        tp_field += np.maximum(rng.standard_normal(d_km.shape).astype("float32") * 0.5, 0.0)
        tp[ti] = tp_field.astype("float32")

    ds = xr.Dataset(
        data_vars={
            "u10": (
                ("time", "lat", "lon"),
                u,
                {"standard_name": "eastward_wind", "long_name": "10m u-wind", "units": "m s-1"},
            ),
            "v10": (
                ("time", "lat", "lon"),
                v,
                {"standard_name": "northward_wind", "long_name": "10m v-wind", "units": "m s-1"},
            ),
            "msl": (
                ("time", "lat", "lon"),
                p,
                {
                    "standard_name": "air_pressure_at_mean_sea_level",
                    "long_name": "Mean sea-level pressure",
                    "units": "hPa",
                },
            ),
            "tp": (
                ("time", "lat", "lon"),
                tp,
                {
                    "standard_name": "precipitation_amount",
                    "long_name": "Total daily precipitation",
                    "units": "mm",
                },
            ),
        },
        coords={
            "time": ("time", time, {"standard_name": "time"}),
            "lat": ("lat", lat, {"standard_name": "latitude", "units": "degrees_north"}),
            "lon": ("lon", lon, {"standard_name": "longitude", "units": "degrees_east"}),
        },
        attrs={
            "title": "MOSAIC CS2 fixture — synthetic ERA5-like atmosphere",
            "Conventions": "CF-1.11",
            "history": "generated by tests/fixtures/build_cs2_fixtures.py",
            "mosaic_synthetic": "true",
        },
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ds.to_netcdf(out_path, engine="h5netcdf")
    return out_path


# ---------------------------------------------------------------------------
# IBTrACS-style storm track CSV
# ---------------------------------------------------------------------------


def build_ibtracs_track(out_path: Path) -> Path:
    """A minimal IBTrACS-style CSV with the synthetic track for notebook overlay."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    times = pd.date_range(TIME_START, TIME_STOP, freq="1D", inclusive="both")
    rows = []
    for i, t in enumerate(times):
        k = min(i, len(TRACK_LON) - 1)
        rows.append(
            {
                "SID": "2021AL09",
                "NAME": "IDA-LIKE",
                "ISO_TIME": t.isoformat(),
                "LAT": float(TRACK_LAT[k]),
                "LON": float(TRACK_LON[k]),
                "WMO_PRES": float(TRACK_MSLP[k]),
            }
        )
    with out_path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return out_path


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------


def build_all(fixtures_dir: Path | None = None) -> dict[str, Path]:
    """Materialise all CS2 fixtures under ``fixtures_dir``."""
    fixtures_dir = Path(fixtures_dir) if fixtures_dir else Path(__file__).parent / "cs2"
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    return {
        "cmems_sst": build_cmems_sst(fixtures_dir / "cmems_gulf_sst_2021-08.nc"),
        "era5_atmos": build_era5_atmos(fixtures_dir / "era5_gulf_atmos_2021-08.nc"),
        "ibtracs": build_ibtracs_track(fixtures_dir / "ibtracs_ida_like.csv"),
    }


if __name__ == "__main__":  # pragma: no cover - manual invocation
    paths = build_all()
    for k, v in paths.items():
        print(f"{k}: {v}")
