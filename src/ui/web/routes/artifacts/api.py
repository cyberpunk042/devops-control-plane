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
        for event_json in build_target_stream(root, name):
            yield f"data: {event_json}\n\n"

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


# ── Makefile Evolution ──────────────────────────────────────────────

@bp.route("/makefile/evolution", methods=["GET"])
def makefile_evolution():
    """Analyze Makefile for operability issues and propose evolution."""
    from src.core.services.artifacts.discovery import detect_makefile_evolution

    root = _project_root()
    result = detect_makefile_evolution(root)
    return jsonify({"ok": True, **result})


@bp.route("/makefile/patch", methods=["POST"])
def makefile_patch():
    """Apply remediation patches to the Makefile.

    Request body:
      {
        "apply_remediation": true,     # Apply venv prefix changes
        "add_targets": ["build", ...]  # Add proposed targets
      }
    """
    from src.core.services.artifacts.discovery import detect_makefile_evolution

    root = _project_root()
    data = request.get_json(force=True) if request.data else {}
    apply_remediation = data.get("apply_remediation", False)
    add_targets = data.get("add_targets", [])

    makefile = root / "Makefile"
    if not makefile.exists() and not add_targets:
        return jsonify({"ok": False, "error": "No Makefile found"}), 404

    evolution = detect_makefile_evolution(root)
    changes_made = []

    try:
        if makefile.exists():
            content = makefile.read_text()
            lines = content.splitlines()
        else:
            lines = [
                ".PHONY: help " + " ".join(add_targets),
                "",
                "help: ## Show this help",
                "\t@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \\",
                "\t\tawk 'BEGIN {FS = \":.*?## \"}; {printf \"  \\033[36m%-15s\\033[0m %s\\n\", $$1, $$2}'",
                "",
            ]
            changes_made.append("Created new Makefile with help target")

        # Apply venv remediation
        if apply_remediation and evolution.get("remediation"):
            rem = evolution["remediation"]

            # Add preamble (VENV variable) if not already present
            if rem.get("preamble") and "VENV" not in "\n".join(lines):
                insert_at = rem.get("preamble_after_line", 0)
                lines.insert(insert_at + 1, "")
                lines.insert(insert_at + 1, rem["preamble"])
                changes_made.append(f"Added VENV auto-detection variable")

                # Adjust line numbers for subsequent changes (we inserted 2 lines)
                offset = 2
            else:
                offset = 0

            # Apply line changes
            for change in rem.get("changes", []):
                target_line = change["line_number"] - 1 + offset  # 0-indexed + offset
                if 0 <= target_line < len(lines):
                    lines[target_line] = change["proposed"]
                    changes_made.append(
                        f"Line {change['line_number']}: "
                        f"prefixed with $(VENV)"
                    )

        # Add new targets
        proposed_map = {p["target"]: p for p in evolution.get("proposed_additions", [])}
        for target_name in add_targets:
            if target_name not in proposed_map:
                continue
            p = proposed_map[target_name]

            # Update .PHONY line
            for i, line in enumerate(lines):
                if line.startswith(".PHONY:"):
                    if target_name not in line:
                        lines[i] = line.rstrip() + " " + target_name
                    break

            # Add target at the end
            desc = p.get("description", "")
            deps = p.get("deps", "")
            recipe = p.get("recipe", "")

            lines.append("")
            lines.append(f"{target_name}: {deps}## {desc}".rstrip())
            for recipe_line in recipe.split("\n"):
                lines.append(f"\t{recipe_line.lstrip(chr(9))}")

            changes_made.append(f"Added target: {target_name}")

        # Write the file
        makefile.write_text("\n".join(lines) + "\n")

    except OSError as e:
        return jsonify({"ok": False, "error": str(e)}), 500

    return jsonify({
        "ok": True,
        "changes": changes_made,
        "total_changes": len(changes_made),
    })


# ── Publish endpoints ──────────────────────────────────────────────

@bp.route("/publish/capabilities", methods=["GET"])
def publish_capabilities():
    """Detect available publishing tools and auth."""
    from src.core.services.artifacts.engine import detect_publish_capabilities

    root = _project_root()
    return jsonify(detect_publish_capabilities(root))


@bp.route("/<name>/publishable", methods=["GET"])
def publishable_artifacts(name: str):
    """List publishable files and available publish options for a target."""
    from src.core.services.artifacts.engine import get_publishable_artifacts

    root = _project_root()
    result = get_publishable_artifacts(root, name)
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)


@bp.route("/publish/<name>/stream", methods=["POST"])
def publish_stream(name: str):
    """Publish an artifact with SSE streaming output."""
    from src.core.services.artifacts.engine import publish_target_stream

    root = _project_root()
    data = request.get_json(force=True) if request.data else {}
    publish_target = data.get("publish_target", "github-release")
    version = data.get("version", "")
    release_notes = data.get("release_notes", "")
    tag_name = data.get("tag_name", "")

    def generate():
        for event_json in publish_target_stream(
            root, name, publish_target,
            version=version,
            release_notes=release_notes,
            tag_name=tag_name,
        ):
            yield f"data: {event_json}\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@bp.route("/<name>/release-notes", methods=["GET"])
def release_notes_preview(name: str):
    """Generate release notes preview for a target."""
    from src.core.services.artifacts.release_notes import generate_release_notes
    from src.core.services.artifacts.version import resolve_version

    root = _project_root()
    version, version_source = resolve_version(root)
    since_tag = request.args.get("since_tag")
    notes = generate_release_notes(root, version, since_tag=since_tag)

    return jsonify({
        "version": version,
        "version_source": version_source,
        "notes": notes,
    })

