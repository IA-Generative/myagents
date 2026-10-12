"""Portées client → opérations (ADR §4.7, matrice des droits d'application).

Une portée = un droit de l'APPLICATION appelante (lu dans le claim `scope` du jeton) ; les droits
de la PERSONNE (visibilité, groupes, rôle `mesagents-reviewer`) se lisent ailleurs. L'intersection
fait foi. `mesagents:delegate` est déclarée mais hors V2 : un jeton qui la porte est refusé.
"""

from collections.abc import Iterable
from enum import StrEnum

from app.core.config import get_settings
from app.core.contrat import ContratError


class Operation(StrEnum):
    LISTER = (
        "lister"  # tools/list, prompts/*, recherche, description, GET /capabilities
    )
    APPELER_LECTURE = (
        "appeler_lecture"  # tools/call sur une capacité readOnlyHint: true
    )
    APPELER_ACTION = "appeler_action"  # tools/call sur une capacité readOnlyHint: false
    REDIGER = "rediger"  # créer, modifier, tester, publier private|community, retirer les siennes
    REVOIR = "revoir"  # publier ministry / non lecture seule, retirer d'autrui, administration
    DELEGUER = "deleguer"  # déclarée, toujours refusée (régime délégué hors V2)


PORTEE: dict[Operation, str] = {
    Operation.LISTER: "mesagents:read",
    Operation.APPELER_LECTURE: "mesagents:read",
    Operation.APPELER_ACTION: "mesagents:act",
    Operation.REDIGER: "mesagents:author",
    Operation.REVOIR: "mesagents:review",
    Operation.DELEGUER: "mesagents:delegate",
}

PORTEES_CONNUES: tuple[str, ...] = (
    "mesagents:read",
    "mesagents:act",
    "mesagents:author",
    "mesagents:review",
    "mesagents:delegate",
)

REFUSEES: frozenset[str] = frozenset({"mesagents:delegate"})

# Repli de nommage si un Keycloak refuse « : » dans le nom d'une portée : les formes
# `mesagents-read` et `mesagents.read` valent `mesagents:read`. D'autres alias par configuration.
_ALIAS_FIXES: dict[str, str] = {}
for _p in PORTEES_CONNUES:
    _prefixe, _droit = _p.split(":")
    _ALIAS_FIXES[f"{_prefixe}-{_droit}"] = _p
    _ALIAS_FIXES[f"{_prefixe}.{_droit}"] = _p


def normaliser_portees(claim: str | None) -> frozenset[str]:
    """Éclate le claim `scope` (séparé par des espaces) et rabat les alias sur la forme canonique."""
    if not claim:
        return frozenset()
    alias = {**_ALIAS_FIXES, **get_settings().mesagents_portees_alias}
    return frozenset(alias.get(p, p) for p in claim.split() if p)


def portee_pour_appel(read_only: bool) -> str:
    return PORTEE[Operation.APPELER_LECTURE if read_only else Operation.APPELER_ACTION]


def exiger(portees: Iterable[str], operation: Operation) -> None:
    """Refuse (`403 scope_missing`, portée nommée) si le client n'a pas la portée de l'opération."""
    portees = frozenset(portees)
    if portees & REFUSEES:
        raise ContratError(
            403,
            "forbidden",
            "la portée mesagents:delegate est hors du contrat V2 : jeton refusé",
        )
    attendue = PORTEE[operation]
    if attendue not in portees:
        raise ContratError(403, "scope_missing", f"portée manquante : {attendue}")
