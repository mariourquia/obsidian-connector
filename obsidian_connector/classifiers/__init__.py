"""Deterministic classifiers for routing captures to vault destinations.

Exposes rule-based classifiers that decide whether a capture is an
``action``, an ``idea``, or unstructured ``raw`` text. These run offline,
have no external dependencies, and serve as the deterministic fallback
when the connector's smart-triage path is unavailable or low-confidence.
"""

from __future__ import annotations

from obsidian_connector.classifiers.rule_based import RuleBasedClassifier

__all__ = ["RuleBasedClassifier"]
