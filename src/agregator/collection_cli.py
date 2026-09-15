from __future__ import annotations

import asyncio
import json

import typer

from .benchmark_preflight import build_benchmark_preflight
from .collection_workspace import run_collection_workspace
from .sources import default_registry
from .storage import SQLiteStore

app = typer.Typer(help="Faro source collection smoke/benchmark runner")
_DEFAULT_SOURCES = "jooble,adzuna"


def _source_names(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


@app.command("sources")
def sources() -> None:
    """Show source access policy without creating API clients or reading secrets."""

    payload = [
        {
            "name": item.name,
            "access_mode": item.access_mode,
            "experimental": item.experimental,
            "notes": item.notes,
        }
        for item in default_registry().registrations()
    ]
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))


@app.command("preflight")
def preflight(
    sources: str = typer.Option(_DEFAULT_SOURCES, "--sources"),
    allow_experimental_sources: bool = typer.Option(
        False,
        "--allow-experimental-sources",
        help="Jawnie zezwól na źródła oznaczone jako experimental",
    ),
    strict: bool = typer.Option(False, "--strict"),
) -> None:
    result = build_benchmark_preflight(
        default_registry(),
        _source_names(sources),
        search_provider_ready=False,
        require_search_provider=False,
        allow_experimental_sources=allow_experimental_sources,
    )
    typer.echo(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    if strict and not result.ready:
        raise typer.Exit(code=2)


@app.command("run")
def run(
    output_dir: str = typer.Option("benchmark/collection", "--output-dir"),
    db: str = typer.Option("benchmark/collection.sqlite3", "--db"),
    sources: str = typer.Option(_DEFAULT_SOURCES, "--sources"),
    target_jobs: int = typer.Option(100, "--target-jobs", min=1, max=1_000_000),
    max_rounds: int = typer.Option(20, "--max-rounds", min=1, max=10_000),
    max_errors_per_source: int = typer.Option(
        3,
        "--max-errors-per-source",
        min=1,
        max=100,
    ),
    fresh_collection: bool = typer.Option(False, "--fresh-collection"),
    fail_fast_collection: bool = typer.Option(False, "--fail-fast-collection"),
    allow_experimental_sources: bool = typer.Option(
        False,
        "--allow-experimental-sources",
    ),
    strict: bool = typer.Option(
        False,
        "--strict",
        help=(
            "Kod wyjścia 2, jeśli target ofert nie został osiągnięty albo któreś "
            "żądane źródło nie zostało skutecznie przećwiczone"
        ),
    ),
) -> None:
    source_names = _source_names(sources)
    registry = default_registry()
    preflight_result = build_benchmark_preflight(
        registry,
        source_names,
        search_provider_ready=False,
        require_search_provider=False,
        allow_experimental_sources=allow_experimental_sources,
    )
    if not preflight_result.ready:
        blockers = ", ".join(preflight_result.blockers) or "unknown"
        raise typer.BadParameter(f"collection preflight blockers: {blockers}")

    try:
        result = asyncio.run(
            run_collection_workspace(
                SQLiteStore(db),
                registry,
                source_names,
                output_dir,
                preflight=preflight_result,
                target_jobs=target_jobs,
                max_rounds=max_rounds,
                max_errors_per_source=max_errors_per_source,
                fresh_collection=fresh_collection,
                fail_fast_collection=fail_fast_collection,
            )
        )
    except (KeyError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc

    typer.echo(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    if strict and not result.ready_for_full_enrichment_benchmark:
        raise typer.Exit(code=2)


if __name__ == "__main__":
    app()
