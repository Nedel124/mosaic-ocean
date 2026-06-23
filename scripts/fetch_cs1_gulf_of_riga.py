"""Reproducible CS1 (Gulf of Riga upwelling) data acquisition.

Populates ``data/cache/`` with the CMEMS L4 SST and ERA5 10 m wind slices
needed by the Gulf of Riga CS1 workflow. The script also emits a manifest with
SHA-256 checksums so a data bundle can be verified elsewhere.

Subcommands
-----------
``sst``         Download CMEMS Baltic/North-Sea L4 SST for the CS1 window.
``wind``        Download ERA5 10 m wind components for the CS1 window.
``all``         Run ``sst`` then ``wind``.
``populate-fixtures``
                Skip the network and seed cache locations from deterministic
                CS1 Gulf-of-Riga test fixtures.
``manifest``    Emit ``data/cs1_gulf_of_riga_manifest.json`` with SHA-256.
``verify``      Verify files against the manifest.

Usage
-----
::

    # First-time fetch (requires CMEMS + CDS credentials):
    python scripts/fetch_cs1_gulf_of_riga.py all

    # Reviewer / CI without credentials:
    python scripts/fetch_cs1_gulf_of_riga.py populate-fixtures

    # Emit and verify manifest:
    python scripts/fetch_cs1_gulf_of_riga.py manifest
    python scripts/fetch_cs1_gulf_of_riga.py verify
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import typer

# ---------------------------------------------------------------------------
# CS1 configuration — Gulf of Riga upwelling, July 2021.
# ---------------------------------------------------------------------------

# Western Gulf of Riga domain used in the current CS1 workflow.
CS1_BBOX: tuple[float, float, float, float] = (22.0, 56.5, 24.8, 58.5)
CS1_TIME_START: datetime = datetime(2021, 7, 12)
CS1_TIME_STOP: datetime = datetime(2021, 7, 22)

# CMEMS Baltic / North-Sea daily L4 analysed SST.
# This is the same product family used in the live CS1 notebook; the local
# fixture normalises the variable to ``sea_surface_temperature`` and adds
# ``daily_median_sst`` for the spatial-anomaly workflow.
CMEMS_SST_DATASET_ID = "cmems_obs-sst_bal_phy-temp_my_l4_P1D-m"
CMEMS_SST_VARIABLE = "analysed_sst"

ERA5_DATASET = "reanalysis-era5-single-levels"
ERA5_VARIABLES = ["10m_u_component_of_wind", "10m_v_component_of_wind"]
ERA5_HOURS = ["00:00", "06:00", "12:00", "18:00"]

DEFAULT_CACHE_DIR = Path("data/cache")
DEFAULT_MANIFEST = Path("data/cs1_gulf_of_riga_manifest.json")
DEFAULT_FIXTURES_DIR = Path("tests/fixtures/cs1_gulf_of_riga")

# Cache locations used by the current CS1 Gulf of Riga workflow.
DEFAULT_CMEMS_CACHE_SUBDIR = Path("cmems/cs1_gulf_of_riga")
DEFAULT_ERA5_CACHE_SUBDIR = Path("era5/cs1_gulf_of_riga")

REPO_ROOT = Path(__file__).resolve().parents[1]

app = typer.Typer(
    add_completion=False,
    help="Fetch CMEMS + ERA5 inputs for the CS1 Gulf of Riga upwelling case study.",
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


@dataclass
class FetchPlan:
    """What a subcommand intends to do — printed in --dry-run."""

    label: str
    plugin: str
    target: Path
    notes: dict[str, Any]


def _resolve_repo_path(p: Path) -> Path:
    """Make a path absolute against the repo root if it isn't already."""
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
    """Return cache files (.nc) sorted by name. Tolerate missing dirs."""
    if not cache_dir.exists():
        return []
    return sorted(p for p in cache_dir.iterdir() if p.is_file() and p.suffix == ".nc")


def _load_fixture_builder(builder: Path):
    """Load the Gulf of Riga fixture builder even when tests/ is not a package."""
    spec = importlib.util.spec_from_file_location("build_cs1_gulf_of_riga_fixtures", builder)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load fixture builder: {builder}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# sst — CMEMS subset
# ---------------------------------------------------------------------------


def _do_sst(*, cache_dir: Path, dataset_id: str, dry_run: bool) -> None:
    cache_dir = _resolve_repo_path(cache_dir) / DEFAULT_CMEMS_CACHE_SUBDIR
    plan = FetchPlan(
        label="CMEMS L4 SST — Gulf of Riga",
        plugin="cmems",
        target=cache_dir,
        notes={
            "dataset": dataset_id,
            "var": CMEMS_SST_VARIABLE,
            "bbox": CS1_BBOX,
            "time": f"{CS1_TIME_START.date()}…{CS1_TIME_STOP.date()}",
        },
    )
    _print_plan(plan)
    if dry_run:
        typer.echo("(dry-run, no network calls)")
        return

    from mosaic.sources.base import SourceQuery
    from mosaic.sources.cmems import CmemsSource

    src = CmemsSource(
        source_id="cmems_sst",
        dataset_id=dataset_id,
        variables=[CMEMS_SST_VARIABLE],
        cache_dir=str(cache_dir),
    )
    query = SourceQuery(
        bbox=CS1_BBOX, time_start=CS1_TIME_START, time_stop=CS1_TIME_STOP
    )
    ds = src.fetch(query)
    typer.secho(
        f"[ok] cmems_sst — cache_hit={ds.attrs.get('mosaic_cache_hit')} "
        f"shape={dict(ds.sizes)}",
        fg=typer.colors.GREEN,
    )


@app.command(help="Download CMEMS L4 SST subset for the CS1 Gulf of Riga window.")
def sst(
    cache_dir: Path = typer.Option(DEFAULT_CACHE_DIR, "--cache-dir"),
    dataset_id: str = typer.Option(CMEMS_SST_DATASET_ID, "--dataset-id"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    _do_sst(cache_dir=cache_dir, dataset_id=dataset_id, dry_run=dry_run)


# ---------------------------------------------------------------------------
# wind — ERA5
# ---------------------------------------------------------------------------


def _do_wind(*, cache_dir: Path, dataset: str, dry_run: bool) -> None:
    cache_dir = _resolve_repo_path(cache_dir) / DEFAULT_ERA5_CACHE_SUBDIR
    plan = FetchPlan(
        label="ERA5 10 m wind — Gulf of Riga",
        plugin="era5",
        target=cache_dir,
        notes={
            "dataset": dataset,
            "vars": ERA5_VARIABLES,
            "hours": ERA5_HOURS,
            "bbox": CS1_BBOX,
            "time": f"{CS1_TIME_START.date()}…{CS1_TIME_STOP.date()}",
        },
    )
    _print_plan(plan)
    if dry_run:
        typer.echo("(dry-run, no network calls)")
        return

    from mosaic.sources.base import SourceQuery
    from mosaic.sources.era5 import Era5Source

    src = Era5Source(
        source_id="era5_wind",
        variables=ERA5_VARIABLES,
        dataset=dataset,
        hours=ERA5_HOURS,
        cache_dir=str(cache_dir),
    )
    query = SourceQuery(
        bbox=CS1_BBOX, time_start=CS1_TIME_START, time_stop=CS1_TIME_STOP
    )
    ds = src.fetch(query)
    typer.secho(
        f"[ok] era5_wind — cache_hit={ds.attrs.get('mosaic_cache_hit')} "
        f"shape={dict(ds.sizes)}",
        fg=typer.colors.GREEN,
    )


@app.command(help="Download ERA5 10 m wind components for the CS1 Gulf of Riga window.")
def wind(
    cache_dir: Path = typer.Option(DEFAULT_CACHE_DIR, "--cache-dir"),
    dataset: str = typer.Option(ERA5_DATASET, "--dataset"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    _do_wind(cache_dir=cache_dir, dataset=dataset, dry_run=dry_run)


# ---------------------------------------------------------------------------
# all
# ---------------------------------------------------------------------------


@app.command(name="all", help="Run sst and wind in sequence.")
def fetch_all(
    cache_dir: Path = typer.Option(DEFAULT_CACHE_DIR, "--cache-dir"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    _do_sst(cache_dir=cache_dir, dataset_id=CMEMS_SST_DATASET_ID, dry_run=dry_run)
    _do_wind(cache_dir=cache_dir, dataset=ERA5_DATASET, dry_run=dry_run)


# ---------------------------------------------------------------------------
# populate-fixtures (offline-friendly path)
# ---------------------------------------------------------------------------


@app.command(
    name="populate-fixtures",
    help="Seed cache locations from deterministic CS1 Gulf-of-Riga fixtures.",
)
def populate_fixtures(
    cache_dir: Path = typer.Option(DEFAULT_CACHE_DIR, "--cache-dir"),
    fixtures_dir: Path = typer.Option(DEFAULT_FIXTURES_DIR, "--fixtures-dir"),
) -> None:
    cache_dir = _resolve_repo_path(cache_dir)
    fixtures_dir = _resolve_repo_path(fixtures_dir)

    expected = {
        "cmems_sst": fixtures_dir / "cmems_gulf_of_riga_sst_2021-07.nc",
        "era5_wind": fixtures_dir / "era5_gulf_of_riga_wind_2021-07.nc",
    }

    if not all(p.exists() for p in expected.values()):
        builder = REPO_ROOT / "tests" / "fixtures" / "build_cs1_gulf_of_riga_fixtures.py"
        if not builder.exists():
            typer.secho(
                f"[err] missing fixtures and builder not found: {builder}",
                fg=typer.colors.RED,
            )
            raise typer.Exit(code=2)
        module = _load_fixture_builder(builder)
        built = module.build_all(fixtures_dir)
        expected = {k: Path(v) for k, v in built.items()}

    src_to_dst = {
        expected["cmems_sst"]: cache_dir / DEFAULT_CMEMS_CACHE_SUBDIR / "cmems_gulf_of_riga_sst_2021-07.nc",
        expected["era5_wind"]: cache_dir / DEFAULT_ERA5_CACHE_SUBDIR / "era5_gulf_of_riga_wind_2021-07.nc",
    }

    for src, dst in src_to_dst.items():
        if not src.exists():
            typer.secho(f"[err] missing fixture: {src}", fg=typer.colors.RED)
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
    out: Path = typer.Option(DEFAULT_MANIFEST, "--out"),
) -> None:
    cache_dir = _resolve_repo_path(cache_dir)
    out = _resolve_repo_path(out)

    files: list[Path] = []
    files.extend(_existing_cache_files(cache_dir / DEFAULT_CMEMS_CACHE_SUBDIR))
    files.extend(_existing_cache_files(cache_dir / DEFAULT_ERA5_CACHE_SUBDIR))

    if not files:
        typer.secho(
            "[warn] no files found — run `sst`, `wind`, `all`, or `populate-fixtures` first.",
            fg=typer.colors.YELLOW,
        )

    payload = {
        "version": 1,
        "case_study": "CS1 — Gulf of Riga coastal upwelling, July 2021",
        "bbox": list(CS1_BBOX),
        "time_start": CS1_TIME_START.isoformat(),
        "time_stop": CS1_TIME_STOP.isoformat(),
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


# ---------------------------------------------------------------------------
# misc
# ---------------------------------------------------------------------------


def _download_to(url: str, dest: Path) -> None:
    """Stream a remote file into ``dest`` using urllib (stdlib only)."""
    import urllib.request

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url) as resp, tmp.open("wb") as fh:  # noqa: S310 (audited URL)
        shutil.copyfileobj(resp, fh)
    os.replace(tmp, dest)


if __name__ == "__main__":
    app()
