"""Reproducible CS3 (Arctic sea-ice retreat) data acquisition.

Mirrors :file:`scripts/fetch_cs1.py` for the Arctic sea-ice case study.
Populates ``data/cache/`` with the NSIDC daily sea-ice concentration field
(G02202 climate-data record) and the ERA5 single-levels surface fields
(2 m air temperature, mean sea-level pressure) that
``pipelines/cs3_arctic_seaice.yaml`` consumes, and computes (or downloads)
the September 1991-2020 SIC climatology.

Subcommands
-----------
``sic``         Fetch (or copy) the NSIDC daily SIC field for the CS3 window.
``surface``     Download ERA5 single-levels (t2m, msl) for the window.
``climatology`` Compute (or download) the September SIC climatology.
``all``         Run sic / surface / climatology in sequence.
``manifest``    (Re-)emit ``data/cs3_manifest.json``.
``verify``      Verify the on-disk files against ``data/cs3_manifest.json``.
``populate-fixtures``
                Skip the network and seed the cache locations from the
                synthetic test fixtures.

The NSIDC G02202 record is delivered through the NSIDC DAAC; in
production we use a thin :class:`mosaic.sources.local.LocalNetcdfSource`
pointing at the file fetched here. The ``sic`` subcommand exposes a
``--source-uri`` option to point at any HTTP/HTTPS NetCDF endpoint.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import typer

# ---------------------------------------------------------------------------
# CS3 configuration — single source of truth for the case study.
# ---------------------------------------------------------------------------

CS3_BBOX: tuple[float, float, float, float] = (-170.0, 70.0, -130.0, 80.0)
CS3_TIME_START: datetime = datetime(2012, 9, 1)
CS3_TIME_STOP: datetime = datetime(2012, 9, 15)

ERA5_DATASET = "reanalysis-era5-single-levels"
ERA5_VARIABLES = ["2m_temperature", "mean_sea_level_pressure"]
ERA5_HOURS = ["00:00", "06:00", "12:00", "18:00"]

DEFAULT_CACHE_DIR = Path("data/cache")
DEFAULT_CLIM_DIR = Path("data/climatologies")
DEFAULT_NSIDC_DIR = Path("data/cache/nsidc")
DEFAULT_MANIFEST = Path("data/cs3_manifest.json")
DEFAULT_FIXTURES_DIR = Path("tests/fixtures/cs3")
DEFAULT_CLIM_YEARS = (1991, 2020)

REPO_ROOT = Path(__file__).resolve().parents[1]


app = typer.Typer(
    add_completion=False,
    help="Fetch NSIDC SIC + ERA5 inputs for the CS3 Arctic sea-ice case study.",
)


# ---------------------------------------------------------------------------
# Shared helpers (kept local for self-containment).
# ---------------------------------------------------------------------------


@dataclass
class FetchPlan:
    label: str
    plugin: str
    target: Path
    notes: dict[str, Any]


def _resolve_repo_path(p: Path) -> Path:
    return p if p.is_absolute() else REPO_ROOT / p


def _sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def _print_plan(plan: FetchPlan) -> None:
    typer.secho(f"[plan] {plan.label}", fg=typer.colors.CYAN, bold=True)
    typer.echo(f"       plugin : {plan.plugin}")
    typer.echo(f"       target : {plan.target}")
    for k, v in plan.notes.items():
        typer.echo(f"       {k:<7}: {v}")


def _existing_cache_files(cache_dir: Path) -> list[Path]:
    if not cache_dir.exists():
        return []
    return sorted(p for p in cache_dir.iterdir() if p.is_file() and p.suffix == ".nc")


def _download_to(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url) as resp, tmp.open("wb") as fh:  # noqa: S310 (audited URL)
        shutil.copyfileobj(resp, fh)
    os.replace(tmp, dest)


# ---------------------------------------------------------------------------
# Subcommand implementations
# ---------------------------------------------------------------------------


def _do_sic(*, nsidc_dir: Path, source_uri: str | None, dry_run: bool) -> None:
    nsidc_dir = _resolve_repo_path(nsidc_dir)
    target = nsidc_dir / "g02202_v4_sic_2012-09.nc"
    plan = FetchPlan(
        label="NSIDC daily sea-ice concentration (G02202-like)",
        plugin="nsidc",
        target=target,
        notes={
            "source_uri": source_uri or "(unset — pass --source-uri or use populate-fixtures)",
            "bbox": CS3_BBOX,
            "time": f"{CS3_TIME_START.date()}…{CS3_TIME_STOP.date()}",
        },
    )
    _print_plan(plan)
    if dry_run:
        typer.echo("(dry-run, no network calls)")
        return

    if source_uri is None:
        typer.secho(
            "[err] CS3 SIC fetch requires --source-uri pointing at the NSIDC file. "
            "Use `populate-fixtures` for an offline run.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=2)

    if target.exists():
        typer.secho(f"[skip] {target} already exists — delete to re-download", fg=typer.colors.YELLOW)
        return
    _download_to(source_uri, target)
    typer.secho(f"[ok] NSIDC SIC fetched to {target}", fg=typer.colors.GREEN)


def _do_surface(*, cache_dir: Path, dataset: str, dry_run: bool) -> None:
    cache_dir = _resolve_repo_path(cache_dir) / "era5"
    plan = FetchPlan(
        label="ERA5 surface subset (t2m, msl)",
        plugin="era5",
        target=cache_dir,
        notes={
            "dataset": dataset,
            "vars": ERA5_VARIABLES,
            "hours": ERA5_HOURS,
            "bbox": CS3_BBOX,
            "time": f"{CS3_TIME_START.date()}…{CS3_TIME_STOP.date()}",
        },
    )
    _print_plan(plan)
    if dry_run:
        typer.echo("(dry-run, no network calls)")
        return

    from mosaic.sources.base import SourceQuery
    from mosaic.sources.era5 import Era5Source

    src = Era5Source(
        source_id="era5_surface",
        variables=ERA5_VARIABLES,
        dataset=dataset,
        hours=ERA5_HOURS,
        cache_dir=str(cache_dir),
    )
    query = SourceQuery(
        bbox=CS3_BBOX, time_start=CS3_TIME_START, time_stop=CS3_TIME_STOP
    )
    ds = src.fetch(query)
    typer.secho(
        f"[ok] era5_surface — cache_hit={ds.attrs.get('mosaic_cache_hit')} "
        f"shape={dict(ds.sizes)}",
        fg=typer.colors.GREEN,
    )


def _do_climatology(
    *,
    out_path: Path,
    download_url: str | None,
    dry_run: bool,
) -> None:
    out_path = _resolve_repo_path(out_path)
    plan = FetchPlan(
        label="September SIC climatology (1991-2020)",
        plugin="cmems-derived" if download_url is None else "url",
        target=out_path,
        notes={"url": download_url or "(populate-fixtures provides the synthetic baseline)"},
    )
    _print_plan(plan)
    if dry_run:
        typer.echo("(dry-run, no network calls)")
        return

    if download_url:
        _download_to(download_url, out_path)
        typer.secho(f"[ok] climatology fetched to {out_path}", fg=typer.colors.GREEN)
        return

    typer.secho(
        "[err] CS3 climatology compute is not yet implemented for live data. "
        "Pass --download-url, or use `populate-fixtures` for the synthetic baseline.",
        fg=typer.colors.RED,
    )
    raise typer.Exit(code=2)


# ---------------------------------------------------------------------------
# Typer wrappers
# ---------------------------------------------------------------------------


@app.command(help="Fetch NSIDC daily sea-ice concentration for the CS3 window.")
def sic(
    nsidc_dir: Path = typer.Option(DEFAULT_NSIDC_DIR, "--nsidc-dir"),
    source_uri: str = typer.Option(None, "--source-uri"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    _do_sic(nsidc_dir=nsidc_dir, source_uri=source_uri, dry_run=dry_run)


@app.command(help="Download ERA5 surface subset (t2m, msl) for the CS3 window.")
def surface(
    cache_dir: Path = typer.Option(DEFAULT_CACHE_DIR, "--cache-dir"),
    dataset: str = typer.Option(ERA5_DATASET, "--dataset"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    _do_surface(cache_dir=cache_dir, dataset=dataset, dry_run=dry_run)


@app.command(help="Compute (or fetch from URL) the September SIC climatology.")
def climatology(
    out_path: Path = typer.Option(
        DEFAULT_CLIM_DIR / "arctic_sic_climatology_sep.nc", "--out-path"
    ),
    download_url: str = typer.Option(None, "--download-url"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    _do_climatology(out_path=out_path, download_url=download_url, dry_run=dry_run)


@app.command(name="all", help="Run sic, surface, climatology in sequence.")
def fetch_all(
    cache_dir: Path = typer.Option(DEFAULT_CACHE_DIR, "--cache-dir"),
    nsidc_dir: Path = typer.Option(DEFAULT_NSIDC_DIR, "--nsidc-dir"),
    clim_out: Path = typer.Option(
        DEFAULT_CLIM_DIR / "arctic_sic_climatology_sep.nc", "--clim-out"
    ),
    source_uri: str = typer.Option(None, "--source-uri"),
    download_url: str = typer.Option(None, "--download-url"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    _do_sic(nsidc_dir=nsidc_dir, source_uri=source_uri, dry_run=dry_run)
    _do_surface(cache_dir=cache_dir, dataset=ERA5_DATASET, dry_run=dry_run)
    _do_climatology(out_path=clim_out, download_url=download_url, dry_run=dry_run)


# ---------------------------------------------------------------------------
# populate-fixtures
# ---------------------------------------------------------------------------


@app.command(
    name="populate-fixtures",
    help="Seed cache locations from the synthetic test fixtures (no network).",
)
def populate_fixtures(
    cache_dir: Path = typer.Option(DEFAULT_CACHE_DIR, "--cache-dir"),
    nsidc_dir: Path = typer.Option(DEFAULT_NSIDC_DIR, "--nsidc-dir"),
    clim_out: Path = typer.Option(
        DEFAULT_CLIM_DIR / "arctic_sic_climatology_sep.nc", "--clim-out"
    ),
    fixtures_dir: Path = typer.Option(DEFAULT_FIXTURES_DIR, "--fixtures-dir"),
) -> None:
    cache_dir = _resolve_repo_path(cache_dir)
    nsidc_dir = _resolve_repo_path(nsidc_dir)
    clim_out = _resolve_repo_path(clim_out)
    fixtures_dir = _resolve_repo_path(fixtures_dir)

    if not fixtures_dir.exists():
        sys.path.insert(0, str(REPO_ROOT))
        from tests.fixtures.build_cs3_fixtures import build_all  # type: ignore

        build_all(fixtures_dir)

    src_to_dst = {
        fixtures_dir / "nsidc_arctic_sic_2012-09.nc":
            nsidc_dir / "g02202_v4_sic_2012-09.nc",
        fixtures_dir / "era5_arctic_surface_2012-09.nc":
            cache_dir / "era5" / "era5_surface_offline.nc",
        fixtures_dir / "arctic_sic_climatology_sep.nc": clim_out,
    }
    for src, dst in src_to_dst.items():
        if not src.exists():
            raise typer.Exit(code=2)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        typer.secho(f"[ok] {src.name} -> {dst.relative_to(REPO_ROOT)}", fg=typer.colors.GREEN)


# ---------------------------------------------------------------------------
# manifest + verify
# ---------------------------------------------------------------------------


@app.command(help="Re-emit the SHA-256 manifest from whatever is on disk.")
def manifest(
    cache_dir: Path = typer.Option(DEFAULT_CACHE_DIR, "--cache-dir"),
    nsidc_dir: Path = typer.Option(DEFAULT_NSIDC_DIR, "--nsidc-dir"),
    clim_dir: Path = typer.Option(DEFAULT_CLIM_DIR, "--clim-dir"),
    out: Path = typer.Option(DEFAULT_MANIFEST, "--out"),
) -> None:
    cache_dir = _resolve_repo_path(cache_dir)
    nsidc_dir = _resolve_repo_path(nsidc_dir)
    clim_dir = _resolve_repo_path(clim_dir)
    out = _resolve_repo_path(out)
    files: list[Path] = []
    files.extend(_existing_cache_files(nsidc_dir))
    files.extend(_existing_cache_files(cache_dir / "era5"))
    if clim_dir.exists():
        files.extend(_existing_cache_files(clim_dir))

    if not files:
        typer.secho(
            "[warn] no files found — run `sic`, `surface`, `climatology`, or "
            "`populate-fixtures` first.",
            fg=typer.colors.YELLOW,
        )

    payload = {
        "version": 1,
        "case_study": "CS3 — Arctic sea-ice retreat, September 2012",
        "bbox": list(CS3_BBOX),
        "time_start": CS3_TIME_START.isoformat(),
        "time_stop": CS3_TIME_STOP.isoformat(),
        "files": [
            {
                "path": str(p.relative_to(REPO_ROOT)),
                "size_bytes": p.stat().st_size,
                "sha256": _sha256_file(p),
            }
            for p in files
        ],
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2))
    typer.secho(f"[ok] wrote {out} ({len(files)} files)", fg=typer.colors.GREEN)


@app.command(help="Verify on-disk files match the manifest checksums.")
def verify(
    manifest_path: Path = typer.Option(DEFAULT_MANIFEST, "--manifest"),
) -> None:
    manifest_path = _resolve_repo_path(manifest_path)
    if not manifest_path.exists():
        typer.secho(f"[err] no manifest at {manifest_path}", fg=typer.colors.RED)
        raise typer.Exit(code=2)
    payload = json.loads(manifest_path.read_text())

    bad = 0
    for entry in payload["files"]:
        path = REPO_ROOT / entry["path"]
        if not path.exists():
            typer.secho(f"[miss] {entry['path']}", fg=typer.colors.RED)
            bad += 1
            continue
        actual = _sha256_file(path)
        if actual != entry["sha256"]:
            typer.secho(
                f"[bad ] {entry['path']}\n        want {entry['sha256']}\n        got  {actual}",
                fg=typer.colors.RED,
            )
            bad += 1
        else:
            typer.secho(f"[ok  ] {entry['path']}", fg=typer.colors.GREEN)

    if bad:
        typer.secho(f"\n{bad} file(s) failed verification", fg=typer.colors.RED, bold=True)
        raise typer.Exit(code=1)
    typer.secho(f"\nall {len(payload['files'])} files verified", fg=typer.colors.GREEN, bold=True)


if __name__ == "__main__":
    app()
