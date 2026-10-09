"""Schémas du contrat d'agents MirAI (docs/contrats/contrat-agents-mirai.md)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.models.enums import AgentStatus, Visibility


class FicheAgent(BaseModel):
    """Ce qu'un consommateur lit pour présenter et lancer un agent."""

    id: str
    name: str
    description: str
    origin: Literal["mine", "shared"]
    categories: list[str]
    tags: list[str]
    version: int
    visibility: Visibility
    status: AgentStatus
    inputs: list[str]
    outputs: list[str]
    greeting: str
    examples: list[str]
    # Valeur à passer dans `model` de POST /v1/chat/completions.
    model: str
    updated_at: datetime
    url: str


class ListeAgents(BaseModel):
    source: Literal["mesagents"] = "mesagents"
    total: int
    agents: list[FicheAgent]
