"""Tests for entity note writer (Task 15.A/15.C).

Covers: upsert idempotency, frontmatter fields, aliases section,
open/done commitment lists, wiki fence, user-notes preservation.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from obsidian_connector.entity_notes import (
    ENTITIES_ROOT,
    ENTITY_USER_NOTES_BEGIN,
    ENTITY_USER_NOTES_END,
    ENTITY_WIKI_BEGIN,
    ENTITY_WIKI_END,
    EntityInput,
    LinkedAction,
    resolve_entity_path,
    write_entity_note,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _entity(**kwargs) -> EntityInput:
    defaults = dict(
        entity_id="ent_01HTEST",
        kind="project",
        canonical_name="Test Project",
        slug="test-project",
    )
    defaults.update(kwargs)
    return EntityInput(**defaults)


def _action(action_id: str, title: str, status: str = "open", path: str | None = None) -> LinkedAction:
    return LinkedAction(action_id=action_id, title=title, status=status, commitment_path=path)


@pytest.fixture()
def vault(tmp_path: Path) -> Path:
    return tmp_path


# ---------------------------------------------------------------------------
# 1. Path resolution
# ---------------------------------------------------------------------------

def test_resolve_path_project(tmp_path: Path):
    ent = _entity(kind="project", slug="my-project")
    path = resolve_entity_path(tmp_path, ent)
    assert path == tmp_path / ENTITIES_ROOT / "Projects" / "my-project.md"


def test_resolve_path_person(tmp_path: Path):
    ent = _entity(kind="person", slug="mario")
    path = resolve_entity_path(tmp_path, ent)
    assert path == tmp_path / ENTITIES_ROOT / "People" / "mario.md"


def test_invalid_kind_raises():
    ent = _entity(kind="invalid")
    with pytest.raises(ValueError, match="invalid entity kind"):
        resolve_entity_path(Path("/tmp"), ent)


def test_unsafe_slug_raises():
    ent = _entity(slug="../etc/passwd")
    with pytest.raises(ValueError, match="unsafe entity slug"):
        resolve_entity_path(Path("/tmp"), ent)


# ---------------------------------------------------------------------------
# 2. Create / upsert
# ---------------------------------------------------------------------------

def test_write_creates_file(vault: Path):
    ent = _entity()
    result = write_entity_note(vault, ent)
    assert result.path.exists()
    assert result.created is True


def test_write_idempotent(vault: Path):
    ent = _entity()
    r1 = write_entity_note(vault, ent)
    r2 = write_entity_note(vault, ent)
    assert r1.path == r2.path
    assert r2.created is False


# ---------------------------------------------------------------------------
# 3. Frontmatter
# ---------------------------------------------------------------------------

def test_frontmatter_fields(vault: Path):
    ent = _entity(
        entity_id="ent_ABCD",
        kind="project",
        canonical_name="My Project",
        slug="my-project",
        description="A test project",
        aliases=["MP", "Project X"],
    )
    result = write_entity_note(vault, ent)
    content = result.path.read_text()
    assert "type: entity" in content
    assert "entity_id: ent_ABCD" in content
    assert "kind: project" in content
    assert "canonical_name: My Project" in content
    assert "my-project" in content  # slug (may be quoted by YAML serializer)
    assert "description: A test project" in content
    assert "MP" in content
    assert "Project X" in content


# ---------------------------------------------------------------------------
# 4. Open / done commitments
# ---------------------------------------------------------------------------

def test_open_commitments_section(vault: Path):
    ent = _entity(
        open_actions=[
            _action("act_001", "Do something", "open", "Commitments/Open/2026/04/do-something-act_001.md"),
        ]
    )
    result = write_entity_note(vault, ent)
    content = result.path.read_text()
    assert "## Open commitments" in content
    assert "Do something" in content
    assert "Commitments/Open/2026/04/do-something-act_001" in content


def test_no_open_commitments_placeholder(vault: Path):
    ent = _entity()
    result = write_entity_note(vault, ent)
    content = result.path.read_text()
    assert "## Open commitments" in content
    assert "_No open commitments._" in content


def test_done_commitments_section(vault: Path):
    ent = _entity(
        done_actions=[
            _action("act_002", "Finished task", "done"),
        ]
    )
    result = write_entity_note(vault, ent)
    content = result.path.read_text()
    assert "## Completed commitments" in content
    assert "Finished task" in content


# ---------------------------------------------------------------------------
# 5. User-notes fence preserved
# ---------------------------------------------------------------------------

def test_user_notes_preserved_on_rewrite(vault: Path):
    ent = _entity()
    result = write_entity_note(vault, ent)
    content = result.path.read_text()
    injected = content.replace(
        f"{ENTITY_USER_NOTES_BEGIN}\n\n{ENTITY_USER_NOTES_END}",
        f"{ENTITY_USER_NOTES_BEGIN}\nMy personal note.\n{ENTITY_USER_NOTES_END}",
    )
    result.path.write_text(injected)

    # Re-render
    result2 = write_entity_note(vault, ent)
    final = result2.path.read_text()
    assert "My personal note." in final


# ---------------------------------------------------------------------------
# 6. Wiki fence (15.C)
# ---------------------------------------------------------------------------

def test_wiki_fence_always_present(vault: Path):
    ent = _entity()
    result = write_entity_note(vault, ent)
    content = result.path.read_text()
    assert ENTITY_WIKI_BEGIN in content
    assert ENTITY_WIKI_END in content


def test_wiki_content_written_when_provided(vault: Path):
    ent = _entity(wiki_content="This project involves AI strategy work.")
    result = write_entity_note(vault, ent)
    content = result.path.read_text()
    assert "This project involves AI strategy work." in content


def test_wiki_content_preserved_when_not_supplied(vault: Path):
    ent_v1 = _entity(wiki_content="First generated summary.")
    result = write_entity_note(vault, ent_v1)
    assert "First generated summary." in result.path.read_text()

    # Re-render without wiki_content — existing content preserved
    ent_v2 = replace(ent_v1, wiki_content=None)
    result2 = write_entity_note(vault, ent_v2)
    assert "First generated summary." in result2.path.read_text()


def test_wiki_content_replaced_when_newly_supplied(vault: Path):
    ent_v1 = _entity(wiki_content="Old summary.")
    write_entity_note(vault, ent_v1)

    ent_v2 = replace(ent_v1, wiki_content="New summary, better.")
    result2 = write_entity_note(vault, ent_v2)
    content = result2.path.read_text()
    assert "New summary, better." in content
    assert "Old summary." not in content
