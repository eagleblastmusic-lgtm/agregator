from typer.testing import CliRunner

from agregator.workflow_cli import app


def test_workflow_cli_keeps_run_subcommand() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["run", "--help"])

    assert result.exit_code == 0, result.output
