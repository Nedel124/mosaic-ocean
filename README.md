# MOSAIC

**Multi-source Ocean Sensor And model Integration Catalogue**

A lightweight, open-source Python library for declarative, reproducible
integration of heterogeneous oceanographic data — satellite, numerical model,
and in-situ observations — with automatic semantic harmonization, quality
control, and content-addressable provenance recorded as STAC metadata.

> **Status:** alpha (`v0.1.0.dev0`). Public API may still change.

## What MOSAIC does

- Pulls data from multiple sources through a pluggable connector interface.
  Implemented today: Copernicus Marine (`cmems`) and ERA5/CDS (`era5`), plus
  `local_netcdf` and a synthetic `dummy` source used for offline tests and
  fixtures. Sentinel-3 STAC, NDBC and OSI SAF are not yet implemented as
  connectors; IBTrACS ships only as a static CSV overlaid on the CS2 figures
  for visual context, not as a pipeline source (see `docs/datasets.md`).
- Harmonizes variable names, units, CRS and temporal axes against the CF
  Standard Name Table (v85) and three domain-specific dictionaries
  (Baltic / Atlantic / Arctic).
- Runs a configurable pipeline (`ingest → QC → harmonize → fuse → export`).
- Records full provenance as a STAC Item with the `mosaic` extension
  (pipeline hash, content hash, mapping accuracy, QC statistics, environment).
  This is the same metric the companion paper calls *semantic resolution
  rate*; the code, tests and STAC field name (`mapping_accuracy`) keep the
  original implementation-level name.
- Exports to Zarr (default) or NetCDF-CF.
- Ships a CLI (`mosaic run pipeline.yaml`) and a Python API.

## What MOSAIC does **not** do

- It does **not** host a server. THREDDS/ERDDAP/OGC services are *consumed*,
  not replaced.
- It does **not** ship a GUI or dashboard.
- It does **not** invent its own storage format. We use Zarr / NetCDF / STAC.
- It does **not** include numerical models or data-assimilation algorithms —
  MOSAIC is the *integration* layer.

## Install

```bash
pip install mosaic-ocean                  # core
pip install "mosaic-ocean[copernicus]"    # + Copernicus Marine connector
pip install "mosaic-ocean[cds]"           # + ERA5 (CDS) connector
pip install "mosaic-ocean[stac]"          # + STAC client connectors
pip install "mosaic-ocean[parallel]"      # + Dask parallelism
pip install "mosaic-ocean[viz]"           # + plotting deps
```

Requires Python ≥ 3.11.

## Quickstart

Run a pipeline declared in YAML:

```bash
mosaic validate pipelines/example_minimal.yaml
mosaic run      pipelines/example_minimal.yaml
mosaic prov show out/example_minimal.zarr.stac.json
```

Or build it programmatically:

```python
import mosaic as ms

pipe = (
    ms.Pipeline(name="demo")
    .add_source(ms.sources.DummySource(variables=["sst", "u10"]))
    .harmonize(cf_dictionary="configs/cf_baltic.yaml", time_alignment="instantaneous")
    .qc(rules={"sst": {"type": "range", "min": -2.0, "max": 35.0}})
    .export(path="out/demo.zarr")
)
result = pipe.run()
print(result.provenance.id)
print(result.qc_report)
```

## Pipeline file format

A pipeline is a single YAML file validated by [pydantic](https://docs.pydantic.dev/).
Minimal example:

```yaml
apiVersion: mosaic/v1
kind: Pipeline
metadata:
  name: example_minimal

spec:
  domain:
    bbox: [14.0, 54.0, 22.0, 60.0]
    time: { start: "2022-06-01", stop: "2022-06-07", resolution: "1D" }

  sources:
    - id: dummy
      plugin: dummy
      params:
        variables: [sst, u10]

  harmonize:
    cf_dictionary: configs/cf_baltic.yaml

  export:
    format: zarr
    path: out/example.zarr
    provenance: true
```

## Authentication for connectors

Each connector reads credentials from two locations, with environment variables
taking priority:

1. `CMEMS_USERNAME`, `CMEMS_PASSWORD`, `CDSAPI_KEY`, ... (env)
2. `~/.mosaic/credentials` (TOML)

Credentials never appear in logs or in STAC provenance.

## How does it compare?

MOSAIC sits in the *integration / harmonization* niche of the ocean data stack.
It uses xarray + Zarr + STAC under the hood, and is complementary to:

- **THREDDS / ERDDAP** — data servers (we consume them);
- **Pangeo** — compute substrate (we build on it);
- **STAC / intake** — catalog standards (we adopt them);
- **Argopy / OceanSpy** — domain libraries (we wrap or coexist).

A more detailed comparison is in the related-work section of the companion
paper (not part of this code repository).

## Reproducibility

Every run produces a STAC Item with `mosaic:pipeline_hash` and
`mosaic:content_hash`, giving a deterministic re-run guarantee for
non-stochastic stages. See `docs/reproducibility.md` for exactly what each
hash covers, what it does not cover (e.g. live vs. offline-fixture content
hashes are *not* expected to match), and the current state of environment
pinning.

### CS1 — Gulf of Riga coastal upwelling, July 2021

The first case study ships end-to-end. Two reproduction paths are
supported, running the same processing stages (ingest → QC → harmonize →
fuse → export) and producing the same derived variables — but as two
distinct YAML pipelines (different source plugins: `cmems`/`era5` for live
vs. `local_netcdf` for the offline fixture), they have distinct
`mosaic:pipeline_hash` values, and the synthetic fixture path (b) is a
stand-in for the live CMEMS/ERA5 inputs rather than a byte-for-byte replica
of them, so its `mosaic:content_hash` differs from path (a) too. Each path
is independently reproducible across repeated runs (same inputs in, same
`mosaic:pipeline_hash` and `mosaic:content_hash` out).

```bash
# (a) live data — needs free CMEMS + CDS accounts (see docs/credentials.md)
python scripts/fetch_cs1_gulf_of_riga.py all
mosaic run pipelines/cs1_gulf_of_riga_upwelling.yaml

# (b) synthetic fixtures — no credentials, no network
python scripts/fetch_cs1_gulf_of_riga.py populate-fixtures
mosaic run tests/fixtures/cs1_gulf_of_riga_offline.yaml
```

The companion notebook `notebooks/cs1_gulf_of_riga_upwelling.ipynb` reads
the resulting Zarr store and reproduces every figure used in the paper's
Results section. After a fetch, run
`python scripts/fetch_cs1_gulf_of_riga.py manifest`
to emit `data/cs1_gulf_of_riga_manifest.json` with SHA-256 checksums — that
file is what gets uploaded alongside the data bundle to Zenodo, and
`python scripts/fetch_cs1_gulf_of_riga.py verify` cross-checks the local
files against it.

### CS2 and CS3

Two further case studies ship the same way — same `all` /
`populate-fixtures` / `manifest` / `verify` CLI shape as CS1, a live
pipeline YAML, an offline fixture YAML, and a companion notebook that
reproduces the paper figures:

```bash
# CS2 — Atlantic hurricane (Ida-like landfall, Aug-Sep 2021)
python scripts/fetch_cs2.py populate-fixtures   # or: all (needs CMEMS + CDS accounts)
mosaic run tests/fixtures/cs2_offline.yaml      # or: pipelines/cs2_atlantic_hurricane.yaml
# -> notebooks/cs2_atlantic_hurricane.ipynb

# CS3 — Arctic sea-ice retreat (September 2012)
python scripts/fetch_cs3.py populate-fixtures   # or: all (needs CDS account; NSIDC has no live connector)
mosaic run tests/fixtures/cs3_offline.yaml      # or: pipelines/cs3_arctic_seaice.yaml
# -> notebooks/cs3_arctic_seaice.ipynb
```

Source plugins, bbox/time bounds and what is/isn't a live connector for each
case study are documented in `docs/datasets.md`.

## License

MIT — see `LICENSE`.

## Citation

If you use MOSAIC, please cite the software via Zenodo (DOI assigned at
release) and the accompanying paper. See `CITATION.cff`.

## Contributing

Issues and PRs welcome on
<https://github.com/gagigr/mosaic-ocean/issues>.

## Funding & acknowledgments

MOSAIC is an academic project developed alongside a manuscript submitted to
*Computers & Geosciences*. Detailed acknowledgments will be listed at the
first stable release.
