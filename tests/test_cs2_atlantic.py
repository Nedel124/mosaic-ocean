"""End-to-end test for CS2 — Atlantic hurricane (Ida-like), Aug-Sep 2021."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import xarray as xr

import mosaic as ms

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def cs2_workdir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    cs2_fixtures: dict[str, Path],
) -> Path:
    """Copy the offline pipeline + configs + fixtures into a temp working dir."""
    work = tmp_path / "run"
    work.mkdir()
    shutil.copytree(REPO_ROOT / "configs", work / "configs")
    shutil.copytree(REPO_ROOT / "tests" / "fixtures", work / "tests" / "fixtures")
    monkeypatch.chdir(work)
    return work


def test_cs2_offline_pipeline_runs(cs2_workdir: Path) -> None:
    result = ms.run("tests/fixtures/cs2_offline.yaml")

    output = Path(result.output_path)
    assert output.exists(), f"missing output: {output}"
    ds = xr.open_zarr(output, consolidated=True)

    # Harmonization recovered the canonical CF names.
    for var in (
        "sea_surface_temperature",
        "eastward_wind",
        "northward_wind",
        "air_pressure_at_mean_sea_level",
        "precipitation_amount",
    ):
        assert var in ds.data_vars, f"missing harmonized var: {var}"

    # Derived variables were added by the fuse pass.
    for var in ("wind_speed", "storm_intensity", "hurricane_zone"):
        assert var in ds.data_vars, f"missing derived var: {var}"

    # Hurricane zone actually fires — synthetic Ida-like landfall produces
    # cells that simultaneously satisfy wind > 17 m/s and MSLP < 980 hPa.
    flagged = int(ds["hurricane_zone"].astype("uint8").sum().values)
    assert flagged > 0, "synthetic hurricane should produce flagged cells"

    # Storm intensity is positive somewhere (i.e. low-pressure anomaly exists).
    assert float(ds["storm_intensity"].max()) > 30.0

    # STAC sidecar carries pipeline + content hashes.
    sidecar = output.with_suffix(output.suffix + ".stac.json")
    assert sidecar.exists()
    props = result.provenance.properties
    assert "mosaic:pipeline_hash" in props
    assert "mosaic:content_hash" in props

    # All five source variables map cleanly through override + dictionary tiers.
    assert result.harmonization_summary["mapping_accuracy"] == 1.0

    # Derive report records all three derived variables.
    derived_summary = result.harmonization_summary.get("derived", {})
    assert sorted(derived_summary.get("derived", [])) == [
        "hurricane_zone",
        "storm_intensity",
        "wind_speed",
    ]

    ds.close()


def test_cs2_two_runs_same_content_hash(cs2_workdir: Path) -> None:
    a = ms.run("tests/fixtures/cs2_offline.yaml")
    b = ms.run("tests/fixtures/cs2_offline.yaml")
    assert (
        a.provenance.properties["mosaic:content_hash"]
        == b.provenance.properties["mosaic:content_hash"]
    )
