"""
Security operations — backward-compat re-export hub.

Constants and helpers live in ``security.common``.
Scanning lives in ``security.scan``.
Posture scoring lives in ``security.posture``.
"""

from __future__ import annotations

# ── Common ──
from .common import (  # noqa: F401
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
    batch_dismiss_findings,
    undismiss_finding_audited,
)

# ── Scanning ──
from .scan import (  # noqa: F401
    scan_secrets,
    _iter_files,
    _sensitive_patterns,
    detect_sensitive_files,
    _is_gitignored,
    gitignore_analysis,
    generate_gitignore,
)

# ── Posture ──
from .posture import (  # noqa: F401
    security_posture,
)
