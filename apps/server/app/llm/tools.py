"""Registry of built-in tools an agent creator can attach to their agent.

Mirrors `catalog.py` for models: a small static list the frontend renders as
checkboxes, plus a resolver turning selected ids into real LangChain tools.
"""

import logging
import re
import unicodedata
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from langchain_core.tools import BaseTool, StructuredTool, tool

from app.core import signing
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.llm.presentations.builder import build_pptx, get_theme
from app.llm.presentations.schema import DeckSpec, SlideSpec
from app.llm.presentations.themes import DEFAULT_THEME, THEMES
from app.schemas.agent import ToolProfile
from app.services import presentations as presentations_service

logger = logging.getLogger(__name__)


@tool
def current_datetime() -> str:
    """Renvoie la date et l'heure actuelles (UTC, ISO 8601)."""
    return datetime.now(UTC).isoformat()


@tool
def list_presentation_themes() -> str:
    """Liste les thèmes graphiques disponibles pour create_presentation."""
    return "\n".join(f"- {t.name} : {t.description}" for t in THEMES.values())


def _slugify(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")[:60].strip("-")
    return slug or "presentation"


async def _create_presentation(
    title: str,
    slides: list[SlideSpec],
    subtitle: str = "",
    author: str = "",
    theme: str = DEFAULT_THEME,
) -> str:
    deck = DeckSpec(
        title=title, slides=slides, subtitle=subtitle, author=author, theme=theme
    )
    try:
        get_theme(deck.theme)
        data = build_pptx(deck)
        settings = get_settings()
        ttl = timedelta(minutes=settings.presentation_ttl_minutes)
        async with SessionLocal() as db:
            generated = await presentations_service.save_file(
                db,
                filename=f"{_slugify(deck.title)}.pptx",
                content_type=presentations_service.PPTX_CONTENT_TYPE,
                data=data,
                ttl=ttl,
            )
        url = signing.build_download_url(generated.id, int(ttl.total_seconds()))
    except ValueError as exc:
        return f"Erreur : {exc}"
    except signing.SigningUnavailableError:
        logger.error("create_presentation: aucun secret de signature configuré")
        return "Erreur : la génération de liens de téléchargement est indisponible."

    return (
        f"Présentation générée ({len(deck.slides) + 1} diapositives, thème {deck.theme}). "
        f"Lien de téléchargement valable {settings.presentation_ttl_minutes} minutes, "
        f"à transmettre tel quel à l'utilisateur : [{generated.filename}]({url})"
    )


create_presentation = StructuredTool.from_function(
    coroutine=_create_presentation,
    name="create_presentation",
    description=(
        "Génère un fichier PowerPoint (.pptx) à partir d'un plan complet de diapositives "
        "et renvoie un lien de téléchargement. Une page de titre est ajoutée "
        "automatiquement. Layouts : section, bullets, two_column, table, chart."
    ),
    args_schema=DeckSpec,
)

TOOL_REGISTRY: dict[str, Callable[[], BaseTool]] = {
    "current_datetime": lambda: current_datetime,
    "create_presentation": lambda: create_presentation,
    "list_presentation_themes": lambda: list_presentation_themes,
}

AVAILABLE_TOOLS: list[ToolProfile] = [
    ToolProfile(
        id="current_datetime",
        label="Date et heure actuelles",
        description="Permet à l'agent de connaître la date et l'heure du jour.",
    ),
    ToolProfile(
        id="create_presentation",
        label="Création de présentations PowerPoint",
        description=(
            "Génère un fichier .pptx (titres, puces, tableaux, graphiques, notes) et "
            "fournit un lien de téléchargement temporaire."
        ),
    ),
    ToolProfile(
        id="list_presentation_themes",
        label="Thèmes de présentation",
        description="Liste les thèmes graphiques disponibles pour les présentations.",
    ),
]


def resolve_tools(tool_ids: list[str], knowledge_ids: list[str]) -> list[BaseTool]:
    """Turn an agent's `tool_ids`/`knowledge_ids` config into bound LangChain tools."""
    tools: list[BaseTool] = []
    for tool_id in tool_ids:
        factory = TOOL_REGISTRY.get(tool_id)
        if factory is None:
            logger.warning("tool_id inconnu ignoré: %s", tool_id)
            continue
        tools.append(factory())

    if knowledge_ids:
        from app.llm.rag import build_retriever_tool

        tools.append(build_retriever_tool(knowledge_ids))

    return tools
