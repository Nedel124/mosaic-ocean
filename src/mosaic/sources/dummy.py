"""Synthetic source used for tests, tutorials, and the minimal example pipeline.

It produces a small deterministic dataset on a regular lon/lat/time grid with
plausible CF-compliant coordinates and a couple of named variables (default:
``sst`` and ``u10``).  Determinism is essential — the dummy source feeds the
provenance round-trip tests.
"""
from __future__ import annotations

from typing import Any, ClassVar

import numpy as np
import pandas as pd
import xarray as xr

from mosaic.sources.base import Source, SourceQuery, register


@register
class DummySource(Source):
    """Synthetic, deterministic, CF-styled dataset on a regular grid."""

    plugin_name = "dummy"
    plugin_version = "0.1.0"

    DEFAULTS: ClassVar[dict[str, dict[str, Any]]] = {
        "sst": {
            "amplitude": 5.0,
            "offset": 15.0,
            "standard_name": "sea_surface_temperature",
            "units": "degree_Celsius",
        },
        "u10": {
            "amplitude": 8.0,
            "offset": 0.0,
            "standard_name": "eastward_wind",
            "units": "m s-1",
        },
        "v10": {
            "amplitude": 6.0,
            "offset": 0.0,
            "standard_name": "northward_wind",
            "units": "m s-1",
        },
        "chlorophyll": {
            "amplitude": 0.6,
            "offset": 1.2,
            "standard_name": "mass_concentration_of_chlorophyll_in_sea_water",
            "units": "mg m-3",
        },
    }

    def __init__(
        self,
        source_id: str = "dummy",
        *,
        variables: list[str] | None = None,
        resolution_deg: float = 0.5,
        seed: int = 0,
        **params: Any,
    ) -> None:
        super().__init__(source_id, variables=variables, resolution_deg=resolution_deg, seed=seed, **params)
        self.variables = list(variables or ["sst", "u10"])
        self.resolution_deg = float(resolution_deg)
        self.seed = int(seed)

    # ------------------------------------------------------------------ API
    def fetch(self, query: SourceQuery) -> xr.Dataset:
        west, south, east, north = query.bbox
        if east < west:  # antimeridian crossing — extend
            east = east + 360.0
        lon = np.arange(west, east + 1e-9, self.resolution_deg)
        lat = np.arange(south, north + 1e-9, self.resolution_deg)
        time = pd.date_range(query.time_start, query.time_stop, freq="1D", inclusive="both")

        rng = np.random.default_rng(self.seed)

        coords: dict[str, Any] = {
            "time": ("time", time),
            "lat": ("lat", lat.astype("float32")),
            "lon": ("lon", lon.astype("float32")),
        }
        data_vars: dict[str, Any] = {}

        for var in self.variables:
            spec = self.DEFAULTS.get(var, {"amplitude": 1.0, "offset": 0.0, "standard_name": var, "units": "1"})
            base = self._smooth_field(rng, len(time), len(lat), len(lon))
            arr = (spec["amplitude"] * base + spec["offset"]).astype("float32")
            data_vars[var] = (
                ("time", "lat", "lon"),
                arr,
                {"standard_name": spec["standard_name"], "units": spec["units"]},
            )

        ds = xr.Dataset(data_vars=data_vars, coords=coords)
        ds["lat"].attrs.update({"standard_name": "latitude", "units": "degrees_north"})
        ds["lon"].attrs.update({"standard_name": "longitude", "units": "degrees_east"})
        ds.attrs["Conventions"] = "CF-1.11"
        ds.attrs["title"] = f"DummySource:{self.source_id}"
        ds.attrs["mosaic_synthetic"] = "true"
        return ds

    # ------------------------------------------------------------------ utils
    @staticmethod
    def _smooth_field(rng: np.random.Generator, nt: int, ny: int, nx: int) -> np.ndarray:
        """Return a low-frequency, deterministic field shaped (nt, ny, nx)."""
        # combine two sinusoids with a small noise term — fully determined by seed
        t = np.linspace(0.0, 2 * np.pi, max(nt, 1))[:, None, None]
        y = np.linspace(0.0, np.pi, max(ny, 1))[None, :, None]
        x = np.linspace(0.0, 2 * np.pi, max(nx, 1))[None, None, :]
        signal = np.sin(t) * np.sin(y) * np.cos(x / 2.0)
        noise = rng.standard_normal((nt, ny, nx)) * 0.05
        return (signal + noise).astype("float32")
