# tests/test_creation_events.py
from pathlib import Path
from obsidian_connector import creation_events as ce


def test_append_then_read_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    vault = tmp_path / "v"; vault.mkdir()
    ce.append_event(vault, "session.start", {"repo": "x"},
                    event_id="ses_a", ts_iso="2026-06-18T00:00:00Z", session_id="ses_a")
    ce.append_event(vault, "checkpoint.created", {"n": 1},
                    event_id="chk_b", ts_iso="2026-06-18T00:01:00Z", session_id="ses_a")
    events = ce.read_events(vault)
    assert [e["event_type"] for e in events] == ["session.start", "checkpoint.created"]
    assert events[0]["payload"]["repo"] == "x"
    assert events[1]["session_id"] == "ses_a"


def test_read_tolerates_malformed_lines(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    vault = tmp_path / "v"; vault.mkdir()
    ce.append_event(vault, "session.start", {},
                    event_id="ses_a", ts_iso="2026-06-18T00:00:00Z")
    from obsidian_connector import creation_paths
    with creation_paths.events_path(vault).open("a") as fh:
        fh.write("this is not json\n")
    events = ce.read_events(vault)
    assert len(events) == 1                       # malformed line skipped, valid kept


def test_unknown_event_type_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    vault = tmp_path / "v"; vault.mkdir()
    import pytest
    with pytest.raises(ValueError, match="event_type"):
        ce.append_event(vault, "totally.bogus", {}, event_id="x", ts_iso="t")
