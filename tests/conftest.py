"""Shared fixtures for obsidian-connector pytest suite."""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest


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
