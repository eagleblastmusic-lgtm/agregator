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


class FailingSource:
    name = "failing"

    async def collect(self, cursor: str | None = None) -> SourceBatch:
        raise RuntimeError("source unavailable")


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
    runs = store.list_source_runs(source="fake")

    assert first.next_cursor == "page-2"
    assert second.next_cursor is None
    assert source.cursors == [None, "page-2"]
    assert store.list_companies()[0]["job_count"] == 2
    assert len(runs) == 2
    assert runs[0]["status"] == "success"
    assert runs[0]["jobs_inserted"] == 1
    assert runs[0]["cursor_before"] == "page-2"
    assert runs[0]["cursor_after"] is None
    assert first.run_id != second.run_id


@pytest.mark.asyncio
async def test_ingest_records_failed_run(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "failed.sqlite3")

    with pytest.raises(RuntimeError, match="source unavailable"):
        await ingest_source(FailingSource(), store, pages=2)

    run = store.list_source_runs(source="failing")[0]
    assert run["status"] == "failed"
    assert run["pages_requested"] == 2
    assert run["pages_processed"] == 0
    assert run["error_type"] == "RuntimeError"
    assert run["error_message"] == "source unavailable"
