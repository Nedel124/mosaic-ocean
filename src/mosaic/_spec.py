"""Pydantic models for the MOSAIC pipeline YAML format.

The schema version is ``mosaic/v1``. A pipeline file is the canonical, hashable
description of a reproducible run. The same file, fed to :class:`mosaic.runner`
under the same lock file, must produce identical outputs (modulo numerical
non-determinism that we explicitly bound).
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Shared scalars
# ---------------------------------------------------------------------------

API_VERSION: Literal["mosaic/v1"] = "mosaic/v1"

BBox = Annotated[
    tuple[float, float, float, float],
    Field(description="(west, south, east, north) in degrees, EPSG:4326."),
]


def _coerce_iso(value: str | date | datetime) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


# ---------------------------------------------------------------------------
# metadata block
# ---------------------------------------------------------------------------


class AuthorRef(BaseModel):
    name: str
    orcid: str | None = None
    email: str | None = None


class Metadata(BaseModel):
    name: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_\-]+$")
    description: str | None = None
    authors: list[AuthorRef] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# spec.domain
# ---------------------------------------------------------------------------


class TimeWindow(BaseModel):
    start: str
    stop: str
    resolution: str = "1D"

    @field_validator("start", "stop", mode="before")
    @classmethod
    def _normalize_iso(cls, v: Any) -> str:
        return _coerce_iso(v)


class Domain(BaseModel):
    bbox: BBox
    time: TimeWindow

    @field_validator("bbox")
    @classmethod
    def _validate_bbox(cls, v: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
        w, s, e, n = v
        if not (-180.0 <= w <= 180.0 and -180.0 <= e <= 180.0):
            raise ValueError("bbox longitudes must lie within [-180, 180]")
        if not (-90.0 <= s <= 90.0 and -90.0 <= n <= 90.0):
            raise ValueError("bbox latitudes must lie within [-90, 90]")
        if s >= n:
            raise ValueError("bbox south must be strictly less than north")
        # We intentionally allow w >= e (antimeridian crossing), but tag it.
        return v


# ---------------------------------------------------------------------------
# spec.sources
# ---------------------------------------------------------------------------


class SourceSpec(BaseModel):
    id: str = Field(min_length=1, pattern=r"^[a-zA-Z0-9_]+$")
    plugin: str = Field(min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# spec.harmonize
# ---------------------------------------------------------------------------


class TargetGrid(BaseModel):
    """Either pick another source's grid (``from: <id>``) or specify it inline."""

    model_config = ConfigDict(extra="forbid")

    from_source: str | None = Field(default=None, alias="from")
    resolution_deg: float | None = None
    crs: str = "EPSG:4326"

    @model_validator(mode="after")
    def _exclusive(self) -> TargetGrid:
        if self.from_source is None and self.resolution_deg is None:
            raise ValueError("target_grid must specify either 'from' or 'resolution_deg'")
        if self.from_source is not None and self.resolution_deg is not None:
            raise ValueError("target_grid cannot mix 'from' and 'resolution_deg'")
        return self


class HarmonizeSpec(BaseModel):
    target_grid: TargetGrid | None = None
    time_alignment: Literal["daily_mean", "hourly_mean", "instantaneous", "nearest"] = "instantaneous"
    cf_dictionary: str | None = None  # path to YAML extension dictionary
    overrides: dict[str, dict[str, Any]] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# spec.qc
# ---------------------------------------------------------------------------


class InlineQCRule(BaseModel):
    type: Literal["range", "spike", "stuck", "gradient", "gap"]
    # range
    min: float | None = None
    max: float | None = None
    # spike / stuck / gradient
    window: int | None = None
    threshold_sigma: float | None = None
    # generic
    flag: str | None = None


class QCSpec(BaseModel):
    rules_file: str | None = None
    rules: dict[str, InlineQCRule] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _at_least_one(self) -> QCSpec:
        if self.rules_file is None and not self.rules:
            # QC is optional; an empty QCSpec is fine.
            pass
        return self


# ---------------------------------------------------------------------------
# spec.fuse
# ---------------------------------------------------------------------------


class DerivedVariable(BaseModel):
    name: str = Field(pattern=r"^[a-zA-Z_][a-zA-Z0-9_]*$")
    expression: str | None = None
    type: Literal["expression", "temporal_lag", "spatial_aggregate"] | None = None
    source: str | None = None
    shifts_days: list[int] = Field(default_factory=list)


class FuseSpec(BaseModel):
    derived: list[DerivedVariable] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# spec.export
# ---------------------------------------------------------------------------


class ExportSpec(BaseModel):
    format: Literal["zarr", "netcdf"] = "zarr"
    path: str
    provenance: bool = True
    consolidated: bool = True


# ---------------------------------------------------------------------------
# spec.reproducibility
# ---------------------------------------------------------------------------


class ReproducibilitySpec(BaseModel):
    seed: int = 0
    strict_versions: bool = True


# ---------------------------------------------------------------------------
# top-level Spec
# ---------------------------------------------------------------------------


class Spec(BaseModel):
    domain: Domain
    sources: list[SourceSpec] = Field(min_length=1)
    harmonize: HarmonizeSpec = Field(default_factory=HarmonizeSpec)
    qc: QCSpec = Field(default_factory=QCSpec)
    fuse: FuseSpec = Field(default_factory=FuseSpec)
    export: ExportSpec
    reproducibility: ReproducibilitySpec = Field(default_factory=ReproducibilitySpec)

    @field_validator("sources")
    @classmethod
    def _unique_source_ids(cls, v: list[SourceSpec]) -> list[SourceSpec]:
        ids = [s.id for s in v]
        if len(ids) != len(set(ids)):
            raise ValueError("source ids must be unique within a pipeline")
        return v


class PipelineSpec(BaseModel):
    """Top-level pipeline document."""

    apiVersion: Literal["mosaic/v1"] = API_VERSION
    kind: Literal["Pipeline"] = "Pipeline"
    metadata: Metadata
    spec: Spec

    # ---------------------------------------------------------------- helpers
    @classmethod
    def from_yaml(cls, path: str | Path) -> PipelineSpec:
        """Parse and validate a pipeline YAML file."""
        import yaml  # local import keeps optional deps light at module-import time

        text = Path(path).read_text(encoding="utf-8")
        data = yaml.safe_load(text)
        if data is None:
            raise ValueError(f"empty pipeline file: {path}")
        return cls.model_validate(data)

    def canonical_yaml(self) -> str:
        """Deterministic YAML serialization used as input to the pipeline hash."""
        import yaml

        # We dump from ``model_dump(mode='json')`` so dates / paths are normalized,
        # then sort keys to remove ordering ambiguity from the hash.
        return yaml.safe_dump(
            self.model_dump(mode="json", by_alias=True),
            sort_keys=True,
            default_flow_style=False,
            allow_unicode=False,
        )
