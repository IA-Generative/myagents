"""Central logging configuration, applied once at startup."""

import logging

from app.core.config import get_settings

_CONFIGURED = False

# Chemins lus en boucle par des automates (noteur de version, ADR-0004) : hors journal d'accès.
SILENT_ACCESS_PATHS = ("/__version__",)


class _SilentPathsFilter(logging.Filter):
    """Écarte du journal d'accès d'uvicorn les requêtes vers SILENT_ACCESS_PATHS."""

    def filter(self, record: logging.LogRecord) -> bool:
        # uvicorn.access : args = (client, méthode, chemin complet, version HTTP, statut).
        args = record.args if isinstance(record.args, tuple) else ()
        path = str(args[2]).split("?", 1)[0] if len(args) > 2 else ""
        return path not in SILENT_ACCESS_PATHS


def setup_logging() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )
    # Quiet down noisy third-party transport loggers unless we're in DEBUG.
    # (langchain-openai vendors its own httpx/httpcore under the "...2" names.)
    if level > logging.DEBUG:
        for noisy in (
            "httpx",
            "httpx2",
            "httpcore",
            "httpcore2",
            "openai._base_client",
        ):
            logging.getLogger(noisy).setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").addFilter(_SilentPathsFilter())
    _CONFIGURED = True
