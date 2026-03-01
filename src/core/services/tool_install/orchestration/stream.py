"""
Streaming plan executor — yields SSE-shaped event dicts as steps run.

This is the shared step-execution loop used by both the "execute" and
"resume" SSE routes.  It runs each step in order, handles success /
failure / skip, persists plan state, and detects restart needs.

**No Flask dependency** — yields plain dicts.  The route handler wraps
these in ``data: {json}\\n\\n`` and returns a ``text/event-stream``
Response.
"""

from __future__ import annotations

import json as _json
import logging
import os
from typing import Any, Iterator

from src.core.services.tool_install.detection.install_failure import (
    _analyse_install_failure,
)
from src.core.services.tool_install.execution.plan_state import save_plan_state

logger = logging.getLogger(__name__)


def stream_step_execution(
    *,
    plan_id: str,
    tool: str,
    steps: list[dict],
    sudo_password: str = "",
    step_offset: int = 0,
    post_env: dict[str, str] | None = None,
    system_profile: dict | None = None,
    network_warnings: list[dict] | None = None,
    enable_remediation: bool = True,
    enable_streaming_subprocess: bool = True,
) -> Iterator[dict[str, Any]]:
    """Execute plan steps sequentially, yielding SSE event dicts.

    This is the core step loop shared by execute-plan and resume-plan
    SSE routes.  Each ``yield`` produces a dict ready to be serialised
    as a ``data: {json}\\n\\n`` SSE frame.

    Args:
        plan_id: Unique ID for state tracking.
        tool: Tool name (e.g. ``"ruff"``).
        steps: List of step dicts from the plan.
        sudo_password: Sudo password for privileged steps.
        step_offset: Logical offset for step indices (resume support).
            When resuming, previously-completed steps are not in
            *steps* but the client needs correct absolute indices.
        post_env: ``plan["post_env"]`` — extra env vars to accumulate
            across steps (e.g. PATH additions after rustup).
        system_profile: OS detection dict for remediation analysis.
        network_warnings: Pre-flight network warnings to emit before
            step execution starts.
        enable_remediation: Whether to run failure analysis and emit
            remediation hints on step failure.
        enable_streaming_subprocess: Whether to stream subprocess
            output line-by-line for tool/post_install steps.

    Yields:
        Event dicts with ``"type"`` key:
        - ``step_start``
        - ``log``
        - ``step_done``
        - ``step_failed``
        - ``network_warning``
        - ``done``
    """
    from src.core.services.tool_install.orchestration.orchestrator import (
        execute_plan_step,
    )

    env_overrides: dict[str, str] = {}
    completed_steps: list[int] = list(range(step_offset))

    # ── Emit network warnings before starting ──
    if network_warnings:
        for nw in network_warnings:
            yield {
                "type": "network_warning",
                "registry": nw["registry"],
                "url": nw.get("url", ""),
                "error": nw.get("error", ""),
                "proxy_detected": nw.get("proxy_detected", False),
            }

    for i, step in enumerate(steps):
        step_index = step_offset + i
        step_label = step.get("label", f"Step {step_index + 1}")
        step_type = step.get("type", "tool")

        yield {
            "type": "step_start",
            "step": i,
            "label": step_label,
            "total": len(steps),
        }

        # Accumulate env overrides from post_env after tool steps
        if step_type == "tool" and post_env:
            for key, val in post_env.items():
                env_overrides[key] = os.path.expandvars(val)

        # ── Execute step ──
        result = None

        if enable_streaming_subprocess and step_type in ("tool", "post_install"):
            # Stream subprocess output line-by-line
            from src.core.services.tool_install.execution.subprocess_runner import (
                _run_subprocess_streaming,
            )
            cmd = step.get("command", [])
            if not cmd:
                yield {"type": "step_failed", "step": i, "error": "No command"}
                yield {
                    "type": "done", "ok": False, "plan_id": plan_id,
                    "error": "Empty command",
                }
                return

            try:
                for chunk in _run_subprocess_streaming(
                    cmd,
                    needs_sudo=step.get("needs_sudo", False),
                    sudo_password=sudo_password,
                    timeout=step.get("timeout", 300),
                    env_overrides=env_overrides if env_overrides else None,
                ):
                    if chunk.get("done"):
                        result = chunk
                    elif "line" in chunk:
                        yield {"type": "log", "step": i, "line": chunk["line"]}
            except Exception as exc:
                result = {"ok": False, "error": str(exc)}

            if result is None:
                result = {"ok": False, "error": "No result from subprocess"}

        else:
            # Non-streaming steps (packages, verify, repo_setup, etc.)
            try:
                result = execute_plan_step(
                    step,
                    sudo_password=sudo_password,
                    env_overrides=env_overrides if env_overrides else None,
                )
            except Exception as exc:
                # Save interrupted state
                _save_state(plan_id, tool, "failed", step_index, completed_steps, steps)
                yield {"type": "step_failed", "step": i, "error": str(exc)}
                yield {
                    "type": "done", "ok": False, "plan_id": plan_id,
                    "error": f"Step {step_index + 1} crashed: {exc}",
                }
                return

            # Emit captured stdout as log lines
            stdout = result.get("stdout", "")
            if stdout:
                for line in stdout.splitlines():
                    yield {"type": "log", "step": i, "line": line}

            stderr_out = result.get("stderr", "")
            if stderr_out and not result.get("ok"):
                for line in stderr_out.splitlines()[-10:]:
                    yield {"type": "log", "step": i, "line": line}

        # ── Handle result ──

        if result.get("skipped"):
            completed_steps.append(step_index)
            yield {
                "type": "step_done", "step": i,
                "skipped": True,
                "message": result.get("message", "Already satisfied"),
            }
            continue

        if result.get("ok"):
            completed_steps.append(step_index)
            _save_state(plan_id, tool, "running", step_index, completed_steps, steps)
            yield {
                "type": "step_done", "step": i,
                "elapsed_ms": result.get("elapsed_ms"),
            }
        else:
            # ── Failure ──
            _save_state(plan_id, tool, "failed", step_index, completed_steps, steps)

            # Check for sudo needed
            if result.get("needs_sudo"):
                yield {
                    "type": "step_failed", "step": i,
                    "error": result.get("error", "Sudo required"),
                    "needs_sudo": True,
                }
                yield {
                    "type": "done", "ok": False, "plan_id": plan_id,
                    "error": result.get("error", "Sudo required"),
                    "needs_sudo": True,
                }
                return

            yield {
                "type": "step_failed", "step": i,
                "error": result.get("error", "Step failed"),
            }

            # ── Remediation analysis ──
            remediation = None
            if enable_remediation:
                if step_type in ("tool", "post_install"):
                    step_method = step.get("method", "")
                    remediation = _analyse_install_failure(
                        tool,
                        step.get("cli", tool),
                        result.get("stderr", ""),
                        exit_code=result.get("exit_code", 1),
                        method=step_method,
                        system_profile=system_profile,
                    )
                elif step_type == "verify":
                    cli = step.get("cli", tool)
                    remediation = {
                        "reason": f"'{cli}' not found in PATH after install",
                        "options": [
                            {"label": "Retry install (with sudo)", "action": "retry"},
                            {
                                "label": "Refresh server PATH and re-check",
                                "command": ["which", cli],
                                "action": "remediate",
                            },
                        ],
                    }

            done_event: dict[str, Any] = {
                "type": "done",
                "ok": False,
                "plan_id": plan_id,
                "error": result.get("error", f"Step {step_index + 1} failed"),
                "step": i,
                "step_label": step_label,
            }
            if remediation:
                done_event["remediation"] = remediation
            yield done_event
            return

    # ── All steps done ──
    _save_state(plan_id, tool, "done", None, completed_steps, steps)

    # Restart detection
    from src.core.services.tool_install.domain.restart import (
        _batch_restarts,
        detect_restart_needs,
    )
    completed_step_dicts = [steps[ci - step_offset] for ci in completed_steps
                           if step_offset <= ci < step_offset + len(steps)]
    restart_needs = detect_restart_needs(
        {"tool": tool, "steps": steps}, completed_step_dicts,
    )
    restart_actions = _batch_restarts(restart_needs) if any(
        restart_needs.get(k)
        for k in ("shell_restart", "reboot_required", "service_restart")
    ) else []

    done_event: dict[str, Any] = {
        "type": "done",
        "ok": True,
        "plan_id": plan_id,
        "message": f"{tool} installed successfully",
        "steps_completed": len(steps),
    }

    if restart_needs.get("shell_restart") or restart_needs.get("reboot_required") or restart_needs.get("service_restart"):
        done_event["restart"] = restart_needs
        done_event["restart_actions"] = restart_actions

    yield done_event


# ── Internal helpers ───────────────────────────────────────────


def _save_state(
    plan_id: str,
    tool: str,
    status: str,
    current_step: int | None,
    completed_steps: list[int],
    steps: list[dict],
) -> None:
    """Persist plan state (fire-and-forget)."""
    try:
        state: dict[str, Any] = {
            "plan_id": plan_id,
            "tool": tool,
            "status": status,
            "completed_steps": completed_steps,
            "steps": [dict(s) for s in steps],
        }
        if current_step is not None:
            state["current_step"] = current_step
        save_plan_state(state)
    except Exception:
        pass
