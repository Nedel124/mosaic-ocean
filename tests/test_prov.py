"""Tests for the provenance subsystem."""

from __future__ import annotations

import numpy as np
import pandas as pd
import xarray as xr

from mosaic.prov import dataset_content_hash, pipeline_hash, text_hash


def _toy_ds(seed: int = 0) -> xr.Dataset:
    rng = np.random.default_rng(seed)
    arr = rng.standard_normal((3, 2, 2)).astype("float32")
    time = pd.date_range("2022-06-01", periods=3, freq="1D")
    return xr.Dataset(
        {"sst": (("time", "lat", "lon"), arr)},
        coords={"time": time, "lat": [54.0, 55.0], "lon": [14.0, 15.0]},
    )


def test_text_hash_is_stable() -> None:
    a = text_hash("hello")
    b = text_hash("hello")
    c = text_hash("Hello")
    assert a == b
    assert a != c
    assert ":" in a  # algorithm prefix


def test_pipeline_hash_changes_with_canonical_form() -> None:
    h1 = pipeline_hash("a: 1\nb: 2\n")
    h2 = pipeline_hash("a: 1\nb: 3\n")
    assert h1 != h2


def test_dataset_content_hash_is_deterministic() -> None:
    a = dataset_content_hash(_toy_ds(seed=0))
    b = dataset_content_hash(_toy_ds(seed=0))
    assert a == b


def test_dataset_content_hash_distinguishes_data() -> None:
    a = dataset_content_hash(_toy_ds(seed=0))
    b = dataset_content_hash(_toy_ds(seed=1))
    assert a != b


def test_dataset_content_hash_ignores_attribute_changes() -> None:
    ds = _toy_ds()
    a = dataset_content_hash(ds)
    ds.attrs["title"] = "with attrs"
    ds["sst"].attrs["long_name"] = "Sea Surface Temperature"
    b = dataset_content_hash(ds)
    assert a == b
