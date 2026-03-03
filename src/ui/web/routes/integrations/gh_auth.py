"""GitHub authentication — login, logout, device flow, terminal poll, token."""

from __future__ import annotations

import subprocess
from pathlib import Path

from flask import jsonify, request

from src.core.services import git_ops
from src.core.services.run_tracker import run_tracked
from src.ui.web.helpers import project_root as _project_root

from . import integrations_bp


@integrations_bp.route("/gh/auth/logout", methods=["POST"])
@run_tracked("setup", "setup:gh_logout")
def gh_auth_logout():  # type: ignore[no-untyped-def]
    """Logout from GitHub CLI."""
    result = git_ops.gh_auth_logout(_project_root())
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@integrations_bp.route("/gh/auth/login", methods=["POST"])
@run_tracked("setup", "setup:gh_login")
def gh_auth_login():  # type: ignore[no-untyped-def]
    """Authenticate with GitHub CLI.

    Body (JSON):
        {"token": "ghp_…"}          → token mode (non-interactive)
        {"mode": "interactive"}     → spawn terminal for OAuth
        {} (empty)                  → spawn terminal for OAuth
    """
    data = request.get_json(silent=True) or {}
    token = data.get("token", "").strip()
    auto_drive = bool(data.get("auto_drive", False))

    result = git_ops.gh_auth_login(
        _project_root(),
        token=token,
        auto_drive=auto_drive,
    )

    # Cache-bust on successful token auth so status is fresh
    if result.get("ok") and result.get("authenticated"):
        try:
            from src.core.services.devops import cache as devops_cache
            root = _project_root()
            devops_cache.invalidate(root, "github")
            devops_cache.invalidate(root, "wiz:detect")
        except Exception:
            pass

    # Determine HTTP status:
    #  - 200 for success, terminal spawned, no_terminal (actionable), or fallback
    #  - 400 for actual errors (bad token, gh not installed, etc.)
    if result.get("ok") or result.get("no_terminal") or result.get("fallback"):
        status = 200
    else:
        status = 400
    return jsonify(result), status


@integrations_bp.route("/gh/auth/token")
def gh_auth_token_route():  # type: ignore[no-untyped-def]
    """Extract current auth token from gh CLI (for auto-detection)."""
    result = git_ops.gh_auth_token(_project_root())
    status = 200 if result.get("ok") else 400
    return jsonify(result), status


@integrations_bp.route("/gh/auth/device", methods=["POST"])
@run_tracked("setup", "setup:gh_device_flow")
def gh_auth_device_start_route():  # type: ignore[no-untyped-def]
    """Start a GitHub device flow — returns one-time code + URL.

    Auto-selects the implementation:
    - Normal Linux: PTY-based (drives gh auth login)
    - Android VM: HTTP-based (calls GitHub API directly)

    Always returns 200 so the frontend can inspect diagnostics.
    """
    caps = git_ops.detect_platform_capabilities()

    if caps.get("can_pty_device_flow"):
        result = git_ops.gh_auth_device_start(_project_root())
    else:
        result = git_ops.gh_auth_device_start_http()

    return jsonify(result), 200


@integrations_bp.route("/gh/auth/device/poll")
def gh_auth_device_poll_route():  # type: ignore[no-untyped-def]
    """Poll a device flow session for completion.

    Dispatches to PTY or HTTP poll based on session method.
    """
    session_id = request.args.get("session", "").strip()
    if not session_id:
        return jsonify({"error": "session parameter required"}), 400

    root = _project_root()

    # Try HTTP poll first (checks session method internally)
    result = git_ops.gh_auth_device_poll_http(session_id, root)

    # Cache-bust on successful auth — only the github card
    if result.get("complete") and result.get("authenticated"):
        try:
            from src.core.services.devops import cache as devops_cache
            devops_cache.invalidate(root, "github")
            devops_cache.invalidate(root, "wiz:detect")
        except Exception:
            pass

    return jsonify(result)


@integrations_bp.route("/gh/auth/terminal/poll")
def gh_auth_terminal_poll_route():  # type: ignore[no-untyped-def]
    """Poll signal file for terminal auth progress.

    Reads ``.state/.gh-auth-result`` written by the auto-drive bash
    script.  Returns the JSON from the file, which contains:

    - ``{"status": "running"}``  — script started
    - ``{"status": "code_ready", "code": "XXXX-XXXX", "url": "..."}``
    - ``{"status": "success"}``  — auth completed
    - ``{"status": "failed"}``   — auth failed
    """
    import json as _json

    import tempfile

    signal_file = Path(tempfile.gettempdir()) / ".gh-auth-result"

    if not signal_file.exists():
        return jsonify({"status": "unknown"})

    try:
        data = _json.loads(signal_file.read_text())

        # If success, bust cache
        if data.get("status") == "success":
            try:
                from src.core.services.devops import cache as devops_cache
                root = _project_root()
                devops_cache.invalidate(root, "github")
                devops_cache.invalidate(root, "wiz:detect")
            except Exception:
                pass
            return jsonify(data)

        # If stuck at code_ready, check live gh auth status
        if data.get("status") == "code_ready":
            gh_rc = -999
            gh_err = ""
            try:
                result = subprocess.run(
                    ["gh", "auth", "status"],
                    capture_output=True, text=True, timeout=5,
                )
                gh_rc = result.returncode
                gh_err = result.stderr[:200] if result.stderr else ""
                if gh_rc == 0:
                    # Auth succeeded! Update signal file + bust cache
                    data = {"status": "success", "ts": data.get("ts", "")}
                    signal_file.write_text(_json.dumps(data))
                    try:
                        from src.core.services.devops import cache as devops_cache
                        root = _project_root()
                        devops_cache.invalidate(root, "github")
                        devops_cache.invalidate(root, "wiz:detect")
                    except Exception:
                        pass
                    return jsonify(data)
            except Exception as exc:
                gh_err = str(exc)
            # Include debug info so we can see in network tab
            data["_debug_gh_rc"] = gh_rc
            data["_debug_gh_err"] = gh_err

        return jsonify(data)
    except Exception:
        return jsonify({"status": "unknown"})
