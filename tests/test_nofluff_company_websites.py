import json

import httpx
import pytest

from agregator.sources.public_html import HtmlJobSourceConfig
from agregator.sources.public_sources import (
    _NoFluffJobsSource,
    _repair_nofluff_company_website,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "https://static-dev.nofluffjobs.com/https://silvair.com/",
            "https://silvair.com/",
        ),
        (
            "https://static-dev.nofluffjobs.com/www.veritahr.com",
            "https://www.veritahr.com",
        ),
        (
            "https://static-dev.nofluffjobs.com/grp.hsbc/krakow",
            "https://grp.hsbc/krakow",
        ),
        (
            "https://www.capgemini.com/pl-pl/#jobs",
            "https://www.capgemini.com/pl-pl/",
        ),
    ],
)
def test_repair_nofluff_company_website(raw: str, expected: str) -> None:
    assert _repair_nofluff_company_website(raw) == expected


@pytest.mark.asyncio
async def test_nofluff_source_repairs_jsonld_sameas_before_storage() -> None:
    config = HtmlJobSourceConfig(
        name="nofluffjobs",
        base_url="https://nofluffjobs.com",
        listing_url_template="https://nofluffjobs.com/pl/poland",
        offer_path_patterns=(r"^/pl/job/",),
        paginated=False,
        max_offer_links=10,
    )
    payload = {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": "Developer",
        "identifier": {"value": "nfj-1"},
        "hiringOrganization": {
            "@type": "Organization",
            "name": "Silvair",
            "sameAs": "https://static-dev.nofluffjobs.com/https://silvair.com/",
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        if request.url.path == "/pl/poland":
            return httpx.Response(200, text='<a href="/pl/job/developer-1">Job</a>')
        if request.url.path == "/pl/job/developer-1":
            return httpx.Response(
                200,
                text=(
                    '<script type="application/ld+json">'
                    + json.dumps(payload)
                    + "</script>"
                ),
            )
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        source = _NoFluffJobsSource(config, client=client, request_delay=0)
        batch = await source.collect()

    assert len(batch.jobs) == 1
    candidates = batch.jobs[0].company_website_candidates
    assert len(candidates) == 1
    assert candidates[0].url == "https://silvair.com/"
    assert candidates[0].source == (
        "jsonld.hiringOrganization.sameAs.repaired_nofluff_static_wrapper"
    )
    assert candidates[0].confidence == 0.90
