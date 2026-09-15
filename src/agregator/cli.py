from __future__ import annotations

import asyncio
import json
import os
from dataclasses import asdict

import typer

from .crawler import WebsiteCrawler
from .enrich import enrich_pending_companies
from .importers import load_jobs_csv
from .ingest import ingest_source
from .pipeline import EmployerDiscoveryPipeline
from .search import BraveSearchProvider
from .sources import default_registry
from .storage import SQLiteStore

app = typer.Typer(help="Faro Employer Discovery Engine")


def _crawler() -> WebsiteCrawler:
    return WebsiteCrawler(
        user_agent=os.getenv("AGREGATOR_USER_AGENT", "FaroEmployerDiscovery/0.1"),
        max_pages=int(os.getenv("AGREGATOR_MAX_PAGES", "12")),
        request_delay=float(os.getenv("AGREGATOR_REQUEST_DELAY", "0.8")),
    )


def _search_provider() -> BraveSearchProvider:
    api_key = os.getenv("BRAVE_SEARCH_API_KEY", "")
    if not api_key:
        raise typer.BadParameter("Ustaw BRAVE_SEARCH_API_KEY przed użyciem wyszukiwania")
    return BraveSearchProvider(api_key)


async def _collect(
    source_name: str,
    db: str,
    pages: int,
    fresh: bool,
) -> dict[str, object]:
    registry = default_registry()
    try:
        source = registry.create(source_name)
    except KeyError as exc:
        raise typer.BadParameter(str(exc)) from exc

    store = SQLiteStore(db)
    result = await ingest_source(source, store, pages=pages, resume=not fresh)
    return {
        "run_id": result.run_id,
        "source": result.source,
        "pages": result.pages,
        "next_cursor": result.next_cursor,
        "jobs_seen": result.stats.jobs_seen,
        "jobs_inserted": result.stats.jobs_inserted,
        "jobs_updated": result.stats.jobs_updated,
        "companies_created": result.stats.companies_created,
        "db": db,
    }


@app.command("scan-url")
def scan_url(
    company: str = typer.Option(..., "--company"),
    url: str = typer.Option(..., "--url"),
    city: str | None = typer.Option(None, "--city"),
) -> None:
    async def run() -> None:
        pipeline = EmployerDiscoveryPipeline(crawler=_crawler())
        result = await pipeline.scan_known_website(company, url, city)
        typer.echo(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))

    asyncio.run(run())


@app.command("discover")
def discover(
    company: str = typer.Option(..., "--company"),
    city: str | None = typer.Option(None, "--city"),
) -> None:
    async def run() -> None:
        pipeline = EmployerDiscoveryPipeline(
            crawler=_crawler(),
            search_provider=_search_provider(),
        )
        result = await pipeline.discover(company, city)
        typer.echo(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))

    asyncio.run(run())


@app.command("db-init")
def db_init(
    db: str = typer.Option("agregator.sqlite3", "--db"),
) -> None:
    store = SQLiteStore(db)
    store.init_schema()
    typer.echo(f"Baza gotowa: {db}")


@app.command("sources")
def sources() -> None:
    typer.echo(json.dumps(default_registry().names(), ensure_ascii=False, indent=2))


@app.command("collect")
def collect_source(
    source: str = typer.Option(..., "--source"),
    db: str = typer.Option("agregator.sqlite3", "--db"),
    pages: int = typer.Option(1, "--pages", min=1, max=20),
    fresh: bool = typer.Option(False, "--fresh", help="Zacznij od początku źródła"),
) -> None:
    result = asyncio.run(_collect(source, db, pages, fresh))
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


@app.command("collect-olx")
def collect_olx(
    db: str = typer.Option("agregator.sqlite3", "--db"),
    pages: int = typer.Option(1, "--pages", min=1, max=20),
    fresh: bool = typer.Option(False, "--fresh", help="Zacznij od offsetu 0"),
) -> None:
    result = asyncio.run(_collect("olx", db, pages, fresh))
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


@app.command("runs")
def runs(
    db: str = typer.Option("agregator.sqlite3", "--db"),
    source: str | None = typer.Option(None, "--source"),
    limit: int = typer.Option(50, "--limit", min=1, max=1000),
) -> None:
    store = SQLiteStore(db)
    store.init_schema()
    typer.echo(
        json.dumps(
            store.list_source_runs(source=source, limit=limit),
            ensure_ascii=False,
            indent=2,
        )
    )


@app.command("import-csv")
def import_csv(
    path: str = typer.Option(..., "--path"),
    db: str = typer.Option("agregator.sqlite3", "--db"),
    default_source: str = typer.Option("csv", "--default-source"),
) -> None:
    store = SQLiteStore(db)
    store.init_schema()
    jobs = load_jobs_csv(path, default_source=default_source)
    stats = store.upsert_jobs(jobs)
    typer.echo(json.dumps(asdict(stats), ensure_ascii=False, indent=2))


@app.command("enrich-db")
def enrich_db(
    db: str = typer.Option("agregator.sqlite3", "--db"),
    limit: int = typer.Option(20, "--limit", min=1, max=500),
    min_identity_confidence: float = typer.Option(0.7, "--min-identity-confidence"),
    refresh: bool = typer.Option(False, "--refresh"),
) -> None:
    async def run() -> None:
        store = SQLiteStore(db)
        pipeline = EmployerDiscoveryPipeline(
            crawler=_crawler(),
            search_provider=_search_provider(),
        )
        stats = await enrich_pending_companies(
            store,
            pipeline,
            limit=limit,
            min_identity_confidence=min_identity_confidence,
            refresh=refresh,
        )
        typer.echo(json.dumps(asdict(stats), ensure_ascii=False, indent=2))

    asyncio.run(run())


@app.command("companies")
def companies(
    db: str = typer.Option("agregator.sqlite3", "--db"),
    limit: int = typer.Option(50, "--limit", min=1, max=1000),
) -> None:
    store = SQLiteStore(db)
    store.init_schema()
    typer.echo(json.dumps(store.list_companies(limit), ensure_ascii=False, indent=2))


@app.command("green")
def green(
    db: str = typer.Option("agregator.sqlite3", "--db"),
    limit: int = typer.Option(100, "--limit", min=1, max=5000),
) -> None:
    store = SQLiteStore(db)
    store.init_schema()
    typer.echo(json.dumps(store.list_green_channels(limit), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    app()
