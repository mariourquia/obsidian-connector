# tests/test_creation_session.py
from obsidian_connector import creation_session as csess
from obsidian_connector import creation_events as ce


def test_start_creates_active_marker_and_event(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    vault = tmp_path / "v"; (vault / ".obsidian").mkdir(parents=True)
    res = csess.start_session(vault, repo="mcmc-erp", branch="main",
                              now_iso="2026-06-18T00:00:00Z")
    sid = res["session_id"]
    assert sid.startswith("ses_")
    assert csess.active_session(vault) == sid
    assert (vault / "sessions" / f"{sid}.md").exists()
    assert ce.read_events(vault)[0]["event_type"] == "session.start"


def test_end_clears_active_marker(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    vault = tmp_path / "v"; (vault / ".obsidian").mkdir(parents=True)
    sid = csess.start_session(vault, repo="x", branch="main",
                              now_iso="2026-06-18T00:00:00Z")["session_id"]
    csess.end_session(vault, session_id=sid, report="done", next_action="ship",
                      now_iso="2026-06-18T01:00:00Z")
    assert csess.active_session(vault) is None
    types = [e["event_type"] for e in ce.read_events(vault)]
    assert types == ["session.start", "session.end"]


def test_dry_run_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    vault = tmp_path / "v"; (vault / ".obsidian").mkdir(parents=True)
    res = csess.start_session(vault, repo="x", branch="main",
                              now_iso="2026-06-18T00:00:00Z", dry_run=True)
    assert res["dry_run"] is True
    assert csess.active_session(vault) is None
    assert ce.read_events(vault) == []
