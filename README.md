# MOSAIC

**Multi-source Ocean Sensor And model Integration Catalogue**

A lightweight, open-source Python library for declarative, reproducible integration of heterogeneous oceanographic data — satellite, numerical model, and in-situ observations — with automatic semantic harmonization, quality control, and content-addressable provenance recorded as STAC metadata.

> **Status:** alpha (`v0.1.0.dev0`). Public API may still change.

## What MOSAIC does

- Pulls data from multiple sources through a pluggable connector interface (Copernicus Marine, ERA5/CDS, Sentinel-3 STAC, NDBC, IBTrACS, OSI SAF, ...).
- Harmonizes variable names, units, CRS and temporal axes against the CF Standard Name Table (v85) and three domain-specific dictionaries (Baltic / Atlantic / Arctic).
- Runs a configurable pipeline (`ingest → QC → harmonize → fuse → export`).
- Records full provenance as a STAC Item with the `mosaic` extension (pipeline hash, content hash, mapping accuracy, QC statistics, environment).
- Exports to Zarr (default) or NetCDF-CF.
- Ships a CLI (`mosaic run pipeline.yaml`) and a Python API.

## What MOSAIC does **not** do

- It does **not** host a server. THREDDS/ERDDAP/OGC services are *consumed*, not replaced.
- It does **not** ship a GUI or dashboard.
- It does **not** invent its own storage format. We use Zarr / NetCDF / STAC.
- It does **not** include numerical models or data-assimilation algorithms — MOSAIC is the *integration* layer.

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
mosaic run     pipelines/example_minimal.yaml
mosaic prov show out/example.zarr.stac.json
```

Or build it programmatically:

```python
import mosaic as ms

pipe = (
    ms.Pipeline(name="demo")
    .domain(bbox=(14.0, 54.0, 22.0, 60.0), time_start="2022-06-01", time_stop="2022-06-07")
    .add_source(ms.sources.DummySource(variables=["sst", "u10"]))
    .harmonize(cf_dictionary="configs/cf_baltic.yaml")
    .qc(rules={"sst": {"type": "range", "min": -2.0, "max": 35.0}})
    .export(path="out/demo.zarr")
)
result = pipe.run()
print(result.provenance.id)
print(result.qc_report)
```

## Pipeline file format

A pipeline is a single YAML file validated by [pydantic](https://docs.pydantic.dev/). Minimal example:

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

Each connector reads credentials from two locations, with environment variables taking priority:

1. `CMEMS_USERNAME`, `CMEMS_PASSWORD`, `CDSAPI_KEY`, ... (env)
2. `~/.mosaic/credentials` (TOML)

Credentials never appear in logs or in STAC provenance.

## How does it compare?

MOSAIC sits in the *integration / harmonization* niche of the ocean data stack. It uses xarray + Zarr + STAC under the hood, and is complementary to:

- **THREDDS / ERDDAP** — data servers (we consume them);
- **Pangeo** — compute substrate (we build on it);
- **STAC / intake** — catalog standards (we adopt them);
- **Argopy / OceanSpy** — domain libraries (we wrap or coexist).

A more detailed comparison is in `RELATED_WORK.md` of the companion paper.

## Reproducibility

Every run produces:

- a STAC Item with content hashes for inputs and outputs (saved as `<output>.stac.json`),
- a deterministic re-run guarantee for non-stochastic stages.

### CS1 — Gulf of Riga coastal upwelling, July 2021

The first case study ships end-to-end. Two reproduction paths are supported, both producing the same `mosaic:content_hash`:

```bash
# (a) live data — needs free CMEMS + CDS accounts (see docs/credentials.md)
python scripts/fetch_cs1_gulf_of_riga.py all
mosaic run pipelines/cs1_gulf_of_riga_upwelling.yaml

# (b) synthetic fixtures — no credentials, no network
python scripts/fetch_cs1_gulf_of_riga.py populate-fixtures
mosaic run tests/fixtures/cs1_gulf_of_riga_offline.yaml
```

The companion notebook `notebooks/cs1_gulf_of_riga_upwelling.ipynb` reads the resulting Zarr store and reproduces every figure used in the paper's Results section.

After a fetch, run `python scripts/fetch_cs1_gulf_of_riga.py manifest` to emit `data/cs1_gulf_of_riga_manifest.json` with SHA-256 checksums — that file is what gets uploaded alongside the data bundle to Zenodo, and `python scripts/fetch_cs1_gulf_of_riga.py verify` cross-checks the local files against it.

Dataset identifiers, license terms and bbox/time bounds are documented in `docs/datasets.md`.

## License

MIT — see `LICENSE`.

## Citation

If you use MOSAIC, please cite the software via Zenodo (DOI assigned at release) and the accompanying paper. See `CITATION.cff`.

## Contributing

Issues and PRs welcome on [GitHub](https://github.com/Nedel124/mosaic-ocean).

## Funding & acknowledgments

MOSAIC is an academic project developed alongside a manuscript submitted to *Computers & Geosciences*. Detailed acknowledgments will be listed at the first stable release.
