"""
CDP Test routes — browser test recording, validation, and replay.

Blueprint: ``cdp_test_bp``, registered at ``/api`` prefix.

Sub-modules:
    suites.py     — Test suite CRUD endpoints
    recording.py  — Recording control endpoints (Phase 2)
    replay.py     — Replay endpoints + SSE stream (Phase 5)
"""

from __future__ import annotations

from flask import Blueprint

cdp_test_bp = Blueprint("cdp_test", __name__)

# Import sub-modules so their routes register on the blueprint.
from src.ui.web.routes.cdp_test import suites as _suites  # noqa: F401, E402
from src.ui.web.routes.cdp_test import recording as _recording  # noqa: F401, E402
