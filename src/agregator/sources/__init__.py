"""Job-source adapters."""

from .olx import OlxPublicSource
from .registry import SourceRegistry


def default_registry() -> SourceRegistry:
    registry = SourceRegistry()
    registry.register("olx", OlxPublicSource)
    return registry


__all__ = ["OlxPublicSource", "SourceRegistry", "default_registry"]
