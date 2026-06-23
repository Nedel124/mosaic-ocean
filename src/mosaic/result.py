"""Container for the result of a pipeline run."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import xarray as xr
from pystac import Item


@dataclass
class Result:
    """Container returned by :meth:`mosaic.Pipeline.run` and :func:`mosaic.run`."""

    dataset: xr.Dataset
    provenance: Item
    qc_report: dict[str, Any]
    harmonization_summary: dict[str, Any]
    output_path: str

    def to_summary(self) -> dict[str, Any]:
        """A compact dict of the most important diagnostics."""
        return {
            "output_path": self.output_path,
            "stac_id": self.provenance.id,
            "pipeline_hash": self.provenance.properties.get("mosaic:pipeline_hash"),
            "content_hash": self.provenance.properties.get("mosaic:content_hash"),
            "mapping_accuracy": self.harmonization_summary.get("mapping_accuracy"),
            "flagged_fraction": self.qc_report.get("flagged_fraction"),
        }
