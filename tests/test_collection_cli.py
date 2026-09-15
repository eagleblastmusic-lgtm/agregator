import json

from typer.testing import CliRunner

from agregator.collection_cli import app

runner = CliRunner()


def test_collection_sources_exposes_access_policy_without_credentials() -> None:
    result = runner.invoke(app, ["sources"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    by_name = {item["name"]: item for item in payload}

    assert by_name["jooble"]["access_mode"] == "partner_api"
    assert by_name["jooble"]["experimental"] is False
    assert by_name["epraca"]["access_mode"] == "official_partner_feed"
    assert by_name["olx"]["access_mode"] == "public_web_endpoint"
    assert by_name["olx"]["experimental"] is True
    assert "revalidate" in (by_name["olx"]["notes"] or "")


def test_collection_preflight_does_not_require_search_provider(monkeypatch) -> None:
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
    monkeypatch.setenv("JOOBLE_API_KEY", "test-key")

    result = runner.invoke(
        app,
        ["preflight", "--sources", "jooble", "--strict"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["search_provider_required"] is False
    assert payload["search_provider_ready"] is False
    assert payload["ready"] is True


def test_collection_preflight_keeps_experimental_source_guard(monkeypatch) -> None:
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)

    result = runner.invoke(
        app,
        ["preflight", "--sources", "olx", "--strict"],
    )

    assert result.exit_code == 2
    payload = json.loads(result.output)
    assert payload["ready"] is False
    assert "experimental_source_not_acknowledged:olx" in payload["blockers"]
