"""ECMWF ERA5 (CDS) source plugin.

Wraps :mod:`cdsapi` for retrieval of ERA5 single-level (and pressure-level)
products from the Copernicus Climate Data Store. Same cache-first behaviour
as :class:`mosaic.sources.cmems.CmemsSource`: cached NetCDF on disk produces
the same harmonized output and ``content_hash`` regardless of whether the
network was hit or not.

Authentication
--------------
``cdsapi`` reads ``CDSAPI_URL`` / ``CDSAPI_KEY`` from the environment, or a
``~/.cdsapirc`` file. MOSAIC does not capture credentials. Cache hits do
not require credentials.

Time discretisation
-------------------
ERA5 returns hourly data; the request expands a YAML time window into
explicit (year, month, day, time) lists, which is what the CDS API expects.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import xarray as xr

from mosaic.sources.base import Source, SourceQuery, register


@register
class Era5Source(Source):
    """Retrieve a slice of an ERA5 product from the Climate Data Store.

    YAML usage::

        sources:
          - id: era5_wind
            plugin: era5
            params:
              dataset: reanalysis-era5-single-levels
              product_type: reanalysis
              variables:
                - 10m_u_component_of_wind
                - 10m_v_component_of_wind
              hours: ["00:00", "06:00", "12:00", "18:00"]
              cache_dir: data/cache/era5
    """

    plugin_name = "era5"
    plugin_version = "0.1.0"

    def __init__(
        self,
        source_id: str,
        *,
        variables: list[str],
        dataset: str = "reanalysis-era5-single-levels",
        product_type: str = "reanalysis",
        hours: list[str] | None = None,
        format: str = "netcdf",
        cache_dir: str | None = None,
        pressure_level: list[int] | None = None,
        **params: Any,
    ) -> None:
        super().__init__(
            source_id,
            dataset=dataset,
            product_type=product_type,
            variables=list(variables),
            hours=list(hours or _DEFAULT_HOURS),
            format=format,
            cache_dir=cache_dir,
            pressure_level=list(pressure_level or []),
            **params,
        )
        self.dataset = dataset
        self.product_type = product_type
        self.variables = list(variables)
        self.hours = list(hours or _DEFAULT_HOURS)
        self.format = format
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.pressure_level = list(pressure_level) if pressure_level else None

    # ------------------------------------------------------------------ API
    def fetch(self, query: SourceQuery) -> xr.Dataset:
        cache_path = self._cache_path(query)
        if cache_path is not None and cache_path.exists():
            return self._open(cache_path, cache_hit=True)

        out_path = cache_path or _tmp_path(self.source_id)
        self._retrieve(query, out_path)
        return self._open(out_path, cache_hit=False)

    # ------------------------------------------------------------------ cache
    def _cache_key(self, query: SourceQuery) -> str:
        payload = {
            "dataset": self.dataset,
            "product_type": self.product_type,
            "variables": sorted(self.variables),
            "hours": sorted(self.hours),
            "pressure_level": self.pressure_level,
            "bbox": list(query.bbox),
            "time_start": _iso(query.time_start),
            "time_stop": _iso(query.time_stop),
            "format": self.format,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()[:16]

    def _cache_path(self, query: SourceQuery) -> Path | None:
        if self.cache_dir is None:
            return None
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        ext = "nc" if self.format == "netcdf" else "grib"
        return self.cache_dir / f"{self.source_id}_{self._cache_key(query)}.{ext}"

    def _open(self, path: Path, *, cache_hit: bool) -> xr.Dataset:
        engine = "h5netcdf" if self.format == "netcdf" else "cfgrib"
        ds = xr.open_dataset(path, engine=engine)
        ds.attrs["mosaic_source_uri"] = str(path.resolve())
        ds.attrs["mosaic_source_plugin"] = self.plugin_name
        ds.attrs["mosaic_cache_hit"] = "true" if cache_hit else "false"
        return ds

    # ------------------------------------------------------------------ network
    def _retrieve(self, query: SourceQuery, out_path: Path) -> None:
        try:
            import cdsapi  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise ImportError(
                "Era5Source requires the 'cds' extra. "
                "Install with: pip install 'mosaic-ocean[cds]'."
            ) from exc

        west, south, east, north = query.bbox
        years, months, days = _expand_calendar(query.time_start, query.time_stop)

        request: dict[str, Any] = {
            "product_type": self.product_type,
            "variable": list(self.variables),
            "year": years,
            "month": months,
            "day": days,
            "time": list(self.hours),
            "area": [north, west, south, east],  # CDS area is N, W, S, E
            "format": self.format,
        }
        if self.pressure_level:
            request["pressure_level"] = [str(p) for p in self.pressure_level]

        out_path.parent.mkdir(parents=True, exist_ok=True)
        client = cdsapi.Client()
        client.retrieve(self.dataset, request, str(out_path))


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

_DEFAULT_HOURS: list[str] = [f"{h:02d}:00" for h in range(0, 24, 6)]


def _iso(value: datetime | str) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _expand_calendar(
    start: datetime, stop: datetime
) -> tuple[list[str], list[str], list[str]]:
    """Return sorted year / month / day lists covering [start, stop]."""
    if stop < start:
        start, stop = stop, start
    days = pd.date_range(start, stop, freq="1D", inclusive="both")
    if len(days) == 0:
        days = pd.DatetimeIndex([pd.Timestamp(start)])
    years = sorted({f"{d.year:04d}" for d in days})
    months = sorted({f"{d.month:02d}" for d in days})
    day_strs = sorted({f"{d.day:02d}" for d in days})
    return years, months, day_strs


def _tmp_path(source_id: str) -> Path:
    import tempfile

    tmpdir = Path(tempfile.gettempdir()) / "mosaic_era5"
    tmpdir.mkdir(parents=True, exist_ok=True)
    return tmpdir / f"{source_id}.nc"


__all__ = ["Era5Source"]
