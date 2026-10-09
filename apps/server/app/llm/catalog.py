"""Small static fallback catalog, used when the live LLM endpoint is unreachable.

Only the hub's stable aliases belong here: a dated model name gets retired or renamed by
the operator, and an agent created from this list would then be broken from birth.
"""

from app.schemas.agent import ModelProfile

FALLBACK_MODELS: list[ModelProfile] = [
    ModelProfile(
        id="chat",
        label="Chat",
        tier="balanced",
        short_pitch="Modele generaliste du hub, adapte a la redaction courante.",
    ),
    ModelProfile(
        id="chat-pro",
        label="Chat Pro (raisonnement)",
        tier="reasoning",
        short_pitch="Modele plus puissant, pour les demandes complexes.",
    ),
]
