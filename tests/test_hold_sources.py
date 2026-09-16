from pathlib import Path

import pytest

from agregator.sources import default_registry
from agregator.workflow import resolve_workflow_sources, run_collection_workflow


def test_hold_source_is_skipped_before_collection() -> None:
    requested, selected, skipped = resolve_workflow_sources(
        default_registry(),
        "olx",
        environment={},
    )

    assert requested == ["olx"]
    assert selected == []
    assert skipped == [
        {
            "source": "olx",
            "status": "skipped",
            "reason": "hold_access_blocked",
            "detail": (
                "OLX automated collection route is access-blocked "
                "(HTTP 403 / robots policy)"
            ),
            "access_mode": "public_web_endpoint",
        }
    ]


@pytest.mark.asyncio
async def test_hold_only_collection_finishes_without_strict_failure(tmp_path: Path) -> None:
    db = tmp_path / "hold.sqlite3"

    result = await run_collection_workflow(
        db=str(db),
        sources="olx",
        pages_per_source=5,
        fresh_sources=True,
        registry=default_registry(),
        environment={},
    )

    assert result.status == "success"
    assert result.selected_sources == []
    assert result.failed_sources == []
    assert result.source_results == []
    assert result.skipped_sources[0]["reason"] == "hold_access_blocked"
    assert db.exists()
