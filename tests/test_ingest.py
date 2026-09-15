from pathlib import Path

import pytest

from agregator.ingest import ingest_source
from agregator.models import JobPosting
from agregator.sources.base import SourceBatch
from agregator.storage import SQLiteStore


class FakeSource:
    name = "fake"

    def __init__(self) -> None:
        self.cursors: list[str | None] = []

    async def collect(self, cursor: str | None = None) -> SourceBatch:
        self.cursors.append(cursor)
        if cursor is None:
            return SourceBatch(jobs=[_job("1")], next_cursor="page-2")
        if cursor == "page-2":
            return SourceBatch(jobs=[_job("2")], next_cursor=None)
        raise AssertionError(f"unexpected cursor: {cursor}")


def _job(source_id: str) -> JobPosting:
    return JobPosting(
        source="fake",
        source_id=source_id,
        url=f"https://example.test/{source_id}",
        title=f"Oferta {source_id}",
        company_name="Firma Testowa",
        company_name_confidence=0.9,
        city="Gdańsk",
    )


@pytest.mark.asyncio
async def test_ingest_resumes_from_saved_cursor(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "ingest.sqlite3")
    source = FakeSource()

    first = await ingest_source(source, store, pages=1)
    second = await ingest_source(source, store, pages=1)

    assert first.next_cursor == "page-2"
    assert second.next_cursor is None
    assert source.cursors == [None, "page-2"]
    assert store.list_companies()[0]["job_count"] == 2
