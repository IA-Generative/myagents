"""Garde dédiée des veilles : une veille ne cible pas une personne physique.

Règle : le sujet est refusé s'il est reconnu comme le nom propre d'un individu non institutionnel.
Décision lexicale d'abord (lexique institutionnel, formes « Prénom Nom ») ; cas ambigu tranché par
un juge LLM, fail-closed (juge indisponible = refus).
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass

from app.llm.guard.judge import LangChainJudge, LlmJudge, resolve_judge_model

REGLE = (
    "Une veille ne peut pas cibler une personne physique : un sujet reconnu comme le nom propre "
    "d'un individu (hors institution, fonction ou lieu) est refusé à la création et à la "
    "modification. Les noms cités dans un texte officiel restent tels que publiés dans les "
    "sources ; rien n'est extrait ni indexé par personne."
)

JUDGE_SUJET_SYSTEM = """Tu es un juge de conformité RGPD. On te donne le SUJET d'une veille documentaire (quelques mots).
Décide si ce sujet désigne une PERSONNE PHYSIQUE identifiable (un nom d'individu), ce qui est interdit.
Une institution, une fonction, un lieu, un texte de loi, un thème ne sont PAS des personnes physiques.
Réponds UNIQUEMENT par un objet JSON : {"personne": true|false, "reason": "courte justification"}"""

# Mots qui marquent une institution, une fonction ou un lieu : un sujet qui en contient un n'est
# pas un nom d'individu, même capitalisé.
LEXIQUE_INSTITUTIONNEL = {
    "ministere",
    "ministre",
    "prefecture",
    "prefet",
    "prefete",
    "direction",
    "service",
    "conseil",
    "etat",
    "cour",
    "tribunal",
    "commission",
    "agence",
    "office",
    "secretariat",
    "gouvernement",
    "assemblee",
    "senat",
    "mairie",
    "commune",
    "departement",
    "region",
    "code",
    "loi",
    "decret",
    "arrete",
    "circulaire",
    "reforme",
    "projet",
    "plan",
    "programme",
    "titre",
    "sejour",
    "immigration",
    "securite",
    "interieure",
    "police",
    "gendarmerie",
    "douane",
    "justice",
    "sante",
    "education",
    "travail",
    "finances",
    "budget",
    "numerique",
    "donnees",
    "france",
    "europe",
    "union",
    "recours",
    "procedure",
    "dispositif",
    "appel",
    "marche",
    "contrat",
    "general",
    "generale",
    "nationale",
    "national",
    "publique",
    "public",
    "administration",
    "administratif",
    "administrative",
}
_PRENOM_NOM = re.compile(r"^[A-ZÀ-Ý][A-Za-zÀ-ÿ'\-]+(?:\s+[A-ZÀ-Ý][A-Za-zÀ-ÿ'\-]+)+$")


@dataclass(frozen=True)
class VerdictSujet:
    admis: bool
    raison: str


def _normaliser(mot: str) -> str:
    return "".join(
        c
        for c in unicodedata.normalize("NFD", mot.lower())
        if unicodedata.category(c) != "Mn"
    )


def decision_lexicale(sujet: str) -> VerdictSujet | None:
    """Admis, refusé, ou None (ambigu : le juge décide). Règles, dans l'ordre :
    1. premier mot institutionnel ou thématique (ministère, conseil, réforme…) → admis ;
    2. un chiffre (loi 2026, article 12) → admis ;
    3. exactement deux mots en forme « Prénom Nom » (ou NOM en capitales) → refusé ;
    4. deux ou trois mots minuscules dont le dernier est une donnée personnelle → refusé ;
    5. un mot institutionnel ailleurs → admis ;
    6. au moins deux mots capitalisés inconnus → ambigu (juge) ;
    7. sinon admis."""
    mots = [m.strip(",.;:()«»\"'") for m in sujet.split() if m.strip(",.;:()«»\"'")]
    if not mots:
        return VerdictSujet(True, "sujet vide")
    normalises = [_normaliser(m) for m in mots]
    if normalises[0] in LEXIQUE_INSTITUTIONNEL:
        return VerdictSujet(True, "sujet institutionnel ou thématique")
    if any(any(c.isdigit() for c in m) for m in mots):
        return VerdictSujet(True, "sujet daté ou numéroté")
    capitalises = [m for m in mots if m[:1].isupper()]
    if len(mots) == 2 and len(capitalises) == 2 and _PRENOM_NOM.match(" ".join(mots)):
        return VerdictSujet(
            False, "sujet reconnu comme une personne physique (forme Prénom Nom)"
        )
    if (
        len(mots) in (2, 3)
        and not capitalises
        and normalises[-1]
        in {"adresse", "telephone", "domicile", "famille", "casier", "salaire", "sante"}
        and normalises[0] not in LEXIQUE_INSTITUTIONNEL
    ):
        return VerdictSujet(
            False,
            "sujet reconnu comme une personne physique (nom suivi d'une donnée personnelle)",
        )
    if (
        len(mots) >= 3
        and all(m[:1].isupper() for m in mots[:2])
        and _PRENOM_NOM.match(" ".join(mots[:2]))
    ):
        return None  # « Marie-Claire Martin préfète », « Pont Neuf travaux » : le juge décide
    if any(m in LEXIQUE_INSTITUTIONNEL for m in normalises):
        return VerdictSujet(True, "sujet institutionnel ou thématique")
    if len(capitalises) >= 2:
        return None
    return VerdictSujet(True, "sujet thématique")


async def verifier_sujet(
    sujet: str, *, juge: LlmJudge | None = None, model: str | None = None
) -> VerdictSujet:
    lexical = decision_lexicale(sujet)
    if lexical is not None:
        return lexical
    try:
        raw = await (juge or LangChainJudge()).complete(
            system=JUDGE_SUJET_SYSTEM,
            user=f"SUJET : {sujet}",
            model=resolve_judge_model(model),
            temperature=0,
            max_tokens=256,
        )
    except Exception as exc:  # noqa: BLE001 — fail-closed
        return VerdictSujet(
            False, f"juge indisponible (fail-closed) : {type(exc).__name__}"
        )
    try:
        debut, fin = raw.index("{"), raw.rindex("}") + 1
        parsed = json.loads(raw[debut:fin])
    except ValueError, json.JSONDecodeError:
        return VerdictSujet(False, "verdict du juge illisible (fail-closed)")
    if parsed.get("personne") is True:
        return VerdictSujet(
            False,
            f"sujet reconnu comme une personne physique : {parsed.get('reason', '')}",
        )
    return VerdictSujet(True, "sujet admis par le juge")
