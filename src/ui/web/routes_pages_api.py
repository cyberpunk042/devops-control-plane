"""
Pages API routes — segment CRUD, build, deploy.

Blueprint: pages_api_bp
Prefix: /api

Endpoints:
    GET  /pages/segments         — list all segments
    POST /pages/segments         — add a new segment
    PUT  /pages/segments/<name>  — update segment config
    DEL  /pages/segments/<name>  — remove a segment
    GET  /pages/meta             — get pages metadata
    POST /pages/meta             — update pages metadata
    GET  /pages/builders         — list available builders
    GET  /pages/features         — list builder features
    GET  /pages/resolve-file     — resolve file path to segments
    POST /pages/builders/<n>/install — install a builder (SSE)
    POST /pages/build/<name>     — build a segment
    GET  /pages/build-status/<n> — build status
    POST /pages/build-all        — build all segments
    POST /pages/merge            — merge outputs
    POST /pages/deploy           — deploy to gh-pages
    POST /pages/init             — auto-init from project.yml
    POST /pages/preview/<name>   — start preview
    DEL  /pages/preview/<name>   — stop preview
    GET  /pages/previews         — list previews
    POST /pages/ci               — generate CI workflow
    POST /pages/build-stream/<n> — build with SSE streaming

Thin HTTP wrappers over ``src.core.services.pages_engine``.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from flask import Blueprint, Response, current_app, jsonify, request

from src.core.services.pages_engine import (
    # Segment CRUD
    get_segments as _get_segments,
    add_segment,
    update_segment,
    remove_segment,
    # Metadata
    get_pages_meta,
    set_pages_meta,
    # Build
    build_segment,
    get_build_status,
    # Merge + Deploy
    merge_segments,
    deploy_to_ghpages,
    # Preview
    start_preview,
    stop_preview,
    list_previews,
    # CI
    generate_ci_workflow,
    # Builder / feature listing
    list_builders_detail,
    list_feature_categories,
    # File resolution
    resolve_file_to_segments,
    # Auto-init
    init_pages_from_project,
    # Install streaming
    install_builder_stream,
    install_builder_events,
    # Build streaming
    build_segment_stream,
)
from src.core.services.pages_builders import SegmentConfig
from src.core.services.run_tracker import run_tracked

logger = logging.getLogger(__name__)

pages_api_bp = Blueprint("pages_api", __name__)


def _project_root() -> Path:
    return Path(current_app.config["PROJECT_ROOT"])


# ── Segments CRUD ───────────────────────────────────────────────────


@pages_api_bp.route("/pages/segments")
def list_segments():  # type: ignore[no-untyped-def]
    """List all configured segments."""
    from src.core.services.devops_cache import get_cached

    root = _project_root()
    force = request.args.get("bust", "") == "1"

    def _compute() -> dict:
        segments = _get_segments(root)
        return {
            "segments": [
                {
                    "name": s.name,
                    "source": s.source,
                    "builder": s.builder,
                    "path": s.path,
                    "auto": s.auto,
                    "config": s.config,
                    "build_status": get_build_status(root, s.name),
                }
                for s in segments
            ]
        }

    return jsonify(get_cached(root, "pages", _compute, force=force))


@pages_api_bp.route("/pages/segments", methods=["POST"])
def create_segment():  # type: ignore[no-untyped-def]
    """Add a new segment."""
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "Segment name is required"}), 400

    seg = SegmentConfig(
        name=name,
        source=data.get("source", name),
        builder=data.get("builder", "raw"),
        path=data.get("path", f"/{name}"),
        auto=data.get("auto", False),
        config=data.get("config", {}),
    )

    try:
        add_segment(_project_root(), seg)
    except ValueError as e:
        return jsonify({"error": str(e)}), 409

    return jsonify({"ok": True, "segment": name})


@pages_api_bp.route("/pages/segments/<name>", methods=["PUT"])
def update_segment_route(name: str):  # type: ignore[no-untyped-def]
    """Update segment config."""
    data = request.get_json(silent=True) or {}
    try:
        update_segment(_project_root(), name, data)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    return jsonify({"ok": True})


@pages_api_bp.route("/pages/segments/<name>", methods=["DELETE"])
def delete_segment_route(name: str):  # type: ignore[no-untyped-def]
    """Remove a segment."""
    remove_segment(_project_root(), name)
    return jsonify({"ok": True})


# ── Pages metadata ──────────────────────────────────────────────────


@pages_api_bp.route("/pages/meta")
def get_meta():  # type: ignore[no-untyped-def]
    """Get top-level pages config."""
    return jsonify(get_pages_meta(_project_root()))


@pages_api_bp.route("/pages/meta", methods=["POST"])
def set_meta():  # type: ignore[no-untyped-def]
    """Update pages metadata."""
    data = request.get_json(silent=True) or {}
    set_pages_meta(_project_root(), data)
    return jsonify({"ok": True})


# ── Builders ────────────────────────────────────────────────────────


@pages_api_bp.route("/pages/builders")
def list_builders_route():  # type: ignore[no-untyped-def]
    """List available page builders with pipeline stage info."""
    return jsonify({"builders": list_builders_detail()})


@pages_api_bp.route("/pages/resolve-file")
def resolve_file_to_pages():  # type: ignore[no-untyped-def]
    """Resolve a content vault file path to Pages preview URLs."""
    file_path = request.args.get("path", "").strip()
    return jsonify({"matches": resolve_file_to_segments(_project_root(), file_path)})


@pages_api_bp.route("/pages/features")
def list_features_route():  # type: ignore[no-untyped-def]
    """List available builder features for the configuration wizard."""
    return jsonify({"categories": list_feature_categories()})


@pages_api_bp.route("/pages/builders/<name>/install", methods=["POST"])
def install_builder_route(name: str):  # type: ignore[no-untyped-def]
    """Install a builder's dependencies (SSE stream)."""
    preflight = install_builder_stream(name)
    if preflight is not None:
        # Quick response — already installed, not found, or no install cmd
        status = 404 if "error" in preflight and "not found" in preflight["error"] else (
            400 if "error" in preflight else 200
        )
        return jsonify(preflight), status

    # Stream installation events
    def sse():  # type: ignore[no-untyped-def]
        for event in install_builder_events(name):
            yield f"data: {json.dumps(event)}\n\n"

    return Response(sse(), mimetype="text/event-stream")


# ── Build ───────────────────────────────────────────────────────────


@pages_api_bp.route("/pages/build/<name>", methods=["POST"])
@run_tracked("build", "build:pages_segment")
def build_segment_route(name: str):  # type: ignore[no-untyped-def]
    """Build a single segment."""
    result = build_segment(_project_root(), name)
    resp = {
        "ok": result.ok,
        "segment": result.segment,
        "duration_ms": result.duration_ms,
        "error": result.error,
    }
    if result.ok and result.output_dir:
        resp["serve_url"] = f"/pages/site/{name}/"
    return jsonify(resp)


@pages_api_bp.route("/pages/build-status/<name>")
def build_status_route(name: str):  # type: ignore[no-untyped-def]
    """Get build status for a segment."""
    status = get_build_status(_project_root(), name)
    if status is None:
        return jsonify({"built": False})
    return jsonify({"built": True, **status})


@pages_api_bp.route("/pages/build-all", methods=["POST"])
@run_tracked("build", "build:pages_all")
def build_all_route():  # type: ignore[no-untyped-def]
    """Build all segments."""
    root = _project_root()
    segments = _get_segments(root)
    results = []
    for seg in segments:
        r = build_segment(root, seg.name)
        results.append({
            "segment": seg.name,
            "ok": r.ok,
            "error": r.error,
            "duration_ms": r.duration_ms,
        })
    return jsonify({
        "ok": all(r["ok"] for r in results),
        "results": results,
    })


# ── Merge + Deploy ──────────────────────────────────────────────────


@pages_api_bp.route("/pages/merge", methods=["POST"])
@run_tracked("build", "build:pages_merge")
def merge_route():  # type: ignore[no-untyped-def]
    """Merge all built segments into a single output."""
    return jsonify(merge_segments(_project_root()))


@pages_api_bp.route("/pages/deploy", methods=["POST"])
@run_tracked("deploy", "deploy:pages")
def deploy_route():  # type: ignore[no-untyped-def]
    """Deploy merged output to gh-pages."""
    return jsonify(deploy_to_ghpages(_project_root()))


# ── Init ────────────────────────────────────────────────────────────


@pages_api_bp.route("/pages/init", methods=["POST"])
@run_tracked("setup", "setup:pages")
def init_pages():  # type: ignore[no-untyped-def]
    """Initialize pages config from project.yml content_folders."""
    return jsonify(init_pages_from_project(_project_root()))


# ── Preview ─────────────────────────────────────────────────────────


@pages_api_bp.route("/pages/preview/<name>", methods=["POST"])
def start_preview_route(name: str):  # type: ignore[no-untyped-def]
    """Start a preview server for a segment."""
    return jsonify(start_preview(_project_root(), name))


@pages_api_bp.route("/pages/preview/<name>", methods=["DELETE"])
def stop_preview_route(name: str):  # type: ignore[no-untyped-def]
    """Stop a preview server."""
    return jsonify(stop_preview(name))


@pages_api_bp.route("/pages/previews")
def list_previews_route():  # type: ignore[no-untyped-def]
    """List running preview servers."""
    return jsonify({"previews": list_previews()})


# ── CI Workflow Generation ──────────────────────────────────────────


@pages_api_bp.route("/pages/ci", methods=["POST"])
@run_tracked("generate", "generate:pages_ci")
def generate_ci_route():  # type: ignore[no-untyped-def]
    """Generate GitHub Actions workflow for Pages deployment."""
    return jsonify(generate_ci_workflow(_project_root()))


# ── SSE Build Log Streaming (Pipeline-Aware) ───────────────────────


@pages_api_bp.route("/pages/build-stream/<name>", methods=["POST"])
def build_stream_route(name: str):  # type: ignore[no-untyped-def]
    """Build a segment with stage-aware SSE streaming."""
    root = _project_root()
    clean = request.args.get("clean", "").lower() in ("true", "1", "yes")
    wipe = request.args.get("wipe", "").lower() in ("true", "1", "yes")
    no_minify = request.args.get("no_minify", "").lower() in ("true", "1", "yes")

    def sse():  # type: ignore[no-untyped-def]
        for event in build_segment_stream(
            root, name,
            clean=clean, wipe=wipe, no_minify=no_minify,
        ):
            yield f"data: {json.dumps(event)}\n\n"

    return Response(sse(), mimetype="text/event-stream")
