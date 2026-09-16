from __future__ import annotations

import os

import httpx

from .olx import OlxPublicSource
from .olx_browser import OlxBrowserTransport

_FALSE_VALUES = {"0", "false", "no", "off"}


class OlxBrowserFallbackSource(OlxPublicSource):
    """OLX source that falls back to a normal visible browser after HTTP 403/406.

    The fallback is enabled by default on Windows, where Faro is used interactively.
    Once the HTTP client is rejected, subsequent OLX pages stay on the same browser
    session instead of issuing a rejected HTTP request before every page.
    """

    def __init__(
        self,
        *,
        browser_transport: OlxBrowserTransport | None = None,
        browser_fallback: bool | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self._browser_transport = browser_transport
        if browser_fallback is None:
            configured = os.getenv("AGREGATOR_OLX_BROWSER_FALLBACK")
            if configured is None:
                browser_fallback = os.name == "nt"
            else:
                browser_fallback = configured.strip().lower() not in _FALSE_VALUES
        self._browser_fallback = browser_fallback
        self._browser_mode = False

    async def _get(self, url: str) -> httpx.Response:
        if self._browser_mode:
            return await self._get_in_browser(url)

        try:
            return await super()._get(url)
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status not in {403, 406} or not self._browser_fallback:
                raise
            self._browser_mode = True
            return await self._get_in_browser(url)

    async def _get_in_browser(self, url: str) -> httpx.Response:
        if self._browser_transport is None:
            self._browser_transport = OlxBrowserTransport()
        html = await self._browser_transport.fetch_html(url)
        request = httpx.Request("GET", url)
        return httpx.Response(
            200,
            text=html,
            headers={"content-type": "text/html; charset=utf-8"},
            request=request,
        )

    async def _close_owned_client(self) -> None:
        await super()._close_owned_client()
        if self._browser_transport is not None:
            await self._browser_transport.close()
