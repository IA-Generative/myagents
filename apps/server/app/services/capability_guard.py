"""La garde vue du contrat de capacités : `guard.check` (définition), `guard.io` (exécution),
`guard.recheck_all` (règle 7). Les enveloppes d'exécution RENDENT un verdict (« ok » / « blocked »)
au lieu de lever : le journal en a besoin dans tous les cas."""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.guard import BLOCK_MESSAGE_USER_INPUT
from app.llm.guard import definition as garde_definition
from app.llm.guard.definition import VerdictDefinition
from app.models.capability import Capability
from app.services import prompt_guard
from app.services.prompt_guard import GuardBlockedError

logger = logging.getLogger(__name__)


async def verifier_definition(cap) -> VerdictDefinition:
    """`guard.check(definition, description)` sur une capacité ou une version (mêmes attributs)."""
    return await garde_definition.check(
        cap.definition,
        cap.description,
        kind=getattr(cap, "kind", "prompt"),
        title=cap.title,
        examples=cap.examples or [],
    )


async def io_entree(
    db: AsyncSession | None, texte: str, *, route: str, user_id: str
) -> str:
    try:
        await prompt_guard.check_input(
            db,
            route=route,
            text=texte,
            role="user",
            block_message=BLOCK_MESSAGE_USER_INPUT,
            user_id=user_id,
        )
    except GuardBlockedError:
        return "blocked"
    return "ok"


async def io_sortie(
    db: AsyncSession | None,
    texte: str,
    *,
    route: str,
    user_id: str,
    canary: str | None,
) -> str:
    try:
        await prompt_guard.check_output(
            db, route=route, text=texte, user_id=user_id, role="user", canary=canary
        )
    except GuardBlockedError:
        return "blocked"
    return "ok"


async def recheck_all(db: AsyncSession, user) -> dict:
    """Règle 7 : rejoue la garde sur chaque version servie ; retire les non conformes."""
    from app.services import capabilities as service

    caps = list(
        (
            await db.execute(
                select(Capability).where(Capability.current_version.is_not(None))
            )
        )
        .scalars()
        .all()
    )
    retirees: list[str] = []
    verifiees = 0
    for cap in caps:
        if cap.status in ("retired", "suspended"):
            continue
        version = await service.version_servie(db, cap)
        if version is None:
            continue
        kind = cap.kind
        verdict = await garde_definition.check(
            version.definition,
            version.description,
            kind=kind,
            title=version.title,
            examples=version.examples or [],
        )
        verifiees += 1
        if not verdict.favorable:
            await service.retirer(db, user, cap, motif="recheck")
            retirees.append(cap.name)
    return {"rechecked": verifiees, "retired": retirees}
