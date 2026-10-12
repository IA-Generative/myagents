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
    configurer_journal_capacites(settings.mesagents_journal_fichier)
    _CONFIGURED = True


JOURNAL_LOGGER = "mesagents.journal"


def configurer_journal_capacites(fichier: str = "") -> None:
    """Journal des exécutions de capacités : une ligne JSON NUE par appel (règle 6 de l'ADR).

    Logger dédié, sans propagation (pas de préfixe horodaté qui casserait le JSON), sur la sortie
    standard et, si demandé, dans un fichier (exploité par les tests de conformité).
    """
    import sys

    journal = logging.getLogger(JOURNAL_LOGGER)
    journal.setLevel(logging.INFO)
    journal.propagate = False
    if not any(getattr(h, "_journal_capacites", False) for h in journal.handlers):
        sortie = logging.StreamHandler(sys.stdout)
        sortie.setFormatter(logging.Formatter("%(message)s"))
        sortie._journal_capacites = True  # type: ignore[attr-defined]
        journal.addHandler(sortie)
    if fichier and not any(
        getattr(h, "baseFilename", None) == fichier for h in journal.handlers
    ):
        try:
            f = logging.FileHandler(fichier, encoding="utf-8")
        except OSError as exc:
            # Un fichier de journal inaccessible ne doit jamais empêcher le service de démarrer :
            # la sortie standard reste le support premier du journal.
            logging.getLogger(__name__).error(
                "journal des capacités : fichier %s inaccessible (%s), sortie standard seule",
                fichier,
                exc,
            )
            return
        f.setFormatter(logging.Formatter("%(message)s"))
        f._journal_capacites = True  # type: ignore[attr-defined]
        journal.addHandler(f)
