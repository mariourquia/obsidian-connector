# tests/test_creation_freshness.py
from obsidian_connector import creation_schema as cs
from obsidian_connector import creation_freshness as cf


def _f(**kw):
    base = dict(id="bkl_x", authority_level="repo_grounded")
    base.update(kw)
    return cs.Freshness(**base)


def test_repo_commit_staleness():
    f = _f(staleness_policy="repo-commit", source_commit="abc")
    assert cf.is_stale(f, repo_head="abc") is False
    assert cf.is_stale(f, repo_head="def") is True            # HEAD moved -> stale


def test_ttl_staleness():
    f = _f(staleness_policy="ttl", valid_until="2026-06-20")
    assert cf.is_stale(f, now_iso="2026-06-19") is False
    assert cf.is_stale(f, now_iso="2026-06-25") is True


def test_resolve_label_downgrades_stale():
    f = _f(staleness_policy="repo-commit", source_commit="abc")
    assert cf.resolve_label(f, repo_head="def") == "stale_needs_review"
    assert cf.resolve_label(f, repo_head="abc") == "repo_grounded"


def test_can_complete_requires_evidence():
    ok, _ = cf.can_complete(_f(source_commit="abc"))
    assert ok is True
    ok, reason = cf.can_complete(_f())                         # no commit, no PR
    assert ok is False and "evidence" in reason.lower()
