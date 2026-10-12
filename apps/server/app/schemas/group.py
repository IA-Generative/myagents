"""Schéma de réponse pour la recherche de groupes Keycloak."""

from pydantic import BaseModel


class GroupProfile(BaseModel):
    id: str
    name: str
    path: str
