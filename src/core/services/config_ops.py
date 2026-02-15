"""
Config operations — read/write project.yml, detect content folders.

Channel-independent: no Flask or HTTP dependency.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# ── Audit helper ────────────────────────────────────────────────

def _audit(label: str, summary: str, **kwargs: Any) -> None:
    """Record an audit event if a project root is registered."""
    try:
        from src.core.context import get_project_root
        root = get_project_root()
    except Exception:
        return
    if root is None:
        return
    from src.core.services.devops_cache import record_event
    record_event(root, label=label, summary=summary, card="config", **kwargs)


# ── Skip directories for content folder detection ───────────────

_SKIP_DIRS = frozenset({
    "node_modules", "__pycache__", ".git", "venv", ".venv",
    "env", "dist", "build", "target", "out", ".tox",
    ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "state", "stacks", "automations",
})

_COMMON_CONTENT_NAMES = frozenset({
    "docs", "media", "content", "assets", "images", "files",
    "uploads", "resources", "public", "static", "data",
    "backups", "backup", "archive", "notes", "wiki",
})


# ── Read Config ─────────────────────────────────────────────────


def read_config(project_root: Path, config_path: Path | None = None) -> dict:
    """Read the current project.yml as structured JSON.

    Args:
        project_root: Project root directory.
        config_path: Optional explicit path to project.yml.

    Returns:
        {"exists": bool, "config": {...}, "path": str | None}
        or {"error": "..."} on failure.
    """
    if config_path is None:
        from src.core.config.loader import find_project_file
        config_path = find_project_file(project_root)

    if config_path is None or not config_path.is_file():
        return {
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
        }

    try:
        raw = config_path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw)
        if not isinstance(data, dict):
            data = {}
    except Exception as e:
        return {"error": f"Failed to read config: {e}"}

    # Normalize — handle both flat and nested "project" key formats
    conf = data.get("project", data) if "project" in data else data

    return {
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
    }


# ── Save Config ─────────────────────────────────────────────────


def save_config(
    project_root: Path,
    config: dict,
    config_path: Path | None = None,
) -> dict:
    """Save updated project.yml config from wizard data.

    Args:
        project_root: Project root directory.
        config: Config dict with name, description, modules, etc.
        config_path: Optional explicit path to write to.

    Returns:
        {"ok": True, "path": "..."} or {"error": "..."}.
    """
    if not config.get("name"):
        return {"error": "Project name is required"}

    # Build YAML structure
    yml: dict[str, Any] = {
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

    # Resolve target path
    if config_path is None:
        from src.core.config.loader import find_project_file
        config_path = find_project_file(project_root)
    if config_path is None:
        config_path = project_root / "project.yml"

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
        return {"error": f"Failed to save: {e}"}

    _audit(
        "⚙️ Config Saved",
        f"project.yml saved ({config.get('name', '?')})",
        action="saved",
        target="project.yml",
        detail={"project": config.get("name", "?"), "path": str(config_path)},
    )

    return {"ok": True, "path": str(config_path)}


# ── Detect Content Folders ──────────────────────────────────────


def detect_content_folders(project_root: Path) -> list[dict]:
    """List detected content folders and suggest common ones.

    Returns:
        List of {"name", "path", "file_count", "suggested"} dicts.
    """
    detected: list[dict] = []

    for entry in sorted(project_root.iterdir()):
        if not entry.is_dir():
            continue
        name = entry.name
        if name.startswith(".") or name.startswith("_"):
            continue
        if name in _SKIP_DIRS:
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

        is_suggested = name.lower() in _COMMON_CONTENT_NAMES
        detected.append({
            "name": name,
            "path": name,
            "file_count": file_count,
            "suggested": is_suggested,
        })

    return detected
