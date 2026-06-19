# tests/test_creation_schema.py
import pytest
from obsidian_connector import creation_schema as cs


def test_status_labels_exact():
    assert cs.STATUS_LABELS == (
        "verified_current", "fresh_user_instruction", "repo_grounded",
        "agent_reported_unverified", "stale_needs_review", "deprecated", "conflicting",
    )


def test_new_id_deterministic_and_prefixed():
    a = cs.new_id("bkl", "2026-06-18T00:00:00Z|0|hello")
    b = cs.new_id("bkl", "2026-06-18T00:00:00Z|0|hello")
    c = cs.new_id("bkl", "2026-06-18T00:00:00Z|1|hello")
    assert a == b and a != c
    assert a.startswith("bkl_")


def test_freshness_round_trip_defaults_and_unknown_keys():
    f = cs.Freshness(id="bkl_x", authority_level="repo_grounded", source_commit="abc1234")
    d = cs.freshness_to_dict(f)
    d["totally_unknown"] = "ignore me"          # tolerate forward-compat keys
    back = cs.freshness_from_dict(d)
    assert back.id == "bkl_x"
    assert back.authority_level == "repo_grounded"
    assert back.source_commit == "abc1234"
    assert back.staleness_policy == "manual"     # defaulted
    assert back.supersedes == ()


def test_freshness_rejects_unknown_authority_level():
    with pytest.raises(ValueError, match="authority_level"):
        cs.Freshness(id="x", authority_level="totally-made-up")
