"""Re-render every CS1 figure to ``docs/figures/cs1/*.png`` (and *.pdf).

Reuses the same plotting logic as ``cs1_gulf_of_riga_upwelling.ipynb`` but
writes publication-quality files instead of inline PNGs. Intended to feed
directly into the paper's Results section.
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ZARR = REPO_ROOT / "out" / "cs1_gulf_of_riga_upwelling_offline.zarr"
SIDECAR = OUTPUT_ZARR.with_suffix(OUTPUT_ZARR.suffix + ".stac.json")
FIG_DIR = REPO_ROOT / "docs" / "figures" / "cs1"


def _save(fig: plt.Figure, stem: str) -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG_DIR / f"{stem}.png", dpi=200, bbox_inches="tight")
    fig.savefig(FIG_DIR / f"{stem}.pdf", bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    if not OUTPUT_ZARR.exists():
        from tests.fixtures.build_cs1_gulf_of_riga_fixtures import build_all
        build_all(REPO_ROOT / "tests" / "fixtures" / "cs1_gulf_of_riga")
        import mosaic as ms
        ms.run(str(REPO_ROOT / "tests" / "fixtures" / "cs1_gulf_of_riga_offline.yaml"))

    ds = xr.open_zarr(OUTPUT_ZARR, consolidated=True)
    with open(SIDECAR) as fh:
        stac = json.load(fh)

    plt.rcParams.update({"figure.dpi": 200, "font.size": 9})

    n = ds.sizes["time"]
    panel_days = np.linspace(0, n - 1, 4, dtype=int)

    # --- SST evolution ------------------------------------------------
    fig, axes = plt.subplots(1, 4, figsize=(13, 3.4), sharey=True)
    sst_c = ds["sea_surface_temperature"] - 273.15
    vmin, vmax = float(sst_c.min()), float(sst_c.max())
    for ax, t in zip(axes, panel_days):
        sst = sst_c.isel(time=t)
        pcm = ax.pcolormesh(
            sst.lon, sst.lat, sst.values,
            cmap="RdYlBu_r", vmin=vmin, vmax=vmax, shading="auto",
        )
        ax.set_title(str(ds["time"].isel(time=t).values)[:10])
        ax.set_xlabel("lon (°E)")
    axes[0].set_ylabel("lat (°N)")
    fig.colorbar(pcm, ax=axes, fraction=0.025, pad=0.02, label="SST (°C)")
    fig.suptitle("CS1 — Gulf of Riga SST (CMEMS L4, harmonised)", y=1.02)
    _save(fig, "fig_cs1_riga_sst_evolution")

    # --- Spatial SST anomaly ------------------------------------------
    fig, axes = plt.subplots(1, 4, figsize=(13, 3.4), sharey=True)
    ano_max = float(np.abs(ds["sst_spatial_anomaly"]).max())
    for ax, t in zip(axes, panel_days):
        ano = ds["sst_spatial_anomaly"].isel(time=t)
        pcm = ax.pcolormesh(
            ano.lon, ano.lat, ano.values,
            cmap="RdBu_r", vmin=-ano_max, vmax=ano_max, shading="auto",
        )
        ax.contour(ano.lon, ano.lat, ano.values, levels=[-2.0], colors="k", linewidths=0.6)
        ax.set_title(str(ds["time"].isel(time=t).values)[:10])
        ax.set_xlabel("lon (°E)")
    axes[0].set_ylabel("lat (°N)")
    fig.colorbar(pcm, ax=axes, fraction=0.025, pad=0.02, label="SST anomaly (K)")
    fig.suptitle("CS1 — Spatial SST anomaly (SST − daily median)", y=1.02)
    _save(fig, "fig_cs1_riga_spatial_anomaly_2021-07-16")

    # --- SST-only upwelling mask on 2021-07-16 ------------------------
    t16_idx = int(np.argmin(np.abs(
        pd.to_datetime(ds["time"].values) - pd.Timestamp("2021-07-16")
    )))
    mask_sst = ds["upwelling_mask_sst"].isel(time=t16_idx).astype("uint8")

    fig, ax = plt.subplots(figsize=(6, 5))
    ax.pcolormesh(mask_sst.lon, mask_sst.lat, mask_sst.values,
                  cmap="Greys", vmin=0, vmax=1, shading="auto")
    ax.set_title("CS1 — SST-only upwelling mask, 16 July 2021")
    ax.set_xlabel("lon (°E)")
    ax.set_ylabel("lat (°N)")
    _save(fig, "fig_cs1_riga_mask_sst_2021-07-16")

    # --- Mask comparison (SST anomaly + wind context) -----------------
    ano_16 = ds["sst_spatial_anomaly"].isel(time=t16_idx)
    wsp_16 = ds["wind_speed"].isel(time=t16_idx)

    fig, axes = plt.subplots(1, 2, figsize=(12, 5), sharey=True)
    # left: spatial anomaly with SST-mask contour
    ax = axes[0]
    ano_lim = float(np.abs(ano_16).max())
    pcm = ax.pcolormesh(ano_16.lon, ano_16.lat, ano_16.values,
                        cmap="RdBu_r", vmin=-ano_lim, vmax=ano_lim, shading="auto")
    ax.contour(mask_sst.lon, mask_sst.lat, mask_sst.values, levels=[0.5],
               colors="k", linewidths=1.0)
    fig.colorbar(pcm, ax=ax, label="SST anomaly (K)")
    ax.set_title("Spatial SST anomaly + SST-mask contour")
    ax.set_xlabel("lon (°E)")
    ax.set_ylabel("lat (°N)")
    # right: wind speed with SST-mask contour
    ax = axes[1]
    pcm2 = ax.pcolormesh(wsp_16.lon, wsp_16.lat, wsp_16.values,
                         cmap="YlOrRd", shading="auto")
    ax.contour(mask_sst.lon, mask_sst.lat, mask_sst.values, levels=[0.5],
               colors="k", linewidths=1.0)
    fig.colorbar(pcm2, ax=ax, label="wind speed (m s⁻¹)")
    ax.set_title("ERA5 daily mean wind speed + SST-mask contour")
    ax.set_xlabel("lon (°E)")
    fig.suptitle("CS1 — SST anomaly and wind context, 16 July 2021", y=1.02)
    plt.tight_layout()
    _save(fig, "fig_cs1_riga_mask_comparison_2021-07-16_v2")

    # --- Flagged-cells time series ------------------------------------
    sst_counts = ds["upwelling_mask_sst"].astype("uint8").sum(dim=("lat", "lon")).values
    wind_counts = ds["upwelling_mask_sst_wind"].astype("uint8").sum(dim=("lat", "lon")).values
    times = ds["time"].values

    fig, ax = plt.subplots(figsize=(8, 3.6))
    ax.plot(times, sst_counts,  marker="o", label="SST-only mask")
    ax.plot(times, wind_counts, marker="s", label="SST–wind intersection")
    ax.set_ylabel("flagged cells")
    ax.set_xlabel("date")
    ax.set_title("CS1 — daily flagged cell counts, Gulf of Riga")
    ax.legend()
    fig.autofmt_xdate()
    _save(fig, "fig_cs1_riga_flagged_cells_timeseries")

    # --- Provenance summary side-output --------------------------------
    props = stac["properties"]
    summary = {
        "pipeline_hash": props["mosaic:pipeline_hash"],
        "content_hash": props["mosaic:content_hash"],
        "n_flagged_sst": int(ds["upwelling_mask_sst"].astype("uint8").sum().values),
        "n_flagged_sst_wind": int(ds["upwelling_mask_sst_wind"].astype("uint8").sum().values),
        "n_total": int(ds["upwelling_mask_sst"].size),
        "panel_days": panel_days.tolist(),
    }
    (FIG_DIR / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
