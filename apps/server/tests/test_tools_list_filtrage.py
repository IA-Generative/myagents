"""`tools/list` : trois méta-outils + épinglés (≤ 7), filtrés par visibilité et par contexte `azp`
(ADR §4.4 « Tenir la taille de tools/list constante »)."""

import json

from app.mcp.filtrage import (
    META_OUTILS_NOMS,
    champs_fournis,
    construire_tools_list,
    servie_au_contexte,
)

SCHEMA_TEXT = {
    "type": "object",
    "properties": {"text": {"type": "string"}},
    "required": ["text"],
}
SCHEMA_EMAIL = {
    "type": "object",
    "properties": {"email": {"type": "string"}, "text": {"type": "string"}},
    "required": ["email"],
}
SCHEMA_OPTIONNEL = {
    "type": "object",
    "properties": {"selection": {"type": "string", "default": ""}},
    "required": ["selection"],
}


def test_trois_meta_outils():
    assert META_OUTILS_NOMS == (
        "rechercher_capacites",
        "decrire_capacite",
        "executer_capacite",
    )


def test_champs_fournis_par_contexte():
    contextes = {
        "socle": ["text"],
        "extension": ["text", "email", "selection"],
        "*": ["text"],
    }
    assert champs_fournis("socle", contextes) == {"text"}
    assert champs_fournis("extension", contextes) == {"text", "email", "selection"}
    assert champs_fournis("inconnu", contextes) == {"text"}
    assert champs_fournis("inconnu", {"socle": ["text"]}) == set()


def test_capacite_exigeant_un_champ_non_fournissable_non_servie():
    assert servie_au_contexte(SCHEMA_TEXT, {"text"})
    assert not servie_au_contexte(SCHEMA_EMAIL, {"text"})
    assert servie_au_contexte(SCHEMA_EMAIL, {"text", "email"})


def test_champ_requis_avec_defaut_compte_comme_fourni():
    assert servie_au_contexte(SCHEMA_OPTIONNEL, set())


def test_sans_champ_requis_toujours_servie():
    assert servie_au_contexte({"type": "object", "properties": {}}, set())


def _outil(name, schema=SCHEMA_TEXT, maturity="general"):
    return {
        "name": name,
        "title": name,
        "description": f"Capacité {name}",
        "inputSchema": schema,
        "annotations": {"readOnlyHint": True},
        "_meta": {
            "hash": "0" * 64,
            "version": 1,
            "maturity": maturity,
            "grounding": "input",
        },
    }


def test_taille_constante_quelle_que_soit_la_taille_du_catalogue():
    """C-A7 : méta-outils + épinglés seulement ; le nombre de capacités publiées n'entre pas."""
    epingles = [_outil(f"cap-{i}") for i in range(3)]
    petit = construire_tools_list(
        epingles, catalogue_taille=10, champs={"text"}, plafond=7
    )
    grand = construire_tools_list(
        epingles, catalogue_taille=1000, champs={"text"}, plafond=7
    )
    assert len(petit) == len(grand) == 3 + 3
    assert len(json.dumps(petit)) == len(json.dumps(grand))


def test_plafond_des_epingles():
    epingles = [_outil(f"cap-{i}") for i in range(12)]
    liste = construire_tools_list(
        epingles, catalogue_taille=12, champs={"text"}, plafond=7
    )
    assert len(liste) == 3 + 7
    assert [t["name"] for t in liste[3:]] == [f"cap-{i}" for i in range(7)]


def test_epingle_hors_contexte_ecartee():
    epingles = [_outil("texte"), _outil("mail", SCHEMA_EMAIL)]
    liste = construire_tools_list(
        epingles, catalogue_taille=2, champs={"text"}, plafond=7
    )
    assert [t["name"] for t in liste[3:]] == ["texte"]


def test_beta_marquee():
    liste = construire_tools_list(
        [_outil("b", maturity="beta")], catalogue_taille=1, champs={"text"}, plafond=7
    )
    outil = liste[3]
    assert outil["description"].startswith("[bêta] ")
    assert outil["_meta"]["maturity"] == "beta"


def test_meta_outils_en_tete_et_toujours_presents():
    liste = construire_tools_list([], catalogue_taille=0, champs=set(), plafond=7)
    assert [t["name"] for t in liste] == list(META_OUTILS_NOMS)
    for t in liste:
        assert t["inputSchema"]["type"] == "object"
        assert t["annotations"]["readOnlyHint"] in (True, False)
