import json

import httpx
import pytest

from agregator.sources import default_registry
from agregator.sources.olx_browser_source import OlxBrowserFallbackSource


def _prerendered_html() -> str:
    state = {
        "listing": {
            "listing": {
                "visibleTotalCount": 1,
                "totalElements": 1,
                "totalPages": 1,
                "ads": [
                    {
                        "id": 123,
                        "title": "Pracownik",
                        "url": "/d/oferta/pracownik-IDABC123.html",
                        "location": {"cityName": "Wrocław"},
                        "user": {"companyName": "Firma Testowa Sp. z o.o."},
                    }
                ],
            }
        }
    }
    encoded = json.dumps(json.dumps(state, ensure_ascii=False))
    return f'<html><script>window.__PRERENDERED_STATE__= {encoded};</script></html>'


class FakeBrowserTransport:
    def __init__(self) -> None:
        self.urls: list[str] = []
        self.closed = False

    async def fetch_html(self, url: str) -> str:
        self.urls.append(url)
        return _prerendered_html()

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_olx_switches_to_browser_after_403_and_stays_in_browser_mode() -> None:
    http_urls: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        http_urls.append(str(request.url))
        return httpx.Response(403, text="Forbidden", request=request)

    browser = FakeBrowserTransport()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        source = OlxBrowserFallbackSource(
            client=client,
            request_delay=0,
            browser_transport=browser,  # type: ignore[arg-type]
            browser_fallback=True,
        )
        first = await source.collect()
        second = await source.collect(first.next_cursor)

    assert len(first.jobs) == 1
    assert len(http_urls) == 1
    assert len(browser.urls) == 2
    assert browser.urls[0] == http_urls[0]
    assert browser.urls[1] != browser.urls[0]
    assert second.next_cursor is not None


@pytest.mark.asyncio
async def test_olx_does_not_turn_other_http_errors_into_browser_fallback() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="Too Many Requests", request=request)

    browser = FakeBrowserTransport()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        source = OlxBrowserFallbackSource(
            client=client,
            request_delay=0,
            browser_transport=browser,  # type: ignore[arg-type]
            browser_fallback=True,
        )
        with pytest.raises(httpx.HTTPStatusError):
            await source.collect()

    assert browser.urls == []


def test_default_registry_uses_browser_capable_olx_source() -> None:
    source = default_registry().create("olx")

    assert isinstance(source, OlxBrowserFallbackSource)
