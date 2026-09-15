from agregator.crawler import CrawlPage
from agregator.website_verification import verify_company_website


def _page(url: str, html: str) -> CrawlPage:
    return CrawlPage(url=url, html=html, status_code=200)


def test_verification_accepts_company_identity_confirmed_by_site() -> None:
    result = verify_company_website(
        "ACME Logistics Sp. z o.o.",
        "Gdańsk",
        "https://acme-logistics.example",
        [
            _page(
                "https://acme-logistics.example",
                """
                <html><head><title>ACME Logistics</title></head>
                <body>
                  <h1>ACME Logistics Sp. z o.o.</h1>
                  <p>Transport i logistyka. Siedziba: Gdańsk.</p>
                </body></html>
                """,
            )
        ],
        search_score=0.82,
    )

    assert result.accepted is True
    assert result.score >= 0.55
    assert result.name_coverage == 1.0
    assert "exact_normalized_company_name" in result.signals
    assert "city_on_website" in result.signals


def test_verification_rejects_unrelated_search_result() -> None:
    result = verify_company_website(
        "ACME Logistics",
        "Gdańsk",
        "https://directory-example.test",
        [
            _page(
                "https://directory-example.test",
                """
                <html><body>
                  <h1>Katalog lokalnych usług</h1>
                  <p>Restauracje, fryzjerzy i wydarzenia w Warszawie.</p>
                </body></html>
                """,
            )
        ],
        search_score=0.78,
    )

    assert result.accepted is False
    assert result.name_coverage == 0.0
    assert "identity_not_confirmed" in result.signals


def test_verification_rejects_domain_when_crawler_has_no_pages() -> None:
    result = verify_company_website(
        "ACME Logistics",
        None,
        "https://acme.example",
        [],
        search_score=0.9,
    )

    assert result.accepted is False
    assert result.content_score == 0.0
    assert result.signals == ("no_crawlable_pages",)


def test_jsonld_organization_can_confirm_identity_when_visible_copy_is_sparse() -> None:
    result = verify_company_website(
        "Baltic Robotics Sp. z o.o.",
        "Gdynia",
        "https://balticrobotics.example",
        [
            _page(
                "https://balticrobotics.example",
                """
                <html>
                  <head>
                    <script type="application/ld+json">
                    {
                      "@context": "https://schema.org",
                      "@type": "Organization",
                      "legalName": "Baltic Robotics Sp. z o.o.",
                      "url": "https://balticrobotics.example",
                      "taxID": "PL1234567890",
                      "address": {
                        "@type": "PostalAddress",
                        "addressLocality": "Gdynia"
                      }
                    }
                    </script>
                  </head>
                  <body><h1>Rozwiązania automatyki przemysłowej</h1></body>
                </html>
                """,
            )
        ],
        search_score=0.88,
    )

    assert result.accepted is True
    assert "jsonld_organization_name" in result.signals
    assert "jsonld_organization_url" in result.signals
    assert "jsonld_address_city" in result.signals
    assert "jsonld_tax_id_present" in result.signals
