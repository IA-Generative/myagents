"""`tools/list` de taille constante (ADR §4.4) : trois méta-outils + les épinglés (≤ plafond),
filtrés par le contexte de surface (`azp` → champs que la surface sait fournir)."""

from __future__ import annotations

from typing import Any

META_OUTILS_NOMS: tuple[str, str, str] = (
    "rechercher_capacites",
    "decrire_capacite",
    "executer_capacite",
)


def definitions_meta_outils() -> list[dict[str, Any]]:
    from app.mcp.meta_outils import DEFINITIONS

    return [dict(d) for d in DEFINITIONS]


def champs_fournis(azp: str, contextes: dict[str, list[str]]) -> set[str]:
    """Les champs qu'une surface sait fournir ; `*` pour les surfaces inconnues ; sinon aucun."""
    if azp in contextes:
        return set(contextes[azp])
    return set(contextes.get("*", []))


def servie_au_contexte(input_schema: dict[str, Any], champs: set[str]) -> bool:
    """Servie ssi chaque champ REQUIS est fournissable (ou porte une valeur par défaut)."""
    proprietes = input_schema.get("properties") or {}
    for requis in input_schema.get("required") or []:
        spec = proprietes.get(requis) or {}
        if requis in champs or "default" in spec:
            continue
        return False
    return True


def construire_tools_list(
    epingles: list[dict[str, Any]],
    *,
    catalogue_taille: int,
    champs: set[str],
    plafond: int,
) -> list[dict[str, Any]]:
    """Méta-outils puis épinglés (dans l'ordre des rangs), sans jamais dépendre de `catalogue_taille`."""
    del catalogue_taille  # la taille du catalogue n'entre pas : c'est le point de l'ADR
    liste = definitions_meta_outils()
    retenus = 0
    for outil in epingles:
        if retenus >= plafond:
            break
        if not servie_au_contexte(outil.get("inputSchema") or {}, champs):
            continue
        servi = dict(outil)
        meta = dict(servi.get("_meta") or {})
        if meta.get("maturity") == "beta" and not str(
            servi.get("description", "")
        ).startswith("[bêta] "):
            servi["description"] = f"[bêta] {servi.get('description', '')}"
        servi["_meta"] = meta
        liste.append(servi)
        retenus += 1
    return liste
