from __future__ import annotations

import asyncio
import json
import os

import typer

from .crawler import WebsiteCrawler
from .pipeline import EmployerDiscoveryPipeline
from .search import BraveSearchProvider

app = typer.Typer(help="Faro Employer Discovery Engine")


def _crawler() -> WebsiteCrawler:
    return WebsiteCrawler(
        user_agent=os.getenv("AGREGATOR_USER_AGENT", "FaroEmployerDiscovery/0.1"),
        max_pages=int(os.getenv("AGREGATOR_MAX_PAGES", "12")),
        request_delay=float(os.getenv("AGREGATOR_REQUEST_DELAY", "0.8")),
    )


@app.command("scan-url")
def scan_url(
    company: str = typer.Option(..., "--company"),
    url: str = typer.Option(..., "--url"),
    city: str | None = typer.Option(None, "--city"),
) -> None:
    async def run() -> None:
        pipeline = EmployerDiscoveryPipeline(crawler=_crawler())
        result = await pipeline.scan_known_website(company, url, city)
        typer.echo(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))

    asyncio.run(run())


@app.command("discover")
def discover(
    company: str = typer.Option(..., "--company"),
    city: str | None = typer.Option(None, "--city"),
) -> None:
    api_key = os.getenv("BRAVE_SEARCH_API_KEY", "")
    if not api_key:
        raise typer.BadParameter("Ustaw BRAVE_SEARCH_API_KEY przed użyciem discover")

    async def run() -> None:
        provider = BraveSearchProvider(api_key)
        pipeline = EmployerDiscoveryPipeline(crawler=_crawler(), search_provider=provider)
        result = await pipeline.discover(company, city)
        typer.echo(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))

    asyncio.run(run())


if __name__ == "__main__":
    app()
