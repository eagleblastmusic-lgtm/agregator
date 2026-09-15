from pathlib import Path

from agregator.models import JobPosting
from agregator.storage import SQLiteStore


def _job(
    source_id: str,
    title: str = "Kasjer",
    *,
    source: str = "olx",
    company_name: str = "Słodka Chatka Sp. z o.o.",
    company_name_confidence: float = 0.95,
    city: str | None = "Koleczkowo",
) -> JobPosting:
    return JobPosting(
        source=source,
        source_id=source_id,
        url=f"https://example.test/{source}/{source_id}",
        title=title,
        company_name=company_name,
        company_name_source="company.name",
        company_name_confidence=company_name_confidence,
        city=city,
    )


def test_store_deduplicates_company_and_updates_job(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "test.sqlite3")
    store.init_schema()

    first = store.upsert_jobs([_job("1"), _job("2")])
    second = store.upsert_jobs([_job("1", title="Kasjer Sprzedawca")])
    companies = store.list_companies()

    assert first.jobs_inserted == 2
    assert first.companies_created == 1
    assert second.jobs_updated == 1
    assert second.companies_created == 0
    assert len(companies) == 1
    assert companies[0]["job_count"] == 2
    assert companies[0]["canonical_name"] == "Słodka Chatka Sp. z o.o."


def test_strong_exact_name_merges_company_across_cities_and_sources(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "cross-city.sqlite3")
    store.init_schema()

    first = store.upsert_jobs(
        [
            _job(
                "olx-1",
                source="olx",
                company_name="ACME Logistics Sp. z o.o.",
                city="Gdańsk",
            )
        ]
    )
    second = store.upsert_jobs(
        [
            _job(
                "jooble-1",
                source="jooble",
                company_name="ACME Logistics",
                city="Warszawa",
            )
        ]
    )
    companies = store.list_companies()

    assert first.companies_created == 1
    assert second.companies_created == 0
    assert len(companies) == 1
    assert companies[0]["job_count"] == 2
    assert set(str(companies[0]["sources"]).split(",")) == {"olx", "jooble"}
    assert "ACME Logistics Sp. z o.o." in str(companies[0]["aliases"])
    assert "ACME Logistics" in str(companies[0]["aliases"])
    assert "Gdańsk" in str(companies[0]["locations"])
    assert "Warszawa" in str(companies[0]["locations"])

    stats = {row["method"]: row for row in store.company_resolution_stats()}
    assert stats["new_company"]["job_count"] == 1
    assert stats["exact_name_cross_city"]["job_count"] == 1


def test_low_confidence_cross_city_name_stays_separate(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "low-confidence.sqlite3")
    store.init_schema()

    store.upsert_jobs(
        [
            _job(
                "1",
                company_name="ACME Logistics",
                company_name_confidence=0.95,
                city="Gdańsk",
            ),
            _job(
                "2",
                source="other",
                company_name="ACME Logistics",
                company_name_confidence=0.45,
                city="Warszawa",
            ),
        ]
    )

    companies = store.list_companies()
    assert len(companies) == 2


def test_short_name_cross_city_stays_separate(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "short-name.sqlite3")
    store.init_schema()

    store.upsert_jobs(
        [
            _job("1", company_name="ABC", city="Gdańsk"),
            _job("2", source="other", company_name="ABC", city="Warszawa"),
        ]
    )

    assert len(store.list_companies()) == 2


def test_source_cursor_roundtrip(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "state.sqlite3")
    store.init_schema()

    assert store.get_source_cursor("olx") is None
    store.set_source_cursor("olx", "40")
    assert store.get_source_cursor("olx") == "40"
    store.set_source_cursor("olx", None)
    assert store.get_source_cursor("olx") is None
