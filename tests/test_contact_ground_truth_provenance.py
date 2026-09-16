import csv
from pathlib import Path

from agregator.audit import record_discovery_audit
from agregator.contact_ground_truth import export_contact_ground_truth_template
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


def test_contact_truth_template_links_latest_evidence_snapshot(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "contact-provenance.sqlite3")
    store.init_schema()
    store.upsert_jobs(
        [
            JobPosting(
                source="fixture",
                source_id="1",
                url="https://jobs.test/1",
                title="Pracownik",
                company_name="Firma Testowa",
                company_name_source="fixture.company",
                company_name_confidence=0.99,
                city="Gdynia",
            )
        ]
    )
    company_id = int(store.list_companies()[0]["id"])
    result = DiscoveryResult(
        company=CompanyIdentity(
            name="Firma Testowa",
            city="Gdynia",
            website_url="https://firma.test",
            domain="firma.test",
            website_confidence=0.95,
        ),
        channels=[
            ContactChannel(
                kind=ChannelKind.EMAIL,
                value="partnerzy@firma.test",
                purpose=ChannelPurpose.BUSINESS_PARTNERSHIP,
                decision=Decision.GREEN,
                confidence=0.98,
                evidence=Evidence(
                    url="https://firma.test/partnerzy",
                    text="Kontakt dla partnerów: partnerzy@firma.test",
                    signal="partnerzy",
                ),
            )
        ],
    )
    store.save_discovery_result(company_id, result)
    record_discovery_audit(store, company_id, result)

    path = export_contact_ground_truth_template(store, tmp_path / "contact_truth.csv")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        row = next(csv.DictReader(handle))

    assert row["value"] == "partnerzy@firma.test"
    assert row["latest_evidence_snapshot_id"]
    assert len(row["evidence_content_sha256"]) == 64
    assert row["evidence_captured_at"]
    assert row["evidence_text"] == "Kontakt dla partnerów: partnerzy@firma.test"
