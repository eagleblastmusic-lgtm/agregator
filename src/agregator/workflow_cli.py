from __future__ import annotations

import asyncio
import json
import os

import typer

from .crawler import WebsiteCrawler
from .pipeline import EmployerDiscoveryPipeline
from .search import BraveSearchProvider
from .workflow import run_end_to_end_workflow

app = typer.Typer(
    help=(
        "Faro end-to-end runner: job sources -> companies -> official websites -> "
        "B2B contact classification -> final Excel."
    )
)


@app.callback()
def main() -> None:
    """Run resumable Faro end-to-end workflows."""


def _crawler_from_env() -> WebsiteCrawler:
    return WebsiteCrawler(
        user_agent=os.getenv("AGREGATOR_USER_AGENT", "FaroEmployerDiscovery/0.1"),
        max_pages=int(os.getenv("AGREGATOR_MAX_PAGES", "12")),
        request_delay=float(os.getenv("AGREGATOR_REQUEST_DELAY", "0.8")),
    )


def _search_from_env() -> BraveSearchProvider | None:
    api_key = os.getenv("BRAVE_SEARCH_API_KEY", "").strip()
    return BraveSearchProvider(api_key) if api_key else None


@app.command("run")
def run(
    sources: str = typer.Option(
        "all",
        "--sources",
        help=(
            "Lista źródeł oddzielona przecinkami albo 'all'. Przy 'all' adaptery wymagające "
            "brakujących poświadczeń są pomijane i raportowane jako skipped."
        ),
    ),
    db: str = typer.Option("agregator.sqlite3", "--db"),
    output: str = typer.Option("export/faro_firmy_kontakt.xlsx", "--output"),
    pages_per_source: int = typer.Option(
        1,
        "--pages-per-source",
        min=1,
        max=1000,
    ),
    enrichment_limit: int = typer.Option(
        100,
        "--enrichment-limit",
        min=1,
        max=500,
        help="Maksymalna liczba jeszcze niewzbogaconych firm analizowanych w tym przebiegu.",
    ),
    min_identity_confidence: float = typer.Option(
        0.7,
        "--min-identity-confidence",
        min=0.0,
        max=1.0,
    ),
    fresh_sources: bool = typer.Option(
        False,
        "--fresh-sources",
        help="Zignoruj zapisane cursory i zacznij wybrane źródła od początku.",
    ),
    refresh_enrichment: bool = typer.Option(
        False,
        "--refresh-enrichment",
        help="Ponownie analizuj także firmy wcześniej wzbogacone.",
    ),
    fail_fast: bool = typer.Option(
        False,
        "--fail-fast",
        help="Przerwij zbieranie po pierwszym błędzie źródła; enrichment i eksport nadal wykonaj.",
    ),
    strict: bool = typer.Option(
        False,
        "--strict",
        help="Zwróć kod 2, jeżeli co najmniej jedno uruchomione źródło zakończy się błędem.",
    ),
) -> None:
    pipeline = EmployerDiscoveryPipeline(
        crawler=_crawler_from_env(),
        search_provider=_search_from_env(),
    )
    try:
        result = asyncio.run(
            run_end_to_end_workflow(
                db=db,
                output=output,
                pipeline=pipeline,
                sources=sources,
                pages_per_source=pages_per_source,
                fresh_sources=fresh_sources,
                fail_fast=fail_fast,
                enrichment_limit=enrichment_limit,
                min_identity_confidence=min_identity_confidence,
                refresh_enrichment=refresh_enrichment,
            )
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    typer.echo(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    if strict and result.failed_sources:
        raise typer.Exit(code=2)


if __name__ == "__main__":
    app()
