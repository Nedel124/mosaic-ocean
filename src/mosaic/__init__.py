"""MOSAIC — Multi-source Ocean Sensor And model Integration Catalogue.

Public API surface:

    from mosaic import Pipeline, run, sources

The :class:`Pipeline` is the primary entry point for the programmatic builder.
The :func:`run` helper executes a pipeline declared in a YAML file.
"""

from __future__ import annotations

from importlib import metadata as _metadata

from mosaic import sources
from mosaic._spec import PipelineSpec
from mosaic.pipeline import Pipeline
from mosaic.result import Result
from mosaic.runner import run


class MosaicWarning(UserWarning):
    """Base class for warnings raised by MOSAIC itself.

    Tests promote these to errors via :file:`pyproject.toml` ``filterwarnings``,
    so any warning emitted from within :mod:`mosaic` must be expected and
    documented.
    """


try:
    __version__ = _metadata.version("mosaic-ocean")
except _metadata.PackageNotFoundError:  # editable install before metadata is built
    __version__ = "0.0.0+unknown"

__all__ = [
    "MosaicWarning",
    "Pipeline",
    "PipelineSpec",
    "Result",
    "__version__",
    "run",
    "sources",
]
