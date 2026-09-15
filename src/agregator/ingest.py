from __future__ import annotations

from dataclasses import dataclass

from .company_identifiers import persist_job_company_identifiers
from .sources.base import JobSource
from .storage import SQLiteStore, UpsertStats


@dataclass(slots=True)
class IngestResult:
    source: str
    pages: int
    next_cursor: str | None
    stats: UpsertStats
    run_id: int


async def ingest_source(
    source: JobSource,
    store: SQLiteStore,
    *,
    pages: int = 1,
    resume: bool = True,
) -> IngestResult:
    store.init_schema()
    requested_pages = max(1, pages)
    cursor = store.get_source_cursor(source.name) if resume else None
    cursor_before = cursor
    aggregate = UpsertStats()
    processed_pages = 0
    run_id = store.start_source_run(
        source.name,
        cursor_before=cursor_before,
        pages_requested=requested_pages,
    )

    try:
        for _ in range(requested_pages):
            batch = await source.collect(cursor)
            stats = store.upsert_jobs(batch.jobs)
            persist_job_company_identifiers(store, batch.jobs)
            aggregate.jobs_seen += stats.jobs_seen
            aggregate.jobs_inserted += stats.jobs_inserted
            aggregate.jobs_updated += stats.jobs_updated
            aggregate.companies_created += stats.companies_created
            processed_pages += 1

            cursor = batch.next_cursor
            store.set_source_cursor(source.name, cursor)
            if cursor is None:
                break
    except Exception as exc:
        store.finish_source_run(
            run_id,
            status="failed",
            cursor_after=cursor,
            pages_processed=processed_pages,
            stats=aggregate,
            error=exc,
        )
        raise

    store.finish_source_run(
        run_id,
        status="success",
        cursor_after=cursor,
        pages_processed=processed_pages,
        stats=aggregate,
    )
    return IngestResult(
        source=source.name,
        pages=processed_pages,
        next_cursor=cursor,
        stats=aggregate,
        run_id=run_id,
    )
