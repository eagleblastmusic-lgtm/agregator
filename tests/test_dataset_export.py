import json
from pathlib import Path

from agregator.dataset_export import export_dataset_bundle
from agregator.models import (
    ChannelKind,
    ChannelPurpose,
    CompanyIdentity,
    ContactChannel,
    Decision,
    DiscoveryResult,
    Evidence,
    JobPosting,
)
from agregator.storage import SQLiteStore


def test_export_dataset_bundle_preserves_resolution_and_evidence(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "dataset.sqlite3")
    store.init_schema()
    store.upsert_jobs(
        [
            JobPosting(
                source="olx",
                source_id="1",
                url="https://jobs.test/1",
                title="Specjalista",
                company_name="ACME Sp. z o.o.",
                company_name_source="company.name",
                company_name_confidence=0.98,
                city="Gdańsk",
            )
        ]
    )
    company_id = int(store.list_companies()[0]["id"])
    store.save_discovery_result(
        company_id,
        DiscoveryResult(
            company=CompanyIdentity(
                name="ACME Sp. z o.o.",
                city="Gdańsk",
                website_url="https://acme.test",
                domain="acme.test",
                website_confidence=0.99,
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
        ),
    )

    result = export_dataset_bundle(store, tmp_path / "export")

    assert result.companies == 1
    assert result.jobs == 1
    assert result.contacts == 1
    assert result.companies_path.exists()
    assert result.jobs_path.exists()
    assert result.contacts_path.exists()
    assert result.manifest_path.exists()

    companies = result.companies_path.read_text(encoding="utf-8-sig")
    jobs = result.jobs_path.read_text(encoding="utf-8-sig")
    contacts = result.contacts_path.read_text(encoding="utf-8-sig")
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))

    assert "ACME Sp. z o.o." in companies
    assert "new_company" in jobs
    assert "company_resolution_confidence" in jobs
    assert "partnerzy@acme.test" in contacts
    assert "evidence_url" in contacts
    assert manifest["schema_version"] == "1"
    assert manifest["counts"] == {
        "companies": 1,
        "job_postings": 1,
        "contact_channels": 1,
    }
