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
  during harmonisation — see `harmonize.time_alignment` in
  `docs/reproducibility.md`).
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

## CS2 — Atlantic hurricane (Ida-like), August–September 2021

| field | value |
|-|-|
| bbox | `(west, south, east, north) = (-95.0, 18.0, -78.0, 32.0)` |
| time window | `2021-08-26` … `2021-09-02` (inclusive, daily means) |

### CMEMS — Global L4 SST

* **Product**: *Global OSTIA L4 SST, 0.05° × 0.05°, daily reprocessed* (Met Office).
* **Dataset id (toolbox)**: `METOFFICE-GLO-SST-L4-REP-OBS-SST`.
* **Variable used**: `analysed_sst` (Kelvin); harmonised to `sea_surface_temperature`.
* **License**: Copernicus Marine free re-use under the
  [Marine Service license](https://marine.copernicus.eu/user-corner/service-commitments-and-licence).

Cache directory: `data/cache/cmems/`.

### ERA5 — single-levels reanalysis

* **Variables used**: `10m_u_component_of_wind`, `10m_v_component_of_wind`,
  `mean_sea_level_pressure`, `total_precipitation`.
* **Hours retrieved**: `00, 06, 12, 18` UTC (aggregated to daily means
  during harmonisation — see `harmonize.time_alignment` in
  `docs/reproducibility.md`).
* **License**: ECMWF / Copernicus Climate Change Service open licence.

Cache directory: `data/cache/era5/`.

### IBTrACS storm track (visualisation only)

A synthetic, Ida-like IBTrACS-style CSV (`tests/fixtures/cs2/ibtracs_ida_like.csv`)
is bundled and copied into `data/tracks/` by `scripts/fetch_cs2.py track`. It is
overlaid on the figures in the companion notebook for context — it is **not**
a pipeline source and does not enter the harmonized dataset or the
`mosaic:content_hash`. There is no NDBC connector in this codebase.

### How to reproduce

With credentials:

```bash
python scripts/fetch_cs2.py all
mosaic run pipelines/cs2_atlantic_hurricane.yaml
```

Without credentials (synthetic fixtures, identical pipeline path otherwise):

```bash
python scripts/fetch_cs2.py populate-fixtures
mosaic run tests/fixtures/cs2_offline.yaml
```

## CS3 — Arctic sea-ice retreat, September 2012

| field | value |
|-|-|
| bbox | `(west, south, east, north) = (-170.0, 70.0, -130.0, 80.0)` |
| time window | `2012-09-01` … `2012-09-15` (inclusive, daily means) |

### NSIDC — daily sea-ice concentration

* **Product**: *NSIDC G02202-like daily sea-ice concentration climate-data record*.
* **Variable used**: `sic`; harmonised to `sea_ice_area_fraction`.
* **Connector status**: there is no live NSIDC API connector yet. The pipeline
  reads the field through `LocalNetcdfSource`; `scripts/fetch_cs3.py sic`
  only downloads from an explicit `--source-uri` you provide, or the case
  study runs from `populate-fixtures`.
* Also used: a September 1991-2020 SIC climatology
  (`data/climatologies/arctic_sic_climatology_sep.nc`), likewise read through
  `LocalNetcdfSource`. `scripts/fetch_cs3.py climatology` requires
  `--download-url`; live computation from raw NSIDC archives is not yet
  implemented (`populate-fixtures` provides the synthetic baseline).

Cache directory: `data/cache/nsidc/`.

### ERA5 — single-levels reanalysis

* **Variables used**: `2m_temperature`, `mean_sea_level_pressure`.
* **Hours retrieved**: `00, 06, 12, 18` UTC (aggregated to daily means
  during harmonisation — see `harmonize.time_alignment` in
  `docs/reproducibility.md`).

Cache directory: `data/cache/era5/`.

### How to reproduce

Without credentials (synthetic fixtures — the only fully-automated path
today, since CS3 has no live NSIDC fetch):

```bash
python scripts/fetch_cs3.py populate-fixtures
mosaic run tests/fixtures/cs3_offline.yaml
```

With an ERA5 account and a known NSIDC file URL, `python scripts/fetch_cs3.py
all --source-uri <nsidc-url> --download-url <climatology-url>` followed by
`mosaic run pipelines/cs3_arctic_seaice.yaml` reproduces the live path.
