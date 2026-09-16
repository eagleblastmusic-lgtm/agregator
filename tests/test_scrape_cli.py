import json
from pathlib import Path

from typer.testing import CliRunner

from agregator.models import JobPosting
from agregator.scrape_cli import _resolve_source_names, _run_scrapers, app
from agregator.sources.base import SourceBatch
from agregator.sources.registry import SourceRegistry
from agregator.storage import SQLiteStore

runner = CliRunner()


class _FixtureSource:
    name = "fixture"

    async def collect(self, cursor: str | None = None) -> SourceBatch:
        return SourceBatch(
            jobs=[
                JobPosting(
                    source="fixture",
                    source_id="same-job",
                    url="https://fixture.example/job/1",
                    title="Specjalista",
                    company_name="ACME S.A.",
                    company_name_source="fixture",
                    company_name_confidence=0.99,
                    city="Warszawa",
                    source_payload={"phone": "+48 000 000 000"},
                )
            ],
            next_cursor=None,
        )


class _SecondFixtureSource:
    name = "fixture2"

    async def collect(self, cursor: str | None = None) -> SourceBatch:
        return SourceBatch(
            jobs=[
                JobPosting(
                    source="fixture2",
                    source_id="same-job",
                    url="https://fixture2.example/job/1",
                    title="Specjalista",
                    company_name="ACME S.A.",
                    company_name_source="fixture2",
                    company_name_confidence=0.99,
                    city="Warszawa",
                    source_payload={"website": "https://acme.example"},
                )
            ],
            next_cursor=None,
        )


def test_scrape_sources_lists_only_public_credential_free_adapters() -> None:
    result = runner.invoke(app, ["sources"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    names = {item["name"] for item in payload}
    assert "pracuj" in names
    assert "skillshot" in names
    assert "jooble" not in names
    assert "adzuna" not in names


def test_resolve_all_selects_public_modes_only() -> None:
    registry = SourceRegistry()
    registry.register("web", _FixtureSource, access_mode="public_html")
    registry.register("api", _FixtureSource, access_mode="partner_api")

    assert _resolve_source_names(registry, "all") == ["web"]


def test_resolve_rejects_partner_api_in_scraper_cli() -> None:
    registry = SourceRegistry()
    registry.register("api", _FixtureSource, access_mode="partner_api")

    try:
        _resolve_source_names(registry, "api")
    except Exception as exc:
        assert "publiczne adaptery" in str(exc)
    else:
        raise AssertionError("partner API should not be selectable in scraper CLI")


async def test_scraper_run_preserves_same_company_job_from_two_sources(tmp_path: Path) -> None:
    registry = SourceRegistry()
    registry.register("fixture", _FixtureSource, access_mode="public_html")
    registry.register("fixture2", _SecondFixtureSource, access_mode="public_html")
    db = tmp_path / "scrape.sqlite3"

    result = await _run_scrapers(
        registry=registry,
        source_value="all",
        db=str(db),
        pages_per_source=1,
        fresh=True,
        fail_fast=False,
    )

    assert result["failed_sources"] == []
    assert result["raw_observation_policy"] == (
        "append_only_no_cross_source_deduplication"
    )

    store = SQLiteStore(db)
    with store.connect() as connection:
        raw = connection.execute(
            "SELECT source, payload_json FROM job_posting_observations ORDER BY id"
        ).fetchall()
        current = connection.execute(
            "SELECT source, source_id FROM job_postings ORDER BY source"
        ).fetchall()

    assert [row["source"] for row in raw] == ["fixture", "fixture2"]
    assert len(current) == 2
    assert "+48 000 000 000" in raw[0]["payload_json"]
    assert "https://acme.example" in raw[1]["payload_json"]
