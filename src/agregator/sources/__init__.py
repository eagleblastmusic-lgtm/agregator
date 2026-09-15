"""Job-source adapters."""

from __future__ import annotations

import os

from .adzuna import AdzunaApiSource
from .careerjet import CareerjetApiSource
from .epraca import EPracaSource
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


def _careerjet_from_env() -> CareerjetApiSource:
    api_key = os.getenv("CAREERJET_API_KEY", "")
    referer = os.getenv("CAREERJET_REFERER", "")
    user_ip = os.getenv("CAREERJET_USER_IP", "")
    user_agent = os.getenv("CAREERJET_USER_AGENT", "")
    missing = [
        name
        for name, value in {
            "CAREERJET_API_KEY": api_key,
            "CAREERJET_REFERER": referer,
            "CAREERJET_USER_IP": user_ip,
            "CAREERJET_USER_AGENT": user_agent,
        }.items()
        if not value
    ]
    if missing:
        raise ValueError(
            "Ustaw wymagane zmienne Careerjet: " + ", ".join(missing)
        )

    return CareerjetApiSource(
        api_key,
        referer=referer,
        user_ip=user_ip,
        user_agent=user_agent,
        locale_code=os.getenv("CAREERJET_LOCALE", "pl_PL"),
        keywords=os.getenv("CAREERJET_KEYWORDS") or None,
        location=os.getenv("CAREERJET_LOCATION") or None,
        page_size=int(os.getenv("CAREERJET_PAGE_SIZE", "20")),
        sort=os.getenv("CAREERJET_SORT", "date"),
    )


def _epraca_from_env() -> EPracaSource:
    partner = os.getenv("EPRACA_PARTNER", "")
    if not partner:
        raise ValueError("Ustaw EPRACA_PARTNER nadany przez MRPiPS")

    voivodeship = os.getenv("EPRACA_WOJEWODZTWO") or None
    unit = os.getenv("EPRACA_JEDNOSTKA") or None
    all_offers = os.getenv("EPRACA_ALL", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "tak",
    }

    return EPracaSource(
        partner,
        language=os.getenv("EPRACA_LANGUAGE", "pl"),
        voivodeship=voivodeship,
        unit=unit,
        all_offers=all_offers,
    )


def default_registry() -> SourceRegistry:
    registry = SourceRegistry()
    registry.register("olx", OlxPublicSource)
    registry.register("jooble", _jooble_from_env)
    registry.register("adzuna", _adzuna_from_env)
    registry.register("careerjet", _careerjet_from_env)
    registry.register("epraca", _epraca_from_env)
    return registry


__all__ = [
    "AdzunaApiSource",
    "CareerjetApiSource",
    "EPracaSource",
    "JoobleApiSource",
    "OlxPublicSource",
    "SourceRegistry",
    "default_registry",
]
