"""Job-source adapters."""

from __future__ import annotations

import os

from .adzuna import AdzunaApiSource
from .careerjet import CareerjetApiSource
from .epraca import EPracaSource
from .jooble import JoobleApiSource
from .kprm import KprmPublicSource
from .olx import OlxPublicSource
from .public_sources import (
    justjoinit_source,
    karierawfinansach_source,
    nofluffjobs_source,
    pracuj_source,
    rocketjobs_source,
    skillshot_source,
)
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
        raise ValueError("Ustaw wymagane zmienne Careerjet: " + ", ".join(missing))

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
    registry.register(
        "olx",
        OlxPublicSource,
        access_mode="public_web_endpoint",
        experimental=True,
        notes=(
            "Uses a public read endpoint outside the documented partner API contract; "
            "revalidate source terms/access before production use."
        ),
    )
    registry.register(
        "pracuj",
        pracuj_source,
        access_mode="public_sitemap_html",
        experimental=True,
        notes=(
            "Current-offer sitemap is advertised in robots.txt; detail pages are fetched "
            "only when robots allows them. Terms review remains required before production."
        ),
    )
    registry.register(
        "skillshot",
        skillshot_source,
        access_mode="public_html",
        experimental=True,
        notes=(
            "Server-rendered public listing with numbered pagination; robots is checked "
            "before listing and detail requests."
        ),
    )
    registry.register(
        "nofluffjobs",
        nofluffjobs_source,
        access_mode="public_html",
        experimental=True,
        notes=(
            "Public HTML only. Hidden/API endpoints are not used; current adapter collects "
            "the server-rendered listing batch and respects robots.txt."
        ),
    )
    registry.register(
        "justjoinit",
        justjoinit_source,
        access_mode="public_html",
        experimental=True,
        notes=(
            "Public server-rendered listing/detail pages only; no private API or access-control "
            "bypass. Pagination expansion is pending source-specific validation."
        ),
    )
    registry.register(
        "rocketjobs",
        rocketjobs_source,
        access_mode="public_html",
        experimental=True,
        notes=(
            "Public server-rendered listing/detail pages only; pagination expansion and terms "
            "review are pending."
        ),
    )
    registry.register(
        "karierawfinansach",
        karierawfinansach_source,
        access_mode="public_html",
        experimental=True,
        notes=(
            "Public listing/detail pages only; current first batch is intentionally conservative "
            "until pagination and terms are fully audited."
        ),
    )
    registry.register(
        "kprm",
        KprmPublicSource,
        access_mode="official_public_html",
        experimental=True,
        notes=(
            "Official civil-service recruitment site. The footer advertises an XML export; "
            "this adapter currently preserves the human-visible public HTML notices and checks "
            "robots.txt before requests."
        ),
    )
    registry.register(
        "jooble",
        _jooble_from_env,
        access_mode="partner_api",
        required_env=("JOOBLE_API_KEY",),
        configuration_env=(
            "JOOBLE_KEYWORDS",
            "JOOBLE_LOCATION",
            "JOOBLE_RESULTS_PER_PAGE",
            "JOOBLE_RADIUS",
        ),
    )
    registry.register(
        "adzuna",
        _adzuna_from_env,
        access_mode="partner_api",
        required_env=("ADZUNA_APP_ID", "ADZUNA_APP_KEY"),
        configuration_env=(
            "ADZUNA_COUNTRY",
            "ADZUNA_WHAT",
            "ADZUNA_WHERE",
            "ADZUNA_RESULTS_PER_PAGE",
        ),
    )
    registry.register(
        "careerjet",
        _careerjet_from_env,
        access_mode="partner_api",
        required_env=(
            "CAREERJET_API_KEY",
            "CAREERJET_REFERER",
            "CAREERJET_USER_IP",
            "CAREERJET_USER_AGENT",
        ),
        configuration_env=(
            "CAREERJET_LOCALE",
            "CAREERJET_KEYWORDS",
            "CAREERJET_LOCATION",
            "CAREERJET_PAGE_SIZE",
            "CAREERJET_SORT",
        ),
    )
    registry.register(
        "epraca",
        _epraca_from_env,
        access_mode="official_partner_feed",
        required_env=("EPRACA_PARTNER",),
        configuration_env=(
            "EPRACA_LANGUAGE",
            "EPRACA_WOJEWODZTWO",
            "EPRACA_JEDNOSTKA",
            "EPRACA_ALL",
        ),
    )
    return registry


__all__ = [
    "AdzunaApiSource",
    "CareerjetApiSource",
    "EPracaSource",
    "JoobleApiSource",
    "KprmPublicSource",
    "OlxPublicSource",
    "SourceRegistry",
    "default_registry",
]
