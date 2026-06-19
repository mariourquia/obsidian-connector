"""The committed creation/sync_config.example.json stays valid + in-schema.

Guards against the example drifting from what load_sync_config / list_projects
actually parse. The example is the public schema reference (no private repos).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from obsidian_connector.creation_projects import get_project, list_projects
from obsidian_connector.project_sync import load_sync_config

EXAMPLE = Path(__file__).resolve().parents[1] / "creation" / "sync_config.example.json"


def test_example_file_exists_and_is_valid_json():
    assert EXAMPLE.is_file(), f"missing {EXAMPLE}"
    json.loads(EXAMPLE.read_text(encoding="utf-8"))


@pytest.fixture
def _point_at_example(monkeypatch):
    monkeypatch.setenv("OBSIDIAN_SYNC_CONFIG", str(EXAMPLE))


def test_example_parses_into_sync_config(_point_at_example):
    config = load_sync_config(None)

    assert str(config.github_root).endswith("/dev")
    assert config.vault_subdir == ""
    assert config.group_display_names == {"acme": "Acme Platform", "standalone": "Standalone"}
    assert {r.dir_name for r in config.repos} == {"acme-api", "acme-web", "my-tool"}


def test_example_groups_collapse_into_projects(_point_at_example):
    acme = get_project(None, "acme")

    assert acme is not None
    assert acme.name == "Acme Platform"
    assert set(acme.repos) == {"acme-api", "acme-web"}


def test_example_standalone_repo_is_own_project(_point_at_example):
    projects = list_projects(None)
    slugs = {p.slug for p in projects}

    assert "my-tool" in slugs
    my_tool = next(p for p in projects if p.slug == "my-tool")
    assert my_tool.repos == ("my-tool",)
    assert my_tool.status == "paused"
