"""Génère `docs/contrats/contrat-capacites-mirai.md` (V2) depuis le code : OpenAPI des routes du
contrat, méthodes MCP, méta-outils, portées, erreurs, journal. Un test de non-régression compare
le fichier committé à la génération.

    python -m app.scripts.exporter_contrat          # écrit le fichier
    python -m app.scripts.exporter_contrat --check  # code 1 si le fichier diverge
"""

from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path

CHEMIN_DOC = (
    Path(__file__).resolve().parents[4]
    / "docs"
    / "contrats"
    / "contrat-capacites-mirai.md"
)

ENTETE = """# Contrat de capacités MirAI — version 2

> Document GÉNÉRÉ depuis le code de Mes agents (`python -m app.scripts.exporter_contrat`) ;
> toute modification manuelle est écrasée. Référence : ADR « Mes agents : un catalogue de
> capacités gouvernées, exposé par MCP ». Remplace le contrat d'agents V1 (compatibilité OpenAI
> non conservée).

## Principe

Une **capacité** est un prompt métier, un outil externe (serveur MCP, API HTTP) ou leur
composition. Le fournisseur (Mes agents) la catalogue, la vérifie à la publication (garde), la
sert à ceux qui ont le droit de l'appeler et journalise chaque exécution. Une version publiée est
immuable et hachée ; `tools/list` ne sert jamais le catalogue complet : trois méta-outils et les
capacités épinglées par la personne (au plus `MESAGENTS_EPINGLES_MAX`).

## Conventions communes

- Transport : HTTPS ; MCP en Streamable HTTP sur `POST /mcp` (et `GET /mcp` pour les
  notifications) ; API de cycle de vie en REST JSON sous `/api/v2/`.
- Authentification : `Authorization: Bearer <jeton d'accès Keycloak de la personne>`. Le
  fournisseur vérifie signature (JWKS), émetteur, expiration, `aud` contenant `mesagents`, et lit
  `sub`, `groups` (chemins complets), `azp`, `scope`. Un consommateur n'envoie jamais de droit dans
  le corps ; les champs `published_by`, `published_from`, `hash`, `version` envoyés sont ignorés.
- En-têtes : toutes les réponses des routes du contrat portent `Cache-Control: no-store` et
  `Vary: Origin`. CORS limité aux origines configurées (`CONTRAT_ORIGINES`, motifs), préflight
  `OPTIONS` avec `Access-Control-Allow-Headers: Authorization, Content-Type`, sans
  `Allow-Credentials`.
- Identifiants : `name` est un slug stable `[a-z0-9][a-z0-9._-]{2,63}` ; une version est un entier
  croissant ; `hash` est le `sha256` hexadécimal de la sérialisation canonique (JSON trié, UTF-8,
  sans espaces) de `definition + input_schema + dependencies`.
- Découverte OAuth 2.1 : `GET /.well-known/oauth-protected-resource` (RFC 9728) ; un `401` porte
  `WWW-Authenticate: Bearer resource_metadata="…/.well-known/oauth-protected-resource/mcp"`.
"""


def _tableau(lignes: list[list[str]], entetes: list[str]) -> str:
    sortie = ["| " + " | ".join(entetes) + " |", "|" + "---|" * len(entetes)]
    for ligne in lignes:
        sortie.append(
            "| "
            + " | ".join(c.replace("|", "\\|").replace("\n", " ") for c in ligne)
            + " |"
        )
    return "\n".join(sortie) + "\n"


def _section_portees() -> str:
    from app.core.portees import PORTEE, REFUSEES, Operation

    descriptions = {
        Operation.LISTER: "`tools/list`, `prompts/*`, `GET /api/v2/capabilities`, recherche et description",
        Operation.APPELER_LECTURE: "`tools/call` et `executer_capacite` sur une capacité `readOnlyHint: true`",
        Operation.APPELER_ACTION: "`tools/call` et `executer_capacite` sur une capacité `readOnlyHint: false` (confirmation par la surface)",
        Operation.REDIGER: "créer, modifier, tester, publier en `private` / `community` (lecture seule), retirer ses propres capacités, épingler",
        Operation.REVOIR: "publier en `ministry` ou une capacité non lecture seule, retirer la capacité d'un autre, administration (export, re-vérification, clients suspendus) — avec le rôle `mesagents-reviewer`",
        Operation.DELEGUER: "déclarée, toujours refusée (régime délégué hors V2)",
    }
    lignes = [[f"`{PORTEE[op]}`", descriptions[op]] for op in Operation]
    texte = "## Portées client (claim `scope`)\n\nUne portée dit ce que l'application appelante PEUT demander ; les droits de la personne (visibilité, groupes, rôle) disent ce qu'elle peut obtenir. L'intersection fait foi.\n\n"
    texte += _tableau(lignes, ["Portée", "Ce qu'elle permet"])
    texte += f"\nUn jeton portant {', '.join(f'`{p}`' for p in sorted(REFUSEES))} est refusé (`403 forbidden`). Un client (`azp`) suspendu est refusé sur toutes les routes (`403 forbidden`), jeton valide ou non.\n"
    return texte


def _section_erreurs() -> str:
    from app.core.contrat import CODES_EXECUTION, ERREURS

    lignes = [
        [str(statut), f"`{code}`", message]
        for code, (statut, message) in ERREURS.items()
    ]
    texte = '## Erreurs\n\nREST : `{"error": {"code": "...", "message": "..."[, "details": [...]]}}` ; `message` est affichable tel quel ; `scope_missing` nomme la portée manquante ; `not_found` ne distingue jamais « n\'existe pas » de « pas pour vous ».\n\n'
    texte += _tableau(lignes, ["Statut", "Code", "Message par défaut"])
    texte += (
        "\nMCP : codes JSON-RPC standard pour le protocole ; un refus de garde ou de droit est un RÉSULTAT d'outil `isError: true`, `_meta.error = {code, message}`, mêmes codes, plus "
        + ", ".join(f"`{c}`" for c in CODES_EXECUTION)
        + " à l'exécution.\n"
    )
    return texte


def _section_journal() -> str:
    from app.services.journal import CHAMPS

    return (
        "## Journal\n\nUne ligne JSON par appel (logger `mesagents.journal`, table `runs`), exportable en JSON Lines par `GET /api/v2/capabilities/{id}/runs` (auteur, relecteur) et `GET /api/v2/admin/runs`. Jamais le contenu.\n\nChamps : "
        + ", ".join(f"`{c}`" for c in CHAMPS)
        + ".\n"
    )


def _section_mcp() -> str:
    from app.mcp import meta_outils, server

    texte = (
        "## Serveur MCP (`/mcp`)\n\nVersions de protocole parlées : "
        + ", ".join(f"`{v}`" for v in server.VERSIONS_PROTOCOLE)
        + f" (défaut `{server.VERSION_DEFAUT}`). `Mcp-Session-Id` émis à l'initialisation, serveur sans état. `GET /mcp` (`Accept: text/event-stream`) transporte `notifications/tools/list_changed`.\n\n"
    )
    lignes = []
    for nom, handler in server.METHODES.items():
        doc = inspect.getdoc(handler) or ""
        lignes.append([f"`{nom}`", doc])
    lignes.append(
        [
            "`notifications/initialized`",
            "Notification du client ; réponse `202` sans corps.",
        ]
    )
    texte += _tableau(lignes, ["Méthode", "Effet"])
    texte += "\n### Méta-outils (toujours présents dans `tools/list`)\n\n"
    for outil in meta_outils.DEFINITIONS:
        texte += f"#### `{outil['name']}`\n\n{outil['description']}\n\n```json\n{json.dumps(outil['inputSchema'], ensure_ascii=False, indent=2)}\n```\n\n"
    texte += "### Forme d'un outil servi\n\n`name`, `title`, `description` (préfixée `[bêta] ` pour une version `beta`), `inputSchema` (JSON Schema de la version servie), `annotations` (`readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`), `_meta` (`hash`, `version`, `maturity`, `grounding`). Résultat de `tools/call` : `content[]`, `isError`, `_meta` (`hash`, `version`, `maturity`, `generated` = `grounding: open`, `error` sur refus), `structuredContent` quand il y a lieu.\n"
    return texte


def _section_rest() -> str:
    from app.main import app

    schema = app.openapi()
    texte = "## API REST (`/api/v2`) et métadonnées\n\n"
    lignes = []
    for chemin in sorted(schema.get("paths", {})):
        if not chemin.startswith(("/api/v2/", "/.well-known/")):
            continue
        for methode, op in schema["paths"][chemin].items():
            if methode.upper() not in ("GET", "POST", "PUT", "PATCH", "DELETE"):
                continue
            resume = op.get("summary", "")
            description = (op.get("description") or "").strip().split("\n")[0]
            lignes.append([f"`{methode.upper()} {chemin}`", resume, description])
    texte += _tableau(lignes, ["Route", "Résumé", "Détail"])
    texte += "\n### Corps de création (`POST /api/v2/capabilities`)\n\n"
    corps = schema.get("components", {}).get("schemas", {}).get("CapabilityCreate", {})
    texte += (
        "```json\n"
        + json.dumps(corps, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n```\n"
    )
    return texte


def _section_cycle() -> str:
    return """## Cycle de vie

Brouillon → (test) → publication (`maturity` `alpha` | `beta` | `general`, `visibility`) → version
immuable → retrait. `PATCH` sur une capacité publiée répond `409 immutable_version` ; `POST
…/draft` ouvre un brouillon pendant que la version publiée reste servie ; la publication suivante
crée la version n+1. `publish` applique dans l'ordre : droit de la personne, portée du client,
verdict de garde (`422 guard_rejected` + `details[]`), règle de dépendance (publiée, visible,
version épinglée, maturité au moins égale : `422 dependency_not_allowed`), puis crée la version et
son `hash`. Une capacité `grounding: open` se publie avec au moins trois exemples. La visibilité
`ministry` et toute capacité non lecture seule passent par une revue (`status: submitted` jusqu'à
la publication par un porteur de `mesagents:review` et du rôle `mesagents-reviewer`). `retire`
suspend les dépendants (`status: suspended`) et émet `notifications/tools/list_changed`.

Visibilité : l'auteur voit tout ; les autres voient une capacité servie `ministry` (tout le
ministère) ou `community` (membres du groupe `community_path`) ; `alpha` n'est visible que de
l'auteur et de son groupe ; `beta` est servie marquée.
"""


def generer() -> str:
    parties = [
        ENTETE,
        _section_cycle(),
        _section_portees(),
        _section_rest(),
        _section_mcp(),
        _section_erreurs(),
        _section_journal(),
    ]
    return "\n".join(p.rstrip("\n") + "\n" for p in parties)


def main(argv: list[str]) -> int:
    texte = generer()
    if "--check" in argv:
        actuel = CHEMIN_DOC.read_text(encoding="utf-8") if CHEMIN_DOC.exists() else ""
        if actuel != texte:
            print(f"{CHEMIN_DOC} diverge de la génération", file=sys.stderr)
            return 1
        print("contrat conforme à la génération")
        return 0
    CHEMIN_DOC.parent.mkdir(parents=True, exist_ok=True)
    CHEMIN_DOC.write_text(texte, encoding="utf-8")
    print(f"écrit : {CHEMIN_DOC}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
