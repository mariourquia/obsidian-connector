"""Deterministic rule-based capture classifier.

Classifies free-text captures into ``action``, ``idea``, or ``raw`` with a
confidence score in ``[0.0, 1.0]``. Used as the deterministic fallback
when a smart-triage path is unavailable or returns low confidence.

Signals are additive. Scoring is intentionally simple so behavior stays
predictable when reading transcripts. Tune the thresholds or rule set in
this module; consumers read results via :class:`ClassificationResult`.
"""

from __future__ import annotations

import logging
import re
from typing import Literal

from obsidian_connector.smart_triage import ClassificationResult

logger = logging.getLogger(__name__)

Kind = Literal["action", "idea", "raw"]


# ---------------------------------------------------------------------------
# Tunable constants (formerly scattered or derived from capture-service config)
# ---------------------------------------------------------------------------

# Weight awarded to an idea marker ("idea:", "what if", "i wonder", ...).
_SCORE_IDEA_MARKER: float = 0.6

# Weight awarded to a sentence starting with a known imperative verb.
_SCORE_IMPERATIVE_START: float = 0.5

# Weight awarded when a due-date-like phrase is detected ("by tomorrow", ...).
_SCORE_DUE_PHRASE: float = 0.4

# Weight awarded to a question opener ("how", "why", "what", ...).
_SCORE_QUESTION_OPENER: float = 0.3

# Minimum combined score required to commit to an ``action`` classification.
_ACTION_MIN_SCORE: float = 0.5

# Minimum combined score required to commit to an ``idea`` classification.
_IDEA_MIN_SCORE: float = 0.5

# Confidence assigned to the ``raw`` fallback so a downstream reprocess pass
# can tell a hedge from a true empty classification.
_RAW_FALLBACK_CONFIDENCE: float = 0.3


# ---------------------------------------------------------------------------
# Rule patterns
# ---------------------------------------------------------------------------

# Imperative verbs that signal an action when they appear at the start of a
# sentence. Duplicated here deliberately so classification does not depend on
# any external extractor's rule set.
_IMPERATIVES: frozenset[str] = frozenset({
    "add", "arrange", "book", "buy", "call", "cancel", "check", "confirm",
    "draft", "edit", "email", "finalize", "finish", "fix", "follow", "investigate",
    "meet", "message", "order", "organize", "pay", "ping", "plan", "prepare",
    "purchase", "read", "remind", "research", "reserve", "review", "schedule",
    "send", "ship", "submit", "text", "update", "verify", "write", "do",
})

_IMPERATIVE_START_RE = re.compile(
    r"^\s*(?:please\s+|could\s+you\s+|can\s+you\s+)?(?P<verb>[A-Za-z']+)\b",
    re.I,
)

_DUE_PHRASE_RE = re.compile(
    r"\b(?:"
    r"by\s+(?:today|tomorrow|tonight|monday|tuesday|wednesday|thursday|friday|saturday|sunday|\d+[/-]\d+|end\s+of\s+(?:day|week)|eod|eow)"
    r"|tomorrow|tonight|today"
    r"|next\s+(?:week|month|monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
    r"|this\s+(?:week|afternoon|evening|morning)"
    r"|in\s+\d+\s+(?:minute|minutes|hour|hours|day|days|week|weeks)"
    r"|at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?"
    r"|on\s+\d+[/-]\d+"
    r")\b",
    re.I,
)

_IDEA_MARKER_RE = re.compile(
    r"(?:^|\s)(?:"
    r"idea\s*[:\-]|"
    r"thought\s*[:\-]|"
    r"concept\s*[:\-]|"
    r"what\s+if|"
    r"should\s+we|"
    r"could\s+we|"
    r"might\s+be\s+worth|"
    r"i\s+wonder|"
    r"maybe\s+we|"
    r"it\s+would\s+be\s+cool"
    r")",
    re.I,
)

_QUESTION_OPENERS_RE = re.compile(
    r"^\s*(?:how|why|what|could|should|would)\b",
    re.I,
)


class RuleBasedClassifier:
    """Deterministic classifier for routing captures.

    Produces a :class:`ClassificationResult` with ``source="rules"`` and no
    ``slug`` (slug assignment belongs to the router, not the classifier).
    Safe to instantiate once and share across threads: it holds no mutable
    state and all compiled patterns are module-level.
    """

    def classify(self, text: str) -> ClassificationResult:
        """Classify ``text`` as ``action``, ``idea``, or ``raw``.

        Returns a :class:`ClassificationResult` with confidence clamped to
        ``[0.0, 1.0]`` and a comma-separated ``reason`` listing the
        heuristics that fired (or ``"none"`` when nothing matched,
        ``"empty"`` for blank input).
        """
        cleaned = (text or "").strip()
        if not cleaned:
            return ClassificationResult(
                kind="raw",
                confidence=0.0,
                reason="empty",
                source="rules",
                slug=None,
            )

        score_action = 0.0
        score_idea = 0.0
        signals: list[str] = []

        # Idea markers are strong and override a following imperative because
        # people often say "idea: build a service that sends emails" where
        # "build" would otherwise flag as action.
        if _IDEA_MARKER_RE.search(cleaned):
            score_idea += _SCORE_IDEA_MARKER
            signals.append("idea_marker")

        first_match = _IMPERATIVE_START_RE.match(cleaned)
        if first_match and first_match.group("verb").lower() in _IMPERATIVES:
            score_action += _SCORE_IMPERATIVE_START
            signals.append(f"imperative:{first_match.group('verb').lower()}")

        if _DUE_PHRASE_RE.search(cleaned):
            score_action += _SCORE_DUE_PHRASE
            signals.append("due_phrase")

        # Question openers without an imperative verb look idea-ish.
        if _QUESTION_OPENERS_RE.match(cleaned) and not first_match or (
            first_match and first_match.group("verb").lower() not in _IMPERATIVES
        ):
            if _QUESTION_OPENERS_RE.match(cleaned):
                score_idea += _SCORE_QUESTION_OPENER
                signals.append("question_opener")

        reason = ",".join(signals) or "none"

        if score_action >= _ACTION_MIN_SCORE and score_action >= score_idea:
            return ClassificationResult(
                kind="action",
                confidence=min(1.0, score_action),
                reason=reason,
                source="rules",
                slug=None,
            )
        if score_idea >= _IDEA_MIN_SCORE:
            return ClassificationResult(
                kind="idea",
                confidence=min(1.0, score_idea),
                reason=reason,
                source="rules",
                slug=None,
            )

        # No strong signal. Return raw with a small confidence so a later
        # reprocess pass can pick it up and the router knows to default-route
        # to the daily inbox.
        return ClassificationResult(
            kind="raw",
            confidence=_RAW_FALLBACK_CONFIDENCE,
            reason=reason,
            source="rules",
            slug=None,
        )
