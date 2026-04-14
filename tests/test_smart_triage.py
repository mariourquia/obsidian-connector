"""Unit tests for ``obsidian_connector.smart_triage``.

Covers every branch of the triage decision tree: high-confidence rules win,
low-confidence rules escalate to the LLM, LLM failures gracefully degrade to
the rule result tagged ``rules_only_llm_failed``, and a hard crash in the
rule classifier falls back to a safe ``raw`` result.

The tests use a small :class:`FakeLLMClient` helper rather than a real LLM so
that every branch is deterministic.
"""
from __future__ import annotations

import dataclasses
from typing import Callable

import pytest

from obsidian_connector import smart_triage as smart_triage_module
from obsidian_connector.classifiers.rule_based import RuleBasedClassifier
from obsidian_connector.smart_triage import (
    ClassificationResult,
    LLMClient,
    smart_triage,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class FakeLLMClient:
    """Configurable stand-in for the optional LLM client.

    Behaviour:
      * ``return_value`` is returned from ``classify`` when set.
      * ``raise_exc`` is raised from ``classify`` when set. Takes precedence
        over ``return_value``.
      * ``calls`` records each invocation's input text.
    """

    return_value: ClassificationResult | None = None
    raise_exc: BaseException | None = None
    calls: list[str] = dataclasses.field(default_factory=list)

    def classify(self, text: str) -> ClassificationResult | None:
        self.calls.append(text)
        if self.raise_exc is not None:
            raise self.raise_exc
        return self.return_value


def _patch_rule_classify(
    monkeypatch: pytest.MonkeyPatch,
    behaviour: Callable[[RuleBasedClassifier, str], ClassificationResult],
) -> None:
    """Monkeypatch the rule-based classifier used by smart_triage.

    ``smart_triage`` imports ``RuleBasedClassifier`` lazily inside the
    function body, so patching the class method itself covers both the
    module-level import and any lazy re-import.
    """
    monkeypatch.setattr(RuleBasedClassifier, "classify", behaviour, raising=True)


# ---------------------------------------------------------------------------
# Rules win path
# ---------------------------------------------------------------------------


def test_smart_triage_returns_rules_when_confidence_meets_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    preset = ClassificationResult(
        kind="action",
        confidence=0.9,
        reason="imperative:send,due_phrase",
        source="rules",
    )
    _patch_rule_classify(monkeypatch, lambda self, text: preset)

    result = smart_triage("Send the report to Alex by Friday", threshold=0.7)

    assert result is preset or result == preset
    assert result.source == "rules"
    assert result.kind == "action"
    assert result.confidence == 0.9


def test_smart_triage_without_llm_client_returns_low_confidence_rules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Below threshold with no LLM available: return rule result unchanged."""
    preset = ClassificationResult(
        kind="raw",
        confidence=0.3,
        reason="none",
        source="rules",
    )
    _patch_rule_classify(monkeypatch, lambda self, text: preset)

    result = smart_triage("random musings", threshold=0.7, llm_client=None)

    assert result == preset
    assert result.source == "rules"
    assert result.confidence == 0.3


# ---------------------------------------------------------------------------
# LLM fallback path
# ---------------------------------------------------------------------------


def test_smart_triage_calls_llm_when_confidence_below_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rule_preset = ClassificationResult(
        kind="raw",
        confidence=0.3,
        reason="none",
        source="rules",
    )
    llm_preset = ClassificationResult(
        kind="idea",
        confidence=0.85,
        reason="llm:semantic",
        source="rules",  # smart_triage should rewrite this to "llm"
        slug=None,
    )
    _patch_rule_classify(monkeypatch, lambda self, text: rule_preset)
    llm = FakeLLMClient(return_value=llm_preset)

    result = smart_triage("random musings", threshold=0.7, llm_client=llm)

    assert llm.calls == ["random musings"]
    assert result.source == "llm"
    assert result.kind == "idea"
    assert result.confidence == 0.85


def test_smart_triage_returns_rules_only_llm_failed_when_llm_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rule_preset = ClassificationResult(
        kind="action",
        confidence=0.3,
        reason="imperative:send",
        source="rules",
    )
    _patch_rule_classify(monkeypatch, lambda self, text: rule_preset)
    llm = FakeLLMClient(raise_exc=RuntimeError("llm down"))

    result = smart_triage("send maybe", threshold=0.7, llm_client=llm)

    assert result.source == "rules_only_llm_failed"
    assert result.kind == rule_preset.kind
    assert result.confidence == rule_preset.confidence
    assert result.reason == rule_preset.reason


def test_smart_triage_returns_rules_only_llm_failed_when_llm_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rule_preset = ClassificationResult(
        kind="action",
        confidence=0.4,
        reason="imperative:send",
        source="rules",
    )
    _patch_rule_classify(monkeypatch, lambda self, text: rule_preset)
    llm = FakeLLMClient(return_value=None)

    result = smart_triage("send maybe", threshold=0.7, llm_client=llm)

    assert result.source == "rules_only_llm_failed"
    assert result.kind == rule_preset.kind
    assert result.confidence == rule_preset.confidence
    assert result.reason == rule_preset.reason


# ---------------------------------------------------------------------------
# Fallback path (rules crash)
# ---------------------------------------------------------------------------


def test_smart_triage_returns_fallback_when_rules_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom(self: RuleBasedClassifier, text: str) -> ClassificationResult:
        raise RuntimeError("rule engine crashed")

    _patch_rule_classify(monkeypatch, _boom)

    result = smart_triage("anything", threshold=0.7)

    assert result.source == "fallback"
    assert result.kind == "raw"
    assert result.confidence == 0.0
    assert "rule classifier failed" in result.reason


def test_smart_triage_fallback_suppresses_llm_when_rules_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When rules crash we short-circuit before consulting the LLM."""

    def _boom(self: RuleBasedClassifier, text: str) -> ClassificationResult:
        raise RuntimeError("rule engine crashed")

    _patch_rule_classify(monkeypatch, _boom)
    llm = FakeLLMClient(
        return_value=ClassificationResult(
            kind="idea",
            confidence=0.99,
            reason="llm",
            source="rules",
        )
    )

    result = smart_triage("anything", threshold=0.7, llm_client=llm)

    assert result.source == "fallback"
    assert llm.calls == []


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


def test_llm_client_protocol_is_runtime_checkable() -> None:
    fake = FakeLLMClient(
        return_value=ClassificationResult(
            kind="raw",
            confidence=0.0,
            reason="stub",
            source="rules",
        )
    )
    assert isinstance(fake, LLMClient)


def test_classification_result_is_frozen() -> None:
    """Freezing the dataclass prevents accidental mutation downstream."""
    cr = ClassificationResult(
        kind="raw",
        confidence=0.0,
        reason="r",
        source="rules",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        cr.kind = "action"  # type: ignore[misc]


def test_module_exports_expected_symbols() -> None:
    """Sanity check that the public surface stays stable."""
    for name in ("smart_triage", "ClassificationResult", "LLMClient"):
        assert hasattr(smart_triage_module, name), name
