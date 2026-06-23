"""End-to-end tests for the programmatic Pipeline builder and the YAML runner."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import xarray as xr

import mosaic as ms


@pytest.fixture()
def tmp_workdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_programmatic_pipeline_runs(tmp_workdir: Path) -> None:
    pipe = (
        ms.Pipeline(name="demo")
        .domain(bbox=(14.0, 54.0, 22.0, 60.0), time_start="2022-06-01", time_stop="2022-06-03")
        .add_source(ms.sources.DummySource(variables=["sst", "u10"]))
        .harmonize()
        .qc(rules={"sea_surface_temperature": {"type": "range", "min": -2.0, "max": 35.0}})
        .export(path=str(tmp_workdir / "out.zarr"))
    )
    result = pipe.run()
    assert Path(result.output_path).exists()
    assert result.harmonization_summary["mapping_accuracy"] > 0.0
    assert "mosaic:pipeline_hash" in result.provenance.properties
    assert "mosaic:content_hash" in result.provenance.properties
    sidecar = Path(result.output_path).with_suffix(".zarr.stac.json")
    assert sidecar.exists()


def test_runner_from_yaml_minimal_example(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Run the shipped example_minimal.yaml from a temp working directory."""
    repo_root = Path(__file__).resolve().parents[1]
    work = tmp_path / "run"
    work.mkdir()
    # Copy the example pipeline + configs so relative paths resolve in tmp.
    shutil.copytree(repo_root / "configs", work / "configs")
    shutil.copytree(repo_root / "pipelines", work / "pipelines")
    monkeypatch.chdir(work)

    result = ms.run("pipelines/example_minimal.yaml")
    assert "mosaic:pipeline_hash" in result.provenance.properties
    ds = xr.open_zarr(result.output_path, consolidated=True)
    assert "sea_surface_temperature" in ds.data_vars
    ds.close()


def test_two_runs_produce_identical_content_hash(tmp_path: Path) -> None:
    """Determinism test: two builders with the same inputs produce the same content hash."""
    out1 = tmp_path / "a.zarr"
    out2 = tmp_path / "b.zarr"

    def _build(out: Path) -> ms.Result:
        return (
            ms.Pipeline(name="determ")
            .domain(bbox=(14.0, 54.0, 22.0, 60.0), time_start="2022-06-01", time_stop="2022-06-03")
            .add_source(ms.sources.DummySource(variables=["sst"], seed=0))
            .harmonize()
            .export(path=str(out))
            .run()
        )

    a = _build(out1)
    b = _build(out2)
    assert (
        a.provenance.properties["mosaic:content_hash"]
        == b.provenance.properties["mosaic:content_hash"]
    )
