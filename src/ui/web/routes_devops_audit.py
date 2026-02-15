"""
DevOps audit — finding dismissal endpoints.

Split from routes_devops.py for maintainability.
"""

from __future__ import annotations

from flask import current_app, jsonify, request

from src.core.services import devops_cache
from src.ui.web.routes_devops import devops_bp


def _project_root() -> Path:
    return current_app.config["PROJECT_ROOT"]


# ── Audit finding dismissals ────────────────────────────────────
# Dismiss = write ``# nosec: <reason>`` to the source line.
# The scanner respects # nosec and skips the line on next scan.

@devops_bp.route("/devops/audit/dismissals", methods=["POST"])
def audit_dismissals_add():
    """Dismiss finding(s) by writing # nosec to the source line(s).

    Body (batch):  {"items": [{"file": "...", "line": N}, ...], "comment": "reason"}
    Body (single): {"file": "path/to/file.py", "line": 42, "comment": "reason"}
    """
    from src.core.services.security_ops import dismiss_finding

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

    root = _project_root()
    results = []
    errors = []
    for item in items:
        r = dismiss_finding(root, item["file"], int(item["line"]), comment)
        results.append(r)
        if not r.get("ok"):
            errors.append(r)

    # Bust server cache once after all writes
    devops_cache.invalidate(root, "audit:l2:risks")
    devops_cache.invalidate(root, "security")

    # Log to audit activity so it shows in Debugging → Audit Log
    ok_items = [r for r in results if r.get("ok") and not r.get("already")]
    if ok_items:
        files_str = ", ".join(f"{r['file']}:{r['line']}" for r in ok_items)
        devops_cache.record_event(
            root,
            label="🚫 Finding Dismissed",
            summary=f"# nosec added to {len(ok_items)} line(s): {files_str}"
                    + (f" — {comment}" if comment else ""),
            detail={"items": ok_items, "comment": comment},
            card="dismissal",
        )

    return jsonify({"ok": len(errors) == 0, "count": len(results), "results": results})


@devops_bp.route("/devops/audit/dismissals", methods=["DELETE"])
def audit_dismissals_remove():
    """Undismiss a finding by removing # nosec from the source line.

    Body: {"file": "path/to/file.py", "line": 42}
    """
    from src.core.services.security_ops import undismiss_finding

    data = request.get_json(silent=True) or {}
    file = data.get("file", "")
    line = data.get("line", 0)

    if not file or not line:
        return jsonify({"ok": False, "error": "file and line are required"}), 400

    result = undismiss_finding(_project_root(), file, int(line))

    if not result.get("ok"):
        return jsonify(result), 400

    root = _project_root()
    devops_cache.invalidate(root, "audit:l2:risks")
    devops_cache.invalidate(root, "security")

    # Log the restore action
    if not result.get("already"):
        devops_cache.record_event(
            root,
            label="↩️ Finding Restored",
            summary=f"# nosec removed from {file}:{line}",
            detail={"file": file, "line": line},
            card="dismissal",
        )

    return jsonify(result)

