"""
Plan execution endpoints — execute, resume, cancel, archive.

Routes registered on ``audit_bp`` from the parent package.

Both install plans and update plans (posture remediation) flow
through these endpoints.  The ``mode`` body parameter selects
which resolver to use: ``"install"`` (default) or ``"update"``.

Endpoints:
    POST /audit/install-plan/execute-sync — sync execution (no SSE)
    POST /audit/install-plan/execute      — SSE streaming execution
    GET  /audit/install-plan/pending       — list resumable plans
    POST /audit/install-plan/resume        — resume a paused/failed plan
    POST /audit/install-plan/cancel        — cancel an interrupted plan
    POST /audit/install-plan/archive       — archive a completed plan
"""

from __future__ import annotations

from pathlib import Path

from flask import current_app, jsonify, request

from src.core.services.events.emit import emit_event
from src.core.services.events.tracked import tracked
from src.core.services.tool_install.path_refresh import refresh_server_path as _refresh_server_path
from src.ui.web.helpers import bust_tool_caches

from . import audit_bp


def _emit_completion_event(
    event_type: str, tool: str, mode: str,
    ok: bool, detail: dict,
):
    """Emit a rich event at the END of a streaming operation."""
    from src.core.services.events.correlation import get_correlation

    verb = "updated" if mode == "update" else "installed"
    if not ok:
        summary = f"{tool} {mode} failed"
        if detail.get("error"):
            summary += f": {detail['error'][:80]}"
    else:
        summary = detail.get("message", f"{tool} {verb} successfully")
        steps = detail.get("steps_completed")
        if steps:
            summary += f" ({steps} steps)"

    emit_event(
        event_type,
        summary=summary,
        correlation_id=get_correlation() or "",
        status="ok" if ok else "error",
        duration_ms=detail.get("elapsed_ms", 0),
        detail=detail,
    )

    # Invalidate dependency caches so the dashboard/modal reflects new installs
    if ok:
        try:
            from src.core.services.mediator import get_mediator
            m = get_mediator()
            if m:
                m.put("dependency.installed", cascade=True)
        except Exception:
            pass


# ── Phase 3: Plan execution ───────────────────────────────────


@audit_bp.route("/audit/install-plan/execute-sync", methods=["POST"])
@tracked("tools.plan.executed")
def audit_execute_plan_sync():
    """Execute an install or update plan synchronously (non-streaming).

    For CLI callers and batch operations. Returns a single JSON
    response when all steps are complete — no SSE stream.

    Request body:
        {"tool": "cargo-audit", "sudo_password": "...", "answers": {},
         "mode": "install"}

    The ``mode`` parameter selects the resolver:
        - ``"install"`` (default): uses ``resolve_install_plan()``
        - ``"update"``: uses ``resolve_update_plan()``

    Response:
        {"ok": true, "tool": "cargo-audit", "steps_completed": 3, ...}
        or
        {"ok": false, "error": "...", "step": 1, ...}
    """
    from src.core.services.dev_overrides import resolve_system_profile
    from src.core.services.tool_install import (
        resolve_install_plan,
        resolve_install_plan_with_choices,
    )
    from src.core.services.tool_install.orchestration.orchestrator import execute_plan

    body = request.get_json(silent=True) or {}
    tool = body.get("tool", "").strip().lower()
    sudo_password = body.get("sudo_password", "")
    answers = body.get("answers", {})
    mode = body.get("mode", "install")

    if not tool:
        return jsonify({"error": "No tool specified"}), 400

    _refresh_server_path()
    system_profile, _ = resolve_system_profile(current_app.config["PROJECT_ROOT"])

    if mode == "update":
        from src.core.services.tool_install.resolver.update_resolution import (
            resolve_update_plan,
        )
        plan = resolve_update_plan(tool, system_profile)
    elif answers:
        plan = resolve_install_plan_with_choices(tool, system_profile, answers)
    else:
        plan = resolve_install_plan(tool, system_profile)

    if plan.get("error"):
        return jsonify({"ok": False, "error": plan["error"]}), 400

    if plan.get("already_installed"):
        return jsonify({
            "ok": True,
            "already_installed": True,
            "message": f"{tool} is already installed",
            "version_installed": plan.get("version_installed"),
        })

    result = execute_plan(plan, sudo_password=sudo_password)

    if result.get("ok"):
        _refresh_server_path()
        bust_tool_caches()

    return jsonify(result)


@audit_bp.route("/audit/install-plan/execute", methods=["POST"])
@tracked("tools.plan.executed")
def audit_execute_plan():
    """Execute an install or update plan with SSE streaming.

    Resolves a plan for the requested tool, then executes each step
    in order, streaming progress events to the client.

    Request body:
        {"tool": "cargo-audit", "sudo_password": "...", "answers": {},
         "mode": "install"}

    The ``mode`` parameter selects the resolver:
        - ``"install"`` (default): uses ``resolve_install_plan()``
        - ``"update"``: uses ``resolve_update_plan()``

    SSE events:
        {"type": "step_start", "step": 0, "label": "..."}
        {"type": "log", "step": 0, "line": "..."}
        {"type": "step_done", "step": 0}
        {"type": "step_failed", "step": 0, "error": "..."}
        {"type": "done", "ok": true, "message": "..."}
        {"type": "done", "ok": false, "error": "..."}
    """
    import json as _json
    import os as _os

    from flask import Response, stream_with_context

    from src.core.services.dev_overrides import resolve_system_profile
    from src.core.services.tool_install import (
        execute_plan_dag,
        execute_plan_step,
        resolve_install_plan,
        resolve_install_plan_with_choices,
        save_plan_state,
    )

    body = request.get_json(silent=True) or {}
    tool = body.get("tool", "").strip().lower()
    sudo_password = body.get("sudo_password", "")
    answers = body.get("answers", {})
    mode = body.get("mode", "install")
    prefer_method = body.get("prefer_method", "")

    if not tool:
        return jsonify({"error": "No tool specified"}), 400

    # Refresh PATH before resolving — picks up tools installed by
    # previous remediations (e.g. rustup → ~/.cargo/bin) so the
    # resolver finds the correct binary versions.
    _refresh_server_path()

    # Resolve the plan — mode selects install vs update resolver
    system_profile, _ = resolve_system_profile(current_app.config["PROJECT_ROOT"])
    if mode == "update":
        from src.core.services.tool_install.resolver.update_resolution import (
            resolve_update_plan,
        )
        plan = resolve_update_plan(tool, system_profile, prefer_method=prefer_method or None)
    elif answers:
        plan = resolve_install_plan_with_choices(tool, system_profile, answers)
    else:
        plan = resolve_install_plan(tool, system_profile)

    if plan.get("error"):
        return jsonify({"ok": False, "error": plan["error"]}), 400

    if plan.get("already_installed"):
        return jsonify({
            "ok": True,
            "already_installed": True,
            "message": f"{tool} is already installed",
        })

    steps = plan.get("steps", [])

    # ── Pre-flight: network reachability for required registries ──
    from src.core.services.tool_install.detection.network import (
        check_registry_reachable,
        detect_proxy,
    )

    # Infer required registries from step commands
    _needed_registries: set[str] = set()
    for s in steps:
        cmd_str = " ".join(s.get("command", []))
        if "pip " in cmd_str or "pip3 " in cmd_str:
            _needed_registries.add("pypi")
        elif "cargo " in cmd_str:
            _needed_registries.add("crates")
        elif "npm " in cmd_str:
            _needed_registries.add("npm")
        elif "curl " in cmd_str or "wget " in cmd_str:
            _needed_registries.add("github")

    network_warnings: list[dict] = []
    if _needed_registries:
        proxy_info = detect_proxy()
        for reg in _needed_registries:
            result = check_registry_reachable(reg, timeout=3)
            if not result.get("reachable"):
                warning = {
                    "registry": reg,
                    "url": result.get("url", ""),
                    "error": result.get("error", "unreachable"),
                }
                if proxy_info.get("has_proxy"):
                    warning["proxy_detected"] = True
                network_warnings.append(warning)

    # Generate plan_id for state tracking
    import uuid as _uuid_mod
    plan_id = str(_uuid_mod.uuid4())

    def _sse(data: dict) -> str:
        return f"data: {_json.dumps(data)}\n\n"

    # ── Detect DAG-shaped plans ──────────────────────────────
    is_dag = any(step.get("depends_on") for step in steps)

    if is_dag:
        # DAG execution: bridge callback → SSE via queue
        import queue
        import threading

        # Attach plan_id to plan dict for DAG executor's state saves
        plan["plan_id"] = plan_id

        # Build step index by id for progress events
        step_idx = {s.get("id", f"step_{i}"): i for i, s in enumerate(steps)}

        event_queue: queue.Queue = queue.Queue()

        def _on_progress(step_id: str, status: str) -> None:
            """DAG executor callback → push event to queue."""
            idx = step_idx.get(step_id, 0)
            if status == "started":
                event_queue.put({
                    "type": "step_start", "step": idx,
                    "label": steps[idx].get("label", step_id) if idx < len(steps) else step_id,
                    "total": len(steps),
                })
            elif status == "done":
                event_queue.put({"type": "step_done", "step": idx})
            elif status == "failed":
                event_queue.put({
                    "type": "step_failed", "step": idx,
                    "error": f"Step '{step_id}' failed",
                })
            elif status == "skipped":
                event_queue.put({
                    "type": "step_done", "step": idx,
                    "skipped": True, "message": "Dependency failed",
                })

        def _run_dag() -> None:
            """Execute DAG in background thread."""
            try:
                result = execute_plan_dag(
                    plan, sudo_password=sudo_password,
                    on_progress=_on_progress,
                )
                event_queue.put(("__done__", result))
            except Exception as exc:
                event_queue.put(("__done__", {
                    "ok": False, "error": str(exc),
                }))

        thread = threading.Thread(target=_run_dag, daemon=True)
        thread.start()

        def generate_dag():
            while True:
                event = event_queue.get()
                if isinstance(event, tuple) and event[0] == "__done__":
                    # Final result from DAG executor
                    result = event[1]
                    # Bust caches
                    bust_tool_caches()
                    dag_ok = result.get("ok", False)
                    dag_msg = (f"{tool} installed successfully"
                               if dag_ok else result.get("error", "DAG execution failed"))
                    _emit_completion_event(
                        "tools.plan.completed" if dag_ok else "tools.plan.failed",
                        tool, mode, ok=dag_ok,
                        detail={"message": dag_msg, "plan_id": plan_id},
                    )
                    yield _sse({
                        "type": "done",
                        "ok": dag_ok,
                        "plan_id": plan_id,
                        "message": dag_msg,
                        "paused": result.get("paused", False),
                        "pause_reason": result.get("pause_reason"),
                    })
                    return
                else:
                    yield _sse(event)

        return Response(
            stream_with_context(generate_dag()),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # ── Linear execution (original path) ─────────────────────
    def generate():
        env_overrides: dict[str, str] = {}
        post_env = plan.get("post_env", {})
        completed_steps: list[int] = []

        # Emit network warnings before starting execution
        for nw in network_warnings:
            yield _sse({
                "type": "network_warning",
                "registry": nw["registry"],
                "url": nw.get("url", ""),
                "error": nw.get("error", ""),
                "proxy_detected": nw.get("proxy_detected", False),
            })

        for i, step in enumerate(steps):
            step_label = step.get("label", f"Step {i + 1}")
            step_type = step.get("type", "tool")

            yield _sse({
                "type": "step_start",
                "step": i,
                "label": step_label,
                "total": len(steps),
            })

            # Accumulate env overrides from post_env after tool steps
            if step_type == "tool" and post_env:
                for key, val in post_env.items():
                    env_overrides[key] = _os.path.expandvars(val)

            # ── Execute step ──
            # For tool/post_install steps: stream output live via Popen
            # For other step types: use blocking executor (fast steps)
            if step_type in ("tool", "post_install"):
                from src.core.services.tool_install.execution.subprocess_runner import (
                    _run_subprocess_streaming,
                )
                cmd = step.get("command", [])
                if not cmd:
                    _emit_completion_event(
                        "tools.plan.failed", tool, mode, ok=False,
                        detail={"error": "Empty command", "step": i, "plan_id": plan_id})
                    yield _sse({"type": "step_failed", "step": i, "error": "No command"})
                    yield _sse({"type": "done", "ok": False, "plan_id": plan_id, "error": "Empty command"})
                    return

                result = None
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
                            yield _sse({"type": "log", "step": i, "line": chunk["line"]})
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
                    try:
                        save_plan_state({
                            "plan_id": plan_id,
                            "tool": tool,
                            "status": "failed",
                            "current_step": i,
                            "completed_steps": completed_steps,
                            "steps": [dict(s) for s in steps],
                        })
                    except Exception:
                        pass
                    yield _sse({
                        "type": "step_failed",
                        "step": i,
                        "error": str(exc),
                    })
                    _emit_completion_event(
                        "tools.plan.failed", tool, mode, ok=False,
                        detail={"error": f"Step {i + 1} crashed: {exc}",
                                "step": i, "plan_id": plan_id},
                    )
                    yield _sse({
                        "type": "done",
                        "ok": False,
                        "plan_id": plan_id,
                        "error": f"Step {i + 1} crashed: {exc}",
                    })
                    return

                # Emit captured stdout as log lines (for non-streaming steps)
                stdout = result.get("stdout", "")
                if stdout:
                    for line in stdout.splitlines():
                        yield _sse({"type": "log", "step": i, "line": line})

                stderr_out = result.get("stderr", "")
                if stderr_out and not result.get("ok"):
                    for line in stderr_out.splitlines()[-10:]:
                        yield _sse({"type": "log", "step": i, "line": line})

            if result.get("skipped"):
                completed_steps.append(i)
                yield _sse({
                    "type": "step_done",
                    "step": i,
                    "skipped": True,
                    "message": result.get("message", "Already satisfied"),
                })
                continue

            if result.get("ok"):
                completed_steps.append(i)
                # Persist progress after each successful step
                try:
                    save_plan_state({
                        "plan_id": plan_id,
                        "tool": tool,
                        "status": "running",
                        "current_step": i,
                        "completed_steps": completed_steps,
                        "steps": [dict(s) for s in steps],
                    })
                except Exception:
                    pass
                yield _sse({
                    "type": "step_done",
                    "step": i,
                    "elapsed_ms": result.get("elapsed_ms"),
                })
            else:
                # Save failed state
                try:
                    save_plan_state({
                        "plan_id": plan_id,
                        "tool": tool,
                        "status": "failed",
                        "current_step": i,
                        "completed_steps": completed_steps,
                        "steps": [dict(s) for s in steps],
                    })
                except Exception:
                    pass

                # Check for sudo needed
                if result.get("needs_sudo"):
                    _emit_completion_event(
                        "tools.plan.failed", tool, mode, ok=False,
                        detail={"error": "Sudo required", "step": i,
                                "plan_id": plan_id},
                    )
                    yield _sse({
                        "type": "step_failed",
                        "step": i,
                        "error": result.get("error", "Sudo required"),
                        "needs_sudo": True,
                    })
                    yield _sse({
                        "type": "done",
                        "ok": False,
                        "plan_id": plan_id,
                        "error": result.get("error", "Sudo required"),
                        "needs_sudo": True,
                    })
                    return

                yield _sse({
                    "type": "step_failed",
                    "step": i,
                    "error": result.get("error", "Step failed"),
                })

                # ── Remediation analysis ──
                remediation = None
                if step_type in ("tool", "post_install"):
                    from src.core.services.tool_install.detection.install_failure import (
                        _analyse_install_failure,
                    )
                    step_method = step.get("method", plan.get("method", ""))
                    remediation = _analyse_install_failure(
                        tool,
                        plan.get("cli", tool),
                        result.get("stderr", ""),
                        exit_code=result.get("exit_code", 1),
                        method=step_method,
                        system_profile=system_profile,
                    )
                elif step_type == "verify":
                    cli = plan.get("cli", tool)
                    remediation = {
                        "reason": f"'{cli}' not found in PATH after install",
                        "options": [
                            {
                                "label": "Retry install (with sudo)",
                                "action": "retry",
                            },
                            {
                                "label": f"Refresh server PATH and re-check",
                                "command": ["which", cli],
                                "action": "remediate",
                            },
                        ],
                    }

                done_event: dict = {
                    "type": "done",
                    "ok": False,
                    "plan_id": plan_id,
                    "error": result.get("error", f"Step {i + 1} failed"),
                    "step": i,
                    "step_label": step_label,
                }
                if remediation:
                    done_event["remediation"] = remediation
                _emit_completion_event(
                    "tools.plan.failed", tool, mode, ok=False,
                    detail={"error": done_event["error"],
                            "step": i, "step_label": step_label,
                            "plan_id": plan_id},
                )
                yield _sse(done_event)
                return

        # All steps done — mark plan complete and bust caches
        try:
            save_plan_state({
                "plan_id": plan_id,
                "tool": tool,
                "status": "done",
                "completed_steps": completed_steps,
                "steps": [dict(s) for s in steps],
            })
        except Exception:
            pass

        _refresh_server_path()
        bust_tool_caches()

        # ── Post-update version verification ──
        version_info: dict = {}
        if mode == "update":
            try:
                from src.core.services.tool_install.detection.tool_version import (
                    get_tool_version,
                )
                new_version = get_tool_version(tool)
                old_version = plan.get("from_version", "")
                version_info["new_version"] = new_version or ""
                version_info["old_version"] = old_version
                if new_version and old_version and new_version == old_version:
                    version_info["version_unchanged"] = True

                    # Offer alternative update methods as remediation
                    used_method = plan.get("method", "")
                    try:
                        from src.core.services.tool_install.data.recipes import TOOL_RECIPES
                        from src.core.services.tool_install.resolver.method_selection import (
                            get_update_map,
                        )
                        recipe = TOOL_RECIPES.get(tool, {})
                        update_map = get_update_map(recipe)
                        if update_map:
                            alt_methods = [
                                m for m in update_map
                                if m != used_method and not m.startswith("_")
                            ]
                            # Include _default as "direct download"
                            if "_default" in update_map and used_method != "_default":
                                alt_methods.append("_default")
                            if alt_methods:
                                version_info["alternative_methods"] = alt_methods
                                version_info["used_method"] = used_method
                    except Exception:
                        pass
            except Exception:
                pass

        # ── Restart detection ──
        from src.core.services.tool_install.domain.restart import (
            _batch_restarts,
            detect_restart_needs,
        )

        completed_step_dicts = [steps[ci] for ci in completed_steps if ci < len(steps)]
        restart_needs = detect_restart_needs(plan, completed_step_dicts)
        restart_actions = _batch_restarts(restart_needs) if any(
            restart_needs.get(k) for k in ("shell_restart", "reboot_required", "service_restart")
        ) else []

        verb = "updated" if mode == "update" else "installed"
        done_event: dict = {
            "type": "done",
            "ok": True,
            "plan_id": plan_id,
            "message": f"{tool} {verb} successfully",
            "steps_completed": len(steps),
        }

        if version_info:
            done_event.update(version_info)

        if restart_needs.get("shell_restart") or restart_needs.get("reboot_required") or restart_needs.get("service_restart"):
            done_event["restart"] = restart_needs
            done_event["restart_actions"] = restart_actions

        _emit_completion_event(
            "tools.plan.completed", tool, mode, ok=True,
            detail={"message": done_event["message"],
                    "steps_completed": len(steps),
                    "plan_id": plan_id,
                    "method": plan.get("method", ""),
                    **version_info},
        )
        yield _sse(done_event)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Resumable Plans ────────────────────────────────────────────


@audit_bp.route("/audit/install-plan/pending", methods=["GET"])
def audit_pending_plans():
    """Return a list of resumable (paused/failed) plans.

    Response:
        {"plans": [{"plan_id": "...", "tool": "...", "status": "failed",
                     "completed_steps": [...], "steps": [...]}]}
    """
    from src.core.services.tool_install import list_pending_plans

    plans = list_pending_plans()

    # Return a shallow summary for each plan
    summary = []
    for p in plans:
        summary.append({
            "plan_id": p.get("plan_id", ""),
            "tool": p.get("tool", ""),
            "status": p.get("status", ""),
            "completed_count": len(p.get("completed_steps", [])),
            "total_steps": len(p.get("steps", [])),
        })

    return jsonify({"plans": summary})


@audit_bp.route("/audit/install-plan/resume", methods=["POST"])
@tracked("tools.plan.resumed")
def audit_resume_plan():
    """Resume a paused or failed installation plan via SSE.

    Request body:
        {"plan_id": "abc123...", "sudo_password": "..."}

    SSE events: same as /audit/install-plan/execute.
    """
    import json as _json
    import os as _os

    from flask import Response, stream_with_context

    from src.core.services.tool_install import (
        execute_plan_step,
        resume_plan,
        save_plan_state,
    )

    body = request.get_json(silent=True) or {}
    plan_id = body.get("plan_id", "").strip()
    sudo_password = body.get("sudo_password", "")

    if not plan_id:
        return jsonify({"error": "No plan_id specified"}), 400

    # Resume — get remaining steps
    plan = resume_plan(plan_id)
    if plan.get("error"):
        return jsonify({"ok": False, "error": plan["error"]}), 400

    tool = plan.get("tool", "")
    steps = plan.get("steps", [])
    completed_count = plan.get("completed_count", 0)
    original_total = plan.get("original_total", len(steps))

    def _sse(data: dict) -> str:
        return f"data: {_json.dumps(data)}\n\n"

    def generate():
        completed_steps: list[int] = list(range(completed_count))

        for i, step in enumerate(steps):
            step_index = completed_count + i
            step_label = step.get("label", f"Step {step_index + 1}")

            yield _sse({
                "type": "step_start",
                "step": i,
                "label": step_label,
                "total": len(steps),
                "resumed_offset": completed_count,
            })

            try:
                result = execute_plan_step(
                    step,
                    sudo_password=sudo_password,
                )
            except Exception as exc:
                try:
                    save_plan_state({
                        "plan_id": plan_id,
                        "tool": tool,
                        "status": "failed",
                        "current_step": step_index,
                        "completed_steps": completed_steps,
                        "steps": [dict(s) for s in steps],
                    })
                except Exception:
                    pass
                yield _sse({
                    "type": "step_failed",
                    "step": i,
                    "error": str(exc),
                })
                _emit_completion_event(
                    "tools.plan.failed", tool, "install", ok=False,
                    detail={"error": f"Step {step_index + 1} crashed: {exc}",
                            "plan_id": plan_id, "step": step_index})
                yield _sse({
                    "type": "done",
                    "ok": False,
                    "plan_id": plan_id,
                    "error": f"Step {step_index + 1} crashed: {exc}",
                })
                return

            # Emit stdout
            stdout = result.get("stdout", "")
            if stdout:
                for line in stdout.splitlines():
                    yield _sse({"type": "log", "step": i, "line": line})

            stderr_out = result.get("stderr", "")
            if stderr_out and not result.get("ok"):
                for line in stderr_out.splitlines()[-10:]:
                    yield _sse({"type": "log", "step": i, "line": line})

            if result.get("skipped"):
                completed_steps.append(step_index)
                yield _sse({
                    "type": "step_done",
                    "step": i,
                    "skipped": True,
                    "message": result.get("message", "Already satisfied"),
                })
                continue

            if result.get("ok"):
                completed_steps.append(step_index)
                try:
                    save_plan_state({
                        "plan_id": plan_id,
                        "tool": tool,
                        "status": "running",
                        "current_step": step_index,
                        "completed_steps": completed_steps,
                        "steps": [dict(s) for s in steps],
                    })
                except Exception:
                    pass
                yield _sse({
                    "type": "step_done",
                    "step": i,
                    "elapsed_ms": result.get("elapsed_ms"),
                })
            else:
                try:
                    save_plan_state({
                        "plan_id": plan_id,
                        "tool": tool,
                        "status": "failed",
                        "current_step": step_index,
                        "completed_steps": completed_steps,
                        "steps": [dict(s) for s in steps],
                    })
                except Exception:
                    pass

                if result.get("needs_sudo"):
                    _emit_completion_event(
                        "tools.plan.failed", tool, "install", ok=False,
                        detail={"error": "Sudo required", "step": i, "plan_id": plan_id})
                    yield _sse({
                        "type": "step_failed",
                        "step": i,
                        "error": result.get("error", "Sudo required"),
                        "needs_sudo": True,
                    })
                    yield _sse({
                        "type": "done",
                        "ok": False,
                        "plan_id": plan_id,
                        "error": result.get("error", "Sudo required"),
                        "needs_sudo": True,
                    })
                    return

                _emit_completion_event(
                    "tools.plan.failed", tool, "install", ok=False,
                    detail={"error": result.get("error", "Step failed"),
                            "step": i, "step_label": step_label, "plan_id": plan_id})
                yield _sse({
                    "type": "step_failed",
                    "step": i,
                    "error": result.get("error", "Step failed"),
                })
                yield _sse({
                    "type": "done",
                    "ok": False,
                    "plan_id": plan_id,
                    "error": result.get("error", f"Step {step_index + 1} failed"),
                    "step": i,
                    "step_label": step_label,
                })
                return

        # All steps done
        try:
            save_plan_state({
                "plan_id": plan_id,
                "tool": tool,
                "status": "done",
                "completed_steps": completed_steps,
                "steps": [dict(s) for s in steps],
            })
        except Exception:
            pass

        bust_tool_caches()

        _emit_completion_event(
            "tools.plan.completed", tool, "install", ok=True,
            detail={"message": f"{tool} resumed and completed",
                    "steps_completed": len(steps), "plan_id": plan_id},
        )
        yield _sse({
            "type": "done",
            "ok": True,
            "plan_id": plan_id,
            "message": f"{tool} resumed and completed successfully",
            "steps_completed": len(steps),
        })

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Plan Cancel / Archive ──────────────────────────────────────


@audit_bp.route("/audit/install-plan/cancel", methods=["POST"])
def audit_cancel_plan():
    """Cancel an interrupted/failed plan.

    Request body:
        {"plan_id": "abc123..."}

    Response:
        {"ok": true, "plan_id": "abc123...", "status": "cancelled"}
    """
    from src.core.services.tool_install import cancel_plan

    body = request.get_json(silent=True) or {}
    plan_id = body.get("plan_id", "").strip()

    if not plan_id:
        return jsonify({"error": "No plan_id specified"}), 400

    result = cancel_plan(plan_id)
    if result.get("error"):
        return jsonify({"ok": False, "error": result["error"]}), 404

    return jsonify({"ok": True, "plan_id": plan_id, "status": "cancelled"})


@audit_bp.route("/audit/install-plan/archive", methods=["POST"])
def audit_archive_plan():
    """Archive a completed/cancelled plan.

    Request body:
        {"plan_id": "abc123..."}

    Response:
        {"ok": true, "plan_id": "abc123...", "status": "archived"}
    """
    from src.core.services.tool_install import archive_plan

    body = request.get_json(silent=True) or {}
    plan_id = body.get("plan_id", "").strip()

    if not plan_id:
        return jsonify({"error": "No plan_id specified"}), 400

    result = archive_plan(plan_id)
    if result.get("error"):
        return jsonify({"ok": False, "error": result["error"]}), 404

    return jsonify({"ok": True, "plan_id": plan_id, "status": "archived"})
