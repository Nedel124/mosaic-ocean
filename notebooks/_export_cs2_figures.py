"""Re-render CS2 figures to ``docs/figures/cs2/*.png`` (and *.pdf).

Reuses the same plotting recipes that the companion notebook would use,
but writes publication-quality files for direct inclusion in the paper's
Results section.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ZARR = REPO_ROOT / "out" / "cs2_atlantic_hurricane_offline.zarr"
SIDECAR = OUTPUT_ZARR.with_suffix(OUTPUT_ZARR.suffix + ".stac.json")
TRACK_CSV = REPO_ROOT / "tests" / "fixtures" / "cs2" / "ibtracs_ida_like.csv"
FIG_DIR = REPO_ROOT / "docs" / "figures" / "cs2"


def _save(fig: plt.Figure, stem: str) -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG_DIR / f"{stem}.png", dpi=200, bbox_inches="tight")
    fig.savefig(FIG_DIR / f"{stem}.pdf", bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    if not OUTPUT_ZARR.exists():
        from tests.fixtures.build_cs2_fixtures import build_all

        build_all(REPO_ROOT / "tests" / "fixtures" / "cs2")
        import mosaic as ms

        ms.run(str(REPO_ROOT / "tests" / "fixtures" / "cs2_offline.yaml"))

    ds = xr.open_zarr(OUTPUT_ZARR, consolidated=True)
    with open(SIDECAR) as fh:
        stac = json.load(fh)
    track = pd.read_csv(TRACK_CSV, parse_dates=["ISO_TIME"])

    plt.rcParams.update({"figure.dpi": 200, "font.size": 9})

    n = ds.sizes["time"]
    panel_days = np.linspace(0, n - 1, 4, dtype=int)

    # --- MSLP + wind quiver evolution ---------------------------------
    fig, axes = plt.subplots(1, 4, figsize=(13, 3.4), sharey=True)
    pmin = float(ds["air_pressure_at_mean_sea_level"].min())
    pmax = float(ds["air_pressure_at_mean_sea_level"].max())
    step = 3
    for ax, t in zip(axes, panel_days, strict=False):
        p = ds["air_pressure_at_mean_sea_level"].isel(time=t)
        u = ds["eastward_wind"].isel(time=t)
        v = ds["northward_wind"].isel(time=t)
        pcm = ax.pcolormesh(
            p.lon,
            p.lat,
            p.values,
            cmap="viridis_r",
            vmin=pmin,
            vmax=pmax,
            shading="auto",
        )
        ax.contour(p.lon, p.lat, p.values, levels=[980, 990, 1000], colors="white", linewidths=0.5)
        ax.quiver(
            u.lon[::step],
            u.lat[::step],
            u.values[::step, ::step],
            v.values[::step, ::step],
            scale=300,
            color="k",
            alpha=0.55,
            width=0.004,
        )
        ax.plot(track["LON"], track["LAT"], "r-", lw=1.0, alpha=0.8)
        ax.plot(track["LON"], track["LAT"], "r.", ms=3)
        ax.set_title(str(ds["time"].isel(time=t).values)[:10])
        ax.set_xlabel("lon (°E)")
    axes[0].set_ylabel("lat (°N)")
    fig.colorbar(pcm, ax=axes, fraction=0.025, pad=0.02, label="MSLP (hPa)")
    fig.suptitle("CS2 — MSLP + 10 m wind, Ida-like landfall (Aug 26 — Sep 2, 2021)", y=1.03)
    _save(fig, "fig_cs2_mslp_wind")

    # --- SST cold-wake panels -----------------------------------------
    fig, axes = plt.subplots(1, 4, figsize=(13, 3.4), sharey=True)
    sst = ds["sea_surface_temperature"] - 273.15
    vmin, vmax = float(sst.min()), float(sst.max())
    for ax, t in zip(axes, panel_days, strict=False):
        pcm = ax.pcolormesh(
            sst.lon,
            sst.lat,
            sst.isel(time=t).values,
            cmap="RdYlBu_r",
            vmin=vmin,
            vmax=vmax,
            shading="auto",
        )
        ax.plot(track["LON"], track["LAT"], "k-", lw=0.8, alpha=0.6)
        ax.plot(track["LON"], track["LAT"], "k.", ms=2)
        ax.set_title(str(ds["time"].isel(time=t).values)[:10])
        ax.set_xlabel("lon (°E)")
    axes[0].set_ylabel("lat (°N)")
    fig.colorbar(pcm, ax=axes, fraction=0.025, pad=0.02, label="SST (°C)")
    fig.suptitle("CS2 — SST with cold wake along the storm track", y=1.03)
    _save(fig, "fig_cs2_sst_wake")

    # --- Hurricane zone mask + storm-intensity time series ------------
    fig, ax = plt.subplots(figsize=(7.5, 4.0))
    intensity_max = ds["storm_intensity"].max(dim=("lat", "lon"))
    flagged_per_day = ds["hurricane_zone"].astype("uint8").sum(dim=("lat", "lon"))
    ax.plot(
        intensity_max.time,
        intensity_max.values,
        color="tab:blue",
        label="max storm_intensity (hPa)",
    )
    ax2 = ax.twinx()
    ax2.bar(
        flagged_per_day.time,
        flagged_per_day.values,
        color="tab:red",
        alpha=0.4,
        width=0.7,
        label="flagged cells",
    )
    ax.set_xlabel("date")
    ax.set_ylabel("max storm_intensity (hPa)", color="tab:blue")
    ax2.set_ylabel("flagged cells (count)", color="tab:red")
    ax.set_title("CS2 — storm intensity and hurricane-zone footprint")
    fig.autofmt_xdate()
    _save(fig, "fig_cs2_intensity_timeseries")

    # --- Hurricane-zone mask snapshots --------------------------------
    fig, axes = plt.subplots(1, 4, figsize=(13, 3.4), sharey=True)
    for ax, t in zip(axes, panel_days, strict=False):
        m = ds["hurricane_zone"].isel(time=t).astype("uint8")
        ax.pcolormesh(m.lon, m.lat, m.values, cmap="Greys", vmin=0, vmax=1, shading="auto")
        ax.plot(track["LON"], track["LAT"], "r-", lw=0.8, alpha=0.7)
        ax.plot(track["LON"], track["LAT"], "r.", ms=2)
        ax.set_title(str(ds["time"].isel(time=t).values)[:10])
        ax.set_xlabel("lon (°E)")
    axes[0].set_ylabel("lat (°N)")
    fig.suptitle("CS2 — hurricane zone (wind > 17 m/s AND MSLP < 980 hPa)", y=1.03)
    _save(fig, "fig_cs2_hurricane_zone")

    # --- Provenance summary -------------------------------------------
    summary = {
        "pipeline_hash": stac["properties"]["mosaic:pipeline_hash"],
        "content_hash": stac["properties"]["mosaic:content_hash"],
        "n_flagged": int(ds["hurricane_zone"].astype("uint8").sum().values),
        "n_total": int(ds["hurricane_zone"].size),
        "panel_days": panel_days.tolist(),
        "mapping_accuracy": stac["properties"]["mosaic:harmonization"]["mapping_accuracy"],
    }
    (FIG_DIR / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
