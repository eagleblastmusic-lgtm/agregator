from agregator.gui import CREDENTIAL_SOURCES, HOLD_SOURCES, VERIFIED_SOURCES
from agregator.gui_app import selectable_sources


def test_safe_gui_never_marks_hold_sources_selectable() -> None:
    selectable = set(selectable_sources())

    assert selectable == set(VERIFIED_SOURCES + CREDENTIAL_SOURCES)
    assert not (selectable & set(HOLD_SOURCES))
    assert "olx" not in selectable
    assert "pracuj" not in selectable
    assert "theprotocol" not in selectable
    assert "bulldogjob" not in selectable
