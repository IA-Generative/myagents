"""LA règle de visibilité d'une capacité (ADR §4.2, §4.3 règle 5), la même pour toutes les routes.

- son auteur voit tout (brouillons compris) ;
- les autres voient une capacité SERVIE (une version publiée, ni retirée ni suspendue) :
  `ministry` → tout le ministère ; `community` → les membres du groupe `community_path` ;
  `private` → personne ;
- maturité `alpha` : l'auteur et son groupe (`community_path`) seulement.
`not_found` ne distingue jamais « n'existe pas » de « pas pour vous ».
"""

from collections.abc import Iterable

STATUTS_NON_SERVIS = ("retired", "suspended")


def groupe_correspond(community_path: str | None, groups: Iterable[str]) -> bool:
    """La communauté déclarée fait-elle partie des groupes du jeton ?

    Un chemin (« /g/juridique ») se compare aux chemins complets ; un nom (« juridique ») au
    nom feuille — même règle que `OIDC_GROUPE_EXIGE` (app.core.security.has_required_group).
    """
    chemin = (community_path or "").strip()
    if not chemin:
        return False
    if chemin.startswith("/"):
        return chemin.rstrip("/") in {g.rstrip("/") for g in groups}
    return chemin in {g.rstrip("/").rsplit("/", 1)[-1] for g in groups}


def est_reviewer(user) -> bool:
    """Rôle de realm `mesagents-reviewer` ET portée `mesagents:review` dans le jeton."""
    return bool(getattr(user, "is_reviewer", False)) and "mesagents:review" in (
        getattr(user, "scopes", ()) or ()
    )


def est_servie(cap) -> bool:
    """Une version publiée existe et la capacité n'est ni retirée ni suspendue."""
    return cap.current_version is not None and cap.status not in STATUTS_NON_SERVIS


def est_visible(cap, user) -> bool:
    """Visibilité hors maturité (voir `visible_pour` quand on connaît la version servie)."""
    if cap is None:
        return False
    if cap.owner_sub == user.user_id:
        return True
    if cap.status == "submitted" and est_reviewer(user):
        # L'écran de revue : une soumission d'autrui se lit, elle n'est servie à personne.
        return True
    if not est_servie(cap):
        return False
    if cap.visibility == "ministry":
        return True
    if cap.visibility == "community":
        return groupe_correspond(cap.community_path, user.groups)
    return False


def visible_pour(cap, version, user) -> bool:
    """Visibilité complète : règle ci-dessus, puis la maturité de la version servie."""
    if not est_visible(cap, user):
        return False
    if cap.owner_sub == user.user_id:
        return True
    if version is not None and version.maturity == "alpha":
        return groupe_correspond(cap.community_path, user.groups)
    return True
