import json
from pathlib import Path

from typer.testing import CliRunner

from agregator.benchmark_cli import app

runner = CliRunner()


def _company_labels(directory: Path) -> None:
    directory.mkdir()
    (directory / "company_resolution_truth.csv").write_text(
        "source,source_id,truth_company_id,company_name_raw,city,url\n"
        "olx,1,,Alpha,Gdańsk,https://jobs.test/1\n",
        encoding="utf-8-sig",
    )


def test_label_next_and_set_round_trip(tmp_path: Path) -> None:
    labels = tmp_path / "labels"
    _company_labels(labels)

    next_result = runner.invoke(
        app,
        [
            "label-next",
            "--kind",
            "company_resolution",
            "--label-dir",
            str(labels),
        ],
    )
    assert next_result.exit_code == 0, next_result.output
    payload = json.loads(next_result.output)
    assert payload["complete"] is False
    assert payload["next"]["row_number"] == 1
    assert "predicted_company_id" not in payload["next"]["row"]

    set_result = runner.invoke(
        app,
        [
            "label-set",
            "--kind",
            "company_resolution",
            "--row",
            "1",
            "--value",
            "truth-alpha",
            "--label-dir",
            str(labels),
        ],
    )
    assert set_result.exit_code == 0, set_result.output
    update = json.loads(set_result.output)
    assert update["new_value"] == "truth-alpha"
    assert update["remaining_rows"] == 0

    complete_result = runner.invoke(
        app,
        [
            "label-next",
            "--kind",
            "company_resolution",
            "--label-dir",
            str(labels),
        ],
    )
    assert complete_result.exit_code == 0, complete_result.output
    assert json.loads(complete_result.output)["complete"] is True


def test_label_set_does_not_expose_accept_prediction_shortcut(tmp_path: Path) -> None:
    labels = tmp_path / "labels"
    _company_labels(labels)

    result = runner.invoke(
        app,
        [
            "label-set",
            "--kind",
            "company_resolution",
            "--row",
            "1",
            "--accept-predicted",
            "--label-dir",
            str(labels),
        ],
    )

    assert result.exit_code != 0
    assert "No such option" in result.output
