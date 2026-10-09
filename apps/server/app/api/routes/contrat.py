"""Contrat d'agents MirAI : GET /api/v1/agents (docs/contrats/contrat-agents-mirai.md).

Jeton utilisateur Keycloak avec l'audience du contrat ; droits appliqués ici, depuis `sub`
et `groups`. Le lancement passe par la surface OpenAI-compatible (/v1/chat/completions).
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_contrat_user
from app.core.contrat import INPUTS, ContratError
from app.core.security import AuthUser
from app.db.session import get_db
from app.schemas.contrat import ListeAgents
from app.services import agents as agents_service
from app.services.contrat import fiche

router = APIRouter(prefix="/v1", tags=["contrat-agents"])

LIMITE_DEFAUT = 100
LIMITE_MAX = 200


@router.get("/agents", response_model=ListeAgents)
async def lister_les_agents(
    input: str | None = Query(default=None, max_length=40),
    limit: int = Query(default=LIMITE_DEFAUT),
    user: AuthUser = Depends(get_contrat_user),
    db: AsyncSession = Depends(get_db),
) -> ListeAgents:
    if input is not None and input not in INPUTS:
        raise ContratError(
            400, "invalid_query", f"input inconnu ; valeurs : {', '.join(INPUTS)}"
        )
    if not 1 <= limit <= LIMITE_MAX:
        raise ContratError(400, "invalid_query", f"limit entre 1 et {LIMITE_MAX}")

    agents = await agents_service.list_accessible(db, user.user_id, user.groups)
    fiches = [fiche(a, user.user_id) for a in agents]
    if input is not None:
        fiches = [f for f in fiches if input in f.inputs]
    return ListeAgents(total=len(fiches), agents=fiches[:limit])
