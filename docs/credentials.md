# Credentials for live-mode connectors

MOSAIC connectors never store or capture credentials. They pass through
whatever the underlying client library finds in its standard locations.
This page documents the *exact* locations each connector reads from, so
that running `python scripts/fetch_cs1_gulf_of_riga.py all` succeeds without surprises.

> If you only want to *exercise* the CS1 pipeline without registering
> for any service, run `python scripts/fetch_cs1_gulf_of_riga.py populate-fixtures`.
> That seeds `data/cache/` from the synthetic test fixtures, which the
> pipeline accepts as drop-in replacements (same NetCDF schema, same
> harmonization overrides, same harness).

## Copernicus Marine (CMEMS)

Used by `CmemsSource` for the Baltic L4 SST product. Backend: the
official [`copernicusmarine`](https://pypi.org/project/copernicusmarine/)
toolbox.

1. Register a **free** account at <https://marine.copernicus.eu>.
2. Install the optional extra:

   ```bash
   pip install "mosaic-ocean[copernicus]"
   ```

3. Provide credentials by **either** of:

   **Environment variables** (preferred for CI):

   ```bash
   export COPERNICUSMARINE_SERVICE_USERNAME="your-username"
   export COPERNICUSMARINE_SERVICE_PASSWORD="your-password"
   ```

   **Persistent login file** (preferred for workstations):

   ```bash
   copernicusmarine login   # writes ~/.copernicusmarine/.copernicusmarine-credentials
   ```

The toolbox checks env vars first, then `~/.copernicusmarine/`. MOSAIC does
not redact credentials in error traces — the toolbox is responsible for
that, and the current versions do.

## Climate Data Store (ERA5)

Used by `Era5Source`. Backend:
[`cdsapi`](https://pypi.org/project/cdsapi/).

1. Register a **free** account at <https://cds.climate.copernicus.eu>.
2. Accept the *Terms of use* of the **ERA5 hourly data on single levels
   from 1940 to present** dataset on the dataset page itself
   (one-time click).
3. Install the optional extra:

   ```bash
   pip install "mosaic-ocean[cds]"
   ```

4. Configure the API key. CDS provides a small snippet on the *API key*
   page in your profile; it goes into `~/.cdsapirc`:

   ```ini
   url: https://cds.climate.copernicus.eu/api
   key: <UID>:<API-KEY>
   ```

   Or, equivalently, set environment variables:

   ```bash
   export CDSAPI_URL="https://cds.climate.copernicus.eu/api"
   export CDSAPI_KEY="<UID>:<API-KEY>"
   ```

## Cache hits don't need credentials

Both connectors are cache-first: a request is keyed by
`(dataset_id, bbox, time_window, variables)` and stored as NetCDF in
`data/cache/<plugin>/`. Once the cache is warm, the same pipeline run
produces an identical `mosaic:content_hash` on a machine that has no
CMEMS or CDS account. This is the mechanism that makes Zenodo-backed
reproducibility possible: the data archive is the cache, and reviewers
only need `pip install mosaic-ocean` plus the published bundle.

## What gets sent and what does *not*

| | sent to upstream service | recorded in STAC sidecar |
|-|-|-|
| dataset id, bbox, time, variables | ✅ | ✅ (`mosaic:inputs[*]`) |
| credentials | ✅ (toolbox manages this) | ❌ |
| hostname / username | ❌ | ❌ |

The sidecar lists the *plugin* used (`cmems`, `era5`) and the cache URI
(local path), so a reader can reconstruct the upstream request without
ever seeing a token.
