import json
from pathlib import Path

from agregator.audit import record_discovery_audit
from agregator.company_websites import persist_job_company_website_candidates
from agregator.models import (
    ChannelKind,
    ChannelPurpose,
    CompanyIdentity,
    CompanyWebsiteCandidate,
    ContactChannel,
    Decision,
    DiscoveryResult,
    Evidence,
    JobPosting,
    WebsiteResolutionOrigin,
)
from agregator.reporting import build_benchmark_report, export_green_channels
from agregator.storage import SQLiteStore


def _seed(store: SQLiteStore) -> int:
    store.init_schema()
    store.upsert_jobs(
        [
            JobPosting(
                source="source-a",
                source_id="1",
                url="https://jobs.test/1",
                title="Kasjer",
                company_name="Firma Testowa",
                company_name_source="api.company",
                company_name_confidence=0.95,
                city="Gdynia",
            ),
            JobPosting(
                source="source-b",
                source_id="2",
                url="https://jobs.test/2",
                title="Sprzedawca",
                company_name="Firma Testowa",
                company_name_source="api.company",
                company_name_confidence=0.95,
                city="Gdynia",
            ),
        ]
    )
    company_id = int(store.list_companies()[0]["id"])
    store.save_discovery_result(
        company_id,
        DiscoveryResult(
            company=CompanyIdentity(
                name="Firma Testowa",
                city="Gdynia",
                website_url="https://firma.test",
                domain="firma.test",
                website_confidence=0.98,
            ),
            channels=[
                ContactChannel(
                    kind=ChannelKind.EMAIL,
                    value="partnerzy@firma.test",
                    purpose=ChannelPurpose.BUSINESS_PARTNERSHIP,
                    decision=Decision.GREEN,
                    confidence=0.99,
                    evidence=Evidence(
                        url="https://firma.test/partnerzy",
                        text="Kontakt dla partnerów: partnerzy@firma.test",
                        signal="partnerzy",
                    ),
                )
            ],
        ),
    )
    return company_id


def test_benchmark_report_counts_pipeline_outputs(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "report.sqlite3")
    _seed(store)

    report = build_benchmark_report(store)

    assert report.jobs_total == 2
    assert report.companies_total == 1
    assert report.sources_total == 2
    assert report.high_confidence_companies == 1
    assert report.enriched_companies == 1
    assert report.websites_found == 1
    assert report.company_identifiers_total == 0
    assert report.companies_with_identifiers == 0
    assert report.identifier_conflicts == 0
    assert report.identifier_company_rate == 0.0
    assert report.website_candidates_total == 0
    assert report.companies_with_website_candidates == 0
    assert report.source_verified_websites == 0
    assert report.source_website_candidate_company_rate == 0.0
    assert report.source_verified_website_rate == 0.0
    assert report.source_verified_share_of_found == 0.0
    assert report.website_resolution_origin_counts == {}
    assert report.source_verified_website_counts == {}
    assert report.green_channels == 1
    assert report.company_to_job_ratio == 0.5
    assert report.website_find_rate == 1.0
    assert report.green_company_rate == 1.0
    assert report.employer_score_average == 75.0
    assert report.employer_score_ge_60 == 1
    assert report.employer_score_distribution == {
        "0-24": 0,
        "25-49": 0,
        "50-74": 0,
        "75-100": 1,
    }
    assert report.source_job_counts == {"source-a": 1, "source-b": 1}
    assert report.company_resolution_counts == {
        "exact_name_city": 1,
        "new_company": 1,
    }


def test_benchmark_report_measures_source_website_shortcut(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "source-websites.sqlite3")
    store.init_schema()
    job = JobPosting(
        source="epraca",
        source_id="1",
        url="https://jobs.test/1",
        title="Magazynier",
        company_name="ACME Logistics",
        company_name_source="official_feed.pracodawca",
        company_name_confidence=0.995,
        company_website_candidates=[
            CompanyWebsiteCandidate(
                url="https://acme.test",
                source="official_feed.adresWww",
                confidence=0.98,
            )
        ],
        city="Gdańsk",
    )
    store.upsert_jobs([job])
    persist_job_company_website_candidates(store, [job])
    company_id = int(store.list_companies()[0]["id"])
    discovery = DiscoveryResult(
        company=CompanyIdentity(
            name="ACME Logistics",
            city="Gdańsk",
            website_url="https://acme.test",
            domain="acme.test",
            website_confidence=0.97,
            website_resolution_origin=WebsiteResolutionOrigin.SOURCE_CANDIDATE,
            website_resolution_source="official_feed.adresWww",
            website_verification_signals=[
                "source_website_candidate:official_feed.adresWww",
                "accepted",
            ],
        ),
        search_candidates=[],
    )
    store.save_discovery_result(company_id, discovery)
    record_discovery_audit(store, company_id, discovery)

    report = build_benchmark_report(store)

    assert report.website_candidates_total == 1
    assert report.companies_with_website_candidates == 1
    assert report.source_verified_websites == 1
    assert report.source_website_candidate_company_rate == 1.0
    assert report.source_verified_website_rate == 1.0
    assert report.source_verified_share_of_found == 1.0
    assert report.website_resolution_origin_counts == {"source_candidate": 1}
    assert report.source_verified_website_counts == {
        "official_feed.adresWww": 1
    }


def test_export_green_channels_json_and_csv(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "export.sqlite3")
    _seed(store)

    json_path = export_green_channels(store, tmp_path / "green.json")
    csv_path = export_green_channels(store, tmp_path / "green.csv")

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    csv_text = csv_path.read_text(encoding="utf-8-sig")

    assert payload[0]["value"] == "partnerzy@firma.test"
    assert "partnerzy@firma.test" in csv_text
    assert "evidence_url" in csv_text
