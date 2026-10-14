"""Corpus red-team de la production, chargé depuis `data/` (copié tel quel depuis origin/main).

Les payloads sont des gabarits offensifs publics (OWASP LLM01) ; le code keylogger
qu'ils contiennent est inerte (chaînes de caractères) et sert de cible aux détecteurs.
"""

import json
from functools import cache
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).parent / "data"


@cache
def load(name: str) -> dict[str, Any]:
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


ATTACKS: list[dict[str, Any]] = load("attacks.json")["ATTACKS"]
ZORG_ATTACKS: list[dict[str, Any]] = load("zorg_attacks.json")["ZORG_ATTACKS"]
KEYLOGGER: str = load("attacks.json")["KEYLOGGER"]
BENIGN: dict[str, list[str]] = {
    k: v for k, v in load("benign.json").items() if not k.startswith("_")
}
GCG: dict[str, str] = {
    k: v for k, v in load("gcg.json").items() if not k.startswith("_")
}
PROD_PARITY: dict[str, Any] = load("prod_parity.json")


def attack(attack_id: str) -> dict[str, Any]:
    return next(a for a in ATTACKS if a["id"] == attack_id)
