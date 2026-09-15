import pytest

from agregator.sources import default_registry


def test_default_registry_contains_api_and_public_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JOOBLE_API_KEY", "test-key")
    monkeypatch.setenv("ADZUNA_APP_ID", "test-id")
    monkeypatch.setenv("ADZUNA_APP_KEY", "test-key")
    registry = default_registry()

    assert registry.names() == ["adzuna", "jooble", "olx"]
    assert registry.create("OLX").name == "olx"
    assert registry.create("JOOBLE").name == "jooble"
    assert registry.create("ADZUNA").name == "adzuna"


def test_jooble_registry_requires_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JOOBLE_API_KEY", raising=False)
    registry = default_registry()

    with pytest.raises(ValueError, match="JOOBLE_API_KEY"):
        registry.create("jooble")


def test_adzuna_registry_requires_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ADZUNA_APP_ID", raising=False)
    monkeypatch.delenv("ADZUNA_APP_KEY", raising=False)
    registry = default_registry()

    with pytest.raises(ValueError, match="ADZUNA_APP_ID"):
        registry.create("adzuna")
