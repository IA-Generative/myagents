"""Convention ADR-0004 MirAI next, format Dockerflow : /app/version.json servi sur /__version__.

Le fichier est écrit au build de l'image (Dockerfile, scripts/version_json.py). Route publique,
hors schéma OpenAPI, hors journaux d'accès (VERSION_PATH dans app.main et app.core.logging) : le
noteur de version la lit par le Service interne.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter

VERSION_PATH = "/__version__"
VERSION_JSON = Path("/app/version.json")
DEV = {
    "source": "",
    "version": "dev",
    "commit": "",
    "build": "",
    "code_date": "",
    "changes": [],
    "history": [],
}

router = APIRouter()


@router.get(VERSION_PATH, include_in_schema=False)
def version_json() -> dict:
    """Le journal que l'image porte. Hors image le fichier manque : « dev », jamais une erreur."""
    try:
        return json.loads(VERSION_JSON.read_text(encoding="utf-8"))
    except OSError, ValueError:
        return dict(DEV)
