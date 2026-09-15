from __future__ import annotations

import asyncio
import json
import os
from dataclasses import asdict

import typer

from .catalog import catalog_summary, filter_catalog, load_source_catalog
from .crawler import WebsiteCrawler
from .dataset_export import export_dataset_bundle
from .enrich import enrich_pending_companies
from .ground_truth import evaluate_company_resolution_csv, export_ground_truth_template
from .importers import load_jobs_csv
from .ingest import IngestResult, ingest_source
from .pipeline import EmployerDiscoveryPipeline
from .reporting import build_benchmark_report, export_green_channels
from .resolution_review import build_resolution_review_queue
from .search import BraveSearchProvider
from .sources import default_registry
from .sources.adzuna import AdzunaApiSource
from .sources.jooble import JoobleApiSource
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


def _source_result(result: IngestResult, db: str) -> dict[str, object]:
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


async def _collect(
    source_name: str,
    db: str,
    pages: int,
    fresh: bool,
) -> dict[str, object]:
    registry = default_registry()
    try:
        source = registry.create(source_name)
    except (KeyError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc

    store = SQLiteStore(db)
    result = await ingest_source(source, store, pages=pages, resume=not fresh)
    return _source_result(result, db)


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


@app.command("catalog")
def catalog(
    priority: str | None = typer.Option(None, "--priority"),
    implemented_only: bool = typer.Option(False, "--implemented-only"),
    pending_only: bool = typer.Option(False, "--pending-only"),
    summary: bool = typer.Option(False, "--summary"),
) -> None:
    if implemented_only and pending_only:
        raise typer.BadParameter("Wybierz tylko --implemented-only albo --pending-only")

    entries = load_source_catalog()
    if summary:
        typer.echo(json.dumps(catalog_summary(entries), ensure_ascii=False, indent=2))
        return

    implemented: bool | None = None
    if implemented_only:
        implemented = True
    elif pending_only:
        implemented = False

    filtered = filter_catalog(
        entries,
        priority=priority,
        implemented=implemented,
    )
    typer.echo(
        json.dumps(
            [entry.to_dict() for entry in filtered],
            ensure_ascii=False,
            indent=2,
        )
    )


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


@app.command("collect-jooble")
def collect_jooble(
    keywords: str = typer.Option(..., "--keywords"),
    location: str = typer.Option(..., "--location"),
    db: str = typer.Option("agregator.sqlite3", "--db"),
    pages: int = typer.Option(1, "--pages", min=1, max=20),
    result_on_page: int = typer.Option(20, "--result-on-page", min=1, max=100),
    radius: str | None = typer.Option(None, "--radius"),
    fresh: bool = typer.Option(False, "--fresh"),
) -> None:
    api_key = os.getenv("JOOBLE_API_KEY", "")
    if not api_key:
        raise typer.BadParameter("Ustaw JOOBLE_API_KEY przed użyciem collect-jooble")

    async def run() -> None:
        store = SQLiteStore(db)
        source = JoobleApiSource(
            api_key,
            keywords=keywords,
            location=location,
            result_on_page=result_on_page,
            radius=radius,
        )
        result = await ingest_source(source, store, pages=pages, resume=not fresh)
        typer.echo(json.dumps(_source_result(result, db), ensure_ascii=False, indent=2))

    asyncio.run(run())


@app.command("collect-adzuna")
def collect_adzuna(
    db: str = typer.Option("agregator.sqlite3", "--db"),
    pages: int = typer.Option(1, "--pages", min=1, max=20),
    what: str | None = typer.Option(None, "--what"),
    where: str | None = typer.Option(None, "--where"),
    country: str = typer.Option("pl", "--country"),
    results_per_page: int = typer.Option(20, "--results-per-page", min=1, max=50),
    fresh: bool = typer.Option(False, "--fresh"),
) -> None:
    app_id = os.getenv("ADZUNA_APP_ID", "")
    app_key = os.getenv("ADZUNA_APP_KEY", "")
    if not app_id or not app_key:
        raise typer.BadParameter("Ustaw ADZUNA_APP_ID i ADZUNA_APP_KEY")

    async def run() -> None:
        store = SQLiteStore(db)
        source = AdzunaApiSource(
            app_id,
            app_key,
            country=country,
            what=what,
            where=where,
            results_per_page=results_per_page,
        )
        result = await ingest_source(source, store, pages=pages, resume=not fresh)
        typer.echo(json.dumps(_source_result(result, db), ensure_ascii=False, indent=2))

    asyncio.run(run())


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


@app.command("benchmark")
def benchmark(
    db: str = typer.Option("agregator.sqlite3", "--db"),
    high_confidence_threshold: float = typer.Option(0.7, "--high-confidence-threshold"),
) -> None:
    store = SQLiteStore(db)
    report = build_benchmark_report(
        store,
        high_confidence_threshold=high_confidence_threshold,
    )
    typer.echo(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))


@app.command("resolution-review")
def resolution_review(
    db: str = typer.Option("agregator.sqlite3", "--db"),
    min_score: float = typer.Option(0.82, "--min-score", min=0.0, max=1.0),
    limit: int = typer.Option(100, "--limit", min=1, max=10_000),
    company_limit: int = typer.Option(5000, "--company-limit", min=1, max=100_000),
) -> None:
    store = SQLiteStore(db)
    candidates = build_resolution_review_queue(
        store,
        min_score=min_score,
        limit=limit,
        company_limit=company_limit,
    )
    typer.echo(
        json.dumps(
            [candidate.to_dict() for candidate in candidates],
            ensure_ascii=False,
            indent=2,
        )
    )


@app.command("export-ground-truth")
def export_ground_truth(
    output: str = typer.Option(..., "--output"),
    db: str = typer.Option("agregator.sqlite3", "--db"),
    limit: int = typer.Option(1000, "--limit", min=1, max=100_000),
) -> None:
    store = SQLiteStore(db)
    path = export_ground_truth_template(store, output, limit=limit)
    typer.echo(str(path))


@app.command("evaluate-resolution")
def evaluate_resolution(
    path: str = typer.Option(..., "--path"),
    db: str = typer.Option("agregator.sqlite3", "--db"),
) -> None:
    store = SQLiteStore(db)
    try:
        report = evaluate_company_resolution_csv(store, path)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))


@app.command("export-green")
def export_green(
    output: str = typer.Option(..., "--output"),
    db: str = typer.Option("agregator.sqlite3", "--db"),
    format: str | None = typer.Option(None, "--format"),
) -> None:
    store = SQLiteStore(db)
    try:
        path = export_green_channels(store, output, format=format)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(str(path))


@app.command("export-dataset")
def export_dataset(
    output_dir: str = typer.Option(..., "--output-dir"),
    db: str = typer.Option("agregator.sqlite3", "--db"),
) -> None:
    store = SQLiteStore(db)
    result = export_dataset_bundle(store, output_dir)
    typer.echo(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    app()
