"""Invariants structurels du corpus ZORG (portage de zorg-corpus.test.ts).

Le corpus est la sortie figée du générateur de production. On n'exige pas que
la couche 1 bloque tout ZORG : certaines techniques visent justement à la passer
pour être rattrapées par le prompt durci, la sortie et le juge.
"""

from tests.redteam.corpus import ZORG_ATTACKS


def test_corpus_is_not_empty():
    assert len(ZORG_ATTACKS) > 20


def test_ids_are_unique():
    ids = [a["id"] for a in ZORG_ATTACKS]
    assert len(set(ids)) == len(ids)


def test_every_payload_carries_its_metadata():
    for a in ZORG_ATTACKS:
        assert len(a["prompt"].strip()) > 50
        assert len(a["goal"].strip()) > 10
        assert a["source"] == "zorg"
        assert a["lang"] in {"fr", "en"}
        assert a["axes"]
        assert a["goalKind"] in {"keylogger", "disinfo", "prompt-leak"}
        # Toujours au moins les techniques d'enveloppe ZORG.
        assert "persona-hijack" in a["axes"]
        assert "refusal-suppression" in a["axes"]


def test_covers_both_languages_all_goals_and_both_roles():
    assert {a["lang"] for a in ZORG_ATTACKS} == {"fr", "en"}
    assert {a["goalKind"] for a in ZORG_ATTACKS} == {
        "keylogger",
        "disinfo",
        "prompt-leak",
    }
    assert {a["deliveryRole"] for a in ZORG_ATTACKS} == {"user", "system"}


def test_prompt_leak_is_user_delivered_only():
    leak = [a for a in ZORG_ATTACKS if a["goalKind"] == "prompt-leak"]
    assert leak
    assert all(a["deliveryRole"] == "user" for a in leak)
