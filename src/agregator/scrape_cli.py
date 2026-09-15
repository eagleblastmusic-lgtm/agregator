from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from typing import Any

import typer

from .ingest import ingest_source
from .sources import default_registry
from .sources.registry import SourceRegistration, SourceRegistry
from .storage import SQLiteStore

app = typer.Typer(
    help=(
        "Faro public job-board scraper. Collects public pages/feeds into the append-only "
        "source observation layer without requiring partner API credentials."
    )
)

_PUBLIC_ACCESS_MODES = {
    "public_html",
    "public_sitemap_html",
    "public_web_endpoint",
    "public_xml",
    "official_public_feed",
}


def _public_registrations(registry: SourceRegistry) -> list[SourceRegistration]:
    return [
        registration
        for registration in registry.registrations()
        if registration.access_mode in _PUBLIC_ACCESS_MODES
    ]


def _resolve_source_names(registry: SourceRegistry, value: str) -> list[str]:
    public = _public_registrations(registry)
    public_names = {item.name for item in public}
    requested = [item.strip().lower() for item in value.split(",") if item.strip()]
    if not requested or requested == ["all"]:
        return [item.name for item in public]

    unknown = sorted(set(requested) - set(registry.names()))
    if unknown:
        raise typer.BadParameter("Nieznane źródła: " + ", ".join(unknown))

    not_public = sorted(set(requested) - public_names)
    if not_public:
        raise typer.BadParameter(
            "agregator-scrape obsługuje tylko publiczne adaptery scraper/feed: "
            + ", ".join(not_public)
        )
    return list(dict.fromkeys(requested))


@app.command("sources")
def sources() -> None:
    """List scraper/feed sources that do not require partner API credentials."""

    registry = default_registry()
    payload = [
        {
            "name": item.name,
            "access_mode": item.access_mode,
            "experimental": item.experimental,
            "notes": item.notes,
        }
        for item in _public_registrations(registry)
    ]
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))


@app.command("run")
def run(
    sources: str = typer.Option("all", "--sources"),
    db: str = typer.Option("agregator.sqlite3", "--db"),
    pages_per_source: int = typer.Option(
        1,
        "--pages-per-source",
        min=1,
        max=1000,
        help="Liczba stron/chunków do pobrania z każdego źródła w tym uruchomieniu.",
    ),
    fresh: bool = typer.Option(
        False,
        "--fresh",
        help="Zacznij każdy wybrany scraper od początku zamiast wznawiać cursor.",
    ),
    fail_fast: bool = typer.Option(
        False,
        "--fail-fast",
        help="Przerwij po pierwszym błędzie źródła.",
    ),
    strict: bool = typer.Option(
        False,
        "--strict",
        help="Zwróć kod 2, jeżeli którekolwiek wybrane źródło zakończy się błędem.",
    ),
) -> None:
    result = asyncio.run(
        _run_scrapers(
            registry=default_registry(),
            source_value=sources,
            db=db,
            pages_per_source=pages_per_source,
            fresh=fresh,
            fail_fast=fail_fast,
        )
    )
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))
    if strict and result["failed_sources"]:
        raise typer.Exit(code=2)


async def _run_scrapers(
    *,
    registry: SourceRegistry,
    source_value: str,
    db: str,
    pages_per_source: int,
    fresh: bool,
    fail_fast: bool,
) -> dict[str, Any]:
    source_names = _resolve_source_names(registry, source_value)
    store = SQLiteStore(db)
    store.init_schema()
    results: list[dict[str, Any]] = []
    failed: list[str] = []

    for source_name in source_names:
        registration = registry.describe(source_name)
        try:
            source = registry.create(source_name)
            ingest = await ingest_source(
                source,
                store,
                pages=pages_per_source,
                resume=not fresh,
            )
            results.append(
                {
                    "source": source_name,
                    "status": "success",
                    "access_mode": registration.access_mode,
                    "experimental": registration.experimental,
                    **asdict(ingest.stats),
                    "pages": ingest.pages,
                    "next_cursor": ingest.next_cursor,
                    "run_id": ingest.run_id,
                }
            )
        except Exception as exc:
            failed.append(source_name)
            results.append(
                {
                    "source": source_name,
                    "status": "failed",
                    "access_mode": registration.access_mode,
                    "experimental": registration.experimental,
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:1000],
                }
            )
            if fail_fast:
                break

    return {
        "db": db,
        "requested_sources": source_names,
        "successful_sources": [
            item["source"] for item in results if item["status"] == "success"
        ],
        "failed_sources": failed,
        "results": results,
        "raw_observation_policy": "append_only_no_cross_source_deduplication",
    }


if __name__ == "__main__":
    app()
