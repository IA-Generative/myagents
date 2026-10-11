"""Shared pytest fixtures: isolated in-memory DB + async test client."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core import ratelimit
from app.db.base import Base
from app.db.session import get_db
from app.main import app


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    ratelimit.reset()
    yield
    ratelimit.reset()


@pytest.fixture
async def session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
async def db_session(session_factory):
    async with session_factory() as session:
        yield session


@pytest.fixture
async def client(session_factory):
    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# --- Capacités gouvernées (ADR Mes agents) -----------------------------------------------


@pytest.fixture
def juge_definition_favorable(monkeypatch):
    """Juge LLM de définition simulé : défavorable seulement si la définition porte « POISON »."""
    from app.llm.guard import definition as definition_module
    from app.llm.guard.core import Verdict

    async def _juger(texte: str, **_):
        return Verdict("POISON" in texte, "juge de définition simulé")

    monkeypatch.setattr(definition_module, "juger_definition", _juger)
    return _juger


@pytest.fixture
def fake_llm(monkeypatch):
    """Modèle simulé branché sur LlmClient.chat_model ; la file `responses` est remplissable."""
    from unittest.mock import patch

    from langchain_core.messages import AIMessage

    from app.llm.client import LlmClient
    from tests.fakes import FakeToolCallingModel

    fake = FakeToolCallingModel(responses=[AIMessage("Réponse simulée.")])
    with patch.object(LlmClient, "chat_model", return_value=fake):
        yield fake


# --- Veilles (chantier 3) ---------------------------------------------------------------


@pytest.fixture
def garde_noms_favorable(monkeypatch):
    """Garde des sujets simulée : refus seulement si le sujet porte « PERSONNE »."""
    from app.veilles import garde_noms

    async def _verifier(sujet: str, **_):
        return garde_noms.VerdictSujet("PERSONNE" not in sujet, "garde simulée")

    monkeypatch.setattr(garde_noms, "verifier_sujet", _verifier)
    return _verifier


@pytest.fixture
async def capacites_de_veille(client):
    """Sème les capacités des veilles (web.collecter, legifrance.rechercher, veille.synthese)
    comme le fait `python -m app.scripts.seed_veilles`."""
    from app.db.session import get_db
    from app.main import app
    from app.scripts.seed_veilles import semer

    get_session = app.dependency_overrides[get_db]
    async for db in get_session():
        await semer(db)
        break
