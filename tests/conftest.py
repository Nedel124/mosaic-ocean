"""Shared pytest fixtures for the MOSAIC test-suite.

The CS1 (Baltic upwelling) tests run against synthetic NetCDF fixtures that
emulate the layout of the real CMEMS / ERA5 / climatology subsets. We
materialise those fixtures on first run so the repo doesn't carry binary
artefacts.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

FIXTURES_ROOT = Path(__file__).parent / "fixtures"
REPO_ROOT = Path(__file__).resolve().parents[1]
CS1_DIR = REPO_ROOT / "tests" / "fixtures" / "cs1_gulf_of_riga"
CS2_DIR = FIXTURES_ROOT / "cs2"
CS3_DIR = FIXTURES_ROOT / "cs3"


@pytest.fixture(scope="session")
def cs1_fixtures() -> dict[str, Path]:
    """Ensure CS1 Gulf of Riga fixtures exist on disk; return their paths."""
    expected = {
        "cmems_sst": CS1_DIR / "cmems_gulf_of_riga_sst_2021-07.nc",
        "era5_wind": CS1_DIR / "era5_gulf_of_riga_wind_2021-07.nc",
    }

    if all(p.exists() for p in expected.values()):
        return expected

    builder = REPO_ROOT / "tests" / "fixtures" / "build_cs1_gulf_of_riga_fixtures.py"
    if builder.exists():
        spec = importlib.util.spec_from_file_location(
            "build_cs1_gulf_of_riga_fixtures",
            builder,
        )
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Could not load fixture builder: {builder}")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        built = module.build_all(CS1_DIR)
        return {k: Path(v) for k, v in built.items()}

    missing = [str(p) for p in expected.values() if not p.exists()]
    raise FileNotFoundError(
        "Missing CS1 Gulf of Riga fixture files and no builder was found. "
        "Expected files:\n- " + "\n- ".join(missing)
    )


@pytest.fixture(scope="session")
def cs2_fixtures() -> dict[str, Path]:
    """Ensure CS2 fixtures exist on disk; return their paths."""
    expected = {
        "cmems_sst": CS2_DIR / "cmems_gulf_sst_2021-08.nc",
        "era5_atmos": CS2_DIR / "era5_gulf_atmos_2021-08.nc",
        "ibtracs": CS2_DIR / "ibtracs_ida_like.csv",
    }
    if not all(p.exists() for p in expected.values()):
        from tests.fixtures.build_cs2_fixtures import build_all

        build_all(CS2_DIR)
    return expected


@pytest.fixture(scope="session")
def cs3_fixtures() -> dict[str, Path]:
    """Ensure CS3 fixtures exist on disk; return their paths."""
    expected = {
        "nsidc_sic": CS3_DIR / "nsidc_arctic_sic_2012-09.nc",
        "era5_surface": CS3_DIR / "era5_arctic_surface_2012-09.nc",
        "sic_clim": CS3_DIR / "arctic_sic_climatology_sep.nc",
    }
    if not all(p.exists() for p in expected.values()):
        from tests.fixtures.build_cs3_fixtures import build_all

        build_all(CS3_DIR)
    return expected
