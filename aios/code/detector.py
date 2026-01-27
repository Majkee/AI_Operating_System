"""
Coding request detection for AIOS.

Uses regex-based classification to determine whether a user's input
is a coding task that should be routed to Claude Code.
"""

import re
from typing import Optional


# Strong patterns (score +2.0) — almost certainly coding
_STRONG_PATTERNS = [
    re.compile(
        r"(write|create|build|make|generate)\s+(a\s+)?"
        r"(python|javascript|typescript|rust|go|java|c\+\+|ruby|php|swift|kotlin|"
        r"bash|shell|sql|html|css|react|vue|angular|flask|django|express|fastapi|"
        r"script|program|app|application|website|web\s*app|api|cli|tool|library|package|module)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(refactor|optimize|debug|fix)\s+(the\s+|this\s+|my\s+)?"
        r"(code|script|function|class|module|component|codebase|program|application|bug|error|issue)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(add|implement|create)\s+(a\s+)?"
        r"(feature|endpoint|component|test|tests|unit\s*test|route|middleware|model|view|controller|migration|hook)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(set\s*up|scaffold|bootstrap|init|initialize)\s+(a\s+)?"
        r"(project|repo|repository|app|application|workspace|monorepo|environment)",
        re.IGNORECASE,
    ),
    re.compile(
        r"create\s+.+\s+(using|with|in)\s+"
        r"(react|flask|express|django|fastapi|next\.?js|vue|angular|spring|rails|laravel)",
        re.IGNORECASE,
    ),
]

# Moderate patterns (score +0.5 each, capped at +1.0)
_MODERATE_PATTERNS = [
    re.compile(r"\b(code|coding|programming|develop|development)\b", re.IGNORECASE),
    re.compile(r"\bgit\s+(commit|push|pull|merge|rebase|branch|checkout|stash|clone|init)\b", re.IGNORECASE),
    re.compile(r"\b(npm|pip|cargo|yarn|pnpm|poetry|composer|gem|maven|gradle)\s+(install|add|remove|update|init|run|build)\b", re.IGNORECASE),
    re.compile(r"\b(dockerfile|makefile|webpack|eslint|prettier|tsconfig|vite|rollup|babel)\b", re.IGNORECASE),
    re.compile(r"\b(api|endpoint|database|schema|migration)\b.*\b(create|build|design|update|modify)\b", re.IGNORECASE),
    re.compile(r"\b(class|function|method|variable|interface|type|struct|enum)\b.*\b(add|create|define|implement|rename)\b", re.IGNORECASE),
]

# Sensitivity thresholds
_THRESHOLDS = {
    "high": 2.0,
    "moderate": 1.0,
    "low": 0.5,
}


class CodingRequestDetector:
    """Regex-based classifier for coding requests."""

    def __init__(self, sensitivity: str = "moderate"):
        self._sensitivity = sensitivity
        self._threshold = _THRESHOLDS.get(sensitivity, _THRESHOLDS["moderate"])

    @property
    def sensitivity(self) -> str:
        return self._sensitivity

    @sensitivity.setter
    def sensitivity(self, value: str) -> None:
        self._sensitivity = value
        self._threshold = _THRESHOLDS.get(value, _THRESHOLDS["moderate"])

    def score(self, text: str) -> float:
        """Score the likelihood that *text* is a coding request (0.0–3.0)."""
        total = 0.0

        # Strong patterns
        for pattern in _STRONG_PATTERNS:
            if pattern.search(text):
                total += 2.0
                break  # One strong match is enough

        # Moderate patterns (capped at 1.0)
        moderate_score = 0.0
        for pattern in _MODERATE_PATTERNS:
            if pattern.search(text):
                moderate_score += 0.5
        total += min(moderate_score, 1.0)

        return min(total, 3.0)

    def is_coding_request(self, text: str) -> bool:
        """Return True if *text* appears to be a coding request."""
        return self.score(text) >= self._threshold

    def describe_match(self, text: str) -> str:
        """Return a human-readable reason for the match (or empty string)."""
        reasons = []

        for pattern in _STRONG_PATTERNS:
            m = pattern.search(text)
            if m:
                reasons.append(f"strong match: '{m.group()}'")
                break

        for pattern in _MODERATE_PATTERNS:
            m = pattern.search(text)
            if m:
                reasons.append(f"keyword: '{m.group()}'")

        if reasons:
            return "Detected coding request — " + "; ".join(reasons)
        return ""
