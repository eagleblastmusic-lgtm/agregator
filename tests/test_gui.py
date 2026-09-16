from pathlib import Path

import pytest

from agregator.gui import RunConfig, build_run_command, validate_run_config


def _config(**overrides: object) -> RunConfig:
    values = {
        "sources": ("aplikuj", "ngo"),
        "pages_per_source": 5,
        "enrichment_limit": 300,
        "database_path": Path("wyniki/production.sqlite3"),
        "output_path": Path("wyniki/Faro_Firmy_Kontakt.xlsx"),
        "fresh_sources": True,
        "refresh_enrichment": False,
        "strict": True,
    }
    values.update(overrides)
    return RunConfig(**values)  # type: ignore[arg-type]


def test_build_run_command_contains_gui_selection() -> None:
    command = build_run_command(_config(), python_executable="python")

    assert command[:4] == ["python", "-m", "agregator.workflow_cli", "run"]
    assert command[command.index("--sources") + 1] == "aplikuj,ngo"
    assert command[command.index("--pages-per-source") + 1] == "5"
    assert command[command.index("--enrichment-limit") + 1] == "300"
    assert "--fresh-sources" in command
    assert "--strict" in command
    assert "--refresh-enrichment" not in command


def test_build_run_command_supports_refresh_without_strict() -> None:
    command = build_run_command(
        _config(fresh_sources=False, refresh_enrichment=True, strict=False),
        python_executable="python",
    )

    assert "--fresh-sources" not in command
    assert "--refresh-enrichment" in command
    assert "--strict" not in command


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"sources": ()}, "co najmniej jedno źródło"),
        ({"pages_per_source": 0}, "1–1000"),
        ({"enrichment_limit": 501}, "1–500"),
        ({"output_path": Path("wyniki/faro.csv")}, ".xlsx"),
        ({"database_path": Path("wyniki/faro.txt")}, ".sqlite3"),
    ],
)
def test_validate_run_config_rejects_invalid_values(
    overrides: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        validate_run_config(_config(**overrides))
