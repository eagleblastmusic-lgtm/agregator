from __future__ import annotations

import asyncio
import json
import os

import typer

from .benchmark_evaluation import evaluate_labeled_benchmark
from .benchmark_pipeline import run_benchmark_pipeline
from .benchmark_preflight import build_benchmark_preflight
from .crawler import WebsiteCrawler
from .label_sampling import DEFAULT_SAMPLING_SEED
from .label_status import build_label_bundle_status
from .pipeline import EmployerDiscoveryPipeline
from .search import BraveSearchProvider
from .sources import default_registry
from .storage import SQLiteStore

app = typer.Typer(help="Faro controlled benchmark runner")


def _crawler() -> WebsiteCrawler:
    return WebsiteCrawler(
        user_agent=os.getenv("AGREGATOR_USER_AGENT", "FaroEmployerDiscovery/0.1"),
        max_pages=int(os.getenv("AGREGATOR_MAX_PAGES", "12")),
        request_delay=float(os.getenv("AGREGATOR_REQUEST_DELAY", "0.8")),
    )


def _search_provider() -> BraveSearchProvider:
    api_key = os.getenv("BRAVE_SEARCH_API_KEY", "")
    if not api_key:
        raise typer.BadParameter(
            "Ustaw BRAVE_SEARCH_API_KEY przed uruchomieniem pełnego benchmarku"
        )
    return BraveSearchProvider(api_key)


def _source_names(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


@app.command("preflight")
def preflight(
    sources: str = typer.Option("olx,jooble,adzuna", "--sources"),
    strict: bool = typer.Option(
        False,
        "--strict",
        help="Kod wyjścia 2, jeśli search lub którekolwiek żądane źródło nie jest gotowe",
    ),
) -> None:
    result = build_benchmark_preflight(
        default_registry(),
        _source_names(sources),
        search_provider_ready=bool(os.getenv("BRAVE_SEARCH_API_KEY", "")),
    )
    typer.echo(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    if strict and not result.ready:
        raise typer.Exit(code=2)


@app.command("run")
def run(
    output_dir: str = typer.Option("benchmark/run", "--output-dir"),
    db: str = typer.Option("benchmark/benchmark.sqlite3", "--db"),
    sources: str = typer.Option("olx,jooble,adzuna", "--sources"),
    target_jobs: int = typer.Option(1000, "--target-jobs", min=1, max=1_000_000),
    max_rounds: int = typer.Option(100, "--max-rounds", min=1, max=10_000),
    max_errors_per_source: int = typer.Option(
        3,
        "--max-errors-per-source",
        min=1,
        max=100,
    ),
    fresh_collection: bool = typer.Option(False, "--fresh-collection"),
    fail_fast_collection: bool = typer.Option(False, "--fail-fast-collection"),
    enrichment_batch_size: int = typer.Option(
        25,
        "--enrichment-batch-size",
        min=1,
        max=500,
    ),
    max_enrichment_companies: int = typer.Option(
        1000,
        "--max-enrichment-companies",
        min=1,
        max=1_000_000,
    ),
    min_identity_confidence: float = typer.Option(
        0.7,
        "--min-identity-confidence",
        min=0.0,
        max=1.0,
    ),
    job_label_limit: int = typer.Option(1000, "--job-label-limit", min=1, max=100_000),
    company_label_limit: int = typer.Option(
        1000,
        "--company-label-limit",
        min=1,
        max=100_000,
    ),
    contact_label_limit: int = typer.Option(
        1000,
        "--contact-label-limit",
        min=1,
        max=100_000,
    ),
    label_sampling_seed: str = typer.Option(
        DEFAULT_SAMPLING_SEED,
        "--label-sampling-seed",
        help="Deterministyczny seed wyboru rekordów do ręcznego ground truth",
    ),
    strict: bool = typer.Option(
        False,
        "--strict",
        help="Kod wyjścia 2, jeśli target lub pełny enrichment nie są domknięte",
    ),
) -> None:
    source_names = _source_names(sources)
    store = SQLiteStore(db)
    pipeline = EmployerDiscoveryPipeline(
        crawler=_crawler(),
        search_provider=_search_provider(),
    )

    try:
        result = asyncio.run(
            run_benchmark_pipeline(
                store,
                default_registry(),
                pipeline,
                source_names,
                output_dir,
                target_jobs=target_jobs,
                max_rounds=max_rounds,
                max_errors_per_source=max_errors_per_source,
                fresh_collection=fresh_collection,
                fail_fast_collection=fail_fast_collection,
                enrichment_batch_size=enrichment_batch_size,
                max_enrichment_companies=max_enrichment_companies,
                min_identity_confidence=min_identity_confidence,
                job_label_limit=job_label_limit,
                company_label_limit=company_label_limit,
                contact_label_limit=contact_label_limit,
                label_sampling_seed=label_sampling_seed,
            )
        )
    except (KeyError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc

    typer.echo(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    if strict and not result.readiness.ready_for_manual_labeling:
        raise typer.Exit(code=2)


@app.command("status")
def status(
    label_dir: str = typer.Option("benchmark/run/labels", "--label-dir"),
    strict: bool = typer.Option(
        False,
        "--strict",
        help="Kod wyjścia 2, dopóki wszystkie trzy pliki ground truth nie są kompletne",
    ),
) -> None:
    result = build_label_bundle_status(label_dir)
    typer.echo(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    if strict and not result.ready_for_quality_gate:
        raise typer.Exit(code=2)


@app.command("evaluate")
def evaluate(
    db: str = typer.Option("benchmark/benchmark.sqlite3", "--db"),
    label_dir: str = typer.Option("benchmark/run/labels", "--label-dir"),
    min_resolution_f1: float = typer.Option(0.95, "--min-resolution-f1", min=0.0, max=1.0),
    min_website_f1: float = typer.Option(0.95, "--min-website-f1", min=0.0, max=1.0),
    min_contact_macro_f1: float = typer.Option(
        0.90,
        "--min-contact-macro-f1",
        min=0.0,
        max=1.0,
    ),
    fail_on_error: bool = typer.Option(False, "--fail-on-error"),
) -> None:
    result = evaluate_labeled_benchmark(
        SQLiteStore(db),
        label_dir,
        min_resolution_f1=min_resolution_f1,
        min_website_f1=min_website_f1,
        min_contact_macro_f1=min_contact_macro_f1,
    )
    typer.echo(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    if not result.evaluated:
        raise typer.Exit(code=2)
    if fail_on_error and not result.passed:
        raise typer.Exit(code=2)


if __name__ == "__main__":
    app()
