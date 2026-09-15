from agregator.sources.public_html import extract_offer_links, parse_job_detail_html
from agregator.sources.public_sources import theprotocol_source


def test_theprotocol_source_config_discovers_public_offer_links() -> None:
    source = theprotocol_source()
    html = """
    <html><body>
      <a href="/praca/backend-developer-warszawa%2Coferta%2Cabc-123?pageNumber=2">
        Backend Developer
      </a>
      <a href="/szczegoly/praca/devops-gdansk%2Coferta%2Cdef-456">DevOps</a>
      <a href="/firmy/acme">Firma</a>
      <a href="https://other.example/praca/x%2Coferta%2C999">External</a>
    </body></html>
    """

    links = extract_offer_links(
        "https://theprotocol.it/praca?pageNumber=1",
        html,
        source.config,
    )

    assert links == [
        "https://theprotocol.it/praca/backend-developer-warszawa%2Coferta%2Cabc-123?pageNumber=2",
        "https://theprotocol.it/szczegoly/praca/devops-gdansk%2Coferta%2Cdef-456",
    ]
    assert source.config.paginated is True
    assert source.config.listing_url_template.endswith("?pageNumber={page}")


def test_theprotocol_source_prefers_jsonld_jobposting() -> None:
    source = theprotocol_source()
    html = """
    <html><body>
      <script type="application/ld+json">
      {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "identifier": {"value": "tp-123"},
        "title": "Senior Python Developer",
        "datePosted": "2026-09-15",
        "description": "<p>Rozwój usług backendowych.</p>",
        "hiringOrganization": {
          "@type": "Organization",
          "name": "ACME Technologies Sp. z o.o.",
          "url": "https://acme.example"
        },
        "jobLocation": {
          "@type": "Place",
          "address": {
            "@type": "PostalAddress",
            "addressLocality": "Warszawa"
          }
        }
      }
      </script>
      <main>Pełna publiczna treść oferty</main>
    </body></html>
    """

    job = parse_job_detail_html(
        source.config,
        "https://theprotocol.it/praca/senior-python-warszawa%2Coferta%2Ctp-123",
        html,
    )

    assert job is not None
    assert job.source == "theprotocol"
    assert job.source_id == "tp-123"
    assert job.title == "Senior Python Developer"
    assert job.company_name == "ACME Technologies Sp. z o.o."
    assert job.city == "Warszawa"
    assert job.published_at == "2026-09-15"
    assert job.company_website_candidates[0].url == "https://acme.example"
    assert "json_ld_job_posting" in job.source_payload
