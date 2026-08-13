"""Standard-library logging configuration, aligned with uvicorn's loggers.

Called once at startup (before the app is created) so that application,
uvicorn, and sqlalchemy records share one format and stream.
"""

from __future__ import annotations

import logging
import sys

from app.core.config import settings

_LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def configure_logging() -> None:
    """Configure root logging; idempotent (safe under uvicorn reloads)."""
    level = logging.INFO if settings.app_env == "production" else logging.DEBUG

    root = logging.getLogger()
    root.setLevel(level)

    # Replace any pre-existing handlers so reloads don't duplicate output.
    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))
    root.addHandler(handler)

    # Let uvicorn's loggers propagate to the root handler instead of using
    # their own, so all lines share one format.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers = []
        logger.propagate = True

    # SQL echo is too chatty even in development unless explicitly needed.
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
