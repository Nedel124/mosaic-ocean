"""Read-from-disk source plugin.

:class:`LocalNetcdfSource` opens a single NetCDF file (or a glob) with
:func:`xarray.open_dataset` / :func:`xarray.open_mfdataset` and slices it to
the bbox / time / variables requested by the pipeline. It serves two roles:

1. *Primary* source for users who already maintain a local archive of
   NetCDF/Zarr files (typical of operational installations).
2. *Cache backend* for the live API connectors (CMEMS, ERA5): on a cache
   hit they delegate to this class instead of calling the network. The
   provenance entry recorded in STAC is identical regardless of whether
   the bytes came from the network this run or from disk — only the
   ``source_uri`` field differs.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd
import xarray as xr

from mosaic.sources.base import Source, SourceQuery, register


@register
class LocalNetcdfSource(Source):
    """Read a NetCDF (or Zarr) file from the local filesystem.

    Parameters in the YAML pipeline:

    .. code-block:: yaml

        sources:
          - id: cmems_sst
            plugin: local_netcdf
            params:
              path: tests/fixtures/cs1_gulf_of_riga/cmems_gulf_of_riga_sst_2021-07.nc
              variables: [sea_surface_temperature, daily_median_sst]
              engine: h5netcdf

    Optional knobs:

    ``path``         file path or glob (required).
    ``variables``    list of dataset variables to retain (defaults to all).
    ``engine``       xarray backend, e.g. ``h5netcdf``, ``netcdf4``, ``zarr``.
    ``time_dim``     name of the time coordinate, defaults to ``time``.
    ``lon_dim`` / ``lat_dim``    names of horizontal coords, autodetected by default.
    ``rename``       mapping ``{file_var: pipeline_var}`` applied before slicing.
    """

    plugin_name = "local_netcdf"
    plugin_version = "0.1.0"

    def __init__(
        self,
        source_id: str,
        *,
        path: str,
        variables: list[str] | None = None,
        engine: str | None = None,
        time_dim: str = "time",
        lon_dim: str | None = None,
        lat_dim: str | None = None,
        rename: dict[str, str] | None = None,
        chunks: dict[str, int] | None = None,
        **params: Any,
    ) -> None:
        super().__init__(
            source_id,
            path=path,
            variables=list(variables or []),
            engine=engine,
            time_dim=time_dim,
            lon_dim=lon_dim,
            lat_dim=lat_dim,
            rename=dict(rename or {}),
            chunks=dict(chunks or {}),
            **params,
        )
        self.path = path
        self.variables = list(variables) if variables else None
        self.engine = engine
        self.time_dim = time_dim
        self.lon_dim = lon_dim
        self.lat_dim = lat_dim
        self.rename = dict(rename or {})
        self.chunks = dict(chunks) if chunks else None

    # ------------------------------------------------------------------ API
    def fetch(self, query: SourceQuery) -> xr.Dataset:
        ds = self._open()

        if self.rename:
            ds = ds.rename({k: v for k, v in self.rename.items() if k in ds.variables})

        lon_name = self.lon_dim or _autodetect(ds, ("lon", "longitude", "x"))
        lat_name = self.lat_dim or _autodetect(ds, ("lat", "latitude", "y"))

        ds = _slice_bbox(ds, query.bbox, lon_name=lon_name, lat_name=lat_name)
        ds = _slice_time(ds, query.time_start, query.time_stop, time_name=self.time_dim)

        wanted = self.variables or query.variables
        if wanted:
            keep = [v for v in wanted if v in ds.data_vars]
            if keep:
                ds = ds[keep]

        # Stamp provenance breadcrumbs in attrs (does not affect content_hash —
        # the hashing layer ignores attributes, only data + structure).
        ds.attrs["mosaic_source_uri"] = str(Path(self.path).resolve())
        ds.attrs["mosaic_source_plugin"] = self.plugin_name
        return ds

    # ------------------------------------------------------------------ helpers
    def _open(self) -> xr.Dataset:
        path = self.path
        kwargs: dict[str, Any] = {}
        if self.engine:
            kwargs["engine"] = self.engine
        else:
            # Default to the pure-Python `h5netcdf` engine (a hard dependency
            # of MOSAIC) rather than letting xarray pick `netCDF4`. The C-level
            # `netCDF4` library uses the system's ANSI locale to encode file
            # paths on Windows, which causes spurious `FileNotFoundError`s on
            # any path containing characters outside the active code page
            # (e.g. Polish diacritics in a user folder name). `h5netcdf`
            # routes the open through `h5py`, which honours `PYTHONUTF8` and
            # works on Unicode paths regardless of the system locale. Modern
            # CMEMS / ERA5 / NSIDC L4 products are HDF5-based NetCDF4, which
            # both engines support; users requiring NetCDF3 classic can still
            # override via `engine="scipy"` or `engine="netcdf4"`.
            kwargs["engine"] = "h5netcdf"
        if self.chunks is not None:
            kwargs["chunks"] = self.chunks

        # zarr stores live in directories; everything else is opened by file.
        if path.endswith((".zarr", ".zarr/")) or Path(path).is_dir():
            return cast(xr.Dataset, xr.open_zarr(path, consolidated=True, chunks=self.chunks))
        if any(ch in path for ch in "*?["):
            return xr.open_mfdataset(path, combine="by_coords", **kwargs)
        return xr.open_dataset(path, **kwargs)


# ---------------------------------------------------------------------------
# slicing helpers (also used by CMEMS/ERA5 cache hits)
# ---------------------------------------------------------------------------


def _autodetect(ds: xr.Dataset, candidates: tuple[str, ...]) -> str:
    for cand in candidates:
        if cand in ds.coords or cand in ds.dims:
            return cand
    raise KeyError(
        f"Could not autodetect coordinate among {candidates!r}. "
        f"Pass lon_dim/lat_dim explicitly. Coords were: {list(ds.coords)}"
    )


def _slice_bbox(
    ds: xr.Dataset,
    bbox: tuple[float, float, float, float],
    *,
    lon_name: str,
    lat_name: str,
) -> xr.Dataset:
    west, south, east, north = bbox
    if lon_name not in ds.coords:
        return ds
    lon = ds[lon_name].values
    # sel works regardless of monotonicity direction — but slice is direction-aware.
    lon_ascending = bool(np.all(np.diff(lon) >= 0))
    lat = ds[lat_name].values
    lat_ascending = bool(np.all(np.diff(lat) >= 0))

    lon_slice = slice(west, east) if lon_ascending else slice(east, west)
    lat_slice = slice(south, north) if lat_ascending else slice(north, south)
    return ds.sel({lon_name: lon_slice, lat_name: lat_slice})


def _slice_time(
    ds: xr.Dataset,
    start: datetime,
    stop: datetime,
    *,
    time_name: str = "time",
) -> xr.Dataset:
    if time_name not in ds.coords:
        return ds
    return ds.sel({time_name: slice(pd.Timestamp(start), pd.Timestamp(stop))})
