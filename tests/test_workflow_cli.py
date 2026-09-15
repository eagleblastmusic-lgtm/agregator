from click.utils import strip_ansi
from typer.testing import CliRunner

from agregator.workflow_cli import app


def test_workflow_cli_keeps_run_subcommand() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["run", "--help"])
    output = strip_ansi(result.output)

    assert result.exit_code == 0, result.output
    assert "--sources" in output
    assert "--enrichment-limit" in output
