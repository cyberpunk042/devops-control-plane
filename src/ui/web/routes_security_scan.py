"""
Security routes — secret scanning, sensitive files, posture endpoints.

Blueprint: security_bp2
Prefix: /api

Thin HTTP wrappers over ``src.core.services.security_ops``.

Note: Named ``security_bp2`` to avoid conflict with the existing
``secrets_bp`` in routes_secrets.py (which handles GitHub secrets
management). This blueprint handles code security analysis.

Endpoints:
    GET  /security/scan            — scan for hardcoded secrets
    GET  /security/files           — detect sensitive files
    GET  /security/gitignore       — analyze .gitignore coverage
    GET  /security/posture         — unified security score
    POST /security/generate/gitignore — generate .gitignore
"""

from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

from src.core.services import security_ops

security_bp2 = Blueprint("security2", __name__)


def _project_root() -> Path:
    return Path(current_app.config["PROJECT_ROOT"])


def _get_stack_names() -> list[str]:
    """Auto-detect unique stack names."""
    try:
        from src.core.config.loader import load_project
        from src.core.config.stack_loader import discover_stacks
        from src.core.services.detection import detect_modules

        root = _project_root()
        project = load_project(root / "project.yml")
        stacks = discover_stacks(root / "stacks")
        detection = detect_modules(project, root, stacks)
        return list({m.effective_stack for m in detection.modules if m.effective_stack})
    except Exception:
        return []


# ── Combined status (for dashboard) ────────────────────────────────


@security_bp2.route("/security/status")
def security_status():  # type: ignore[no-untyped-def]
    """Combined security status — scan findings + posture score."""
    from src.core.services.devops_cache import get_cached

    root = _project_root()
    force = request.args.get("bust", "") == "1"

    def _compute() -> dict:
        scan = security_ops.scan_secrets(root)
        posture = security_ops.security_posture(root)
        return {
            "findings": scan.get("findings", []),
            "finding_count": scan.get("count", 0),
            "posture": posture,
        }

    return jsonify(get_cached(root, "security", _compute, force=force))


@security_bp2.route("/security/posture-summary")
def security_posture_summary():  # type: ignore[no-untyped-def]
    """Read-only: return cached security data if available, else empty.

    This endpoint NEVER triggers a scan — it only reads the server-side
    devops_cache.  Used by the DevOps tab Security card to show a
    lightweight summary without blocking on pip-audit / secret scanning.

    Tries two cache sources in order:
    1. ``security`` — from a previous /security/status call
    2. ``audit:l2:risks`` — from the Audit tab's Risks card
    """
    from src.core.services.devops_cache import _load_cache

    root = _project_root()
    cache = _load_cache(root)

    # 1. Try direct security cache
    sec_entry = cache.get("security")
    if sec_entry and "data" in sec_entry:
        return jsonify(sec_entry["data"])

    # 2. Fallback: extract from audit risks cache
    risks_entry = cache.get("audit:l2:risks")
    if risks_entry and "data" in risks_entry:
        risk_data = risks_entry["data"]
        all_findings = risk_data.get("findings", [])
        sec_findings = [
            f for f in all_findings
            if f.get("category") in ("secrets", "security")
        ]
        # Only use this fallback if we actually have findings to show.
        # Returning posture:{} causes the card to render with score=0/grade=?
        # which is misleading — better to show the "not yet loaded" state.
        if sec_findings:
            return jsonify({
                "findings": sec_findings,
                "finding_count": len(sec_findings),
                "posture": {},  # No posture from audit cache
                "_source": "audit:l2:risks",
            })

    return jsonify({"empty": True})


# ── Detect ──────────────────────────────────────────────────────────


@security_bp2.route("/security/scan")
def security_scan():  # type: ignore[no-untyped-def]
    """Scan source code for hardcoded secrets."""
    return jsonify(security_ops.scan_secrets(_project_root()))


@security_bp2.route("/security/files")
def security_files():  # type: ignore[no-untyped-def]
    """Detect sensitive files."""
    return jsonify(security_ops.detect_sensitive_files(_project_root()))


# ── Observe ─────────────────────────────────────────────────────────


@security_bp2.route("/security/gitignore")
def security_gitignore():  # type: ignore[no-untyped-def]
    """Analyze .gitignore coverage."""
    stack_names = _get_stack_names()
    return jsonify(security_ops.gitignore_analysis(_project_root(), stack_names=stack_names))


@security_bp2.route("/security/posture")
def security_posture():  # type: ignore[no-untyped-def]
    """Unified security posture score."""
    return jsonify(security_ops.security_posture(_project_root()))


# ── Facilitate ──────────────────────────────────────────────────────


@security_bp2.route("/security/generate/gitignore", methods=["POST"])
def security_generate_gitignore():  # type: ignore[no-untyped-def]
    """Generate .gitignore from detected stacks."""
    data = request.get_json(silent=True) or {}
    stack_names = data.get("stacks") or _get_stack_names()

    result = security_ops.generate_gitignore(_project_root(), stack_names)

    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)
