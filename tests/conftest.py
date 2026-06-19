"""Shared fixtures for obsidian-connector pytest suite."""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def _isolate_user_config(tmp_path_factory, monkeypatch):
    """Isolate user-level config so tests never read the real ~/.config.

    The canonical Creation registry lives at
    ``~/.config/obsidian-connector/sync_config.json``. Without isolation, any
    test that exercises ``load_sync_config`` and does not provide its own
    fixture would silently read the developer's real registry, making tests
    non-hermetic. This fixture points ``XDG_CONFIG_HOME`` at a fresh temp dir
    and clears the explicit ``OBSIDIAN_SYNC_CONFIG`` override for every test.
    Tests that want to exercise the canonical path can write into the
    ``xdg_config_home`` fixture's directory or set the env vars themselves.
    """
    xdg = tmp_path_factory.mktemp("xdg")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    monkeypatch.delenv("OBSIDIAN_SYNC_CONFIG", raising=False)


@pytest.fixture
def xdg_config_home() -> Path:
    """Return the isolated XDG_CONFIG_HOME directory set by ``_isolate_user_config``."""
    return Path(os.environ["XDG_CONFIG_HOME"])


@pytest.fixture
def tmp_vault(tmp_path: Path) -> Path:
    """Create a temporary vault with standard folder structure."""
    for d in [
        "daily", "Cards", "Inbox", "Inbox/Agent Drafts", "Inbox/Agent Drafts/Tasks",
        "Inbox/Agent Drafts/Ideas", "Inbox/Project Ideas", "Archive",
        "Archive/Rejected Drafts", "Archive/Stale Drafts", "Reports",
        "Project Tracking", "Research/Inbox", "_templates",
        "Projects/Unsorted Voice Captures", "sessions",
    ]:
        (tmp_path / d).mkdir(parents=True, exist_ok=True)
    return tmp_path


@pytest.fixture
def mock_index_store() -> MagicMock:
    """Return a MagicMock for IndexStore."""
    store = MagicMock()
    store.update_incremental = MagicMock()
    return store


@pytest.fixture
def sample_config() -> dict:
    """Return a standard config dict."""
    return {
        "default_vault": None,
        "timeout_seconds": 30,
        "protected_folders": ["Archive/"],
        "draft_max_age_days": 14,
        "watcher_enabled": True,
        "daily_note_path": "daily/{{date}}.md",
        "daily_note_format": "YYYY-MM-DD",
    }
