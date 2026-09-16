from __future__ import annotations

from . import gui

ACTIVE_OLX_SOURCES = ("olx",)
BLOCKED_HOLD_SOURCES = tuple(source for source in gui.HOLD_SOURCES if source != "olx")


def selectable_sources() -> tuple[str, ...]:
    """Sources that the desktop GUI may actively run in Etap 1."""

    return gui.VERIFIED_SOURCES + ACTIVE_OLX_SOURCES + gui.CREDENTIAL_SOURCES


def main() -> None:
    """Launch the two-stage GUI with OLX enabled as an exhaustive catalog source."""

    gui.VERIFIED_SOURCES = gui.VERIFIED_SOURCES + ACTIVE_OLX_SOURCES
    gui.HOLD_SOURCES = BLOCKED_HOLD_SOURCES
    gui.EXPERIMENTAL_SOURCES = gui.HOLD_SOURCES + gui.CREDENTIAL_SOURCES
    gui.ALL_GUI_SOURCES = gui.VERIFIED_SOURCES + gui.HOLD_SOURCES + gui.CREDENTIAL_SOURCES
    gui.DEFAULT_SOURCES = gui.VERIFIED_SOURCES
    gui.SOURCE_LABELS["olx"] = "OLX Praca — pełny katalog ofert"
    gui.main()


if __name__ == "__main__":
    main()
