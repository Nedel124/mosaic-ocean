"""End-to-end test for CS3 — Arctic sea-ice retreat, September 2012."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import xarray as xr

import mosaic as ms


REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def cs3_workdir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    cs3_fixtures: dict[str, Path],
) -> Path:
    work = tmp_path / "run"
    work.mkdir()
    shutil.copytree(REPO_ROOT / "configs", work / "configs")
    shutil.copytree(REPO_ROOT / "tests" / "fixtures", work / "tests" / "fixtures")
    monkeypatch.chdir(work)
    return work


def test_cs3_offline_pipeline_runs(cs3_workdir: Path) -> None:
    result = ms.run("tests/fixtures/cs3_offline.yaml")

    output = Path(result.output_path)
    assert output.exists(), f"missing output: {output}"
    ds = xr.open_zarr(output, consolidated=True)

    # Harmonization recovered the canonical CF names.
    for var in (
        "sea_ice_area_fraction",
        "sea_ice_area_fraction_climatology",
        "air_temperature",
        "air_pressure_at_mean_sea_level",
    ):
        assert var in ds.data_vars, f"missing harmonized var: {var}"

    # Derived variables were added by the fuse pass.
    for var in ("sic_anomaly", "melt_pond_proxy"):
        assert var in ds.data_vars, f"missing derived var: {var}"

    # Melt-pond proxy fires somewhere — synthetic event has below-50% ice
    # combined with above-freezing air over the southern part of the domain.
    flagged = int(ds["melt_pond_proxy"].astype("uint8").sum().values)
    assert flagged > 0, "synthetic Sep-2012 retreat should flag melt cells"

    # The retreat manifests as a meaningfully negative anomaly somewhere.
    assert float(ds["sic_anomaly"].min()) < -0.3

    # STAC sidecar carries pipeline + content hashes.
    sidecar = output.with_suffix(output.suffix + ".stac.json")
    assert sidecar.exists()
    props = result.provenance.properties
    assert "mosaic:pipeline_hash" in props
    assert "mosaic:content_hash" in props

    # Override + dictionary tiers cover everything in this fixture.
    assert result.harmonization_summary["mapping_accuracy"] == 1.0

    derived_summary = result.harmonization_summary.get("derived", {})
    assert sorted(derived_summary.get("derived", [])) == ["melt_pond_proxy", "sic_anomaly"]

    ds.close()


def test_cs3_two_runs_same_content_hash(cs3_workdir: Path) -> None:
    a = ms.run("tests/fixtures/cs3_offline.yaml")
    b = ms.run("tests/fixtures/cs3_offline.yaml")
    assert (
        a.provenance.properties["mosaic:content_hash"]
        == b.provenance.properties["mosaic:content_hash"]
    )
