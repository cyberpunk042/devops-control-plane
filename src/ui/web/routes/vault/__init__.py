"""
Vault routes — secrets management, encryption, .env key operations.

Blueprint: vault_bp
Prefix: /api

Sub-modules:
    helpers.py   — shared utilities (_env_path)
    status.py    — vault status, secret file detection
    security.py  — lock, unlock, register passphrase, auto-lock
    keys.py      — CRUD on .env keys (list, add, update, delete, move, raw-value, etc.)
    env_mgmt.py  — active environment, templates, create .env
    transfer.py  — export / import encrypted vault files
"""

from __future__ import annotations

from flask import Blueprint

vault_bp = Blueprint("vault", __name__)

from . import status, security, keys, env_mgmt, transfer  # noqa: E402, F401
