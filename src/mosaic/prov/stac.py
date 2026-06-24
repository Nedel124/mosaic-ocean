"""Build a STAC Item describing a MOSAIC pipeline run.

The Item uses two STAC extensions:

* ``processing`` (official) — software, lineage, processing level.
* ``mosaic``    (custom)    — pipeline / content hashes, mapping accuracy,
                              QC stats, environment fingerprint.

We construct the Item with the ``pystac`` builder so that it is compatible
with any STAC-aware tooling (``pystac-client``, ``stac-fastapi``, etc.).
"""
from __future__ import annotations

import platform
import sys
from datetime import UTC, datetime
from typing import Any

from pystac import Item

from mosaic._spec import PipelineSpec

MOSAIC_EXT_URL = "https://mosaic-ocean.org/stac/v1/schema.json"
PROCESSING_EXT_URL = "https://stac-extensions.github.io/processing/v1.1.0/schema.json"


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
    """Return a :class:`pystac.Item` for a single pipeline run."""
    bbox = list(spec.spec.domain.bbox)
    geom = _bbox_to_polygon(bbox)
    start = _to_datetime(spec.spec.domain.time.start)
    stop = _to_datetime(spec.spec.domain.time.stop)

    short_hash = pipeline_hash.split(":", 1)[-1][:12]
    item_id = f"{spec.metadata.name}_{start.strftime('%Y%m%d')}_{short_hash}"

    properties: dict[str, Any] = {
        "datetime": stop.isoformat(),
        "start_datetime": start.isoformat(),
        "end_datetime": stop.isoformat(),
        "processing:software": {"mosaic-ocean": _mosaic_version()},
        "processing:level": "L4",
        "processing:lineage": "Multi-source harmonization via MOSAIC pipeline.",
        "mosaic:pipeline_hash": pipeline_hash,
        "mosaic:content_hash": content_hash,
        "mosaic:inputs": inputs,
        "mosaic:harmonization": harmonization_summary,
        "mosaic:qc": qc_summary,
        "mosaic:environment": _environment_fingerprint(),
    }

    item = Item(
        id=item_id,
        geometry=geom,
        bbox=bbox,
        datetime=stop,
        properties=properties,
    )
    item.stac_extensions = [PROCESSING_EXT_URL, MOSAIC_EXT_URL]
    item.add_asset(
        "data",
        _asset(asset_href, asset_format, role="data"),
    )
    return item


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _to_datetime(s: str) -> datetime:
    if isinstance(s, datetime):
        return s if s.tzinfo else s.replace(tzinfo=UTC)
    # accept "YYYY-MM-DD" or full ISO
    try:
        return datetime.fromisoformat(s).replace(tzinfo=UTC)
    except ValueError:
        return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=UTC)


def _bbox_to_polygon(bbox: list[float]) -> dict[str, Any]:
    w, s, e, n = bbox
    return {
        "type": "Polygon",
        "coordinates": [
            [[w, s], [e, s], [e, n], [w, n], [w, s]],
        ],
    }


def _asset(href: str, fmt: str, *, role: str) -> Any:
    from pystac import Asset, MediaType

    media: str
    if fmt == "zarr":
        media = "application/vnd+zarr"
    elif fmt == "netcdf":
        media = MediaType.HDF5  # closest registered choice
    else:
        media = "application/octet-stream"
    return Asset(href=href, media_type=media, roles=[role])


def _mosaic_version() -> str:
    try:
        from mosaic import __version__

        return __version__
    except Exception:  # pragma: no cover - extremely defensive
        return "0.0.0+unknown"


def _environment_fingerprint() -> dict[str, str]:
    return {
        "python": sys.version.split()[0],
        "implementation": platform.python_implementation(),
        "os": f"{platform.system()} {platform.release()}",
        "machine": platform.machine(),
    }
