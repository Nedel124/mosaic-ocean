"""Source plugins. Each plugin implements :class:`Source`.

Built-in plugins exposed here:

- :class:`DummySource` — synthetic dataset for tests and tutorials.
- :class:`LocalNetcdfSource` — read an on-disk NetCDF/Zarr file or glob.
- :class:`CmemsSource` — Copernicus Marine subset via the ``copernicusmarine``
  toolbox (requires the ``copernicus`` optional extra).
- :class:`Era5Source` — ERA5 retrieval via the CDS ``cdsapi`` client
  (requires the ``cds`` optional extra).

CMEMS and ERA5 are imported eagerly so their plugin names are registered;
their *network* paths import ``copernicusmarine`` / ``cdsapi`` lazily inside
:meth:`fetch`, so users without those extras can still load and validate
pipelines, and run cache-only fixtures.
"""

from __future__ import annotations

from mosaic.sources.base import Source, SourceQuery, SourceRegistry, register, registry
from mosaic.sources.cmems import CmemsSource
from mosaic.sources.dummy import DummySource
from mosaic.sources.era5 import Era5Source
from mosaic.sources.local import LocalNetcdfSource

__all__ = [
    "CmemsSource",
    "DummySource",
    "Era5Source",
    "LocalNetcdfSource",
    "Source",
    "SourceQuery",
    "SourceRegistry",
    "register",
    "registry",
]
