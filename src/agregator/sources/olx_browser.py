from __future__ import annotations

import os
import tempfile
from pathlib import Path

from playwright.async_api import (
    BrowserContext,
    Error as PlaywrightError,
    Page,
    Playwright,
    async_playwright,
)

_ACCESS_CONTROL_MARKERS = (
    "access denied",
    "403 forbidden",
    "verify you are human",
    "sprawdź, czy jesteś człowiekiem",
    "captcha",
    "zostałeś zablokowany",
    "you have been blocked",
)


class OlxBrowserAccessError(RuntimeError):
    """Raised when OLX blocks even a normal visible browser page."""


class OlxBrowserTransport:
    """Read public OLX pages in a normal visible Edge/Chrome window.

    This transport deliberately does not use stealth patches, proxy rotation, CAPTCHA
    solving, hidden APIs, or browser-fingerprint spoofing. It is only a compatibility
    fallback for environments where OLX rejects a plain HTTP client but serves the same
    public page to a standard browser.
    """

    def __init__(
        self,
        *,
        timeout_ms: int = 45_000,
        settle_ms: int = 1_000,
        profile_dir: str | Path | None = None,
        channels: tuple[str, ...] = ("msedge", "chrome"),
    ) -> None:
        self.timeout_ms = max(5_000, timeout_ms)
        self.settle_ms = max(0, settle_ms)
        self.profile_dir = Path(profile_dir) if profile_dir else _default_profile_dir()
        self.channels = channels
        self._playwright: Playwright | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self.channel: str | None = None

    async def fetch_html(self, url: str) -> str:
        page = await self._ensure_page()
        try:
            response = await page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=self.timeout_ms,
            )
            if self.settle_ms:
                await page.wait_for_timeout(self.settle_ms)
            html = await page.content()
        except PlaywrightError as exc:
            raise RuntimeError(f"OLX browser navigation failed for {url}: {exc}") from exc

        status = response.status if response is not None else None
        if status is not None and status >= 400:
            raise OlxBrowserAccessError(
                f"OLX returned HTTP {status} in the visible browser for {url}. "
                "Faro will not bypass this access control."
            )

        lowered = html.lower()
        has_listing_signal = (
            "window.__prerendered_state__" in lowered
            or 'data-cy="l-card"' in lowered
            or 'data-testid="l-card"' in lowered
        )
        if not has_listing_signal and any(marker in lowered for marker in _ACCESS_CONTROL_MARKERS):
            raise OlxBrowserAccessError(
                "OLX displayed an access-control/CAPTCHA page in the visible browser. "
                "Faro will not attempt to bypass it."
            )
        return html

    async def close(self) -> None:
        context = self._context
        playwright = self._playwright
        self._page = None
        self._context = None
        self._playwright = None
        self.channel = None

        if context is not None:
            try:
                await context.close()
            except PlaywrightError:
                pass
        if playwright is not None:
            try:
                await playwright.stop()
            except PlaywrightError:
                pass

    async def _ensure_page(self) -> Page:
        if self._page is not None and not self._page.is_closed():
            return self._page

        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = await async_playwright().start()
        last_error: Exception | None = None

        for channel in self.channels:
            try:
                self._context = await self._playwright.chromium.launch_persistent_context(
                    user_data_dir=str(self.profile_dir),
                    channel=channel,
                    headless=False,
                    locale="pl-PL",
                    accept_downloads=False,
                )
            except PlaywrightError as exc:
                last_error = exc
                continue
            self.channel = channel
            break

        if self._context is None:
            await self._playwright.stop()
            self._playwright = None
            detail = f": {last_error}" if last_error else ""
            raise RuntimeError(
                "Nie udało się uruchomić Microsoft Edge ani Google Chrome dla OLX" + detail
            )

        pages = self._context.pages
        self._page = pages[0] if pages else await self._context.new_page()
        return self._page


def _default_profile_dir() -> Path:
    root = os.getenv("LOCALAPPDATA")
    if root:
        return Path(root) / "Faro" / "OLXBrowserProfile"
    return Path(tempfile.gettempdir()) / "faro-olx-browser-profile"
