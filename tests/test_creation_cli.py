"""Tests for the `creation` CLI subcommand group (Task 7)."""
import json
import subprocess
import sys


def _run(args, env_home, vault):
    return subprocess.run(
        [sys.executable, "-m", "obsidian_connector.cli", "--json", "--vault", str(vault), *args],
        capture_output=True,
        text=True,
        env={"HOME": str(env_home), "PATH": __import__("os").environ["PATH"]},
    )


def test_creation_status_json_envelope(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    vault = tmp_path / "v"
    (vault / ".obsidian").mkdir(parents=True)
    p = _run(["creation", "status"], home, vault)
    assert p.returncode == 0, p.stderr
    env = json.loads(p.stdout)
    assert env["ok"] is True
    assert env["command"].startswith("creation")
    assert "active_session" in env["data"]


def test_creation_sync_start_dry_run_default(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    vault = tmp_path / "v"
    (vault / ".obsidian").mkdir(parents=True)
    p = _run(["creation", "sync", "start", "--repo", "x", "--branch", "main"], home, vault)
    assert p.returncode == 0, p.stderr
    env = json.loads(p.stdout)
    assert env["ok"] is True
    assert env["data"]["dry_run"] is True  # default is dry-run
    assert not (vault / "sessions" / "_active.md").exists()


def test_creation_freshness_audit_json_envelope(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    vault = tmp_path / "v"
    (vault / ".obsidian").mkdir(parents=True)
    p = _run(["creation", "freshness-audit"], home, vault)
    assert p.returncode == 0, p.stderr
    env = json.loads(p.stdout)
    assert env["ok"] is True
    assert "stale" in env["data"]
    assert "checked" in env["data"]


def test_creation_sync_start_with_allow_write(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    vault = tmp_path / "v"
    (vault / ".obsidian").mkdir(parents=True)
    p = _run(
        ["creation", "sync", "start", "--repo", "mcmc-erp", "--branch", "main", "--allow-write"],
        home,
        vault,
    )
    assert p.returncode == 0, p.stderr
    env = json.loads(p.stdout)
    assert env["ok"] is True
    assert env["data"]["dry_run"] is False
    sid = env["data"]["session_id"]
    assert sid.startswith("ses_")
    assert (vault / "sessions" / f"{sid}.md").exists()


def _run_no_json(args, env_home, vault):
    """Run CLI without --json so the early-return paths that print to stderr are reachable."""
    return subprocess.run(
        [sys.executable, "-m", "obsidian_connector.cli", "--vault", str(vault), *args],
        capture_output=True,
        text=True,
        env={"HOME": str(env_home), "PATH": __import__("os").environ["PATH"]},
    )


def test_creation_no_subcommand_exits_nonzero(tmp_path):
    """Invoking `creation` with no sub-command must exit 1 and print usage to stderr."""
    home = tmp_path / "home"
    home.mkdir()
    vault = tmp_path / "v"
    (vault / ".obsidian").mkdir(parents=True)
    p = _run_no_json(["creation"], home, vault)
    assert p.returncode == 1
    assert "Usage:" in p.stderr


def test_creation_sync_no_subcommand_exits_nonzero(tmp_path):
    """Invoking `creation sync` with no sub-command must exit 1 and print usage to stderr."""
    home = tmp_path / "home"
    home.mkdir()
    vault = tmp_path / "v"
    (vault / ".obsidian").mkdir(parents=True)
    p = _run_no_json(["creation", "sync"], home, vault)
    assert p.returncode == 1
    assert "Usage:" in p.stderr


def test_mcp_creation_status_passthrough(tmp_path, monkeypatch):
    """MCP obsidian_creation_status tool returns the raw creation_status() dict (not the CLI envelope)."""
    home = tmp_path / "home"
    home.mkdir()
    vault = tmp_path / "v"
    (vault / ".obsidian").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(vault))
    from obsidian_connector.mcp_server import obsidian_creation_status

    raw = obsidian_creation_status()  # uses OBSIDIAN_VAULT_PATH env var
    result = json.loads(raw)
    assert "active_session" in result
    assert "event_count" in result
