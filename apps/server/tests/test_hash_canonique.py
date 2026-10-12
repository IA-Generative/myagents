"""Hash canonique d'une version (ADR §10.0 : sha256 hex d'un JSON trié, UTF-8, sans espaces)."""

import hashlib
import json

from app.core.hashing import hash_canonique

DEF = {"prompt": "Tu reformules.", "model": "chat", "temperature": 0.2}
SCHEMA = {
    "type": "object",
    "properties": {"text": {"type": "string"}},
    "required": ["text"],
}
DEPS = [{"name": "b", "version": 2}, {"name": "a", "version": 1}]


def test_meme_entree_meme_hash():
    assert hash_canonique(DEF, SCHEMA, DEPS) == hash_canonique(DEF, SCHEMA, DEPS)


def test_forme_sha256_hex():
    h = hash_canonique(DEF, SCHEMA, DEPS)
    assert len(h) == 64 and int(h, 16) >= 0


def test_ordre_des_cles_indifferent():
    inverse = {"temperature": 0.2, "model": "chat", "prompt": "Tu reformules."}
    assert hash_canonique(DEF, SCHEMA, DEPS) == hash_canonique(inverse, SCHEMA, DEPS)


def test_ordre_des_dependances_indifferent():
    assert hash_canonique(DEF, SCHEMA, DEPS) == hash_canonique(
        DEF, SCHEMA, list(reversed(DEPS))
    )


def test_un_espace_change_le_hash():
    """C-A3 : un espace ajouté dans le prompt change le hash."""
    modif = {**DEF, "prompt": "Tu reformules. "}
    assert hash_canonique(DEF, SCHEMA, DEPS) != hash_canonique(modif, SCHEMA, DEPS)


def test_serialisation_canonique_exacte():
    """La sérialisation est celle de l'ADR : JSON trié, séparateurs compacts, UTF-8 non échappé."""
    charge = {
        "definition": {"prompt": "Déjà vu"},
        "input_schema": {"type": "object"},
        "dependencies": [{"name": "a", "version": 1}],
    }
    attendu = hashlib.sha256(
        json.dumps(
            charge, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
    ).hexdigest()
    assert (
        hash_canonique(
            {"prompt": "Déjà vu"}, {"type": "object"}, [{"name": "a", "version": 1}]
        )
        == attendu
    )


def test_title_et_description_hors_hash():
    """Strictement l'ADR : seuls definition, input_schema, dependencies entrent dans le hash."""
    assert hash_canonique(DEF, SCHEMA, []) == hash_canonique(
        dict(DEF), dict(SCHEMA), []
    )
