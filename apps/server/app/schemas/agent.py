"""Pydantic schemas for the agent wizard draft and API payloads."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import AgentStatus, Visibility


class ConfigSnapshot(BaseModel):
    """Full wizard draft — mirrors the frontend's wizard store shape."""

    name: str
    description: str = ""
    category: str = ""
    community_path: str | None = None
    system_prompt: str = ""
    greeting: str = ""
    examples: list[str] = Field(default_factory=list)
    model_id: str = ""
    temperature: float = 0.7
    knowledge_ids: list[str] = Field(default_factory=list)
    tool_ids: list[str] = Field(default_factory=list)


class AgentCreate(BaseModel):
    visibility: Visibility = Visibility.private
    status: AgentStatus = AgentStatus.draft
    category: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    config: ConfigSnapshot


class AgentUpdate(BaseModel):
    visibility: Visibility | None = None
    status: AgentStatus | None = None
    category: list[str] | None = None
    tags: list[str] | None = None
    changelog: str | None = None
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


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]


class ChatResponse(BaseModel):
    reply: str


class RatingCreate(BaseModel):
    score: int = Field(ge=1, le=5)
    comment: str | None = None


class RatingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_id: uuid.UUID
    user_id: str
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
    prompt: str = ""
    hints: dict[str, str] = Field(default_factory=dict)


class PromptResponse(BaseModel):
    prompt: str


class SuggestStartersRequest(BaseModel):
    prompt: str
    count: int = 4


class SuggestStartersResponse(BaseModel):
    greeting: str = Field(
        description="Message d'accueil court (moins de 300 caractères), ton formel, en français"
    )
    examples: list[str] = Field(
        description="Exemples de prompts utilisateur réalistes, 40 à 120 caractères, en français"
    )


class PromptValidateRequest(BaseModel):
    prompt: str


class PromptValidateResponse(BaseModel):
    ok: bool
    message: str | None = None


class OnboardingMessage(BaseModel):
    role: str
    content: str


class OnboardingChatRequest(BaseModel):
    messages: list[OnboardingMessage]


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
