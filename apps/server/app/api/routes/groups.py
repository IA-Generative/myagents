"""Route : recherche dynamique de groupes Keycloak pour la publication d'agents.

Avec credentials admin Keycloak (OIDC_ADMIN_CLIENT_SECRET) : recherche serveur via
l'Admin REST API, qui retourne tous les groupes du realm (pas seulement ceux de
l'utilisateur). Sans credentials : repli sur les groupes du token utilisateur.
"""

import logging

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.keycloak_admin import KeycloakAdminError, search_groups
from app.core.security import AuthUser
from app.schemas.group import GroupProfile

router = APIRouter(
    prefix="/groups", tags=["groups"], dependencies=[Depends(get_current_user)]
)
logger = logging.getLogger(__name__)


@router.get("", response_model=list[GroupProfile])
async def list_groups(
    q: str = Query(default="", max_length=100),
    user: AuthUser = Depends(get_current_user),
) -> list[GroupProfile]:
    settings = get_settings()
    query = q.strip()

    if settings.oidc_admin_client_secret:
        try:
            groups = await search_groups(query)
            return [
                GroupProfile(id=g.id, name=g.name, path=g.path) for g in groups
            ]
        except KeycloakAdminError as exc:
            logger.warning(
                "recherche groupes via admin API échouée: %s — repli token", exc
            )

    # Repli : groupes du token utilisateur, filtrés par la requête.
    groups: list[GroupProfile] = []
    for g in user.groups:
        name = g.rstrip("/").rsplit("/", 1)[-1]
        if query and query.lower() not in name.lower():
            continue
        groups.append(GroupProfile(id=name, name=name, path=g))
    return groups[:20]
