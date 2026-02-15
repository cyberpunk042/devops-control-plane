"""
Config API routes — read/write project.yml from the wizard.

GET  /api/config              → current project.yml as JSON
POST /api/config              → save updated project.yml from JSON
GET  /api/config/content-folders → configured + detected content folders
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml
from flask import Blueprint, current_app, jsonify, request

from src.core.services import devops_cache

logger = logging.getLogger(__name__)

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
    config_path = _config_path()
    if config_path is None or not config_path.is_file():
        return jsonify({
            "exists": False,
            "config": {
                "version": 1,
                "name": "",
                "description": "",
                "repository": "",
                "domains": [],
                "environments": [],
                "modules": [],
                "external": {},
            },
        })

    try:
        raw = config_path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw)
        if not isinstance(data, dict):
            data = {}
    except Exception as e:
        return jsonify({"error": f"Failed to read config: {e}"}), 500

    # Normalize — handle both flat and nested "project" key formats
    conf = data.get("project", data) if "project" in data else data

    return jsonify({
        "exists": True,
        "path": str(config_path),
        "config": {
            "version": conf.get("version", 1),
            "name": conf.get("name", ""),
            "description": conf.get("description", ""),
            "repository": conf.get("repository", ""),
            "domains": conf.get("domains", []),
            "environments": conf.get("environments", []),
            "modules": conf.get("modules", []),
            "content_folders": conf.get("content_folders", []),
            "external": conf.get("external", {}),
        },
    })


# ── Save Config ─────────────────────────────────────────────────────


@config_bp.route("/config", methods=["POST"])
def api_config_save():  # type: ignore[no-untyped-def]
    """Save updated project.yml config from wizard data."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "No JSON body"}), 400

    config = data.get("config", {})
    if not config.get("name"):
        return jsonify({"error": "Project name is required"}), 400

    # Build YAML structure
    yml = {
        "version": config.get("version", 1),
        "name": config["name"],
    }

    if config.get("description"):
        yml["description"] = config["description"]
    if config.get("repository"):
        yml["repository"] = config["repository"]
    if config.get("domains"):
        yml["domains"] = config["domains"]

    # Environments
    envs = config.get("environments", [])
    if envs:
        yml["environments"] = envs

    # Modules
    modules = config.get("modules", [])
    if modules:
        yml["modules"] = modules

    # Content folders (from wizard's _contentFolders internal key)
    content_folders = config.get("_contentFolders") or config.get("content_folders")
    if content_folders:
        yml["content_folders"] = content_folders

    # External
    ext = config.get("external", {})
    if ext:
        yml["external"] = ext

    # Write to project.yml
    config_path = _config_path()
    if config_path is None:
        config_path = _project_root() / "project.yml"

    # Add a comment header
    header = (
        "# project.yml — Control Plane Configuration\n"
        "#\n"
        "# Generated/updated by the Setup Wizard.\n"
        "# Manual edits are welcome.\n\n"
    )

    try:
        yaml_content = yaml.dump(
            yml,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )
        config_path.write_text(header + yaml_content, encoding="utf-8")
    except Exception as e:
        return jsonify({"error": f"Failed to save: {e}"}), 500

    devops_cache.record_event(
        _project_root(),
        label="⚙️ Config Saved",
        summary=f"project.yml saved ({config.get('name', '?')})",
        detail={"project": config.get("name", "?"), "path": str(config_path)},
        card="config",
    )

    return jsonify({"ok": True, "path": str(config_path)})


# ── Content Folders ─────────────────────────────────────────────────


@config_bp.route("/config/content-folders")
def api_config_content_folders():  # type: ignore[no-untyped-def]
    """List configured content folders and detect potential new ones."""
    root = _project_root()

    # Common content folder names to suggest
    common_names = {"docs", "media", "content", "assets", "images", "files",
                    "uploads", "resources", "public", "static", "data",
                    "backups", "backup", "archive", "notes", "wiki"}

    detected = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        name = entry.name
        if name.startswith(".") or name.startswith("_"):
            continue
        if name in {"node_modules", "__pycache__", ".git", "venv", ".venv",
                     "env", "dist", "build", "target", "out", ".tox",
                     ".mypy_cache", ".pytest_cache", ".ruff_cache",
                     "state", "stacks", "automations"}:
            continue

        # Count files recursively (limit scan depth)
        file_count = 0
        try:
            for f in entry.rglob("*"):
                if f.is_file():
                    file_count += 1
                if file_count > 999:
                    break
        except PermissionError:
            pass

        is_suggested = name.lower() in common_names
        detected.append({
            "name": name,
            "path": name,
            "file_count": file_count,
            "suggested": is_suggested,
        })

    return jsonify({"folders": detected})
