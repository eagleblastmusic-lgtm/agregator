"""Job-source adapters."""

from __future__ import annotations

import os

from .adzuna import AdzunaApiSource
from .aplikuj import AplikujPublicSource
from .careerjet import CareerjetApiSource
from .epraca import EPracaSource
from .jooble import JoobleApiSource
from .kprm import KprmPublicSource
from .manpower import ManpowerPublicSource
from .ngo import NgoPublicSource
from .ofertypracy_edu import OfertyPracyEduPublicSource
from .olx import OlxPublicSource
from .public_sources import (
    bulldogjob_source,
    justjoinit_source,
    karierawfinansach_source,
    nofluffjobs_source,
    pracuj_source,
    rocketjobs_source,
    skillshot_source,
    theprotocol_source,
)
from .randstad import RandstadPublicSource
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
        "aplikuj",
        AplikujPublicSource,
        access_mode="public_html",
        experimental=True,
        notes=(
            "Public server-rendered /praca/strona-N listing and /oferta detail pages. "
            "Employer name, NIP when visible, and full source evidence are preserved."
        ),
    )
    registry.register(
        "theprotocol",
        theprotocol_source,
        access_mode="public_html",
        experimental=True,
        notes=(
            "Public theprotocol.it listing/detail pages only. Current adapter uses the visible "
            "HTML/JSON-LD path and does not call private APIs or bypass access controls."
        ),
    )
    registry.register(
        "bulldogjob",
        bulldogjob_source,
        access_mode="public_html",
        experimental=True,
        notes=(
            "Public Bulldogjob listing/detail pages only. The initial adapter collects the "
            "server-rendered batch; complete pagination/infinite-load coverage still needs "
            "real-source validation."
        ),
    )
    registry.register(
        "randstad",
        RandstadPublicSource,
        access_mode="public_html",
        experimental=True,
        notes=(
            "Public Randstad Poland listing/detail pages with /page-N pagination. Undisclosed "
            "client employers remain explicit low-confidence agency fallbacks rather than "
            "invented employer identities."
        ),
    )
    registry.register(
        "manpower",
        ManpowerPublicSource,
        access_mode="public_html",
        experimental=True,
        notes=(
            "Public Manpower Poland job search and /pl/job/<id>/<slug> details. Undisclosed "
            "client employers remain explicit low-confidence agency fallbacks rather than "
            "invented employer identities."
        ),
    )
    registry.register(
        "skillshot",
        skillshot_source,
        access_mode="public_html",
        experimental=True,
        notes="Public server-rendered listing/detail pages; robots is checked before requests.",
    )
    registry.register(
        "nofluffjobs",
        nofluffjobs_source,
        access_mode="public_html",
        experimental=True,
        notes="Public HTML only; hidden/API endpoints are not used and robots is respected.",
    )
    registry.register(
        "justjoinit",
        justjoinit_source,
        access_mode="public_html",
        experimental=True,
        notes="Public HTML only; no private API or access-control bypass.",
    )
    registry.register(
        "rocketjobs",
        rocketjobs_source,
        access_mode="public_html",
        experimental=True,
        notes="Public HTML only; pagination expansion and terms review remain pending.",
    )
    registry.register(
        "karierawfinansach",
        karierawfinansach_source,
        access_mode="public_html",
        experimental=True,
        notes="Public listing/detail pages only; conservative first rollout.",
    )
    registry.register(
        "kprm",
        KprmPublicSource,
        access_mode="official_public_html",
        experimental=True,
        notes=(
            "Official civil-service recruitment site; preserves public notice text and checks "
            "robots.txt before requests."
        ),
    )
    registry.register(
        "ofertypracyedu",
        OfertyPracyEduPublicSource,
        access_mode="official_public_html",
        experimental=True,
        notes=(
            "Official MEN/SIO public vacancy listing; recruitment contacts remain raw evidence "
            "and are not treated as GREEN outreach."
        ),
    )
    registry.register(
        "ngo",
        NgoPublicSource,
        access_mode="public_html",
        experimental=True,
        notes=(
            "Public NGO.pl job/cooperation listings and detail pages only. Recruitment contacts "
            "remain source evidence, not automatic GREEN cooperation channels."
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
    "AplikujPublicSource",
    "CareerjetApiSource",
    "EPracaSource",
    "JoobleApiSource",
    "KprmPublicSource",
    "ManpowerPublicSource",
    "NgoPublicSource",
    "OfertyPracyEduPublicSource",
    "OlxPublicSource",
    "RandstadPublicSource",
    "SourceRegistry",
    "default_registry",
]
