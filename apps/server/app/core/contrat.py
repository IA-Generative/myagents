"""Contrat d'agents MirAI : vocabulaire fermé, erreurs et CORS des routes du contrat.

Référence : docs/contrats/contrat-agents-mirai.md. Les routes concernées sont
`GET /api/v1/agents` et tout `/v1/*` (surface OpenAI-compatible, appelée aussi par le socle).
"""

from __future__ import annotations

import fnmatch
from collections.abc import Callable, Iterable
from typing import Literal, get_args

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# Vocabulaire FERMÉ (contrat §Vocabulaire). Ajouter une valeur = modifier le contrat d'abord.
Input = Literal[
    "text", "selection", "document", "email", "thread", "meeting", "collection", "page"
]
Output = Literal["text", "replacement", "insertion"]
INPUTS: tuple[str, ...] = get_args(Input)
OUTPUTS: tuple[str, ...] = get_args(Output)

_CHEMINS_EXACTS = frozenset({"/api/v1/agents"})
_PREFIXES = ("/v1/",)

_TYPES_OPENAI = {
    401: "authentication_error",
    403: "permission_error",
    429: "rate_limit_error",
}


def est_route_du_contrat(path: str) -> bool:
    return path in _CHEMINS_EXACTS or path.startswith(_PREFIXES)


def origine_autorisee(origin: str | None, motifs: Iterable[str]) -> bool:
    """L'origine du navigateur figure-t-elle dans les motifs autorisés (fnmatch) ?"""
    if not origin:
        return False
    o = origin.strip().rstrip("/").lower()
    return any(
        fnmatch.fnmatchcase(o, m.strip().rstrip("/").lower()) for m in motifs if m
    )


class ContratError(Exception):
    """Refus d'une route du contrat : rendu `{"error": {"code", "message"}}`."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = headers or {}


class OpenAIApiError(Exception):
    """Refus d'une route /v1 : rendu au format d'erreur OpenAI."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = headers or {}

    @property
    def type(self) -> str:
        if self.status_code >= 500:
            return "api_error"
        return _TYPES_OPENAI.get(self.status_code, "invalid_request_error")


class ContratCorsMiddleware:
    """CORS des seules routes du contrat, origines par motifs, sans credentials.

    Répond lui-même au préflight (le CORSMiddleware global répondrait 400 à une origine
    qu'il ne connaît pas) et pose `Cache-Control: no-store` sur toute réponse du contrat.
    """

    def __init__(
        self, app: ASGIApp, motifs: Callable[[], Iterable[str]] | Iterable[str] = ()
    ) -> None:
        self.app = app
        # Lus à chaque requête quand c'est un appelable : la configuration peut changer
        # après la construction de l'application (tests, rechargement).
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
                await Response(status_code=403)(scope, receive, send)
                return
            reponse = Response(status_code=204)
            reponse.headers["Access-Control-Allow-Origin"] = origin or ""
            reponse.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            reponse.headers["Access-Control-Allow-Headers"] = (
                "Authorization, Content-Type"
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
                    h["Access-Control-Expose-Headers"] = "Retry-After"
            await send(message)

        await self.app(scope, receive, send_wrapper)
