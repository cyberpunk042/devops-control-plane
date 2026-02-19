"""
Git authentication API routes.

Blueprint: git_auth_bp
Prefix: /api (applied by server.py)

Endpoints:
    /api/git/auth-status  — check if git auth is working
    /api/git/auth-ssh     — provide SSH key passphrase
    /api/git/auth-https   — provide HTTPS token/credentials
"""

from __future__ import annotations

import logging
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

from src.core.services.git_auth import (
    add_https_credentials,
    add_ssh_key,
    check_auth,
)

logger = logging.getLogger(__name__)

git_auth_bp = Blueprint("git_auth", __name__)


def _project_root() -> Path:
    return Path(current_app.config.get("PROJECT_ROOT", ".")).resolve()


# ── Auth status check ─────────────────────────────────────────────

@git_auth_bp.route("/git/auth-status")
def auth_status():
    """Check if git network auth is working.

    Returns JSON with:
        ok, remote_type, remote_url, ssh_key, needs, error
    """
    try:
        root = _project_root()
        result = check_auth(root)
        return jsonify(result)
    except Exception as e:
        logger.exception("Failed to check git auth")
        return jsonify({"ok": False, "error": str(e)}), 500


# ── SSH passphrase ────────────────────────────────────────────────

@git_auth_bp.route("/git/auth-ssh", methods=["POST"])
def auth_ssh():
    """Provide SSH key passphrase.

    Body (JSON):
        passphrase — the SSH key passphrase
    """
    try:
        root = _project_root()
        body = request.get_json(silent=True) or {}
        passphrase = body.get("passphrase", "")

        if not passphrase:
            return jsonify({"ok": False, "error": "Passphrase is required"}), 400

        result = add_ssh_key(root, passphrase)

        # If successful, verify it actually works end-to-end
        if result.get("ok"):
            verify = check_auth(root)
            if not verify.get("ok"):
                result = {"ok": False, "error": "Key added but auth still failing: " + (verify.get("error") or "")}

        return jsonify(result)
    except Exception as e:
        logger.exception("Failed to add SSH key")
        return jsonify({"ok": False, "error": str(e)}), 500


# ── HTTPS credentials ────────────────────────────────────────────

@git_auth_bp.route("/git/auth-https", methods=["POST"])
def auth_https():
    """Provide HTTPS token/credentials.

    Body (JSON):
        token — GitHub PAT or other access token
    """
    try:
        root = _project_root()
        body = request.get_json(silent=True) or {}
        token = body.get("token", "")

        if not token:
            return jsonify({"ok": False, "error": "Token is required"}), 400

        result = add_https_credentials(root, token)

        # If successful, verify it actually works
        if result.get("ok"):
            verify = check_auth(root)
            if not verify.get("ok"):
                result = {"ok": False, "error": "Credentials stored but auth still failing: " + (verify.get("error") or "")}

        return jsonify(result)
    except Exception as e:
        logger.exception("Failed to store HTTPS credentials")
        return jsonify({"ok": False, "error": str(e)}), 500
