"""Sème les capacités des veilles (chantier 3), idempotent :

- `web.collecter`      kind http (point d'accès interne `interne:web.collecter`), lecture seule,
                       monde ouvert ;
- `legifrance.rechercher` kind mcp vers le serveur MCP Légifrance (`LEGIFRANCE_MCP_URL`), outil
                       `legifrance_search`, compte technique porté par ce serveur (PISTE) ;
- `veille.synthese`    kind prompt, `grounding: input`, dépendances épinglées sur les deux outils.
Visibilité `ministry`, maturité `general`, versions au verdict « seed » (hors garde : aucune
définition rédigée par une personne).

    python -m app.scripts.seed_veilles
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.hashing import hash_canonique
from app.models.capability import Capability, CapabilityVersion
from app.veilles.collecte import Definition as WebCollecter

logger = logging.getLogger(__name__)
PROPRIETAIRE = "service:veilles"

PROMPT_VEILLE = """Tu es une veille documentaire du ministère de l'Intérieur. Tu reçois un SUJET, la liste des SOURCES permises et des pages de départ.
1. Si « legifrance » est dans les sources, appelle d'abord l'outil legifrance.rechercher avec le sujet.
2. Si « web » est dans les sources, appelle l'outil web.collecter avec le sujet (et les pages de départ en `urls`).
3. Rédige ensuite une synthèse courte (dix lignes au plus) UNIQUEMENT à partir des éléments rendus par ces outils : n'invente rien, ne complète pas de mémoire. Cite chaque élément utilisé par son lien. Si les outils ne rendent rien d'utile, dis-le en une phrase.
4. Termine par la liste des liens cités, un par ligne."""


def _definitions() -> list[dict]:
    settings = get_settings()
    return [
        {
            "name": WebCollecter.name,
            "kind": "http",
            "title": WebCollecter.title,
            "description": WebCollecter.description,
            "input_schema": WebCollecter.input_schema,
            "definition": {
                "method": "POST",
                "url": "interne:web.collecter",
                "identity": "service",
                "service_token_ref": "",
                "headers": {},
            },
            "dependencies": [],
            "grounding": "input",
            "annotations": dict(WebCollecter.annotations),
        },
        {
            "name": "legifrance.rechercher",
            "kind": "mcp",
            "title": "Rechercher sur Légifrance",
            "description": "Recherche dans les fonds juridiques de Légifrance (codes, lois, décrets, jurisprudence) par le serveur MCP Légifrance (PISTE). Réutilisation sous licence ouverte, source à citer.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Termes de recherche",
                        "maxLength": 300,
                    }
                },
                "required": ["query"],
            },
            "definition": {
                "endpoint": settings.legifrance_mcp_url
                or "https://legifrance-mcp.invalid/mcp",
                "tool": "legifrance_search",
                "identity": "service",
                "service_token_ref": "",
                "headers": {},
            },
            "dependencies": [],
            "grounding": "input",
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": True,
            },
        },
        {
            "name": "veille.synthese",
            "kind": "prompt",
            "title": "Veille : synthèse des sources",
            "description": "Synthétise, à partir des seules sources rendues par Légifrance et par les sites autorisés, les publications récentes sur un sujet ; cite chaque source par son lien.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "sujet": {"type": "string", "maxLength": 200},
                    "sources": {"type": "array", "items": {"type": "string"}},
                    "seeds": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["sujet"],
            },
            "definition": {
                "prompt": PROMPT_VEILLE,
                "model": settings.llm_default_model,
                "temperature": 0.2,
            },
            "dependencies": [
                {"name": "legifrance.rechercher", "version": 1},
                {"name": WebCollecter.name, "version": 1},
            ],
            "grounding": "input",
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": True,
            },
        },
    ]


async def semer(db: AsyncSession) -> list[str]:
    """Crée et publie les capacités absentes ; rend les noms créés."""
    crees: list[str] = []
    for d in _definitions():
        existante = (
            await db.execute(select(Capability).where(Capability.name == d["name"]))
        ).scalar_one_or_none()
        if existante is not None:
            continue
        cap = Capability(
            name=d["name"],
            kind=d["kind"],
            title=d["title"],
            description=d["description"],
            input_schema=d["input_schema"],
            definition=d["definition"],
            dependencies=d["dependencies"],
            grounding=d["grounding"],
            annotations=d["annotations"],
            examples=[],
            visibility="ministry",
            owner_sub=PROPRIETAIRE,
            status="published",
            current_version=1,
        )
        db.add(cap)
        await db.flush()
        db.add(
            CapabilityVersion(
                capability_id=cap.id,
                version=1,
                maturity="general",
                hash=hash_canonique(
                    d["definition"], d["input_schema"], d["dependencies"]
                ),
                title=d["title"],
                description=d["description"],
                definition=d["definition"],
                input_schema=d["input_schema"],
                dependencies=d["dependencies"],
                annotations=d["annotations"],
                grounding=d["grounding"],
                examples=[],
                published_by=PROPRIETAIRE,
                published_from="seed",
                guard_verdict="seed",
                guard_ruleset_version="seed",
                guard_details=[],
            )
        )
        crees.append(d["name"])
    await db.commit()
    return crees


async def _main() -> None:
    from app.db.session import SessionLocal

    async with SessionLocal() as db:
        crees = await semer(db)
    logger.info("[veilles] capacités semées : %s", crees or "aucune (déjà présentes)")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_main())
