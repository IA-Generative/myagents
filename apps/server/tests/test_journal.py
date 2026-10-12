"""Journal des exécutions (règle 6, §10.0) : une ligne JSON par appel, champs minimaux, sans contenu,
exportable."""

import json
import logging

import pytest

from app.services import journal
from tests.outils_capacites import entetes, fiche_prompt

pytestmark = pytest.mark.usefixtures("juge_definition_favorable")

CHAMPS = (
    "ts",
    "capability",
    "version",
    "hash",
    "sub",
    "azp",
    "scope_used",
    "guard_in",
    "guard_out",
    "duration_ms",
    "status",
)


def test_champs_minimaux_du_contrat():
    assert tuple(journal.CHAMPS[: len(CHAMPS)]) == CHAMPS


class _Capture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.lignes: list[str] = []

    def emit(self, record):
        self.lignes.append(record.getMessage())


async def test_une_ligne_json_sur_le_logger_dedie(client, fake_llm):
    res = await client.post(
        "/api/v2/capabilities", json=fiche_prompt(), headers=entetes()
    )
    cap = res.json()
    await client.post(
        f"/api/v2/capabilities/{cap['id']}/publish",
        json={"maturity": "general"},
        headers=entetes(),
    )
    capture = _Capture()
    logger = logging.getLogger("mesagents.journal")
    logger.addHandler(capture)
    try:
        res = await client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "executer_capacite",
                    "arguments": {
                        "name": cap["name"],
                        "arguments": {"text": "SECRET-ENTREE"},
                    },
                },
            },
            headers={**entetes(), "Accept": "application/json, text/event-stream"},
        )
    finally:
        logger.removeHandler(capture)
    assert res.json()["result"]["isError"] is False
    assert len(capture.lignes) == 1
    ligne = json.loads(capture.lignes[0])
    for champ in CHAMPS:
        assert champ in ligne, champ
    assert ligne["capability"] == cap["name"] and ligne["status"] == "ok"
    assert logger.propagate is False
    assert "SECRET-ENTREE" not in capture.lignes[0]
    assert "Réponse simulée" not in capture.lignes[0]


async def test_export_json_lines_par_l_auteur_et_par_l_admin(client, fake_llm):
    res = await client.post(
        "/api/v2/capabilities", json=fiche_prompt(), headers=entetes()
    )
    cap = res.json()
    await client.post(
        f"/api/v2/capabilities/{cap['id']}/publish",
        json={"maturity": "general"},
        headers=entetes(),
    )
    for i in range(3):
        fake_llm.responses.append(
            __import__("langchain_core.messages", fromlist=["AIMessage"]).AIMessage(
                f"r{i}"
            )
        )
        await client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "executer_capacite",
                    "arguments": {"name": cap["name"], "arguments": {"text": str(i)}},
                },
            },
            headers={**entetes(), "Accept": "application/json, text/event-stream"},
        )
    res = await client.get(
        f"/api/v2/capabilities/{cap['id']}/runs?limit=2", headers=entetes()
    )
    assert res.status_code == 200 and res.headers["content-type"].startswith(
        "application/x-ndjson"
    )
    assert len([l for l in res.text.splitlines() if l.strip()]) == 2
    # Un autre que l'auteur : 404 ; la revue/administration : export global.
    assert (
        await client.get(
            f"/api/v2/capabilities/{cap['id']}/runs", headers=entetes(sub="bob")
        )
    ).status_code == 404
    admin = entetes(
        sub="admin",
        roles="mesagents-reviewer",
        portees="mesagents:read mesagents:review",
    )
    res = await client.get("/api/v2/admin/runs", headers=admin)
    assert res.status_code == 200
    assert len([l for l in res.text.splitlines() if l.strip()]) >= 3
    assert (
        await client.get("/api/v2/admin/runs", headers=entetes())
    ).status_code == 403
