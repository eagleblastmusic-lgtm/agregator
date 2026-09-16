import json

from agregator.sources.public_html import HtmlJobSourceConfig, parse_job_detail_html


def test_jsonld_display_fields_decode_html_entities_without_mutating_raw_payload() -> None:
    config = HtmlJobSourceConfig(
        name="fixture",
        base_url="https://jobs.example",
        listing_url_template="https://jobs.example/jobs",
        offer_path_patterns=(r"^/job/",),
    )
    payload = {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": "Crew &amp; Shift Lead",
        "identifier": {"value": "job&amp;42"},
        "hiringOrganization": {
            "@type": "Organization",
            "name": "McDonald&apos;s Polska",
        },
        "jobLocation": {
            "@type": "Place",
            "address": {
                "@type": "PostalAddress",
                "addressLocality": "Łódź &amp; okolice",
            },
        },
    }
    html = (
        '<script type="application/ld+json">'
        + json.dumps(payload)
        + "</script>"
    )

    job = parse_job_detail_html(config, "https://jobs.example/job/42", html)

    assert job is not None
    assert job.title == "Crew & Shift Lead"
    assert job.company_name == "McDonald's Polska"
    assert job.city == "Łódź & okolice"
    assert job.source_id == "job&amp;42"
    raw = job.source_payload["json_ld_job_posting"]
    assert raw["title"] == "Crew &amp; Shift Lead"
    assert raw["hiringOrganization"]["name"] == "McDonald&apos;s Polska"
