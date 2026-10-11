"""Hash canonique d'une version publiée (ADR §4.2, §10.0 Identifiants).

`sha256` hexadécimal de la sérialisation canonique — JSON trié à tous les niveaux, séparateurs
compacts, UTF-8 non échappé — de `definition + input_schema + dependencies`. Aucune normalisation
Unicode : un espace changé dans le prompt change le hash (C-A3). Le titre, la description et les
annotations n'entrent pas dans le hash (strictement l'ADR ; voir le rapport, question Q1).

La migration `capacites_gouvernees` embarque une copie figée de cette fonction : un test vérifie
qu'elles rendent la même valeur.
"""

import hashlib
import json


def _cle_dependance(dep: dict) -> tuple[str, int]:
    return (str(dep.get("name", "")), int(dep.get("version", 0)))


def hash_canonique(
    definition: dict, input_schema: dict, dependencies: list[dict]
) -> str:
    charge = {
        "definition": definition,
        "input_schema": input_schema,
        "dependencies": sorted((dict(d) for d in dependencies), key=_cle_dependance),
    }
    octets = json.dumps(
        charge, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(octets).hexdigest()
