"""Jeu d'essai du contrat d'agents MirAI : des agents dont on connaît d'avance la visibilité.

Pour une preview : `python -m app.scripts.seed_contrat` dans le pod. Idempotent (identifiants
déterministes). Vu par un testeur du groupe /g/mirai-beta-testeurs qui n'est l'auteur d'aucun :

| Agent | Attendu dans GET /api/v1/agents |
|---|---|
| Relecteur de courriels (ministère, publié) | oui, origin shared |
| Préparateur de réunion (communauté testeurs, publié) | oui, origin shared |
| Synthèse pour la direction (ministère, soumis) | oui, status submitted |
| Agent de l'autre communauté (communauté /g/autre-direction) | NON |
| Agent privé d'un collègue (privé, publié) | NON |
| Brouillon d'un collègue (ministère, brouillon) | NON |
| Agent archivé (ministère, archivé) | NON |
"""

import asyncio
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.db.session import SessionLocal
from app.models.agent import Agent, AgentVersion
from app.models.enums import AgentStatus, Visibility
from app.schemas.agent import ConfigSnapshot

logger = logging.getLogger(__name__)

CREATOR_ID = "contrat-test-collegue"
GROUPE_TESTEURS = "/g/mirai-beta-testeurs"
_NAMESPACE = uuid.UUID("3b7b3c6a-5e1b-4d8f-9a2e-7c1d2e3f4a5b")


def _agent_id(slug: str) -> uuid.UUID:
    return uuid.uuid5(_NAMESPACE, f"mes-agents.contrat.{slug}")


def _config(name: str, description: str, inputs: list[str], outputs: list[str], **kw):
    return ConfigSnapshot(
        name=name,
        description=description,
        category=kw.get("category", "transverse"),
        community_path=kw.get("community_path"),
        system_prompt=(
            f"Rôle : tu es « {name} ». {description} Réponds en français, de façon "
            "concise et structurée. Si le contenu fourni ne suffit pas, dis ce qui manque."
        ),
        greeting=f"Bonjour, je suis {name}. Que puis-je faire pour vous ?",
        examples=kw.get("examples", []),
        temperature=0.4,
        inputs=inputs,
        outputs=outputs,
    )


AGENTS: list[dict] = [
    {
        "slug": "relecteur-courriels",
        "visibility": Visibility.ministry,
        "status": AgentStatus.published,
        "category": ["redaction"],
        "config": _config(
            "Relecteur de courriels",
            "Relit un courriel ou une sélection et propose une version plus claire.",
            ["text", "selection", "email", "thread"],
            ["text", "replacement"],
            category="redaction",
            examples=["Reformule ce courriel sur un ton plus formel."],
        ),
    },
    {
        "slug": "preparateur-reunion",
        "visibility": Visibility.community,
        "status": AgentStatus.published,
        "category": ["reunions"],
        "config": _config(
            "Préparateur de réunion",
            "À partir d'une transcription ou d'un compte rendu, dégage décisions, "
            "actions et points en suspens.",
            ["text", "meeting", "document"],
            ["text"],
            category="transverse",
            community_path=GROUPE_TESTEURS,
            examples=["Liste les décisions prises et les actions à suivre."],
        ),
    },
    {
        "slug": "synthese-direction",
        "visibility": Visibility.ministry,
        "status": AgentStatus.submitted,
        "category": ["redaction"],
        "config": _config(
            "Synthèse pour la direction",
            "Résume un document ou une page en dix lignes pour un décideur.",
            ["text", "document", "page", "collection"],
            ["text", "insertion"],
            category="redaction",
        ),
    },
    {
        "slug": "autre-communaute",
        "visibility": Visibility.community,
        "status": AgentStatus.published,
        "category": ["transverse"],
        "config": _config(
            "Agent de l'autre communauté",
            "Réservé au groupe /g/autre-direction : ne doit pas apparaître aux testeurs.",
            ["text"],
            ["text"],
            community_path="/g/autre-direction",
        ),
    },
    {
        "slug": "prive-collegue",
        "visibility": Visibility.private,
        "status": AgentStatus.published,
        "category": ["transverse"],
        "config": _config(
            "Agent privé d'un collègue",
            "Privé : ne doit apparaître à personne d'autre que son auteur.",
            ["text"],
            ["text"],
        ),
    },
    {
        "slug": "brouillon-collegue",
        "visibility": Visibility.ministry,
        "status": AgentStatus.draft,
        "category": ["transverse"],
        "config": _config(
            "Brouillon d'un collègue",
            "Brouillon : ne doit apparaître qu'à son auteur.",
            ["text"],
            ["text"],
        ),
    },
    {
        "slug": "archive",
        "visibility": Visibility.ministry,
        "status": AgentStatus.archived,
        "category": ["transverse"],
        "config": _config(
            "Agent archivé",
            "Archivé : ne doit jamais être servi.",
            ["text"],
            ["text"],
        ),
    },
]


async def seed_contrat_agents(db: AsyncSession) -> int:
    """Crée les agents d'essai absents. Rend le nombre créé."""
    ids = [_agent_id(item["slug"]) for item in AGENTS]
    existing = set(
        (await db.execute(select(Agent.id).where(Agent.id.in_(ids)))).scalars().all()
    )
    created = 0
    for item, agent_id in zip(AGENTS, ids, strict=True):
        if agent_id in existing:
            continue
        config: ConfigSnapshot = item["config"]
        agent = Agent(
            id=agent_id,
            creator_id=CREATOR_ID,
            model_ref=config.model_id or get_settings().llm_default_model,
            visibility=item["visibility"],
            status=item["status"],
            category=item["category"],
            tags=["contrat-test"],
            version=1,
        )
        agent.versions.append(
            AgentVersion(
                version=1,
                config_snapshot=config.model_dump(),
                changelog="Jeu d'essai du contrat d'agents",
            )
        )
        db.add(agent)
        created += 1
        logger.info("agent d'essai créé: %s (%s)", config.name, agent_id)
    if created:
        await db.commit()
    return created


async def main() -> None:
    setup_logging()
    async with SessionLocal() as db:
        created = await seed_contrat_agents(db)
    logger.info(
        "jeu d'essai du contrat: %d créé(s), %d déjà présent(s)",
        created,
        len(AGENTS) - created,
    )


if __name__ == "__main__":
    asyncio.run(main())
