import csv
from pathlib import Path

from agregator.audit import record_discovery_audit
from agregator.company_websites import persist_job_company_website_candidates
from agregator.models import (
    CompanyIdentity,
    CompanyWebsiteCandidate,
    DiscoveryResult,
    JobPosting,
    WebsiteResolutionOrigin,
)
from agregator.storage import SQLiteStore
from agregator.website_ground_truth import export_website_ground_truth_template


def test_website_ground_truth_template_includes_latest_provenance(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "provenance.sqlite3")
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
        )
    )
    store.save_discovery_result(company_id, discovery)
    record_discovery_audit(store, company_id, discovery)

    path = export_website_ground_truth_template(store, tmp_path / "website_truth.csv")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        row = next(csv.DictReader(handle))

    assert row["company_id"] == str(company_id)
    assert row["predicted_domain"] == "acme.test"
    assert row["verification_outcome"] == "verified"
    assert row["predicted_resolution_origin"] == "source_candidate"
    assert row["predicted_resolution_source"] == "official_feed.adresWww"
    assert row["source_website_candidate_count"] == "1"
    assert row["latest_verification_id"]
    assert "accepted" in row["verification_signals_json"]
