"""Tests for the pipeline schema (mosaic._spec)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from mosaic._spec import PipelineSpec

VALID_DOC: dict = {
    "apiVersion": "mosaic/v1",
    "kind": "Pipeline",
    "metadata": {"name": "demo"},
    "spec": {
        "domain": {
            "bbox": [14.0, 54.0, 22.0, 60.0],
            "time": {"start": "2022-06-01", "stop": "2022-06-07"},
        },
        "sources": [{"id": "dummy", "plugin": "dummy", "params": {"variables": ["sst"]}}],
        "export": {"format": "zarr", "path": "out/demo.zarr"},
    },
}


def test_valid_pipeline_parses() -> None:
    spec = PipelineSpec.model_validate(VALID_DOC)
    assert spec.metadata.name == "demo"
    assert spec.spec.sources[0].plugin == "dummy"
    assert spec.spec.export.format == "zarr"


def test_canonical_yaml_is_deterministic() -> None:
    a = PipelineSpec.model_validate(VALID_DOC).canonical_yaml()
    b = PipelineSpec.model_validate(VALID_DOC).canonical_yaml()
    assert a == b


def test_bbox_must_be_valid() -> None:
    bad = dict(VALID_DOC)
    bad["spec"] = dict(bad["spec"])
    bad["spec"]["domain"] = {
        "bbox": [10, 60, 5, 50],
        "time": {"start": "2022-06-01", "stop": "2022-06-02"},
    }
    with pytest.raises(ValidationError):
        PipelineSpec.model_validate(bad)


def test_duplicate_source_ids_rejected() -> None:
    bad = {
        **VALID_DOC,
        "spec": {
            **VALID_DOC["spec"],
            "sources": [
                {"id": "x", "plugin": "dummy"},
                {"id": "x", "plugin": "dummy"},
            ],
        },
    }
    with pytest.raises(ValidationError):
        PipelineSpec.model_validate(bad)


def test_target_grid_exclusive() -> None:
    bad = {
        **VALID_DOC,
        "spec": {
            **VALID_DOC["spec"],
            "harmonize": {"target_grid": {"from": "dummy", "resolution_deg": 0.25}},
        },
    }
    with pytest.raises(ValidationError):
        PipelineSpec.model_validate(bad)
