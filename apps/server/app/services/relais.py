"""Relais d'une capacité `kind: mcp|http` vers son point d'accès (ADR §4.4, §10.1 point 5).

- `mcp` : JSON-RPC 2.0 en Streamable HTTP : `initialize` (session), `notifications/initialized`,
  `tools/call`, puis `DELETE` de la session (best-effort) ; réponse JSON ou SSE (un événement) ;
- `http` : la requête déclarée, arguments en corps JSON (ou en paramètres pour GET).
Identité : `user` = le jeton reçu, relayé tel quel ; `service` = un jeton d'environnement
(`MESAGENTS_JETON_SERVICE_<REF>`), jamais en base. Garde SSRF : hôte dans la liste d'autorisation,
sinon https obligatoire et jamais une adresse privée.
"""

from __future__ import annotations

import fnmatch
import ipaddress
import json
import os
import uuid
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

from app.core.config import get_settings

# Posé par les tests (httpx.MockTransport) ; None en production.
_transport_pour_tests: httpx.AsyncBaseTransport | None = None

_ENTETES_INTERDITS = ("authorization", "cookie", "x-api-key", "proxy-authorization")
_HOTES_LOCAUX = ("localhost",)


class RelaisError(RuntimeError):
    """Le point d'accès n'a pas répondu, ou a répondu hors protocole."""


@dataclass
class ResultatRelais:
    texte: str
    is_error: bool = False


def hote_autorise(url: str) -> bool:
    parts = urlsplit(url)
    hote = (parts.hostname or "").lower()
    if not hote or parts.scheme not in ("http", "https"):
        return False
    motifs = get_settings().mesagents_relais_hotes_autorises
    if any(fnmatch.fnmatchcase(hote, m.lower()) for m in motifs if m):
        return True
    if parts.scheme != "https":
        return False
    if hote in _HOTES_LOCAUX or hote.endswith(
        (".local", ".svc", ".svc.cluster.local", ".internal")
    ):
        return False
    try:
        adresse = ipaddress.ip_address(hote)
    except ValueError:
        return True
    return not (
        adresse.is_private
        or adresse.is_loopback
        or adresse.is_link_local
        or adresse.is_reserved
    )


def jeton_de_service(ref: str) -> str | None:
    if not ref:
        return None
    nom = "MESAGENTS_JETON_SERVICE_" + "".join(
        c if c.isalnum() else "_" for c in ref.upper()
    )
    return os.environ.get(nom) or None


def autorisation_pour(definition: dict, jeton_personne: str | None) -> str | None:
    """L'en-tête Authorization à relayer selon l'identité déclarée par la capacité."""
    if definition.get("identity", "user") == "service":
        jeton = jeton_de_service(str(definition.get("service_token_ref") or ""))
        return f"Bearer {jeton}" if jeton else None
    return f"Bearer {jeton_personne}" if jeton_personne else None


def _entetes_declares(definition: dict) -> dict[str, str]:
    return {
        str(k): str(v)
        for k, v in (definition.get("headers") or {}).items()
        if str(k).lower() not in _ENTETES_INTERDITS
    }


def _client(url: str) -> httpx.AsyncClient:
    settings = get_settings()
    hote = (urlsplit(url).hostname or "").lower()
    interne = any(
        fnmatch.fnmatchcase(hote, m.lower())
        for m in settings.mesagents_relais_hotes_autorises
        if m
    )
    return httpx.AsyncClient(
        transport=_transport_pour_tests,
        timeout=settings.mesagents_relais_timeout,
        trust_env=not interne,
        follow_redirects=False,
    )


def _lire_reponse_jsonrpc(reponse: httpx.Response) -> dict:
    """Une réponse JSON, ou un flux SSE dont on prend le premier événement JSON-RPC complet."""
    type_contenu = reponse.headers.get("content-type", "")
    if type_contenu.startswith("text/event-stream"):
        for ligne in reponse.text.splitlines():
            if ligne.startswith("data:"):
                try:
                    return json.loads(ligne[5:].strip())
                except json.JSONDecodeError:
                    continue
        raise RelaisError("flux SSE sans message JSON-RPC")
    try:
        return reponse.json()
    except ValueError as exc:
        raise RelaisError("réponse non JSON du point d'accès MCP") from exc


def _texte_du_resultat(resultat: dict) -> str:
    morceaux = []
    for bloc in resultat.get("content") or []:
        if isinstance(bloc, dict) and bloc.get("type") == "text":
            morceaux.append(str(bloc.get("text", "")))
        elif isinstance(bloc, dict):
            morceaux.append(json.dumps(bloc, ensure_ascii=False))
    if not morceaux and "structuredContent" in resultat:
        morceaux.append(json.dumps(resultat["structuredContent"], ensure_ascii=False))
    return "\n".join(morceaux)


async def relayer_mcp(
    endpoint: str,
    tool: str,
    arguments: dict,
    *,
    autorisation: str | None,
    entetes: dict[str, str] | None = None,
) -> ResultatRelais:
    if not hote_autorise(endpoint):
        raise RelaisError("point d'accès MCP hors de la liste d'autorisation")
    base = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        **(entetes or {}),
    }
    if autorisation:
        base["Authorization"] = autorisation
    async with _client(endpoint) as client:
        try:
            init = await client.post(
                endpoint,
                headers=base,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {"name": "mes-agents", "version": "2"},
                    },
                },
            )
        except httpx.HTTPError as exc:
            raise RelaisError(f"initialize : {type(exc).__name__}") from exc
        if init.status_code >= 400:
            raise RelaisError(f"initialize : HTTP {init.status_code}")
        session = init.headers.get("mcp-session-id")
        suite = dict(base)
        if session:
            suite["Mcp-Session-Id"] = session
        try:
            await client.post(
                endpoint,
                headers=suite,
                json={"jsonrpc": "2.0", "method": "notifications/initialized"},
            )
        except httpx.HTTPError:
            pass
        try:
            reponse = await client.post(
                endpoint,
                headers=suite,
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": tool, "arguments": arguments},
                },
            )
        except httpx.HTTPError as exc:
            raise RelaisError(f"tools/call : {type(exc).__name__}") from exc
        if reponse.status_code >= 400:
            raise RelaisError(f"tools/call : HTTP {reponse.status_code}")
        message = _lire_reponse_jsonrpc(reponse)
        if session:
            try:
                await client.delete(endpoint, headers=suite)
            except httpx.HTTPError:
                pass
    if "error" in message:
        erreur = message["error"] or {}
        raise RelaisError(
            f"erreur JSON-RPC {erreur.get('code')} : {str(erreur.get('message', ''))[:200]}"
        )
    resultat = message.get("result") or {}
    return ResultatRelais(
        texte=_texte_du_resultat(resultat), is_error=bool(resultat.get("isError"))
    )


async def relayer_http(
    definition: dict, arguments: dict, *, autorisation: str | None
) -> ResultatRelais:
    url = str(definition.get("url", ""))
    if not hote_autorise(url):
        raise RelaisError("point d'accès HTTP hors de la liste d'autorisation")
    methode = str(definition.get("method", "POST")).upper()
    entetes = {
        "Accept": "application/json, text/plain",
        **_entetes_declares(definition),
    }
    if autorisation:
        entetes["Authorization"] = autorisation
    async with _client(url) as client:
        try:
            if methode == "GET":
                reponse = await client.get(
                    url,
                    headers=entetes,
                    params={k: str(v) for k, v in arguments.items()},
                )
            else:
                reponse = await client.request(
                    methode,
                    url,
                    headers={**entetes, "Content-Type": "application/json"},
                    json=arguments,
                )
        except httpx.HTTPError as exc:
            raise RelaisError(f"{methode} : {type(exc).__name__}") from exc
    if reponse.status_code >= 400:
        raise RelaisError(f"{methode} : HTTP {reponse.status_code}")
    return ResultatRelais(texte=reponse.text, is_error=False)


def identifiant_appel() -> str:
    return uuid.uuid4().hex
