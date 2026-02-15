"""
DevOps audit — finding dismissal endpoints.

Blueprint: devops_bp (imported from routes_devops)
Prefix: /api

Thin HTTP wrappers over ``src.core.services.security_common``.

Endpoints:
    POST   /devops/audit/dismissals — dismiss finding(s)
    DELETE /devops/audit/dismissals — undismiss a finding
"""

from __future__ import annotations

from pathlib import Path

from flask import current_app, jsonify, request

from src.ui.web.routes_devops import devops_bp


def _project_root() -> Path:
    return current_app.config["PROJECT_ROOT"]


@devops_bp.route("/devops/audit/dismissals", methods=["POST"])
def audit_dismissals_add():  # type: ignore[no-untyped-def]
    """Dismiss finding(s) by writing # nosec to the source line(s).

    Body (batch):  {"items": [{"file": "...", "line": N}, ...], "comment": "reason"}
    Body (single): {"file": "path/to/file.py", "line": 42, "comment": "reason"}
    """
    from src.core.services.security_ops import batch_dismiss_findings

    data = request.get_json(silent=True) or {}
    comment = data.get("comment", "")

    # Build list of items — batch or single
    items = data.get("items")
    if not items:
        file = data.get("file", "")
        line = data.get("line", 0)
        if not file or not line:
            return jsonify({"ok": False, "error": "file and line are required"}), 400
        items = [{"file": file, "line": line}]

    result = batch_dismiss_findings(_project_root(), items, comment)
    return jsonify(result)


@devops_bp.route("/devops/audit/dismissals", methods=["DELETE"])
def audit_dismissals_remove():  # type: ignore[no-untyped-def]
    """Undismiss a finding by removing # nosec from the source line.

    Body: {"file": "path/to/file.py", "line": 42}
    """
    from src.core.services.security_ops import undismiss_finding_audited

    data = request.get_json(silent=True) or {}
    file = data.get("file", "")
    line = data.get("line", 0)

    if not file or not line:
        return jsonify({"ok": False, "error": "file and line are required"}), 400

    result = undismiss_finding_audited(_project_root(), file, int(line))

    if not result.get("ok"):
        return jsonify(result), 400
    return jsonify(result)
