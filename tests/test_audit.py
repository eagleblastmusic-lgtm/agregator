import json
from pathlib import Path

from agregator.audit import init_audit_schema, record_discovery_audit
from agregator.models import (
    ChannelKind,
    ChannelPurpose,
    CompanyIdentity,
    ContactChannel,
    Decision,
    DiscoveryResult,
    Evidence,
    JobPosting,
    PageSnapshot,
    SearchCandidate,
    WebsiteResolutionOrigin,
    WebsiteVerificationAttempt,
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
    snapshot = PageSnapshot(
        url="https://firma.test/partnerzy",
        status_code=200,
        content_sha256="a" * 64,
        text_excerpt=text,
    )
    attempt = WebsiteVerificationAttempt(
        url="https://firma.test",
        resolved_url="https://firma.test",
        accepted=True,
        score=0.93,
        search_score=0.88,
        content_score=0.96,
        name_coverage=1.0,
        origin=WebsiteResolutionOrigin.SEARCH,
        source="search_provider",
        signals=["exact_normalized_company_name", "accepted"],
        scanned_pages=["https://firma.test/partnerzy"],
        page_snapshots=[snapshot],
    )
    return DiscoveryResult(
        company=CompanyIdentity(
            name="Firma Testowa",
            city="Gdynia",
            website_url="https://firma.test",
            domain="firma.test",
            website_confidence=0.93,
            website_resolution_origin=WebsiteResolutionOrigin.SEARCH,
            website_resolution_source="search_provider",
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
        page_snapshots=[snapshot],
        search_candidates=[
            SearchCandidate(
                title="Firma Testowa",
                url="https://firma.test",
                snippet="Oficjalna strona",
                score=0.88,
            )
        ],
        website_attempts=[attempt],
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
    assert first.evidence_observations_recorded == 1
    assert first.evidence_changes_recorded == 0
    assert second.website_runs_recorded == 1
    assert second.evidence_snapshots_recorded == 0
    assert second.evidence_observations_recorded == 1
    assert second.evidence_changes_recorded == 0

    with store.connect() as connection:
        runs = connection.execute(
            "SELECT * FROM website_verification_runs ORDER BY id"
        ).fetchall()
        snapshots = connection.execute(
            "SELECT * FROM contact_evidence_snapshots ORDER BY id"
        ).fetchall()
        observations = connection.execute(
            "SELECT * FROM contact_evidence_observations ORDER BY id"
        ).fetchall()

    assert len(runs) == 2
    assert runs[0]["outcome"] == "verified"
    assert runs[0]["resolution_origin"] == "search"
    assert runs[0]["resolution_source"] == "search_provider"
    assert json.loads(runs[0]["verification_signals_json"]) == [
        "jsonld_organization_name",
        "accepted",
    ]
    assert json.loads(runs[0]["scanned_pages_json"])[1].endswith("/partnerzy")
    page_snapshots = json.loads(runs[0]["page_snapshots_json"])
    assert page_snapshots[0]["content_sha256"] == "a" * 64
    attempts = json.loads(runs[0]["website_attempts_json"])
    assert attempts[0]["accepted"] is True
    assert attempts[0]["origin"] == "search"
    assert attempts[0]["source"] == "search_provider"
    assert attempts[0]["page_snapshots"][0]["content_sha256"] == "a" * 64
    assert len(snapshots) == 1
    assert len(snapshots[0]["content_sha256"]) == 64
    assert len(observations) == 2
    assert observations[0]["snapshot_id"] == observations[1]["snapshot_id"]
    assert observations[0]["snapshot_changed"] == 0
    assert observations[1]["snapshot_changed"] == 0
    assert observations[0]["website_verification_run_id"] == runs[0]["id"]
    assert observations[1]["website_verification_run_id"] == runs[1]["id"]


def test_audit_schema_migrates_legacy_website_runs_before_creating_origin_index(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "legacy-audit.sqlite3")
    store.init_schema()
    with store.connect() as connection:
        connection.executescript(
            """
            CREATE TABLE website_verification_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL,
                outcome TEXT NOT NULL,
                website_url TEXT,
                website_confidence REAL NOT NULL DEFAULT 0,
                verification_signals_json TEXT NOT NULL,
                search_candidates_json TEXT NOT NULL,
                website_attempts_json TEXT NOT NULL DEFAULT '[]',
                scanned_pages_json TEXT NOT NULL,
                page_snapshots_json TEXT NOT NULL DEFAULT '[]',
                captured_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(company_id) REFERENCES companies(id)
            );
            """
        )

    init_audit_schema(store)

    with store.connect() as connection:
        columns = {
            str(row["name"])
            for row in connection.execute(
                "PRAGMA table_info(website_verification_runs)"
            ).fetchall()
        }
        indexes = {
            str(row["name"])
            for row in connection.execute(
                "PRAGMA index_list(website_verification_runs)"
            ).fetchall()
        }
        observation_columns = {
            str(row["name"])
            for row in connection.execute(
                "PRAGMA table_info(contact_evidence_observations)"
            ).fetchall()
        }

    assert "resolution_origin" in columns
    assert "resolution_source" in columns
    assert "idx_website_verification_runs_origin" in indexes
    assert "website_verification_run_id" in observation_columns
    assert "snapshot_changed" in observation_columns


def test_changed_evidence_creates_new_snapshot_and_change_observation(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "changed.sqlite3")
    company_id = _seed_company(store)

    first_result = _result("Kontakt dla partnerów: partnerzy@firma.test")
    store.save_discovery_result(company_id, first_result)
    first_audit = record_discovery_audit(store, company_id, first_result)

    changed_result = _result("Nowy kontakt dla partnerów: partnerzy@firma.test")
    store.save_discovery_result(company_id, changed_result)
    audit = record_discovery_audit(store, company_id, changed_result)

    assert first_audit.evidence_changes_recorded == 0
    assert audit.evidence_snapshots_recorded == 1
    assert audit.evidence_observations_recorded == 1
    assert audit.evidence_changes_recorded == 1
    with store.connect() as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM contact_evidence_snapshots"
        ).fetchone()[0]
        observations = connection.execute(
            """
            SELECT snapshot_id, snapshot_changed
            FROM contact_evidence_observations
            ORDER BY id
            """
        ).fetchall()
    assert count == 2
    assert len(observations) == 2
    assert observations[0]["snapshot_id"] != observations[1]["snapshot_id"]
    assert observations[0]["snapshot_changed"] == 0
    assert observations[1]["snapshot_changed"] == 1
