#!/usr/bin/env python3
"""Tests for the entity notes module (entity_notes.py).

Uses tempfile for test vaults and plain assert statements.
Run with: python3 scripts/entity_notes_test.py
"""

from __future__ import annotations

import sys
import tempfile
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from obsidian_connector.entity_notes import (
    ENTITY_USER_NOTES_BEGIN,
    ENTITY_USER_NOTES_END,
    EntityInput,
    LinkedAction,
    resolve_entity_path,
    write_entity_note,
)

PASS = 0
FAIL = 0


def test(label: str, fn):
    global PASS, FAIL
    print(f"\n{'=' * 60}")
    print(f"TEST: {label}")
    print(f"{'=' * 60}")
    try:
        fn()
        print("  OK")
        PASS += 1
    except Exception as exc:
        print(f"  FAIL  {type(exc).__name__}: {exc}")
        traceback.print_exc(limit=3)
        FAIL += 1


def _sample_entity(**overrides) -> EntityInput:
    base = dict(
        entity_id="ent_01HS000000000000000001",
        kind="project",
        canonical_name="Capodagli AI Strategy",
        slug="capodagli-ai-strategy",
        aliases=["Capodagli", "AI Strategy"],
        description="Work-stream covering the board deck and LP brief.",
        open_actions=[
            LinkedAction(
                action_id="act_01HS1",
                title="Send board deck draft",
                status="open",
                commitment_path="Commitments/Open/2026/04/send-board-deck-draft-abc1234.md",
            ),
        ],
        done_actions=[
            LinkedAction(
                action_id="act_01HS2",
                title="Draft LP memo",
                status="done",
                commitment_path="Commitments/Done/2026/04/draft-lp-memo-xyz7890.md",
            ),
        ],
    )
    base.update(overrides)
    return EntityInput(**base)


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------


def test_resolve_path_uses_kind_subdir():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        ent = _sample_entity()
        path = resolve_entity_path(vault, ent)
        assert path == vault / "Entities" / "Projects" / "capodagli-ai-strategy.md", path


def test_resolve_path_rejects_unsafe_slug():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        ent = _sample_entity(slug="../../../etc/passwd")
        try:
            resolve_entity_path(vault, ent)
        except ValueError:
            return
        raise AssertionError("expected ValueError for unsafe slug")


def test_resolve_path_rejects_unknown_kind():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        ent = _sample_entity(kind="species")
        try:
            resolve_entity_path(vault, ent)
        except ValueError:
            return
        raise AssertionError("expected ValueError for unknown kind")


# ---------------------------------------------------------------------------
# Write behaviour
# ---------------------------------------------------------------------------


def test_write_creates_note_with_frontmatter_and_sections():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        ent = _sample_entity()
        result = write_entity_note(vault, ent)

        assert result.created is True
        assert result.path.exists()
        content = result.path.read_text(encoding="utf-8")
        assert content.startswith("---\n")
        assert "type: entity" in content
        assert "entity_id: ent_01HS000000000000000001" in content
        assert "kind: project" in content
        # Canonical name and aliases in frontmatter.
        assert "canonical_name: " in content
        assert "aliases: [" in content
        # Body sections.
        assert "## Aliases" in content
        assert "## Open commitments" in content
        assert "## Completed commitments" in content
        # Wikilinks preserve the commitment path.
        assert (
            "[[Commitments/Open/2026/04/send-board-deck-draft-abc1234|Send board deck draft]]"
            in content
        )
        # User-notes fence present.
        assert ENTITY_USER_NOTES_BEGIN in content
        assert ENTITY_USER_NOTES_END in content


def test_write_is_idempotent_and_preserves_user_notes():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        ent = _sample_entity()
        path = resolve_entity_path(vault, ent)

        write_entity_note(vault, ent)
        # Inject user notes between the fences.
        original = path.read_text(encoding="utf-8")
        user_content = "I had coffee with Mario about this.\nFollow up next week."
        replaced = original.replace(
            f"{ENTITY_USER_NOTES_BEGIN}\n\n{ENTITY_USER_NOTES_END}",
            f"{ENTITY_USER_NOTES_BEGIN}\n{user_content}\n{ENTITY_USER_NOTES_END}",
        )
        # Fallback: if empty fence shape did not match, manually rewrite.
        if replaced == original:
            begin_idx = original.index(ENTITY_USER_NOTES_BEGIN) + len(
                ENTITY_USER_NOTES_BEGIN
            )
            end_idx = original.index(ENTITY_USER_NOTES_END, begin_idx)
            replaced = (
                original[:begin_idx]
                + "\n"
                + user_content
                + "\n"
                + original[end_idx:]
            )
        path.write_text(replaced, encoding="utf-8")

        # Re-render with an updated list of actions.
        updated_entity = _sample_entity(
            open_actions=[
                LinkedAction(
                    action_id="act_01HS1",
                    title="Send revised board deck",
                    status="open",
                    commitment_path=(
                        "Commitments/Open/2026/04/send-revised-board-deck-abc1234.md"
                    ),
                ),
            ]
        )
        result = write_entity_note(vault, updated_entity)
        assert result.created is False

        rendered = path.read_text(encoding="utf-8")
        assert "Send revised board deck" in rendered
        # User content preserved.
        assert "I had coffee with Mario about this." in rendered
        assert "Follow up next week." in rendered


def test_write_handles_empty_actions_gracefully():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        ent = _sample_entity(open_actions=[], done_actions=[])
        result = write_entity_note(vault, ent)
        content = result.path.read_text(encoding="utf-8")
        assert "_No open commitments._" in content
        assert "## Completed commitments" not in content


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def main() -> int:
    test("resolve_path_uses_kind_subdir", test_resolve_path_uses_kind_subdir)
    test("resolve_path_rejects_unsafe_slug", test_resolve_path_rejects_unsafe_slug)
    test("resolve_path_rejects_unknown_kind", test_resolve_path_rejects_unknown_kind)
    test("write_creates_note_with_frontmatter", test_write_creates_note_with_frontmatter_and_sections)
    test("write_idempotent_preserves_user_notes", test_write_is_idempotent_and_preserves_user_notes)
    test("write_handles_empty_actions", test_write_handles_empty_actions_gracefully)

    total = PASS + FAIL
    print(f"\n{'=' * 60}")
    print(f"RESULT: {PASS}/{total} passed")
    print(f"{'=' * 60}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
