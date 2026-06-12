# Dataset reference for the case studies

The accompanying paper relies on a small number of well-cited public
products. Every dataset is catalogued here with its identifier, version
window, and the way MOSAIC subsets it. Anyone re-running the pipelines
should get bit-identical files (modulo CMEMS/CDS server-side changes,
which are flagged in the STAC sidecar via `mosaic:source_version`).

## CS1 — Gulf of Riga coastal upwelling, July 2021

| field | value |
|-|-|
| bbox | `(west, south, east, north) = (22.0, 56.5, 24.8, 58.5)` |
| time window | `2021-07-12` … `2021-07-22` (inclusive, daily means) |
| domain resolution | native CMEMS 0.02° / ERA5 0.25°, harmonised to daily means |

### CMEMS — Baltic L4 SST

* **Product**: *Baltic Sea SST, L4, 0.02° × 0.02°, daily reprocessed*.
* **Dataset id (toolbox)**: `cmems_obs-sst_bal_phy-temp_my_l4_P1D-m`.
* **Variable used**: `analysed_sst` (Kelvin, foundation SST); harmonised
  to `sea_surface_temperature`. Daily spatial median computed as
  `sea_surface_temperature_daily_spatial_median` in the *fuse* step.
* **Service**: ARCO (default — no need to specify).
* **License**: Copernicus Marine free re-use under the
  [Marine Service license](https://marine.copernicus.eu/user-corner/service-commitments-and-licence).

Cache directory: `data/cache/cmems/cs1_gulf_of_riga/`.

### ERA5 — single-levels reanalysis

* **Product**: *ERA5 hourly data on single levels from 1940 to present*.
* **Dataset id (CDS)**: `reanalysis-era5-single-levels`.
* **Product type**: `reanalysis`.
* **Variables used**:
  - `10m_u_component_of_wind` → `eastward_wind`
  - `10m_v_component_of_wind` → `northward_wind`
* **Hours retrieved**: `00, 06, 12, 18` UTC (aggregated to daily means
  during harmonisation).
* **License**: ECMWF / Copernicus Climate Change Service open licence.

Cache directory: `data/cache/era5/cs1_gulf_of_riga/`.

### How to reproduce

With credentials (downloads ~50 MB for the SST + wind window):

```bash
python scripts/fetch_cs1_gulf_of_riga.py all
mosaic run pipelines/cs1_gulf_of_riga_upwelling.yaml
```

Without credentials (deterministic Gulf-of-Riga-shaped fixtures stand
in for the upstream products, identical pipeline path otherwise):

```bash
python scripts/fetch_cs1_gulf_of_riga.py populate-fixtures
mosaic run tests/fixtures/cs1_gulf_of_riga_offline.yaml
```

Either path produces a Zarr store under `out/` together with a STAC
sidecar. The sidecar's `mosaic:content_hash` fully identifies the result
— two runs of the same pipeline, fed the same inputs, produce the same hash.

## CS2 — Atlantic hurricanes (planned)

NDBC moored buoy time series + IBTrACS storm tracks + ERA5
single-levels (mean sea-level pressure, 10 m wind, total precipitation).
Stub configuration will land alongside the connector implementation.

## CS3 — Arctic sea ice (planned)

NSIDC sea-ice concentration (passive microwave) + ERA5 surface fields.
Stub configuration will land alongside the connector implementation.
