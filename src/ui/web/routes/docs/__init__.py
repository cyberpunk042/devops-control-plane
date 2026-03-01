"""
Docs routes — status, coverage, links, generation.

Blueprint: docs_bp
Prefix: /api

Sub-modules:
    status.py   — docs inventory, coverage, links
    generate.py — changelog, readme generation
"""

from __future__ import annotations

from flask import Blueprint

docs_bp = Blueprint("docs", __name__)

from . import status, generate  # noqa: E402, F401
