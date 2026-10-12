"""Expressions cron à cinq champs (minute heure jour mois jour-de-semaine), sans dépendance.

Grammaire admise : `*`, `*/n`, `a`, `a-b`, `a,b,c`, `a-b/n` ; jour de semaine 0-6 (0 = dimanche)
et 7 = dimanche. Un créneau est une minute. `creneaux_dus` borne le rattrapage.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

PRESETS: dict[str, str] = {
    "quotidienne": "0 7 * * *",
    "hebdomadaire": "0 7 * * 1",
    "mensuelle": "0 7 1 * *",
    "deux-fois-par-jour": "0 7,19 * * 1-5",
}

_BORNES = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7))


class CronInvalide(ValueError):
    pass


@dataclass(frozen=True)
class Cron:
    expression: str
    minutes: frozenset[int]
    heures: frozenset[int]
    jours: frozenset[int]
    mois: frozenset[int]
    jours_semaine: frozenset[int]  # 0 = dimanche … 6 = samedi


def _champ(texte: str, bornes: tuple[int, int]) -> frozenset[int]:
    bas, haut = bornes
    valeurs: set[int] = set()
    for partie in texte.split(","):
        pas = 1
        if "/" in partie:
            partie, pas_txt = partie.split("/", 1)
            if not pas_txt.isdigit() or int(pas_txt) < 1:
                raise CronInvalide(f"pas invalide : {pas_txt}")
            pas = int(pas_txt)
        if partie == "*":
            debut, fin = bas, haut
        elif "-" in partie:
            a, b = partie.split("-", 1)
            if not (a.isdigit() and b.isdigit()):
                raise CronInvalide(f"plage invalide : {partie}")
            debut, fin = int(a), int(b)
        elif partie.isdigit():
            debut = fin = int(partie)
        else:
            raise CronInvalide(f"valeur invalide : {partie}")
        if debut < bas or fin > haut or debut > fin:
            raise CronInvalide(f"hors bornes {bas}-{haut} : {partie}")
        valeurs.update(range(debut, fin + 1, pas))
    return frozenset(valeurs)


def analyser(expression: str) -> Cron:
    champs = (expression or "").split()
    if len(champs) != 5:
        raise CronInvalide(
            "cinq champs attendus : minute heure jour mois jour-de-semaine"
        )
    m, h, j, mo, js = (_champ(c, b) for c, b in zip(champs, _BORNES, strict=True))
    js = frozenset(0 if v == 7 else v for v in js)
    return Cron(expression, m, h, j, mo, js)


def correspond(cron: Cron, instant: datetime) -> bool:
    jour_semaine = (
        instant.weekday() + 1
    ) % 7  # Python : lundi = 0 ; cron : dimanche = 0
    return (
        instant.minute in cron.minutes
        and instant.hour in cron.heures
        and instant.day in cron.jours
        and instant.month in cron.mois
        and jour_semaine in cron.jours_semaine
    )


def creneau_courant(cron: Cron, instant: datetime) -> datetime | None:
    minute = instant.replace(second=0, microsecond=0)
    return minute if correspond(cron, minute) else None


def creneaux_dus(
    cron: Cron, depuis: datetime, jusqua: datetime, *, maximum: int = 3
) -> list[datetime]:
    """Les créneaux de `cron` dans ]depuis, jusqua], les `maximum` derniers seulement."""
    dus: list[datetime] = []
    t = jusqua.replace(second=0, microsecond=0)
    plancher = depuis.replace(second=0, microsecond=0)
    # On remonte minute par minute depuis `jusqua` : borné par le rattrapage, jamais par un mois.
    limite = 60 * 24 * 45
    while t > plancher and limite > 0 and len(dus) < maximum:
        if correspond(cron, t):
            dus.append(t)
        t -= timedelta(minutes=1)
        limite -= 1
    dus.reverse()
    return dus
