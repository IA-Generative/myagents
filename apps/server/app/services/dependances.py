"""Règle 3 de l'ADR : une capacité ne dépend que de capacités publiées, visibles de l'auteur, de
maturité au moins égale à la sienne, dans une version épinglée. Appliquée au `publish` sur les
dépendances directes (la transitivité est la question 4 de l'ADR) ; à l'exécution, la règle 4
borne les appels aux dépendances déclarées, jusqu'à `MESAGENTS_PROFONDEUR_MAX`.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.capability import Capability, CapabilityVersion
from app.services.visibilite import est_servie, est_visible

ORDRE_MATURITE: dict[str, int] = {"alpha": 0, "beta": 1, "general": 2}


def verifier(cible, version, maturite_dependante: str, user) -> str | None:
    """Raison du refus d'une dépendance, ou None si elle est admise."""
    if cible is None or not est_visible(cible, user):
        return "introuvable ou invisible"
    if not est_servie(cible):
        return "non publiée"
    if version is None:
        return "version épinglée inexistante"
    if ORDRE_MATURITE[version.maturity] < ORDRE_MATURITE[maturite_dependante]:
        return f"maturité {version.maturity} inférieure à {maturite_dependante}"
    return None


async def resoudre(
    db: AsyncSession, name: str, version: int | None
) -> tuple[Capability | None, CapabilityVersion | None]:
    """La capacité nommée et la version demandée (ou la version servie si `version` est None)."""
    cap = (
        await db.execute(select(Capability).where(Capability.name == name))
    ).scalar_one_or_none()
    if cap is None:
        return None, None
    numero = version if version is not None else cap.current_version
    if numero is None:
        return cap, None
    v = (
        await db.execute(
            select(CapabilityVersion).where(
                CapabilityVersion.capability_id == cap.id,
                CapabilityVersion.version == numero,
            )
        )
    ).scalar_one_or_none()
    return cap, v


async def verifier_dependances(
    db: AsyncSession, dependencies: list[dict], maturite: str, user
) -> list[str]:
    """Les raisons de refus (vide = toutes admises), une par dépendance refusée."""
    raisons: list[str] = []
    for dep in dependencies:
        cible, version = await resoudre(db, dep["name"], dep["version"])
        raison = verifier(cible, version, maturite, user)
        if raison:
            raisons.append(f"{dep['name']}@{dep['version']} : {raison}")
    return raisons
