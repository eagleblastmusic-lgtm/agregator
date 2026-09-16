from __future__ import annotations

import os
import re
from urllib.parse import unquote, urlparse

from ..models import CompanyWebsiteCandidate
from .base import SourceBatch
from .public_html import HtmlJobSourceConfig, PublicHtmlJobSource

_NOFLUFF_STATIC_HOSTS = {
    "static-dev.nofluffjobs.com",
    "www.static-dev.nofluffjobs.com",
}
_DOMAIN_PATH = re.compile(
    r"^(?:www\.)?[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,}(?:/.*)?$"
)


def _delay() -> float:
    return float(os.getenv("AGREGATOR_REQUEST_DELAY", "0.8"))


def _user_agent() -> str:
    return os.getenv("AGREGATOR_USER_AGENT", "FaroEmployerDiscovery/0.2")


def _repair_nofluff_company_website(value: str) -> str | None:
    """Repair malformed employer URLs currently emitted by NoFluffJobs JSON-LD.

    The source sometimes wraps a real employer URL below static-dev.nofluffjobs.com,
    e.g. ``.../https://silvair.com/`` or ``.../www.veritahr.com``. Only that known
    wrapper host is rewritten; normal first-party/external URLs are left untouched.
    """

    candidate = unquote(value.strip())
    parsed = urlparse(candidate)
    host = (parsed.hostname or "").lower()
    if host not in _NOFLUFF_STATIC_HOSTS:
        return parsed._replace(fragment="").geturl()

    wrapped = parsed.path.lstrip("/").strip()
    if wrapped.startswith(("http://", "https://")):
        repaired = wrapped
    elif _DOMAIN_PATH.fullmatch(wrapped):
        repaired = f"https://{wrapped}"
    else:
        return None

    repaired_parsed = urlparse(repaired)
    if not repaired_parsed.hostname:
        return None
    return repaired_parsed._replace(fragment="").geturl()


class _NoFluffJobsSource(PublicHtmlJobSource):
    async def collect(self, cursor: str | None = None) -> SourceBatch:
        batch = await super().collect(cursor)
        for job in batch.jobs:
            repaired: list[CompanyWebsiteCandidate] = []
            seen: set[str] = set()
            for website in job.company_website_candidates:
                url = _repair_nofluff_company_website(website.url)
                if url is None or url in seen:
                    continue
                seen.add(url)
                source = website.source
                if url != website.url:
                    source = f"{source}.repaired_nofluff_static_wrapper"
                repaired.append(
                    CompanyWebsiteCandidate(
                        url=url,
                        source=source,
                        confidence=website.confidence,
                    )
                )
            job.company_website_candidates = repaired
        return batch


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
            company_selectors=(
                "a[href*='/users/']",
                "a[href*='/companies/']",
                "a[href*='/company/']",
            ),
            description_selectors=("main", "article", ".job-description"),
        ),
        user_agent=_user_agent(),
        request_delay=_delay(),
    )


def nofluffjobs_source() -> PublicHtmlJobSource:
    return _NoFluffJobsSource(
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


def bulldogjob_source() -> PublicHtmlJobSource:
    return PublicHtmlJobSource(
        HtmlJobSourceConfig(
            name="bulldogjob",
            base_url="https://bulldogjob.pl",
            listing_url_template="https://bulldogjob.pl/companies/jobs",
            offer_path_patterns=(r"^/companies/jobs/\d+-",),
            paginated=False,
            max_offer_links=100,
            company_selectors=(
                "a[href*='/companies/profiles/']",
                "[class*='company-name']",
            ),
            city_selectors=("[class*='location']",),
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
            offer_path_patterns=(r"^/oferta-pracy/",),
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


def pracuj_source() -> PublicHtmlJobSource:
    """Collect Pracuj.pl from its public HTML listing instead of the blocked sitemap."""

    return PublicHtmlJobSource(
        HtmlJobSourceConfig(
            name="pracuj",
            base_url="https://www.pracuj.pl",
            listing_url_template="https://www.pracuj.pl/praca?pn={page}",
            offer_path_patterns=(r"^/praca/.+,oferta,\d+$",),
            paginated=True,
            start_page=1,
            max_offer_links=50,
            company_selectors=("a[href*='pracodawcy.pracuj.pl']",),
            description_selectors=("main", "article"),
        ),
        user_agent=_user_agent(),
        request_delay=_delay(),
    )


__all__ = [
    "bulldogjob_source",
    "justjoinit_source",
    "karierawfinansach_source",
    "nofluffjobs_source",
    "pracuj_source",
    "rocketjobs_source",
    "skillshot_source",
    "theprotocol_source",
]
