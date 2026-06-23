"""Deterministic content hashing.

The strategy chosen here is the *kerchunk-style* canonical-bytes approach:

* For text artefacts (pipeline YAML), we hash the canonical YAML serialisation
  produced by :meth:`PipelineSpec.canonical_yaml` after ``model_dump(by_alias=True)``.
* For datasets, we hash a deterministic bytestream built from the variables
  in lexicographic order: name, shape, dtype, then raw bytes. We deliberately
  avoid numerical operations that would introduce floating-point sensitivity
  (no resampling at hash time).
* The hash function is BLAKE3 when available, falling back to SHA-256 so that
  unit tests still run on minimal CI.

This module is the place where decision #6 from the briefing will be resolved
empirically. The current implementation is the baseline; alternative dumpers
(zarr consolidated metadata, custom canonical writer) will be benchmarked
against it before ``v0.1.0``.
"""
from __future__ import annotations

import hashlib
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import numpy as np
import xarray as xr

try:
    import blake3 as _blake3

    _HAVE_BLAKE3 = True
except Exception:  # pragma: no cover - import-time fallback
    _HAVE_BLAKE3 = False


def _hasher() -> Any:
    """Return a fresh hasher (BLAKE3 preferred, SHA-256 fallback)."""
    if _HAVE_BLAKE3:
        return _blake3.blake3()
    return hashlib.sha256()


def _label() -> str:
    return "blake3" if _HAVE_BLAKE3 else "sha256"


def text_hash(text: str) -> str:
    """Return a hex digest of ``text`` (UTF-8 encoded)."""
    h = _hasher()
    h.update(text.encode("utf-8"))
    return f"{_label()}:{h.hexdigest()}"


def pipeline_hash(canonical_yaml: str) -> str:
    """Hash the canonical YAML form of a :class:`PipelineSpec`."""
    return text_hash(canonical_yaml)


def dataset_content_hash(ds: xr.Dataset) -> str:
    """Deterministic content hash for an :class:`xarray.Dataset`.

    The order of variables and coordinates is normalised. Within each array,
    raw bytes are emitted in C order. Attribute differences do **not** affect
    the content hash — only data and shape do.
    """
    h = _hasher()
    for name in sorted(ds.coords):
        _hash_array(h, name, ds.coords[name].values)
    for name in sorted(ds.data_vars):
        _hash_array(h, name, ds[name].values)
    return f"{_label()}:{h.hexdigest()}"


def file_hash(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    """Stream-hash a file on disk."""
    h = _hasher()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(chunk_size), b""):
            h.update(chunk)
    return f"{_label()}:{h.hexdigest()}"


# ---------------------------------------------------------------------------
# private helpers
# ---------------------------------------------------------------------------


def _hash_array(hasher: Any, name: str, arr: np.ndarray) -> None:
    hasher.update(b"\x00name=")
    hasher.update(name.encode("utf-8"))
    hasher.update(b"\x00dtype=")
    hasher.update(str(arr.dtype).encode("utf-8"))
    hasher.update(b"\x00shape=")
    hasher.update(repr(tuple(arr.shape)).encode("utf-8"))
    hasher.update(b"\x00data=")
    if arr.dtype.kind in {"U", "O"}:
        # Object/string arrays: serialise element-by-element to avoid
        # platform-dependent NumPy buffer layouts.
        for item in _flatten(arr):
            hasher.update(repr(item).encode("utf-8"))
            hasher.update(b"|")
    elif arr.dtype.kind == "M":  # datetime64
        hasher.update(arr.astype("datetime64[ns]").astype("int64").tobytes(order="C"))
    else:
        hasher.update(np.ascontiguousarray(arr).tobytes(order="C"))


def _flatten(arr: np.ndarray) -> Iterable[Any]:
    if arr.ndim == 0:
        yield arr.item()
        return
    yield from arr.reshape(-1).tolist()
