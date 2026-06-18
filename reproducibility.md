# Reproducibility guide

This document describes how to reproduce the three case studies from the companion paper end-to-end — from raw data download through pipeline execution to the paper figures.

Every MOSAIC run emits a STAC sidecar (`stac.json`) containing a `mosaic:content_hash` that uniquely identifies the output dataset.  Two reproduction paths are available for each case study:

| Path | Credentials required | Network required | Produces identical `content_hash`? |
|------|---------------------|-----------------|-------------------------------------|
| **Live** | Yes (see §[Credentials](#credentials)) | Yes | Yes (CS1 with `strict_versions = true`) |
| **Offline** | No | No | Fixtures are synthetic — values differ from real data |

---

## Environment

```bash
pip install "mosaic-ocean[copernicus,cds]"   # for live CS1 + CS2
# CS3 NSIDC data: manual download (see §CS3)
```

Requires Python ≥ 3.11.  Pin exact versions for bit-identical results:

```bash
pip install -r requirements.lock   # if provided, else pip freeze > requirements.lock after install
```

## Credentials

Credentials are read from environment variables first, then from `~/.mosaic/credentials` (TOML).

```toml
# ~/.mosaic/credentials
[cmems]
username = "..."
password = "..."

[cds]
key = "..."   # from https://cds.climate.copernicus.eu/profile
```

Environment variable equivalents: `CMEMS_USERNAME`, `CMEMS_PASSWORD`, `CDSAPI_KEY`.

Credentials never appear in logs or STAC provenance.

---

## CS1 — Gulf of Riga coastal upwelling, July 2021

### Domain

| Parameter | Value |
|-----------|-------|
| Bounding box | 22.0°E – 24.8°E, 56.5°N – 58.5°N |
| Time window | 2021-07-12 – 2021-07-22 (11 days, daily means) |
| Output | `out/cs1_gulf_of_riga_upwelling_live.zarr` |

### Data sources

| Source | Dataset ID | Variables fetched |
|--------|-----------|-------------------|
| Copernicus Marine (CMEMS) Baltic L4 SST | `cmems_obs-sst_bal_phy-temp_my_l4_P1D-m` | `analysed_sst` |
| ERA5 single-levels reanalysis | `reanalysis-era5-single-levels` | `10m_u_component_of_wind`, `10m_v_component_of_wind` |

CF dictionary: `configs/cf_baltic.yaml`.

### Derived variables

| Variable | Expression |
|----------|-----------|
| `wind_speed` | `sqrt(eastward_wind² + northward_wind²)` |
| `sst_spatial_anomaly` | `sea_surface_temperature − sea_surface_temperature_daily_spatial_median` |
| `upwelling_mask_sst` | `sst_spatial_anomaly < −2.0 K` |
| `upwelling_mask_sst_wind` | `(sst_spatial_anomaly < −2.0) & (wind_speed > 4.0 m s⁻¹)` |

### Reproduction — live data

Requires CMEMS and CDS accounts.

```bash
# 1. Download raw data (~50 MB)
python scripts/fetch_cs1_gulf_of_riga.py all

# 2. Run the pipeline
mosaic run pipelines/cs1_gulf_of_riga_upwelling.yaml

# 3. Verify SHA-256 checksums
python scripts/fetch_cs1_gulf_of_riga.py manifest   # writes data/cs1_gulf_of_riga_manifest.json
python scripts/fetch_cs1_gulf_of_riga.py verify
```

Available `fetch_cs1_gulf_of_riga.py` subcommands: `sst`, `wind`, `all`, `populate-fixtures`, `manifest`, `verify`.

### Reproduction — offline (no credentials)

Fixtures are deterministic synthetic NetCDF files that exercise the full pipeline without touching any external service.

```bash
python scripts/fetch_cs1_gulf_of_riga.py populate-fixtures
mosaic run tests/fixtures/cs1_gulf_of_riga_offline.yaml
```

To regenerate the fixtures themselves:

```bash
python tests/fixtures/build_cs1_gulf_of_riga_fixtures.py
```

Fixture files (in `tests/fixtures/cs1_gulf_of_riga/`):

| File | Seed | Description |
|------|------|-------------|
| `cmems_gulf_of_riga_sst_2021-07.nc` | 20210716 | Baltic SST with synthetic cold patch on 2021-07-16 |
| `era5_gulf_of_riga_wind_2021-07.nc` | 20210717 | 10 m wind components at 0.25° |

### Figures

```bash
python notebooks/_export_cs1_figures.py
```

Output in `docs/figures/cs1/`: `fig_cs1_riga_sst_evolution`, `fig_cs1_riga_spatial_anomaly_*`, `fig_cs1_riga_mask_sst_*`, `fig_cs1_riga_mask_comparison_*`, `fig_cs1_riga_flagged_cells_timeseries`.

---

## CS2 — Atlantic hurricane cold wake, August–September 2021

### Domain

| Parameter | Value |
|-----------|-------|
| Bounding box | 95.0°W – 78.0°W, 18.0°N – 32.0°N (Gulf of Mexico) |
| Time window | 2021-08-26 – 2021-09-02 (7 days, daily means) |
| Output | `out/cs2_atlantic_hurricane_2021.zarr` |

### Data sources

| Source | Dataset ID | Variables fetched |
|--------|-----------|-------------------|
| CMEMS Global L4 SST | `METOFFICE-GLO-SST-L4-REP-OBS-SST` | `analysed_sst` |
| ERA5 single-levels reanalysis | `reanalysis-era5-single-levels` | `u10`, `v10`, `mean_sea_level_pressure`, `total_precipitation` |
| IBTrACS-style storm track | — (synthetic CSV) | — (notebook overlay only) |

CF dictionary: `configs/cf_atlantic.yaml`.

### Derived variables

| Variable | Expression |
|----------|-----------|
| `wind_speed` | `sqrt(eastward_wind² + northward_wind²)` |
| `storm_intensity` | `1013.0 − air_pressure_at_mean_sea_level` (hPa proxy) |
| `hurricane_zone` | `(wind_speed > 17.0 m s⁻¹) & (air_pressure_at_mean_sea_level < 980 hPa)` |

### Reproduction — live data

Requires CDS credentials (CMEMS credentials optional if the CMEMS dataset is publicly accessible).

```bash
python scripts/fetch_cs2.py all
mosaic run pipelines/cs2_atlantic_hurricane.yaml
python scripts/fetch_cs2.py manifest    # writes data/cs2_manifest.json
python scripts/fetch_cs2.py verify
```

Available `fetch_cs2.py` subcommands: `sst`, `atmos`, `track`, `all`, `populate-fixtures`, `manifest`, `verify`.

### Reproduction — offline

```bash
python scripts/fetch_cs2.py populate-fixtures
mosaic run tests/fixtures/cs2_offline.yaml
```

Fixture files (in `tests/fixtures/cs2/`):

| File | Seed | Description |
|------|------|-------------|
| `cmems_gulf_sst_2021-08.nc` | 20210826 | Global SST with synthetic cold wake along storm track |
| `era5_gulf_atmos_2021-08.nc` | 20210827 | Cyclonic wind pattern, pressure depression, precipitation |
| `ibtracs_ida_like.csv` | — | 8-waypoint synthetic track; landfall 2021-08-29 at 90.5°W, 29.2°N |

### Figures

```bash
python notebooks/_export_cs2_figures.py
```

Output in `docs/figures/cs2/`: `fig_cs2_mslp_wind`, `fig_cs2_sst_wake`, `fig_cs2_intensity_timeseries`, `fig_cs2_hurricane_zone`.

---

## CS3 — Arctic sea-ice retreat, September 2012

### Domain

| Parameter | Value |
|-----------|-------|
| Bounding box | 170.0°W – 130.0°W, 70.0°N – 80.0°N (Beaufort/Chukchi sector) |
| Time window | 2012-09-01 – 2012-09-15 (15 days, daily means) |
| Output | `out/cs3_arctic_seaice_2012.zarr` |

### Data sources

| Source | Dataset ID | Variables fetched |
|--------|-----------|-------------------|
| NSIDC Climate Data Record (G02202 v4) | `g02202_v4` | `sic` (sea-ice concentration, fraction 0–1) |
| ERA5 single-levels reanalysis | `reanalysis-era5-single-levels` | `2m_temperature`, `mean_sea_level_pressure` |
| September SIC climatology (1991–2020) | `data/climatologies/arctic_sic_climatology_sep.nc` | `sic_climatology` |

CF dictionary: `configs/cf_arctic.yaml`.

> **Note:** NSIDC G02202 v4 files require a manual download or access via the `--source-uri` flag pointing to an NSIDC HTTP/S3 endpoint.  Use `populate-fixtures` to skip this step.

### Derived variables

| Variable | Expression |
|----------|-----------|
| `sic_anomaly` | `sea_ice_area_fraction − sea_ice_area_fraction_climatology` |
| `melt_pond_proxy` | `(sea_ice_area_fraction < 0.5) & (air_temperature > 273.15 K)` |

### Reproduction — live data

Requires NSIDC HTTP access and CDS credentials.

```bash
# Download raw data (NSIDC URI must be supplied)
python scripts/fetch_cs3.py sic --source-uri <NSIDC-HTTP-URL>
python scripts/fetch_cs3.py surface
python scripts/fetch_cs3.py climatology --download-url <climatology-URL>
# — or all at once:
python scripts/fetch_cs3.py all --source-uri <URL> --download-url <clim-URL>

mosaic run pipelines/cs3_arctic_seaice.yaml

python scripts/fetch_cs3.py manifest    # writes data/cs3_manifest.json
python scripts/fetch_cs3.py verify
```

Available `fetch_cs3.py` subcommands: `sic`, `surface`, `climatology`, `all`, `populate-fixtures`, `manifest`, `verify`.

### Reproduction — offline

```bash
python scripts/fetch_cs3.py populate-fixtures
mosaic run tests/fixtures/cs3_offline.yaml
```

Fixture files (in `tests/fixtures/cs3/`):

| File | Seed | Description |
|------|------|-------------|
| `nsidc_arctic_sic_2012-09.nc` | 20120901 | SIC with synthetic retreat tongue, 1° grid |
| `era5_arctic_surface_2012-09.nc` | 20120902 | t2m warm anomaly co-located with retreating ice |
| `arctic_sic_climatology_sep.nc` | — | Constant September 1991–2020 reference (0–1 ramp 70°N–77°N) |

### Figures

```bash
python notebooks/_export_cs3_figures.py
```

Output in `docs/figures/cs3/`: `fig_cs3_sic_evolution`, `fig_cs3_sic_anomaly`, `fig_cs3_melt_pond`, `fig_cs3_timeseries`.

---

## Dataset licenses

| Dataset | License |
|---------|---------|
| CMEMS Baltic L4 SST | Copernicus Marine free re-use (non-commercial & commercial) |
| CMEMS Global L4 SST | Copernicus Marine free re-use |
| ERA5 single-levels | ECMWF / Copernicus C3S open licence |
| NSIDC G02202 v4 | NSIDC/NASA open data |

Detailed identifiers, DOIs, and bounding-box metadata are in `docs/datasets.md`.

---

## Provenance & checksums

Every pipeline run writes a STAC Item alongside the Zarr store.  To inspect it:

```bash
mosaic prov show out/cs1_gulf_of_riga_upwelling_live.zarr/stac.json
```

The item records the pipeline hash, `mosaic:content_hash` of the output, harmonization mapping accuracy, QC pass/fail counts, and the full software environment.

SHA-256 manifests for Zenodo uploads are generated by the `manifest` subcommand of each fetch script and stored in `data/<cs>_manifest.json`.

---

## Summary of commands

| Task | Command |
|------|---------|
| CS1 live fetch | `python scripts/fetch_cs1_gulf_of_riga.py all` |
| CS1 offline | `python scripts/fetch_cs1_gulf_of_riga.py populate-fixtures` |
| CS1 run (live) | `mosaic run pipelines/cs1_gulf_of_riga_upwelling.yaml` |
| CS1 run (offline) | `mosaic run tests/fixtures/cs1_gulf_of_riga_offline.yaml` |
| CS2 live fetch | `python scripts/fetch_cs2.py all` |
| CS2 offline | `python scripts/fetch_cs2.py populate-fixtures` |
| CS2 run (live) | `mosaic run pipelines/cs2_atlantic_hurricane.yaml` |
| CS2 run (offline) | `mosaic run tests/fixtures/cs2_offline.yaml` |
| CS3 live fetch | `python scripts/fetch_cs3.py all --source-uri <URL> --download-url <clim-URL>` |
| CS3 offline | `python scripts/fetch_cs3.py populate-fixtures` |
| CS3 run (live) | `mosaic run pipelines/cs3_arctic_seaice.yaml` |
| CS3 run (offline) | `mosaic run tests/fixtures/cs3_offline.yaml` |
| Regenerate CS1 fixtures | `python tests/fixtures/build_cs1_gulf_of_riga_fixtures.py` |
| Regenerate CS2 fixtures | `python tests/fixtures/build_cs2_fixtures.py` |
| Regenerate CS3 fixtures | `python tests/fixtures/build_cs3_fixtures.py` |
| Export CS1 figures | `python notebooks/_export_cs1_figures.py` |
| Export CS2 figures | `python notebooks/_export_cs2_figures.py` |
| Export CS3 figures | `python notebooks/_export_cs3_figures.py` |
