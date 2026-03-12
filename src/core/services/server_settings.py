"""
Server settings — server-side feature toggles.

Persisted to ``.state/server_settings.json``.  These are server-level
settings that affect background services and API behaviour — separate
from browser preferences (localStorage) and devops card prefs.

Current settings:
    peek_index_enabled: bool
        Controls whether the project index (background AST parse,
        symbol index, peek cache) runs on the server.  When disabled,
        peek-refs returns empty and no background index thread starts.
        Does NOT affect Docusaurus build-time peek (that uses its own
        feature flag in project.yml → pages → segments → features).

    file_logging_enabled: bool
        When True, server logs are also written to a file on disk.
        Takes effect immediately (no restart required).

    file_logging_path: str
        Relative path for the log file.  Default: ``.state/web.log``.
        Resolved relative to the project root.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SETTINGS_FILE = ".state/server_settings.json"

# ── Defaults ────────────────────────────────────────────────────

_DEFAULTS: dict[str, Any] = {
    "peek_index_enabled": True,
    "file_logging_enabled": False,
    "file_logging_path": ".state/web.log",
}

# Handler name used to identify our runtime file handler
_FILE_HANDLER_NAME = "dcp_file_log"

# Max number of archived session logs to keep
_MAX_ARCHIVED_LOGS = 10


# ── Public API ──────────────────────────────────────────────────


def load_settings(project_root: Path) -> dict[str, Any]:
    """Load server settings, merging with defaults.

    The ``file_logging_path`` default is resolved from project.yml's
    ``web.log_file`` field if present, falling back to ``.state/web.log``.
    """
    # Start with hard defaults
    defaults = dict(_DEFAULTS)

    # Override file_logging_path default from project.yml web.log_file
    try:
        import yaml
        yml_path = project_root / "project.yml"
        if yml_path.is_file():
            yml = yaml.safe_load(yml_path.read_text(encoding="utf-8")) or {}
            web_cfg = yml.get("web") or {}
            if "log_file" in web_cfg:
                defaults["file_logging_path"] = web_cfg["log_file"]
    except Exception:
        pass  # YAML parse error — use hard default

    path = project_root / _SETTINGS_FILE
    if not path.is_file():
        return defaults
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        merged = dict(defaults)
        merged.update(raw)
        return merged
    except (json.JSONDecodeError, IOError):
        return defaults


def save_settings(project_root: Path, settings: dict[str, Any]) -> dict[str, Any]:
    """Save server settings.  Returns the validated/merged result."""
    merged = dict(_DEFAULTS)
    # Only accept known keys
    for key in _DEFAULTS:
        if key in settings:
            merged[key] = settings[key]

    path = project_root / _SETTINGS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(merged, indent=2), encoding="utf-8")

    return merged


def is_peek_index_enabled(project_root: Path) -> bool:
    """Quick check: is the peek/index feature enabled?"""
    return bool(load_settings(project_root).get("peek_index_enabled", True))


# ── File logging toggle (runtime) ──────────────────────────────

# Saved state before file logging boosted verbosity
_original_root_level: int | None = None
_original_console_levels: list[tuple[logging.Handler, int, logging.Formatter | None]] = []


def toggle_file_logging(project_root: Path, enabled: bool) -> dict[str, Any]:
    """Enable or disable file logging at runtime.

    When enabled:
      - File handler captures DEBUG-level logs (full detail).
      - Console handler is boosted to INFO (timestamped).
    When disabled:
      - File handler is removed.
      - Console handler reverts to its original level/format.

    No restart required.  Returns the updated settings dict.
    """
    global _original_root_level

    settings = load_settings(project_root)
    settings["file_logging_enabled"] = enabled
    merged = save_settings(project_root, settings)

    root_logger = logging.getLogger()
    log_path = project_root / merged.get("file_logging_path", ".state/web.log")

    # Remove existing file handler if present
    for handler in list(root_logger.handlers):
        if getattr(handler, "name", None) == _FILE_HANDLER_NAME:
            root_logger.removeHandler(handler)
            handler.close()

    if enabled:
        # Save original state so we can restore it later
        if _original_root_level is None:
            _original_root_level = root_logger.level
            _original_console_levels.clear()
            for h in root_logger.handlers:
                if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler):
                    _original_console_levels.append((h, h.level, h.formatter))

        # ── Archive previous session log before opening new one ──
        _rotate_log_on_startup(log_path)

        # ── File handler (DEBUG — full detail, per-session) ──
        log_path.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(
            str(log_path),
            mode="w",           # fresh file each session
            encoding="utf-8",
        )
        fh.name = _FILE_HANDLER_NAME
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-5s %(name)s:%(lineno)d — %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        root_logger.addHandler(fh)

        # ── Boost console to INFO (timestamped) ──
        info_fmt = logging.Formatter(
            "%(asctime)s [%(name)s] %(message)s",
            datefmt="%H:%M:%S",
        )
        for h in root_logger.handlers:
            if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler):
                h.setLevel(logging.INFO)
                h.setFormatter(info_fmt)

        # Root must be low enough for both handlers
        if root_logger.level > logging.DEBUG:
            root_logger.setLevel(logging.DEBUG)

        logger.info("File logging enabled → %s", log_path)
    else:
        # Restore original console levels and formats
        for h, orig_level, orig_fmt in _original_console_levels:
            h.setLevel(orig_level)
            if orig_fmt:
                h.setFormatter(orig_fmt)
        _original_console_levels.clear()

        # Restore original root level
        if _original_root_level is not None:
            root_logger.setLevel(_original_root_level)
            _original_root_level = None

        logger.info("File logging disabled")

    return merged


# ── Session-based log rotation ─────────────────────────────────


def _rotate_log_on_startup(log_path: Path) -> None:
    """Archive the previous session's log file before opening a new one.

    Layout::

        .state/web.log                          ← current session (always fresh)
        .state/logs/web.2026-03-12_131625.log   ← archived session
        .state/logs/web.2026-03-11_094512.log   ← older session
        .state/logs/web.previous.log            ← symlink → latest archive

    Only the last ``_MAX_ARCHIVED_LOGS`` archives are kept.
    """
    if not log_path.is_file() or log_path.stat().st_size == 0:
        return  # nothing to archive

    archive_dir = log_path.parent / "logs"
    archive_dir.mkdir(parents=True, exist_ok=True)

    # Use the log file's modification time for the archive name
    # (reflects when the previous session last wrote)
    mtime = datetime.fromtimestamp(log_path.stat().st_mtime)
    stem = log_path.stem   # "web"
    suffix = log_path.suffix  # ".log"
    archive_name = f"{stem}.{mtime.strftime('%Y-%m-%d_%H%M%S')}{suffix}"
    archive_path = archive_dir / archive_name

    # Avoid overwriting if somehow the same timestamp exists
    if archive_path.exists():
        archive_name = f"{stem}.{mtime.strftime('%Y-%m-%d_%H%M%S')}.{os.getpid()}{suffix}"
        archive_path = archive_dir / archive_name

    try:
        shutil.move(str(log_path), str(archive_path))
    except OSError:
        return  # can't archive — just let the new session overwrite

    # Update "previous" symlink for convenience
    previous_link = archive_dir / f"{stem}.previous{suffix}"
    try:
        if previous_link.is_symlink() or previous_link.exists():
            previous_link.unlink()
        previous_link.symlink_to(archive_path.name)
    except OSError:
        pass  # symlink not critical

    # Prune old archives (keep only _MAX_ARCHIVED_LOGS most recent)
    archives = sorted(
        [
            f for f in archive_dir.iterdir()
            if f.is_file()
            and not f.is_symlink()
            and f.name.startswith(stem + ".")
            and f.suffix == suffix
            and f.name != f"{stem}.previous{suffix}"
        ],
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    for old in archives[_MAX_ARCHIVED_LOGS:]:
        try:
            old.unlink()
        except OSError:
            pass
