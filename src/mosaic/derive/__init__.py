"""Derived-variable layer for MOSAIC pipelines.

After harmonization and QC, a pipeline may declare a list of *derived*
variables under ``spec.fuse.derived``. Each derived variable is a small
expression evaluated against the harmonized dataset; the result is written
back into the dataset before export, and so participates in the
``content_hash`` of the run.

The evaluator is deliberately tiny: a hand-walked AST that whitelists
arithmetic, comparison, boolean, and a small set of NumPy math functions.
This keeps pipeline YAML files declarative and verifiable without exposing
``eval``.

Examples
--------

.. code-block:: yaml

    fuse:
      derived:
        - name: wind_speed
          expression: "sqrt(eastward_wind**2 + northward_wind**2)"
        - name: upwelling_mask
          expression: >-
            (sea_surface_temperature - sea_surface_temperature_climatology < -2.0)
            & (wind_speed > 4.0)
"""
from __future__ import annotations

from mosaic.derive.evaluator import (
    DerivationError,
    DerivationReport,
    apply_derived,
    evaluate_expression,
)

__all__ = [
    "DerivationError",
    "DerivationReport",
    "apply_derived",
    "evaluate_expression",
]
