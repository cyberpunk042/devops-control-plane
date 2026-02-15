"""
Security operations — backward-compat re-export hub.

Constants and helpers live in ``security_common``.
Scanning lives in ``security_scan``.
Posture scoring lives in ``security_posture``.
"""

from __future__ import annotations

# ── Common ──
from src.core.services.security_common import (  # noqa: F401
    _SECRET_PATTERNS,
    _SKIP_DIRS,
    _SKIP_EXTENSIONS,
    _EXPECTED_SECRET_FILES,
    _should_scan,
    _has_nosec,
    _NOSEC_RE,
    _NOSEC_STRIP_RE,
    dismiss_finding,
    undismiss_finding,
)

# ── Scanning ──
from src.core.services.security_scan import (  # noqa: F401
    scan_secrets,
    _iter_files,
    _SENSITIVE_PATTERNS,
    detect_sensitive_files,
    _is_gitignored,
    gitignore_analysis,
    generate_gitignore,
)

# ── Posture ──
from src.core.services.security_posture import (  # noqa: F401
    security_posture,
)
