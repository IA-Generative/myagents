"""Schémas Pydantic des capacités (ADR §4.1, §4.1 bis, §4.5).

Les champs posés par le service (`published_by`, `published_from`, `hash`, `version`, `status`,
`owner_sub`) ne sont PAS dans les schémas d'entrée : envoyés par un client, ils sont ignorés
(`extra="ignore"`, C-C1).
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Kind = Literal["prompt", "mcp", "http"]
Grounding = Literal["input", "open"]
Maturity = Literal["alpha", "beta", "general"]
Visibility = Literal["private", "community", "ministry"]
Identity = Literal["user", "service"]

SLUG = r"^[a-z0-9][a-z0-9._-]{2,63}$"
Slug = Annotated[str, StringConstraints(pattern=SLUG)]
MAX_PROMPT = 20_000
MAX_DESCRIPTION = 2_000
MAX_EXEMPLES = 20
MAX_DEPENDANCES = 20

# Annotations MCP standard, servies telles quelles dans tools/list (ADR §4.1 bis).
ANNOTATIONS_DEFAUT_PROMPT = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": False,
    "openWorldHint": False,
}
# Sans annotation, un outil externe est réputé destructif et ouvert sur le monde (MCP).
ANNOTATIONS_DEFAUT_OUTIL = {
    "readOnlyHint": False,
    "destructiveHint": True,
    "idempotentHint": False,
    "openWorldHint": True,
}


class Annotations(BaseModel):
    model_config = ConfigDict(extra="ignore")

    readOnlyHint: bool | None = None
    destructiveHint: bool | None = None
    idempotentHint: bool | None = None
    openWorldHint: bool | None = None


class Dependency(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: Slug
    version: int = Field(ge=1)


class Example(BaseModel):
    model_config = ConfigDict(extra="ignore")

    input: dict[str, Any]
    expected: str | None = Field(default=None, max_length=MAX_DESCRIPTION)


class PromptDefinition(BaseModel):
    model_config = ConfigDict(extra="ignore")

    prompt: str = Field(min_length=1, max_length=MAX_PROMPT)
    model: str = Field(default="", max_length=255)
    temperature: float = Field(default=0.7, ge=0, le=2)
    greeting: str = Field(default="", max_length=MAX_DESCRIPTION)
    legacy: dict[str, Any] | None = None


class McpDefinition(BaseModel):
    model_config = ConfigDict(extra="ignore")

    endpoint: str = Field(max_length=2048)
    tool: str = Field(max_length=128)
    identity: Identity = "user"
    service_token_ref: str = Field(default="", max_length=64)
    headers: dict[str, str] = Field(default_factory=dict)


class HttpDefinition(BaseModel):
    model_config = ConfigDict(extra="ignore")

    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] = "POST"
    url: str = Field(max_length=2048)
    identity: Identity = "service"
    service_token_ref: str = Field(default="", max_length=64)
    headers: dict[str, str] = Field(default_factory=dict)


DEFINITIONS: dict[str, type[BaseModel]] = {
    "prompt": PromptDefinition,
    "mcp": McpDefinition,
    "http": HttpDefinition,
}


def valider_definition(kind: str, definition: dict[str, Any]) -> dict[str, Any]:
    """Valide la définition selon le genre et la rend normalisée (dict)."""
    modele = DEFINITIONS[kind]
    return modele.model_validate(definition).model_dump(exclude_none=True)


def valider_schema(schema: dict[str, Any]) -> dict[str, Any]:
    if schema.get("type", "object") != "object":
        raise ValueError("input_schema doit décrire un objet (type: object)")
    proprietes = schema.get("properties", {})
    if not isinstance(proprietes, dict):
        raise TypeError("input_schema.properties doit être un objet")
    requis = schema.get("required", [])
    if not isinstance(requis, list) or any(r not in proprietes for r in requis):
        raise ValueError("input_schema.required cite une propriété absente")
    return {"type": "object", **schema}


class CapabilityCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: Slug
    kind: Kind
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=MAX_DESCRIPTION)
    input_schema: dict[str, Any] = Field(
        default_factory=lambda: {"type": "object", "properties": {}}
    )
    output_schema: dict[str, Any] | None = None
    definition: dict[str, Any]
    dependencies: list[Dependency] = Field(
        default_factory=list, max_length=MAX_DEPENDANCES
    )
    grounding: Grounding = "input"
    annotations: Annotations | None = None
    visibility: Visibility = "private"
    community_path: str | None = Field(default=None, max_length=255)
    examples: list[Example] = Field(default_factory=list, max_length=MAX_EXEMPLES)
    run_as: Literal["user"] = "user"

    @model_validator(mode="after")
    def _coherence(self) -> CapabilityCreate:
        self.definition = valider_definition(self.kind, self.definition)
        self.input_schema = valider_schema(self.input_schema)
        if self.visibility == "community" and not (self.community_path or "").strip():
            raise ValueError("community_path est requis pour la visibilité community")
        noms = [d.name for d in self.dependencies]
        if len(set(noms)) != len(noms):
            raise ValueError("une dépendance est déclarée deux fois")
        return self


class CapabilityPatch(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=MAX_DESCRIPTION)
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    definition: dict[str, Any] | None = None
    dependencies: list[Dependency] | None = Field(
        default=None, max_length=MAX_DEPENDANCES
    )
    grounding: Grounding | None = None
    annotations: Annotations | None = None
    visibility: Visibility | None = None
    community_path: str | None = Field(default=None, max_length=255)
    examples: list[Example] | None = Field(default=None, max_length=MAX_EXEMPLES)


class PublishRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    maturity: Maturity = "alpha"
    visibility: Visibility | None = None
    community_path: str | None = Field(default=None, max_length=255)


class TestRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    arguments: dict[str, Any] = Field(default_factory=dict)


class SuspendRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    reason: str = Field(default="", max_length=500)
