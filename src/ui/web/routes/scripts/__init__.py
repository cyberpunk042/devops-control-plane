"""
Scripts API routes — script discovery, execution, and history.

Blueprint: scripts_bp
Prefix: /api

Sub-modules:
    __init__.py        — blueprint definition + sub-module imports
    registry.py        — list, info, detect, templates, categories, coverage
    execution.py       — run, stream, status, adopt
    history.py         — run history endpoints
"""

from __future__ import annotations

from flask import Blueprint

scripts_bp = Blueprint("scripts", __name__, url_prefix="/api")


# ── Import sub-modules to register their routes on scripts_bp ────
# These imports MUST come after scripts_bp is defined (circular import guard).

from . import registry    # noqa: E402, F401 — registers routes
from . import execution   # noqa: E402, F401 — registers routes
from . import history     # noqa: E402, F401 — registers routes
