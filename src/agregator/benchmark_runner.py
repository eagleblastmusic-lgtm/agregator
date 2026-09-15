from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .ingest import ingest_source
from .sources.registry import SourceRegistry
from .storage import SQLiteStore


@dataclass(slots=True)
class BenchmarkSourceStats:
    runs: int = 0
    jobs_seen: int = 0
    jobs_inserted: int = 0
    jobs_updated: int = 0
    companies_created: int = 0
    errors: int = 0
    exhausted: bool = False
    last_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class BenchmarkCollectionResult:
    target_jobs: int
    jobs_before: int
    jobs_after: int
    companies_after: int
    rounds: int
    target_reached: bool
    stopped_reason: str
    sources: dict[str, BenchmarkSourceStats]

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_jobs": self.target_jobs,
            "jobs_before": self.jobs_before,
            "jobs_after": self.jobs_after,
            "companies_after": self.companies_after,
            "rounds": self.rounds,
            "target_reached": self.target_reached,
            "stopped_reason": self.stopped_reason,
            "sources": {
                name: stats.to_dict() for name, stats in self.sources.items()
            },
        }


async def collect_benchmark(
    store: SQLiteStore,
    registry: SourceRegistry,
    source_names: list[str],
    *,
    target_jobs: int = 1000,
    max_rounds: int = 100,
    fresh: bool = False,
    fail_fast: bool = False,
) -> BenchmarkCollectionResult:
    """Collect jobs round-robin until the database reaches the requested size.

    Each active source receives at most one page per round. This avoids letting one
    high-volume source dominate the benchmark before the remaining adapters are
    exercised. Existing source cursors are honored unless ``fresh`` is requested.
    """

    store.init_schema()
    names = _normalize_sources(source_names)
    if not names:
        raise ValueError("benchmark requires at least one source")
    if target_jobs < 1:
        raise ValueError("target_jobs must be >= 1")
    if max_rounds < 1:
        raise ValueError("max_rounds must be >= 1")

    if fresh:
        for name in names:
            store.set_source_cursor(name, None)

    jobs_before = _count(store, "job_postings")
    stats = {name: BenchmarkSourceStats() for name in names}
    rounds = 0

    if jobs_before >= target_jobs:
        return BenchmarkCollectionResult(
            target_jobs=target_jobs,
            jobs_before=jobs_before,
            jobs_after=jobs_before,
            companies_after=_count(store, "companies"),
            rounds=0,
            target_reached=True,
            stopped_reason="target_already_reached",
            sources=stats,
        )

    stopped_reason = "max_rounds"
    for round_number in range(1, max_rounds + 1):
        rounds = round_number
        active_this_round = 0

        for name in names:
            source_stats = stats[name]
            if source_stats.exhausted:
                continue
            active_this_round += 1

            try:
                source = registry.create(name)
                result = await ingest_source(source, store, pages=1, resume=True)
            except Exception as exc:
                source_stats.errors += 1
                source_stats.last_error = f"{type(exc).__name__}: {exc}"[:1000]
                if fail_fast:
                    raise
                continue

            source_stats.runs += 1
            source_stats.jobs_seen += result.stats.jobs_seen
            source_stats.jobs_inserted += result.stats.jobs_inserted
            source_stats.jobs_updated += result.stats.jobs_updated
            source_stats.companies_created += result.stats.companies_created
            if result.next_cursor is None:
                source_stats.exhausted = True

            if _count(store, "job_postings") >= target_jobs:
                stopped_reason = "target_reached"
                break

        jobs_after_round = _count(store, "job_postings")
        if jobs_after_round >= target_jobs:
            stopped_reason = "target_reached"
            break
        if active_this_round == 0 or all(item.exhausted for item in stats.values()):
            stopped_reason = "sources_exhausted"
            break

    jobs_after = _count(store, "job_postings")
    return BenchmarkCollectionResult(
        target_jobs=target_jobs,
        jobs_before=jobs_before,
        jobs_after=jobs_after,
        companies_after=_count(store, "companies"),
        rounds=rounds,
        target_reached=jobs_after >= target_jobs,
        stopped_reason=stopped_reason,
        sources=stats,
    )


def _normalize_sources(source_names: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in source_names:
        name = value.strip().lower()
        if not name or name in seen:
            continue
        seen.add(name)
        normalized.append(name)
    return normalized


def _count(store: SQLiteStore, table: str) -> int:
    if table not in {"job_postings", "companies"}:
        raise ValueError(f"unsupported benchmark count table: {table}")
    with store.connect() as connection:
        row = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
    return int(row[0]) if row is not None else 0
