"""Re-render CS3 figures to ``docs/figures/cs3/*.png`` (and *.pdf)."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import xarray as xr

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ZARR = REPO_ROOT / "out" / "cs3_arctic_seaice_offline.zarr"
SIDECAR = OUTPUT_ZARR.with_suffix(OUTPUT_ZARR.suffix + ".stac.json")
FIG_DIR = REPO_ROOT / "docs" / "figures" / "cs3"


def _save(fig: plt.Figure, stem: str) -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG_DIR / f"{stem}.png", dpi=200, bbox_inches="tight")
    fig.savefig(FIG_DIR / f"{stem}.pdf", bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    if not OUTPUT_ZARR.exists():
        from tests.fixtures.build_cs3_fixtures import build_all

        build_all(REPO_ROOT / "tests" / "fixtures" / "cs3")
        import mosaic as ms

        ms.run(str(REPO_ROOT / "tests" / "fixtures" / "cs3_offline.yaml"))

    ds = xr.open_zarr(OUTPUT_ZARR, consolidated=True)
    with open(SIDECAR) as fh:
        stac = json.load(fh)

    plt.rcParams.update({"figure.dpi": 200, "font.size": 9})

    n = ds.sizes["time"]
    panel_days = np.linspace(0, n - 1, 4, dtype=int)

    # --- SIC evolution ------------------------------------------------
    fig, axes = plt.subplots(1, 4, figsize=(13, 3.4), sharey=True)
    for ax, t in zip(axes, panel_days, strict=False):
        sic = ds["sea_ice_area_fraction"].isel(time=t)
        pcm = ax.pcolormesh(
            sic.lon,
            sic.lat,
            sic.values,
            cmap="Blues_r",
            vmin=0.0,
            vmax=1.0,
            shading="auto",
        )
        ax.contour(sic.lon, sic.lat, sic.values, levels=[0.15, 0.5], colors="k", linewidths=0.6)
        ax.set_title(str(ds["time"].isel(time=t).values)[:10])
        ax.set_xlabel("lon (°E)")
    axes[0].set_ylabel("lat (°N)")
    fig.colorbar(pcm, ax=axes, fraction=0.025, pad=0.02, label="SIC (1)")
    fig.suptitle("CS3 — Arctic sea-ice concentration, Sept 2012", y=1.03)
    _save(fig, "fig_cs3_sic_evolution")

    # --- SIC anomaly --------------------------------------------------
    fig, axes = plt.subplots(1, 4, figsize=(13, 3.4), sharey=True)
    amax = float(np.abs(ds["sic_anomaly"]).max())
    for ax, t in zip(axes, panel_days, strict=False):
        a = ds["sic_anomaly"].isel(time=t)
        pcm = ax.pcolormesh(
            a.lon,
            a.lat,
            a.values,
            cmap="RdBu",
            vmin=-amax,
            vmax=amax,
            shading="auto",
        )
        ax.contour(a.lon, a.lat, a.values, levels=[-0.3], colors="k", linewidths=0.6)
        ax.set_title(str(ds["time"].isel(time=t).values)[:10])
        ax.set_xlabel("lon (°E)")
    axes[0].set_ylabel("lat (°N)")
    fig.colorbar(pcm, ax=axes, fraction=0.025, pad=0.02, label="SIC anomaly (1)")
    fig.suptitle("CS3 — SIC anomaly (Sept 2012 minus 1991-2020 climatology)", y=1.03)
    _save(fig, "fig_cs3_sic_anomaly")

    # --- Melt-pond proxy ----------------------------------------------
    fig, axes = plt.subplots(1, 4, figsize=(13, 3.4), sharey=True)
    for ax, t in zip(axes, panel_days, strict=False):
        m = ds["melt_pond_proxy"].isel(time=t).astype("uint8")
        ax.pcolormesh(m.lon, m.lat, m.values, cmap="Greys", vmin=0, vmax=1, shading="auto")
        ax.set_title(str(ds["time"].isel(time=t).values)[:10])
        ax.set_xlabel("lon (°E)")
    axes[0].set_ylabel("lat (°N)")
    fig.suptitle("CS3 — melt-pond proxy (SIC < 0.5 AND t2m > 273.15 K)", y=1.03)
    _save(fig, "fig_cs3_melt_pond")

    # --- Total ice area + flagged-cell time series --------------------
    # area per cell ~ d_lat * d_lon * cos(lat) * 111^2 km^2
    lat = ds["sea_ice_area_fraction"].lat.values
    dlon = float(np.diff(ds["sea_ice_area_fraction"].lon.values).mean())
    dlat = float(np.diff(lat).mean())
    cell_area = (dlon * 111.0) * (dlat * 111.0) * np.cos(np.deg2rad(lat))[:, None]
    sic_area_km2 = (ds["sea_ice_area_fraction"] * cell_area[None, :, :]).sum(
        dim=("lat", "lon")
    ).values * 1e-6  # in million km²
    flagged = ds["melt_pond_proxy"].astype("uint8").sum(dim=("lat", "lon")).values
    fig, ax1 = plt.subplots(figsize=(7.5, 3.6))
    ax2 = ax1.twinx()
    ax1.plot(ds["time"].values, sic_area_km2, color="tab:blue", label="ice area (10⁶ km²)")
    ax2.bar(
        ds["time"].values, flagged, color="tab:red", alpha=0.4, width=0.7, label="melt-pond cells"
    )
    ax1.set_ylabel("ice area (10⁶ km²)", color="tab:blue")
    ax2.set_ylabel("melt-pond proxy cells", color="tab:red")
    ax1.set_xlabel("date")
    fig.autofmt_xdate()
    ax1.set_title("CS3 — sectorial ice area and melt-pond proxy footprint")
    _save(fig, "fig_cs3_timeseries")

    # --- Provenance ---------------------------------------------------
    summary = {
        "pipeline_hash": stac["properties"]["mosaic:pipeline_hash"],
        "content_hash": stac["properties"]["mosaic:content_hash"],
        "n_flagged": int(ds["melt_pond_proxy"].astype("uint8").sum().values),
        "n_total": int(ds["melt_pond_proxy"].size),
        "panel_days": panel_days.tolist(),
        "mapping_accuracy": stac["properties"]["mosaic:harmonization"]["mapping_accuracy"],
        "sic_anomaly_min": float(ds["sic_anomaly"].min()),
    }
    (FIG_DIR / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
