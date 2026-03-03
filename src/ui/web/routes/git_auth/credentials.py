"""Git auth credentials — auth status check, SSH passphrase, HTTPS token, identity."""

from __future__ import annotations

import logging

from flask import jsonify, request

from src.core.services.git_auth import add_https_credentials, add_ssh_key, check_auth
from src.core.services.git.auth import check_git_identity, set_git_identity
from src.ui.web.helpers import project_root as _project_root

from . import git_auth_bp

logger = logging.getLogger(__name__)


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


# ── Git Identity (user.name / user.email) ───────────────────────


@git_auth_bp.route("/git/identity")
def identity_status():
    """Check if git user.name and user.email are configured.

    Returns JSON with:
        ok, name, email, needs
    """
    try:
        return jsonify(check_git_identity())
    except Exception as e:
        logger.exception("Failed to check git identity")
        return jsonify({"ok": False, "error": str(e)}), 500


@git_auth_bp.route("/git/identity", methods=["POST"])
def identity_set():
    """Set git user.name and user.email globally.

    Body (JSON):
        name  — git user.name
        email — git user.email
    """
    try:
        body = request.get_json(silent=True) or {}
        name = body.get("name", "").strip()
        email = body.get("email", "").strip()

        if not name or not email:
            return jsonify({"ok": False, "error": "Both name and email are required"}), 400

        result = set_git_identity(name, email)
        if not result.get("ok"):
            return jsonify(result), 400

        return jsonify(result)
    except Exception as e:
        logger.exception("Failed to set git identity")
        return jsonify({"ok": False, "error": str(e)}), 500

