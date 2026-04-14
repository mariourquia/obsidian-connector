"""Tests for commitment-note related block (Task 15.A.2).

Covers: fence marker rendering, idempotent re-render, edge/shared-entity
formatting, and interaction with the existing follow-up log / user-notes blocks.
"""
from __future__ import annotations

import tempfile
from dataclasses import replace
from pathlib import Path

import pytest

from obsidian_connector.commitment_notes import (
    RELATED_BEGIN,
    RELATED_END,
    ActionInput,
    render_commitment_note,
    write_commitment_note,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _base_action(**kwargs) -> ActionInput:
    defaults = dict(
        action_id="act_01HTEST",
        capture_id="cap_01HTEST",
        title="Test action",
        created_at="2026-04-13T12:00:00+00:00",
        status="open",
    )
    defaults.update(kwargs)
    return ActionInput(**defaults)


@pytest.fixture()
def vault(tmp_path: Path) -> Path:
    return tmp_path


# ---------------------------------------------------------------------------
# 1. No related data — fence absent
# ---------------------------------------------------------------------------

def test_no_related_data_no_fence():
    action = _base_action()
    rendered = render_commitment_note(action)
    assert RELATED_BEGIN not in rendered
    assert RELATED_END not in rendered


# ---------------------------------------------------------------------------
# 2. Edge-only
# ---------------------------------------------------------------------------

def test_edge_only_renders_fence():
    action = _base_action(
        related_edges=[
            {
                "relation": "blocks",
                "direction": "outgoing",
                "action_title": "Other task",
                "action_path": "Commitments/Open/2026/04/other-task-abc1234.md",
            }
        ]
    )
    rendered = render_commitment_note(action)
    assert RELATED_BEGIN in rendered
    assert RELATED_END in rendered
    assert "### Edges" in rendered
    assert "Blocks:" in rendered
    assert "Other task" in rendered


def test_incoming_edge_label():
    action = _base_action(
        related_edges=[
            {
                "relation": "blocks",
                "direction": "incoming",
                "action_title": "Upstream task",
                "action_path": None,
            }
        ]
    )
    rendered = render_commitment_note(action)
    assert "Blocks (incoming)" in rendered
    assert "Upstream task" in rendered


def test_edge_with_path_renders_wikilink():
    action = _base_action(
        related_edges=[
            {
                "relation": "follows_from",
                "direction": "outgoing",
                "action_title": "Prior step",
                "action_path": "Commitments/Open/2026/04/prior-step-abc1234.md",
            }
        ]
    )
    rendered = render_commitment_note(action)
    # .md extension should be stripped in wikilink
    assert "[[Commitments/Open/2026/04/prior-step-abc1234|Prior step]]" in rendered


# ---------------------------------------------------------------------------
# 3. Shared-entity groups
# ---------------------------------------------------------------------------

def test_shared_entities_renders_section():
    action = _base_action(
        related_actions=[
            {
                "entity_name": "Capodagli AI Strategy",
                "entity_kind": "project",
                "actions": [
                    {"title": "Peer action", "path": None},
                ],
            }
        ]
    )
    rendered = render_commitment_note(action)
    assert "### Shared context" in rendered
    assert "Capodagli AI Strategy" in rendered
    assert "Project:" in rendered


def test_shared_entity_with_path_renders_wikilink():
    action = _base_action(
        related_actions=[
            {
                "entity_name": "Mario",
                "entity_kind": "person",
                "actions": [
                    {
                        "title": "Linked action",
                        "path": "Commitments/Open/2026/04/linked-action-abc1234.md",
                    },
                ],
            }
        ]
    )
    rendered = render_commitment_note(action)
    assert "[[Commitments/Open/2026/04/linked-action-abc1234|Linked action]]" in rendered


def test_empty_actions_group_skipped():
    action = _base_action(
        related_actions=[
            {"entity_name": "Empty entity", "entity_kind": "topic", "actions": []},
        ]
    )
    rendered = render_commitment_note(action)
    # No fence — no content survived filtering
    assert RELATED_BEGIN not in rendered


# ---------------------------------------------------------------------------
# 4. Idempotent re-render
# ---------------------------------------------------------------------------

def test_related_block_replaced_on_rerender(vault: Path):
    action_v1 = _base_action(
        related_edges=[
            {
                "relation": "blocks",
                "direction": "outgoing",
                "action_title": "First peer",
                "action_path": None,
            }
        ]
    )
    result = write_commitment_note(vault, action_v1)
    content_v1 = result.path.read_text()
    assert "First peer" in content_v1

    action_v2 = replace(
        action_v1,
        related_edges=[
            {
                "relation": "relates_to",
                "direction": "outgoing",
                "action_title": "Second peer",
                "action_path": None,
            }
        ],
    )
    result2 = write_commitment_note(vault, action_v2)
    content_v2 = result2.path.read_text()
    assert result.path == result2.path
    assert "Second peer" in content_v2
    # Old edge gone
    assert "First peer" not in content_v2


def test_related_disappears_when_cleared(vault: Path):
    action_v1 = _base_action(
        related_edges=[
            {
                "relation": "blocks",
                "direction": "outgoing",
                "action_title": "Will be cleared",
                "action_path": None,
            }
        ]
    )
    write_commitment_note(vault, action_v1)

    action_v2 = replace(action_v1, related_edges=[], related_actions=[])
    result2 = write_commitment_note(vault, action_v2)
    content = result2.path.read_text()
    assert RELATED_BEGIN not in content
    assert "Will be cleared" not in content


# ---------------------------------------------------------------------------
# 5. User-notes fence is preserved alongside related block
# ---------------------------------------------------------------------------

def test_user_notes_preserved_with_related(vault: Path):
    action = _base_action(
        related_edges=[
            {
                "relation": "relates_to",
                "direction": "outgoing",
                "action_title": "Other",
                "action_path": None,
            }
        ]
    )
    result = write_commitment_note(vault, action)
    # Manually inject a user note
    content = result.path.read_text()
    from obsidian_connector.commitment_notes import USER_NOTES_BEGIN, USER_NOTES_END
    injected = content.replace(
        f"{USER_NOTES_BEGIN}\n_User-editable area below.",
        f"{USER_NOTES_BEGIN}\nMy hand-written note.",
    )
    result.path.write_text(injected)

    # Re-render with different related data
    action_v2 = replace(
        action,
        related_edges=[
            {
                "relation": "blocks",
                "direction": "outgoing",
                "action_title": "New peer",
                "action_path": None,
            }
        ],
    )
    result2 = write_commitment_note(vault, action_v2)
    final = result2.path.read_text()
    assert "My hand-written note." in final
    assert "New peer" in final
