"""Shared vault utilities."""

from __future__ import annotations

from pathlib import Path

from flask import request

from src.ui.web.helpers import project_root as _project_root


def _env_path() -> Path:
    """Resolve .env file path from optional ``?env=`` query param."""
    env_name = request.args.get("env", "").strip().lower()
    root = _project_root()
    if not env_name:
        return root / ".env"
    return root / f".env.{env_name}"
