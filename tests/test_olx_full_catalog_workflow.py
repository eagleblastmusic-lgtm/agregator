from pathlib import Path

import pytest

from agregator.models import JobPosting
from agregator.sources.base import SourceBatch
from agregator.sources.registry import SourceRegistry
from agregator.workflow import run_collection_workflow


class FakeOlxCatalogSource:
    name = "olx"

    async def collect(self, cursor: str | None = None) -> SourceBatch:
        if cursor is None:
            return SourceBatch(
                jobs=[
                    JobPosting(
                        source="olx",
                        source_id="olx-1",
                        url="https://www.olx.pl/d/oferta/one-IDONE.html",
                        title="Oferta 1",
                        company_name="Firma 1",
                        company_name_source="test",
                        company_name_confidence=1.0,
                    )
                ],
                next_cursor="second",
            )
        if cursor == "second":
            return SourceBatch(
                jobs=[
                    JobPosting(
                        source="olx",
                        source_id="olx-2",
                        url="https://www.olx.pl/d/oferta/two-IDTWO.html",
                        title="Oferta 2",
                        company_name="Firma 2",
                        company_name_source="test",
                        company_name_confidence=1.0,
                    )
                ],
                next_cursor=None,
            )
        raise AssertionError(f"unexpected cursor: {cursor}")


def _registry() -> SourceRegistry:
    registry = SourceRegistry()
    registry.register("olx", FakeOlxCatalogSource, access_mode="public_html")
    return registry


@pytest.mark.asyncio
async def test_olx_full_catalog_ignores_generic_page_limit(tmp_path: Path) -> None:
    result = await run_collection_workflow(
        db=str(tmp_path / "olx.sqlite3"),
        sources="olx",
        pages_per_source=1,
        fresh_sources=True,
        registry=_registry(),
        environment={"AGREGATOR_OLX_FULL_CATALOG": "1"},
    )

    assert result.status == "success"
    assert result.successful_sources == ["olx"]
    source = result.source_results[0]
    assert source["collection_mode"] == "full_catalog"
    assert source["pages"] == 2
    assert source["jobs_seen"] == 2
    assert source["next_cursor"] is None


@pytest.mark.asyncio
async def test_olx_bounded_mode_is_available_for_ci_smoke(tmp_path: Path) -> None:
    result = await run_collection_workflow(
        db=str(tmp_path / "olx.sqlite3"),
        sources="olx",
        pages_per_source=1,
        fresh_sources=True,
        registry=_registry(),
        environment={"AGREGATOR_OLX_FULL_CATALOG": "0"},
    )

    source = result.source_results[0]
    assert source["collection_mode"] == "bounded_pages"
    assert source["pages"] == 1
    assert source["jobs_seen"] == 1
    assert source["next_cursor"] == "second"
