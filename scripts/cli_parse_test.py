"""Verify CLI argument parsing for key subcommands.

Tests parse_args() behavior without executing any Obsidian commands.
"""

import sys


def test_help_exits_zero():
    """obsx --help should exit 0."""
    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "obsidian_connector", "--help"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, f"--help exited {result.returncode}: {result.stderr}"
    assert "usage:" in result.stdout.lower() or "obsidian" in result.stdout.lower()
    print("PASS: test_help_exits_zero")


def test_subcommand_help():
    """Key subcommands should have --help that exits 0."""
    import subprocess
    subcommands = [
        "search", "read", "tasks", "log-daily", "doctor",
        "today", "close", "ghost", "drift", "ideas",
        "uninstall",
    ]
    for cmd in subcommands:
        result = subprocess.run(
            [sys.executable, "-m", "obsidian_connector", cmd, "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0, (
            f"{cmd} --help exited {result.returncode}: {result.stderr}"
        )
    print(f"PASS: test_subcommand_help ({len(subcommands)} subcommands)")


def test_json_flag_accepted():
    """--json flag should be accepted by commands that support it."""
    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "obsidian_connector", "search", "--json", "--help"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, f"search --json --help failed: {result.stderr}"
    print("PASS: test_json_flag_accepted")


def test_unknown_subcommand_fails():
    """Unknown subcommand should exit non-zero."""
    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "obsidian_connector", "nonexistent-command"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode != 0, "unknown subcommand should fail"
    print("PASS: test_unknown_subcommand_fails")


if __name__ == "__main__":
    test_help_exits_zero()
    test_subcommand_help()
    test_json_flag_accepted()
    test_unknown_subcommand_fails()
    print("\nAll CLI parse tests passed.")
