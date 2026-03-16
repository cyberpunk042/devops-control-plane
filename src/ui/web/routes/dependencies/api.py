"""
Dependency management API routes.

Read endpoints use the mediator (cached).
Write endpoints use the pipeline (streaming or synchronous).

Routes::

    GET  /dependencies/tree          — Full dependency tree
    GET  /dependencies/summary       — Dashboard card counts
    GET  /dependencies/snapshots     — Rollback snapshot list

    POST /dependencies/install/stream  — SSE: install at scope
    POST /dependencies/update/stream   — SSE: update at scope
    POST /dependencies/rollback/stream — SSE: rollback to snapshot

    POST /dependencies/install         — Synchronous install
    POST /dependencies/update          — Synchronous update
    POST /dependencies/rollback        — Synchronous rollback

    POST   /dependencies/note          — Add/update note
    DELETE /dependencies/note          — Remove note
"""

from __future__ import annotations

import json

from flask import Response, jsonify, request

from src.core.services.events.tracked import tracked
from src.ui.web.helpers import project_root as _project_root

from . import dep_bp


# ═════════════════════════════════════════════════════════════════
#  Read endpoints (mediator-backed)
# ═════════════════════════════════════════════════════════════════


@dep_bp.route("/dependencies/tree")
def dep_tree():
    """Full dependency tree (cached via mediator)."""
    force = request.args.get("bust", "") == "1"

    from src.core.services.mediator import get_mediator
    m = get_mediator()
    result = m.get("dependency.tree", force=force)
    return jsonify(result["data"])


@dep_bp.route("/dependencies/summary")
def dep_summary():
    """Dashboard card summary counts."""
    force = request.args.get("bust", "") == "1"

    from src.core.services.mediator import get_mediator
    m = get_mediator()
    result = m.get("dependency.summary", force=force)
    return jsonify(result["data"])


@dep_bp.route("/dependencies/snapshots")
def dep_snapshots():
    """List rollback snapshots."""
    from src.core.services.dependency_mgr.state import list_snapshots

    snaps = list_snapshots(_project_root())
    return jsonify({"snapshots": [s.to_dict() for s in snaps]})


# ═════════════════════════════════════════════════════════════════
#  Write endpoints — SSE streaming
# ═════════════════════════════════════════════════════════════════


def _get_registry():
    from src.core.services.dependency_mgr import get_registry
    return get_registry()


def _stream_operation(action):
    """Shared SSE streaming handler for install/update/rollback."""
    from src.core.services.dependency_mgr.pipeline import run_operation

    body = request.get_json(silent=True) or {}
    scope = body.get("scope", "")
    if not scope:
        return jsonify({"error": "scope is required"}), 400

    root = _project_root()
    registry = _get_registry()

    def sse():
        for event in run_operation(
            root, scope, action,
            registry=registry,
            packages=body.get("packages"),
            dev=body.get("dev", False),
            frozen=body.get("frozen", True),
            snapshot_id=body.get("snapshot_id"),
            correlation_id=body.get("correlation_id"),
        ):
            yield f"data: {json.dumps(event.to_dict())}\n\n"

    return Response(sse(), mimetype="text/event-stream")


@dep_bp.route("/dependencies/install/stream", methods=["POST"])
@tracked("dependency.install.started")
def dep_install_stream():
    """SSE stream: install dependencies at scope."""
    return _stream_operation("install")


@dep_bp.route("/dependencies/update/stream", methods=["POST"])
@tracked("dependency.update.started")
def dep_update_stream():
    """SSE stream: update dependencies at scope."""
    return _stream_operation("update")


@dep_bp.route("/dependencies/rollback/stream", methods=["POST"])
@tracked("dependency.rollback.started")
def dep_rollback_stream():
    """SSE stream: rollback to a snapshot."""
    return _stream_operation("rollback")


# ═════════════════════════════════════════════════════════════════
#  Write endpoints — synchronous
# ═════════════════════════════════════════════════════════════════


def _sync_operation(action):
    """Shared synchronous handler — collects all events, returns summary."""
    from src.core.services.dependency_mgr.pipeline import run_operation

    body = request.get_json(silent=True) or {}
    scope = body.get("scope", "")
    if not scope:
        return jsonify({"error": "scope is required"}), 400

    root = _project_root()
    registry = _get_registry()

    events = list(run_operation(
        root, scope, action,
        registry=registry,
        packages=body.get("packages"),
        dev=body.get("dev", False),
        frozen=body.get("frozen", True),
        snapshot_id=body.get("snapshot_id"),
        correlation_id=body.get("correlation_id"),
    ))

    # Find the done event
    done = next((e for e in reversed(events) if e.type in
                 ("operation_done", "rollback_done", "error")), None)

    if done is None:
        return jsonify({"ok": False, "error": "No completion event"}), 500

    if done.type == "error":
        return jsonify({"ok": False, "error": done.message}), 400

    ok = done.status == "ok"
    result = {
        "ok": ok,
        "scope": scope,
        "action": action,
        "count": done.count,
        "duration_ms": done.duration_ms,
        "warnings": done.detail.get("warnings", 0),
        "errors": done.detail.get("errors", 0),
    }
    if not ok:
        result["error"] = done.message

    return jsonify(result), 200 if ok else 400


@dep_bp.route("/dependencies/install", methods=["POST"])
@tracked("dependency.install.started")
def dep_install():
    """Synchronous install at scope."""
    return _sync_operation("install")


@dep_bp.route("/dependencies/update", methods=["POST"])
@tracked("dependency.update.started")
def dep_update():
    """Synchronous update at scope."""
    return _sync_operation("update")


@dep_bp.route("/dependencies/rollback", methods=["POST"])
@tracked("dependency.rollback.started")
def dep_rollback():
    """Synchronous rollback to a snapshot."""
    return _sync_operation("rollback")


# ═════════════════════════════════════════════════════════════════
#  Notes
# ═════════════════════════════════════════════════════════════════


@dep_bp.route("/dependencies/note", methods=["POST"])
@tracked("dependency.note.added")
def dep_note_add():
    """Add or update a note on a package version."""
    from src.core.services.dependency_mgr.state import set_note

    body = request.get_json(silent=True) or {}
    ecosystem = body.get("ecosystem", "").strip()
    package = body.get("package", "").strip()
    version = body.get("version", "").strip()
    note = body.get("note", "").strip()

    if not all([ecosystem, package, version, note]):
        return jsonify({"error": "ecosystem, package, version, and note are required"}), 400

    set_note(
        _project_root(),
        ecosystem, package, version, note,
        dismiss_until=body.get("dismiss_until"),
    )
    return jsonify({"ok": True})


@dep_bp.route("/dependencies/note", methods=["DELETE"])
@tracked("dependency.note.removed")
def dep_note_remove():
    """Remove a note from a package version."""
    from src.core.services.dependency_mgr.state import remove_note

    body = request.get_json(silent=True) or {}
    ecosystem = body.get("ecosystem", "").strip()
    package = body.get("package", "").strip()
    version = body.get("version", "").strip()

    if not all([ecosystem, package, version]):
        return jsonify({"error": "ecosystem, package, and version are required"}), 400

    existed = remove_note(_project_root(), ecosystem, package, version)
    return jsonify({"ok": True, "existed": existed})
