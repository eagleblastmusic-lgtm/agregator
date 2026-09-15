from pathlib import Path

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
from agregator.quality_gate import evaluate_quality_gate
from agregator.quality_labels import export_quality_label_bundle
from agregator.storage import SQLiteStore


def _seed(store: SQLiteStore) -> tuple[int, int]:
    store.init_schema()
    store.upsert_jobs(
        [
            JobPosting(
                source="a",
                source_id="1",
                url="https://jobs.test/1",
                title="A",
                company_name="Alpha Systems",
                company_name_source="api.company",
                company_name_confidence=0.95,
                city="Gdańsk",
            ),
            JobPosting(
                source="b",
                source_id="2",
                url="https://jobs.test/2",
                title="B",
                company_name="Alpha Systems Sp. z o.o.",
                company_name_source="api.company",
                company_name_confidence=0.95,
                city="Warszawa",
            ),
        ]
    )
    company_id = int(store.list_companies()[0]["id"])
    store.save_discovery_result(
        company_id,
        DiscoveryResult(
            company=CompanyIdentity(
                name="Alpha Systems",
                city="Gdańsk",
                website_url="https://alpha.example",
                domain="alpha.example",
                website_confidence=0.93,
            ),
            channels=[
                ContactChannel(
                    kind=ChannelKind.EMAIL,
                    value="partnerzy@alpha.example",
                    purpose=ChannelPurpose.BUSINESS_PARTNERSHIP,
                    decision=Decision.GREEN,
                    confidence=0.98,
                    evidence=Evidence(
                        url="https://alpha.example/partnerzy",
                        text="Kontakt dla partnerów: partnerzy@alpha.example",
                        signal="kontakt dla partnerow",
                    ),
                )
            ],
        ),
    )
    with store.connect() as connection:
        contact_id = int(
            connection.execute("SELECT id FROM contact_channels").fetchone()[0]
        )
    return company_id, contact_id


def test_quality_gate_combines_all_three_manual_evaluations(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "quality.sqlite3")
    company_id, contact_id = _seed(store)

    resolution = tmp_path / "resolution.csv"
    resolution.write_text(
        "source,source_id,truth_company_id\n"
        "a,1,alpha\n"
        "b,2,alpha\n",
        encoding="utf-8",
    )
    website = tmp_path / "website.csv"
    website.write_text(
        "company_id,truth_domain\n"
        f"{company_id},alpha.example\n",
        encoding="utf-8",
    )
    contacts = tmp_path / "contacts.csv"
    contacts.write_text(
        "contact_id,truth_decision,truth_purpose\n"
        f"{contact_id},green,business_partnership\n",
        encoding="utf-8",
    )

    result = evaluate_quality_gate(
        store,
        resolution_truth=resolution,
        website_truth=website,
        contact_truth=contacts,
        min_resolution_f1=1.0,
        min_website_f1=1.0,
        min_contact_macro_f1=1.0,
    )

    assert result.passed is True
    assert len(result.checks) == 3
    assert all(check.passed for check in result.checks)
    assert result.reports["company_resolution"]["f1"] == 1.0
    assert result.reports["website_resolution"]["f1"] == 1.0
    assert result.reports["contact_classification"]["decision_macro_f1"] == 1.0


def test_quality_label_bundle_exports_all_templates(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "labels.sqlite3")
    _seed(store)

    bundle = export_quality_label_bundle(store, tmp_path / "labels")

    assert bundle.company_resolution_path.exists()
    assert bundle.website_resolution_path.exists()
    assert bundle.contact_classification_path.exists()
    assert "truth_company_id" in bundle.company_resolution_path.read_text(encoding="utf-8-sig")
    assert "truth_domain" in bundle.website_resolution_path.read_text(encoding="utf-8-sig")
    assert "truth_decision" in bundle.contact_classification_path.read_text(encoding="utf-8-sig")
