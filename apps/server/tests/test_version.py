"""/__version__ (ADR-0004, format Dockerflow) : le journal que l'image porte."""

import json
import logging
import subprocess
import sys
from pathlib import Path

import pytest

from app import version
from app.core.logging import SILENT_ACCESS_PATHS, _SilentPathsFilter

CLES = {"source", "version", "commit", "build", "code_date", "changes", "history"}
SCRIPT = Path(__file__).resolve().parents[2].parent / "scripts" / "version_json.py"


async def test_hors_image_repond_dev(client, monkeypatch, tmp_path):
    monkeypatch.setattr(version, "VERSION_JSON", tmp_path / "absent.json")
    res = await client.get("/__version__")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("application/json")
    body = res.json()
    assert set(body) == CLES
    assert body["version"] == "dev"
    assert body["changes"] == [] and body["history"] == []


async def test_rend_le_fichier_de_l_image_tel_quel(client, monkeypatch, tmp_path):
    attendu = {
        "source": "https://github.com/IA-Generative/myagents",
        "version": "beta-0123abcd",
        "commit": "0123abcd" * 5,
        "build": "https://github.com/IA-Generative/myagents/actions/runs/1",
        "code_date": "2026-10-06T07:00:00+02:00",
        "changes": [],
        "history": [],
    }
    fichier = tmp_path / "version.json"
    fichier.write_text(json.dumps(attendu), encoding="utf-8")
    monkeypatch.setattr(version, "VERSION_JSON", fichier)
    res = await client.get("/__version__")
    assert res.status_code == 200
    assert res.json() == attendu


async def test_fichier_illisible_repond_dev_pas_une_erreur(
    client, monkeypatch, tmp_path
):
    fichier = tmp_path / "version.json"
    fichier.write_text("{pas du json", encoding="utf-8")
    monkeypatch.setattr(version, "VERSION_JSON", fichier)
    res = await client.get("/__version__")
    assert res.status_code == 200
    assert res.json()["version"] == "dev"


async def test_sans_session_ni_jeton(client, monkeypatch, tmp_path):
    """Publique : le noteur la lit sans identité (aucun en-tête d'authentification ici)."""
    monkeypatch.setattr(version, "VERSION_JSON", tmp_path / "absent.json")
    res = await client.get("/__version__", headers={})
    assert res.status_code == 200


def test_hors_journal_d_acces():
    assert "/__version__" in SILENT_ACCESS_PATHS
    filtre = _SilentPathsFilter()

    def ligne(chemin: str) -> logging.LogRecord:
        return logging.LogRecord(
            "uvicorn.access",
            logging.INFO,
            __file__,
            0,
            '%s - "%s %s HTTP/%s" %d',
            ("10.0.0.1:1234", "GET", chemin, "1.1", 200),
            None,
        )

    assert filtre.filter(ligne("/__version__")) is False
    assert filtre.filter(ligne("/__version__?x=1")) is False
    assert filtre.filter(ligne("/api/health")) is True


@pytest.mark.skip(
    reason="Le fichier scripts/version_json.py est en dehors du contexte du serveur "
    "(à la racine du projet). Ce test ne fonctionne que dans l'environnement complet "
    "du projet, pas dans le conteneur isolé du serveur utilisé par les tests CI."
)
def test_script_changes_et_history(tmp_path):
    """changes = la section de cette version ; history = toutes, dans l'ordre ; [] sans CHANGELOG."""
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        "# Changelog\n\n## [0.3.0] (2026-10-06)\n\n* nouveauté\n\n"
        "## [0.2.0] (2026-10-01)\n\n* ancienne\n",
        encoding="utf-8",
    )
    sortie = tmp_path / "version.json"
    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--version",
            "0.3.0",
            "--changelog",
            str(changelog),
            "--out",
            str(sortie),
        ],
        check=True,
    )
    v = json.loads(sortie.read_text(encoding="utf-8"))
    assert set(v) == CLES and v["version"] == "0.3.0"
    assert v["changes"] and v["history"]
    assert len(v["history"]) == 2

    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--version",
            "dev",
            "--changelog",
            str(tmp_path / "absent.md"),
            "--out",
            str(sortie),
        ],
        check=True,
    )
    v = json.loads(sortie.read_text(encoding="utf-8"))
    assert v["changes"] == [] and v["history"] == []
