import httpx
import pytest

from agregator.models import CompanyWebsiteCandidate
from agregator.sources.rocketjobs import (
    RocketJobsPublicSource,
    extract_employer_profile_url,
    extract_employer_website,
)


def test_profile_url_prefers_dedicated_company_profile_cta() -> None:
    html = """
    <html><body>
      <section>
        <a href="/brands/story/lvl-up-media"></a>
        <a href="/brands/story/lvl-up-media">LVL UP COMMERCE</a>
        <a href="/brands/story/lvl-up-media">Zobacz profil firmy</a>
      </section>
      <footer>
        <a href="/brands/story/rocket-jobs">O nas</a>
        <a href="/brands/story/rocket-jobs">Kariera</a>
      </footer>
    </body></html>
    """

    assert extract_employer_profile_url(
        html,
        "https://rocketjobs.pl/oferta-pracy/lvl-up-test",
        "LVL UP COMMERCE",
    ) == "https://rocketjobs.pl/brands/story/lvl-up-media"


def test_footer_brand_profile_is_not_fallback_for_unrelated_company() -> None:
    html = """
    <html><body>
      <h1>Sales Representative</h1>
      <footer>
        <a href="/brands/story/rocket-jobs">O nas</a>
        <a href="/brands/story/rocket-jobs">Kariera</a>
      </footer>
    </body></html>
    """

    assert extract_employer_profile_url(
        html,
        "https://rocketjobs.pl/oferta-pracy/singu-sales-representative",
        "Singu",
    ) is None


def test_exact_company_name_link_can_identify_profile_without_cta() -> None:
    html = '<a href="/brands/story/acme">ACME Sp. z o.o.</a>'

    assert extract_employer_profile_url(
        html,
        "https://rocketjobs.pl/oferta-pracy/acme-test",
        "ACME Sp. z o.o.",
    ) == "https://rocketjobs.pl/brands/story/acme"


def test_profile_website_uses_serialized_website_type_not_first_external() -> None:
    html = r'''
    <html><body>
      <a href="https://www.facebook.com/LVLUPMEDIA"></a>
      <a href="https://levelupmedia.pl/"></a>
      <a href="https://www.linkedin.com/company/lvl-up-media/"></a>
      <script>
        self.__next_f.push([1,"{\"socialMedia\":[{\"link\":\"https://levelupmedia.pl/\",\"type\":\"Website\"},{\"link\":\"https://www.facebook.com/LVLUPMEDIA\",\"type\":\"Facebook\"},{\"link\":\"https://www.linkedin.com/company/lvl-up-media/\",\"type\":\"LinkedIn\"}]} "])
      </script>
    </body></html>
    '''

    candidate = extract_employer_website(
        html,
        "https://rocketjobs.pl/brands/story/lvl-up-media",
    )

    assert candidate is not None
    assert candidate.url == "https://levelupmedia.pl/"
    assert candidate.source == "rocketjobs.employer_profile.social_media.website"
    assert candidate.confidence == 0.98


def test_profile_website_must_also_be_rendered_as_external_anchor() -> None:
    html = r'''
    <html><body>
      <a href="https://www.facebook.com/example"></a>
      <script>
        self.__next_f.push([1,"{\"socialMedia\":[{\"link\":\"https://hidden.example/\",\"type\":\"Website\"}]} "])
      </script>
    </body></html>
    '''

    assert extract_employer_website(
        html,
        "https://rocketjobs.pl/brands/story/example",
    ) is None


def test_profile_website_rejects_rocketjobs_as_source_portal() -> None:
    html = r'''
    <html><body>
      <a href="https://rocketjobs.pl/"></a>
      <script>
        self.__next_f.push([1,"{\"socialMedia\":[{\"link\":\"https://rocketjobs.pl/\",\"type\":\"Website\"}]} "])
      </script>
    </body></html>
    '''

    assert extract_employer_website(
        html,
        "https://rocketjobs.pl/brands/story/rocket-jobs",
    ) is None


@pytest.mark.asyncio
async def test_collect_caches_profile_and_filters_portal_jsonld_candidate() -> None:
    listing = """
    <a href="/oferta-pracy/lvl-up-one">One</a>
    <a href="/oferta-pracy/lvl-up-two">Two</a>
    """
    detail_template = """
    <html><body>
      <script type="application/ld+json">
      {{
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": "{title}",
        "description": "Opis",
        "hiringOrganization": {{
          "@type": "Organization",
          "name": "LVL UP COMMERCE",
          "url": "https://rocketjobs.pl/brands/story/lvl-up-media"
        }}
      }}
      </script>
      <a href="/brands/story/lvl-up-media">LVL UP COMMERCE</a>
      <a href="/brands/story/lvl-up-media">Zobacz profil firmy</a>
      <footer><a href="/brands/story/rocket-jobs">O nas</a></footer>
    </body></html>
    """
    profile = r'''
    <html><body>
      <a href="https://levelupmedia.pl/"></a>
      <a href="https://www.facebook.com/LVLUPMEDIA"></a>
      <script>
        self.__next_f.push([1,"{\"socialMedia\":[{\"link\":\"https://levelupmedia.pl/\",\"type\":\"Website\"},{\"link\":\"https://www.facebook.com/LVLUPMEDIA\",\"type\":\"Facebook\"}]} "])
      </script>
    </body></html>
    '''
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        if request.url.path == "/":
            return httpx.Response(200, text=listing)
        if request.url.path == "/oferta-pracy/lvl-up-one":
            return httpx.Response(200, text=detail_template.format(title="Planner"))
        if request.url.path == "/oferta-pracy/lvl-up-two":
            return httpx.Response(200, text=detail_template.format(title="Specialist"))
        if request.url.path == "/brands/story/lvl-up-media":
            return httpx.Response(200, text=profile)
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        source = RocketJobsPublicSource(client=client, request_delay=0)
        batch = await source.collect()

    assert len(batch.jobs) == 2
    assert requests.count("/brands/story/lvl-up-media") == 1
    for job in batch.jobs:
        assert job.source_payload["employer_profile_url"] == (
            "https://rocketjobs.pl/brands/story/lvl-up-media"
        )
        assert any(
            item.kind == "rocketjobs_employer_profile"
            and item.value == "https://rocketjobs.pl/brands/story/lvl-up-media"
            and item.confidence == 0.99
            for item in job.company_identifiers
        )
        assert [item.url for item in job.company_website_candidates] == [
            "https://levelupmedia.pl/"
        ]


@pytest.mark.asyncio
async def test_external_jsonld_website_keeps_precedence_and_skips_profile_fetch() -> None:
    listing = '<a href="/oferta-pracy/acme-test">Oferta</a>'
    detail = """
    <html><body>
      <script type="application/ld+json">
      {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": "Developer",
        "description": "Opis",
        "hiringOrganization": {
          "@type": "Organization",
          "name": "ACME",
          "url": "https://acme.example/"
        }
      }
      </script>
      <a href="/brands/story/acme">ACME</a>
      <a href="/brands/story/acme">Zobacz profil firmy</a>
    </body></html>
    """
    profile_requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal profile_requests
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        if request.url.path == "/":
            return httpx.Response(200, text=listing)
        if request.url.path == "/oferta-pracy/acme-test":
            return httpx.Response(200, text=detail)
        if request.url.path == "/brands/story/acme":
            profile_requests += 1
            return httpx.Response(200, text="")
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        source = RocketJobsPublicSource(client=client, request_delay=0)
        batch = await source.collect()

    assert len(batch.jobs) == 1
    job = batch.jobs[0]
    assert job.company_website_candidates == [
        CompanyWebsiteCandidate(
            url="https://acme.example/",
            source="jsonld.hiringOrganization.url",
            confidence=0.90,
        )
    ]
    assert any(item.kind == "rocketjobs_employer_profile" for item in job.company_identifiers)
    assert profile_requests == 0
