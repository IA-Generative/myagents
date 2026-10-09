"""Business logic for agent CRUD, versioning, forking and publishing."""

import uuid
from collections.abc import Iterable

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.models.agent import Agent, AgentVersion
from app.models.enums import AgentStatus, Visibility
from app.schemas.agent import AgentCreate, AgentListItem, AgentUpdate, ConfigSnapshot


def _with_versions(stmt):
    return stmt.options(selectinload(Agent.versions))


async def create_agent(
    db: AsyncSession, creator_id: str, payload: AgentCreate
) -> Agent:
    agent = Agent(
        creator_id=creator_id,
        model_ref=payload.config.model_id or get_settings().llm_default_model,
        visibility=payload.visibility,
        status=payload.status,
        category=payload.category,
        tags=payload.tags,
        version=1,
    )
    agent.versions.append(
        AgentVersion(
            version=1,
            config_snapshot=payload.config.model_dump(),
            changelog="Creation initiale",
        )
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent, attribute_names=["versions"])
    return agent


async def get_agent(db: AsyncSession, agent_id: uuid.UUID) -> Agent | None:
    stmt = _with_versions(select(Agent).where(Agent.id == agent_id))
    return (await db.execute(stmt)).scalar_one_or_none()


_CATALOG_STATUSES = (AgentStatus.published, AgentStatus.submitted)


def is_catalog_visible(agent: Agent) -> bool:
    """Agent shared with other users: non-private and published/submitted."""
    return agent.visibility != Visibility.private and agent.status in _CATALOG_STATUSES


def groupe_correspond(community_path: str | None, groups: Iterable[str]) -> bool:
    """La communauté déclarée fait-elle partie des groupes du jeton ?

    Un chemin (« /g/juridique ») se compare aux chemins complets ; un nom (« juridique ») au
    nom feuille — même règle que `OIDC_GROUPE_EXIGE` (app.core.security.has_required_group).
    """
    chemin = (community_path or "").strip()
    if not chemin:
        return False
    if chemin.startswith("/"):
        return chemin.rstrip("/") in {g.rstrip("/") for g in groups}
    return chemin in {g.rstrip("/").rsplit("/", 1)[-1] for g in groups}


def is_accessible(agent: Agent, user_id: str, groups: Iterable[str] = ()) -> bool:
    """LA règle d'accès (contrat d'agents §Les droits), la même pour toutes les surfaces.

    Son auteur voit tout sauf l'archivé ; les autres voient un agent publié ou soumis,
    ouvert au ministère ou à une communauté dont ils font partie.
    """
    if agent.status == AgentStatus.archived:
        return False
    if agent.creator_id == user_id:
        return True
    if agent.status not in _CATALOG_STATUSES:
        return False
    if agent.visibility == Visibility.ministry:
        return True
    if agent.visibility == Visibility.community:
        return groupe_correspond(current_config(agent).community_path, groups)
    return False


def is_in_catalog(agent: Agent, user_id: str, groups: Iterable[str] = ()) -> bool:
    """Dans le catalogue partagé : publié ou soumis, non privé, et accessible à la personne.

    Ses propres brouillons n'y figurent pas (ils sont dans « Mes agents »).
    """
    return is_catalog_visible(agent) and is_accessible(agent, user_id, groups)


async def get_accessible_agent(
    db: AsyncSession, agent_id: uuid.UUID, user_id: str, groups: Iterable[str] = ()
) -> Agent | None:
    """Agent readable by `user_id`: their own (non-archived) or one shared with them."""
    agent = await get_agent(db, agent_id)
    if agent is None:
        return None
    return agent if is_accessible(agent, user_id, groups) else None


async def list_accessible(
    db: AsyncSession, user_id: str, groups: Iterable[str] = ()
) -> list[Agent]:
    """Les agents que `user_id` peut lancer : les siens d'abord, puis les partagés avec lui."""
    groups = list(groups)
    stmt = _with_versions(
        select(Agent)
        .where(
            Agent.status != AgentStatus.archived,
            or_(
                Agent.creator_id == user_id,
                and_(
                    Agent.visibility != Visibility.private,
                    Agent.status.in_(_CATALOG_STATUSES),
                ),
            ),
        )
        .order_by(Agent.updated_at.desc())
    )
    agents = [
        a
        for a in (await db.execute(stmt)).scalars().all()
        if is_accessible(a, user_id, groups)
    ]
    agents.sort(key=lambda a: a.creator_id != user_id)  # stable : les miens d'abord
    return agents


async def list_my_agents(db: AsyncSession, creator_id: str) -> list[Agent]:
    stmt = _with_versions(
        select(Agent)
        .where(Agent.creator_id == creator_id, Agent.status != AgentStatus.archived)
        .order_by(Agent.updated_at.desc())
    )
    return list((await db.execute(stmt)).scalars().all())


async def list_exposed_agents(db: AsyncSession) -> list[Agent]:
    """Agents made available to external OpenAI-compatible callers (catalog-visible only)."""
    stmt = _with_versions(
        select(Agent)
        .where(
            Agent.visibility != Visibility.private,
            Agent.status.in_(_CATALOG_STATUSES),
        )
        .order_by(Agent.updated_at.desc())
    )
    return list((await db.execute(stmt)).scalars().all())


async def list_catalog(
    db: AsyncSession,
    category: str | None = None,
    user_id: str | None = None,
    groups: Iterable[str] = (),
) -> list[Agent]:
    """Catalogue partagé. Avec `user_id`, les agents de communauté sont filtrés par groupe."""
    groups = list(groups)
    stmt = _with_versions(
        select(Agent).where(
            Agent.visibility != Visibility.private,
            Agent.status.in_(_CATALOG_STATUSES),
        )
    )
    agents = list((await db.execute(stmt)).scalars().all())
    if user_id is not None:
        agents = [a for a in agents if is_in_catalog(a, user_id, groups)]
    if category:
        agents = [a for a in agents if category in a.category]
    return agents


def current_config(agent: Agent) -> ConfigSnapshot:
    latest = agent.versions[0] if agent.versions else None
    return (
        ConfigSnapshot.model_validate(latest.config_snapshot)
        if latest
        else ConfigSnapshot(name="")
    )


def to_list_item(agent: Agent) -> AgentListItem:
    return AgentListItem(
        id=agent.id,
        creator_id=agent.creator_id,
        name=current_config(agent).name,
        model_ref=agent.model_ref,
        visibility=agent.visibility,
        status=agent.status,
        category=agent.category,
        tags=agent.tags,
        version=agent.version,
        created_at=agent.created_at,
        updated_at=agent.updated_at,
    )


async def update_agent(db: AsyncSession, agent: Agent, payload: AgentUpdate) -> Agent:
    if payload.visibility is not None:
        agent.visibility = payload.visibility
    if payload.status is not None:
        agent.status = payload.status
    if payload.category is not None:
        agent.category = payload.category
    if payload.tags is not None:
        agent.tags = payload.tags

    agent.version += 1
    agent.model_ref = payload.config.model_id or agent.model_ref
    agent.versions.insert(
        0,
        AgentVersion(
            version=agent.version,
            config_snapshot=payload.config.model_dump(),
            changelog=payload.changelog or "Modification via le wizard",
        ),
    )
    await db.commit()
    await db.refresh(agent, attribute_names=["versions"])
    return agent


async def archive_agent(db: AsyncSession, agent: Agent) -> Agent:
    agent.status = AgentStatus.archived
    await db.commit()
    return agent


async def submit_agent(db: AsyncSession, agent: Agent) -> Agent:
    agent.status = AgentStatus.submitted
    await db.commit()
    return agent


async def fork_agent(db: AsyncSession, source: Agent, creator_id: str) -> Agent:
    config = current_config(source)
    if source.creator_id != creator_id:
        # Les bases de connaissances appartiennent à l'auteur d'origine.
        config = config.model_copy(update={"knowledge_ids": []})
    payload = AgentCreate(
        visibility=Visibility.private,
        status=AgentStatus.draft,
        category=list(source.category),
        tags=list(source.tags),
        config=config,
    )
    return await create_agent(db, creator_id, payload)
