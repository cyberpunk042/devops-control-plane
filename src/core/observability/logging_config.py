"""
Logging configuration — central setup for all entrypoints.

Called once at startup by main.py.  Every module that does
``logger = logging.getLogger(__name__)`` inherits this config.

Levels are resolved in precedence order:
    CLI flag  >  DCP_LOG_LEVEL env var  >  WARNING (default)

Optional file output via DCP_LOG_FILE / DCP_LOG_FILE_LEVEL env vars.
"""

from __future__ import annotations

import logging
import sys

# ── Format strings ──────────────────────────────────────────────

# WARNING level — minimal, no noise
_FMT_MINIMAL = "%(message)s"

# INFO level — timestamped with module context
_FMT_VERBOSE = "%(asctime)s [%(name)s] %(message)s"
_DATEFMT_VERBOSE = "%H:%M:%S"

# DEBUG level — full diagnostic with file:line
_FMT_DEBUG = "%(asctime)s %(levelname)-5s %(name)s:%(lineno)d — %(message)s"
_DATEFMT_DEBUG = "%H:%M:%S"

# File output — always full detail
_FMT_FILE = "%(asctime)s %(levelname)-5s %(name)s:%(lineno)d — %(message)s"
_DATEFMT_FILE = "%Y-%m-%d %H:%M:%S"

# Third-party loggers that are noisy at INFO/DEBUG
_NOISY_LOGGERS = ("urllib3", "watchdog", "PIL", "charset_normalizer")


def setup_logging(
    level: str = "WARNING",
    log_file: str | None = None,
    log_file_level: str | None = None,
    quiet_third_party: bool = True,
) -> None:
    """Configure Python logging for the entire process.

    Args:
        level: Log level name (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        log_file: Optional path to a log file.
        log_file_level: Optional separate level for the log file.
            Defaults to the same as ``level``.
        quiet_third_party: If True, keep noisy third-party loggers at WARNING
            unless we're at DEBUG level.
    """
    numeric_level = _parse_level(level)

    # ── Console handler (stderr) ────────────────────────────────
    if numeric_level <= logging.DEBUG:
        fmt, datefmt = _FMT_DEBUG, _DATEFMT_DEBUG
    elif numeric_level <= logging.INFO:
        fmt, datefmt = _FMT_VERBOSE, _DATEFMT_VERBOSE
    else:
        fmt, datefmt = _FMT_MINIMAL, None

    console = logging.StreamHandler(sys.stderr)
    console.setLevel(numeric_level)
    console.setFormatter(logging.Formatter(fmt, datefmt=datefmt))

    # ── Root logger ─────────────────────────────────────────────
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(console)

    # Effective root level = minimum of console and file levels
    effective_level = numeric_level

    # ── File handler (optional) ─────────────────────────────────
    if log_file:
        file_level = _parse_level(log_file_level) if log_file_level else numeric_level
        effective_level = min(effective_level, file_level)

        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setLevel(file_level)
        fh.setFormatter(logging.Formatter(_FMT_FILE, datefmt=_DATEFMT_FILE))
        root.addHandler(fh)

    root.setLevel(effective_level)

    # ── Third-party noise control ───────────────────────────────
    if quiet_third_party and numeric_level > logging.DEBUG:
        for name in _NOISY_LOGGERS:
            logging.getLogger(name).setLevel(logging.WARNING)

    # Don't propagate exceptions from logging itself
    logging.raiseExceptions = False


def _parse_level(level: str | None) -> int:
    """Convert a level name string to its numeric constant."""
    if not level:
        return logging.WARNING
    numeric = getattr(logging, level.upper(), None)
    if not isinstance(numeric, int):
        return logging.WARNING
    return numeric
