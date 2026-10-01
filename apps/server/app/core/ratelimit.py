"""Limiteur de débit en mémoire (fenêtre glissante d'une minute, par clé et par réplique)."""

import time
from collections import defaultdict, deque

_WINDOW_SECONDS = 60.0
_hits: dict[str, deque[float]] = defaultdict(deque)


def allow(key: str, limit: int) -> bool:
    """Enregistre un appel pour `key` ; False si `limit` appels ont déjà eu lieu sur la fenêtre."""
    if limit <= 0:
        return True
    now = time.monotonic()
    hits = _hits[key]
    while hits and now - hits[0] > _WINDOW_SECONDS:
        hits.popleft()
    if len(hits) >= limit:
        return False
    hits.append(now)
    return True


def reset() -> None:
    _hits.clear()
