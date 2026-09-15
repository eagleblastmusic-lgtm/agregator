import pytest

from agregator.sources import default_registry


def test_default_registry_contains_api_and_public_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JOOBLE_API_KEY", "test-key")
    monkeypatch.setenv("ADZUNA_APP_ID", "test-id")
    monkeypatch.setenv("ADZUNA_APP_KEY", "test-key")
    monkeypatch.setenv("CAREERJET_API_KEY", "publisher-key")
    monkeypatch.setenv("CAREERJET_REFERER", "https://faro.example/jobs")
    monkeypatch.setenv("CAREERJET_USER_IP", "203.0.113.10")
    monkeypatch.setenv("CAREERJET_USER_AGENT", "Mozilla/5.0 Test")
    registry = default_registry()

    assert registry.names() == ["adzuna", "careerjet", "jooble", "olx"]
    assert registry.create("OLX").name == "olx"
    assert registry.create("JOOBLE").name == "jooble"
    assert registry.create("ADZUNA").name == "adzuna"
    assert registry.create("CAREERJET").name == "careerjet"


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


def test_careerjet_registry_requires_publisher_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CAREERJET_API_KEY", "publisher-key")
    monkeypatch.delenv("CAREERJET_REFERER", raising=False)
    monkeypatch.setenv("CAREERJET_USER_IP", "203.0.113.10")
    monkeypatch.setenv("CAREERJET_USER_AGENT", "Mozilla/5.0 Test")
    registry = default_registry()

    with pytest.raises(ValueError, match="CAREERJET_REFERER"):
        registry.create("careerjet")
