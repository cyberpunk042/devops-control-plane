"""
Git authentication routes — auth status, SSH, HTTPS.

Blueprint: git_auth_bp
Prefix: /api

Sub-modules:
    helpers.py     — requires_git_auth decorator
    credentials.py — auth status, SSH passphrase, HTTPS token
"""

from __future__ import annotations

from flask import Blueprint

git_auth_bp = Blueprint("git_auth", __name__)

from . import helpers, credentials  # noqa: E402, F401
