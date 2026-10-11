"""Planification des veilles : expressions cron à cinq champs, créneaux dus, une exécution par
veille et par créneau (chantier 3, partie « modèle »)."""

from datetime import UTC, datetime

import pytest

from app.veilles.planification import (
    PRESETS,
    CronInvalide,
    analyser,
    correspond,
    creneau_courant,
    creneaux_dus,
)


def _t(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=UTC)


def test_presets_sont_des_cron_valides():
    for nom, expression in PRESETS.items():
        analyser(expression)
        assert nom


@pytest.mark.parametrize(
    ("expression", "instant", "attendu"),
    [
        ("0 7 * * *", "2026-10-12T07:00", True),
        ("0 7 * * *", "2026-10-12T07:01", False),
        ("0 7 * * 1", "2026-10-12T07:00", True),  # lundi
        ("0 7 * * 1", "2026-10-13T07:00", False),
        ("*/15 * * * *", "2026-10-12T07:45", True),
        ("*/15 * * * *", "2026-10-12T07:50", False),
        ("0 7 1 * *", "2026-11-01T07:00", True),
        ("0 7,19 * * 1-5", "2026-10-16T19:00", True),  # vendredi
        ("0 7,19 * * 1-5", "2026-10-17T19:00", False),  # samedi
    ],
)
def test_correspondance(expression, instant, attendu):
    assert correspond(analyser(expression), _t(instant)) is attendu


@pytest.mark.parametrize(
    "expression", ["", "0 7 * *", "60 7 * * *", "0 25 * * *", "a b c d e", "0 7 * * 8"]
)
def test_expressions_invalides(expression):
    with pytest.raises(CronInvalide):
        analyser(expression)


def test_creneau_courant_est_la_minute_du_cron():
    assert creneau_courant(analyser("0 7 * * *"), _t("2026-10-12T07:00:42")) == _t(
        "2026-10-12T07:00"
    )
    assert creneau_courant(analyser("0 7 * * *"), _t("2026-10-12T07:01:00")) is None


def test_creneaux_dus_entre_deux_instants():
    dus = creneaux_dus(
        analyser("*/30 * * * *"), _t("2026-10-12T07:10"), _t("2026-10-12T08:40")
    )
    assert dus == [
        _t("2026-10-12T07:30"),
        _t("2026-10-12T08:00"),
        _t("2026-10-12T08:30"),
    ]


def test_creneaux_dus_bornes_au_rattrapage_maximal():
    """Un service arrêté un mois ne rejoue pas trente jours : au plus `maximum` créneaux, les derniers."""
    dus = creneaux_dus(
        analyser("0 7 * * *"), _t("2026-09-01T00:00"), _t("2026-10-12T08:00"), maximum=3
    )
    assert dus == [
        _t("2026-10-10T07:00"),
        _t("2026-10-11T07:00"),
        _t("2026-10-12T07:00"),
    ]
