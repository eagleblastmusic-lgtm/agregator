"""Job-source adapters."""

from __future__ import annotations

import os

from .jooble import JoobleApiSource
from .olx import OlxPublicSource
from .registry import SourceRegistry


def _jooble_from_env() -> JoobleApiSource:
    api_key = os.getenv("JOOBLE_API_KEY", "")
    if not api_key:
        raise ValueError("Ustaw JOOBLE_API_KEY przed użyciem źródła jooble")

    return JoobleApiSource(
        api_key,
        keywords=os.getenv("JOOBLE_KEYWORDS", "praca"),
        location=os.getenv("JOOBLE_LOCATION", "Polska"),
        result_on_page=int(os.getenv("JOOBLE_RESULTS_PER_PAGE", "20")),
        radius=os.getenv("JOOBLE_RADIUS") or None,
    )


def default_registry() -> SourceRegistry:
    registry = SourceRegistry()
    registry.register("olx", OlxPublicSource)
    registry.register("jooble", _jooble_from_env)
    return registry


__all__ = [
    "JoobleApiSource",
    "OlxPublicSource",
    "SourceRegistry",
    "default_registry",
]
