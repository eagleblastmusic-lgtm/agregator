from pathlib import Path

from agregator.company_websites import (
    list_company_website_candidates,
    normalize_company_website_candidate,
    persist_job_company_website_candidates,
)
from agregator.models import CompanyWebsiteCandidate, JobPosting
from agregator.storage import SQLiteStore


def _job(source_id: str, website_url: str) -> JobPosting:
    return JobPosting(
        source="fixture",
        source_id=source_id,
        url=f"https://jobs.test/{source_id}",
        title="Pracownik",
        company_name="Firma Testowa Sp. z o.o.",
        company_name_source="official_feed.pracodawca",
        company_name_confidence=0.995,
        company_website_candidates=[
            CompanyWebsiteCandidate(
                url=website_url,
                source="official_feed.adresWww",
                confidence=0.98,
            )
        ],
        city="Gdańsk",
    )


def test_normalize_company_website_candidate_adds_https() -> None:
    assert normalize_company_website_candidate("www.example.pl/kontakt") == (
        "https://www.example.pl/kontakt",
        "example.pl",
    )


def test_normalize_company_website_candidate_rejects_invalid_values() -> None:
    assert normalize_company_website_candidate("javascript:alert(1)") is None
    assert normalize_company_website_candidate("http://localhost") is None
    assert normalize_company_website_candidate("not a domain") is None


def test_website_candidate_persistence_counts_observations(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "websites.sqlite3")
    store.init_schema()
    job = _job("1", "https://www.example.pl")
    store.upsert_jobs([job])

    first = persist_job_company_website_candidates(store, [job])
    second = persist_job_company_website_candidates(store, [job])
    company_id = int(store.list_companies()[0]["id"])
    candidates = list_company_website_candidates(store, company_id)

    assert first.inserted == 1
    assert first.invalid == 0
    assert second.updated == 1
    assert len(candidates) == 1
    assert candidates[0]["url"] == "https://www.example.pl"
    assert candidates[0]["host"] == "example.pl"
    assert candidates[0]["source"] == "official_feed.adresWww"
    assert candidates[0]["confidence"] == 0.98
    assert candidates[0]["observation_count"] == 2


def test_invalid_candidate_is_not_persisted(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "invalid-websites.sqlite3")
    store.init_schema()
    job = _job("1", "javascript:alert(1)")
    store.upsert_jobs([job])

    stats = persist_job_company_website_candidates(store, [job])

    assert stats.invalid == 1
    assert stats.inserted == 0
