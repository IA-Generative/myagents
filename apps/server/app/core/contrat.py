"""Erreurs et CORS des routes du contrat de capacités (ADR §10.0 « Conventions communes »).

Les routes concernées : `/api/v2/*`, `/mcp*`, `/.well-known/oauth-protected-resource*`. Toute
réponse porte `Cache-Control: no-store` et `Vary: Origin` ; le CORS n'admet que les origines
configurées (`CONTRAT_ORIGINES`, motifs fnmatch), sans credentials ; le préflight annonce
`Authorization, Content-Type`.
"""

from __future__ import annotations

import fnmatch
from collections.abc import Callable, Iterable

from fastapi.responses import JSONResponse
from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_PREFIXES = ("/api/v2/", "/mcp", "/.well-known/oauth-protected-resource")

# code → (statut HTTP, message affichable par défaut). Le message est affichable tel quel.
ERREURS: dict[str, tuple[int, str]] = {
    "invalid_request": (400, "Requête invalide."),
    "invalid_token": (401, "Jeton absent ou invalide."),
    "audience_mismatch": (403, "Ce jeton n'est pas destiné à Mes agents."),
    "scope_missing": (403, "Portée manquante."),
    "forbidden": (403, "Accès refusé."),
    "not_found": (404, "Capacité introuvable."),
    "immutable_version": (
        409,
        "Une version publiée ne se modifie pas : ouvrez un brouillon.",
    ),
    "guard_rejected": (422, "La garde a refusé la définition."),
    "dependency_not_allowed": (422, "Une dépendance déclarée n'est pas admise."),
    "rate_limited": (429, "Trop d'appels : réessayez plus tard."),
    "upstream_unavailable": (502, "La capacité ne répond pas."),
}

# Codes rendus dans un résultat d'outil MCP (isError) sans statut HTTP propre.
CODES_EXECUTION: tuple[str, ...] = ("blocked_input", "blocked_output")


def est_route_du_contrat(path: str) -> bool:
    return path == "/api/v2" or path.startswith(_PREFIXES)


def origine_autorisee(origin: str | None, motifs: Iterable[str]) -> bool:
    """L'origine du navigateur figure-t-elle dans les motifs autorisés (fnmatch) ?"""
    if not origin:
        return False
    o = origin.strip().rstrip("/").lower()
    return any(
        fnmatch.fnmatchcase(o, m.strip().rstrip("/").lower()) for m in motifs if m
    )


class ContratError(Exception):
    """Refus d'une route du contrat : rendu `{"error": {"code", "message"[, "details"]}}`."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str | None = None,
        *,
        details: list[str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        texte = message or ERREURS.get(code, (status_code, "Erreur."))[1]
        super().__init__(texte)
        self.status_code = status_code
        self.code = code
        self.message = texte
        self.details = details
        self.headers = headers or {}

    @classmethod
    def de(cls, code: str, message: str | None = None, **kw) -> ContratError:
        statut = ERREURS[code][0]
        return cls(statut, code, message, **kw)

    def corps(self) -> dict:
        erreur: dict = {"code": self.code, "message": self.message}
        if self.details is not None:
            erreur["details"] = self.details
        return {"error": erreur}

    def reponse(self) -> JSONResponse:
        return JSONResponse(
            status_code=self.status_code, content=self.corps(), headers=self.headers
        )


class CapacitesCorsMiddleware:
    """CORS des seules routes du contrat, origines par motifs, sans credentials.

    Répond lui-même au préflight (le CORSMiddleware global répondrait 400 à une origine qu'il
    ne connaît pas) et pose `Cache-Control: no-store` + `Vary: Origin` sur toute réponse.
    """

    def __init__(
        self, app: ASGIApp, motifs: Callable[[], Iterable[str]] | Iterable[str] = ()
    ) -> None:
        self.app = app
        # Appelable : lu à chaque requête (la configuration peut changer après la construction).
        self._motifs = motifs

    @property
    def motifs(self) -> list[str]:
        valeurs = self._motifs() if callable(self._motifs) else self._motifs
        return [m for m in valeurs if m]

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not est_route_du_contrat(scope["path"]):
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        origin = headers.get("origin")
        autorisee = origine_autorisee(origin, self.motifs)

        if scope["method"] == "OPTIONS" and headers.get(
            "access-control-request-method"
        ):
            if not autorisee:
                reponse = Response(status_code=403)
                reponse.headers["Cache-Control"] = "no-store"
                reponse.headers["Vary"] = "Origin"
                await reponse(scope, receive, send)
                return
            reponse = Response(status_code=204)
            reponse.headers["Access-Control-Allow-Origin"] = origin or ""
            reponse.headers["Access-Control-Allow-Methods"] = (
                "GET, POST, PATCH, PUT, DELETE, OPTIONS"
            )
            reponse.headers["Access-Control-Allow-Headers"] = (
                "Authorization, Content-Type, Accept, Mcp-Session-Id, MCP-Protocol-Version"
            )
            reponse.headers["Access-Control-Max-Age"] = "600"
            reponse.headers["Vary"] = "Origin"
            reponse.headers["Cache-Control"] = "no-store"
            await reponse(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                h = MutableHeaders(scope=message)
                h["Cache-Control"] = "no-store"
                h.append("Vary", "Origin")
                if autorisee and origin:
                    h["Access-Control-Allow-Origin"] = origin
                    h["Access-Control-Expose-Headers"] = (
                        "Retry-After, Mcp-Session-Id, WWW-Authenticate"
                    )
            await send(message)

        await self.app(scope, receive, send_wrapper)
