# Reproducibility

MOSAIC distinguishes two independent guarantees, both recorded as STAC
properties on every run:

| property | derived from | captures |
|-|-|-|
| `mosaic:pipeline_hash` | canonical YAML form of the `PipelineSpec` (`PipelineSpec.canonical_yaml()`) | processing *intent* — domain, sources, harmonize/QC/fuse/export config |
| `mosaic:content_hash` | sorted coords + data vars of the fused `xarray.Dataset` (name, dtype, shape, raw bytes; `src/mosaic/prov/hashing.py`) | output *bytes* |

Both hashes use BLAKE3 when available, falling back to SHA-256 (prefixed
`blake3:`/`sha256:` so the algorithm is self-describing). Attribute metadata
does **not** affect `mosaic:content_hash` — only data and shape do. Inspect
either hash on a finished run with:

```bash
mosaic prov show out/<name>.zarr.stac.json
```

## What is guaranteed

- **Same pipeline, same inputs → same `mosaic:content_hash`.** Re-running an
  unchanged YAML file against an unchanged cache (or unchanged fixtures)
  reproduces byte-identical output. This is what
  `tests/test_cs1_gulf_of_riga.py::test_cs1_gulf_of_riga_two_runs_same_content_hash`
  checks.
- **Same YAML file → same `mosaic:pipeline_hash`**, regardless of which
  inputs feed it. The hash is derived from the *entire* canonical spec
  (domain, source plugins and params, harmonize/QC/fuse/export config), not
  just the conceptual processing steps — so it changes whenever any of that
  changes, including which source plugin is used or where the output is
  written.

## Temporal alignment and derived-variable provenance

- **`harmonize.time_alignment` is applied between harmonization and QC.**
  `_apply_time_alignment()` (`src/mosaic/runner.py`) resamples the harmonized
  dataset before any QC rule, derived variable or mask sees it:
  `daily_mean`/`hourly_mean` call `ds.resample(time=...).mean(keep_attrs=True)`,
  `instantaneous`/`nearest` are no-ops. This is what realises the "aggregated
  to daily means" claims in `docs/datasets.md` for the `00/06/12/18` UTC
  ERA5 pulls in CS1–CS3 — all three offline fixtures declare
  `time_alignment: daily_mean`. Covered by
  `tests/test_time_alignment.py::test_daily_mean_time_alignment`.
- **Derived-variable provenance attrs (`long_name`, `mosaic:expression`,
  `mosaic:derived`) are force-assigned per variable**, not merged with
  `dict.setdefault`. xarray's default `keep_attrs` behaviour carries a
  DataArray's attrs into the result of a binary op against a scalar (e.g.
  `wind_speed > 4.0` inherits `wind_speed`'s attrs), so a later derived
  variable referencing an earlier one could otherwise end up with the
  *earlier* variable's `mosaic:expression` recorded in its own metadata
  (`src/mosaic/derive/evaluator.py`). This does not affect
  `mosaic:content_hash` (attrs are excluded from it — see above) but did
  affect the accuracy of `mosaic:harmonization.derived` provenance.

## What is *not* guaranteed

- **Neither `mosaic:pipeline_hash` nor `mosaic:content_hash` is shared
  between live and offline-fixture runs of the same case study.** The two
  paths are declared as separate YAML files with different source plugins
  (e.g. `cmems`/`era5` for live vs. `local_netcdf` for the offline fixture
  in CS1) and different export paths, so `mosaic:pipeline_hash` already
  differs before any data is read. The offline fixture is a deterministic,
  schema-compatible stand-in for the live upstream product, not a
  byte-for-byte replica of it, so its data — and therefore its
  `mosaic:content_hash` — differs too. Its job is to prove the *declared
  processing path executes deterministically without credentials*, not to
  reproduce live-data diagnostics. For CS1 (Gulf of Riga, July 2021)
  specifically:
  - the live CMEMS/ERA5 workflow reports **183** SST-anomaly cells and an
    **empty (0-cell)** pixel-wise SST–wind intersection on 2021-07-16;
  - the offline fixture is only required to produce a non-empty SST-led mask
    whose pixel-wise intersection is no larger than that mask
    (`tests/test_cs1_gulf_of_riga.py`) — it is neither expected nor asserted
    to reproduce the 183/0 live counts.
- **Environment pinning is partial.** Each STAC sidecar records a
  `mosaic:environment` fingerprint (Python version/implementation, OS,
  machine — see `_environment_fingerprint()` in `src/mosaic/prov/stac.py`),
  but MOSAIC does not currently emit a dependency lock file enumerating
  pinned package versions.
- **`spec.reproducibility.seed` and `spec.reproducibility.strict_versions`
  are declared but not yet enforced.** Both fields exist on
  `ReproducibilitySpec` (`src/mosaic/_spec.py`) and are accepted by the
  pipeline schema, but the runner does not currently read either of them —
  there is no stochastic stage to seed yet, and no version-pinning check is
  performed. Treat them as reserved for a future release.

## Cache-based reproducibility (live path)

Connectors are cache-first: a request is keyed by
`(dataset_id, bbox, time_window, variables)` and stored as NetCDF under
`data/cache/<plugin>/`. Once the cache is warm, re-running the same pipeline
produces the same `mosaic:content_hash` even on a machine with no CMEMS or
CDS account — the cache *is* the reproducibility artefact. See
`docs/credentials.md` for the cache layout and what each connector does and
does not send upstream.

## CS1 reproduction paths

```bash
# (a) live data — needs free CMEMS + CDS accounts (see docs/credentials.md)
python scripts/fetch_cs1_gulf_of_riga.py all
mosaic run pipelines/cs1_gulf_of_riga_upwelling.yaml

# (b) synthetic fixtures — no credentials, no network
python scripts/fetch_cs1_gulf_of_riga.py populate-fixtures
mosaic run tests/fixtures/cs1_gulf_of_riga_offline.yaml
```

Both paths run the same processing stages (ingest → QC → harmonize → fuse →
export) and produce the same derived variables, but as distinct YAML
pipelines they have distinct `mosaic:pipeline_hash` and `mosaic:content_hash`
values; only path (a) is expected to match the live diagnostics reported in
the paper. See `docs/datasets.md` for dataset identifiers, license terms and
bbox/time bounds.
