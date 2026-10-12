"""Fiches du contrat d'agents MirAI, construites depuis un agent et l'identité de l'appelant."""

from app.core.config import get_settings
from app.models.agent import Agent
from app.schemas.contrat import FicheAgent
from app.services import agents as agents_service


def url_de_l_agent(agent: Agent, mine: bool) -> str:
    base = get_settings().web_public_url.rstrip("/")
    if mine:
        return f"{base}/agents/{agent.id}/edit"
    return f"{base}/catalog/{agent.id}"


def fiche(agent: Agent, user_id: str) -> FicheAgent:
    config = agents_service.current_config(agent)
    mine = agent.creator_id == user_id
    return FicheAgent(
        id=str(agent.id),
        name=config.name,
        description=config.description,
        origin="mine" if mine else "shared",
        categories=list(agent.category),
        tags=list(agent.tags),
        version=agent.version,
        visibility=agent.visibility,
        status=agent.status,
        inputs=list(config.inputs),
        outputs=list(config.outputs),
        greeting=config.greeting,
        examples=list(config.examples),
        model=str(agent.id),
        updated_at=agent.updated_at,
        url=url_de_l_agent(agent, mine),
    )
