"""Posture par défaut de la garde côté application.

Le modèle du juge se règle par `LLM_GUARD_JUDGE_MODEL` (repli sur
`LLM_ASSIST_MODEL`), voir `judge.resolve_judge_model`. Les noms de modèles bougent
chez les opérateurs : une variable d'environnement se corrige sans reconstruire.
Le juge est toujours fail-closed (aucun réglage ne le rend permissif).
"""

from dataclasses import dataclass

from app.llm.guard.core import AnomalyConfig

# Anomalie en posture « audit » : journalise un signal advisory sans bloquer
# (le proxy ne distingue pas le code légitime du gibberish).
AUDIT_ANOMALY = AnomalyConfig(mode="audit")


@dataclass(frozen=True)
class GuardConfig:
    anomaly: AnomalyConfig = AUDIT_ANOMALY


DEFAULT_GUARD_CONFIG = GuardConfig()
