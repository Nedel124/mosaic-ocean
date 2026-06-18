"""Programmatic builder for ``cs1_gulf_of_riga_upwelling.ipynb``.

This script generates a Jupyter notebook that loads the CS1 pipeline output
(produced by ``mosaic run tests/fixtures/cs1_gulf_of_riga_offline.yaml``) and
reproduces the figures used in the Results section of the CAGEO paper.

Run from the repository root:

    python notebooks/_build_cs1_notebook.py
"""

from __future__ import annotations

from pathlib import Path

import nbformat as nbf

NB_PATH = Path(__file__).resolve().parent / "cs1_gulf_of_riga_upwelling.ipynb"
REPO_ROOT = Path(__file__).resolve().parents[1]


def md(text: str) -> nbf.NotebookNode:
    return nbf.v4.new_markdown_cell(text)


def code(src: str) -> nbf.NotebookNode:
    return nbf.v4.new_code_cell(src)


def build() -> nbf.NotebookNode:
    nb = nbf.v4.new_notebook()
    nb.metadata = {
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        },
        "language_info": {"name": "python", "pygments_lexer": "ipython3"},
        "mosaic": {
            "case_study": "CS1 — Gulf of Riga upwelling, July 2021",
            "pipeline": "tests/fixtures/cs1_gulf_of_riga_offline.yaml",
            "purpose": "Companion notebook for CAGEO Results section",
        },
    }

    cells: list[nbf.NotebookNode] = []

    # 1. Title + scope ---------------------------------------------------
    cells.append(
        md(
            "# CS1 — Gulf of Riga coastal upwelling, July 2021\n"
            "\n"
            "Companion notebook for the *Computers & Geosciences* paper "
            "*An Open Python Framework for Reproducible Multi-Source Ocean Data "
            "Integration*. It loads the Zarr output produced by the offline "
            "fixture pipeline (`tests/fixtures/cs1_gulf_of_riga_offline.yaml`) and "
            "reproduces the figures used in the Results section.\n"
            "\n"
            "**Reproducibility contract.** Re-running this notebook from a fresh "
            "checkout regenerates the identical content hash printed in the final "
            "section. The pipeline is declarative (YAML) and the data sources are "
            "deterministic Gulf-of-Riga-shaped fixtures that ship with the "
            "repository, so no external credentials are required."
        )
    )

    # 2. Bootstrap -------------------------------------------------------
    cells.append(md("## 1. Bootstrap — run the pipeline if its output is missing"))
    cells.append(
        code(
            "from __future__ import annotations\n"
            "\n"
            "import json\n"
            "import os\n"
            "from pathlib import Path\n"
            "\n"
            "# Resolve the repository root regardless of where the notebook is launched.\n"
            "NB_DIR = Path.cwd()\n"
            "if NB_DIR.name == 'notebooks':\n"
            "    REPO_ROOT = NB_DIR.parent\n"
            "else:\n"
            "    REPO_ROOT = NB_DIR\n"
            "os.chdir(REPO_ROOT)\n"
            "\n"
            "PIPELINE = Path('tests/fixtures/cs1_gulf_of_riga_offline.yaml')\n"
            "OUTPUT   = Path('out/cs1_gulf_of_riga_upwelling_offline.zarr')\n"
            "SIDECAR  = OUTPUT.with_suffix(OUTPUT.suffix + '.stac.json')\n"
            "\n"
            "if not OUTPUT.exists():\n"
            "    # Build synthetic fixtures (deterministic) and run the pipeline.\n"
            "    from tests.fixtures.build_cs1_gulf_of_riga_fixtures import build_all\n"
            "    build_all(REPO_ROOT / 'tests' / 'fixtures' / 'cs1_gulf_of_riga')\n"
            "    import mosaic as ms\n"
            "    ms.run(str(PIPELINE))\n"
            "\n"
            "print(f'output: {OUTPUT} ({OUTPUT.exists()})')\n"
            "print(f'sidecar: {SIDECAR} ({SIDECAR.exists()})')"
        )
    )

    # 3. Load ------------------------------------------------------------
    cells.append(md("## 2. Load the integrated dataset and its provenance sidecar"))
    cells.append(
        code(
            "import xarray as xr\n"
            "\n"
            "ds = xr.open_zarr(OUTPUT, consolidated=True)\n"
            "with open(SIDECAR) as fh:\n"
            "    stac = json.load(fh)\n"
            "\n"
            "print(ds)"
        )
    )
    cells.append(
        code(
            "props = stac['properties']\n"
            "summary = {\n"
            "    'pipeline_hash': props['mosaic:pipeline_hash'],\n"
            "    'content_hash':  props['mosaic:content_hash'],\n"
            "    'sources':       [s['source_id'] for s in props['mosaic:inputs']],\n"
            "    'mapping_accuracy': props['mosaic:harmonization']['mapping_accuracy'],\n"
            "    'derived_variables': props['mosaic:harmonization']['derived']['derived'],\n"
            "}\n"
            "summary"
        )
    )

    # 4. SST evolution maps ---------------------------------------------
    cells.append(
        md(
            "## 3. SST evolution\n"
            "\n"
            "Four-panel snapshot of `sea_surface_temperature` showing the thermal "
            "structure in the Gulf of Riga over 12--22 July 2021, providing context "
            "for the cold-water feature detected on 16 July."
        )
    )
    cells.append(
        code(
            "import matplotlib.pyplot as plt\n"
            "import numpy as np\n"
            "\n"
            "plt.rcParams.update({'figure.dpi': 110, 'font.size': 9})\n"
            "\n"
            "def _panel_days(ds, n_panels=4):\n"
            "    n = ds.sizes['time']\n"
            "    return np.linspace(0, n - 1, n_panels, dtype=int)\n"
            "\n"
            "panel_days = _panel_days(ds)\n"
            "panel_days"
        )
    )
    cells.append(
        code(
            "fig, axes = plt.subplots(1, 4, figsize=(13, 3.4), sharey=True)\n"
            "sst_c = ds['sea_surface_temperature'] - 273.15\n"
            "vmin, vmax = float(sst_c.min()), float(sst_c.max())\n"
            "for ax, t_idx in zip(axes, panel_days):\n"
            "    sst = sst_c.isel(time=t_idx)\n"
            "    pcm = ax.pcolormesh(\n"
            "        sst.lon, sst.lat, sst.values,\n"
            "        cmap='RdYlBu_r', vmin=vmin, vmax=vmax, shading='auto',\n"
            "    )\n"
            "    ax.set_title(str(ds['time'].isel(time=t_idx).values)[:10])\n"
            "    ax.set_xlabel('lon (°E)')\n"
            "axes[0].set_ylabel('lat (°N)')\n"
            "fig.colorbar(pcm, ax=axes, fraction=0.025, pad=0.02, label='SST (°C)')\n"
            "fig.suptitle('CS1 — Gulf of Riga SST (CMEMS L4, harmonised)', y=1.02)\n"
            "plt.show()"
        )
    )

    # 5. Spatial SST anomaly maps ----------------------------------------
    cells.append(
        md(
            "## 4. Spatial SST anomaly\n"
            "\n"
            "`sst_spatial_anomaly = sea_surface_temperature − "
            "sea_surface_temperature_daily_spatial_median` is added in the *fuse* "
            "step. Negative values identify parts of the Gulf that are anomalously "
            "cold relative to the basin-scale daily median."
        )
    )
    cells.append(
        code(
            "fig, axes = plt.subplots(1, 4, figsize=(13, 3.4), sharey=True)\n"
            "ano_max = float(np.abs(ds['sst_spatial_anomaly']).max())\n"
            "for ax, t_idx in zip(axes, panel_days):\n"
            "    ano = ds['sst_spatial_anomaly'].isel(time=t_idx)\n"
            "    pcm = ax.pcolormesh(\n"
            "        ano.lon, ano.lat, ano.values,\n"
            "        cmap='RdBu_r', vmin=-ano_max, vmax=ano_max, shading='auto',\n"
            "    )\n"
            "    ax.contour(\n"
            "        ano.lon, ano.lat, ano.values,\n"
            "        levels=[-2.0], colors='k', linewidths=0.6,\n"
            "    )\n"
            "    ax.set_title(str(ds['time'].isel(time=t_idx).values)[:10])\n"
            "    ax.set_xlabel('lon (°E)')\n"
            "axes[0].set_ylabel('lat (°N)')\n"
            "fig.colorbar(pcm, ax=axes, fraction=0.025, pad=0.02, label='SST anomaly (K)')\n"
            "fig.suptitle('CS1 — Spatial SST anomaly (SST − daily median), -2 K contour overlaid', y=1.02)\n"
            "plt.show()"
        )
    )

    # 6. Wind quiver -----------------------------------------------------
    cells.append(
        md(
            "## 5. Wind regime\n"
            "\n"
            "ERA5 10 m winds (`eastward_wind`, `northward_wind`) overlaid on the "
            "SST field for 16 July 2021. The pipeline derives `wind_speed` from the "
            "components, used in the downstream pixel-wise SST--wind intersection mask."
        )
    )
    cells.append(
        code(
            "import pandas as pd\n"
            "t16_idx = int(np.argmin(np.abs(\n"
            "    pd.to_datetime(ds['time'].values) - pd.Timestamp('2021-07-16')\n"
            ")))\n"
            "\n"
            "step = 2\n"
            "u = ds['eastward_wind'].isel(time=t16_idx)\n"
            "v = ds['northward_wind'].isel(time=t16_idx)\n"
            "sst_day = ds['sea_surface_temperature'].isel(time=t16_idx) - 273.15\n"
            "\n"
            "fig, ax = plt.subplots(figsize=(7.5, 5.0))\n"
            "pcm = ax.pcolormesh(\n"
            "    sst_day.lon, sst_day.lat, sst_day.values,\n"
            "    cmap='RdYlBu_r', shading='auto',\n"
            ")\n"
            "ax.quiver(\n"
            "    u.lon[::step], u.lat[::step],\n"
            "    u.values[::step, ::step], v.values[::step, ::step],\n"
            "    scale=40, color='k', alpha=0.75,\n"
            ")\n"
            "ax.set_title('CS1 — SST + 10 m wind, 16 July 2021')\n"
            "ax.set_xlabel('lon (°E)')\n"
            "ax.set_ylabel('lat (°N)')\n"
            "fig.colorbar(pcm, ax=ax, label='SST (°C)')\n"
            "plt.show()"
        )
    )

    # 7. Upwelling masks -------------------------------------------------
    cells.append(
        md(
            "## 6. Upwelling masks\n"
            "\n"
            "Two masks are derived:\n"
            "- `upwelling_mask_sst` = `sst_spatial_anomaly < -2 K` (SST-only footprint)\n"
            "- `upwelling_mask_sst_wind` = `(sst_spatial_anomaly < -2 K) & (wind_speed > 4 m s⁻¹)`\n"
            "  (pixel-wise intersection — empty on 16 July 2021 in the live workflow)\n"
        )
    )
    cells.append(
        code(
            "mask_sst  = ds['upwelling_mask_sst'].isel(time=t16_idx).astype('uint8')\n"
            "mask_both = ds['upwelling_mask_sst_wind'].isel(time=t16_idx).astype('uint8')\n"
            "\n"
            "fig, axes = plt.subplots(1, 2, figsize=(10, 4), sharey=True)\n"
            "for ax, m, title in zip(\n"
            "    axes,\n"
            "    [mask_sst, mask_both],\n"
            "    ['SST-only mask (anomaly < -2 K)',\n"
            "     'SST–wind intersection (anomaly < -2 K & wind > 4 m s⁻¹)'],\n"
            "):\n"
            "    ax.pcolormesh(m.lon, m.lat, m.values, cmap='Greys', vmin=0, vmax=1, shading='auto')\n"
            "    ax.set_title(title)\n"
            "    ax.set_xlabel('lon (°E)')\n"
            "axes[0].set_ylabel('lat (°N)')\n"
            "fig.suptitle('CS1 — upwelling masks, 16 July 2021', y=1.02)\n"
            "plt.tight_layout()\n"
            "plt.show()\n"
            "\n"
            "print(f'SST-only mask: {int(mask_sst.sum().values)} cells flagged')\n"
            "print(f'SST–wind mask: {int(mask_both.sum().values)} cells flagged')"
        )
    )

    # 8. Time series of flagged cells ------------------------------------
    cells.append(
        md(
            "## 7. Temporal evolution of flagged cells\n"
            "\n"
            "Daily counts of grid cells satisfying each mask over the full CS1 "
            "window. This summarises the difference between the spatial SST "
            "footprint and the more restrictive local SST--wind overlap."
        )
    )
    cells.append(
        code(
            "sst_counts  = ds['upwelling_mask_sst'].astype('uint8').sum(dim=('lat', 'lon')).values\n"
            "wind_counts = ds['upwelling_mask_sst_wind'].astype('uint8').sum(dim=('lat', 'lon')).values\n"
            "times = ds['time'].values\n"
            "\n"
            "fig, ax = plt.subplots(figsize=(8, 3.6))\n"
            "ax.plot(times, sst_counts,  marker='o', label='SST-only mask')\n"
            "ax.plot(times, wind_counts, marker='s', label='SST–wind intersection')\n"
            "ax.set_ylabel('flagged cells')\n"
            "ax.set_xlabel('date')\n"
            "ax.set_title('CS1 — daily flagged cell counts, Gulf of Riga')\n"
            "ax.legend()\n"
            "fig.autofmt_xdate()\n"
            "plt.show()"
        )
    )

    # 9. Provenance ----------------------------------------------------
    cells.append(
        md(
            "## 8. Provenance — content addressing of the result\n"
            "\n"
            "Every MOSAIC run emits a STAC sidecar that pins the exact pipeline "
            "and the bit-exact output. The hashes below should match across "
            "machines and Python versions when the fixture-based pipeline is used."
        )
    )
    cells.append(
        code(
            "for k in ('mosaic:pipeline_hash', 'mosaic:content_hash'):\n"
            "    print(f'{k:<25} {props[k]}')\n"
            "\n"
            "print()\n"
            "print('inputs:')\n"
            "for inp in props['mosaic:inputs']:\n"
            "    print(f\"  - {inp['source_id']:<10} {inp['plugin']:<14} {inp.get('uri', '')}\")\n"
            "\n"
            "print()\n"
            "print('derived:')\n"
            "for d in props['mosaic:harmonization']['derived']['derived']:\n"
            "    print(f'  + {d}')"
        )
    )
    cells.append(
        md(
            "---\n"
            "*Notebook generated by `notebooks/_build_cs1_notebook.py`. Do not "
            "edit by hand — regenerate from the script to keep the build auditable.*"
        )
    )

    nb.cells = cells
    return nb


def main() -> None:
    nb = build()
    NB_PATH.write_text(nbf.writes(nb), encoding="utf-8")
    print(f"wrote {NB_PATH}")


if __name__ == "__main__":
    main()
