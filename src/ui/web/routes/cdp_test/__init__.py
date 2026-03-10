
"""
CDP Test routes — browser test recording, validation, and replay.

Blueprint: ``cdp_test_bp``, registered at ``/api`` prefix.

Sub-modules:
    suites.py     — Test suite CRUD endpoints
    recording.py  — Recording control endpoints (Phase 2)
    replay.py     — Replay endpoints + SSE stream (Phase 5)
"""

from __future__ import annotations

from flask import Blueprint, request

cdp_test_bp = Blueprint("cdp_test", __name__)


# ── CORS for recorded-page event callbacks ────────────────────
# The recorder JS runs in foreign pages (e.g. github.io) and sends
# events to localhost via fetch/sendBeacon. Chrome requires CORS +
# Private Network Access headers on EVERY response (including the
# auto-generated OPTIONS preflight). A blueprint after_request hook
# is the only reliable way to catch all response paths.

@cdp_test_bp.after_request
def _cors_for_record_event(response):
    """Add CORS headers to /cdp-test/record/event responses."""
    if request.path.endswith("/cdp-test/record/event"):
        # Recorder JS uses fetch with credentials:'omit', so wildcard is fine.
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Allow-Private-Network"] = "true"
    return response


# Import sub-modules so their routes register on the blueprint.
from src.ui.web.routes.cdp_test import suites as _suites  # noqa: F401, E402
from src.ui.web.routes.cdp_test import recording as _recording  # noqa: F401, E402
from src.ui.web.routes.cdp_test import replay as _replay  # noqa: F401, E402
from src.ui.web.routes.cdp_test import browser as _browser  # noqa: F401, E402
from src.ui.web.routes.cdp_test import io as _io  # noqa: F401, E402
