"""Migration « capacités gouvernées » : copie des agents, réversible, idempotente (SQLite ici ;
rejouée sur Postgres dans le compose de conformité)."""

import json
import sqlite3
import uuid
from pathlib import Path

import pytest
from alembic.config import Config

from alembic import command
from app.core.config import get_settings

ICI = Path(__file__).resolve().parent.parent
AVANT = "c3f5a7b9d124"


@pytest.fixture
def base(tmp_path, monkeypatch):
    chemin = tmp_path / "migration.db"
    monkeypatch.setattr(get_settings(), "database_url", f"sqlite+aiosqlite:///{chemin}")
    cfg = Config(str(ICI / "alembic.ini"))
    cfg.set_main_option("script_location", str(ICI / "alembic"))
    return cfg, chemin


def _agent(con, *, status, visibility, name, community_path=None, published=True):
    aid = str(uuid.uuid4()).replace("-", "") if False else str(uuid.uuid4())
    con.execute(
        "INSERT INTO agents (id, creator_id, model_ref, visibility, status, category, tags, version, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            aid.replace("-", ""),
            "alice",
            "chat",
            visibility,
            status,
            "[]",
            "[]",
            2,
            "2026-10-01 10:00:00",
            "2026-10-02 10:00:00",
        ),
    )
    for v in (1, 2):
        snap = {
            "name": name,
            "description": f"desc {name}",
            "system_prompt": f"Prompt v{v} de {name}",
            "examples": ["ex1", "ex2"],
            "model_id": "chat",
            "temperature": 0.5,
            "community_path": community_path,
            "knowledge_ids": [],
            "tool_ids": ["current_datetime"],
        }
        con.execute(
            "INSERT INTO agent_versions (id, agent_id, version, config_snapshot, changelog, created_at) VALUES (?,?,?,?,?,?)",
            (
                str(uuid.uuid4()).replace("-", ""),
                aid.replace("-", ""),
                v,
                json.dumps(snap),
                None,
                "2026-10-01 10:00:00",
            ),
        )
    return aid


def test_upgrade_copie_les_agents_puis_downgrade_les_laisse_intacts(base):
    cfg, chemin = base
    command.upgrade(cfg, AVANT)
    con = sqlite3.connect(chemin)
    _agent(con, status="draft", visibility="private", name="Mon brouillon")
    _agent(con, status="published", visibility="ministry", name="Relecteur")
    _agent(
        con,
        status="submitted",
        visibility="community",
        name="Préparateur",
        community_path="/g/G1",
    )
    _agent(con, status="archived", visibility="ministry", name="Archivé")
    _agent(
        con, status="published", visibility="ministry", name="Relecteur"
    )  # collision de slug
    con.commit()

    command.upgrade(cfg, "head")
    caps = con.execute(
        "SELECT name, kind, status, grounding, visibility, community_path, current_version, annotations, definition, input_schema FROM capabilities ORDER BY name"
    ).fetchall()
    noms = [c[0] for c in caps]
    assert len(caps) == 5
    assert (
        "relecteur" in noms
        and "relecteur-2" in noms
        and "mon-brouillon" in noms
        and "archive" in noms
    )
    par_nom = {c[0]: c for c in caps}
    assert (
        par_nom["mon-brouillon"][2] == "draft" and par_nom["mon-brouillon"][6] is None
    )
    assert par_nom["relecteur"][2] == "published" and par_nom["relecteur"][6] == 1
    assert (
        par_nom["preparateur"][2] == "published"
        and par_nom["preparateur"][5] == "/g/G1"
    )
    assert par_nom["archive"][2] == "retired"
    assert all(c[1] == "prompt" and c[3] == "open" for c in caps)
    ann = json.loads(par_nom["relecteur"][7])
    assert ann["readOnlyHint"] is True
    definition = json.loads(par_nom["relecteur"][8])
    assert definition["prompt"] == "Prompt v2 de Relecteur"  # le dernier instantané
    assert definition["legacy"]["tool_ids"] == ["current_datetime"]
    assert json.loads(par_nom["relecteur"][9])["required"] == ["text"]

    versions = con.execute(
        "SELECT version, maturity, hash, published_by, published_from, guard_verdict, guard_ruleset_version FROM capability_versions"
    ).fetchall()
    assert len(versions) == 3  # published, submitted, published (collision)
    assert all(
        v[0] == 1
        and v[1] == "alpha"
        and len(v[2]) == 64
        and v[3] == "alice"
        and v[4] == "migration"
        and v[5] == "migrated"
        for v in versions
    )

    # Idempotence : rejouer la migration ne duplique rien.
    command.downgrade(cfg, AVANT)
    assert (
        con.execute(
            "SELECT name FROM sqlite_master WHERE name IN ('capabilities','capability_versions','runs','pins','suspended_clients')"
        ).fetchall()
        == []
    )
    assert con.execute("SELECT count(*) FROM agents").fetchone()[0] == 5
    assert con.execute("SELECT count(*) FROM agent_versions").fetchone()[0] == 10
    command.upgrade(cfg, "head")
    assert con.execute("SELECT count(*) FROM capabilities").fetchone()[0] == 5
    command.downgrade(cfg, AVANT)
    command.upgrade(cfg, "head")
    assert con.execute("SELECT count(*) FROM capability_versions").fetchone()[0] == 3
    con.close()


def test_hash_de_la_migration_egal_au_hash_canonique(base):
    """La copie figée de la fonction dans la migration donne le même hash que `app.core.hashing`."""
    import importlib.util

    from app.core.hashing import hash_canonique

    chemin = next((ICI / "alembic" / "versions").glob("*capacites_gouvernees.py"))
    spec = importlib.util.spec_from_file_location("migration_capacites", chemin)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    d, s, deps = {"prompt": "é"}, {"type": "object"}, [{"name": "a", "version": 1}]
    assert module.hash_canonique(d, s, deps) == hash_canonique(d, s, deps)
