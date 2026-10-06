"""Les fiches des agents dans le socle (Open WebUI) : ce que Mon assistant montre, et à qui.

Le socle découvre les agents par sa connexion OpenAI vers `/v1` de Mes agents. Avec le
contrôle d'accès par modèle (`BYPASS_MODEL_ACCESS_CONTROL=false`), un modèle sans fiche est
invisible des testeurs : c'est donc Mes agents qui pose la fiche à la publication, avec les
droits de l'agent — ministère : tout compte connecté ; communauté : le groupe du socle qui
porte le nom de la communauté (les groupes du socle sont synchronisés depuis le SSO par leur
nom feuille). Un agent privé, brouillon ou archivé n'a pas de fiche.

Même patron et mêmes pièges que Mes collections (`myrag/app/services/fiche_assistant.py`) :
- OWUI ≥ 0.11 : `access_grants` toujours une LISTE (`null` fait répondre 500 sans un mot) ;
  `user/*` = tout compte connecté, jamais `anyone/*` (sans authentification) ;
- `base_model_id` ABSENT = la fiche recouvre le modèle de connexion du même identifiant ;
  y mettre l'identifiant lui-même ferait disparaître l'agent du sélecteur, sans erreur ;
- l'identifiant est passé en paramètre de requête ET dans le corps de la mise à jour.

La synchronisation ne bloque jamais une publication : elle rend un état que la route renvoie
au client (`socle`), et journalise sans jamais écrire le prompt de l'agent.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

import httpx

from app.core.config import get_settings
from app.models.agent import Agent
from app.models.enums import AgentStatus, Visibility
from app.schemas.agent import ConfigSnapshot
from app.services import agents as agents_service

logger = logging.getLogger(__name__)

TAG = "Mes agents"
_META_GEREE = ("description", "suggestion_prompts", "tags", "capabilities")
_STATUTS_PUBLIES = (AgentStatus.published, AgentStatus.submitted)

# États rendus par `synchroniser` (contrat d'agents, docs/contrats/contrat-agents-mirai.md).
POSEE = "posee"
RETIREE = "retiree"
INDISPONIBLE = "indisponible"


class SocleIndisponible(RuntimeError):
    """Le socle n'est pas configuré (OWUI_BASE_URL ou OWUI_ADMIN_API_KEY absent)."""


def doit_avoir_une_fiche(agent: Agent) -> bool:
    return agent.status in _STATUTS_PUBLIES and agent.visibility != Visibility.private


def grants(visibility: Visibility, group_ids: Iterable[str] = ()) -> list[dict]:
    """Les autorisations de lecture d'une fiche, au format OWUI ≥ 0.11."""
    if visibility == Visibility.ministry:
        return [{"principal_type": "user", "principal_id": "*", "permission": "read"}]
    if visibility == Visibility.community:
        return [
            {"principal_type": "group", "principal_id": g, "permission": "read"}
            for g in group_ids
        ]
    return []


def nom_feuille(community_path: str | None) -> str:
    return (community_path or "").strip().strip("/").rsplit("/", 1)[-1].strip()


def fiche_voulue(
    agent: Agent, config: ConfigSnapshot, group_ids: Iterable[str] = ()
) -> dict:
    """La fiche telle que Mes agents la veut. Fonction pure."""
    group_ids = list(group_ids)
    ac = None
    if agent.visibility == Visibility.community and group_ids:
        ac = {
            "read": {"group_ids": group_ids, "user_ids": []},
            "write": {"group_ids": [], "user_ids": []},
        }
    etiquettes = [*agent.category, TAG]
    return {
        "id": str(agent.id),
        "name": config.name or "Agent sans nom",
        "meta": {
            "description": config.description
            or f"Agent « {config.name} » de Mes agents",
            "profile_image_url": "/static/favicon.png",
            "suggestion_prompts": [{"content": e} for e in config.examples],
            "tags": [{"name": t} for t in dict.fromkeys(etiquettes) if t],
            # Le prompt système et les outils sont appliqués par Mes agents sur /v1 :
            # la fiche ne porte ni `params.system`, ni capacités que le socle ne sert pas.
            "capabilities": {"vision": False, "usage": False, "citations": False},
        },
        "params": {},
        "base_model_id": None,
        "access_control": ac,
        "access_grants": grants(agent.visibility, group_ids),
        "is_active": True,
    }


def fusionner(existante: dict | None, voulue: dict) -> dict:
    """La fiche voulue, sans effacer ce que Mes agents ne gère pas sur une fiche existante
    (paramètres réglés dans le socle, image, étiquettes posées ailleurs)."""
    fiche = {
        **voulue,
        "meta": dict(voulue.get("meta") or {}),
        "params": dict(voulue.get("params") or {}),
    }
    if not existante:
        return fiche
    meta_avant = existante.get("meta") or {}
    fiche["params"] = dict(existante.get("params") or {})
    meta = {k: v for k, v in meta_avant.items() if k not in _META_GEREE}
    meta.update(fiche["meta"])
    if meta_avant.get("profile_image_url"):
        meta["profile_image_url"] = meta_avant["profile_image_url"]
    nos_noms = {t.get("name") for t in fiche["meta"].get("tags") or []}
    autres = [
        t
        for t in meta_avant.get("tags") or []
        if isinstance(t, dict) and t.get("name") and t.get("name") not in nos_noms
    ]
    meta["tags"] = autres + list(fiche["meta"].get("tags") or [])
    fiche["meta"] = meta
    return fiche


class SocleClient:
    """Client d'administration du socle, à clé partagée (OWUI_ADMIN_API_KEY)."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.owui_base_url).rstrip("/")
        self.api_key = api_key or settings.owui_admin_api_key
        if not self.base_url or not self.api_key:
            raise SocleIndisponible("OWUI_BASE_URL ou OWUI_ADMIN_API_KEY absent")
        self.timeout = timeout or settings.owui_timeout
        self._transport = transport

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            transport=self._transport,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

    async def ids_de_groupes(self, noms: Iterable[str]) -> tuple[list[str], list[str]]:
        """Identifiants des groupes du socle portant ces noms (feuilles), et les noms
        restés sans groupe. Le socle désigne un groupe par un identifiant interne."""
        async with self._client() as c:
            res = await c.get("/api/v1/groups/")
        res.raise_for_status()
        par_nom = {
            str(g.get("name", "")).strip().lower(): str(g.get("id"))
            for g in (res.json() or [])
            if isinstance(g, dict)
        }
        ids, inconnus = [], []
        for brut in noms:
            cle = nom_feuille(brut).lower()
            if not cle:
                continue
            if cle in par_nom:
                ids.append(par_nom[cle])
            else:
                inconnus.append(brut)
        return ids, inconnus

    async def fiche_existante(self, model_id: str) -> dict | None:
        async with self._client() as c:
            res = await c.get("/api/v1/models/model", params={"id": model_id})
        # Une fiche ABSENTE répond 401, 403 ou 404 selon la version du socle.
        if res.status_code in (401, 403, 404):
            return None
        res.raise_for_status()
        return res.json() or None

    async def poser(self, body: dict) -> dict:
        """Mise à jour d'abord, création sinon. Idempotent sur le même identifiant."""
        async with self._client() as c:
            upd = await c.post(
                "/api/v1/models/model/update", params={"id": body["id"]}, json=body
            )
            if upd.is_success:
                return upd.json()
            cre = await c.post("/api/v1/models/create", json=body)
            if cre.status_code in (401, 403):
                raise PermissionError(
                    f"clé d'administration refusée ({cre.status_code})"
                )
            if not cre.is_success:
                raise RuntimeError(
                    f"fiche refusée : update {upd.status_code}, create {cre.status_code}"
                )
            return cre.json()

    async def retirer(self, model_id: str) -> None:
        async with self._client() as c:
            for method, path, json_body in (
                ("POST", "/api/v1/models/model/delete", {"id": model_id}),
                ("DELETE", f"/api/v1/models/{model_id}", None),
            ):
                res = await c.request(
                    method, path, params={"id": model_id}, json=json_body
                )
                if res.status_code == 401:
                    raise PermissionError("clé d'administration refusée")
                if res.is_success or res.status_code == 404:
                    return


def _nouveau_client() -> SocleClient:
    return SocleClient()


async def synchroniser(agent: Agent, client: SocleClient | None = None) -> str:
    """Pose, repose ou retire la fiche de l'agent selon son statut et sa visibilité.

    Rend un état lisible, jamais une exception : `posee`, `retiree`, `indisponible`,
    `groupe_inconnu:<nom>` ou `erreur:<type>`. Une publication n'échoue pas parce que le
    socle est muet ; le journal garde la cause.
    """
    try:
        client = client or _nouveau_client()
    except SocleIndisponible:
        return INDISPONIBLE
    try:
        if not doit_avoir_une_fiche(agent):
            await client.retirer(str(agent.id))
            return RETIREE
        config = agents_service.current_config(agent)
        group_ids: list[str] = []
        if agent.visibility == Visibility.community:
            group_ids, inconnus = await client.ids_de_groupes(
                [config.community_path or ""]
            )
            if inconnus or not group_ids:
                logger.warning(
                    "fiche non posée (%s) : groupe inconnu du socle", agent.id
                )
                await client.retirer(str(agent.id))
                return f"groupe_inconnu:{nom_feuille(config.community_path)}"
        existante = await client.fiche_existante(str(agent.id))
        await client.poser(fusionner(existante, fiche_voulue(agent, config, group_ids)))
        return POSEE
    except Exception as exc:  # noqa: BLE001 — l'état dit tout, la route continue
        logger.error(
            "socle : fiche %s non synchronisée (%s)", agent.id, type(exc).__name__
        )
        return f"erreur:{type(exc).__name__}"
