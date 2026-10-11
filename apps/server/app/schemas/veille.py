"""Schémas des veilles (chantier 3)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Source = Literal["legifrance", "web"]


class ScheduleCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    sujet: str = Field(min_length=1, max_length=200)
    sources: list[Source] = Field(min_length=1, max_length=2)
    cron: str = Field(min_length=1, max_length=64)
    actif: bool = True


class SchedulePatch(BaseModel):
    model_config = ConfigDict(extra="ignore")

    sujet: str | None = Field(default=None, min_length=1, max_length=200)
    sources: list[Source] | None = Field(default=None, min_length=1, max_length=2)
    cron: str | None = Field(default=None, min_length=1, max_length=64)
    actif: bool | None = None
