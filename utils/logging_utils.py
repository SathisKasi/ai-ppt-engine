"""
utils/logging_utils.py — Structured logging configuration.

Provides a consistent logger factory for all modules.
Log level is controlled by the LOG_LEVEL environment variable.
"""

from __future__ import annotations

import logging
import os
import sys


def configure_logging() -> None:
    """Configure root logger. Call once at application startup."""
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stderr,
        force=True,
    )


def get_logger(name: str) -> logging.Logger:
    """Return a module-level logger."""
    return logging.getLogger(name)
