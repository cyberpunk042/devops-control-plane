"""
Secrets routes — GitHub secrets/variables management, key generation.

Blueprint: secrets_bp
Prefix: /api

Sub-modules:
    status.py  — gh status, auto-detect, environments, secrets list
    actions.py — set/remove secrets, push, create env, cleanup, seed, key generation
"""

from __future__ import annotations

from flask import Blueprint

secrets_bp = Blueprint("secrets", __name__)

from . import status, actions  # noqa: E402, F401
