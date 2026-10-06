"""OpenAI-compatible schemas for the /v1 endpoints (Open WebUI connection)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.agent import ChatMessage

# Contrat d'agents : un consommateur envoie un contenu entier (transcription d'une réunion,
# document, passages d'une collection) dans le dernier message. 120 000 caractères, soit
# l'ordre de grandeur de la fenêtre des modèles de la passerelle ; au-delà, le modèle refuse
# et la route répond 502.
MAX_CONTENT_CHARS_V1 = 120_000


class OpenAIChatMessage(ChatMessage):
    content: str = Field(max_length=MAX_CONTENT_CHARS_V1)


class OpenAIModel(BaseModel):
    id: str
    object: Literal["model"] = "model"
    created: int
    owned_by: str = "myagents"
    name: str
    # Même forme qu'Open WebUI (`info.meta.description`) : les plug-ins bureautiques la lisent.
    info: dict | None = None


class OpenAIModelList(BaseModel):
    object: Literal["list"] = "list"
    data: list[OpenAIModel]


class OpenAIChatCompletionRequest(BaseModel):
    # extra="ignore": tolerate OpenAI params we don't use (temperature, max_tokens...),
    # the agent's own stored config always drives the actual LLM call.
    model_config = ConfigDict(extra="ignore")

    model: str = Field(max_length=255)
    messages: list[OpenAIChatMessage] = Field(max_length=500)
    stream: bool = False


class OpenAIChatCompletionChoice(BaseModel):
    index: int = 0
    message: ChatMessage
    finish_reason: str = "stop"


class OpenAIChatCompletionResponse(BaseModel):
    id: str
    object: Literal["chat.completion"] = "chat.completion"
    created: int
    model: str
    choices: list[OpenAIChatCompletionChoice]
    usage: dict[str, int] = Field(
        default_factory=lambda: {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
    )
