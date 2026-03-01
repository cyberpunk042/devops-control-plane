"""
Admin server shared helpers.

Centralised utilities used across multiple route blueprints.
Anything that was previously duplicated across route files
(project_root, safe-path resolution, auth decorators, cache
busting) lives here so routes stay thin.
"""

from __future__ import annotations

import functools
import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


# ── Flask app context helpers ──────────────────────────────────


def project_root() -> Path:
    """Active project root from Flask app config."""
    from flask import current_app

    return Path(current_app.config["PROJECT_ROOT"])


def resolve_safe_path(relative: str) -> Path | None:
    """Resolve *relative* safely, preventing directory traversal.

    Returns ``None`` if the resolved path escapes the project root.
    """
    root = project_root()
    try:
        resolved = (root / relative).resolve()
        # Ensure it's within the project root
        resolved.relative_to(root.resolve())
        return resolved
    except (ValueError, RuntimeError):
        return None


def get_enc_key() -> str:
    """Read ``CONTENT_VAULT_ENC_KEY`` from the project's ``.env``."""
    from src.core.services.secrets_ops import fresh_env as svc_fresh_env

    env = svc_fresh_env(project_root())
    return env.get("CONTENT_VAULT_ENC_KEY", "").strip()


def get_stack_names() -> list[str]:
    """Get unique stack names from detected project modules."""
    try:
        from src.core.config.loader import load_project
        from src.core.config.stack_loader import discover_stacks
        from src.core.services.detection import detect_modules

        root = project_root()
        project = load_project(root / "project.yml")
        stacks = discover_stacks(root / "stacks")
        detection = detect_modules(project, root, stacks)

        seen: set[str] = set()
        names: list[str] = []
        for m in detection.modules:
            stack = m.effective_stack
            if stack and stack not in seen:
                names.append(stack)
                seen.add(stack)
        return names
    except Exception:
        return []


# ── Cache helpers ──────────────────────────────────────────────


def bust_tool_caches() -> None:
    """Invalidate devops caches after tool install/update/remove.

    Called after any operation that changes tool availability so
    that the UI picks up the new state on next poll.
    """
    from src.core.services.devops import cache as devops_cache

    try:
        root = project_root()
        devops_cache.invalidate_scope(root, "integrations")
        devops_cache.invalidate_scope(root, "devops")
        devops_cache.invalidate(root, "wiz:detect")
    except Exception as exc:
        logger.warning("Failed to bust tool caches: %s", exc)


# ── Auth middleware ────────────────────────────────────────────


def requires_git_auth(fn):  # type: ignore[no-untyped-def]
    """Decorator for Flask routes that require git network auth.

    Checks ``is_auth_ok()`` before calling the handler.  If auth is
    not ready (SSH key needs passphrase, HTTPS needs token), the
    decorator:

      1. Runs ``check_auth()`` to get the detailed status dict.
      2. Publishes an ``auth:needed`` event on the EventBus so the
         client can reactively show the passphrase modal.
      3. Returns HTTP 401 with the status dict as JSON.

    Usage::

        @some_bp.route("/git/push", methods=["POST"])
        @requires_git_auth
        def git_push():
            ...
    """
    from src.core.services.git_auth import check_auth, is_auth_ok

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):  # type: ignore[no-untyped-def]
        if is_auth_ok():
            return fn(*args, **kwargs)

        # Auth not ready — gather details & notify client via SSE
        try:
            root = project_root()
            status = check_auth(root)
        except Exception:
            status = {"ok": False, "needs": "ssh_passphrase"}

        try:
            from src.core.services.event_bus import bus
            bus.publish("auth:needed", key="git", data=status)
        except Exception:
            logger.debug("EventBus publish failed (non-fatal)")

        from flask import jsonify
        return jsonify(status), 401

    return wrapper


# ── Subprocess helpers ─────────────────────────────────────────


def fresh_env(project_root_path: Path) -> dict:
    """Build subprocess env with fresh .env values.

    The server process's os.environ is stale — it was loaded at startup.
    This reads the current .env file on each call so test commands
    use the latest values.
    """
    env = {**os.environ, "TERM": "dumb"}
    env_file = project_root_path / ".env"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip()
                    # Strip surrounding quotes
                    if (
                        len(value) >= 2
                        and value[0] == value[-1]
                        and value[0] in ('"', "'")
                    ):
                        value = value[1:-1]
                    env[key] = value
    return env


def gh_repo_flag(project_root_path: Path) -> list:
    """Get -R repo flag for gh CLI commands.

    Required because mirror remotes cause gh to fail with
    'multiple remotes detected' when no -R is specified.
    """
    repo = fresh_env(project_root_path).get("GITHUB_REPOSITORY", "")
    return ["-R", repo] if repo else []
