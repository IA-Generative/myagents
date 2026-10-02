"""Plan de présentation fourni par le LLM, validé et borné avant tout rendu.

Le schéma est volontairement plat (pas d'union discriminée) : les modèles OpenAI-compatibles
suivent mieux un schéma d'outil simple.
"""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, Field, StringConstraints, model_validator

from app.llm.presentations.themes import DEFAULT_THEME

MAX_SLIDES = 40

Title = Annotated[str, StringConstraints(min_length=1, max_length=120)]
Line = Annotated[str, StringConstraints(max_length=300)]
Cell = Annotated[str, StringConstraints(max_length=120)]
Bullets = Annotated[list[Line], Field(max_length=12)]
Notes = Annotated[str, StringConstraints(max_length=2000)]

SlideLayout = Literal["section", "bullets", "two_column", "table", "chart"]


class TableSpec(BaseModel):
    headers: Annotated[list[Cell], Field(min_length=1, max_length=8)]
    rows: Annotated[list[list[Cell]], Field(min_length=1, max_length=20)]

    @model_validator(mode="after")
    def _rectangular(self) -> Self:
        width = len(self.headers)
        if any(len(row) != width for row in self.rows):
            raise ValueError(
                "chaque ligne doit avoir autant de cellules que d'en-têtes"
            )
        return self


class ChartSeries(BaseModel):
    name: Cell
    values: Annotated[
        list[Annotated[float, Field(allow_inf_nan=False)]],
        Field(min_length=1, max_length=20),
    ]


class ChartSpec(BaseModel):
    type: Literal["bar", "line", "pie"]
    categories: Annotated[list[Cell], Field(min_length=1, max_length=20)]
    series: Annotated[list[ChartSeries], Field(min_length=1, max_length=5)]

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if any(len(s.values) != len(self.categories) for s in self.series):
            raise ValueError("chaque série doit avoir une valeur par catégorie")
        if self.type == "pie" and len(self.series) != 1:
            raise ValueError("un graphique en camembert n'accepte qu'une seule série")
        return self


class SlideSpec(BaseModel):
    layout: SlideLayout = Field(
        description=(
            "section: page de titre de partie (title + subtitle optionnel) ; "
            "bullets: titre + puces ; two_column: titre + left/right ; "
            "table: titre + table ; chart: titre + chart."
        )
    )
    title: Title
    subtitle: Line = ""
    bullets: Bullets = Field(default_factory=list)
    left: Bullets = Field(default_factory=list)
    right: Bullets = Field(default_factory=list)
    table: TableSpec | None = None
    chart: ChartSpec | None = None
    notes: Notes = Field(default="", description="Notes de l'orateur (optionnel).")

    @model_validator(mode="after")
    def _required_content(self) -> Self:
        if self.layout == "bullets" and not self.bullets:
            raise ValueError("layout 'bullets' : 'bullets' est requis")
        if self.layout == "two_column" and not (self.left and self.right):
            raise ValueError("layout 'two_column' : 'left' et 'right' sont requis")
        if self.layout == "table" and self.table is None:
            raise ValueError("layout 'table' : 'table' est requis")
        if self.layout == "chart" and self.chart is None:
            raise ValueError("layout 'chart' : 'chart' est requis")
        return self


class DeckSpec(BaseModel):
    title: Title
    subtitle: Line = ""
    author: Annotated[str, StringConstraints(max_length=120)] = ""
    theme: str = Field(
        default=DEFAULT_THEME,
        description="Nom d'un thème (voir list_presentation_themes).",
    )
    slides: Annotated[list[SlideSpec], Field(min_length=1, max_length=MAX_SLIDES)]
