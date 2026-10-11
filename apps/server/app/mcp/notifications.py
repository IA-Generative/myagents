"""`notifications/tools/list_changed` (ADR §4.4) : diffusion en mémoire, par personne (`sub`).

Un seul réplica en preview ; avec plusieurs réplicas il faudrait un bus (question du rapport).
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable

LIST_CHANGED = {"jsonrpc": "2.0", "method": "notifications/tools/list_changed"}


class Diffuseur:
    def __init__(self) -> None:
        self._abonnes: dict[str, set[asyncio.Queue]] = {}

    def abonner(self, sub: str) -> asyncio.Queue:
        file: asyncio.Queue = asyncio.Queue(maxsize=64)
        self._abonnes.setdefault(sub, set()).add(file)
        return file

    def desabonner(self, sub: str, file: asyncio.Queue) -> None:
        files = self._abonnes.get(sub)
        if files is not None:
            files.discard(file)
            if not files:
                self._abonnes.pop(sub, None)

    def notifier_list_changed(self, subs: Iterable[str] | None) -> int:
        """Prévient les personnes données (None = toutes les abonnées). Rend le nombre de files."""
        cibles = (
            list(self._abonnes.keys())
            if subs is None
            else [s for s in set(subs) if s in self._abonnes]
        )
        n = 0
        for sub in cibles:
            for file in list(self._abonnes.get(sub, ())):
                try:
                    file.put_nowait(dict(LIST_CHANGED))
                    n += 1
                except asyncio.QueueFull:
                    pass
        return n

    @property
    def nombre_abonnes(self) -> int:
        return sum(len(f) for f in self._abonnes.values())


diffuseur = Diffuseur()
