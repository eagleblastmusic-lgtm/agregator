from pathlib import Path

import pytest

from agregator.gui import (
    ALL_GUI_SOURCES,
    CREDENTIAL_SOURCES,
    EXPERIMENTAL_SOURCES,
    PUBLIC_CANDIDATE_SOURCES,
    VERIFIED_SOURCES,
    CollectionConfig,
    ContactConfig,
    RunConfig,
    build_collection_command,
    build_contact_command,
    build_run_command,
    validate_collection_config,
    validate_contact_config,
    validate_run_config,
)


def _legacy_config(**overrides: object) -> RunConfig:
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


def test_gui_exposes_all_implemented_sources() -> None:
    assert len(ALL_GUI_SOURCES) == 19
    assert set(PUBLIC_CANDIDATE_SOURCES) == {
        "pracuj",
        "olx",
        "theprotocol",
        "bulldogjob",
        "kprm",
        "randstad",
    }
    assert set(CREDENTIAL_SOURCES) == {"epraca", "jooble", "careerjet", "adzuna"}
    assert set(EXPERIMENTAL_SOURCES) == set(PUBLIC_CANDIDATE_SOURCES + CREDENTIAL_SOURCES)
    assert not (set(VERIFIED_SOURCES) & set(EXPERIMENTAL_SOURCES))


def test_collection_command_does_not_run_enrichment_or_export() -> None:
    config = CollectionConfig(
        sources=("aplikuj", "pracuj", "olx"),
        pages_per_source=5,
        database_path=Path("wyniki/faro.sqlite3"),
        fresh_sources=True,
        strict=True,
    )

    command = build_collection_command(config, python_executable="python")

    assert command[:4] == ["python", "-m", "agregator.workflow_cli", "collect"]
    assert command[command.index("--sources") + 1] == "aplikuj,pracuj,olx"
    assert command[command.index("--pages-per-source") + 1] == "5"
    assert "--fresh-sources" in command
    assert "--strict" in command
    assert "--enrichment-limit" not in command
    assert "--output" not in command


def test_contact_command_does_not_collect_sources() -> None:
    config = ContactConfig(
        database_path=Path("wyniki/faro.sqlite3"),
        output_path=Path("wyniki/Faro_Firmy_Kontakt.xlsx"),
        enrichment_limit=300,
        refresh_enrichment=True,
        strict=True,
    )

    command = build_contact_command(config, python_executable="python")

    assert command[:4] == ["python", "-m", "agregator.workflow_cli", "enrich"]
    assert command[command.index("--enrichment-limit") + 1] == "300"
    assert "--refresh-enrichment" in command
    assert "--strict" in command
    assert "--sources" not in command
    assert "--pages-per-source" not in command
    assert "--fresh-sources" not in command


def test_legacy_one_shot_builder_is_kept_for_compatibility() -> None:
    command = build_run_command(_legacy_config(), python_executable="python")

    assert command[:4] == ["python", "-m", "agregator.workflow_cli", "run"]
    assert command[command.index("--sources") + 1] == "aplikuj,ngo"
    assert command[command.index("--enrichment-limit") + 1] == "300"


@pytest.mark.parametrize(
    ("config", "message"),
    [
        (
            CollectionConfig((), 1, Path("wyniki/faro.sqlite3")),
            "co najmniej jedno źródło",
        ),
        (
            CollectionConfig(("aplikuj",), 0, Path("wyniki/faro.sqlite3")),
            "1–1000",
        ),
        (
            CollectionConfig(("aplikuj",), 1, Path("wyniki/faro.txt")),
            ".sqlite3",
        ),
    ],
)
def test_validate_collection_config_rejects_invalid_values(
    config: CollectionConfig,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        validate_collection_config(config)


@pytest.mark.parametrize(
    ("config", "message"),
    [
        (
            ContactConfig(
                Path("wyniki/faro.sqlite3"),
                Path("wyniki/Faro.xlsx"),
                501,
            ),
            "1–500",
        ),
        (
            ContactConfig(Path("wyniki/faro.txt"), Path("wyniki/Faro.xlsx"), 10),
            ".sqlite3",
        ),
        (
            ContactConfig(Path("wyniki/faro.sqlite3"), Path("wyniki/Faro.csv"), 10),
            ".xlsx",
        ),
    ],
)
def test_validate_contact_config_rejects_invalid_values(
    config: ContactConfig,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        validate_contact_config(config)


def test_legacy_validation_still_works() -> None:
    with pytest.raises(ValueError, match="1–500"):
        validate_run_config(_legacy_config(enrichment_limit=501))
