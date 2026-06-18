"""Tests for ``scripts/fetch_cs1_gulf_of_riga.py``.

The tests run entirely offline:

* ``--dry-run`` exercises every subcommand without hitting the network.
* ``populate-fixtures`` is checked end-to-end — it should copy the synthetic
  fixtures into the cache layout the live pipeline expects.
* ``manifest`` / ``verify`` are exercised as a round-trip.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import fetch_cs1_gulf_of_riga as fetch_cs1  # noqa: E402

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def repo_in_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Pretend the repo lives at ``tmp_path`` for the duration of the test.

    We patch the module-level ``REPO_ROOT`` (used by ``_resolve_repo_path``)
    so cache and manifest writes land inside ``tmp_path`` instead of the
    actual checkout.
    """
    monkeypatch.setattr(fetch_cs1, "REPO_ROOT", tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# Dry-run smoke tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("subcmd", ["sst", "wind"])
def test_subcommand_dry_run(repo_in_tmp: Path, subcmd: str) -> None:
    result = runner.invoke(fetch_cs1.app, [subcmd, "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "(dry-run, no network calls)" in result.output


def test_all_dry_run(repo_in_tmp: Path) -> None:
    result = runner.invoke(fetch_cs1.app, ["all", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert result.output.count("(dry-run, no network calls)") == 2


# ---------------------------------------------------------------------------
# populate-fixtures + manifest + verify round trip
# ---------------------------------------------------------------------------


def test_populate_fixtures_then_manifest_and_verify(repo_in_tmp: Path) -> None:
    fixtures_dir = repo_in_tmp / "tests" / "fixtures" / "cs1_gulf_of_riga"
    cache_dir = repo_in_tmp / "data" / "cache"

    result = runner.invoke(
        fetch_cs1.app,
        [
            "populate-fixtures",
            "--cache-dir",
            str(cache_dir),
            "--fixtures-dir",
            str(fixtures_dir),
        ],
    )
    assert result.exit_code == 0, result.output
    assert (cache_dir / "cmems" / "cs1_gulf_of_riga" / "cmems_gulf_of_riga_sst_2021-07.nc").exists()
    assert (cache_dir / "era5" / "cs1_gulf_of_riga" / "era5_gulf_of_riga_wind_2021-07.nc").exists()

    # manifest should now find two NetCDF files.
    manifest_path = repo_in_tmp / "data" / "cs1_gulf_of_riga_manifest.json"
    result = runner.invoke(
        fetch_cs1.app,
        [
            "manifest",
            "--cache-dir",
            str(cache_dir),
            "--out",
            str(manifest_path),
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(manifest_path.read_text())
    assert payload["version"] == 1
    assert len(payload["files"]) == 2
    for entry in payload["files"]:
        assert len(entry["sha256"]) == 64
        assert entry["size_bytes"] > 0

    # verify must succeed against a freshly-generated manifest.
    result = runner.invoke(fetch_cs1.app, ["verify", "--manifest", str(manifest_path)])
    assert result.exit_code == 0, result.output
    assert "all 2 files verified" in result.output


def test_verify_detects_tampering(repo_in_tmp: Path) -> None:
    fixtures_dir = repo_in_tmp / "tests" / "fixtures" / "cs1_gulf_of_riga"
    cache_dir = repo_in_tmp / "data" / "cache"
    manifest_path = repo_in_tmp / "data" / "cs1_gulf_of_riga_manifest.json"

    runner.invoke(
        fetch_cs1.app,
        [
            "populate-fixtures",
            "--cache-dir",
            str(cache_dir),
            "--fixtures-dir",
            str(fixtures_dir),
        ],
    )
    runner.invoke(
        fetch_cs1.app,
        [
            "manifest",
            "--cache-dir",
            str(cache_dir),
            "--out",
            str(manifest_path),
        ],
    )

    # Tamper with one of the cache files — verify must catch it.
    target = cache_dir / "cmems" / "cs1_gulf_of_riga" / "cmems_gulf_of_riga_sst_2021-07.nc"
    target.write_bytes(b"corruption")

    result = runner.invoke(fetch_cs1.app, ["verify", "--manifest", str(manifest_path)])
    assert result.exit_code == 1, result.output
    assert "failed verification" in result.output
