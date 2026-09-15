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
    WebsiteVerificationAttempt,
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
        _contact_discovery("Kontakt dla partnerów: partnerzy@firma.test"),
    )
    return company_id


def _contact_discovery(text: str) -> DiscoveryResult:
    return DiscoveryResult(
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
                    text=text,
                    signal="partnerzy",
                ),
            )
        ],
    )


def _attempt(
    url: str,
    *,
    accepted: bool,
    origin: WebsiteResolutionOrigin,
    source: str,
) -> WebsiteVerificationAttempt:
    return WebsiteVerificationAttempt(
        url=url,
        resolved_url=url,
        accepted=accepted,
        score=0.95 if accepted else 0.2,
        search_score=0.95,
        content_score=0.95 if accepted else 0.1,
        name_coverage=1.0 if accepted else 0.0,
        origin=origin,
        source=source,
        signals=["accepted"] if accepted else ["identity_not_confirmed"],
    )


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
    assert report.source_website_attempts_total == 0
    assert report.source_website_attempts_accepted == 0
    assert report.source_website_attempts_rejected == 0
    assert report.source_website_attempt_acceptance_rate == 0.0
    assert report.search_fallbacks_after_source_rejection == 0
    assert report.search_fallback_after_source_rejection_rate == 0.0
    assert report.source_website_candidate_company_rate == 0.0
    assert report.source_verified_website_rate == 0.0
    assert report.source_verified_share_of_found == 0.0
    assert report.website_resolution_origin_counts == {}
    assert report.source_verified_website_counts == {}
    assert report.source_website_attempt_metrics == {}
    assert report.green_channels == 1
    assert report.contact_evidence_snapshots_total == 0
    assert report.contact_evidence_observations_total == 0
    assert report.contact_evidence_changes_total == 0
    assert report.changed_contact_channels == 0
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


def test_benchmark_report_counts_contact_evidence_timeline(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "evidence-timeline.sqlite3")
    company_id = _seed(store)

    first = _contact_discovery("Kontakt dla partnerów: partnerzy@firma.test")
    record_discovery_audit(store, company_id, first)

    changed = _contact_discovery("Nowy kontakt dla partnerów: partnerzy@firma.test")
    store.save_discovery_result(company_id, changed)
    record_discovery_audit(store, company_id, changed)

    report = build_benchmark_report(store)

    assert report.contact_evidence_snapshots_total == 2
    assert report.contact_evidence_observations_total == 2
    assert report.contact_evidence_changes_total == 1
    assert report.changed_contact_channels == 1


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
        website_attempts=[
            _attempt(
                "https://acme.test",
                accepted=True,
                origin=WebsiteResolutionOrigin.SOURCE_CANDIDATE,
                source="official_feed.adresWww",
            )
        ],
    )
    store.save_discovery_result(company_id, discovery)
    record_discovery_audit(store, company_id, discovery)

    report = build_benchmark_report(store)

    assert report.website_candidates_total == 1
    assert report.companies_with_website_candidates == 1
    assert report.source_verified_websites == 1
    assert report.source_website_attempts_total == 1
    assert report.source_website_attempts_accepted == 1
    assert report.source_website_attempts_rejected == 0
    assert report.source_website_attempt_acceptance_rate == 1.0
    assert report.search_fallbacks_after_source_rejection == 0
    assert report.search_fallback_after_source_rejection_rate == 0.0
    assert report.source_website_candidate_company_rate == 1.0
    assert report.source_verified_website_rate == 1.0
    assert report.source_verified_share_of_found == 1.0
    assert report.website_resolution_origin_counts == {"source_candidate": 1}
    assert report.source_verified_website_counts == {
        "official_feed.adresWww": 1
    }
    assert report.source_website_attempt_metrics == {
        "official_feed.adresWww": {
            "attempts": 1,
            "accepted": 1,
            "rejected": 0,
            "acceptance_rate": 1.0,
        }
    }


def test_benchmark_report_measures_search_fallback_after_source_rejection(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "source-fallback.sqlite3")
    store.init_schema()
    job = JobPosting(
        source="epraca",
        source_id="fallback-1",
        url="https://jobs.test/fallback-1",
        title="Kierowca",
        company_name="ACME Transport",
        company_name_source="official_feed.pracodawca",
        company_name_confidence=0.995,
        company_website_candidates=[
            CompanyWebsiteCandidate(
                url="https://wrong.test",
                source="official_feed.adresWww",
                confidence=0.98,
            )
        ],
        city="Gdynia",
    )
    store.upsert_jobs([job])
    persist_job_company_website_candidates(store, [job])
    company_id = int(store.list_companies()[0]["id"])
    discovery = DiscoveryResult(
        company=CompanyIdentity(
            name="ACME Transport",
            city="Gdynia",
            website_url="https://acme-transport.test",
            domain="acme-transport.test",
            website_confidence=0.96,
            website_resolution_origin=WebsiteResolutionOrigin.SEARCH,
            website_resolution_source="brave",
            website_verification_signals=["accepted"],
        ),
        website_attempts=[
            _attempt(
                "https://wrong.test",
                accepted=False,
                origin=WebsiteResolutionOrigin.SOURCE_CANDIDATE,
                source="official_feed.adresWww",
            ),
            _attempt(
                "https://acme-transport.test",
                accepted=True,
                origin=WebsiteResolutionOrigin.SEARCH,
                source="brave",
            ),
        ],
    )
    store.save_discovery_result(company_id, discovery)
    record_discovery_audit(store, company_id, discovery)

    report = build_benchmark_report(store)

    assert report.source_website_attempts_total == 1
    assert report.source_website_attempts_accepted == 0
    assert report.source_website_attempts_rejected == 1
    assert report.source_website_attempt_acceptance_rate == 0.0
    assert report.search_fallbacks_after_source_rejection == 1
    assert report.search_fallback_after_source_rejection_rate == 1.0
    assert report.website_resolution_origin_counts == {"search": 1}
    assert report.source_verified_websites == 0
    assert report.source_website_attempt_metrics == {
        "official_feed.adresWww": {
            "attempts": 1,
            "accepted": 0,
            "rejected": 1,
            "acceptance_rate": 0.0,
        }
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
