from __future__ import annotations

import asyncio
import json
import os

import typer

from .crawler import WebsiteCrawler
from .ingest import ingest_source
from .pipeline import EmployerDiscoveryPipeline
from .search import BraveSearchProvider
from .sources.olx import OlxPublicSource
from .storage import SQLiteStore

app = typer.Typer(help="Faro Employer Discovery Engine")


def _crawler() -> WebsiteCrawler:
    return WebsiteCrawler(
        user_agent=os.getenv("AGREGATOR_USER_AGENT", "FaroEmployerDiscovery/0.1"),
        max_pages=int(os.getenv("AGREGATOR_MAX_PAGES", "12")),
        request_delay=float(os.getenv("AGREGATOR_REQUEST_DELAY", "0.8")),
    )


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
    api_key = os.getenv("BRAVE_SEARCH_API_KEY", "")
    if not api_key:
        raise typer.BadParameter("Ustaw BRAVE_SEARCH_API_KEY przed użyciem discover")

    async def run() -> None:
        provider = BraveSearchProvider(api_key)
        pipeline = EmployerDiscoveryPipeline(crawler=_crawler(), search_provider=provider)
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


@app.command("collect-olx")
def collect_olx(
    db: str = typer.Option("agregator.sqlite3", "--db"),
    pages: int = typer.Option(1, "--pages", min=1, max=20),
    fresh: bool = typer.Option(False, "--fresh", help="Zacznij od offsetu 0"),
) -> None:
    async def run() -> None:
        store = SQLiteStore(db)
        source = OlxPublicSource()
        result = await ingest_source(source, store, pages=pages, resume=not fresh)
        typer.echo(
            json.dumps(
                {
                    "source": result.source,
                    "pages": result.pages,
                    "next_cursor": result.next_cursor,
                    "jobs_seen": result.stats.jobs_seen,
                    "jobs_inserted": result.stats.jobs_inserted,
                    "jobs_updated": result.stats.jobs_updated,
                    "companies_created": result.stats.companies_created,
                    "db": db,
                },
                ensure_ascii=False,
                indent=2,
            )
        )

    asyncio.run(run())


@app.command("companies")
def companies(
    db: str = typer.Option("agregator.sqlite3", "--db"),
    limit: int = typer.Option(50, "--limit", min=1, max=1000),
) -> None:
    store = SQLiteStore(db)
    store.init_schema()
    typer.echo(json.dumps(store.list_companies(limit), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    app()
