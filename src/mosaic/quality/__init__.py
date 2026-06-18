"""Declarative QC engine.

QC rules are deserialised either from the inline ``spec.qc.rules`` block of a
pipeline YAML or from a dedicated ruleset file. Output is a CF-compliant
ancillary mask plus a structured report stored in provenance.
"""

from __future__ import annotations

from mosaic.quality.engine import QCEngine, QCReport

__all__ = ["QCEngine", "QCReport"]
