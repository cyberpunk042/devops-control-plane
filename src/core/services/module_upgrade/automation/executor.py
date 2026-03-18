"""
Step executor — dispatches automation requests to the right handler.

Central entry point for all step automation. Builds the UpgradeContext,
looks up the handler, calls it in the requested mode, and optionally
marks the step done in project.yml on successful execution.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def execute_step(
    module_name: str,
    step_id: str,
    mode: str,
    project_root: Path,
) -> dict:
    """Execute an automation step in preview or execute mode.

    Args:
        module_name: Module name from project.yml.
        step_id: Step ID (format: automation_id:suffix).
        mode: "preview" or "execute".
        project_root: Absolute path to project root.

    Returns:
        Result dict with at minimum:
          - ok: bool
          - mode: "preview" | "execute"
          - automation_id: str
        Plus handler-specific fields (diff, findings, etc.)
    """
    # ── Extract automation_id from step_id ────────────────────────
    if ":" not in step_id:
        return {"ok": False, "error": "Invalid step_id format"}

    automation_id = step_id.split(":")[0]

    if automation_id in ("manual", "custom", ""):
        return {"ok": False, "error": "This step cannot be automated"}

    # ── Look up handler ──────────────────────────────────────────
    from . import get_handler_registry

    registry = get_handler_registry()
    handler = registry.get(automation_id)

    if not handler:
        return {
            "ok": False,
            "error": f"No automation handler for '{automation_id}'",
        }

    # ── Build context ────────────────────────────────────────────
    from ..context import build_context

    # We need the target from the plan to build context
    target = _get_plan_target(module_name)
    if not target:
        return {"ok": False, "error": "No version plan found for module"}

    ctx = build_context(module_name, target, project_root)

    # ── Execute handler ──────────────────────────────────────────
    try:
        result = handler(ctx, mode)
    except Exception as exc:
        logger.error(
            "Automation handler '%s' failed: %s", automation_id, exc,
            exc_info=True,
        )
        return {"ok": False, "error": str(exc)}

    # ── Mark done on successful execute ──────────────────────────
    if mode == "execute" and result.get("ok"):
        _mark_step_done(module_name, step_id)

    # ── Enrich result ────────────────────────────────────────────
    result.setdefault("mode", mode)
    result.setdefault("automation_id", automation_id)

    return result


def handle_rescan_module(ctx, mode: str) -> dict:
    """Re-scan module and refresh posture data.

    Preview: describes what will happen.
    Execute: invalidates mediator cache and forces recompute.
    """
    if mode == "preview":
        return {
            "ok": True,
            "can_apply": True,
            "preview_type": "action",
            "summary": "Re-scan module and refresh posture evaluation",
            "detail": (
                "This will invalidate the posture cache and force a fresh "
                "scan of the module's runtime constraint, dependency floor, "
                "and code floor."
            ),
        }

    # Execute
    try:
        from src.core.services.mediator import get_mediator

        m = get_mediator()
        m.put("posture.modules", cascade=True)

        return {
            "ok": True,
            "summary": "Module re-scanned successfully",
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# ── Internal helpers ─────────────────────────────────────────────


def _get_plan_target(module_name: str) -> str | None:
    """Get the version plan target for a module."""
    try:
        from src.core.config.loader import load_project

        project = load_project()
        ref = project.get_module(module_name)
        if ref and ref.version_plan:
            return ref.version_plan.target
    except Exception:
        pass
    return None


def _mark_step_done(module_name: str, step_id: str) -> None:
    """Mark a step as done in project.yml by matching step_id."""
    try:
        import yaml
        from src.core.config.loader import find_project_file

        config_path = find_project_file()
        if not config_path:
            return

        raw = config_path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw)
        project_data = data.get("project", data) if "project" in data else data

        for mod in project_data.get("modules", []):
            if mod.get("name") != module_name:
                continue
            plan = mod.get("version_plan")
            if not plan:
                break
            for step in plan.get("checklist", []):
                if step.get("id") == step_id:
                    step["done"] = True
                    break
            break

        config_path.write_text(
            yaml.dump(
                data,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )

        from src.core.services.mediator import get_mediator
        get_mediator().put("posture.modules", cascade=True)

    except Exception as exc:
        logger.error("Failed to mark step done: %s", exc)
