"""Tests de la reprise des données de l'ancienne app (lignes source factices, sans Postgres)."""

import uuid
from collections import Counter
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from app.models.agent import Agent, AgentVersion, Favorite, Rating
from app.models.enums import AgentStatus, Visibility
from app.schemas.agent import MAX_PROMPT_CHARS, ConfigSnapshot
from app.scripts.import_from_prisma import (
    ImportReport,
    Rejected,
    SourceData,
    build_plan,
    convert_agent,
    convert_snapshot,
    favorite_id,
    format_report,
    import_source,
)

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)
CREATED = datetime(2026, 3, 1, 9, 30, tzinfo=UTC)
USER = uuid.UUID("7d3f1c2a-1111-4a8b-9c3d-2e5f6a7b8c9d")
OTHER_USER = uuid.UUID("8e4a2d3b-2222-4b9c-8d4e-3f6a7b8c9d0e")
AGENT_A = uuid.UUID("11111111-aaaa-4aaa-8aaa-111111111111")
AGENT_B = uuid.UUID("22222222-bbbb-4bbb-8bbb-222222222222")


def _snapshot(**overrides) -> dict:
    """Snapshot tel qu'écrit par apps/next/app/api/ab/agents/route.ts."""
    snapshot = {
        "name": "Rédacteur de notes",
        "description": "Aide à rédiger des notes de service.",
        "category": "redaction",
        "visibility": "community",
        "communityPath": "dgfip/rh",
        "systemPrompt": "Rôle : rédacteur administratif.",
        "greeting": "Bonjour, que souhaitez-vous rédiger ?",
        "examples": ["Rédige une note.", "Prépare un courrier."],
        "modelId": "mistral-small-3.2-24b-instruct-2506",
        "temperature": 0.4,
    }
    snapshot.update(overrides)
    return snapshot


def _agent_row(agent_id=AGENT_A, **overrides) -> dict:
    row = {
        "id": agent_id,
        "owui_model_id": "mirai-redacteur-abc123",
        "creator_id": USER,
        "creator_direction": "DGFiP",
        "visibility": "community",
        "status": "published",
        "category": ["redaction"],
        "tags": [],
        "version": 2,
        "parent_agent_id": None,
        "quality_score": None,
        "created_at": CREATED,
        "updated_at": CREATED,
    }
    row.update(overrides)
    return row


def _version_row(agent_id=AGENT_A, version=1, snapshot=None, **overrides) -> dict:
    row = {
        "id": uuid.uuid5(agent_id, str(version)),
        "agent_id": agent_id,
        "version": version,
        "config_snapshot": snapshot if snapshot is not None else _snapshot(),
        "changelog": "Creation initiale via le wizard",
        "created_at": CREATED,
    }
    row.update(overrides)
    return row


def _source() -> SourceData:
    return SourceData(
        agents=[
            _agent_row(),
            _agent_row(AGENT_B, status="validated", version=1, parent_agent_id=AGENT_A),
        ],
        versions=[
            _version_row(version=1, snapshot=_snapshot(modelId="ancien-modele")),
            _version_row(version=2),
            _version_row(AGENT_B, version=1, snapshot=_snapshot(modelId=None)),
        ],
        ratings=[
            {
                "id": uuid.uuid4(),
                "agent_id": AGENT_A,
                "user_id": OTHER_USER,
                "score": 4,
                "comment": "Utile",
                "created_at": CREATED,
            },
            {
                "id": uuid.uuid4(),
                "agent_id": AGENT_B,
                "user_id": USER,
                "score": 9,
                "comment": None,
                "created_at": CREATED,
            },
        ],
        favorites=[{"user_id": OTHER_USER, "agent_id": AGENT_A, "folder": "default"}],
        skipped_counts={"ab_usage_stats": 3, "ab_guard_events": None},
    )


def test_convert_realistic_snapshot():
    notes: Counter[str] = Counter()
    config = convert_snapshot(_snapshot(), notes)

    assert config == ConfigSnapshot(
        name="Rédacteur de notes",
        description="Aide à rédiger des notes de service.",
        category="redaction",
        community_path="dgfip/rh",
        system_prompt="Rôle : rédacteur administratif.",
        greeting="Bonjour, que souhaitez-vous rédiger ?",
        examples=["Rédige une note.", "Prépare un courrier."],
        model_id="mistral-small-3.2-24b-instruct-2506",
        temperature=0.4,
        knowledge_ids=[],
        tool_ids=[],
    )
    assert not notes


def test_convert_snapshot_without_model_id_falls_back_to_default_model():
    notes: Counter[str] = Counter()
    config = convert_snapshot(_snapshot(modelId=None, communityPath=None), notes)
    assert config.model_id == ""
    assert config.community_path is None

    agent = convert_agent(
        _agent_row(), config.model_dump(), "modele-defaut", NOW, notes
    )
    assert agent["model_ref"] == "modele-defaut"
    assert notes["snapshot sans modelId"] == 1


def test_convert_snapshot_truncates_out_of_bounds_values():
    notes: Counter[str] = Counter()
    raw = _snapshot(
        name="n" * 300,
        systemPrompt="p" * (MAX_PROMPT_CHARS + 50),
        examples=["e" * 600] * 25 + [42],
        temperature=3.5,
        tools=["inconnu"],
    )
    config = convert_snapshot(raw, notes)

    # Le résultat repasse la validation Pydantic du nouveau schéma.
    assert ConfigSnapshot.model_validate(config.model_dump()) == config
    assert len(config.name) == 200
    assert len(config.system_prompt) == MAX_PROMPT_CHARS
    assert len(config.examples) == 20
    assert all(len(e) == 500 for e in config.examples)
    assert config.temperature == 2.0
    assert notes["name tronqué à 200 caractères"] == 1
    assert notes[f"system_prompt tronqué à {MAX_PROMPT_CHARS} caractères"] == 1
    assert notes["examples limité à 20 éléments"] == 1
    assert notes["examples : élément non texte retiré"] == 1
    assert notes["temperature ramenée dans [0, 2]"] == 1
    assert notes["clé de snapshot inconnue ignorée"] == 1


def test_convert_snapshot_rejects_non_object():
    with pytest.raises(Rejected):
        convert_snapshot(["pas", "un", "objet"], Counter())


def test_validated_status_becomes_published():
    notes: Counter[str] = Counter()
    agent = convert_agent(_agent_row(status="validated"), None, "defaut", NOW, notes)
    assert agent["status"] is AgentStatus.published
    assert agent["visibility"] is Visibility.community
    assert agent["creator_id"] == str(USER)
    assert notes["statut validated converti en published"] == 1


async def test_import_inserts_then_is_idempotent(db_session):
    first = await import_source(
        db_session, _source(), dry_run=False, default_model="defaut"
    )

    agents = first.tables["agents"]
    assert (agents.read, agents.inserted, agents.existing) == (2, 2, 0)
    assert first.tables["agent_versions"].inserted == 3
    assert first.tables["ratings"].inserted == 1
    assert first.tables["ratings"].rejected == Counter({"note hors de 1 à 5": 1})
    assert first.tables["favorites"].inserted == 1

    agent_a = await db_session.get(Agent, AGENT_A)
    # model_ref vient de la dernière version, pas de la première.
    assert agent_a.model_ref == "mistral-small-3.2-24b-instruct-2506"
    assert agent_a.creator_id == str(USER)
    assert agent_a.created_at.replace(tzinfo=UTC) == CREATED
    agent_b = await db_session.get(Agent, AGENT_B)
    assert agent_b.status is AgentStatus.published
    assert agent_b.model_ref == "defaut"
    assert agent_b.parent_agent_id == AGENT_A
    favorite = (await db_session.execute(select(Favorite))).scalar_one()
    assert favorite.id == favorite_id(AGENT_A, str(OTHER_USER))

    second = await import_source(
        db_session, _source(), dry_run=False, default_model="defaut"
    )
    for name, read in (("agents", 2), ("agent_versions", 3), ("favorites", 1)):
        assert second.tables[name].inserted == 0
        assert second.tables[name].existing == read
    assert second.tables["ratings"].inserted == 0
    assert (await db_session.scalar(select(func.count()).select_from(Agent))) == 2
    assert (
        await db_session.scalar(select(func.count()).select_from(AgentVersion))
    ) == 3


async def test_dry_run_writes_nothing(db_session):
    report = await import_source(
        db_session, _source(), dry_run=True, default_model="defaut"
    )

    assert report.tables["agents"].inserted == 2
    for model in (Agent, AgentVersion, Rating, Favorite):
        assert (await db_session.scalar(select(func.count()).select_from(model))) == 0
    text = format_report(report)
    assert "DRY-RUN" in text
    assert "ab_usage_stats : 3 ligne(s)" in text
    assert "ab_guard_events : table absente" in text


async def test_agent_with_unconvertible_latest_version_is_rejected(db_session):
    source = _source()
    source.versions[1]["config_snapshot"] = "pas du json"
    report = await import_source(
        db_session, source, dry_run=False, default_model="defaut"
    )

    assert report.tables["agents"].rejected == Counter(
        {"dernière version inconvertible": 1}
    )
    assert report.tables["agent_versions"].rejected == Counter({"agent rejeté": 2})
    assert report.tables["ratings"].rejected["agent rejeté ou absent"] == 1
    # L'agent dérivé est repris, sans son lien vers le parent rejeté.
    agent_b = await db_session.get(Agent, AGENT_B)
    assert agent_b.parent_agent_id is None
    assert await db_session.get(Agent, AGENT_A) is None


def test_report_contains_no_prompt_nor_identifier():
    report = ImportReport(dry_run=True)
    build_plan(_source(), report, default_model="defaut", now=NOW)
    text = format_report(report)
    assert "Rôle" not in text
    assert str(USER) not in text and str(AGENT_A) not in text
