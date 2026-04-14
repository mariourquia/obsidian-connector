"""Startup helpers shared by the CLI and optional TUI onboarding flow."""

from __future__ import annotations

from pathlib import Path

_WIZARD_MARKER = Path.home() / ".config" / "obsidian-connector" / ".setup-complete"


def mark_wizard_completed() -> None:
    """Persist that the interactive setup wizard has completed."""
    _WIZARD_MARKER.parent.mkdir(parents=True, exist_ok=True)
    _WIZARD_MARKER.write_text("1", encoding="utf-8")


def is_first_run() -> bool:
    """Return True if the setup wizard has never been completed."""
    return not _WIZARD_MARKER.is_file()
