"""Business logic for agent CRUD, versioning, forking and publishing."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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
        model_ref=payload.config.model_id or "gpt-oss-120b",
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


async def get_accessible_agent(
    db: AsyncSession, agent_id: uuid.UUID, user_id: str
) -> Agent | None:
    """Agent readable by `user_id`: their own (non-archived) or one shared in the catalog."""
    agent = await get_agent(db, agent_id)
    if agent is None:
        return None
    if agent.creator_id == user_id and agent.status != AgentStatus.archived:
        return agent
    return agent if is_catalog_visible(agent) else None


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


async def list_catalog(db: AsyncSession, category: str | None = None) -> list[Agent]:
    stmt = _with_versions(
        select(Agent).where(
            Agent.visibility != Visibility.private,
            Agent.status.in_(_CATALOG_STATUSES),
        )
    )
    agents = list((await db.execute(stmt)).scalars().all())
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
