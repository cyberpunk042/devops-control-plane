"""
Audit staging endpoints — pending snapshot lifecycle.

Routes registered on ``audit_bp`` from the parent package.

Endpoints:
    GET    /audits/pending                — list unsaved snapshots
    GET    /audits/pending/<snapshot_id>   — detail for one pending audit
    POST   /audits/save                   — save pending → ledger
    POST   /audits/discard                — discard pending
    GET    /audits/saved                  — list saved audits
    GET    /audits/saved/<snapshot_id>     — detail for one saved audit
    DELETE /audits/saved/<snapshot_id>     — delete saved audit
"""

from __future__ import annotations

from flask import jsonify, request

from src.ui.web.helpers import project_root as _project_root

from . import audit_bp


@audit_bp.route("/audits/pending")
def audits_pending():
    """List all unsaved audit snapshots (metadata only, no data blobs)."""
    from src.core.services.audit_staging import list_pending

    return jsonify({"pending": list_pending(_project_root())})


@audit_bp.route("/audits/pending/<snapshot_id>")
def audits_pending_detail(snapshot_id):
    """Full detail for a single pending audit (includes data blob)."""
    from src.core.services.audit_staging import get_pending

    result = get_pending(_project_root(), snapshot_id)
    if result is None:
        return jsonify({"error": "Not found"}), 404
    return jsonify(result)


@audit_bp.route("/audits/save", methods=["POST"])
def audits_save():
    """Save pending snapshots to the git ledger.

    Body: ``{"snapshot_ids": ["id1", "id2"]}`` or ``{"snapshot_ids": "all"}``
    """
    from src.core.services.audit_staging import save_audit, save_all_pending

    body = request.get_json(silent=True) or {}
    ids = body.get("snapshot_ids", "all")

    if ids == "all":
        saved = save_all_pending(_project_root())
    else:
        saved = []
        for sid in ids:
            try:
                save_audit(_project_root(), sid)
                saved.append(sid)
            except (ValueError, Exception):
                pass  # skip missing/failed — log is handled in audit_staging

    return jsonify({"saved": saved, "count": len(saved)})


@audit_bp.route("/audits/discard", methods=["POST"])
def audits_discard():
    """Discard pending snapshots (cache unaffected).

    Body: ``{"snapshot_ids": ["id1", "id2"]}`` or ``{"snapshot_ids": "all"}``
    """
    from src.core.services.audit_staging import discard_audit, discard_all_pending

    body = request.get_json(silent=True) or {}
    ids = body.get("snapshot_ids", "all")

    if ids == "all":
        count = discard_all_pending(_project_root())
    else:
        count = sum(1 for sid in ids if discard_audit(_project_root(), sid))

    return jsonify({"discarded": count})


@audit_bp.route("/audits/saved")
def audits_saved():
    """List saved audit snapshots from the git ledger (metadata only)."""
    from src.core.services.ledger.ledger_ops import list_saved_audits

    return jsonify({"saved": list_saved_audits(_project_root())})


@audit_bp.route("/audits/saved/<snapshot_id>")
def audits_saved_detail(snapshot_id):
    """Return the full saved audit snapshot (including data blob)."""
    from src.core.services.ledger.ledger_ops import get_saved_audit

    snap = get_saved_audit(_project_root(), snapshot_id)
    if snap is None:
        return jsonify({"error": f"Saved audit not found: {snapshot_id}"}), 404
    return jsonify(snap)


@audit_bp.route("/audits/saved/<snapshot_id>", methods=["DELETE"])
def audits_saved_delete(snapshot_id):
    """Delete a saved audit snapshot from the ledger branch."""
    from src.core.services.ledger.ledger_ops import delete_saved_audit

    try:
        deleted = delete_saved_audit(_project_root(), snapshot_id)
        if not deleted:
            return jsonify({"error": f"Saved audit not found: {snapshot_id}"}), 404
        return jsonify({"deleted": snapshot_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
