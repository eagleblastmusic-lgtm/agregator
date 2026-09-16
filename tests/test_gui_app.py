from agregator.gui import CREDENTIAL_SOURCES, HOLD_SOURCES, VERIFIED_SOURCES
from agregator.gui_app import ACTIVE_OLX_SOURCES, BLOCKED_HOLD_SOURCES, selectable_sources


def test_gui_keeps_olx_selectable_and_other_hold_sources_blocked() -> None:
    selectable = set(selectable_sources())

    assert "olx" in ACTIVE_OLX_SOURCES
    assert "olx" in selectable
    assert selectable == set(VERIFIED_SOURCES + ACTIVE_OLX_SOURCES + CREDENTIAL_SOURCES)
    assert set(BLOCKED_HOLD_SOURCES) == {"pracuj", "theprotocol", "bulldogjob"}
    assert "pracuj" not in selectable
    assert "theprotocol" not in selectable
    assert "bulldogjob" not in selectable
    assert "olx" in HOLD_SOURCES  # legacy metadata is patched at GUI launch time
