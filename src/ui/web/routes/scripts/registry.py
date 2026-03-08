"""
Scripts registry endpoints — list, info, detect, templates, categories.

Routes registered on ``scripts_bp`` from the parent package.

Endpoints:
    GET  /scripts/list                — list all discovered scripts
    GET  /scripts/info/<script_id>    — script metadata + parameters
    GET  /scripts/categories          — list unique categories
    GET  /scripts/coverage            — language coverage metrics
    POST /scripts/detect              — scan project (for wizard)
    GET  /scripts/templates           — list available templates
"""

from __future__ import annotations

import logging

from flask import jsonify, request

from src.ui.web.helpers import project_root as _project_root

from . import scripts_bp

logger = logging.getLogger(__name__)


# ── List all scripts ───────────────────────────────────────────


@scripts_bp.route("/scripts/list")
def scripts_list():
    """List all discovered scripts with metadata.

    Uses server-side cache (mtime-based invalidation).

    Query params:
        ?category=generator   — filter by category
        ?source=template      — filter by source (template/root/override)
        ?bust                 — force cache refresh
    """
    from src.core.services.scripts.registry import get_scripts_summary
    from src.core.services.devops import cache as devops_cache

    root = _project_root()
    bust = "bust" in request.args

    data = devops_cache.get_cached(
        root, "scripts",
        lambda: get_scripts_summary(root),
        force=bust,
    )

    # Apply client-side filters (on the already-cached summary)
    scripts = data.get("scripts", [])
    category = request.args.get("category")
    source = request.args.get("source")

    if category:
        scripts = [s for s in scripts if s.get("category") == category]
    if source:
        scripts = [s for s in scripts if s.get("source") == source]

    return jsonify({
        "ok": True,
        "scripts": scripts,
        "total": len(scripts),
        "by_category": data.get("by_category", {}),
        "by_source": data.get("by_source", {}),
        "_cache": data.get("_cache"),
    })


# ── Script info ────────────────────────────────────────────────


@scripts_bp.route("/scripts/info/<path:script_id>")
def scripts_info(script_id: str):
    """Full metadata and parameters for a single script."""
    from src.core.services.scripts.registry import get_script

    root = _project_root()
    meta = get_script(root, script_id)

    if meta is None:
        return jsonify({"ok": False, "error": f"Script '{script_id}' not found"}), 404

    return jsonify({
        "ok": True,
        "script": {
            "id": meta.id,
            "name": meta.name,
            "description": meta.description,
            "category": meta.category,
            "language": meta.language,
            "mode": meta.mode,
            "source": meta.source,
            "tags": meta.tags,
            "timeout": meta.timeout,
            "default_output": meta.default_output,
            "output_formats": meta.output_formats,
            "path": meta.path,
            "relative_path": meta.relative_path,
            "parameters": [
                {
                    "name": p.name,
                    "type": p.type,
                    "description": p.description,
                    "required": p.required,
                    "default": p.default,
                    "choices": p.choices,
                }
                for p in meta.parameters
            ],
        },
    })


# ── Categories ─────────────────────────────────────────────────


@scripts_bp.route("/scripts/categories")
def scripts_categories():
    """List unique script categories."""
    from src.core.services.scripts.registry import discover_scripts

    root = _project_root()
    scripts = discover_scripts(root)
    cats = sorted({s.category for s in scripts if s.category})

    return jsonify({"ok": True, "categories": cats})


# ── Language coverage ──────────────────────────────────────────


@scripts_bp.route("/scripts/coverage")
def scripts_coverage():
    """Language coverage metrics — how well each language is supported."""
    coverage = {
        "python": {
            "percentage": 100,
            "features": {
                "execution": True,
                "streaming": True,
                "tracking": True,
                "output_routing": True,
                "header_parsing": True,
                "param_extraction": True,
                "param_form": True,
                "ast_analysis": True,
            },
        },
        "shell": {
            "percentage": 85,
            "features": {
                "execution": True,
                "streaming": True,
                "tracking": True,
                "output_routing": True,
                "header_parsing": True,
                "param_extraction": True,
                "param_form": False,
                "ast_analysis": None,  # N/A
            },
        },
        "powershell": {
            "percentage": 0,
            "features": {},
            "note": "Planned for M8",
        },
    }
    return jsonify({"ok": True, "coverage": coverage})


# ── Detect (wizard step 1) ─────────────────────────────────────


@scripts_bp.route("/scripts/detect", methods=["POST"])
def scripts_detect():
    """Scan project for scripts + available templates (wizard step 1).

    Returns existing user scripts, available templates, and project status.
    """
    from src.core.services.scripts.registry import (
        discover_scripts,
        TEMPLATE_DIR,
        _scan_directory,
    )
    from src.core.services.scripts.config import load_scripts_config

    root = _project_root()
    config = load_scripts_config(root)

    # Scan user scripts directory
    user_dir = root / config.root
    user_scripts = []
    if user_dir.is_dir():
        user_scripts = _scan_directory(user_dir, source="root")

    # Scan templates
    templates = []
    if TEMPLATE_DIR.is_dir():
        templates = _scan_directory(TEMPLATE_DIR, source="template")

    return jsonify({
        "ok": True,
        "user_scripts": [
            {
                "id": s.id,
                "name": s.name,
                "category": s.category,
                "language": s.language,
                "mode": s.mode,
                "has_header": True,  # if we found it, it has @script
                "path": s.relative_path,
            }
            for s in user_scripts
        ],
        "templates": [
            {
                "id": s.id,
                "name": s.name,
                "description": s.description,
                "category": s.category,
                "language": s.language,
            }
            for s in templates
        ],
        "status": {
            "scripts_dir_exists": user_dir.is_dir(),
            "scripts_dir": str(config.root),
            "template_source": config.template_source,
            "user_script_count": len(user_scripts),
            "template_count": len(templates),
        },
    })


# ── Templates ──────────────────────────────────────────────────


@scripts_bp.route("/scripts/templates")
def scripts_templates():
    """List available template scripts."""
    from src.core.services.scripts.registry import TEMPLATE_DIR, _scan_directory

    templates = []
    if TEMPLATE_DIR.is_dir():
        templates = _scan_directory(TEMPLATE_DIR, source="template")

    return jsonify({
        "ok": True,
        "templates": [
            {
                "id": s.id,
                "name": s.name,
                "description": s.description,
                "category": s.category,
                "language": s.language,
                "tags": s.tags,
                "parameters": len(s.parameters),
            }
            for s in templates
        ],
        "total": len(templates),
    })
