"""Copernicus Marine (CMEMS) source plugin.

Wraps the official ``copernicusmarine`` Python toolbox so MOSAIC pipelines
can cite a CMEMS dataset by its product identifier and let MOSAIC handle
spatial / temporal subsetting plus on-disk caching.

Cache strategy
--------------
A request is identified by a deterministic key composed of
``(dataset_id, bbox, time_start, time_stop, variables)``. The first call
issues a ``copernicusmarine.subset()`` and stores the result as a NetCDF
file under ``cache_dir``. Subsequent calls with the same key open that
file via :class:`mosaic.sources.local.LocalNetcdfSource` semantics —
no network round trip, identical bytes, identical ``content_hash``.

Authentication
--------------
The toolbox accepts credentials from environment variables
(``COPERNICUSMARINE_SERVICE_USERNAME`` /
``COPERNICUSMARINE_SERVICE_PASSWORD``) and from ``~/.copernicusmarine``.
MOSAIC does not capture credentials; it passes through whatever the
toolbox finds. Cache hits do not need credentials, which is why CI and
reviewers can re-run a pipeline with shipped cached subsets.
"""
from __future__ import annotations

import hashlib
import inspect
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import xarray as xr

from mosaic.sources.base import Source, SourceQuery, register


@register
class CmemsSource(Source):
    """Subset a Copernicus Marine product to the pipeline domain.

    YAML usage::

        sources:
          - id: cmems_sst
            plugin: cmems
            params:
              dataset_id: cmems_obs-sst_bal_phy-temp_my_l4_P1D-m
              variables: [analysed_sst]
              cache_dir: data/cache/cmems/cs1_gulf_of_riga

    Parameters
    ----------
    dataset_id
        CMEMS product identifier (the ``ID`` column on the catalogue page).
    variables
        Subset of dataset variables to retrieve. ``None`` retrieves all.
    cache_dir
        Directory used to store cached NetCDF subsets. ``None`` disables
        caching (every call hits the network).
    service_id
        Optional service identifier passed to ``copernicusmarine.subset``
        (e.g. to choose between ARCO and OPeNDAP services).
    """

    plugin_name = "cmems"
    plugin_version = "0.1.0"

    def __init__(
        self,
        source_id: str,
        *,
        dataset_id: str,
        variables: list[str] | None = None,
        cache_dir: str | None = None,
        service_id: str | None = None,
        depth_min: float | None = None,
        depth_max: float | None = None,
        username: str | None = None,
        password: str | None = None,
        credentials_file: str | Path | None = None,
        **params: Any,
    ) -> None:
        super().__init__(
            source_id,
            dataset_id=dataset_id,
            variables=list(variables or []),
            cache_dir=cache_dir,
            service_id=service_id,
            depth_min=depth_min,
            depth_max=depth_max,
            **params,
        )
        self.dataset_id = dataset_id
        self.variables = list(variables) if variables else None
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.service_id = service_id
        self.depth_min = depth_min
        self.depth_max = depth_max
        self.username = username
        self.password = password
        self.credentials_file = Path(credentials_file) if credentials_file else None

    # ------------------------------------------------------------------ API
    def fetch(self, query: SourceQuery) -> xr.Dataset:
        cache_path = self._cache_path(query)
        if cache_path is not None and cache_path.exists():
            ds = self._open_cache(cache_path)
            ds.attrs["mosaic_cache_hit"] = "true"
            return ds

        ds = self._download_subset(query, cache_path)
        ds.attrs["mosaic_cache_hit"] = "false"
        return ds

    # ------------------------------------------------------------------ cache
    def _cache_key(self, query: SourceQuery) -> str:
        payload = {
            "dataset_id": self.dataset_id,
            "service_id": self.service_id,
            "variables": sorted(self.variables) if self.variables else None,
            "bbox": list(query.bbox),
            "time_start": _iso(query.time_start),
            "time_stop": _iso(query.time_stop),
            "depth_min": self.depth_min,
            "depth_max": self.depth_max,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()[:16]

    def _cache_path(self, query: SourceQuery) -> Path | None:
        if self.cache_dir is None:
            return None
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        return self.cache_dir / f"{self.source_id}_{self._cache_key(query)}.nc"

    def _open_cache(self, path: Path) -> xr.Dataset:
        # Local relative import keeps the optional `local` plugin loaded
        # only when caching is actually used.
        from mosaic.sources.local import _slice_bbox  # noqa: F401  (used for symmetry)

        ds = xr.open_dataset(path, engine="h5netcdf")
        ds.attrs["mosaic_source_uri"] = str(path.resolve())
        ds.attrs["mosaic_source_plugin"] = self.plugin_name
        return ds

    # ------------------------------------------------------------------ network
    def _download_subset(
        self,
        query: SourceQuery,
        cache_path: Path | None,
    ) -> xr.Dataset:
        try:
            import copernicusmarine  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise ImportError(
                "CmemsSource requires the 'copernicusmarine' extra. "
                "Install with: pip install 'mosaic-ocean[copernicus]'."
            ) from exc

        west, south, east, north = query.bbox
        out_path = cache_path or _tmp_path(self.source_id)

        kwargs: dict[str, Any] = dict(
            dataset_id=self.dataset_id,
            minimum_longitude=west,
            maximum_longitude=east,
            minimum_latitude=south,
            maximum_latitude=north,
            start_datetime=_iso(query.time_start),
            end_datetime=_iso(query.time_stop),
            output_filename=out_path.name,
            output_directory=str(out_path.parent),
        )
        if self.variables:
            kwargs["variables"] = list(self.variables)
        if self.service_id:
            kwargs["service"] = self.service_id
        if self.depth_min is not None:
            kwargs["minimum_depth"] = self.depth_min
        if self.depth_max is not None:
            kwargs["maximum_depth"] = self.depth_max

        # `copernicusmarine` 1.x exposed `force_download=True` to overwrite
        # an existing local file; the 2.x rewrite split that flag into
        # `overwrite` / `skip_existing` and removed `force_download`. We pick
        # whichever parameter the installed toolbox accepts so MOSAIC stays
        # compatible across both API generations without pinning the extra.
        subset_params = inspect.signature(copernicusmarine.subset).parameters
        if "overwrite" in subset_params:
            kwargs["overwrite"] = True
        elif "force_download" in subset_params:  # legacy 1.x toolbox
            kwargs["force_download"] = True

        # Authentication: pass credentials explicitly when provided.
        # This avoids relying on Copernicus Marine global configuration,
        # which may differ between CLI, Jupyter, and Python environments.
        if self.username is not None and "username" in subset_params:
            kwargs["username"] = self.username

        if self.password is not None and "password" in subset_params:
            kwargs["password"] = self.password

        if self.credentials_file is not None and "credentials_file" in subset_params:
            kwargs["credentials_file"] = self.credentials_file

        copernicusmarine.subset(**kwargs)

        ds = xr.open_dataset(out_path, engine="h5netcdf")
        ds.attrs["mosaic_source_uri"] = str(out_path.resolve())
        ds.attrs["mosaic_source_plugin"] = self.plugin_name
        return ds


def _iso(value: datetime | str) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _tmp_path(source_id: str) -> Path:
    import tempfile

    tmpdir = Path(tempfile.gettempdir()) / "mosaic_cmems"
    tmpdir.mkdir(parents=True, exist_ok=True)
    return tmpdir / f"{source_id}.nc"
