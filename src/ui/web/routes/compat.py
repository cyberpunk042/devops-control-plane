"""Compat v2 API routes — /api/compat/*.

All routes call the CompatOrchestrator. No business logic in routes —
just validation, orchestrator call, response formatting.
"""

from __future__ import annotations

import logging

from flask import Blueprint, current_app, jsonify, request

logger = logging.getLogger(__name__)

compat_bp = Blueprint("compat", __name__, url_prefix="/api")


def _get_orchestrator():
    """Get or create the compat orchestrator."""
    from pathlib import Path

    from src.core.services.compat.orchestrator import CompatOrchestrator

    project_root = Path(current_app.config.get("PROJECT_ROOT", "."))

    # Cache on app
    if not hasattr(current_app, "_compat_orchestrator"):
        current_app._compat_orchestrator = CompatOrchestrator.create(project_root)
    return current_app._compat_orchestrator


# ── Analysis ─────────────────────────────────────────────────────


@compat_bp.route("/compat/analyze", methods=["POST"])
def compat_analyze():
    """Analyze a module for version compatibility.

    Body: {module, target_version, direction?, include_transitive?}
    """
    body = request.get_json(silent=True) or {}
    module_name = body.get("module", "")
    target = body.get("target_version", "")
    direction = body.get("direction", "downgrade")
    include_transitive = body.get("include_transitive", True)

    if not module_name or not target:
        return jsonify({"ok": False, "error": "module and target_version required"}), 400

    try:
        compat = _get_orchestrator()
        result = compat.analyze(module_name, target, direction, include_transitive)

        return jsonify({
            "ok": True,
            "module": module_name,
            "target_version": target,
            "direction": direction,
            "summary": result.summary(),
            "findings": [
                {
                    "feature_id": f.feature_id,
                    "feature_name": f.feature_name,
                    "file": f.file,
                    "line": f.line,
                    "source_line": f.source_line,
                    "severity": f.severity,
                    "error_type": f.error_type,
                    "is_transitive": f.is_transitive,
                    "imported_by": f.imported_by,
                    "import_chain": f.import_chain,
                    "source_module": f.source_module,
                    "fix_available": f.fix_available,
                    "fix_strategy": f.fix_strategy,
                    "version": f.version,
                }
                for f in result.findings
            ],
        })
    except Exception as exc:
        logger.error("Compat analyze failed: %s", exc, exc_info=True)
        return jsonify({"ok": False, "error": str(exc)}), 500


@compat_bp.route("/compat/assess", methods=["POST"])
def compat_assess():
    """Pre-plan assessment — is the target achievable?

    Body: {module, target_version, direction?}
    """
    body = request.get_json(silent=True) or {}
    module_name = body.get("module", "")
    target = body.get("target_version", "")
    direction = body.get("direction", "downgrade")

    if not module_name or not target:
        return jsonify({"ok": False, "error": "module and target_version required"}), 400

    try:
        compat = _get_orchestrator()
        assessment = compat.assess(module_name, target, direction)

        return jsonify({
            "ok": True,
            "achievable": assessment.achievable,
            "current_floor": assessment.current_floor,
            "target": assessment.target,
            "gap": assessment.gap,
            "code_fixes_needed": assessment.code_fixes_needed,
            "code_fixes_auto": assessment.code_fixes_auto,
            "code_fixes_manual": assessment.code_fixes_manual,
            "dep_changes_needed": assessment.dep_changes_needed,
            "transitive_fixes_needed": assessment.transitive_fixes_needed,
            "blocking_modules": assessment.blocking_modules,
            "fix_order": assessment.fix_order,
            "recommendation": assessment.recommendation,
            "estimated_effort": assessment.estimated_effort,
        })
    except Exception as exc:
        logger.error("Compat assess failed: %s", exc, exc_info=True)
        return jsonify({"ok": False, "error": str(exc)}), 500


# ── Fixes ────────────────────────────────────────────────────────


@compat_bp.route("/compat/fix/apply-all", methods=["POST"])
def compat_fix_all():
    """Apply all auto-fixable fixes to a module.

    Body: {module, target_version, direction?, verify?}
    """
    body = request.get_json(silent=True) or {}
    module_name = body.get("module", "")
    target = body.get("target_version", "")
    direction = body.get("direction", "downgrade")
    verify = body.get("verify", True)

    if not module_name or not target:
        return jsonify({"ok": False, "error": "module and target_version required"}), 400

    try:
        compat = _get_orchestrator()
        result = compat.fix_all(module_name, target, direction, verify)

        return jsonify({
            "ok": result.all_verified,
            "module": module_name,
            "files_fixed": result.files_fixed,
            "files_verified": result.files_verified,
            "files_rolled_back": result.files_rolled_back,
            "total_fixes": result.total_fixes,
            "verified_fixes": result.verified_fixes,
            "failed_fixes": result.failed_fixes,
            "duration_ms": result.duration_ms,
            "file_results": [
                {
                    "file": fr.file_path,
                    "fixes_applied": fr.fixes_applied,
                    "fixes_verified": fr.fixes_verified,
                    "fixes_failed": fr.fixes_failed,
                    "rolled_back": fr.rolled_back,
                }
                for fr in result.file_results
            ],
        })
    except Exception as exc:
        logger.error("Compat fix failed: %s", exc, exc_info=True)
        return jsonify({"ok": False, "error": str(exc)}), 500


# ── Feature Database ─────────────────────────────────────────────


@compat_bp.route("/compat/features", methods=["GET"])
def compat_features():
    """Browse the feature database.

    Query params: ?language=python&above=3.8&category=stdlib
    """
    language = request.args.get("language", "")
    above = request.args.get("above", "")
    category = request.args.get("category", "")
    search_q = request.args.get("q", "")

    try:
        compat = _get_orchestrator()
        registry = compat.registry

        if search_q:
            entries = registry.search(search_q)
        elif language and above:
            entries = registry.above_version(language, above)
        elif language and category:
            entries = registry.by_category(language, category)
        elif language:
            entries = registry.by_language(language)
        else:
            # Return stats only (no huge entry dump)
            return jsonify({
                "ok": True,
                "stats": registry.stats(),
            })

        return jsonify({
            "ok": True,
            "count": len(entries),
            "entries": [
                {
                    "id": e.id,
                    "language": e.language,
                    "feature_name": e.feature_name,
                    "introduced": e.introduced,
                    "category": e.category,
                    "severity": e.severity.value,
                    "direction": e.direction.value,
                    "fix_strategy": e.fix.strategy.value,
                    "fix_available": e.fix.strategy.value != "manual",
                    "edge_cases": len(e.edge_cases),
                    "description": e.description,
                }
                for e in entries
            ],
        })
    except Exception as exc:
        logger.error("Compat features failed: %s", exc, exc_info=True)
        return jsonify({"ok": False, "error": str(exc)}), 500


@compat_bp.route("/compat/features/stats", methods=["GET"])
def compat_features_stats():
    """Feature database statistics."""
    try:
        compat = _get_orchestrator()
        return jsonify({"ok": True, "stats": compat.registry.stats()})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@compat_bp.route("/compat/deps/check", methods=["POST"])
def compat_deps_check():
    """Check dependency compatibility.

    Body: {module, target_version}
    """
    body = request.get_json(silent=True) or {}
    module_name = body.get("module", "")
    target = body.get("target_version", "")

    if not module_name or not target:
        return jsonify({"ok": False, "error": "module and target_version required"}), 400

    try:
        from pathlib import Path as _Path

        from src.core.services.compat.analysis.dep_analyzer import DependencyAnalyzer

        compat = _get_orchestrator()
        module_dir = compat._resolve_module_dir(module_name)
        if not module_dir:
            return jsonify({"ok": False, "error": f"Module '{module_name}' not found"}), 404

        analyzer = DependencyAnalyzer()
        result = analyzer.analyze(module_dir, "python", target)

        return jsonify({
            "ok": True,
            "module": module_name,
            "target_version": target,
            "summary": result.summary(),
            "packages": [
                {
                    "package": p.package,
                    "version": p.installed_version,
                    "requires_python": p.requires_python,
                    "min_version": p.min_version,
                    "compatible": p.compatible,
                    "unknown": p.unknown,
                    "note": p.note,
                }
                for p in result.packages
            ],
        })
    except Exception as exc:
        logger.error("Compat deps check failed: %s", exc, exc_info=True)
        return jsonify({"ok": False, "error": str(exc)}), 500


# ── Plans ────────────────────────────────────────────────────────


@compat_bp.route("/compat/plan/create", methods=["POST"])
def compat_plan_create():
    """Create a version plan for a module.

    Body: {module, target_version, direction?}
    """
    body = request.get_json(silent=True) or {}
    module_name = body.get("module", "")
    target = body.get("target_version", "")
    direction = body.get("direction", "downgrade")

    if not module_name or not target:
        return jsonify({"ok": False, "error": "module and target_version required"}), 400

    try:
        compat = _get_orchestrator()
        result = compat.create_plan(module_name, target, direction)
        return jsonify(result)
    except Exception as exc:
        logger.error("Compat plan create failed: %s", exc, exc_info=True)
        return jsonify({"ok": False, "error": str(exc)}), 500


@compat_bp.route("/compat/plan/<module_name>", methods=["GET"])
def compat_plan_get(module_name: str):
    """Get current plan for a module."""
    try:
        compat = _get_orchestrator()
        plan = compat.get_plan(module_name)

        if not plan:
            return jsonify({"ok": False, "error": f"No plan found for '{module_name}'"}), 404

        return jsonify({"ok": True, **plan})
    except Exception as exc:
        logger.error("Compat plan get failed: %s", exc, exc_info=True)
        return jsonify({"ok": False, "error": str(exc)}), 500
