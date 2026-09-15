from pathlib import Path

from agregator.models import CompanyIdentity, DiscoveryResult, JobPosting
from agregator.resolution_review import build_resolution_review_queue
from agregator.storage import SQLiteStore


def _job(source_id: str, company_name: str, city: str = "Gdańsk") -> JobPosting:
    return JobPosting(
        source="test",
        source_id=source_id,
        url=f"https://jobs.test/{source_id}",
        title="Test",
        company_name=company_name,
        company_name_source="api.company",
        company_name_confidence=0.95,
        city=city,
    )


def _company_id(store: SQLiteStore, canonical_name: str) -> int:
    with store.connect() as connection:
        row = connection.execute(
            "SELECT id FROM companies WHERE canonical_name = ?",
            (canonical_name,),
        ).fetchone()
    assert row is not None
    return int(row["id"])


def _set_website(
    store: SQLiteStore,
    company_name: str,
    website_url: str,
    confidence: float,
) -> None:
    company_id = _company_id(store, company_name)
    store.save_discovery_result(
        company_id,
        DiscoveryResult(
            company=CompanyIdentity(
                name=company_name,
                website_url=website_url,
                website_confidence=confidence,
            )
        ),
    )


def test_similar_names_are_reviewed_without_merging(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "review.sqlite3")
    store.init_schema()
    store.upsert_jobs(
        [
            _job("1", "North Star Logistics"),
            _job("2", "North Star Logistic"),
            _job("3", "Moon Bakery"),
        ]
    )

    before = len(store.list_companies())
    candidates = build_resolution_review_queue(store, min_score=0.8)
    after = len(store.list_companies())

    assert before == 3
    assert after == 3
    assert len(candidates) == 1
    candidate = candidates[0]
    assert {candidate.left_name, candidate.right_name} == {
        "North Star Logistics",
        "North Star Logistic",
    }
    assert candidate.score >= 0.8
    assert candidate.name_similarity > 0.9
    assert candidate.location_overlap is True
    assert candidate.website_match is False


def test_same_verified_website_is_strong_manual_review_signal(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "website.sqlite3")
    store.init_schema()
    store.upsert_jobs(
        [
            _job("1", "Alpha Systems", "Gdańsk"),
            _job("2", "Beta Holdings", "Warszawa"),
        ]
    )
    _set_website(store, "Alpha Systems", "https://example.test/about", 0.98)
    _set_website(store, "Beta Holdings", "https://www.example.test/contact", 0.96)

    candidates = build_resolution_review_queue(store)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.website_match is True
    assert candidate.score >= 0.9
    assert "same_verified_website_host" in candidate.signals


def test_low_confidence_website_does_not_create_review_pair(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "weak-website.sqlite3")
    store.init_schema()
    store.upsert_jobs(
        [
            _job("1", "Alpha Systems", "Gdańsk"),
            _job("2", "Beta Holdings", "Warszawa"),
        ]
    )
    _set_website(store, "Alpha Systems", "https://example.test", 0.6)
    _set_website(store, "Beta Holdings", "https://example.test", 0.6)

    assert build_resolution_review_queue(store) == []
