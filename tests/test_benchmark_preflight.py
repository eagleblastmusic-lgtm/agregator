import pytest

from agregator.benchmark_preflight import build_benchmark_preflight
from agregator.sources import default_registry


def test_preflight_blocks_experimental_source_without_explicit_acknowledgement() -> None:
    result = build_benchmark_preflight(
        default_registry(),
        ["olx"],
        search_provider_ready=True,
    )

    assert result.ready is False
    assert result.blockers == ("experimental_source_not_acknowledged:olx",)
    assert len(result.sources) == 1
    source = result.sources[0]
    assert source.name == "olx"
    assert source.access_mode == "public_html"
    assert source.experimental is True
    assert source.ready is False
    assert source.error == "experimental_source_requires_explicit_acknowledgement"
    assert result.warnings


def test_preflight_allows_experimental_source_after_explicit_acknowledgement() -> None:
    result = build_benchmark_preflight(
        default_registry(),
        ["OLX"],
        search_provider_ready=True,
        allow_experimental_sources=True,
    )

    assert result.ready is True
    assert result.blockers == ()
    assert result.sources[0].ready is True
    assert result.sources[0].experimental is True
    assert result.warnings


def test_preflight_reports_partner_api_configuration_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("JOOBLE_API_KEY", raising=False)

    result = build_benchmark_preflight(
        default_registry(),
        ["jooble"],
        search_provider_ready=True,
    )

    assert result.ready is False
    assert result.blockers == ("source_not_ready:jooble",)
    assert result.sources[0].access_mode == "partner_api"
    assert result.sources[0].experimental is False
    assert "JOOBLE_API_KEY" in (result.sources[0].error or "")


def test_preflight_ready_for_configured_partner_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JOOBLE_API_KEY", "test-key")

    result = build_benchmark_preflight(
        default_registry(),
        ["jooble"],
        search_provider_ready=True,
    )

    assert result.ready is True
    assert result.blockers == ()
    assert result.warnings == ()
    assert result.sources[0].ready is True
    assert result.sources[0].access_mode == "partner_api"


def test_preflight_still_requires_search_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JOOBLE_API_KEY", "test-key")

    result = build_benchmark_preflight(
        default_registry(),
        ["jooble"],
        search_provider_ready=False,
    )

    assert result.ready is False
    assert "missing_search_provider_configuration" in result.blockers
