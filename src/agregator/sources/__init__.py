"""Job-source adapters."""

from __future__ import annotations

import os

from .adzuna import AdzunaApiSource
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


def _adzuna_from_env() -> AdzunaApiSource:
    app_id = os.getenv("ADZUNA_APP_ID", "")
    app_key = os.getenv("ADZUNA_APP_KEY", "")
    if not app_id or not app_key:
        raise ValueError("Ustaw ADZUNA_APP_ID i ADZUNA_APP_KEY przed użyciem źródła adzuna")

    return AdzunaApiSource(
        app_id,
        app_key,
        country=os.getenv("ADZUNA_COUNTRY", "pl"),
        what=os.getenv("ADZUNA_WHAT") or None,
        where=os.getenv("ADZUNA_WHERE") or None,
        results_per_page=int(os.getenv("ADZUNA_RESULTS_PER_PAGE", "20")),
    )


def default_registry() -> SourceRegistry:
    registry = SourceRegistry()
    registry.register("olx", OlxPublicSource)
    registry.register("jooble", _jooble_from_env)
    registry.register("adzuna", _adzuna_from_env)
    return registry


__all__ = [
    "AdzunaApiSource",
    "JoobleApiSource",
    "OlxPublicSource",
    "SourceRegistry",
    "default_registry",
]
