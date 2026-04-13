"""pytest wrappers for all obsidian-connector test suites.

Each test runs the original script as a subprocess and asserts
"0 failed" in the output.  This gives pytest discovery, CI reporting,
and parallel execution while preserving all 441+ original assertions.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"

_SUITES = [
    "write_manager_test.py",
    "watcher_test.py",
    "draft_manager_test.py",
    "vault_registry_test.py",
    "template_test.py",
    "retrieval_test.py",
    "scheduler_test.py",
    "reports_test.py",
    "project_intelligence_test.py",
    "automation_test.py",
    "commitment_notes_test.py",
    "commitment_ops_test.py",
    "commitment_dashboards_test.py",
]


def _run_suite(name: str) -> None:
    script = SCRIPTS_DIR / name
    assert script.exists(), f"Test script not found: {script}"
    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True, text=True, timeout=120,
        cwd=str(SCRIPTS_DIR.parent),
    )
    # Extract results line
    output = result.stdout + result.stderr
    assert "0 failed" in output, (
        f"{name} had failures:\n"
        f"stdout: {result.stdout[-500:]}\n"
        f"stderr: {result.stderr[-500:]}"
    )


@pytest.mark.parametrize("suite", _SUITES, ids=[s.replace("_test.py", "") for s in _SUITES])
def test_suite(suite: str) -> None:
    _run_suite(suite)
