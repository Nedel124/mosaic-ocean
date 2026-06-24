"""Semantic harmonization layer.

This package implements the three-tier matching algorithm described in
``BRIEFING_aplikacja.md`` (Section 7):

1. CF-match against the CF Standard Name Table v85,
2. Dictionary-match against a domain dictionary YAML
   (``cf_baltic.yaml`` / ``cf_atlantic.yaml`` / ``cf_arctic.yaml``),
3. Heuristic fuzzy match with a confidence score.
"""
from __future__ import annotations

from mosaic.harmonize.harmonizer import HarmonizationResult, Harmonizer, MappingDecision

__all__ = ["HarmonizationResult", "Harmonizer", "MappingDecision"]
