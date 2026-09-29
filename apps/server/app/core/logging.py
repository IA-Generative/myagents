"""Central logging configuration, applied once at startup."""

import logging

from app.core.config import get_settings

_CONFIGURED = False


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
    _CONFIGURED = True
