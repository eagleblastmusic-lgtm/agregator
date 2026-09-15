from agregator.crawler import WebsiteCrawler


def test_sitemap_parser_handles_namespaced_urlset() -> None:
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://example.pl/</loc></url>
      <url><loc>https://example.pl/kontakt</loc></url>
      <url><loc>https://example.pl/wspolpraca</loc></url>
    </urlset>
    """

    locations = WebsiteCrawler._parse_sitemap_locations(xml)

    assert locations == [
        "https://example.pl/",
        "https://example.pl/kontakt",
        "https://example.pl/wspolpraca",
    ]


def test_sitemap_parser_handles_index_and_invalid_xml() -> None:
    index = """
    <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <sitemap><loc>https://example.pl/sitemap-pages.xml</loc></sitemap>
      <sitemap><loc>https://example.pl/sitemap-posts.xml</loc></sitemap>
    </sitemapindex>
    """

    assert WebsiteCrawler._parse_sitemap_locations(index) == [
        "https://example.pl/sitemap-pages.xml",
        "https://example.pl/sitemap-posts.xml",
    ]
    assert WebsiteCrawler._parse_sitemap_locations("<broken") == []


def test_priority_prefers_business_contact_paths() -> None:
    assert WebsiteCrawler._priority("https://example.pl/wspolpraca") == 0
    assert WebsiteCrawler._priority("https://example.pl/dla-firm") == 0
    assert WebsiteCrawler._priority("https://example.pl/blog/aktualnosci") == 10
