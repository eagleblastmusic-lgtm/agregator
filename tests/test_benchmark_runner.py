from pathlib import Path

from agregator.benchmark_runner import collect_benchmark
from agregator.models import JobPosting
from agregator.sources.base import SourceBatch
from agregator.sources.registry import SourceRegistry
from agregator.storage import SQLiteStore


class FakeSource:
    def __init__(self, name: str, pages: int = 3) -> None:
        self.name = name
        self.pages = pages

    async def collect(self, cursor: str | None = None) -> SourceBatch:
        page = int(cursor or "0")
        if page >= self.pages:
            return SourceBatch(jobs=[], next_cursor=None)

        jobs = [
            JobPosting(
                source=self.name,
                source_id=f"{page}-{index}",
                url=f"https://jobs.test/{self.name}/{page}/{index}",
                title=f"Job {page}-{index}",
                company_name=f"Company {self.name}-{page}-{index}",
                company_name_source="fixture",
                company_name_confidence=0.95,
                city="Gdynia",
            )
            for index in range(2)
        ]
        next_cursor = str(page + 1) if page + 1 < self.pages else None
        return SourceBatch(jobs=jobs, next_cursor=next_cursor)


async def test_benchmark_collector_round_robins_until_target(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "benchmark.sqlite3")
    registry = SourceRegistry()
    registry.register("a", lambda: FakeSource("a"))
    registry.register("b", lambda: FakeSource("b"))

    result = await collect_benchmark(
        store,
        registry,
        ["a", "b"],
        target_jobs=5,
        max_rounds=10,
    )

    assert result.target_reached is True
    assert result.stopped_reason == "target_reached"
    assert result.jobs_before == 0
    assert result.jobs_after == 6
    assert result.rounds == 2
    assert result.sources["a"].runs == 2
    assert result.sources["a"].jobs_inserted == 4
    assert result.sources["b"].runs == 1
    assert result.sources["b"].jobs_inserted == 2


async def test_benchmark_collector_stops_when_sources_are_exhausted(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "exhausted.sqlite3")
    registry = SourceRegistry()
    registry.register("a", lambda: FakeSource("a", pages=1))

    result = await collect_benchmark(
        store,
        registry,
        ["a"],
        target_jobs=100,
        max_rounds=10,
    )

    assert result.target_reached is False
    assert result.stopped_reason == "sources_exhausted"
    assert result.jobs_after == 2
    assert result.sources["a"].exhausted is True
