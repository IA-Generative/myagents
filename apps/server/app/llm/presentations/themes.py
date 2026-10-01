"""Palettes disponibles pour les présentations générées (couleurs en hexadécimal RGB)."""

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


THEMES: dict[str, Theme] = {
    "institutionnel": Theme(
        name="institutionnel",
        description="Bleu profond et rouge d'accent, adapté aux documents officiels.",
        background="FFFFFF",
        title_color="000091",
        text_color="161616",
        primary="000091",
        accent="E1000F",
        on_primary="FFFFFF",
        font="Arial",
        series=("000091", "E1000F", "6A6AF4", "FF9575", "7B7B7B"),
    ),
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
    ),
}

DEFAULT_THEME = "institutionnel"
