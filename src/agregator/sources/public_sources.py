from __future__ import annotations

import os

from .public_html import HtmlJobSourceConfig, PublicHtmlJobSource
from .sitemap_html import SitemapHtmlJobSource, SitemapJobSourceConfig


def _delay() -> float:
    return float(os.getenv("AGREGATOR_REQUEST_DELAY", "0.8"))


def _user_agent() -> str:
    return os.getenv("AGREGATOR_USER_AGENT", "FaroEmployerDiscovery/0.2")


def skillshot_source() -> PublicHtmlJobSource:
    return PublicHtmlJobSource(
        HtmlJobSourceConfig(
            name="skillshot",
            base_url="https://www.skillshot.pl",
            listing_url_template="https://www.skillshot.pl/jobs?page={page}",
            offer_path_patterns=(r"^/jobs/\d+-",),
            paginated=True,
            start_page=1,
            max_offer_links=40,
            company_selectors=("a[href*='/companies/']", "a[href*='/company/']"),
            description_selectors=("main", "article", ".job-description"),
        ),
        user_agent=_user_agent(),
        request_delay=_delay(),
    )


def nofluffjobs_source() -> PublicHtmlJobSource:
    return PublicHtmlJobSource(
        HtmlJobSourceConfig(
            name="nofluffjobs",
            base_url="https://nofluffjobs.com",
            listing_url_template="https://nofluffjobs.com/pl/poland",
            offer_path_patterns=(r"^/pl/job/",),
            paginated=False,
            max_offer_links=30,
            company_selectors=("a[href*='/company/']",),
            description_selectors=("main", "article"),
        ),
        user_agent=_user_agent(),
        request_delay=_delay(),
    )


def justjoinit_source() -> PublicHtmlJobSource:
    return PublicHtmlJobSource(
        HtmlJobSourceConfig(
            name="justjoinit",
            base_url="https://justjoin.it",
            listing_url_template="https://justjoin.it/job-offers/all-locations",
            offer_path_patterns=(r"^/job-offer/",),
            paginated=False,
            max_offer_links=50,
            company_selectors=("a[href*='/company/']", "a[href*='/companies/']"),
            description_selectors=("main", "article"),
        ),
        user_agent=_user_agent(),
        request_delay=_delay(),
    )


def rocketjobs_source() -> PublicHtmlJobSource:
    return PublicHtmlJobSource(
        HtmlJobSourceConfig(
            name="rocketjobs",
            base_url="https://rocketjobs.pl",
            listing_url_template="https://rocketjobs.pl/",
            offer_path_patterns=(r"^/job-offer/",),
            paginated=False,
            max_offer_links=50,
            company_selectors=("a[href*='/company/']", "a[href*='/companies/']"),
            description_selectors=("main", "article"),
        ),
        user_agent=_user_agent(),
        request_delay=_delay(),
    )


def theprotocol_source() -> PublicHtmlJobSource:
    return PublicHtmlJobSource(
        HtmlJobSourceConfig(
            name="theprotocol",
            base_url="https://theprotocol.it",
            listing_url_template="https://theprotocol.it/praca?pageNumber={page}",
            offer_path_patterns=(
                r"^/praca/.+,oferta,",
                r"^/szczegoly/praca/.+,oferta,",
            ),
            paginated=True,
            start_page=1,
            max_offer_links=50,
            company_selectors=(
                "a[href*='/firmy/']",
                "[data-testid*='company']",
                ".company-name",
            ),
            city_selectors=("[data-testid*='location']", ".location"),
            description_selectors=("main", "article"),
        ),
        user_agent=_user_agent(),
        request_delay=_delay(),
    )


def karierawfinansach_source() -> PublicHtmlJobSource:
    return PublicHtmlJobSource(
        HtmlJobSourceConfig(
            name="karierawfinansach",
            base_url="https://www.karierawfinansach.pl",
            listing_url_template="https://www.karierawfinansach.pl/praca",
            offer_path_patterns=(r"^/oferta-pracy/\d+",),
            paginated=False,
            max_offer_links=50,
            company_selectors=("a[href*='/pracodawca/']", ".company-name"),
            description_selectors=("main", "article", ".offer-content"),
        ),
        user_agent=_user_agent(),
        request_delay=_delay(),
    )


def pracuj_source() -> SitemapHtmlJobSource:
    detail = HtmlJobSourceConfig(
        name="pracuj",
        base_url="https://www.pracuj.pl",
        listing_url_template="https://www.pracuj.pl/praca",
        offer_path_patterns=(r"^/praca/.+,oferta,\d+$",),
        paginated=False,
        company_selectors=("a[href*='pracodawcy.pracuj.pl']",),
        description_selectors=("main", "article"),
    )
    return SitemapHtmlJobSource(
        SitemapJobSourceConfig(
            detail=detail,
            sitemap_url=(
                "https://www.pracuj.pl/SiteMaps/CurrentOffers/"
                "SiteMapIndexJobOffers.xml"
            ),
            chunk_size=25,
        ),
        user_agent=_user_agent(),
        request_delay=_delay(),
    )


__all__ = [
    "justjoinit_source",
    "karierawfinansach_source",
    "nofluffjobs_source",
    "pracuj_source",
    "rocketjobs_source",
    "skillshot_source",
    "theprotocol_source",
]
