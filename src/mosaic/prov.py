"""Provenance utilities: content-addressable hashing and STAC Item construction."""

from __future__ import annotations

import platform
import sys
from datetime import datetime
from typing import TYPE_CHECKING, Any

import blake3
import numpy as np
import xarray as xr
from pystac import Asset, Item

if TYPE_CHECKING:
    from mosaic._spec import PipelineSpec

_ALGORITHM = "blake3"


def text_hash(text: str) -> str:
    """Return ``blake3:<hex>`` hash of a UTF-8 string."""
    digest = blake3.blake3(text.encode("utf-8")).hexdigest()
    return f"{_ALGORITHM}:{digest}"


def pipeline_hash(canonical_yaml: str) -> str:
    """Stable hash of the canonical YAML form of a PipelineSpec."""
    return text_hash(canonical_yaml)


def dataset_content_hash(ds: xr.Dataset) -> str:
    """Hash the data values of every variable in *ds* (attrs are ignored).

    Variables are processed in sorted name order so the result is independent
    of the order in which variables were added to the dataset.
    """
    h = blake3.blake3()
    for name in sorted(str(k) for k in ds.data_vars):
        arr: np.ndarray = np.asarray(ds[name].values)
        h.update(name.encode("utf-8"))
        h.update(arr.tobytes())
    return f"{_ALGORITHM}:{h.hexdigest()}"


def build_stac_item(
    *,
    spec: PipelineSpec,
    pipeline_hash: str,
    content_hash: str,
    inputs: list[dict[str, Any]],
    harmonization_summary: dict[str, Any],
    qc_summary: dict[str, Any],
    asset_href: str,
    asset_format: str,
) -> Item:
    """Build a pystac Item representing a single MOSAIC pipeline run."""
    bbox = list(spec.spec.domain.bbox)
    w, s, e, n = bbox
    geometry: dict[str, Any] = {
        "type": "Polygon",
        "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]],
    }

    start_dt = _parse_iso(spec.spec.domain.time.start)
    stop_dt = _parse_iso(spec.spec.domain.time.stop)
    mid = start_dt + (stop_dt - start_dt) / 2

    hex_suffix = content_hash.split(":")[-1][:12]
    item_id = f"{spec.metadata.name}-{hex_suffix}"

    media_type = "application/vnd.zarr" if asset_format == "zarr" else "application/netcdf"

    properties: dict[str, Any] = {
        "datetime": mid.isoformat() + "Z",
        "start_datetime": start_dt.isoformat() + "Z",
        "end_datetime": stop_dt.isoformat() + "Z",
        "mosaic:pipeline_hash": pipeline_hash,
        "mosaic:content_hash": content_hash,
        "mosaic:pipeline_name": spec.metadata.name,
        "mosaic:inputs": inputs,
        "mosaic:harmonization": harmonization_summary,
        "mosaic:qc": qc_summary,
        "mosaic:environment": _environment(),
    }

    item = Item(
        id=item_id,
        geometry=geometry,
        bbox=bbox,
        datetime=mid,
        properties=properties,
        stac_extensions=["https://stac-extensions.github.io/mosaic/v1.0.0/schema.json"],
    )
    item.add_asset("data", Asset(href=asset_href, media_type=media_type, roles=["data"]))
    return item


def _parse_iso(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.strptime(value, "%Y-%m-%d")


def _environment() -> dict[str, Any]:
    return {
        "python": sys.version,
        "platform": platform.platform(),
        "xarray": xr.__version__,
        "numpy": np.__version__,
    }
