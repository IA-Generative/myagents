"""Shared enums for the agent domain model."""

import enum


class Visibility(str, enum.Enum):
    private = "private"
    community = "community"
    ministry = "ministry"


class AgentStatus(str, enum.Enum):
    draft = "draft"
    published = "published"
    submitted = "submitted"
    archived = "archived"
