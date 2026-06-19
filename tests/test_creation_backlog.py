# tests/test_creation_backlog.py
import pytest

from obsidian_connector import creation_backlog as cb
from obsidian_connector import creation_events as ce

T0 = "2026-06-18T00:00:00Z"
T1 = "2026-06-18T01:00:00Z"


def _vault(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    v = tmp_path / "v"
    (v / ".obsidian").mkdir(parents=True)
    return v


def test_add_creates_event_and_note(tmp_path, monkeypatch):
    v = _vault(tmp_path, monkeypatch)
    res = cb.add_backlog_item(v, title="JWKS rotation", project="mcmc-erp",
                              repos=["mcmc-erp", "mcmc-erp-web"], priority="P1",
                              now_iso=T0)
    assert res["id"].startswith("bkl_")
    assert res["path"] == f"Backlog/mcmc-erp/{res['id']}.md"
    assert (v / res["path"]).exists()
    evs = ce.read_events(v)
    assert [e["event_type"] for e in evs] == ["backlog.upserted"]
    assert evs[0]["payload"]["item"]["title"] == "JWKS rotation"


def test_note_frontmatter_is_parser_safe_and_repos_inline(tmp_path, monkeypatch):
    v = _vault(tmp_path, monkeypatch)
    res = cb.add_backlog_item(v, title="t", project="p", repos=["a", "b"],
                              now_iso=T0)
    text = (v / res["path"]).read_text(encoding="utf-8")
    assert 'repos: ["a", "b"]' in text          # inline array, not multiline YAML
    assert "type: backlog-item" in text
    assert "source_commit:" not in text          # None freshness fields omitted
    assert cb._FENCE_BEGIN in text and cb._FENCE_END in text


def test_dry_run_writes_nothing(tmp_path, monkeypatch):
    v = _vault(tmp_path, monkeypatch)
    res = cb.add_backlog_item(v, title="t", project="p", now_iso=T0, dry_run=True)
    assert res["dry_run"] is True
    assert ce.read_events(v) == []
    assert not (v / "Backlog").exists()


def test_list_reduces_latest_per_id_and_filters(tmp_path, monkeypatch):
    v = _vault(tmp_path, monkeypatch)
    a = cb.add_backlog_item(v, title="a", project="x", priority="P0", now_iso=T0)["id"]
    cb.add_backlog_item(v, title="b", project="y", priority="P2", now_iso=T0)
    cb.update_backlog_item(v, item_id=a, now_iso=T1, status="ready")
    rows = cb.list_backlog(v)
    assert len(rows) == 2                         # update did not create a 3rd item
    assert next(r for r in rows if r["id"] == a)["status"] == "ready"
    assert [r["project"] for r in cb.list_backlog(v, project="x")] == ["x"]
    assert cb.list_backlog(v, status="ready")[0]["id"] == a


def test_show_returns_item_or_none(tmp_path, monkeypatch):
    v = _vault(tmp_path, monkeypatch)
    a = cb.add_backlog_item(v, title="a", project="x", now_iso=T0)["id"]
    assert cb.show_backlog_item(v, item_id=a)["title"] == "a"
    assert cb.show_backlog_item(v, item_id="bkl_nope") is None


def test_update_unknown_id_raises(tmp_path, monkeypatch):
    v = _vault(tmp_path, monkeypatch)
    with pytest.raises(KeyError):
        cb.update_backlog_item(v, item_id="bkl_nope", now_iso=T0, status="ready")


def test_update_rejects_bad_enum(tmp_path, monkeypatch):
    v = _vault(tmp_path, monkeypatch)
    a = cb.add_backlog_item(v, title="a", project="x", now_iso=T0)["id"]
    with pytest.raises(ValueError):
        cb.update_backlog_item(v, item_id=a, now_iso=T1, priority="P9")


def test_completion_gate_blocks_done_without_evidence(tmp_path, monkeypatch):
    v = _vault(tmp_path, monkeypatch)
    a = cb.add_backlog_item(v, title="a", project="x", now_iso=T0)["id"]
    with pytest.raises(ValueError, match="repo evidence"):
        cb.update_backlog_item(v, item_id=a, now_iso=T1, status="done")


def test_completion_gate_allows_done_with_commit(tmp_path, monkeypatch):
    v = _vault(tmp_path, monkeypatch)
    a = cb.add_backlog_item(v, title="a", project="x", now_iso=T0)["id"]
    res = cb.update_backlog_item(v, item_id=a, now_iso=T1, status="done",
                                 source_commit="abc1234")
    assert res["status"] == "done"
    assert cb.show_backlog_item(v, item_id=a)["source_commit"] == "abc1234"


def test_rebuild_is_idempotent(tmp_path, monkeypatch):
    v = _vault(tmp_path, monkeypatch)
    res = cb.add_backlog_item(v, title="a", project="x",
                              acceptance_criteria=["c1"], now_iso=T0)
    note = v / res["path"]
    first = note.read_text(encoding="utf-8")
    out = cb.rebuild_backlog(v)
    assert out["count"] == 1 and out["dry_run"] is False
    after_one = note.read_text(encoding="utf-8")
    cb.rebuild_backlog(v)
    after_two = note.read_text(encoding="utf-8")
    assert first == after_one == after_two          # byte-identical across rebuilds


def test_rebuild_preserves_user_notes_fence(tmp_path, monkeypatch):
    v = _vault(tmp_path, monkeypatch)
    res = cb.add_backlog_item(v, title="a", project="x", now_iso=T0)
    note = v / res["path"]
    text = note.read_text(encoding="utf-8")
    text = text.replace(cb._FENCE_BEGIN + "\n\n" + cb._FENCE_END,
                        cb._FENCE_BEGIN + "\nMARIO HAND NOTE\n" + cb._FENCE_END)
    note.write_text(text, encoding="utf-8")
    cb.update_backlog_item(v, item_id=res["id"], now_iso=T1, status="in_progress")
    assert "MARIO HAND NOTE" in note.read_text(encoding="utf-8")
    cb.rebuild_backlog(v)
    assert "MARIO HAND NOTE" in note.read_text(encoding="utf-8")


def test_completion_gate_allows_done_with_pr(tmp_path, monkeypatch):
    v = _vault(tmp_path, monkeypatch)
    a = cb.add_backlog_item(v, title="a", project="x", now_iso=T0)["id"]
    res = cb.update_backlog_item(v, item_id=a, now_iso=T1, status="done",
                                 source_pr="https://github.com/o/r/pull/1")
    assert res["status"] == "done"
    assert cb.show_backlog_item(v, item_id=a)["source_pr"].endswith("/pull/1")


def test_title_and_next_action_with_colon_render_yaml_safe(tmp_path, monkeypatch):
    v = _vault(tmp_path, monkeypatch)
    res = cb.add_backlog_item(v, title="Fix: handle colons", project="x",
                              next_action="do X: then Y", now_iso=T0)
    text = (v / res["path"]).read_text(encoding="utf-8")
    assert 'title: "Fix: handle colons"' in text       # quoted -> valid YAML scalar
    assert 'next_action: "do X: then Y"' in text


def test_update_cannot_change_project(tmp_path, monkeypatch):
    v = _vault(tmp_path, monkeypatch)
    a = cb.add_backlog_item(v, title="a", project="x", now_iso=T0)["id"]
    cb.update_backlog_item(v, item_id=a, now_iso=T1, project="y", status="ready")
    assert cb.show_backlog_item(v, item_id=a)["project"] == "x"


def test_freshness_scalar_newline_does_not_inject_frontmatter(tmp_path, monkeypatch):
    from obsidian_connector.draft_manager import _parse_frontmatter
    v = _vault(tmp_path, monkeypatch)
    res = cb.add_backlog_item(v, title="t", project="x", now_iso=T0,
                              source_pr="real\nsuperseded_by: dec_evil")
    fm = _parse_frontmatter((v / res["path"]).read_text(encoding="utf-8"))
    assert fm.get("superseded_by") != "dec_evil"        # newline escaped, no injection
    assert fm["authority_level"] == "agent_reported_unverified"   # frontmatter intact
