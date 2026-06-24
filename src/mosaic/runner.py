"""Pipeline execution.

This module wires together the source layer, harmonizer, QC engine, exporter
and provenance recorder. It is the single place where a :class:`PipelineSpec`
becomes a :class:`Result`.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import xarray as xr

from mosaic._spec import PipelineSpec, SourceSpec
from mosaic.derive import apply_derived
from mosaic.harmonize import Harmonizer
from mosaic.prov import build_stac_item, dataset_content_hash, pipeline_hash
from mosaic.quality import QCEngine
from mosaic.result import Result
from mosaic.sources.base import Source, SourceQuery
from mosaic.sources.base import registry as default_registry

# ---------------------------------------------------------------------------
# public entry points
# ---------------------------------------------------------------------------


def run(pipeline_path: str | Path) -> Result:
    """Execute a pipeline declared in a YAML file."""
    spec = PipelineSpec.from_yaml(pipeline_path)
    return execute(spec)


def execute(
    spec: PipelineSpec,
    *,
    prebuilt_sources: dict[str, Source] | None = None,
) -> Result:
    """Execute an already-validated pipeline."""
    sources = _build_sources(spec.spec.sources, prebuilt_sources or {})
    query = SourceQuery(
        bbox=tuple(spec.spec.domain.bbox),  # type: ignore[arg-type]
        time_start=_to_datetime(spec.spec.domain.time.start),
        time_stop=_to_datetime(spec.spec.domain.time.stop),
    )

    fetched: dict[str, xr.Dataset] = {sid: src.fetch(query) for sid, src in sources.items()}

    harmonizer = Harmonizer(
        cf_dictionary=spec.spec.harmonize.cf_dictionary,
        overrides=spec.spec.harmonize.overrides,
    )
    harmonized = harmonizer.harmonize(fetched)

    aligned_ds = _apply_time_alignment(
        harmonized.dataset,
        spec.spec.harmonize.time_alignment,
    )

    qc_engine = QCEngine(rules=spec.spec.qc.rules)
    qc_ds, qc_report = qc_engine.apply(aligned_ds)

    fused_ds, derive_report = apply_derived(
        qc_ds, list(spec.spec.fuse.derived), strict=True
    )

    output_path = _export(fused_ds, spec)

    p_hash = pipeline_hash(spec.canonical_yaml())
    c_hash = dataset_content_hash(fused_ds)

    inputs = [src.describe() | {"access_time": _now_iso()} for src in sources.values()]
    harmonization_summary = harmonized.summary()
    harmonization_summary["derived"] = derive_report.to_dict()
    item = build_stac_item(
        spec=spec,
        pipeline_hash=p_hash,
        content_hash=c_hash,
        inputs=inputs,
        harmonization_summary=harmonization_summary,
        qc_summary=qc_report.to_dict(),
        asset_href=output_path,
        asset_format=spec.spec.export.format,
    )

    if spec.spec.export.provenance:
        sidecar = Path(output_path).with_suffix(Path(output_path).suffix + ".stac.json")
        sidecar.parent.mkdir(parents=True, exist_ok=True)
        sidecar.write_text(json.dumps(item.to_dict(), indent=2), encoding="utf-8")

    return Result(
        dataset=fused_ds,
        provenance=item,
        qc_report=qc_report.to_dict(),
        harmonization_summary=harmonization_summary,
        output_path=str(output_path),
    )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _build_sources(
    specs: list[SourceSpec],
    prebuilt: dict[str, Source],
) -> dict[str, Source]:
    out: dict[str, Source] = {}
    for s in specs:
        if s.id in prebuilt:
            out[s.id] = prebuilt[s.id]
            continue
        cls = default_registry.get(s.plugin)
        out[s.id] = cls(source_id=s.id, **dict(s.params))
    return out


def _apply_time_alignment(ds: xr.Dataset, mode: str) -> xr.Dataset:
    """Apply the declared temporal alignment to time-indexed variables."""
    if mode == "instantaneous":
        return ds

    if "time" not in ds.coords:
        return ds

    if mode == "daily_mean":
        return ds.resample(time="1D").mean(keep_attrs=True)

    if mode == "hourly_mean":
        return ds.resample(time="1h").mean(keep_attrs=True)

    if mode == "nearest":
        return ds

    raise ValueError(f"unsupported time alignment mode: {mode}")


def _export(ds: xr.Dataset, spec: PipelineSpec) -> str:
    target = Path(spec.spec.export.path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if spec.spec.export.format == "zarr":
        # Remove a stale store if present so re-runs are deterministic.
        if target.exists():
            import shutil

            shutil.rmtree(target)
        ds.to_zarr(target, mode="w", consolidated=spec.spec.export.consolidated)
    elif spec.spec.export.format == "netcdf":
        ds.to_netcdf(target, engine="h5netcdf")
    else:  # pragma: no cover - guarded by pydantic Literal
        raise ValueError(f"unsupported export format: {spec.spec.export.format}")
    return str(target)


def _to_datetime(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return datetime.strptime(value, "%Y-%m-%d")


def _now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
