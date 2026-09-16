from pathlib import Path

from agregator.company_identifiers import (
    list_identifier_conflicts,
    persist_job_company_identifiers,
)
from agregator.models import CompanyIdentifier, JobPosting
from agregator.storage import SQLiteStore


def _job(
    source_id: str,
    company: str,
    *,
    nip: str,
    city: str = "Gdańsk",
) -> JobPosting:
    return JobPosting(
        source="fixture",
        source_id=source_id,
        url=f"https://jobs.test/{source_id}",
        title="Pracownik",
        company_name=company,
        company_name_source="official_feed.pracodawca",
        company_name_confidence=0.995,
        company_identifiers=[
            CompanyIdentifier(
                kind="NIP",
                value=nip,
                source="official_feed.nip",
                confidence=0.995,
            )
        ],
        city=city,
    )


def test_identifier_persistence_normalizes_and_counts_observations(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "identifiers.sqlite3")
    store.init_schema()
    first = _job("1", "Firma Testowa Sp. z o.o.", nip="123-456-78-90")
    store.upsert_jobs([first])

    first_stats = persist_job_company_identifiers(store, [first])
    second_stats = persist_job_company_identifiers(store, [first])

    assert first_stats.inserted == 1
    assert first_stats.invalid == 0
    assert second_stats.updated == 1

    with store.connect() as connection:
        row = connection.execute(
            "SELECT kind, value, confidence, observation_count FROM company_identifiers"
        ).fetchone()

    assert row["kind"] == "nip"
    assert row["value"] == "1234567890"
    assert row["confidence"] == 0.995
    assert row["observation_count"] == 2


def test_invalid_known_identifier_is_not_persisted(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "invalid.sqlite3")
    store.init_schema()
    job = _job("1", "Firma Testowa", nip="123")
    store.upsert_jobs([job])

    stats = persist_job_company_identifiers(store, [job])

    assert stats.invalid == 1
    assert stats.inserted == 0


def test_same_identifier_on_two_company_records_is_review_conflict_not_merge(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "conflict.sqlite3")
    store.init_schema()
    left = _job("1", "Alpha Logistics", nip="1234567890", city="Gdańsk")
    right = _job("2", "Beta Retail", nip="1234567890", city="Warszawa")
    store.upsert_jobs([left, right])

    left_stats = persist_job_company_identifiers(store, [left])
    right_stats = persist_job_company_identifiers(store, [right])
    conflicts = list_identifier_conflicts(store)

    assert left_stats.conflicts == 0
    assert right_stats.conflicts == 1
    assert len(conflicts) == 1
    assert conflicts[0]["kind"] == "nip"
    assert conflicts[0]["value"] == "1234567890"
    assert conflicts[0]["company_count"] == 2

    companies = store.list_companies(limit=10)
    assert len(companies) == 2
