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
    monkeypatch.setenv("EPRACA_PARTNER", "Faro Partner")
    monkeypatch.setenv("EPRACA_ALL", "true")
    registry = default_registry()

    assert registry.names() == [
        "adzuna",
        "careerjet",
        "epraca",
        "jooble",
        "justjoinit",
        "karierawfinansach",
        "kprm",
        "nofluffjobs",
        "ofertypracyedu",
        "olx",
        "pracuj",
        "rocketjobs",
        "skillshot",
    ]
    assert registry.create("OLX").name == "olx"
    assert registry.create("PRACUJ").name == "pracuj"
    assert registry.create("SKILLSHOT").name == "skillshot"
    assert registry.create("NOFLUFFJOBS").name == "nofluffjobs"
    assert registry.create("JUSTJOINIT").name == "justjoinit"
    assert registry.create("ROCKETJOBS").name == "rocketjobs"
    assert registry.create("KARIERAWFINANSACH").name == "karierawfinansach"
    assert registry.create("KPRM").name == "kprm"
    assert registry.create("OFERTYPRACYEDU").name == "ofertypracyedu"
    assert registry.create("JOOBLE").name == "jooble"
    assert registry.create("ADZUNA").name == "adzuna"
    assert registry.create("CAREERJET").name == "careerjet"
    assert registry.create("EPRACA").name == "epraca"


def test_default_registry_exposes_access_policy_metadata() -> None:
    registry = default_registry()

    olx = registry.describe("OLX")
    assert olx.access_mode == "public_web_endpoint"
    assert olx.experimental is True
    assert olx.notes is not None
    assert olx.required_env == ()

    pracuj = registry.describe("pracuj")
    assert pracuj.access_mode == "public_sitemap_html"
    assert pracuj.experimental is True
    assert pracuj.required_env == ()

    skillshot = registry.describe("skillshot")
    assert skillshot.access_mode == "public_html"
    assert skillshot.experimental is True

    kprm = registry.describe("kprm")
    assert kprm.access_mode == "official_public_html"
    assert kprm.experimental is True
    assert kprm.required_env == ()

    education = registry.describe("ofertypracyedu")
    assert education.access_mode == "official_public_html"
    assert education.experimental is True
    assert education.required_env == ()

    epraca = registry.describe("epraca")
    assert epraca.access_mode == "official_partner_feed"
    assert epraca.experimental is False
    assert epraca.required_env == ("EPRACA_PARTNER",)
    assert "EPRACA_ALL" in epraca.configuration_env

    jooble = registry.describe("jooble")
    assert jooble.access_mode == "partner_api"
    assert jooble.experimental is False
    assert jooble.required_env == ("JOOBLE_API_KEY",)
    assert "JOOBLE_LOCATION" in jooble.configuration_env

    adzuna = registry.describe("adzuna")
    assert adzuna.required_env == ("ADZUNA_APP_ID", "ADZUNA_APP_KEY")

    careerjet = registry.describe("careerjet")
    assert careerjet.required_env == (
        "CAREERJET_API_KEY",
        "CAREERJET_REFERER",
        "CAREERJET_USER_IP",
        "CAREERJET_USER_AGENT",
    )


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


def test_epraca_registry_requires_authorized_partner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("EPRACA_PARTNER", raising=False)
    monkeypatch.setenv("EPRACA_ALL", "true")
    registry = default_registry()

    with pytest.raises(ValueError, match="EPRACA_PARTNER"):
        registry.create("epraca")


def test_epraca_registry_requires_explicit_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EPRACA_PARTNER", "Faro Partner")
    monkeypatch.delenv("EPRACA_WOJEWODZTWO", raising=False)
    monkeypatch.delenv("EPRACA_JEDNOSTKA", raising=False)
    monkeypatch.delenv("EPRACA_ALL", raising=False)
    registry = default_registry()

    with pytest.raises(ValueError, match="exactly one criterion"):
        registry.create("epraca")
