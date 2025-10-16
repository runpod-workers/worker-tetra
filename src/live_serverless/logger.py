"""
Logging configuration for worker-tetra.

Provides centralized logging setup matching tetra-rp style with level-based formatting.
"""

import logging
import os
import sys
from typing import Union, Optional


def get_log_level() -> int:
    """Get log level from environment variable, defaulting to INFO."""
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    return getattr(logging, log_level, logging.INFO)


def get_log_format(level: int) -> str:
    """Get appropriate log format based on level, matching tetra-rp style."""
    if level == logging.DEBUG:
        return "%(asctime)s | %(levelname)-5s | %(name)s | %(filename)s:%(lineno)d | %(message)s"
    else:
        return "%(asctime)s | %(levelname)-5s | %(message)s"


def setup_logging(
    level: Optional[Union[int, str]] = None,
    stream=sys.stdout,
    fmt: Optional[str] = None,
) -> None:
    """
    Setup logging configuration for worker-tetra.
    Only shows DEBUG logs from tetra namespace when LOG_LEVEL=DEBUG.

    Args:
        level: Log level (defaults to LOG_LEVEL env var or INFO)
        stream: Output stream for logs
        fmt: Custom format string (auto-selected based on level if None)
    """
    # Determine log level
    if level is None:
        level = get_log_level()
    elif isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)

    # Determine format based on requested level
    if fmt is None:
        fmt = get_log_format(level)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    if not root_logger.hasHandlers():
        handler = logging.StreamHandler(stream)
        handler.setFormatter(logging.Formatter(fmt))
        root_logger.addHandler(handler)

    # When DEBUG is requested, silence the noisy module
    if level == logging.DEBUG:
        logging.getLogger("filelock").setLevel(logging.INFO)
