import csv
from pathlib import Path

from agregator.audit import record_discovery_audit
from agregator.audit_export import export_website_page_snapshots
from agregator.models import (
    CompanyIdentity,
    DiscoveryResult,
    JobPosting,
    PageSnapshot,
    WebsiteResolutionOrigin,
    WebsiteVerificationAttempt,
)
from agregator.storage import SQLiteStore


def _company_id(store: SQLiteStore) -> int:
    store.init_schema()
    store.upsert_jobs(
        [
            JobPosting(
                source="fixture",
                source_id="1",
                url="https://jobs.test/1",
                title="Pracownik",
                company_name="ACME Logistics",
                company_name_source="fixture.company",
                company_name_confidence=0.99,
                city="Gdańsk",
            )
        ]
    )
    return int(store.list_companies()[0]["id"])


def _snapshot(url: str, marker: str) -> PageSnapshot:
    return PageSnapshot(
        url=url,
        status_code=200,
        content_sha256=marker * 64,
        text_excerpt=f"Snapshot {marker}",
    )


def test_export_website_page_snapshots_prefers_attempt_history(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "audit.sqlite3")
    company_id = _company_id(store)
    wrong = _snapshot("https://wrong.test", "a")
    accepted = _snapshot("https://acme.test", "b")
    result = DiscoveryResult(
        company=CompanyIdentity(
            name="ACME Logistics",
            city="Gdańsk",
            website_url="https://acme.test",
            domain="acme.test",
            website_confidence=0.96,
            website_resolution_origin=WebsiteResolutionOrigin.SEARCH,
            website_resolution_source="static",
        ),
        page_snapshots=[accepted],
        website_attempts=[
            WebsiteVerificationAttempt(
                url="https://wrong.test",
                resolved_url="https://wrong.test",
                accepted=False,
                score=0.2,
                search_score=0.8,
                content_score=0.0,
                name_coverage=0.0,
                origin=WebsiteResolutionOrigin.SEARCH,
                source="static",
                signals=["identity_not_confirmed"],
                scanned_pages=["https://wrong.test"],
                page_snapshots=[wrong],
            ),
            WebsiteVerificationAttempt(
                url="https://acme.test",
                resolved_url="https://acme.test",
                accepted=True,
                score=0.96,
                search_score=0.9,
                content_score=1.0,
                name_coverage=1.0,
                origin=WebsiteResolutionOrigin.SEARCH,
                source="static",
                signals=["accepted"],
                scanned_pages=["https://acme.test"],
                page_snapshots=[accepted],
            ),
        ],
    )
    store.save_discovery_result(company_id, result)
    record_discovery_audit(store, company_id, result)

    exported = export_website_page_snapshots(store, tmp_path / "snapshots.csv")

    assert exported.rows == 2
    assert exported.verification_runs == 1
    assert exported.parse_errors == 0
    with exported.path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert [row["snapshot_scope"] for row in rows] == ["attempt", "attempt"]
    assert [row["attempt_accepted"] for row in rows] == ["False", "True"]
    assert rows[0]["page_url"] == "https://wrong.test"
    assert rows[0]["content_sha256"] == "a" * 64
    assert rows[1]["page_url"] == "https://acme.test"
    assert rows[1]["content_sha256"] == "b" * 64


def test_export_website_page_snapshots_uses_final_snapshot_without_attempts(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "known.sqlite3")
    company_id = _company_id(store)
    snapshot = _snapshot("https://known.test", "c")
    result = DiscoveryResult(
        company=CompanyIdentity(
            name="ACME Logistics",
            city="Gdańsk",
            website_url="https://known.test",
            domain="known.test",
            website_confidence=1.0,
            website_resolution_origin=WebsiteResolutionOrigin.KNOWN_URL,
            website_resolution_source="scan_known_website",
        ),
        page_snapshots=[snapshot],
        website_attempts=[],
    )
    store.save_discovery_result(company_id, result)
    record_discovery_audit(store, company_id, result)

    exported = export_website_page_snapshots(store, tmp_path / "known.csv")

    assert exported.rows == 1
    with exported.path.open(encoding="utf-8-sig", newline="") as handle:
        row = next(csv.DictReader(handle))
    assert row["snapshot_scope"] == "final"
    assert row["attempt_index"] == ""
    assert row["page_url"] == "https://known.test"
    assert row["content_sha256"] == "c" * 64
