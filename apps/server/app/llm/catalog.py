"""Small static fallback catalog, used when the live LLM endpoint is unreachable."""

from app.schemas.agent import ModelProfile

FALLBACK_MODELS: list[ModelProfile] = [
    ModelProfile(
        id="gpt-oss-120b",
        label="GPT-OSS 120B (raisonnement)",
        tier="reasoning",
        short_pitch="Modele de raisonnement avance, plan interne avant de repondre.",
    ),
    ModelProfile(
        id="mistral-small-3.2-24b-instruct-2506",
        label="Mistral Small 3.2 (24B)",
        tier="light",
        short_pitch="Rapide et economique, ideal pour la redaction courante.",
    ),
]
