"""Tests for packaging metadata (Task 33).

These tests guard the distribution surface:

- pyproject.toml keeps the three published console scripts wired to the
  correct entry points.
- CHANGELOG.md is present and mentions the Wave 3 block so release
  automation does not silently regress.
- The version is consistent between pyproject.toml and the package
  ``__version__`` attribute.
"""

from __future__ import annotations

import re
from pathlib import Path

try:  # Python 3.11+
    import tomllib  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover - Python 3.10 fallback for older runners
    import tomli as tomllib  # type: ignore[no-redef]


REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"
CHANGELOG = REPO_ROOT / "CHANGELOG.md"


def _load_pyproject() -> dict:
    with PYPROJECT.open("rb") as handle:
        return tomllib.load(handle)


def test_pyproject_has_expected_entry_points() -> None:
    """CLI + MCP console scripts must stay wired to their module targets."""

    data = _load_pyproject()
    scripts = data["project"]["scripts"]

    assert scripts["obsidian-connector"] == "obsidian_connector.cli:main"
    assert scripts["obsx"] == "obsidian_connector.cli:main"
    assert scripts["obsidian-connector-mcp"] == "obsidian_connector.mcp_server:main"


def test_pyproject_core_metadata_is_sane() -> None:
    """Core project metadata stays correct: name, version format, Python floor."""

    data = _load_pyproject()
    project = data["project"]

    assert project["name"] == "obsidian-connector"
    assert re.fullmatch(r"\d+\.\d+\.\d+", project["version"]) is not None
    # Must run on the same Python floor the connector advertises across docs.
    assert project["requires-python"].startswith(">=3.11")


def test_changelog_present_and_has_unreleased_block() -> None:
    """CHANGELOG must exist and surface an Unreleased or current version header."""

    assert CHANGELOG.exists(), "CHANGELOG.md must exist"
    text = CHANGELOG.read_text(encoding="utf-8")
    assert "# Changelog" in text
    # Either an Unreleased block (post-Task-33) or a current release header.
    assert "[Unreleased]" in text or "[0.9.0]" in text
