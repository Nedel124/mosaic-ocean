"""Reproducible CS2 (Atlantic hurricane) data acquisition.

Mirrors :file:`scripts/fetch_cs1.py` for the Atlantic-hurricane case study.
Populates ``data/cache/`` with the CMEMS Global L4 SST and ERA5 multi-variable
atmospheric subsets that ``pipelines/cs2_atlantic_hurricane.yaml`` consumes,
plus copies the bundled IBTrACS-style track CSV into the data directory.
Emits a SHA-256 manifest so the resulting bundle can be uploaded to Zenodo
and verified elsewhere.

Subcommands
-----------
``sst``         Download CMEMS Global L4 SST for the CS2 window.
``atmos``       Download ERA5 single-levels (u10, v10, msl, tp) for the window.
``track``       Copy the bundled IBTrACS-style CSV into the data directory.
``all``         Run ``sst`` then ``atmos`` then ``track``.
``manifest``    (Re-)emit ``data/cs2_manifest.json`` from whatever is on disk.
``verify``      Verify the on-disk files against ``data/cs2_manifest.json``.
``populate-fixtures``
                Skip the network and seed the cache locations from the
                synthetic test fixtures.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import typer

# ---------------------------------------------------------------------------
# CS2 configuration — single source of truth for the case study.
# ---------------------------------------------------------------------------

CS2_BBOX: tuple[float, float, float, float] = (-95.0, 18.0, -78.0, 32.0)
CS2_TIME_START: datetime = datetime(2021, 8, 26)
CS2_TIME_STOP: datetime = datetime(2021, 9, 2)

# Global OSTIA L4 SST, 0.05 deg daily reprocessed (Met Office), kept in sync
# with `pipelines/cs2_atlantic_hurricane.yaml`. The legacy CMEMS-1.x id
# `cmems_obs-sst_glo_phy_l4_my_P1D-m` no longer resolves after the Marine
# Data Store migration; verified live on 2026-05-12 via
# `copernicusmarine.describe(contains=["GLO","SST","L4"])`.
CMEMS_SST_DATASET_ID = "METOFFICE-GLO-SST-L4-REP-OBS-SST"
CMEMS_SST_VARIABLE = "analysed_sst"
ERA5_DATASET = "reanalysis-era5-single-levels"
ERA5_VARIABLES = [
    "10m_u_component_of_wind",
    "10m_v_component_of_wind",
    "mean_sea_level_pressure",
    "total_precipitation",
]
ERA5_HOURS = ["00:00", "06:00", "12:00", "18:00"]

DEFAULT_CACHE_DIR = Path("data/cache")
DEFAULT_TRACK_DIR = Path("data/tracks")
DEFAULT_MANIFEST = Path("data/cs2_manifest.json")
DEFAULT_FIXTURES_DIR = Path("tests/fixtures/cs2")

REPO_ROOT = Path(__file__).resolve().parents[1]


app = typer.Typer(
    add_completion=False,
    help="Fetch CMEMS + ERA5 inputs for the CS2 Atlantic hurricane case study.",
)


# ---------------------------------------------------------------------------
# Shared helpers — kept local so the script stays self-contained.
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
    return sorted(p for p in cache_dir.iterdir() if p.is_file() and p.suffix in (".nc", ".csv"))


# ---------------------------------------------------------------------------
# Subcommand implementations (named _do_*) so `all` can call them in-process.
# ---------------------------------------------------------------------------


def _do_sst(*, cache_dir: Path, dataset_id: str, dry_run: bool) -> None:
    cache_dir = _resolve_repo_path(cache_dir) / "cmems"
    plan = FetchPlan(
        label="CMEMS Global L4 SST",
        plugin="cmems",
        target=cache_dir,
        notes={
            "dataset": dataset_id,
            "var": CMEMS_SST_VARIABLE,
            "bbox": CS2_BBOX,
            "time": f"{CS2_TIME_START.date()}…{CS2_TIME_STOP.date()}",
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
        bbox=CS2_BBOX, time_start=CS2_TIME_START, time_stop=CS2_TIME_STOP
    )
    ds = src.fetch(query)
    typer.secho(
        f"[ok] cmems_sst — cache_hit={ds.attrs.get('mosaic_cache_hit')} "
        f"shape={dict(ds.sizes)}",
        fg=typer.colors.GREEN,
    )


def _do_atmos(*, cache_dir: Path, dataset: str, dry_run: bool) -> None:
    cache_dir = _resolve_repo_path(cache_dir) / "era5"
    plan = FetchPlan(
        label="ERA5 atmospheric subset (u10, v10, msl, tp)",
        plugin="era5",
        target=cache_dir,
        notes={
            "dataset": dataset,
            "vars": ERA5_VARIABLES,
            "hours": ERA5_HOURS,
            "bbox": CS2_BBOX,
            "time": f"{CS2_TIME_START.date()}…{CS2_TIME_STOP.date()}",
        },
    )
    _print_plan(plan)
    if dry_run:
        typer.echo("(dry-run, no network calls)")
        return

    from mosaic.sources.base import SourceQuery
    from mosaic.sources.era5 import Era5Source

    src = Era5Source(
        source_id="era5_atmos",
        variables=ERA5_VARIABLES,
        dataset=dataset,
        hours=ERA5_HOURS,
        cache_dir=str(cache_dir),
    )
    query = SourceQuery(
        bbox=CS2_BBOX, time_start=CS2_TIME_START, time_stop=CS2_TIME_STOP
    )
    ds = src.fetch(query)
    typer.secho(
        f"[ok] era5_atmos — cache_hit={ds.attrs.get('mosaic_cache_hit')} "
        f"shape={dict(ds.sizes)}",
        fg=typer.colors.GREEN,
    )


def _do_track(*, track_dir: Path, dry_run: bool) -> None:
    """Copy the bundled IBTrACS-style storm-track CSV into ``track_dir``."""
    track_dir = _resolve_repo_path(track_dir)
    src_csv = REPO_ROOT / "tests" / "fixtures" / "cs2" / "ibtracs_ida_like.csv"
    dst_csv = track_dir / src_csv.name
    plan = FetchPlan(
        label="IBTrACS-style storm track (synthetic Ida-like)",
        plugin="local_csv",
        target=dst_csv,
        notes={"source": str(src_csv)},
    )
    _print_plan(plan)
    if dry_run:
        typer.echo("(dry-run, no network calls)")
        return

    if not src_csv.exists():
        # Lazily build the fixture if missing.
        sys.path.insert(0, str(REPO_ROOT))
        from tests.fixtures.build_cs2_fixtures import build_all  # type: ignore

        build_all(REPO_ROOT / "tests" / "fixtures" / "cs2")

    track_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_csv, dst_csv)
    typer.secho(f"[ok] track copied to {dst_csv}", fg=typer.colors.GREEN)


# ---------------------------------------------------------------------------
# Typer wrappers
# ---------------------------------------------------------------------------


@app.command(help="Download CMEMS Global L4 SST subset for the CS2 window.")
def sst(
    cache_dir: Path = typer.Option(DEFAULT_CACHE_DIR, "--cache-dir"),
    dataset_id: str = typer.Option(CMEMS_SST_DATASET_ID, "--dataset-id"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    _do_sst(cache_dir=cache_dir, dataset_id=dataset_id, dry_run=dry_run)


@app.command(help="Download ERA5 atmospheric subset (u10, v10, msl, tp) for the CS2 window.")
def atmos(
    cache_dir: Path = typer.Option(DEFAULT_CACHE_DIR, "--cache-dir"),
    dataset: str = typer.Option(ERA5_DATASET, "--dataset"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    _do_atmos(cache_dir=cache_dir, dataset=dataset, dry_run=dry_run)


@app.command(help="Copy the IBTrACS-style storm-track CSV into data/tracks/.")
def track(
    track_dir: Path = typer.Option(DEFAULT_TRACK_DIR, "--track-dir"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    _do_track(track_dir=track_dir, dry_run=dry_run)


@app.command(name="all", help="Run sst, atmos, track in sequence.")
def fetch_all(
    cache_dir: Path = typer.Option(DEFAULT_CACHE_DIR, "--cache-dir"),
    track_dir: Path = typer.Option(DEFAULT_TRACK_DIR, "--track-dir"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    _do_sst(cache_dir=cache_dir, dataset_id=CMEMS_SST_DATASET_ID, dry_run=dry_run)
    _do_atmos(cache_dir=cache_dir, dataset=ERA5_DATASET, dry_run=dry_run)
    _do_track(track_dir=track_dir, dry_run=dry_run)


# ---------------------------------------------------------------------------
# populate-fixtures (offline-friendly path)
# ---------------------------------------------------------------------------


@app.command(
    name="populate-fixtures",
    help="Seed cache locations from the synthetic test fixtures (no network).",
)
def populate_fixtures(
    cache_dir: Path = typer.Option(DEFAULT_CACHE_DIR, "--cache-dir"),
    track_dir: Path = typer.Option(DEFAULT_TRACK_DIR, "--track-dir"),
    fixtures_dir: Path = typer.Option(DEFAULT_FIXTURES_DIR, "--fixtures-dir"),
) -> None:
    cache_dir = _resolve_repo_path(cache_dir)
    track_dir = _resolve_repo_path(track_dir)
    fixtures_dir = _resolve_repo_path(fixtures_dir)

    if not fixtures_dir.exists():
        sys.path.insert(0, str(REPO_ROOT))
        from tests.fixtures.build_cs2_fixtures import build_all  # type: ignore

        build_all(fixtures_dir)

    src_to_dst = {
        fixtures_dir / "cmems_gulf_sst_2021-08.nc":
            cache_dir / "cmems" / "cmems_sst_offline.nc",
        fixtures_dir / "era5_gulf_atmos_2021-08.nc":
            cache_dir / "era5" / "era5_atmos_offline.nc",
        fixtures_dir / "ibtracs_ida_like.csv":
            track_dir / "ibtracs_ida_like.csv",
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
    track_dir: Path = typer.Option(DEFAULT_TRACK_DIR, "--track-dir"),
    out: Path = typer.Option(DEFAULT_MANIFEST, "--out"),
) -> None:
    cache_dir = _resolve_repo_path(cache_dir)
    track_dir = _resolve_repo_path(track_dir)
    out = _resolve_repo_path(out)
    files: list[Path] = []
    for sub in ("cmems", "era5"):
        files.extend(_existing_cache_files(cache_dir / sub))
    files.extend(_existing_cache_files(track_dir))

    if not files:
        typer.secho(
            "[warn] no files found — run `sst`, `atmos`, `track`, or "
            "`populate-fixtures` first.",
            fg=typer.colors.YELLOW,
        )

    payload = {
        "version": 1,
        "case_study": "CS2 — Atlantic hurricane (Ida-like), Aug-Sep 2021",
        "bbox": list(CS2_BBOX),
        "time_start": CS2_TIME_START.isoformat(),
        "time_stop": CS2_TIME_STOP.isoformat(),
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
