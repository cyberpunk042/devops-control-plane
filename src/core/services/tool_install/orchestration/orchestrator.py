"""
L5 Orchestration — Top-level coordinators.

These functions tie everything together: resolve plans, execute
steps, handle failures, and coordinate full install workflows.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Any

from src.core.services.audit_helpers import make_auditor

from src.core.services.tool_install.data.recipes import TOOL_RECIPES
from src.core.services.tool_install.domain.dag import (
    _add_implicit_deps, _validate_dag, _get_ready_steps, _enforce_parallel_safety,
)
from src.core.services.tool_install.domain.restart import detect_restart_needs, _batch_restarts
from src.core.services.tool_install.domain.risk import _infer_risk
from src.core.services.tool_install.domain.rollback import _generate_rollback
from src.core.services.tool_install.detection.install_failure import _analyse_install_failure
from src.core.services.tool_install.detection.tool_version import get_tool_version
from src.core.services.tool_install.execution.backup import _backup_before_step
from src.core.services.tool_install.execution.plan_state import save_plan_state, load_plan_state
from src.core.services.tool_install.execution.subprocess_runner import _run_subprocess
from src.core.services.tool_install.resolver.plan_resolution import resolve_install_plan

logger = logging.getLogger(__name__)

_audit = make_auditor("audit")


def execute_plan_step(
    step: dict,
    *,
    sudo_password: str = "",
    env_overrides: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Execute a single plan step by dispatching on ``step["type"]``.

    Args:
        step: Single step dict from ``plan["steps"]``.
        sudo_password: Sudo password if ``step["needs_sudo"]``.
        env_overrides: Extra env vars (e.g. PATH from ``post_env``).

    Returns:
        ``{"ok": True, ...}`` on success,
        ``{"ok": False, ...}`` on failure.
    """
    step_type = step.get("type", "tool")

    # ── High-risk safeguard: backup before execution ──
    if step.get("risk") == "high" and step.get("backup_before"):
        backed_up = _backup_before_step(step, sudo_password=sudo_password)
        if not backed_up and step.get("backup_before"):
            logger.warning(
                "High-risk step '%s' has backup_before but no backups were created",
                step.get("label", "?"),
            )

    if step_type == "packages":
        return _execute_package_step(step, sudo_password=sudo_password)
    elif step_type == "repo_setup":
        return _execute_repo_step(step, sudo_password=sudo_password)
    elif step_type == "tool":
        return _execute_command_step(
            step, sudo_password=sudo_password, env_overrides=env_overrides,
        )
    elif step_type == "post_install":
        # ── SecureBoot check before modprobe ──
        cmd = step.get("command", [])
        if cmd and len(cmd) >= 1 and cmd[0] == "modprobe":
            sb = _detect_secure_boot()
            if sb is True:
                module_name = cmd[1] if len(cmd) > 1 else "unknown"
                return {
                    "ok": False,
                    "error": (
                        f"SecureBoot is enabled. Loading unsigned kernel module "
                        f"'{module_name}' will fail. Either disable SecureBoot "
                        f"in BIOS or sign the module with MOK (Machine Owner Key)."
                    ),
                    "secure_boot": True,
                    "remediation": [
                        "Option 1: Disable SecureBoot in BIOS/UEFI settings",
                        f"Option 2: Sign the module: sudo mokutil --import /path/to/{module_name}.der",
                        "Option 3: Use DKMS which handles signing automatically (if configured)",
                    ],
                }
        return _execute_command_step(
            step, sudo_password=sudo_password, env_overrides=env_overrides,
        )
    elif step_type == "verify":
        return _execute_verify_step(step, env_overrides=env_overrides)
    # ── Phase 5: Build-from-source step types ──
    elif step_type == "source":
        return _execute_source_step(step, sudo_password=sudo_password)
    elif step_type == "build":
        return _execute_build_step(
            step, sudo_password=sudo_password, env_overrides=env_overrides,
        )
    elif step_type == "install":
        return _execute_install_step(
            step, sudo_password=sudo_password, env_overrides=env_overrides,
        )
    elif step_type == "cleanup":
        return _execute_cleanup_step(step)
    # ── Phase 7: Data pack step type ──
    elif step_type == "download":
        return _execute_download_step(step)
    # ── Phase 8: System config step types ──
    elif step_type == "service":
        return _execute_service_step(step, sudo_password=sudo_password)
    elif step_type == "config":
        return _execute_config_step(step, sudo_password=sudo_password)
    elif step_type == "notification":
        return _execute_notification_step(step)
    elif step_type == "shell_config":
        return _execute_shell_config_step(step)
    elif step_type == "github_release":
        return _execute_github_release_step(step, sudo_password=sudo_password)
    else:
        return {"ok": False, "error": f"Unknown step type: {step_type}"}


def execute_plan(
    plan: dict,
    *,
    sudo_password: str = "",
    start_from: int = 0,
) -> dict[str, Any]:
    """Execute an install plan step by step.

    Runs each step in order, accumulates ``post_env`` for subsequent
    steps, logs progress via ``_audit()``, and handles partial
    failures with remediation analysis.

    Args:
        plan: Install plan from ``resolve_install_plan()``.
        sudo_password: Sudo password for steps that need it.
            Piped to each sudo step — password entered ONCE by
            the user, reused for all sudo steps in the plan
            (per domain-sudo-security §password flow).
        start_from: Step index to resume from (for retry after
            partial failure).  Steps before this index are skipped.

    Returns:
        ``{"ok": True, "tool": "...", "steps_completed": N, ...}``
        on success,
        ``{"ok": False, "error": "...", "step": N, ...}`` on failure.
    """
    tool = plan["tool"]
    steps = plan["steps"]
    post_env = plan.get("post_env", {})
    completed = []
    env_overrides: dict[str, str] = {}

    for i, step in enumerate(steps):
        # Skip already-completed steps (resume support)
        if i < start_from:
            continue

        step_label = step.get("label", f"Step {i + 1}")
        step_type = step.get("type", "tool")

        _audit(
            f"🔧 Plan Step {i + 1}/{len(steps)}",
            f"{tool}: {step_label}",
            action="started",
            target=tool,
        )

        # Accumulate env overrides for tool/post_install/verify steps
        # post_env applies AFTER a tool step installs to a non-standard
        # PATH (e.g. cargo → ~/.cargo/bin).  Applied to the step that
        # produces the env AND all subsequent steps.
        if step_type in ("tool", "post_install", "verify") and post_env:
            env_overrides.update(post_env)

        result = execute_plan_step(
            step,
            sudo_password=sudo_password,
            env_overrides=env_overrides if env_overrides else None,
        )

        # ── Skipped (already satisfied) ──
        if result.get("skipped"):
            _audit(
                "⏭️ Step Skipped",
                f"{tool}: {step_label} (already satisfied)",
                action="skipped",
                target=tool,
            )
            completed.append({
                "step": i, "label": step_label, "skipped": True,
            })
            continue

        # ── Failure ──
        if not result["ok"]:
            # Sudo needed — propagate to caller for password prompt
            if result.get("needs_sudo"):
                return {
                    "ok": False,
                    "needs_sudo": True,
                    "error": result["error"],
                    "step": i,
                    "step_label": step_label,
                    "completed": completed,
                }

            # Step failed — try remediation analysis for tool steps
            remediation = None
            if step_type == "tool":
                remediation = _analyse_install_failure(
                    tool, plan.get("cli", tool),
                    result.get("stderr", ""),
                )

            _audit(
                "❌ Step Failed",
                f"{tool}: {step_label} — {result['error']}",
                action="failed",
                target=tool,
                detail={
                    "step": i,
                    "stderr": result.get("stderr", "")[:500],
                },
            )

            # ── Auto-rollback for completed steps ──
            rollback_plan = _generate_rollback(
                [s for s in steps[:i] if s.get("rollback")]
            )

            # Risk-based failure response
            step_risk = step.get("risk", "low")
            auto_rollback_result = None
            if step_risk == "medium" and step.get("rollback"):
                # Auto-rollback the failed step itself
                auto_rollback_result = _execute_rollback(
                    [step["rollback"]],
                    sudo_password=sudo_password,
                )

            response: dict[str, Any] = {
                "ok": False,
                "error": result["error"],
                "step": i,
                "step_label": step_label,
                "completed": completed,
                "stderr": result.get("stderr", ""),
                "rollback_plan": rollback_plan,
            }
            if remediation:
                response["remediation"] = remediation
            if auto_rollback_result:
                response["auto_rollback"] = auto_rollback_result
            if step_risk == "high" and step.get("rollback", {}).get("manual_instructions"):
                response["manual_instructions"] = step["rollback"]["manual_instructions"]
            return response

        # ── Success ──
        _audit(
            "✅ Step Done",
            f"{tool}: {step_label}",
            action="completed",
            target=tool,
        )
        completed.append({
            "step": i,
            "label": step_label,
            "elapsed_ms": result.get("elapsed_ms"),
        })

        # ── Restart check — pause plan if step requires restart ──
        restart_level = step.get("restart_required")
        if restart_level:
            plan_id = plan.get("plan_id", str(_uuid_mod.uuid4()))
            save_plan_state({
                "plan_id": plan_id,
                "tool": tool,
                "status": "paused",
                "pause_reason": f"{restart_level}_restart",
                "current_step": i,
                "resume_from": i + 1,
                "steps": [
                    {
                        "id": j,
                        "label": s.get("label", f"Step {j + 1}"),
                        "status": "done" if j <= i else "pending",
                    }
                    for j, s in enumerate(steps)
                ],
                "rollback_plan": _generate_rollback(
                    [steps[j] for j in range(i + 1)]
                ),
                "plan": plan,
            })
            _audit(
                "⏸️ Plan Paused",
                f"{tool}: restart required ({restart_level})",
                action="paused",
                target=tool,
            )
            return {
                "ok": False,
                "paused": True,
                "pause_reason": restart_level,
                "pause_message": step.get(
                    "restart_message",
                    f"A {restart_level} restart is required.",
                ),
                "plan_id": plan_id,
                "resume_from": i + 1,
                "step": i,
                "step_label": step_label,
                "completed": completed,
            }

    # ── All steps complete ──
    _audit(
        "✅ Tool Installed",
        f"{tool}: all {len(steps)} steps completed",
        action="installed",
        target=tool,
    )

    return {
        "ok": True,
        "tool": tool,
        "message": f"{tool} installed successfully",
        "steps_completed": len(completed),
        "completed": completed,
        "invalidates": ["l0_detection", "system_deps", "tool_status"],
    }


def execute_plan_dag(
    plan: dict,
    *,
    sudo_password: str = "",
    on_progress: Any = None,
) -> dict[str, Any]:
    """Execute a plan with DAG-aware parallel step support.

    Steps with ``depends_on`` run after their dependencies.
    Independent steps run concurrently (via threads).
    Package manager steps are serialized to avoid lock conflicts.

    Falls back to linear execution for plans without ``depends_on``.

    Spec: Phase 8 §DAG Execution Engine.

    Args:
        plan: Install plan from ``resolve_install_plan()``.
        sudo_password: Password for sudo steps.
        on_progress: Optional callback ``(step_id, status)`` for
                     progress reporting.

    Returns:
        ``{"ok": True, "completed": [...], ...}`` on full success,
        ``{"ok": False, "failed": [...], ...}`` on any failure.
    """
    import concurrent.futures

    steps = list(plan["steps"])  # Shallow copy
    steps = _add_implicit_deps(steps)

    # Validate DAG
    dag_errors = _validate_dag(steps)
    if dag_errors:
        return {"ok": False, "error": f"Invalid plan: {', '.join(dag_errors)}"}

    # Build step lookup
    step_by_id = {s["id"]: s for s in steps}

    completed: set[str] = set()
    failed: set[str] = set()
    results: dict[str, dict] = {}

    plan_id = plan.get("plan_id", str(_uuid_mod.uuid4()))

    while len(completed) + len(failed) < len(steps):
        ready = _get_ready_steps(steps, completed, set())

        if not ready:
            # All remaining steps are blocked by failures
            break

        # Filter out steps blocked by failed dependencies
        runnable: list[dict] = []
        for step in ready:
            deps = step.get("depends_on", [])
            if any(d in failed for d in deps):
                failed.add(step["id"])
                results[step["id"]] = {
                    "ok": False, "skipped": True,
                    "reason": "dependency failed",
                }
                if on_progress:
                    on_progress(step["id"], "skipped")
                continue
            runnable.append(step)

        if not runnable:
            break

        # Check parallelism safety
        if len(runnable) > 1:
            runnable = _enforce_parallel_safety(runnable)

        # Execute: single step → inline, multiple → threaded
        if len(runnable) == 1:
            step = runnable[0]
            if on_progress:
                on_progress(step["id"], "started")
            result = execute_plan_step(step, sudo_password=sudo_password)
            results[step["id"]] = result

            if result.get("ok"):
                completed.add(step["id"])
                if on_progress:
                    on_progress(step["id"], "done")
            else:
                failed.add(step["id"])
                if on_progress:
                    on_progress(step["id"], "failed")

            # Check restart_required — pause plan
            if result.get("ok") and step.get("restart_required"):
                save_plan_state({
                    "plan_id": plan_id,
                    "tool": plan.get("tool", ""),
                    "status": "paused",
                    "pause_reason": f"{step['restart_required']}_restart",
                    "current_step": step["id"],
                    "completed_steps": list(completed),
                    "steps": steps,
                })
                return {
                    "ok": False,
                    "paused": True,
                    "pause_reason": step["restart_required"],
                    "pause_message": step.get(
                        "restart_message",
                        f"A {step['restart_required']} restart is required.",
                    ),
                    "plan_id": plan_id,
                    "completed": list(completed),
                    "results": results,
                }
        else:
            # Parallel execution via thread pool
            def _exec_step(s: dict) -> tuple[dict, dict]:
                """Execute a single step, returning (step, result)."""
                return s, execute_plan_step(s, sudo_password=sudo_password)

            for step in runnable:
                if on_progress:
                    on_progress(step["id"], "started")

            with concurrent.futures.ThreadPoolExecutor(
                max_workers=len(runnable),
            ) as pool:
                futures = {
                    pool.submit(_exec_step, s): s for s in runnable
                }
                for future in concurrent.futures.as_completed(futures):
                    step, result = future.result()
                    results[step["id"]] = result
                    if result.get("ok"):
                        completed.add(step["id"])
                        if on_progress:
                            on_progress(step["id"], "done")
                    else:
                        failed.add(step["id"])
                        if on_progress:
                            on_progress(step["id"], "failed")

    # Save final state
    final_status = "done" if not failed else "failed"
    save_plan_state({
        "plan_id": plan_id,
        "tool": plan.get("tool", ""),
        "status": final_status,
        "completed_steps": list(completed),
        "failed_steps": list(failed),
        "steps": steps,
    })

    return {
        "ok": len(failed) == 0,
        "plan_id": plan_id,
        "completed": list(completed),
        "failed": list(failed),
        "results": results,
    }


def install_tool(
    tool: str,
    *,
    cli: str = "",
    sudo_password: str = "",
    override_command: list[str] | None = None,
) -> dict[str, Any]:
    """Install a missing devops tool — backward-compatible wrapper.

    Generates a plan via ``resolve_install_plan()``, then executes
    it via ``execute_plan()``.  Existing callers don't need changes.

    For override commands (remediation), uses ``_run_subprocess()``
    directly — no plan needed.

    Args:
        tool: Tool name (e.g. ``"helm"``, ``"ruff"``).
        cli: CLI binary name to check (defaults to *tool*).
        sudo_password: Password for sudo, required for system packages.
        override_command: If provided, run this command instead of
            the recipe.  Used by remediation options.

    Returns:
        ``{"ok": True, "message": "...", ...}`` on success,
        ``{"ok": False, "error": "...", ...}`` on failure,
        ``{"ok": False, "needs_sudo": True, ...}`` when password needed.
    """
    tool = tool.lower().strip()
    cli = (cli or tool).strip()

    if not tool:
        return {"ok": False, "error": "No tool specified"}

    # ── Override command (remediation path) ──
    # Direct execution — no plan, no dependency walk.
    if override_command:
        _audit(
            "🔧 Tool Install (override)",
            f"{tool}: custom command",
            action="started",
            target=tool,
        )
        result = _run_subprocess(
            override_command,
            needs_sudo=False,
            timeout=120,
        )
        if result["ok"]:
            installed = shutil.which(cli) is not None
            result["message"] = (
                f"{tool} installed successfully"
                if installed
                else f"Command succeeded but '{cli}' not found in PATH yet"
                " — you may need to restart your shell"
            )
            result["installed"] = installed
            _audit(
                "✅ Tool Installed",
                result["message"],
                action="installed",
                target=tool,
            )
        else:
            remediation = _analyse_install_failure(
                tool, cli, result.get("stderr", ""),
            )
            if remediation:
                result["remediation"] = remediation
            _audit(
                "❌ Tool Install Failed",
                f"{tool}: {result['error']}",
                action="failed",
                target=tool,
            )
        return result

    # ── Plan-based execution ──
    from src.core.services.audit.l0_detection import _detect_os

    system_profile = _detect_os()
    plan = resolve_install_plan(tool, system_profile)

    # Resolution failed?
    if plan.get("error"):
        _audit(
            "🔧 Tool Install — No Plan",
            f"{tool}: {plan['error']}",
            action="failed",
            target=tool,
        )
        return {"ok": False, "error": plan["error"]}

    # Already installed?
    if plan.get("already_installed"):
        _audit(
            "🔧 Tool Already Installed",
            f"{tool} is already available",
            action="checked",
            target=tool,
        )
        return {
            "ok": True,
            "message": f"{tool} is already installed",
            "already_installed": True,
        }

    # Execute the plan
    return execute_plan(plan, sudo_password=sudo_password)
