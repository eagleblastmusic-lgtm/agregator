import json

from typer.testing import CliRunner

from agregator.benchmark_cli import app

runner = CliRunner()


def test_preflight_cli_requires_explicit_opt_in_for_olx(monkeypatch) -> None:
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "test-search-key")

    blocked = runner.invoke(
        app,
        ["preflight", "--sources", "olx", "--strict"],
    )
    assert blocked.exit_code == 2
    payload = json.loads(blocked.output)
    assert payload["ready"] is False
    assert payload["sources"][0]["experimental"] is True
    assert "experimental_source_not_acknowledged:olx" in payload["blockers"]

    allowed = runner.invoke(
        app,
        [
            "preflight",
            "--sources",
            "olx",
            "--allow-experimental-sources",
            "--strict",
        ],
    )
    assert allowed.exit_code == 0, allowed.output
    payload = json.loads(allowed.output)
    assert payload["ready"] is True
    assert payload["sources"][0]["access_mode"] == "public_web_endpoint"
    assert payload["warnings"]


def test_run_cli_refuses_experimental_source_before_network(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "test-search-key")

    result = runner.invoke(
        app,
        [
            "run",
            "--sources",
            "olx",
            "--db",
            str(tmp_path / "benchmark.sqlite3"),
            "--output-dir",
            str(tmp_path / "run"),
            "--target-jobs",
            "1",
        ],
    )

    assert result.exit_code != 0
    assert "experimental_source_not_acknowledged:olx" in result.output
