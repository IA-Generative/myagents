"""Pydantic schemas for the agent wizard draft and API payloads."""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.core.contrat import Input, Output
from app.models.enums import AgentStatus, Visibility

ShortText = Annotated[str, StringConstraints(max_length=255)]
TagList = Annotated[list[ShortText], Field(max_length=20)]
MAX_PROMPT_CHARS = 20_000
MAX_MESSAGES = 100


class ConfigSnapshot(BaseModel):
    """Full wizard draft — mirrors the frontend's wizard store shape."""

    name: str = Field(max_length=200)
    description: str = Field(default="", max_length=2_000)
    category: ShortText = ""
    community_path: ShortText | None = None
    system_prompt: str = Field(default="", max_length=MAX_PROMPT_CHARS)
    greeting: str = Field(default="", max_length=2_000)
    examples: Annotated[
        list[Annotated[str, StringConstraints(max_length=500)]], Field(max_length=20)
    ] = Field(default_factory=list)
    model_id: ShortText = ""
    temperature: float = Field(default=0.7, ge=0, le=2)
    knowledge_ids: Annotated[list[ShortText], Field(max_length=20)] = Field(
        default_factory=list
    )
    tool_ids: Annotated[list[ShortText], Field(max_length=20)] = Field(
        default_factory=list
    )
    # Contrat d'agents MirAI : sur quoi l'agent sait travailler, et ce qu'il rend.
    # Vocabulaire fermé (app.core.contrat) ; un instantané ancien vaut ["text"].
    inputs: Annotated[list[Input], Field(max_length=16)] = Field(
        default_factory=lambda: ["text"]
    )
    outputs: Annotated[list[Output], Field(max_length=16)] = Field(
        default_factory=lambda: ["text"]
    )

    @field_validator("inputs", "outputs")
    @classmethod
    def _sans_doublon_ni_vide(cls, valeurs: list[str]) -> list[str]:
        uniques = list(dict.fromkeys(valeurs))
        return uniques or ["text"]


class AgentCreate(BaseModel):
    visibility: Visibility = Visibility.private
    status: AgentStatus = AgentStatus.draft
    category: TagList = Field(default_factory=list)
    tags: TagList = Field(default_factory=list)
    config: ConfigSnapshot


class AgentUpdate(BaseModel):
    visibility: Visibility | None = None
    status: AgentStatus | None = None
    category: TagList | None = None
    tags: TagList | None = None
    changelog: str | None = Field(default=None, max_length=500)
    config: ConfigSnapshot


class AgentListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    creator_id: str
    name: str
    model_ref: str
    visibility: Visibility
    status: AgentStatus
    category: list[str]
    tags: list[str]
    version: int
    created_at: datetime
    updated_at: datetime


class AgentDetail(AgentListItem):
    config: ConfigSnapshot
    # État de la fiche dans le socle après une écriture (posee, retiree, indisponible,
    # groupe_inconnu:<nom>, erreur:<type>) ; absent en simple lecture.
    socle: str | None = None


class ChatMessage(BaseModel):
    role: str = Field(max_length=32)
    content: str = Field(max_length=MAX_PROMPT_CHARS)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(max_length=MAX_MESSAGES)


class ChatResponse(BaseModel):
    reply: str


class RatingCreate(BaseModel):
    score: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=1000)


class RatingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_id: uuid.UUID
    score: int
    comment: str | None
    created_at: datetime


class FavoriteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_id: uuid.UUID
    created_at: datetime


class ModelProfile(BaseModel):
    id: str
    label: str
    tier: str = "balanced"
    short_pitch: str = ""


class ToolProfile(BaseModel):
    id: str
    label: str
    description: str = ""


class PromptAssistRequest(BaseModel):
    prompt: str = Field(default="", max_length=MAX_PROMPT_CHARS)
    hints: Annotated[
        dict[Annotated[str, StringConstraints(max_length=100)], str],
        Field(max_length=20),
    ] = Field(default_factory=dict)


class PromptResponse(BaseModel):
    prompt: str


class SuggestStartersRequest(BaseModel):
    prompt: str = Field(max_length=MAX_PROMPT_CHARS)
    count: int = Field(default=4, ge=1, le=10)


class SuggestStartersResponse(BaseModel):
    greeting: str = Field(
        description="Message d'accueil court (moins de 300 caractères), ton formel, en français"
    )
    examples: list[str] = Field(
        description="Exemples de prompts utilisateur réalistes, 40 à 120 caractères, en français"
    )


class PromptValidateRequest(BaseModel):
    prompt: str = Field(max_length=MAX_PROMPT_CHARS)


class PromptValidateResponse(BaseModel):
    ok: bool
    message: str | None = None


class OnboardingMessage(BaseModel):
    role: str = Field(max_length=32)
    content: str = Field(max_length=MAX_PROMPT_CHARS)


class OnboardingChatRequest(BaseModel):
    messages: list[OnboardingMessage] = Field(max_length=MAX_MESSAGES)


class OnboardingAgentConfig(BaseModel):
    ready: bool = False
    name: str = ""
    description: str = ""
    category: str = ""
    system_prompt: str = ""
    greeting: str = ""
    examples: list[str] = Field(default_factory=list)


class OnboardingTurn(BaseModel):
    """Structured output the LLM must return for each onboarding chat turn."""

    message: str = Field(
        description="Une seule question ou remarque à afficher à l'utilisateur, en français"
    )
    ready: bool = Field(
        default=False,
        description="true seulement quand toutes les informations ont été recueillies",
    )
    name: str = Field(default="", description="Nom de l'agent")
    description: str = Field(default="", description="Description courte de l'agent")
    category: str = Field(default="", description="Catégorie de l'agent")
    system_prompt: str = Field(
        default="", description="Prompt système complet rédigé pour l'agent"
    )
    greeting: str = Field(default="", description="Message d'accueil de l'agent")
    examples: list[str] = Field(
        default_factory=list, description="3 exemples de prompts utilisateur"
    )


class OnboardingChatResponse(BaseModel):
    message: str
    agent_config: OnboardingAgentConfig | None = None
