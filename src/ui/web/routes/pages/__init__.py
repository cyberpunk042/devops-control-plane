"""
Pages routes — dashboard HTML + Pages API.

Two separate blueprints:
    pages_bp     — dashboard + built site serving (no url_prefix)
    pages_api_bp — pages API endpoints (url_prefix /api)
"""

from __future__ import annotations

# Import and re-export both blueprints
from .serving import pages_bp        # noqa: F401
from .api import pages_api_bp        # noqa: F401
