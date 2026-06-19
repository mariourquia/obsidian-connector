"""Tests for the creation-vault-freshness-guard skill (Task 8)."""
from pathlib import Path

SKILL = Path("src/skills/creation-vault-freshness-guard/SKILL.md")


def test_skill_exists_with_frontmatter():
    assert SKILL.exists(), f"Expected {SKILL} to exist"
    text = SKILL.read_text(encoding="utf-8")
    assert text.startswith("---")
    assert "name: creation-vault-freshness-guard" in text
    assert "description:" in text


def test_skill_has_required_sections():
    text = SKILL.read_text(encoding="utf-8")
    # Should reference the key CLI commands
    assert "freshness-audit" in text
    assert "creation status" in text


def test_skill_frontmatter_closes_properly():
    text = SKILL.read_text(encoding="utf-8")
    # Frontmatter must open AND close with ---
    lines = text.splitlines()
    assert lines[0] == "---"
    close_idx = next((i for i, l in enumerate(lines[1:], 1) if l == "---"), None)
    assert close_idx is not None, "Frontmatter must be closed with ---"
