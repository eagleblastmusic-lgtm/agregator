from pathlib import Path

from agregator.models import JobPosting
from agregator.storage import SQLiteStore


def _job(source_id: str, title: str = "Kasjer") -> JobPosting:
    return JobPosting(
        source="olx",
        source_id=source_id,
        url=f"https://example.test/{source_id}",
        title=title,
        company_name="Słodka Chatka Sp. z o.o.",
        company_name_source="user.company_name",
        company_name_confidence=0.95,
        city="Koleczkowo",
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


def test_source_cursor_roundtrip(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "state.sqlite3")
    store.init_schema()

    assert store.get_source_cursor("olx") is None
    store.set_source_cursor("olx", "40")
    assert store.get_source_cursor("olx") == "40"
    store.set_source_cursor("olx", None)
    assert store.get_source_cursor("olx") is None
