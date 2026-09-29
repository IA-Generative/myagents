"""Deterministic heuristic guard for system prompts (no LLM call, fail-closed).

Mirrors (in a simplified form) the mandatory "Valider les instructions système"
gate of the reference app: blocks obvious keylogger / data-exfiltration code and
common prompt-injection phrasing before an agent can be published.
"""

import re

_BLOCK_PATTERNS = [
    (
        re.compile(r"addEventListener\s*\(\s*['\"]keypress", re.IGNORECASE),
        "code de type keylogger détecté",
    ),
    (re.compile(r"keylogger", re.IGNORECASE), "mention explicite d'un keylogger"),
    (
        re.compile(r"localStorage\.\w+\s*\+=", re.IGNORECASE),
        "exfiltration de frappes clavier vers localStorage",
    ),
    (
        re.compile(
            r"ignor(e|er)\s+(les\s+)?instructions\s+(précédentes|pr(é|e)c(é|e)dentes)",
            re.IGNORECASE,
        ),
        "tentative de contournement des instructions système",
    ),
    (
        re.compile(
            r"r(é|e)v(è|e)le?\s+(tes|ton)\s+(instructions|prompt)", re.IGNORECASE
        ),
        "tentative d'extraction du prompt système",
    ),
]


def validate_system_prompt(text: str) -> tuple[bool, str | None]:
    """Returns (blocked, reason). blocked=True means the prompt must be rejected."""
    for pattern, reason in _BLOCK_PATTERNS:
        if pattern.search(text):
            return True, reason
    return False, None
