"""
Audit API routes — serve analysis data for the Audit tab.

Blueprint: audit_bp
Prefix: /api

This module was split from the monolithic ``routes_audit.py`` (1,781 lines)
into focused sub-modules:

    __init__.py           — blueprint definition + sub-module imports
    analysis.py           — L0/L1/L2 audit data endpoints (11 endpoints)
    staging.py            — audit snapshot lifecycle (7 endpoints)
    tool_install.py       — install, resolve, check, version (10 endpoints)
    tool_execution.py     — plan execution SSE, resume, cancel (6 endpoints)
    deep_detection.py     — deep system detection (1 endpoint)
    offline_cache.py      — offline cache, data packs, service status (7 endpoints)
"""

from __future__ import annotations

from flask import Blueprint

audit_bp = Blueprint("audit", __name__, url_prefix="/api")


# ── Import sub-modules to register their routes on audit_bp ──────
# These imports MUST come after audit_bp is defined (circular import guard).

from . import analysis          # noqa: E402, F401 — registers routes
from . import staging           # noqa: E402, F401 — registers routes
from . import tool_install      # noqa: E402, F401 — registers routes
from . import tool_execution    # noqa: E402, F401 — registers routes
from . import deep_detection    # noqa: E402, F401 — registers routes
from . import offline_cache     # noqa: E402, F401 — registers routes
from . import async_scan        # noqa: E402, F401 — registers routes
