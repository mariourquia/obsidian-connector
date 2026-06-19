# tests/test_creation_status.py
from obsidian_connector import creation_status as cstat
from obsidian_connector import creation_session as csess


def test_status_reports_active_session_and_event_count(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    vault = tmp_path / "v"; (vault / ".obsidian").mkdir(parents=True)
    sid = csess.start_session(vault, repo="x", branch="main",
                              now_iso="2026-06-18T00:00:00Z")["session_id"]
    st = cstat.creation_status(vault)
    assert st["active_session"] == sid
    assert st["event_count"] == 1


def test_freshness_audit_flags_stale_backlog(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    vault = tmp_path / "v"; (vault / "Backlog" / "mcmc").mkdir(parents=True)
    (vault / "Backlog" / "mcmc" / "bkl_x.md").write_text(
        "---\nid: bkl_x\ntype: backlog-item\nauthority_level: repo_grounded\n"
        "staleness_policy: repo-commit\nsource_repo: mcmc-erp\nsource_commit: abc\n---\n",
        encoding="utf-8")
    audit = cstat.freshness_audit(vault, repo_heads={"mcmc-erp": "def"})
    assert "bkl_x" in [i["id"] for i in audit["stale"]]
