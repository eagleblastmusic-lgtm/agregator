from pathlib import Path

from agregator.company_identifiers import persist_job_company_identifiers
from agregator.company_websites import persist_job_company_website_candidates
from agregator.models import CompanyIdentifier, CompanyWebsiteCandidate, JobPosting
from agregator.reporting import build_benchmark_report
from agregator.storage import SQLiteStore


def test_benchmark_report_embeds_source_identity_and_provenance(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "report-source-diagnostics.sqlite3")
    store.init_schema()
    job = JobPosting(
        source="epraca",
        source_id="1",
        url="https://jobs.test/1",
        title="Magazynier",
        company_name="ACME Logistics",
        company_name_source="official_feed.pracodawca",
        company_name_confidence=0.995,
        company_identifiers=[
            CompanyIdentifier(
                kind="nip",
                value="1234567890",
                source="official_feed.nip",
                confidence=0.995,
            )
        ],
        company_website_candidates=[
            CompanyWebsiteCandidate(
                url="https://acme.example",
                source="official_feed.adresWww",
                confidence=0.98,
            )
        ],
        city="Gdańsk",
        description="Opis",
    )
    store.upsert_jobs([job])
    persist_job_company_identifiers(store, [job])
    persist_job_company_website_candidates(store, [job])

    report = build_benchmark_report(store)
    payload = report.to_dict()

    identity = payload["source_identity_metrics"]["epraca"]
    assert identity["jobs"] == 1
    assert identity["avg_company_name_confidence"] == 0.995
    assert identity["city_coverage_rate"] == 1.0

    provenance = payload["source_provenance_metrics"]["epraca"]
    assert provenance["identifier_company_rate"] == 1.0
    assert provenance["identifier_evidence_sources"] == {"official_feed.nip": 1}
    assert provenance["website_candidate_company_rate"] == 1.0
    assert provenance["website_evidence_sources"] == {
        "official_feed.adresWww": 1
    }
