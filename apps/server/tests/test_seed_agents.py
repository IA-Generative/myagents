"""Tests for the default agents seed script."""

from sqlalchemy import select

from app.models.agent import Agent
from app.scripts.seed_agents import DEFAULT_AGENTS, seed_default_agents


async def test_seed_default_agents_creates_all_once(db_session):
    created = await seed_default_agents(db_session)
    assert created == len(DEFAULT_AGENTS)

    agents = (await db_session.execute(select(Agent))).scalars().all()
    assert len(agents) == len(DEFAULT_AGENTS)
    assert all(a.visibility.value == "ministry" for a in agents)
    assert all(a.status.value == "published" for a in agents)


async def test_seed_default_agents_is_idempotent(db_session):
    first = await seed_default_agents(db_session)
    second = await seed_default_agents(db_session)
    assert first == len(DEFAULT_AGENTS)
    assert second == 0

    agents = (await db_session.execute(select(Agent))).scalars().all()
    assert len(agents) == len(DEFAULT_AGENTS)


async def test_seeded_agents_are_visible_in_catalog(client, db_session):
    await seed_default_agents(db_session)

    res = await client.get("/api/catalog")
    assert res.status_code == 200
    assert len(res.json()) == len(DEFAULT_AGENTS)
