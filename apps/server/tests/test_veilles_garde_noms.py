"""Garde dédiée des veilles : une veille ne cible pas une personne physique (mot-clé bloqué si
c'est un nom propre d'individu non institutionnel). Règle lexicale documentée + juge LLM."""

import pytest

from app.llm.guard.core import Verdict
from app.veilles import garde_noms
from app.veilles.garde_noms import verifier_sujet


class _Juge:
    def __init__(self, reponse):
        self.reponse = reponse
        self.appels = []

    async def complete(self, *, system, user, model, temperature, max_tokens):
        self.appels.append(user)
        return self.reponse


@pytest.mark.parametrize(
    "sujet",
    [
        "réforme du code de la sécurité intérieure",
        "Ministère de l'Intérieur",
        "Conseil d'État recours gracieux",
        "Préfecture de la Seine-Saint-Denis titres de séjour",
        "loi immigration 2026",
        "Direction générale des étrangers en France",
    ],
)
async def test_sujets_institutionnels_admis_sans_juge(sujet):
    juge = _Juge('{"personne": true}')
    verdict = await verifier_sujet(sujet, juge=juge, model="juge")
    assert verdict.admis, verdict.raison
    assert juge.appels == []  # décidable lexicalement, le juge n'est pas sollicité


@pytest.mark.parametrize(
    "sujet",
    [
        "Jean Dupont",
        "Marie-Claire Martin préfète",
        "dupont jean adresse",
        "Jean DUPONT",
    ],
)
async def test_nom_d_individu_bloque(sujet):
    juge = _Juge('{"personne": true, "reason": "nom d\'individu"}')
    verdict = await verifier_sujet(sujet, juge=juge, model="juge")
    assert not verdict.admis
    assert "personne" in verdict.raison


async def test_cas_ambigu_tranche_par_le_juge():
    """Deux mots capitalisés inconnus du lexique : le juge décide."""
    verdict = await verifier_sujet(
        "Pont Neuf travaux", juge=_Juge('{"personne": false}'), model="juge"
    )
    assert verdict.admis
    verdict = await verifier_sujet(
        "Pont Neuf travaux",
        juge=_Juge('{"personne": true, "reason": "x"}'),
        model="juge",
    )
    assert not verdict.admis


async def test_juge_indisponible_bloque():
    class Panne:
        async def complete(self, **_):
            raise RuntimeError("hub down")

    verdict = await verifier_sujet("Pont Neuf travaux", juge=Panne(), model="juge")
    assert not verdict.admis and "indisponible" in verdict.raison


def test_regle_documentee():
    assert garde_noms.REGLE.startswith(
        "Une veille ne peut pas cibler une personne physique"
    )
    assert isinstance(Verdict(False, "x"), Verdict)
