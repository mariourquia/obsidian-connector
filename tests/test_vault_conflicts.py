"""Tests for obsidian_connector.vault_conflicts (Task 37)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from obsidian_connector.vault_conflicts import (
    ConflictFile,
    detect_vault_conflicts,
)


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    """Empty vault with just an .obsidian marker."""
    (tmp_path / ".obsidian").mkdir()
    return tmp_path


def _write(vault: Path, rel: str, body: str = "x") -> Path:
    p = vault / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Envelope shape
# ---------------------------------------------------------------------------


def test_missing_vault_returns_envelope_error(tmp_path: Path) -> None:
    result = detect_vault_conflicts(tmp_path / "does-not-exist")
    assert result["ok"] is False
    assert "vault_root" in result["error"]


def test_file_path_rejected(tmp_path: Path) -> None:
    f = tmp_path / "file.md"
    f.write_text("x")
    result = detect_vault_conflicts(f)
    assert result["ok"] is False


def test_empty_vault(vault: Path) -> None:
    result = detect_vault_conflicts(vault)
    assert result["ok"] is True
    assert result["items"] == []
    assert result["scanned"] == 0


def test_clean_vault_no_conflicts(vault: Path) -> None:
    _write(vault, "Inbox/Note.md")
    _write(vault, "Projects/Hello.md")
    result = detect_vault_conflicts(vault)
    assert result["ok"] is True
    assert result["items"] == []
    assert result["scanned"] == 2


# ---------------------------------------------------------------------------
# Per-provider patterns
# ---------------------------------------------------------------------------


def test_dropbox_conflict_detected(vault: Path) -> None:
    _write(vault, "Note.md")
    _write(vault, "Note (Mario's conflicted copy 2026-04-15).md")
    result = detect_vault_conflicts(vault)
    assert result["ok"] is True
    assert len(result["items"]) == 1
    item = result["items"][0]
    assert item["provider"] == "Dropbox"
    assert item["relative_path"] == "Note (Mario's conflicted copy 2026-04-15).md"


def test_icloud_iphone_variant_detected(vault: Path) -> None:
    _write(vault, "Note.md")
    _write(vault, "Note (Mario's iPhone).md")
    result = detect_vault_conflicts(vault)
    providers = {item["provider"] for item in result["items"]}
    assert providers == {"iCloud Drive"}


def test_onedrive_suffix_detected(vault: Path) -> None:
    _write(vault, "Note.md")
    _write(vault, "Note-DESKTOP-ABC.md")
    result = detect_vault_conflicts(vault)
    providers = {item["provider"] for item in result["items"]}
    assert providers == {"OneDrive"}


def test_obsidian_sync_hex_suffix_detected(vault: Path) -> None:
    _write(vault, "Note.md")
    _write(vault, "Note (abc12345).md")
    result = detect_vault_conflicts(vault)
    providers = {item["provider"] for item in result["items"]}
    assert providers == {"Obsidian Sync"}


# ---------------------------------------------------------------------------
# iCloud weak-signal resolver: " 2.md" only flags when a twin exists.
# ---------------------------------------------------------------------------


def test_icloud_weak_signal_requires_twin(vault: Path) -> None:
    """'Note 2.md' without 'Note.md' alongside is NOT a conflict.

    Users deliberately name files like "Draft 2". Only the pair
    pattern gets flagged.
    """
    _write(vault, "Draft 2.md")  # No twin "Draft.md"
    result = detect_vault_conflicts(vault)
    assert result["items"] == []


def test_icloud_weak_signal_with_twin_flags_as_icloud(vault: Path) -> None:
    _write(vault, "Note.md")
    _write(vault, "Note 2.md")
    result = detect_vault_conflicts(vault)
    assert len(result["items"]) == 1
    item = result["items"][0]
    assert item["provider"] == "iCloud Drive"
    # Weak-signal bucket was promoted to canonical iCloud Drive label.
    assert item["provider"] != "iCloud Drive (weak)"


# ---------------------------------------------------------------------------
# Skip rules
# ---------------------------------------------------------------------------


def test_dot_git_is_skipped(vault: Path) -> None:
    _write(vault, "Note.md")
    _write(vault, ".git/foo (Mario's conflicted copy 2026-04-15).md")
    result = detect_vault_conflicts(vault)
    # .git/ contents are skipped even if filename matches a pattern.
    assert all(".git" not in item["relative_path"] for item in result["items"])


def test_dot_obsidian_is_skipped(vault: Path) -> None:
    _write(vault, ".obsidian/workspace (Mario's iPhone).md")
    result = detect_vault_conflicts(vault)
    assert result["items"] == []


def test_underscore_prefixed_dirs_skipped(vault: Path) -> None:
    _write(vault, "_archive/Note (Mario's iPhone).md")
    result = detect_vault_conflicts(vault)
    assert result["items"] == []


def test_trash_is_skipped(vault: Path) -> None:
    _write(vault, ".trash/Note (Mario's conflicted copy 2026-04-15).md")
    result = detect_vault_conflicts(vault)
    assert result["items"] == []


# ---------------------------------------------------------------------------
# Determinism + JSON round-trip
# ---------------------------------------------------------------------------


def test_output_is_sorted_and_json_serializable(vault: Path) -> None:
    _write(vault, "Z.md")
    _write(vault, "A.md")
    _write(vault, "Z (Mario's iPhone).md")
    _write(vault, "A (Mario's iPhone).md")
    result = detect_vault_conflicts(vault)
    rels = [item["relative_path"] for item in result["items"]]
    assert rels == sorted(rels)
    # Envelope is JSON-serializable -- important for MCP / CLI --json.
    assert json.loads(json.dumps(result)) == result


def test_conflict_file_to_dict() -> None:
    cf = ConflictFile(
        relative_path="Note (Mario's iPhone).md",
        provider="iCloud Drive",
        pattern_label="(... iPhone)",
        size_bytes=42,
    )
    assert cf.to_dict() == {
        "relative_path": "Note (Mario's iPhone).md",
        "provider": "iCloud Drive",
        "pattern_label": "(... iPhone)",
        "size_bytes": 42,
    }


def test_size_bytes_populated(vault: Path) -> None:
    _write(vault, "Note.md", body="hello world body" * 10)
    _write(vault, "Note (Mario's iPhone).md", body="conflict")
    result = detect_vault_conflicts(vault)
    assert len(result["items"]) == 1
    assert result["items"][0]["size_bytes"] == len("conflict")
