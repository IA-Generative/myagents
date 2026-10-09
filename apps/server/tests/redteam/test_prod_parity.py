"""Parité avec la garde de production.

`data/prod_parity.json` a été produit en exécutant le code TypeScript de
production (origin/main:src/packages/prompt-guard) sous Node sur les mêmes
fichiers de données. Le portage Python doit rendre exactement les mêmes
décisions : blocage, signaux, scores d'anomalie, déobfuscation, repli du juge.
"""

import math

import pytest

from app.llm.guard import (
    DEFAULT_GUARD_CONFIG,
    anomaly_score,
    deobfuscate,
    inspect_input,
    inspect_output,
    parse_keyword_verdict,
)
from tests.redteam.corpus import ATTACKS, BENIGN, GCG, PROD_PARITY, ZORG_ATTACKS


def _texts() -> dict[str, tuple[str, str]]:
    texts = {
        a["id"]: (a["prompt"], a["deliveryRole"]) for a in [*ATTACKS, *ZORG_ATTACKS]
    }
    for group, samples in BENIGN.items():
        for i, text in enumerate(samples, start=1):
            texts[f"benign-{group}-{i}"] = (text, "user")
    for key, text in GCG.items():
        texts[f"gcg-{key}"] = (text, "user")
    return texts


TEXTS = _texts()
EXPECTED = PROD_PARITY["inputs"]


def test_reference_covers_every_sample():
    assert [e["id"] for e in EXPECTED] == list(TEXTS)


@pytest.mark.parametrize("expected", EXPECTED, ids=lambda e: e["id"])
def test_inspect_input_matches_production(expected):
    text, role = TEXTS[expected["id"]]
    result = inspect_input(text, role, anomaly=DEFAULT_GUARD_CONFIG.anomaly)
    assert result.blocked == expected["blocked"]
    got = [
        {
            "source": s.source,
            "severity": s.severity,
            "advisory": s.advisory,
            # La raison keylogger cite la regex, dont l'écriture diffère en Python.
            "reason": None if s.source == "keylogger" else s.reason,
        }
        for s in result.signals
    ]
    assert got == expected["signals"]


@pytest.mark.parametrize("expected", EXPECTED, ids=lambda e: e["id"])
def test_anomaly_score_matches_production(expected):
    text, _ = TEXTS[expected["id"]]
    score = anomaly_score(text)
    ref = expected["anomaly"]
    assert score.words == ref["words"]
    for name in ("score", "whole", "prefix", "suffix"):
        assert math.isclose(getattr(score, name), ref[name], abs_tol=1e-9), name


@pytest.mark.parametrize("expected", EXPECTED, ids=lambda e: e["id"])
def test_output_heuristics_and_deobfuscation_match_production(expected):
    text, _ = TEXTS[expected["id"]]
    assert inspect_output(text).blocked == expected["outputBlocked"]
    assert deobfuscate(text) == expected["deobfuscated"]


@pytest.mark.parametrize("case", PROD_PARITY["keywords"], ids=lambda c: repr(c["raw"]))
def test_keyword_fallback_matches_production(case):
    verdict = parse_keyword_verdict(case["raw"])
    if case["verdict"] is None:
        assert verdict is None
    else:
        assert verdict is not None
        assert verdict.complied == case["verdict"]["complied"]
        assert verdict.reason == case["verdict"]["reason"]
