import json
from pathlib import Path

from agregator.audit import record_discovery_audit
from agregator.models import (
    ChannelKind,
    ChannelPurpose,
    CompanyIdentity,
    ContactChannel,
    Decision,
    DiscoveryResult,
    Evidence,
    JobPosting,
    SearchCandidate,
)
from agregator.storage import SQLiteStore


def _seed_company(store: SQLiteStore) -> int:
    store.init_schema()
    store.upsert_jobs(
        [
            JobPosting(
                source="source-a",
                source_id="1",
                url="https://jobs.test/1",
                title="Test",
                company_name="Firma Testowa",
                company_name_source="api.company",
                company_name_confidence=0.95,
                city="Gdynia",
            )
        ]
    )
    return int(store.list_companies()[0]["id"])


def _result(text: str = "Kontakt dla partnerów: partnerzy@firma.test") -> DiscoveryResult:
    return DiscoveryResult(
        company=CompanyIdentity(
            name="Firma Testowa",
            city="Gdynia",
            website_url="https://firma.test",
            domain="firma.test",
            website_confidence=0.93,
            website_verification_signals=[
                "jsonld_organization_name",
                "accepted",
            ],
        ),
        channels=[
            ContactChannel(
                kind=ChannelKind.EMAIL,
                value="partnerzy@firma.test",
                purpose=ChannelPurpose.BUSINESS_PARTNERSHIP,
                decision=Decision.GREEN,
                confidence=0.95,
                evidence=Evidence(
                    url="https://firma.test/partnerzy",
                    text=text,
                    signal="kontakt dla partnerow",
                ),
            )
        ],
        scanned_pages=["https://firma.test", "https://firma.test/partnerzy"],
        search_candidates=[
            SearchCandidate(
                title="Firma Testowa",
                url="https://firma.test",
                snippet="Oficjalna strona",
                score=0.88,
            )
        ],
    )


def test_discovery_audit_records_website_run_and_deduplicates_same_evidence(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "audit.sqlite3")
    company_id = _seed_company(store)
    result = _result()
    store.save_discovery_result(company_id, result)

    first = record_discovery_audit(store, company_id, result)
    second = record_discovery_audit(store, company_id, result)

    assert first.website_runs_recorded == 1
    assert first.evidence_snapshots_recorded == 1
    assert second.website_runs_recorded == 1
    assert second.evidence_snapshots_recorded == 0

    with store.connect() as connection:
        runs = connection.execute(
            "SELECT * FROM website_verification_runs ORDER BY id"
        ).fetchall()
        snapshots = connection.execute(
            "SELECT * FROM contact_evidence_snapshots ORDER BY id"
        ).fetchall()

    assert len(runs) == 2
    assert runs[0]["outcome"] == "verified"
    assert json.loads(runs[0]["verification_signals_json"]) == [
        "jsonld_organization_name",
        "accepted",
    ]
    assert json.loads(runs[0]["scanned_pages_json"])[1].endswith("/partnerzy")
    assert len(snapshots) == 1
    assert len(snapshots[0]["content_sha256"]) == 64


def test_changed_evidence_creates_new_snapshot(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "changed.sqlite3")
    company_id = _seed_company(store)

    first_result = _result("Kontakt dla partnerów: partnerzy@firma.test")
    store.save_discovery_result(company_id, first_result)
    record_discovery_audit(store, company_id, first_result)

    changed_result = _result("Nowy kontakt dla partnerów: partnerzy@firma.test")
    store.save_discovery_result(company_id, changed_result)
    audit = record_discovery_audit(store, company_id, changed_result)

    assert audit.evidence_snapshots_recorded == 1
    with store.connect() as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM contact_evidence_snapshots"
        ).fetchone()[0]
    assert count == 2
