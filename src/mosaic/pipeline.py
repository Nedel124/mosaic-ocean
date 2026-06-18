"""Programmatic pipeline builder.

The :class:`Pipeline` produces a :class:`PipelineSpec` that can be either
serialised to YAML or executed directly. The class is deliberately thin: it
delegates execution to :func:`mosaic.runner.execute`. Tests cover both routes
(YAML-on-disk and programmatic).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from mosaic._spec import (
    DerivedVariable,
    Domain,
    ExportSpec,
    FuseSpec,
    HarmonizeSpec,
    InlineQCRule,
    Metadata,
    PipelineSpec,
    QCSpec,
    SourceSpec,
    Spec,
    TimeWindow,
)
from mosaic.result import Result
from mosaic.sources.base import Source


class Pipeline:
    """Fluent builder for a :class:`PipelineSpec`.

    Example
    -------
    >>> import mosaic as ms
    >>> pipe = (
    ...     ms.Pipeline(name="demo")
    ...     .domain(bbox=(14, 54, 22, 60),
    ...             time_start="2022-06-01", time_stop="2022-06-07")
    ...     .add_source(ms.sources.DummySource(variables=["sst", "u10"]))
    ...     .harmonize()
    ...     .export(path="out/demo.zarr")
    ... )
    """

    def __init__(self, name: str, description: str | None = None) -> None:
        self._metadata = Metadata(name=name, description=description)
        self._domain: Domain | None = None
        self._sources: list[SourceSpec] = []
        self._source_objects: list[Source] = []
        self._harmonize: HarmonizeSpec = HarmonizeSpec()
        self._qc: QCSpec = QCSpec()
        self._fuse: FuseSpec = FuseSpec()
        self._export: ExportSpec | None = None

    # ----------------------------------------------------------------- domain
    def domain(
        self,
        *,
        bbox: tuple[float, float, float, float],
        time_start: str,
        time_stop: str,
        resolution: str = "1D",
    ) -> Pipeline:
        self._domain = Domain(
            bbox=bbox,
            time=TimeWindow(start=time_start, stop=time_stop, resolution=resolution),
        )
        return self

    # ----------------------------------------------------------------- sources
    def add_source(self, src: Source) -> Pipeline:
        spec = SourceSpec(id=src.source_id, plugin=src.plugin_name, params=dict(src.params))
        self._sources.append(spec)
        self._source_objects.append(src)
        return self

    # --------------------------------------------------------------- harmonize
    def harmonize(
        self,
        *,
        cf_dictionary: str | None = None,
        time_alignment: str = "instantaneous",
        target_grid_from: str | None = None,
        overrides: dict[str, dict[str, Any]] | None = None,
    ) -> Pipeline:
        target = None
        if target_grid_from is not None:
            from mosaic._spec import TargetGrid

            target = TargetGrid.model_validate({"from": target_grid_from})
        self._harmonize = HarmonizeSpec(
            target_grid=target,
            time_alignment=time_alignment,  # type: ignore[arg-type]
            cf_dictionary=cf_dictionary,
            overrides=overrides or {},
        )
        return self

    # --------------------------------------------------------------------- qc
    def qc(self, *, rules: Mapping[str, Mapping[str, Any]] | None = None) -> Pipeline:
        if rules:
            self._qc = QCSpec(
                rules={var: InlineQCRule.model_validate(spec) for var, spec in rules.items()}
            )
        return self

    # ------------------------------------------------------------------- derive
    def derive(self, name: str, expression: str) -> Pipeline:
        """Add a derived variable evaluated against the harmonized dataset."""
        self._fuse = FuseSpec(
            derived=[*self._fuse.derived, DerivedVariable(name=name, expression=expression)]
        )
        return self

    # ------------------------------------------------------------------ export
    def export(self, *, path: str, format: str = "zarr", provenance: bool = True) -> Pipeline:
        self._export = ExportSpec(format=format, path=path, provenance=provenance)  # type: ignore[arg-type]
        return self

    # --------------------------------------------------------------- materialise
    def to_spec(self) -> PipelineSpec:
        if self._domain is None:
            # Pull a default 1-day window so DummySource demos work without ceremony.
            self._domain = Domain(
                bbox=(14.0, 54.0, 22.0, 60.0),
                time=TimeWindow(start="2022-06-01", stop="2022-06-02"),
            )
        if self._export is None:
            raise ValueError("Pipeline.export(...) is required before to_spec()/run()")
        if not self._sources:
            raise ValueError("Pipeline needs at least one source")
        spec = Spec(
            domain=self._domain,
            sources=self._sources,
            harmonize=self._harmonize,
            qc=self._qc,
            fuse=self._fuse,
            export=self._export,
        )
        return PipelineSpec(metadata=self._metadata, spec=spec)

    # -------------------------------------------------------------------- run
    def run(self) -> Result:
        from mosaic.runner import execute  # local import to break circular ref

        spec = self.to_spec()
        return execute(spec, prebuilt_sources={src.source_id: src for src in self._source_objects})
