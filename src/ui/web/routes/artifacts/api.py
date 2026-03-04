"""
Artifacts API — target CRUD and build operations.

Routes:
  GET  /api/artifacts/targets           — list all targets
  POST /api/artifacts/targets           — add a target
  PUT  /api/artifacts/targets/<name>    — update a target
  DEL  /api/artifacts/targets/<name>    — remove a target
  GET  /api/artifacts/targets/<name>/status — build status
  POST /api/artifacts/build/<name>/stream  — SSE build stream
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from flask import Response, jsonify, request

from . import bp
from src.core.services.artifacts.engine import (
    ArtifactTarget,
    add_target,
    build_target_stream,
    get_build_status,
    get_target,
    get_targets,
    remove_target,
    update_target,
)


def _project_root() -> Path:
    """Get project root from Flask app config or cwd."""
    from flask import current_app
    return Path(current_app.config.get("PROJECT_ROOT", ".")).resolve()


# ── List targets ────────────────────────────────────────────────────

@bp.route("/targets", methods=["GET"])
def list_targets():
    """List all artifact targets with build status."""
    root = _project_root()
    targets = get_targets(root)

    result = []
    for t in targets:
        entry = asdict(t)
        build = get_build_status(root, t.name)
        entry["build"] = build
        result.append(entry)

    return jsonify({"targets": result})


# ── Add target ──────────────────────────────────────────────────────

@bp.route("/targets", methods=["POST"])
def create_target():
    """Add a new artifact target."""
    data = request.get_json(force=True)
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"ok": False, "error": "Target name is required"}), 400

    root = _project_root()

    target = ArtifactTarget(
        name=name,
        kind=data.get("kind", "local"),
        builder=data.get("builder", "makefile"),
        description=data.get("description", ""),
        build_target=data.get("build_target", ""),
        build_cmd=data.get("build_cmd", ""),
        output_dir=data.get("output_dir", "dist/"),
        modules=data.get("modules", []),
        config=data.get("config", {}),
    )

    try:
        add_target(root, target)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 409

    return jsonify({"ok": True, "target": asdict(target)})


# ── Update target ───────────────────────────────────────────────────

@bp.route("/targets/<name>", methods=["PUT"])
def modify_target(name: str):
    """Update an existing artifact target."""
    data = request.get_json(force=True)
    root = _project_root()

    try:
        update_target(root, name, data)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 404

    updated = get_target(root, name)
    return jsonify({"ok": True, "target": asdict(updated) if updated else {}})


# ── Remove target ───────────────────────────────────────────────────

@bp.route("/targets/<name>", methods=["DELETE"])
def delete_target(name: str):
    """Remove an artifact target."""
    root = _project_root()

    try:
        remove_target(root, name)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 404

    return jsonify({"ok": True, "removed": name})


# ── Build status ────────────────────────────────────────────────────

@bp.route("/targets/<name>/status", methods=["GET"])
def target_build_status(name: str):
    """Get the last build status for a target."""
    root = _project_root()
    target = get_target(root, name)
    if not target:
        return jsonify({"ok": False, "error": f"Target '{name}' not found"}), 404

    build = get_build_status(root, name)
    return jsonify({"ok": True, "target": name, "build": build})


# ── Build stream (SSE) ──────────────────────────────────────────────

@bp.route("/build/<name>/stream", methods=["POST"])
def build_stream(name: str):
    """Build an artifact target with SSE streaming output."""
    root = _project_root()
    target = get_target(root, name)
    if not target:
        return jsonify({"ok": False, "error": f"Target '{name}' not found"}), 404

    def generate():
        for line in build_target_stream(root, name):
            yield f"data: {line}\n\n"
        yield "data: __done__\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── Discovery ───────────────────────────────────────────────────────

@bp.route("/detect", methods=["POST"])
def detect_targets():
    """Auto-detect buildable artifact targets from project structure."""
    from src.core.services.artifacts.discovery import detect_artifact_targets

    data = request.get_json(force=True) if request.data else {}
    project_path = data.get("project_path", "")

    if project_path:
        root = Path(project_path).resolve()
    else:
        root = _project_root()

    if not root.exists():
        return jsonify({"ok": False, "error": f"Path not found: {root}"}), 404

    candidates = detect_artifact_targets(root)

    # Mark which candidates are already configured
    existing = {t.name for t in get_targets(root)}
    for c in candidates:
        c["already_configured"] = c["name"] in existing

    return jsonify({
        "ok": True,
        "candidates": candidates,
        "project_root": str(root),
        "total": len(candidates),
    })


# ── Builders ────────────────────────────────────────────────────────

@bp.route("/builders", methods=["GET"])
def list_builders():
    """List available artifact builders."""
    from src.core.services.artifacts.builders import get_builder

    known = ["makefile", "pip", "script", "docker"]
    result = []
    for name in known:
        b = get_builder(name)
        result.append({
            "name": name,
            "label": b.label() if b else name,
            "available": b is not None,
        })
    return jsonify({"builders": result})
