"""End-to-end test for CS1 — Gulf of Riga upwelling, July 2021 (offline fixtures).

Runs :file:`tests/fixtures/cs1_gulf_of_riga_offline.yaml` against deterministic
local NetCDF fixtures shaped like the live CMEMS SST and ERA5 10 m wind inputs
used in the CS1 Gulf of Riga analysis. The test does not try to reproduce the
exact live-data counts reported in the paper (183 SST-anomaly cells and 3 cells
for the pixel-wise SST--wind intersection). Those values belong to the live
CMEMS--ERA5 notebook/pipeline. Instead, the offline test verifies that the same
processing logic is executable and reproducible without external credentials.

It verifies that:

* the harmonised SST and wind variables are present in the exported Zarr store,
* the Gulf-of-Riga derived variables are attached by the fuse stage,
* the SST-led upwelling mask fires somewhere on the synthetic fixture,
* the pixel-wise SST--wind mask is not larger than the SST-only mask,
* STAC/provenance metadata include pipeline and content hashes,
* two consecutive runs reproduce the same ``mosaic:content_hash``.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import xarray as xr

import mosaic as ms

REPO_ROOT = Path(__file__).resolve().parents[1]
PIPELINE = "tests/fixtures/cs1_gulf_of_riga_offline.yaml"
TARGET_DATE = "2021-07-16"


@pytest.fixture()
def cs1_workdir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    cs1_fixtures: dict[str, Path],
) -> Path:
    """Copy the offline pipeline + configs + fixtures into a temp working dir."""
    work = tmp_path / "run"
    work.mkdir()
    shutil.copytree(REPO_ROOT / "configs", work / "configs")
    shutil.copytree(REPO_ROOT / "tests" / "fixtures", work / "tests" / "fixtures")
    monkeypatch.chdir(work)
    return work


def _open_output(result: object) -> xr.Dataset:
    """Open the Zarr store returned by ``mosaic.run`` and validate sidecar output."""
    output = Path(result.output_path)
    assert output.exists(), f"missing output: {output}"

    sidecar = output.with_suffix(output.suffix + ".stac.json")
    assert sidecar.exists(), f"missing STAC sidecar: {sidecar}"

    return xr.open_zarr(output, consolidated=True)


def _first_existing(ds: xr.Dataset, *names: str) -> str:
    """Return the first variable name present in ``ds`` from a list of aliases."""
    for name in names:
        if name in ds.data_vars:
            return name
    raise AssertionError(f"missing all expected variables: {names}")


def test_cs1_gulf_of_riga_offline_pipeline_runs(cs1_workdir: Path) -> None:
    result = ms.run(PIPELINE)
    ds = _open_output(result)

    try:
        # 1. Harmonization recovered the canonical variables required by CS1.
        for var in (
            "sea_surface_temperature",
            "eastward_wind",
            "northward_wind",
        ):
            assert var in ds.data_vars, f"missing harmonized var: {var}"

        # 2. Derived variables expected for the Gulf of Riga workflow.
        # The aliases make the test tolerant of the final naming convention used
        # in the YAML, while still checking the CS1-specific logic.
        wind_speed_var = _first_existing(ds, "wind_speed")
        spatial_anom_var = _first_existing(
            ds,
            "sst_spatial_anomaly",
            "sst_anomaly_spatial",
            "sst_anomaly_daily_median",
        )
        sst_mask_var = _first_existing(
            ds,
            "upwelling_mask_sst",
            "upwelling_mask_spatial",
            "upwelling_mask",
        )
        combined_mask_var = _first_existing(
            ds,
            "upwelling_mask_sst_wind",
            "upwelling_mask_combined",
        )

        # 3. The key diagnostic date used in the paper is present.
        if "time" in ds.coords:
            selected = ds.sel(time=TARGET_DATE, method="nearest")
        else:
            selected = ds

        # 4. SST-led mask must fire on the fixture; the combined pixel-wise mask
        # should be a subset of the SST-led mask.
        sst_flagged = int(selected[sst_mask_var].astype("uint8").sum().values)
        combined_flagged = int(selected[combined_mask_var].astype("uint8").sum().values)

        assert sst_flagged > 0, "synthetic Gulf of Riga SST mask should fire"
        assert combined_flagged <= sst_flagged, (
            "pixel-wise SST--wind mask cannot contain more cells than SST-only mask"
        )

        # 5. The derived fields should have usable numeric content.
        assert float(selected[wind_speed_var].max()) >= 0.0
        assert float(selected[spatial_anom_var].min()) < 0.0

        # 6. STAC/provenance metadata carry hashes.
        props = result.provenance.properties
        assert "mosaic:pipeline_hash" in props
        assert "mosaic:content_hash" in props

        # 7. Mapping accuracy should remain high for fixture-based execution.
        assert result.harmonization_summary["mapping_accuracy"] >= 0.75

        # 8. Derive report contains the Gulf-of-Riga derived variables.
        derived_summary = result.harmonization_summary.get("derived", {})
        derived = set(derived_summary.get("derived", []))
        assert wind_speed_var in derived
        assert spatial_anom_var in derived
        assert sst_mask_var in derived
        assert combined_mask_var in derived
    finally:
        ds.close()


def test_cs1_gulf_of_riga_two_runs_same_content_hash(cs1_workdir: Path) -> None:
    a = ms.run(PIPELINE)
    b = ms.run(PIPELINE)
    assert (
        a.provenance.properties["mosaic:content_hash"]
        == b.provenance.properties["mosaic:content_hash"]
    )
