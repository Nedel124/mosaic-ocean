"""Source plugin interface.

A :class:`Source` returns an :class:`xarray.Dataset` for a given query window.
Implementations are responsible for: fetching data, decoding it into xarray,
and reporting their identity / version (used in provenance).

The plugin layer is intentionally tiny: registration is just a string → class
mapping. Networked connectors live in optional extras and register themselves
on import.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, ClassVar

import xarray as xr


@dataclass(slots=True)
class SourceQuery:
    """Spatio-temporal slice requested from a source."""

    bbox: tuple[float, float, float, float]
    time_start: datetime
    time_stop: datetime
    variables: Sequence[str] | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class Source(ABC):
    """Abstract base class for all MOSAIC data source plugins."""

    #: short identifier matching the ``plugin`` field in the YAML spec
    plugin_name: ClassVar[str] = ""

    #: free-form version of the connector implementation, recorded in provenance
    plugin_version: ClassVar[str] = "0.1.0"

    def __init__(self, source_id: str, **params: Any) -> None:
        self.source_id = source_id
        self.params = params

    # ------------------------------------------------------------------ API
    @abstractmethod
    def fetch(self, query: SourceQuery) -> xr.Dataset:  # pragma: no cover - abstract
        """Return an :class:`xarray.Dataset` for the given query."""

    # --------------------------------------------------------------- provenance
    def describe(self) -> dict[str, Any]:
        """Identity payload included in STAC provenance."""
        return {
            "source_id": self.source_id,
            "plugin": self.plugin_name,
            "plugin_version": self.plugin_version,
            "params": dict(self.params),
        }


# ---------------------------------------------------------------------------
# tiny registry
# ---------------------------------------------------------------------------


class SourceRegistry:
    """In-memory mapping ``plugin_name -> Source subclass``."""

    def __init__(self) -> None:
        self._classes: dict[str, type[Source]] = {}

    def register(self, cls: type[Source]) -> type[Source]:
        if not cls.plugin_name:
            raise ValueError(f"{cls.__name__} must set plugin_name")
        if cls.plugin_name in self._classes:
            raise ValueError(f"plugin name '{cls.plugin_name}' is already registered")
        self._classes[cls.plugin_name] = cls
        return cls

    def get(self, name: str) -> type[Source]:
        try:
            return self._classes[name]
        except KeyError as exc:
            raise KeyError(
                f"unknown source plugin: '{name}'. Registered: {sorted(self._classes)}"
            ) from exc

    def names(self) -> list[str]:
        return sorted(self._classes)


registry = SourceRegistry()


def register(cls: type[Source]) -> type[Source]:
    """Decorator that registers a :class:`Source` implementation.

    Example::

        @register
        class MyConnector(Source):
            plugin_name = "my_connector"
            ...
    """
    return registry.register(cls)
