import json
from pathlib import Path

from agregator.audit import record_discovery_audit
from agregator.company_identifiers import persist_job_company_identifiers
from agregator.company_websites import persist_job_company_website_candidates
from agregator.dataset_export import export_dataset_bundle
from agregator.models import (
    ChannelKind,
    ChannelPurpose,
    CompanyIdentifier,
    CompanyIdentity,
    CompanyWebsiteCandidate,
    ContactChannel,
    Decision,
    DiscoveryResult,
    Evidence,
    JobPosting,
    PageSnapshot,
    WebsiteResolutionOrigin,
)
from agregator.storage import SQLiteStore


def test_export_dataset_bundle_preserves_resolution_and_evidence(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "dataset.sqlite3")
    store.init_schema()
    job = JobPosting(
        source="olx",
        source_id="1",
        url="https://jobs.test/1",
        title="Specjalista",
        company_name="ACME Sp. z o.o.",
        company_name_source="company.name",
        company_name_confidence=0.98,
        company_identifiers=[
            CompanyIdentifier(
                kind="nip",
                value="1234567890",
                source="fixture.nip",
                confidence=0.99,
            )
        ],
        company_website_candidates=[
            CompanyWebsiteCandidate(
                url="https://acme.test",
                source="fixture.website",
                confidence=0.96,
            )
        ],
        city="Gdańsk",
    )
    store.upsert_jobs([job])
    persist_job_company_identifiers(store, [job])
    persist_job_company_website_candidates(store, [job])
    company_id = int(store.list_companies()[0]["id"])
    discovery = DiscoveryResult(
        company=CompanyIdentity(
            name="ACME Sp. z o.o.",
            city="Gdańsk",
            website_url="https://acme.test",
            domain="acme.test",
            website_confidence=0.99,
            website_resolution_origin=WebsiteResolutionOrigin.SOURCE_CANDIDATE,
            website_resolution_source="fixture.website",
            website_verification_signals=["exact_normalized_company_name", "accepted"],
        ),
        channels=[
            ContactChannel(
                kind=ChannelKind.EMAIL,
                value="partnerzy@acme.test",
                purpose=ChannelPurpose.BUSINESS_PARTNERSHIP,
                decision=Decision.GREEN,
                confidence=0.97,
                evidence=Evidence(
                    url="https://acme.test/partnerzy",
                    text="Współpraca: partnerzy@acme.test",
                    signal="współpraca",
                ),
            )
        ],
        scanned_pages=["https://acme.test", "https://acme.test/partnerzy"],
        page_snapshots=[
            PageSnapshot(
                url="https://acme.test",
                status_code=200,
                content_sha256="a" * 64,
                text_excerpt="ACME Sp. z o.o. — kontakt dla partnerów",
            )
        ],
    )
    store.save_discovery_result(company_id, discovery)
    record_discovery_audit(store, company_id, discovery)

    result = export_dataset_bundle(store, tmp_path / "export")

    assert result.companies == 1
    assert result.jobs == 1
    assert result.identifiers == 1
    assert result.identifier_observations == 1
    assert result.website_candidates == 1
    assert result.website_candidate_observations == 1
    assert result.contacts == 1
    assert result.website_verifications == 1
    assert result.evidence_snapshots == 1
    assert result.evidence_observations == 1
    assert result.website_snapshots.rows == 1
    assert result.website_snapshots.parse_errors == 0
    assert result.companies_path.exists()
    assert result.jobs_path.exists()
    assert result.identifiers_path.exists()
    assert result.identifier_observations_path.exists()
    assert result.website_candidates_path.exists()
    assert result.website_candidate_observations_path.exists()
    assert result.contacts_path.exists()
    assert result.website_verifications_path.exists()
    assert result.evidence_snapshots_path.exists()
    assert result.evidence_observations_path.exists()
    assert result.website_snapshots.path.exists()
    assert result.manifest_path.exists()

    companies = result.companies_path.read_text(encoding="utf-8-sig")
    jobs = result.jobs_path.read_text(encoding="utf-8-sig")
    identifiers = result.identifiers_path.read_text(encoding="utf-8-sig")
    identifier_observations = result.identifier_observations_path.read_text(
        encoding="utf-8-sig"
    )
    website_candidates = result.website_candidates_path.read_text(encoding="utf-8-sig")
    website_candidate_observations = result.website_candidate_observations_path.read_text(
        encoding="utf-8-sig"
    )
    contacts = result.contacts_path.read_text(encoding="utf-8-sig")
    website_runs = result.website_verifications_path.read_text(encoding="utf-8-sig")
    snapshots = result.evidence_snapshots_path.read_text(encoding="utf-8-sig")
    observations = result.evidence_observations_path.read_text(encoding="utf-8-sig")
    page_snapshots = result.website_snapshots.path.read_text(encoding="utf-8-sig")
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))

    assert "ACME Sp. z o.o." in companies
    assert "new_company" in jobs
    assert "company_resolution_confidence" in jobs
    assert "1234567890" in identifiers
    assert "fixture.nip" in identifiers
    assert "job_source" in identifier_observations
    assert "olx" in identifier_observations
    assert "fixture.nip" in identifier_observations
    assert "https://acme.test" in website_candidates
    assert "fixture.website" in website_candidates
    assert "observation_count" in website_candidates
    assert "job_source" in website_candidate_observations
    assert "olx" in website_candidate_observations
    assert "fixture.website" in website_candidate_observations
    assert "partnerzy@acme.test" in contacts
    assert "evidence_url" in contacts
    assert "exact_normalized_company_name" in website_runs
    assert "resolution_origin" in website_runs
    assert "source_candidate" in website_runs
    assert "fixture.website" in website_runs
    assert "content_sha256" in snapshots
    assert "website_verification_run_id" in observations
    assert "snapshot_changed" in observations
    assert "business_partnership" in observations
    assert "ACME Sp. z o.o. — kontakt dla partnerów" in page_snapshots
    assert "a" * 64 in page_snapshots
    assert manifest["schema_version"] == "8"
    assert manifest["counts"] == {
        "companies": 1,
        "job_postings": 1,
        "company_identifiers": 1,
        "company_identifier_observations": 1,
        "company_website_candidates": 1,
        "company_website_candidate_observations": 1,
        "contact_channels": 1,
        "website_verification_runs": 1,
        "contact_evidence_snapshots": 1,
        "contact_evidence_observations": 1,
        "website_page_snapshots": 1,
        "website_page_snapshot_parse_errors": 0,
    }
    assert manifest["files"]["company_identifier_observations"] == (
        "company_identifier_observations.csv"
    )
    assert manifest["files"]["company_website_candidate_observations"] == (
        "company_website_candidate_observations.csv"
    )
    assert manifest["files"]["contact_evidence_observations"] == (
        "contact_evidence_observations.csv"
    )
    assert manifest["files"]["website_page_snapshots"] == "website_page_snapshots.csv"
