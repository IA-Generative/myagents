"""`web.collecter` : collecte bornée sur une liste d'autorisation de domaines (chantier 3).

- domaine dans `VEILLE_DOMAINES_AUTORISES` (motifs d'hôte), https obligatoire, pas d'identifiant ;
- `robots.txt` respecté, en-têtes de cache honorés (ETag / If-None-Match) ;
- jamais le texte intégral : titre, URL, date, auteur s'il est fourni, extrait ≤ 300 caractères ;
- pas de rendu JavaScript, pas de contournement de paywall ;
- `User-Agent` explicite nommant le ministère et un contact ;
- hors sources officielles, aucun champ reconnu nominatif n'est conservé.
Toute URL consultée est consignée dans `urls_consultees` (métadonnées, pas le contenu).
"""

from __future__ import annotations

import contextvars
import fnmatch
import html
import re
import unicodedata
from dataclasses import dataclass
from typing import ClassVar
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from app.core.config import get_settings

_transport_pour_tests: httpx.AsyncBaseTransport | None = None
MAX_EXTRAIT = 300
MAX_PAGES = 5
_SOURCES_OFFICIELLES = (
    "legifrance.gouv.fr",
    "journal-officiel.gouv.fr",
    "senat.fr",
    "assemblee-nationale.fr",
    "conseil-etat.fr",
    "courdecassation.fr",
)

# Les URL consultées pendant une exécution de veille (métadonnées).
urls_consultees: contextvars.ContextVar[list[str] | None] = contextvars.ContextVar(
    "urls_consultees", default=None
)
fiches_collectees: contextvars.ContextVar[list[dict] | None] = contextvars.ContextVar(
    "fiches_collectees", default=None
)


class CollecteRefusee(RuntimeError):
    pass


def user_agent() -> str:
    # ASCII seulement : un en-tête HTTP n'admet pas d'accent.
    return f"MirAI-veille/1.0 (ministere de l'Interieur ; contact: {get_settings().veille_contact})"


def domaine_autorise(url: str) -> bool:
    parts = urlsplit(url)
    hote = (parts.hostname or "").lower()
    if (
        parts.scheme not in get_settings().veille_schemas_autorises
        or not hote
        or parts.username
        or parts.password
    ):
        return False
    motifs = [m.lower() for m in get_settings().veille_domaines_autorises if m]
    return any(
        hote == m
        or fnmatch.fnmatchcase(hote, m)
        or (m.startswith("*.") and hote == m[2:])
        for m in motifs
    )


def est_source_officielle(url: str) -> bool:
    hote = (urlsplit(url).hostname or "").lower()
    return any(hote == s or hote.endswith("." + s) for s in _SOURCES_OFFICIELLES)


_BALISES_MUETTES = re.compile(
    r"<(script|style|nav|header|footer|aside|noscript)\b.*?</\1>",
    re.IGNORECASE | re.DOTALL,
)
_TITRE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_HEAD = re.compile(r"<head\b.*?</head>", re.IGNORECASE | re.DOTALL)
_META = re.compile(
    r"<meta\s+[^>]*?(?:name|property)=[\"']([^\"']+)[\"'][^>]*?content=[\"']([^\"']*)[\"'][^>]*>",
    re.IGNORECASE,
)
_ARTICLE = re.compile(r"<(article|main)\b[^>]*>(.*?)</\1>", re.IGNORECASE | re.DOTALL)
_BALISE = re.compile(r"<[^>]+>")
_COURRIEL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_TELEPHONE = re.compile(r"(?:\+33|0)\s?[1-9](?:[\s.-]?\d{2}){4}")
_LIEN = re.compile(
    r"<a\s+[^>]*href=[\"']([^\"'#]+)[\"'][^>]*>(.*?)</a>", re.IGNORECASE | re.DOTALL
)


def _texte(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(_BALISE.sub(" ", fragment))).strip()


def _sans_nominatif(texte: str) -> str:
    return _TELEPHONE.sub("", _COURRIEL.sub("", texte)).strip()


def extraire(page: str, url: str, *, officielle: bool | None = None) -> dict:
    """Titre, URL, date, auteur (si fourni) et extrait court ; jamais plus."""
    if officielle is None:
        officielle = est_source_officielle(url)
    metas = {k.lower(): html.unescape(v) for k, v in _META.findall(page)}
    titre = _texte(_TITRE.search(page).group(1)) if _TITRE.search(page) else ""
    date = (
        metas.get("article:published_time")
        or metas.get("date")
        or metas.get("dc.date")
        or ""
    )
    auteur = metas.get("author") or metas.get("dc.creator") or ""
    corps = _BALISES_MUETTES.sub(" ", _HEAD.sub(" ", page))
    article = _ARTICLE.search(corps)
    texte = _texte(article.group(2) if article else corps)
    if not officielle:
        texte = _sans_nominatif(texte)
        auteur = (
            "" if (_COURRIEL.search(auteur) or _TELEPHONE.search(auteur)) else auteur
        )
    extrait = texte[:MAX_EXTRAIT].rstrip()
    return {
        "title": titre,
        "url": url,
        "date": date,
        "author": auteur,
        "extrait": extrait,
    }


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=_transport_pour_tests,
        timeout=20,
        follow_redirects=False,
        headers={"User-Agent": user_agent(), "Accept": "text/html"},
    )


def _noter(url: str) -> None:
    liste = urls_consultees.get()
    if liste is not None and url not in liste:
        liste.append(url)


async def robots_permet(client: httpx.AsyncClient, url: str) -> bool:
    parts = urlsplit(url)
    adresse = f"{parts.scheme}://{parts.netloc}/robots.txt"
    rp = RobotFileParser()
    try:
        rep = await client.get(adresse)
    except httpx.HTTPError:
        return True
    if rep.status_code >= 400:
        return True
    rp.parse(rep.text.splitlines())
    return rp.can_fetch(user_agent(), url)


async def collecter_page(url: str, *, etag: str | None = None) -> dict | None:
    """Une page : liste d'autorisation, robots.txt, cache, extraction bornée. None si rien de nouveau."""
    if not domaine_autorise(url):
        raise CollecteRefusee(f"domaine non autorisé : {urlsplit(url).hostname}")
    async with _client() as client:
        if not await robots_permet(client, url):
            raise CollecteRefusee(f"robots.txt refuse : {url}")
        entetes = {"If-None-Match": etag} if etag else {}
        _noter(url)
        try:
            rep = await client.get(url, headers=entetes)
        except httpx.HTTPError as exc:
            raise CollecteRefusee(f"{url} : {type(exc).__name__}") from exc
    if rep.status_code == 304:
        return None
    if rep.status_code >= 400 or not rep.headers.get(
        "content-type", "text/html"
    ).startswith("text/html"):
        raise CollecteRefusee(f"{url} : HTTP {rep.status_code}")
    fiche = extraire(rep.text, url)
    if rep.headers.get("etag"):
        fiche["etag"] = rep.headers["etag"]
    return fiche


_MOTS_VIDES = frozenset(
    [
        "des",
        "les",
        "une",
        "uns",
        "unes",
        "pour",
        "dans",
        "sur",
        "par",
        "avec",
        "aux",
        "est",
        "sont",
        "ses",
        "son",
        "leur",
        "leurs",
        "ces",
        "cet",
        "cette",
        "qui",
        "que",
        "quoi",
        "dont",
        "nos",
        "vos",
        "mes",
        "entre",
        "vers",
        "chez",
        "sans",
        "sous",
        "apres",
        "avant",
        "comme",
        "plus",
        "moins",
        "tout",
        "tous",
        "toute",
        "toutes",
        "etc",
    ]
)


def _plat(texte: str) -> str:
    """Minuscules sans accents : « Cybersécurité » et « cybersecurite » se valent."""
    return (
        unicodedata.normalize("NFKD", texte or "")
        .encode("ascii", "ignore")
        .decode()
        .lower()
    )


def _mots(requete: str) -> list[str]:
    """Mots porteurs de la requête (sans accents, sans mots vides) : « des » ne retient rien."""
    return [m for m in re.findall(r"\w{3,}", _plat(requete)) if m not in _MOTS_VIDES]


def _en_rapport(mots: list[str], *textes: str | None) -> bool:
    """Un texte est en rapport s'il porte la racine (5 premières lettres) d'un mot de la requête :
    « cybersécurité » retient « Cybermois », « collectivités » retient « collectivité »."""
    if not mots:
        return True
    plat = _plat(" ".join(t or "" for t in textes))
    return any(m[:5] in plat for m in mots)


async def collecter(
    requete: str, *, seeds: list[str] | None = None, max_pages: int = MAX_PAGES
) -> list[dict]:
    """Depuis les pages de départ (listes d'actualités autorisées), suit les liens du même domaine
    dont le libellé ou l'adresse porte un mot de la requête, et en collecte au plus `max_pages`."""
    mots = _mots(requete)
    fiches: list[dict] = []
    departs = [u for u in (seeds or get_settings().veille_seeds) if domaine_autorise(u)]
    for i, seed in enumerate(departs):
        if len(fiches) >= max_pages:
            break
        # Le budget restant se répartit entre les pages de départ qui restent à lire : une
        # première liste prolixe ne prend pas toute la place des suivantes.
        quota = -(-(max_pages - len(fiches)) // (len(departs) - i))
        pris = 0
        async with _client() as client:
            if not await robots_permet(client, seed):
                continue
            _noter(seed)
            try:
                rep = await client.get(seed)
            except httpx.HTTPError:
                continue
        if rep.status_code >= 400:
            continue
        for href, libelle in _LIEN.findall(rep.text):
            if pris >= quota or len(fiches) >= max_pages:
                break
            cible = urljoin(seed, html.unescape(href))
            if (
                not domaine_autorise(cible)
                or urlsplit(cible).netloc != urlsplit(seed).netloc
                or cible == seed
            ):
                continue
            if not _en_rapport(mots, _texte(libelle), cible):
                continue
            try:
                fiche = await collecter_page(cible)
            except CollecteRefusee:
                continue
            # Le lien promettait le sujet ; la page doit le porter aussi, sinon elle est écartée.
            if fiche and _en_rapport(mots, fiche.get("title"), fiche.get("extrait")):
                fiche.pop("etag", None)
                fiches.append(fiche)
                pris += 1
    memo = fiches_collectees.get()
    if memo is not None:
        memo.extend(fiches)
    return fiches


@dataclass(frozen=True)
class Definition:
    """La capacité `web.collecter` telle que semée (kind http interne)."""

    name = "web.collecter"
    title = "Collecter sur les sites autorisés"
    description = (
        "Collecte, sur les sites institutionnels autorisés, les pages récentes en rapport avec la "
        "requête : titre, lien, date, auteur s'il est fourni et un extrait court. Respecte robots.txt ; "
        "ne conserve jamais le texte intégral."
    )
    input_schema: ClassVar[dict] = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Le sujet à collecter",
                "maxLength": 200,
            },
            "urls": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Pages de départ (facultatif)",
            },
        },
        "required": ["query"],
    }
    annotations: ClassVar[dict] = {
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }


async def outil_collecter(arguments: dict) -> str:
    """Point d'entrée interne de la capacité (relais `interne:web.collecter`)."""
    import json

    seeds = [u for u in (arguments.get("urls") or []) if isinstance(u, str)] or None
    fiches = await collecter(str(arguments.get("query", "")), seeds=seeds)
    return json.dumps({"items": fiches, "count": len(fiches)}, ensure_ascii=False)
