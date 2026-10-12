"""Suite de conformité C-A1…C-A12 (ADR §10.1), jouée en HTTP contre une instance de Mes agents.

Deux cibles :
- le compose de conformité (`docker-compose.conformite.yml`) : BASE_URL, KEYCLOAK_URL,
  CONFORMITE_PASSWORD — jetons obtenus par mot de passe (direct grant) sur le realm `conformite` ;
- une preview : BASE_URL + JETONS_DIR (fichiers `<client>-<compte>.json` écrits par
  `scripts/jeton-preview.py`, rafraîchis ici par `refresh_token`).

Hors de ces deux cas la suite est ignorée (pytest.skip), jamais en échec.
"""

import json
import os
import time
import uuid
from pathlib import Path

import httpx
import pytest

BASE_URL = os.environ.get("BASE_URL", "")
KEYCLOAK_URL = os.environ.get("KEYCLOAK_URL", "")
REALM = os.environ.get("KEYCLOAK_REALM", "conformite")
MOT_DE_PASSE = os.environ.get("CONFORMITE_PASSWORD", "")
JETONS_DIR = os.environ.get("JETONS_DIR", "")
VOLUME = int(os.environ.get("CONFORMITE_VOLUME", "200"))

CLIENT_COMPLET = os.environ.get("CLIENT_COMPLET", "surface-complete")
CLIENT_SOCLE = os.environ.get("CLIENT_SOCLE", "socle")
CLIENT_SUSPENDU = os.environ.get("CLIENT_SUSPENDU", "client-suspendu")
G1 = os.environ.get("GROUPE_G1", "/g/G1")
G2 = os.environ.get("GROUPE_G2", "/g/G2")

PORTEES_COMPLETES = "mesagents:read mesagents:act mesagents:author mesagents:review"

compose_only = pytest.mark.skipif(
    bool(JETONS_DIR),
    reason="exige le compose de conformité (clients et comptes dédiés)",
)


def pytest_collection_modifyitems(config, items):
    if not BASE_URL:
        saute = pytest.mark.skip(
            reason="BASE_URL absent : suite de conformité non jouée"
        )
        for item in items:
            item.add_marker(saute)


def _attendre(url: str, essais: int = 60) -> None:
    for _ in range(essais):
        try:
            if httpx.get(url, timeout=5).status_code < 500:
                return
        except httpx.HTTPError:
            pass
        time.sleep(2)
    raise RuntimeError(f"{url} injoignable")


@pytest.fixture(scope="session", autouse=True)
def _pret():
    if BASE_URL:
        _attendre(f"{BASE_URL}/api/health")
        if KEYCLOAK_URL:
            _attendre(f"{KEYCLOAK_URL}/realms/{REALM}")


class Jetons:
    """Fabrique de jetons : direct grant (compose) ou fichiers rafraîchis (preview)."""

    def __init__(self):
        self._cache: dict[tuple, tuple[float, str]] = {}

    def _direct_grant(self, utilisateur: str, client: str, portees: str) -> str:
        res = httpx.post(
            f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/token",
            data={
                "grant_type": "password",
                "client_id": client,
                "username": utilisateur,
                "password": MOT_DE_PASSE,
                "scope": f"openid {portees}".strip(),
            },
            timeout=20,
        )
        if res.status_code != 200:
            raise RuntimeError(
                f"jeton refusé pour {utilisateur}@{client} ({portees}) : {res.status_code} {res.text[:200]}"
            )
        return res.json()["access_token"]

    def _fichier(self, utilisateur: str, client: str) -> str:
        chemin = Path(JETONS_DIR) / f"{client}-{utilisateur}.json"
        if not chemin.exists():
            pytest.skip(f"jeton absent : {chemin} (scripts/jeton-preview.py)")
        contenu = json.loads(chemin.read_text())
        charge = json.loads(_b64(contenu["access_token"].split(".")[1]))
        # Un test de conformité dure jusqu'à deux minutes (C-A7) : un jeton qui expirerait en
        # cours de test est rafraîchi d'avance (durée de vie de 5 min sur le realm de preview).
        if charge.get("exp", 0) - time.time() < 180 and contenu.get("refresh_token"):
            res = httpx.post(
                contenu["token_endpoint"],
                data={
                    "grant_type": "refresh_token",
                    "client_id": client,
                    "refresh_token": contenu["refresh_token"],
                },
                timeout=20,
            )
            res.raise_for_status()
            contenu.update(res.json())
            chemin.write_text(json.dumps(contenu))
        return contenu["access_token"]

    def __call__(
        self,
        utilisateur: str = "alice",
        client: str = CLIENT_COMPLET,
        portees: str = PORTEES_COMPLETES,
    ) -> str:
        cle = (utilisateur, client, portees)
        maintenant = time.time()
        if cle in self._cache and self._cache[cle][0] > maintenant + 30:
            return self._cache[cle][1]
        jeton = (
            self._fichier(utilisateur, client)
            if JETONS_DIR
            else self._direct_grant(utilisateur, client, portees)
        )
        exp = json.loads(_b64(jeton.split(".")[1])).get("exp", maintenant + 60)
        self._cache[cle] = (exp, jeton)
        return jeton


def _b64(partie: str) -> bytes:
    import base64

    return base64.urlsafe_b64decode(partie + "=" * (-len(partie) % 4))


@pytest.fixture(scope="session")
def jeton():
    return Jetons()


@pytest.fixture
def api():
    """Client HTTP vers Mes agents, avec `Authorization` posé par appel."""

    class Api:
        def __init__(self):
            self.http = httpx.Client(base_url=BASE_URL, timeout=180)

        def _h(self, token: str, extra: dict | None = None) -> dict:
            return {"Authorization": f"Bearer {token}", **(extra or {})}

        def get(self, chemin, token, **kw):
            return self.http.get(
                chemin, headers=self._h(token, kw.pop("headers", None)), **kw
            )

        def post(self, chemin, token, json=None, **kw):
            return self.http.post(
                chemin, json=json, headers=self._h(token, kw.pop("headers", None)), **kw
            )

        def patch(self, chemin, token, json=None, **kw):
            return self.http.patch(
                chemin, json=json, headers=self._h(token, kw.pop("headers", None)), **kw
            )

        def put(self, chemin, token, json=None, **kw):
            return self.http.put(
                chemin, json=json, headers=self._h(token, kw.pop("headers", None)), **kw
            )

        def delete(self, chemin, token, **kw):
            return self.http.delete(
                chemin, headers=self._h(token, kw.pop("headers", None)), **kw
            )

        def mcp(self, token, method, params=None, id=1, extra=None):
            corps = {"jsonrpc": "2.0", "method": method, "id": id}
            if params is not None:
                corps["params"] = params
            return self.http.post(
                "/mcp",
                json=corps,
                headers=self._h(
                    token,
                    {"Accept": "application/json, text/event-stream", **(extra or {})},
                ),
            )

    a = Api()
    yield a
    a.http.close()


@pytest.fixture
def suffixe():
    """Noms uniques par passe : le dépôt garde les capacités des passes précédentes."""
    return uuid.uuid4().hex[:8]


def fiche(name: str, **kw) -> dict:
    corps = {
        "name": name,
        "kind": "prompt",
        "title": f"Capacité {name}",
        "description": "Reformule le texte fourni en langage clair.",
        "input_schema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
        "definition": {
            "prompt": f"Tu reformules le texte fourni ({name}).",
            "model": "chat",
            "temperature": 0.2,
        },
        "dependencies": [],
        "grounding": "input",
        "visibility": "private",
        "examples": [{"input": {"text": "Exemple"}, "expected": "Exemple reformulé"}],
    }
    corps.update(kw)
    return corps


def fiche_mcp(name: str, **kw) -> dict:
    corps = {
        "name": name,
        "kind": "mcp",
        "title": f"Annuaire des services ({name})",
        "description": (
            "Recherche une fiche dans l'annuaire public des services de l'État "
            "(service-public.fr), par le serveur MCP de l'annuaire : nom du service, adresse "
            "et horaires d'ouverture."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
        "definition": {
            "endpoint": os.environ.get("MCP_FAKE_URL", "http://mcp-fake:8000/mcp"),
            "tool": "rechercher",
            "identity": "user",
        },
        "dependencies": [],
        "grounding": "input",
        "visibility": "ministry",
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
        "examples": [],
    }
    corps.update(kw)
    return corps
