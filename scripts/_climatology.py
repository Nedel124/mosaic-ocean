"""Compute a long-term Baltic SST July climatology from CMEMS L4.

Public entry point: :func:`compute_july_climatology`. The function downloads
*all* July daily fields from the CMEMS reprocessed L4 product over the
requested year span, takes the day-of-month mean, then re-indexes those
day-of-month means onto the CS1 production window so that the result has
the same ``time`` axis as the SST and wind inputs and broadcasts cleanly
in the ``fuse`` step (``sst − climatology``).

The function is split into a *pure* core (:func:`_collapse_to_doy_mean`)
and an *I/O wrapper* (:func:`compute_july_climatology`) so the algorithm
stays unit-testable against synthetic inputs without touching the network.
"""
from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import xarray as xr


JULY = 7


def _collapse_to_doy_mean(
    monthly_stack: xr.DataArray,
    target_dates: Iterable[pd.Timestamp],
) -> xr.DataArray:
    """Collapse a multi-year July stack to a per-target-date climatology.

    Parameters
    ----------
    monthly_stack
        DataArray with a ``time`` coordinate covering one or more Julys.
        Non-July samples are silently filtered out so the function tolerates
        whatever the upstream subset returned.
    target_dates
        The ``time`` axis the result should be indexed by — typically the
        CS1 production window (e.g. 2018-07-20…2018-07-30).

    Returns
    -------
    xr.DataArray
        Same spatial shape as the input, but with a ``time`` axis that
        matches ``target_dates``. The value on date *d* is the mean of all
        years' samples for ``day=d.day``.
    """
    if "time" not in monthly_stack.dims:
        raise ValueError("monthly_stack must have a `time` dimension")

    targets = list(target_dates)
    if not targets:
        raise ValueError("target_dates must be non-empty")

    times = pd.to_datetime(monthly_stack["time"].values)
    july_mask = times.month == JULY
    if not july_mask.any():
        raise ValueError("monthly_stack contains no July samples")

    july = monthly_stack.isel(time=np.where(july_mask)[0])
    day_of_month = pd.to_datetime(july["time"].values).day
    july = july.assign_coords(_dom=("time", day_of_month))
    doy_mean = july.groupby("_dom").mean("time", keep_attrs=True)

    # Re-index onto the target dates by day-of-month lookup.
    out = xr.concat(
        [doy_mean.sel(_dom=d.day) for d in targets],
        dim=pd.Index([pd.Timestamp(d) for d in targets], name="time"),
    )
    return out.drop_vars("_dom", errors="ignore")


def compute_july_climatology(
    *,
    bbox: tuple[float, float, float, float],
    target_dates: Iterable[pd.Timestamp | datetime | str],
    year_start: int,
    year_end: int,
    cmems_dataset_id: str,
    cmems_variable: str,
    out_path: Path,
    cache_dir: Path | None = None,
    fetch_dataset: Any = None,
    output_variable: str = "sst_climatology",
) -> Path:
    """Download (or reuse cached) July fields and write the climatology.

    Parameters
    ----------
    bbox
        ``(west, south, east, north)``.
    target_dates
        The dates the resulting climatology will be indexed by — pass the
        production window so ``sst − climatology`` broadcasts trivially.
    year_start, year_end
        Inclusive year range over which to average. 1991-2020 is a common
        WMO-style baseline.
    cmems_dataset_id, cmems_variable
        CMEMS product identifier and variable name (e.g.
        ``cmems_obs-sst_bal_phy_l4_my_P1D-m`` / ``analysed_sst``).
    out_path
        NetCDF file to write. The file's variable will be renamed to
        ``output_variable`` (default ``sst_climatology``) and tagged with
        ``standard_name = sea_surface_temperature_climatology`` and
        ``units = K``.
    cache_dir
        Optional directory for the per-year intermediate downloads. When
        provided the function is idempotent: re-running uses the cache.
    fetch_dataset
        Test seam — a callable ``(year, bbox, variable, dest) -> xr.Dataset``
        that returns a single year's July stack. ``None`` (default) wires
        the function to :class:`mosaic.sources.cmems.CmemsSource`.

    Returns
    -------
    Path
        The path to the written NetCDF file.
    """
    target_idx = pd.DatetimeIndex(pd.to_datetime(list(target_dates)))
    if not (target_idx.month == JULY).all():
        raise ValueError("target_dates must all fall in July for this climatology")

    fetch = fetch_dataset or _default_fetch_year
    yearly: list[xr.DataArray] = []
    for year in range(year_start, year_end + 1):
        ds = fetch(
            year=year,
            bbox=bbox,
            dataset_id=cmems_dataset_id,
            variable=cmems_variable,
            cache_dir=cache_dir,
        )
        if cmems_variable not in ds.data_vars:
            raise KeyError(
                f"variable {cmems_variable!r} not present in CMEMS download for {year}"
            )
        yearly.append(ds[cmems_variable])

    stacked = xr.concat(yearly, dim="time").sortby("time")
    climatology = _collapse_to_doy_mean(stacked, target_idx)
    climatology.name = output_variable
    climatology.attrs.update(
        {
            "standard_name": "sea_surface_temperature_climatology",
            "long_name": "Long-term July day-of-month SST mean",
            "units": "K",
            "mosaic:climatology_window": f"{year_start}-{year_end} July",
            "mosaic:source_dataset": cmems_dataset_id,
        }
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    climatology.to_dataset().to_netcdf(out_path, engine="h5netcdf")
    return out_path


def _default_fetch_year(
    *,
    year: int,
    bbox: tuple[float, float, float, float],
    dataset_id: str,
    variable: str,
    cache_dir: Path | None,
) -> xr.Dataset:
    """Real CMEMS fetcher used in production. Not exercised in unit tests."""
    from mosaic.sources.base import SourceQuery
    from mosaic.sources.cmems import CmemsSource

    src = CmemsSource(
        source_id=f"clim_{year}",
        dataset_id=dataset_id,
        variables=[variable],
        cache_dir=str(cache_dir) if cache_dir else None,
    )
    query = SourceQuery(
        bbox=bbox,
        time_start=datetime(year, 7, 1),
        time_stop=datetime(year, 7, 31),
    )
    return src.fetch(query)


__all__ = ["compute_july_climatology", "_collapse_to_doy_mean"]
