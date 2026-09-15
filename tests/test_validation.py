from pathlib import Path

from typer.testing import CliRunner

from agregator.models import JobPosting
from agregator.sources.base import SourceBatch
from agregator.sources.registry import SourceRegistry
from agregator.storage import SQLiteStore, UpsertStats
from agregator.validation import build_validation_report, render_validation_markdown
from agregator.validation_cli import app


class AlphaSource:
    name = "alpha"

    async def collect(self, cursor: str | None = None) -> SourceBatch:
        return SourceBatch(jobs=[], next_cursor=None)


class BetaSource:
    name = "beta"

    async def collect(self, cursor: str | None = None) -> SourceBatch:
        return SourceBatch(jobs=[], next_cursor=None)


def test_validation_report_covers_all_implemented_sources(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "validation.sqlite3")
    store.init_schema()
    store.upsert_jobs(
        [
            JobPosting(
                source="alpha",
                source_id="1",
                url="https://jobs.test/1",
                title="Specjalista",
                company_name="ACME Sp. z o.o.",
                company_name_source="alpha.company",
                company_name_confidence=0.95,
                city="Gdańsk",
                description="Opis stanowiska",
            )
        ]
    )

    run_id = store.start_source_run("alpha", cursor_before=None, pages_requested=1)
    store.finish_source_run(
        run_id,
        status="success",
        cursor_after=None,
        pages_processed=1,
        stats=UpsertStats(jobs_seen=1, jobs_inserted=1, companies_created=1),
    )

    registry = SourceRegistry()
    registry.register("alpha", AlphaSource, access_mode="public_html", experimental=True)
    registry.register(
        "beta",
        BetaSource,
        access_mode="partner_api",
        required_env=("BETA_API_KEY",),
    )

    report = build_validation_report(store, registry)

    assert report.implemented_sources == 2
    assert report.exercised_sources == 1
    assert report.sources_with_current_jobs == 1
    assert report.healthy_sources == ["alpha"]
    assert report.failing_sources == []
    assert report.unexercised_sources == ["beta"]
    assert report.sources_without_current_jobs == ["beta"]
    assert report.jobs_total == 1
    assert report.companies_total == 1

    by_source = {item.source: item for item in report.sources}
    alpha = by_source["alpha"]
    assert alpha.current_jobs == 1
    assert alpha.current_companies == 1
    assert alpha.source_health["state"] == "healthy"
    assert alpha.identity_metrics["avg_company_name_confidence"] == 0.95

    beta = by_source["beta"]
    assert beta.current_jobs == 0
    assert beta.source_health["state"] == "unexercised"
    assert beta.required_env == ["BETA_API_KEY"]

    markdown = render_validation_markdown(report)
    assert "# Faro — P10 validation report" in markdown
    assert "| alpha | healthy | 1 | 1 | 1 |" in markdown
    assert "| beta | unexercised | 0 | 0 | 0 |" in markdown


def test_validation_cli_keeps_report_subcommand(tmp_path: Path) -> None:
    runner = CliRunner()
    db = tmp_path / "cli.sqlite3"
    output = tmp_path / "report.json"
    markdown = tmp_path / "report.md"

    result = runner.invoke(
        app,
        [
            "report",
            "--db",
            str(db),
            "--output",
            str(output),
            "--markdown",
            str(markdown),
        ],
    )

    assert result.exit_code == 0, result.output
    assert output.exists()
    assert markdown.exists()
