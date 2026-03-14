"""Security detection — status, scan, files, gitignore, posture."""

from __future__ import annotations

from flask import jsonify, request

from src.core.services.security import ops as security_ops
from src.ui.web.helpers import project_root as _project_root, get_stack_names as _get_stack_names

from . import security_bp2


@security_bp2.route("/security/status")
def security_status():  # type: ignore[no-untyped-def]
    """Combined security status — scan findings + posture score."""
    force = request.args.get("bust", "") == "1"

    from src.core.services.mediator import get_mediator
    m = get_mediator()
    result = m.get("devops.security", force=force)
    return jsonify(result["data"])


@security_bp2.route("/security/posture-summary")
def security_posture_summary():  # type: ignore[no-untyped-def]
    """Read-only: return cached security data if available, else empty.

    This endpoint NEVER triggers a scan — it only reads the server-side
    cache.  Used by the DevOps tab Security card to show a
    lightweight summary without blocking on pip-audit / secret scanning.

    Tries cache sources in order:
    1. mediator ``devops.security`` (peek, never blocks)
    2. mediator ``audit.l2_risks`` (peek, never blocks)
    """
    from src.core.services.mediator import get_mediator

    try:
        m = get_mediator()

        sec_result = m.peek("devops.security")
        if sec_result is not None:
            data = sec_result.get("data")
            if data is not None:
                return jsonify(data)

        risks_result = m.peek("audit.l2_risks")
        if risks_result is not None:
            risk_data = risks_result.get("data")
            if risk_data is not None:
                all_findings = risk_data.get("findings", [])
                sec_findings = [
                    f for f in all_findings
                    if f.get("category") in ("secrets", "security")
                ]
                if sec_findings:
                    return jsonify({
                        "findings": sec_findings,
                        "finding_count": len(sec_findings),
                        "posture": {},
                        "_source": "mediator:audit.l2_risks",
                    })
    except Exception:
        pass

    return jsonify({"empty": True})


@security_bp2.route("/security/scan")
def security_scan():  # type: ignore[no-untyped-def]
    """Scan source code for hardcoded secrets."""
    return jsonify(security_ops.scan_secrets(_project_root()))


@security_bp2.route("/security/files")
def security_files():  # type: ignore[no-untyped-def]
    """Detect sensitive files."""
    return jsonify(security_ops.detect_sensitive_files(_project_root()))


@security_bp2.route("/security/gitignore")
def security_gitignore():  # type: ignore[no-untyped-def]
    """Analyze .gitignore coverage."""
    stack_names = _get_stack_names()
    return jsonify(security_ops.gitignore_analysis(_project_root(), stack_names=stack_names))


@security_bp2.route("/security/posture")
def security_posture():  # type: ignore[no-untyped-def]
    """Unified security posture score."""
    return jsonify(security_ops.security_posture(_project_root()))
