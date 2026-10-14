"""Palettes disponibles pour les présentations et graphiques (couleurs en hexadécimal RGB)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Theme:
    name: str
    description: str
    background: str
    title_color: str
    text_color: str
    primary: str
    accent: str
    on_primary: str
    font: str
    series: tuple[str, ...]
    # Page de titre et pages de section.
    cover_background: str
    cover_title_color: str
    cover_text_color: str
    # Fond des lignes paires des tableaux.
    stripe: str
    # Bloc "République Française" et liseré tricolore sur les pages de titre.
    marque: bool = False


DSFR = Theme(
    name="dsfr",
    description=(
        "Système de design de l'État (DSFR) : bleu France, rouge Marianne, police "
        "Marianne, bloc République Française. Thème par défaut."
    ),
    background="FFFFFF",
    title_color="000091",
    text_color="161616",
    primary="000091",
    accent="E1000F",
    on_primary="FFFFFF",
    font="Marianne",
    # Couleurs illustratives du DSFR, ordonnées pour rester distinguables entre elles.
    series=(
        "000091",
        "E1000F",
        "009081",
        "FCC63A",
        "A558A0",
        "417DC4",
        "E4794A",
        "68A532",
    ),
    cover_background="F5F5FE",
    cover_title_color="000091",
    cover_text_color="161616",
    stripe="F5F5FE",
    marque=True,
)

THEMES: dict[str, Theme] = {
    "dsfr": DSFR,
    "sobre": Theme(
        name="sobre",
        description="Gris anthracite et vert discret, très lisible et neutre.",
        background="F6F6F6",
        title_color="3A3A3A",
        text_color="161616",
        primary="3A3A3A",
        accent="18753C",
        on_primary="FFFFFF",
        font="Arial",
        series=("3A3A3A", "18753C", "929292", "B7A73F", "CE614A"),
        cover_background="3A3A3A",
        cover_title_color="FFFFFF",
        cover_text_color="FFFFFF",
        stripe="E8E8E8",
    ),
    "dynamique": Theme(
        name="dynamique",
        description="Turquoise et orange, pour des présentations plus vivantes.",
        background="FFFFFF",
        title_color="006A6F",
        text_color="161616",
        primary="006A6F",
        accent="D64D00",
        on_primary="FFFFFF",
        font="Arial",
        series=("006A6F", "D64D00", "009081", "FCC63A", "6A6AF4"),
        cover_background="006A6F",
        cover_title_color="FFFFFF",
        cover_text_color="FFFFFF",
        stripe="F2F2F2",
    ),
}

DEFAULT_THEME = "dsfr"
