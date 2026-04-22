from __future__ import annotations

import logging
import sys
from typing import Any

import structlog
from pythonjsonlogger.json import JsonFormatter


def configure_logging() -> None:
    """Configure structured logging for the application."""
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.ExtraAdder(),
    ]

    if sys.stderr.isatty():
        # Console rendering
        chain = [
            *shared_processors,
            structlog.dev.ConsoleRenderer(),
        ]
    else:
        # JSON rendering
        chain = [
            *shared_processors,
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ]

    structlog.configure(
        processors=chain,
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure standard library logging
    log_handler = logging.StreamHandler(sys.stdout)
    if not sys.stderr.isatty():
        log_handler.setFormatter(JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"))

    root_logger = logging.getLogger()
    root_logger.handlers = [log_handler]
    root_logger.setLevel(logging.INFO)


def get_logger(name: str) -> Any:
    """Get a structured logger instance."""
    return structlog.get_logger(name)
