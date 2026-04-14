from __future__ import annotations

"""Smart triage entry point: rule classifier with optional LLM fallback.

Exposes the public triage surface consumed by obsidian-capture-service. The
module intentionally keeps its import surface minimal so it can be depended on
without pulling the full classifier tree; the rule-based classifier is imported
lazily inside :func:`smart_triage` to avoid a circular import.
"""

import dataclasses
from typing import Literal, Protocol, runtime_checkable

Kind = Literal["action", "idea", "raw"]
Source = Literal["rules", "llm", "rules_only_llm_failed", "fallback"]


@dataclasses.dataclass(frozen=True)
class ClassificationResult:
    """Outcome of a triage classification call.

    Attributes:
        kind: The predicted capture kind.
        confidence: Confidence score in the range [0.0, 1.0].
        reason: Human-readable explanation of the decision.
        source: Which path produced this result (rules, llm, fallback, ...).
        slug: Optional project slug when the result is project-scoped.
    """

    kind: Kind
    confidence: float
    reason: str
    source: Source = "rules"
    slug: str | None = None


@runtime_checkable
class LLMClient(Protocol):
    """Optional LLM-backed classifier used when rules are low confidence."""

    def classify(self, text: str) -> ClassificationResult | None:
        ...


def smart_triage(
    text: str,
    *,
    threshold: float = 0.7,
    llm_client: LLMClient | None = None,
) -> ClassificationResult:
    """Classify a capture using rules first, optionally escalating to an LLM.

    The rule-based classifier runs first. If its confidence is at or above
    ``threshold`` the rule result is returned unchanged. Otherwise, when an
    ``llm_client`` is provided, the LLM is consulted as a tiebreaker. Any
    exception in either path falls back to a safe default.
    """

    from obsidian_connector.classifiers.rule_based import RuleBasedClassifier

    try:
        classifier = RuleBasedClassifier()
        rule_result = classifier.classify(text)
    except Exception as exc:
        return ClassificationResult(
            kind="raw",
            confidence=0.0,
            reason=f"rule classifier failed: {exc}",
            source="fallback",
            slug=None,
        )

    if rule_result.confidence >= threshold:
        return rule_result

    if llm_client is not None:
        try:
            llm_result = llm_client.classify(text)
        except Exception:
            return dataclasses.replace(rule_result, source="rules_only_llm_failed")

        if llm_result is None:
            return dataclasses.replace(rule_result, source="rules_only_llm_failed")

        return dataclasses.replace(llm_result, source="llm")

    return rule_result
