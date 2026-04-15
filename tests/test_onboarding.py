"""Tests for the connector-side onboarding walkthrough (Task 34)."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from obsidian_connector.onboarding import (
    ONBOARDING_STEPS,
    OnboardingStep,
    format_onboarding,
    get_onboarding_payload,
)


def test_onboarding_payload_has_six_stable_steps():
    """The walkthrough shipped in Task 34 has exactly six ordered steps."""

    payload = get_onboarding_payload()
    assert payload["version"] == 1
    assert payload["total_steps"] == 6
    assert len(payload["steps"]) == 6

    titles = [step["title"] for step in payload["steps"]]
    expected = [
        "Vault setup",
        "Capture-service URL",
        "Bearer token",
        "MCP registration",
        "First sync",
        "Verify",
    ]
    assert titles == expected

    # Indices must be contiguous 1..6 so renderers can loop safely.
    assert [s["index"] for s in payload["steps"]] == [1, 2, 3, 4, 5, 6]


def test_onboarding_steps_all_have_at_least_one_command():
    """Every step ships at least one concrete command so the CLI is useful."""

    for step in ONBOARDING_STEPS:
        assert isinstance(step, OnboardingStep)
        assert step.commands, f"step {step.index} missing commands"


def test_format_onboarding_contains_headings_and_command_lines():
    """Human format surfaces both step headings and shell commands."""

    rendered = format_onboarding()
    assert "obsidian-connector onboarding walkthrough" in rendered
    assert "Step 1: Vault setup" in rendered
    assert "Step 6: Verify" in rendered
    assert "$ obsx init" in rendered
    assert "$ obsx doctor" in rendered


def test_cli_onboarding_subcommand_json(tmp_path, monkeypatch):
    """`obsx onboarding --json` emits the canonical payload shape."""

    monkeypatch.setenv("OBSIDIAN_VAULT", str(tmp_path))
    # Prevent config load from hitting real disk state.
    monkeypatch.setenv("HOME", str(tmp_path))

    result = subprocess.run(
        [sys.executable, "-m", "obsidian_connector.cli", "onboarding", "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    # Strip possible trailing log lines from the envelope.
    stdout = result.stdout.strip()
    payload = None
    for blob in (stdout, stdout.splitlines()[-1] if stdout else ""):
        try:
            payload = json.loads(blob)
            break
        except json.JSONDecodeError:
            continue
    assert payload is not None, f"no JSON in stdout: {stdout!r}"
    # Connector CLI wraps output in a {"ok", "data", ...} envelope.
    data = payload.get("data", payload)
    assert data["total_steps"] == 6
    assert len(data["steps"]) == 6
    assert data["steps"][0]["title"] == "Vault setup"


def test_cli_onboarding_subcommand_human(tmp_path, monkeypatch):
    """Default (non-JSON) output is human-readable with step headings."""

    monkeypatch.setenv("OBSIDIAN_VAULT", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))

    result = subprocess.run(
        [sys.executable, "-m", "obsidian_connector.cli", "onboarding"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "Step 1: Vault setup" in result.stdout
    assert "docs/ONBOARDING.md" in result.stdout
