"""
Config API routes — read/write project.yml from the wizard.

GET  /api/config              → current project.yml as JSON
POST /api/config              → save updated project.yml from JSON
GET  /api/config/content-folders → configured + detected content folders
"""

from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

from src.core.services import config_ops

config_bp = Blueprint("config", __name__)


def _project_root() -> Path:
    return Path(current_app.config["PROJECT_ROOT"])


def _config_path() -> Path | None:
    from src.core.config.loader import find_project_file

    p = current_app.config.get("CONFIG_PATH")
    if p:
        return Path(p)
    return find_project_file(_project_root())


# ── Read Config ─────────────────────────────────────────────────────


@config_bp.route("/config")
def api_config_read():  # type: ignore[no-untyped-def]
    """Read the current project.yml as structured JSON."""
    result = config_ops.read_config(_project_root(), config_path=_config_path())

    if "error" in result:
        return jsonify(result), 500

    return jsonify(result)


# ── Save Config ─────────────────────────────────────────────────────


@config_bp.route("/config", methods=["POST"])
def api_config_save():  # type: ignore[no-untyped-def]
    """Save updated project.yml config from wizard data."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "No JSON body"}), 400

    result = config_ops.save_config(
        _project_root(),
        config=data.get("config", {}),
        config_path=_config_path(),
    )

    if "error" in result:
        return jsonify(result), 400

    return jsonify(result)


# ── Content Folders ─────────────────────────────────────────────────


@config_bp.route("/config/content-folders")
def api_config_content_folders():  # type: ignore[no-untyped-def]
    """List configured content folders and detect potential new ones.

    Query params:
        include_hidden: if "true", also return known infrastructure
            directories (.ledger, .state, .backup, .large, .pages).
    """
    include_hidden = request.args.get("include_hidden", "").lower() == "true"
    folders = config_ops.detect_content_folders(
        _project_root(), include_hidden=include_hidden,
    )
    return jsonify({"folders": folders})
