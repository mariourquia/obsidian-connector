"""Unit tests for the RuleBasedClassifier used by smart triage.

Mirrors the capture-service classifier test suite. The classifier is the
deterministic fallback when the LLM-backed path is unavailable or
low-confidence, so its behavior on imperative verbs, idea markers, and
empty input must stay stable across releases.
"""
from __future__ import annotations

import pytest

from obsidian_connector.classifiers.rule_based import RuleBasedClassifier
from obsidian_connector.smart_triage import ClassificationResult


@pytest.fixture
def clf() -> RuleBasedClassifier:
    return RuleBasedClassifier()


# -- Actions ---------------------------------------------------------------


@pytest.mark.parametrize("text", [
    "Send the report to Alex by Friday",
    "Fix the auth timeout bug",
    "Email the investors the pitch deck tomorrow",
    "Call the accountant at 3pm",
    "Review PR #5 by end of day",
])
def test_imperative_plus_due_scores_action(clf, text):
    result = clf.classify(text)
    assert result.kind == "action"
    assert result.confidence >= 0.5


def test_imperative_alone_is_action_medium_confidence(clf):
    result = clf.classify("Send the report to Alex")
    assert result.kind == "action"
    assert 0.5 <= result.confidence < 1.0


def test_due_phrase_alone_without_imperative_is_raw(clf):
    # "the meeting is tomorrow" has a due phrase but no imperative verb,
    # so it should not be classified as an action.
    result = clf.classify("the meeting is tomorrow")
    assert result.kind == "raw"


# -- Ideas -----------------------------------------------------------------


@pytest.mark.parametrize("text", [
    "Idea: a voice-controlled deal-screening tool",
    "What if we added slug detection to the capture service?",
    "Should we migrate to a different database?",
    "Thought: the vault could sync via Git instead of iCloud",
    "I wonder if fuzzy matching would miss edge cases",
])
def test_idea_markers_score_idea(clf, text):
    result = clf.classify(text)
    assert result.kind == "idea"
    assert result.confidence >= 0.5


def test_idea_marker_beats_trailing_imperative(clf):
    # "Idea: build X" would otherwise trigger on "build" as an imperative.
    # The idea marker must win.
    result = clf.classify("Idea: build a commitment dashboard")
    assert result.kind == "idea"


# -- Raw / ambiguous -------------------------------------------------------


@pytest.mark.parametrize("text", [
    "The weather has been really nice lately",
    "Random thought about the quarterly report",
    "This is a test",
])
def test_no_strong_signal_is_raw(clf, text):
    result = clf.classify(text)
    assert result.kind == "raw"
    assert result.confidence < 0.5


def test_empty_transcript_is_raw_zero_confidence(clf):
    result = clf.classify("")
    assert result.kind == "raw"
    assert result.confidence == 0.0


def test_whitespace_transcript_is_raw_zero_confidence(clf):
    result = clf.classify("   \n\t  ")
    assert result.kind == "raw"
    assert result.confidence == 0.0


# -- Structure -------------------------------------------------------------


def test_result_has_reason_field(clf):
    result = clf.classify("Fix the auth bug tomorrow")
    assert isinstance(result, ClassificationResult)
    assert result.reason
    assert result.slug is None


@pytest.mark.parametrize("text", [
    "Send the report to Alex by Friday",
    "Idea: a voice-controlled deal-screening tool",
    "The weather has been really nice lately",
    "",
    "   ",
])
def test_every_result_has_source_rules(clf, text):
    """The rule-based classifier always tags its own output as ``source='rules'``."""
    result = clf.classify(text)
    assert result.source == "rules"
