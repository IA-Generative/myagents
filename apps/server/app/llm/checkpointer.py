"""LangGraph checkpointer for multi-turn agent state persistence.

Uses AsyncPostgresSaver on PostgreSQL, falls back gracefully on SQLite (tests/dev)
where the Postgres checkpointer cannot operate. In that case no checkpointer is
configured — the agent remains stateless (same behaviour as before this module).
"""

import logging

from langgraph.checkpoint.base import BaseCheckpointSaver

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_checkpointer: BaseCheckpointSaver | None = None
_setup_done = False


async def setup_checkpointer() -> BaseCheckpointSaver | None:
    """Initialise the async Postgres checkpointer. Called once at app startup."""
    global _checkpointer, _setup_done
    if _setup_done:
        return _checkpointer
    _setup_done = True

    settings = get_settings()
    url = settings.database_url

    if url.startswith("postgresql"):
        try:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

            _checkpointer = AsyncPostgresSaver.from_conn_string(_sync_url(url))
            await _checkpointer.setup()
            logger.info("checkpointer AsyncPostgresSaver initialisé")
        except Exception as exc:  # noqa: BLE001
            logger.warning("checkpointer Postgres indisponible: %s", type(exc).__name__)
            _checkpointer = None
    else:
        logger.info(
            "base non-Postgres (%s) — checkpointer désactivé", url.split("://")[0]
        )

    return _checkpointer


def get_checkpointer() -> BaseCheckpointSaver | None:
    """Return the initialised checkpointer, or None if unavailable."""
    return _checkpointer


def _sync_url(async_url: str) -> str:
    """Convert postgresql+asyncpg:// back to postgresql:// for the checkpointer."""
    for scheme in ("postgresql+asyncpg://", "postgres+asyncpg://"):
        if async_url.startswith(scheme):
            return "postgresql://" + async_url.removeprefix(scheme)
    return async_url
