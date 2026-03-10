"""
Plan executor — orchestrates the sequential execution of plan steps.

Takes an ExecutionPlan, validates it, resolves browser config, then
runs each step in sequence while chaining variables between steps.

Core responsibilities:
    1. Validate plan (scripts exist, suites exist, consumed vars declared)
    2. Resolve browser config (launch Chrome if separate_instance)
    3. Execute steps: script → M1 executor, cdp_test → replayer, etc.
    4. Variable chaining: parse DCP_VAR_ outputs, merge into namespace
    5. Browser lifecycle: kill Chrome on finish if !keep_alive
    6. SSE events: plan:start, plan:step_start, plan:step_done, plan:done
    7. Cancellation via stop_event

Uses existing infrastructure:
    - scripts.executor.execute_script() for script steps
    - cdp_test.replayer.replay_suite() for CDP test steps (synchronous)
    - chrome.launcher for browser lifecycle
    - event_bus for real-time events

Singleton: only one plan can run at a time (replayer constraint).
"""

from __future__ import annotations

import logging
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from src.core.services.scripts.plans import (
    BrowserConfig,
    ExecutionPlan,
    PlanRunResult,
    PlanStep,
    StepResult,
    _now_iso,
)

logger = logging.getLogger(__name__)


# ── DCP_VAR convention ─────────────────────────────────────────

_DCP_VAR_PREFIX = "DCP_VAR_"
"""Scripts produce variables by printing DCP_VAR_KEY=VALUE to stdout."""

_DCP_VAR_RE = re.compile(r"^DCP_VAR_([A-Za-z_][A-Za-z0-9_]*)=(.*)$")

_DCP_JSON_PREFIX = "DCP_JSON_"
"""Scripts produce JSON variables by printing DCP_JSON_KEY={...} to stdout."""

_DCP_JSON_RE = re.compile(r"^DCP_JSON_([A-Za-z_][A-Za-z0-9_]*)=(.*)$")


def _extract_variables_from_lines(lines: list[str]) -> dict[str, Any]:
    """Parse DCP_VAR_KEY=VALUE and DCP_JSON_KEY={...} lines from script output.

    Returns dict of extracted variable names → values.
    The DCP_VAR_ / DCP_JSON_ prefix is stripped from keys.

    DCP_VAR_ lines produce string values.
    DCP_JSON_ lines produce parsed JSON values (dict, list, etc.).
    If JSON parsing fails, the raw string is kept as fallback.

    Example:
        Input line:  "DCP_VAR_DEPLOY_PATH=/opt/app/v2"
        Output:      {"DEPLOY_PATH": "/opt/app/v2"}

        Input line:  'DCP_JSON_AUDIT={"ok": true, "score": 95}'
        Output:      {"AUDIT": {"ok": True, "score": 95}}
    """
    import json as _json

    variables: dict[str, Any] = {}
    for line in lines:
        stripped = line.strip()

        # Try DCP_JSON_ first (more specific prefix)
        m = _DCP_JSON_RE.match(stripped)
        if m:
            key = m.group(1)
            raw = m.group(2)
            try:
                variables[key] = _json.loads(raw)
            except (ValueError, TypeError):
                # Fallback to string if JSON is invalid
                variables[key] = raw
            continue

        # Try DCP_VAR_ (simple string)
        m = _DCP_VAR_RE.match(stripped)
        if m:
            variables[m.group(1)] = m.group(2)

    return variables


# ── Active Plan Run ────────────────────────────────────────────


class _PlanRun:
    """Tracks a single active plan execution."""

    __slots__ = (
        "run_id", "plan_id", "thread", "stop_event",
        "resume_event", "paused", "current_step_sequence",
        "skip_requested", "pending_var_updates",
    )

    def __init__(self, run_id: str, plan_id: str):
        self.run_id = run_id
        self.plan_id = plan_id
        self.thread: threading.Thread | None = None
        self.stop_event = threading.Event()
        self.resume_event = threading.Event()
        self.paused = False
        self.current_step_sequence = 0
        self.skip_requested = False
        self.pending_var_updates: dict[str, Any] | None = None


_active_plan: _PlanRun | None = None
_plan_lock = threading.Lock()


def get_active_plan_run() -> _PlanRun | None:
    """Return the active plan run, or None."""
    with _plan_lock:
        return _active_plan


def cancel_active_plan() -> bool:
    """Cancel the active plan run.  Returns True if one was active."""
    with _plan_lock:
        run = _active_plan
    if run is None:
        return False
    run.stop_event.set()
    if run.paused:
        run.resume_event.set()  # Unblock the pause wait
    if run.thread and run.thread.is_alive():
        run.thread.join(timeout=15.0)
    return True


def resume_plan(run_id: str, variable_updates: dict | None = None) -> bool:
    """Resume a paused plan.  Returns True if resumed.

    Args:
        run_id: The run ID to resume.
        variable_updates: Optional dict of variable name → value to merge
            into the namespace before continuing execution.  Sent by the
            UI when the user edits namespace values at a pause point.
    """
    with _plan_lock:
        run = _active_plan
    if run is None or run.run_id != run_id or not run.paused:
        return False
    run.skip_requested = False
    if variable_updates:
        run.pending_var_updates = variable_updates
    run.resume_event.set()
    return True


def skip_step(run_id: str) -> bool:
    """Skip the current step in a paused plan.  Returns True if skipped."""
    with _plan_lock:
        run = _active_plan
    if run is None or run.run_id != run_id or not run.paused:
        return False
    run.skip_requested = True
    run.resume_event.set()
    return True


# ── Validation ─────────────────────────────────────────────────


def _validate_plan(
    project_root: Path,
    plan: ExecutionPlan,
) -> list[str]:
    """Validate a plan before execution.

    Returns a list of error messages. Empty = valid.
    """
    errors: list[str] = []

    if not plan.steps:
        errors.append("Plan has no steps")
        return errors

    # Validate scripts exist
    from src.core.services.scripts.registry import get_script
    for step in plan.steps:
        if step.type == "script" and step.script_id:
            meta = get_script(project_root, step.script_id)
            if meta is None:
                errors.append(
                    f"Step {step.sequence} ({step.name}): "
                    f"script '{step.script_id}' not found in registry"
                )

    # Validate suites exist
    from src.core.services.cdp_test.storage import get_suite
    for step in plan.steps:
        if step.type == "cdp_test" and step.suite_id:
            suite = get_suite(project_root, step.suite_id)
            if suite is None:
                errors.append(
                    f"Step {step.sequence} ({step.name}): "
                    f"CDP test suite '{step.suite_id}' not found"
                )

    # Validate variable chain: consumed vars must be produced by
    # earlier steps or provided in plan.variables
    available_vars = set(plan.variables.keys())
    for step in sorted(plan.steps, key=lambda s: s.sequence):
        for var_name in step.consumes:
            if var_name not in available_vars:
                errors.append(
                    f"Step {step.sequence} ({step.name}): "
                    f"consumes variable '{var_name}' but no earlier step "
                    f"produces it and it's not in plan variables"
                )
        for var_name in step.produces:
            available_vars.add(var_name)

    return errors


# ── Target Tab Discovery ───────────────────────────────────────


def _resolve_cdp_target(
    suite_target_url: str,
    cdp_port: int | None,
) -> tuple[str, str]:
    """Discover or create a tab for a CDP test step.

    Returns (target_id, ws_url).  Either may be empty on failure.
    """
    from src.ui.web import cdp_client

    targets = cdp_client.get_targets(port=cdp_port)
    if not targets:
        return "", ""

    # Try matching by suite target_url
    if suite_target_url:
        # Strip protocol for flexible matching
        url_pattern = re.sub(r"^https?://", "", suite_target_url)
        match = cdp_client.find_target_by_url(targets, url_pattern)
        if not match:
            # Try just the domain
            domain = url_pattern.split("/")[0]
            match = cdp_client.find_target_by_url(targets, domain)

        if match:
            return match["id"], match.get("webSocketDebuggerUrl", "")

        # No matching tab — create one
        logger.info(
            "No tab matches '%s', creating one via CDP", suite_target_url,
        )
        new_tab = cdp_client.create_tab(suite_target_url, port=cdp_port)
        if new_tab and "id" in new_tab:
            time.sleep(3.0)  # Let the page load
            # Re-fetch to get ws_url
            targets = cdp_client.get_targets(port=cdp_port)
            for t in targets:
                if t.get("id") == new_tab["id"]:
                    return t["id"], t.get("webSocketDebuggerUrl", "")
            return new_tab["id"], ""

    # No target_url — use the first page-type target
    for t in targets:
        if t.get("type") == "page":
            return t["id"], t.get("webSocketDebuggerUrl", "")

    return "", ""


# ── Step Executors ─────────────────────────────────────────────


def _execute_script_step(
    project_root: Path,
    step: PlanStep,
    namespace: dict[str, Any],
) -> StepResult:
    """Execute a script step via the M1 executor."""
    from src.core.services.scripts.executor import execute_script

    # Merge plan namespace into script params: step params take priority
    params = dict(namespace)
    params.update(step.script_params)

    result = execute_script(
        project_root,
        step.script_id,
        params=params,
    )

    # Extract DCP_VAR_ lines from stdout
    produced = _extract_variables_from_lines(result.get("lines", []))

    status = "passed" if result.get("ok") else "failed"
    return StepResult(
        step_id=step.id,
        step_name=step.name,
        step_type="script",
        sequence=step.sequence,
        status=status,
        error=result.get("error", "") or "",
        script_run_id=result.get("run_id", ""),
        script_stream_id=result.get("stream_id", ""),
        script_exit_code=result.get("exit_code", -1),
        script_lines=result.get("lines", []),
        variables_produced=produced,
    )


def _execute_cdp_test_step(
    project_root: Path,
    step: PlanStep,
    namespace: dict[str, Any],
    cdp_port: int | None,
    stop_event: threading.Event,
    callback: callable,
    clear_site_data: bool | None = None,
) -> StepResult:
    """Execute a CDP test step via the replayer (synchronous)."""
    from src.core.services.cdp_test.replayer import replay_suite
    from src.core.services.cdp_test.storage import get_suite

    suite = get_suite(project_root, step.suite_id)
    if suite is None:
        return StepResult(
            step_id=step.id,
            step_name=step.name,
            step_type="cdp_test",
            sequence=step.sequence,
            status="failed",
            error=f"Suite '{step.suite_id}' not found",
        )

    # Merge: namespace values override step suite_variables (defaults).
    # suite_variables are pre-filled from the suite's declared defaults;
    # the plan namespace (initial vars + runtime overrides) takes priority.
    variables = dict(step.suite_variables)
    variables.update(namespace)

    # Discover the target tab
    target_id, ws_url = _resolve_cdp_target(
        suite.target_url, cdp_port,
    )
    if not target_id:
        return StepResult(
            step_id=step.id,
            step_name=step.name,
            step_type="cdp_test",
            sequence=step.sequence,
            status="failed",
            error=(
                "No CDP target found — browser may not be available "
                f"(port={cdp_port})"
            ),
        )

    # Find the DCP admin tab for re-activation after replay
    from src.ui.web import cdp_client
    targets = cdp_client.get_targets(port=None)  # Always the main browser
    dcp_match = cdp_client.find_target_by_url(targets, "localhost:8000")
    dcp_tab_id = dcp_match.get("id") if dcp_match else None

    # Create a run ID for this replay within the plan
    replay_run_id = str(uuid.uuid4())

    # Run the replay synchronously — we're already in a background thread
    run_result = replay_suite(
        suite=suite,
        target_id=target_id,
        variables=variables,
        callback=callback,
        stop_event=stop_event,
        run_id=replay_run_id,
        ws_url=ws_url,
        dcp_tab_id=dcp_tab_id,
        cdp_port=cdp_port,
        project_root=str(project_root),
        clear_site_data=clear_site_data,
    )

    # Extract captured variables from diagnostic steps
    produced: dict[str, Any] = {}
    for sr in run_result.step_results:
        if sr.get("captured_value"):
            # Prefer explicit export_name (from step.export_as) over selector
            key = sr.get("export_name") or ""
            if not key:
                # Fallback: use the step selector as variable name (cleaned up)
                key = sr.get("selector", "").replace(".", "_").replace("#", "")
            if key:
                produced[key] = sr["captured_value"]

    status = run_result.status
    if status in ("passed", "partial"):
        plan_status = "passed" if status == "passed" else "failed"
    else:
        plan_status = "failed"

    # Forward full replay step results — keep all fields the replayer
    # produces so the UI can show screenshots, OCR, assertions, etc.
    replay_steps = []
    for sr in run_result.step_results:
        entry = dict(sr)  # shallow copy
        # Convert absolute screenshot_path to just the filename
        # (the UI serves them via /api/cdp-test/screenshots/<filename>)
        sp = entry.get("screenshot_path")
        if sp:
            import os
            entry["screenshot_file"] = os.path.basename(sp)
        entry.pop("screenshot_path", None)
        replay_steps.append(entry)

    # Build consumed vars — only the vars the suite actually declares
    consumed: dict[str, Any] = {}
    for k in suite.variables:
        if k in variables:
            consumed[k] = variables[k]

    return StepResult(
        step_id=step.id,
        step_name=step.name,
        step_type="cdp_test",
        sequence=step.sequence,
        status=plan_status,
        error=run_result.error or "",
        replay_run_id=replay_run_id,
        replay_passed=run_result.passed_steps,
        replay_failed=run_result.failed_steps,
        replay_total=run_result.total_steps,
        replay_step_results=replay_steps,
        variables_produced=produced,
        variables_consumed=consumed,
    )


def _execute_checkpoint_step(
    step: PlanStep,
    namespace: dict[str, Any],
    plan_run: _PlanRun,
    plan_mode: str,
    callback: callable,
    sorted_steps: list | None = None,
    step_results_map: dict | None = None,
) -> StepResult:
    """Execute a checkpoint step.

    In semi_automated and interactive modes: pause and wait for resume.
    In fully_automated mode: just log and continue.
    """
    if plan_mode in ("semi_automated", "interactive"):
        # Find next step info for the UI
        next_step_info = None
        steps_produced_since: dict[str, Any] = {}
        if sorted_steps:
            idx = next(
                (i for i, s in enumerate(sorted_steps) if s.id == step.id),
                -1,
            )
            if idx >= 0 and idx + 1 < len(sorted_steps):
                ns = sorted_steps[idx + 1]
                next_step_info = {
                    "id": ns.id,
                    "name": ns.name,
                    "type": ns.type,
                    "sequence": ns.sequence,
                    "consumes": ns.consumes,
                    "produces": ns.produces,
                }
            # Gather all variables produced since the last checkpoint
            if step_results_map:
                for s in sorted_steps:
                    if s.id == step.id:
                        break  # stop at current checkpoint
                    sr = step_results_map.get(s.id)
                    if sr and sr.variables_produced:
                        steps_produced_since.update(sr.variables_produced)

        # Emit pause event
        callback("plan:paused", {
            "run_id": plan_run.run_id,
            "step_id": step.id,
            "step_name": step.name,
            "reason": "checkpoint",
            "message": step.checkpoint_message,
            "variables": namespace,
            "next_step": next_step_info,
            "steps_produced_since": steps_produced_since,
        })

        # Wait for resume/skip/cancel
        plan_run.paused = True
        plan_run.resume_event.clear()
        plan_run.resume_event.wait()  # Blocks until resume/skip/cancel
        plan_run.paused = False

        # Apply any variable updates from the UI
        if plan_run.pending_var_updates:
            namespace.update(plan_run.pending_var_updates)
            plan_run.pending_var_updates = None

        if plan_run.stop_event.is_set():
            return StepResult(
                step_id=step.id,
                step_name=step.name,
                step_type="checkpoint",
                sequence=step.sequence,
                status="cancelled",
            )

        if plan_run.skip_requested:
            plan_run.skip_requested = False
            return StepResult(
                step_id=step.id,
                step_name=step.name,
                step_type="checkpoint",
                sequence=step.sequence,
                status="skipped",
            )

        callback("plan:resumed", {
            "run_id": plan_run.run_id,
            "step_id": step.id,
        })

    return StepResult(
        step_id=step.id,
        step_name=step.name,
        step_type="checkpoint",
        sequence=step.sequence,
        status="passed",
    )


def _evaluate_conditional_step(
    step: PlanStep,
    step_results_map: dict[str, StepResult],
) -> StepResult:
    """Evaluate a conditional step.

    Checks the result of condition_step_id and returns passed/skipped
    based on whether the condition matches.
    """
    ref_result = step_results_map.get(step.condition_step_id)
    if ref_result is None:
        return StepResult(
            step_id=step.id,
            step_name=step.name,
            step_type="conditional",
            sequence=step.sequence,
            status="failed",
            error=(
                f"Conditional references step '{step.condition_step_id}' "
                f"which has no result"
            ),
        )

    condition_met = ref_result.status == step.condition

    return StepResult(
        step_id=step.id,
        step_name=step.name,
        step_type="conditional",
        sequence=step.sequence,
        status="passed" if condition_met else "skipped",
        variables_produced={
            "_CONDITION_MET": str(condition_met).lower(),
            "_THEN_STEP": step.then_step_id if condition_met else "",
            "_ELSE_STEP": step.else_step_id if not condition_met else "",
        },
    )


# ── Browser Lifecycle ──────────────────────────────────────────


def _launch_plan_browser(
    browser_config: BrowserConfig,
) -> dict[str, Any]:
    """Launch a separate Chrome instance for the plan.

    Returns instance info dict: {port, pid, endpoint}.
    Raises on failure.
    """
    from src.core.services.chrome.launcher import (
        ChromeLaunchConfig,
        get_launcher,
    )

    launcher = get_launcher()
    config = ChromeLaunchConfig(
        headless=browser_config.headless,
        port=browser_config.port if browser_config.port > 0 else 0,
    )
    instance = launcher.launch(config)
    return {
        "port": instance.port,
        "pid": instance.pid,
        "endpoint": instance.endpoint,
    }


def _kill_plan_browser(port: int) -> None:
    """Kill a Chrome instance launched for a plan."""
    from src.core.services.chrome.launcher import get_launcher

    launcher = get_launcher()
    instance = launcher.get_instance(port)
    if instance:
        launcher.kill_instance(instance)
        logger.info("Killed plan browser on port %d", port)
    else:
        logger.warning(
            "Cannot kill plan browser on port %d: not found in launcher",
            port,
        )


# ── Main Execution ─────────────────────────────────────────────


def execute_plan(
    project_root: Path,
    plan: ExecutionPlan,
    callback: callable,
    stop_event: threading.Event,
    *,
    run_id: str = "",
    runtime_options: dict | None = None,
) -> PlanRunResult:
    """Execute an entire plan synchronously.

    This runs in a background thread (started by start_plan).
    Not called directly from route handlers.

    Args:
        project_root: Project root path.
        plan: The plan to execute.
        callback: Function(event_type, data) for SSE events.
        stop_event: Set to cancel the plan.
        run_id: Pre-allocated run ID (from start_plan).
    """
    if not run_id:
        run_id = str(uuid.uuid4())

    result = PlanRunResult(
        id=run_id,
        plan_id=plan.id,
        plan_name=plan.name,
        mode=plan.mode,
        total_steps=len(plan.steps),
        status="running",
    )

    t_start = time.monotonic()

    # ── Step 1: Validate ──────────────────────────────────────
    errors = _validate_plan(project_root, plan)
    if errors:
        result.status = "failed"
        result.error = "; ".join(errors)
        result.finished_at = _now_iso()
        callback("plan:done", {
            "run_id": run_id,
            "plan_id": plan.id,
            "status": "failed",
            "error": result.error,
        })
        return result

    # Notify start
    callback("plan:start", {
        "run_id": run_id,
        "plan_id": plan.id,
        "plan_name": plan.name,
        "total_steps": len(plan.steps),
        "mode": plan.mode,
    })

    # ── Step 2: Resolve browser ───────────────────────────────
    cdp_port: int | None = None
    chrome_info: dict | None = None
    browser_config = plan.browser_config or BrowserConfig()

    if browser_config.mode == "separate_instance":
        try:
            chrome_info = _launch_plan_browser(browser_config)
            cdp_port = chrome_info["port"]
            result.chrome_instance = chrome_info
            logger.info(
                "Plan browser launched: port=%d pid=%d",
                chrome_info["port"], chrome_info["pid"],
            )
        except Exception as exc:
            result.status = "failed"
            result.error = f"Failed to launch browser: {exc}"
            result.finished_at = _now_iso()
            result.duration_ms = int((time.monotonic() - t_start) * 1000)
            callback("plan:done", {
                "run_id": run_id,
                "plan_id": plan.id,
                "status": "failed",
                "error": result.error,
            })
            return result
    elif browser_config.mode == "same_browser":
        cdp_port = None  # Use global endpoint

    # ── Step 3: Execute steps ─────────────────────────────────
    namespace: dict[str, Any] = dict(plan.variables)
    step_results_map: dict[str, StepResult] = {}
    sorted_steps = sorted(plan.steps, key=lambda s: s.sequence)

    with _plan_lock:
        plan_run = _active_plan
    if plan_run is None:
        # Shouldn't happen if called via start_plan, but be safe
        plan_run = _PlanRun(run_id, plan.id)

    for step in sorted_steps:
        # ── Check cancellation ──
        if stop_event.is_set():
            result.status = "cancelled"
            break

        plan_run.current_step_sequence = step.sequence

        # ── Emit step start ──
        callback("plan:step_start", {
            "run_id": run_id,
            "step_id": step.id,
            "step_name": step.name,
            "step_type": step.type,
            "sequence": step.sequence,
        })

        t_step = time.monotonic()

        # ── Route by step type ──
        if step.type == "script":
            step_result = _execute_script_step(
                project_root, step, namespace,
            )

        elif step.type == "cdp_test":
            # clear_site_data applies only to the first CDP step (once,
            # before the plan really starts), not to every step.
            _clear_opt = (runtime_options or {}).get("clear_site_data")
            step_result = _execute_cdp_test_step(
                project_root, step, namespace,
                cdp_port, stop_event, callback,
                clear_site_data=_clear_opt,
            )
            # After first use, disable for remaining steps
            if _clear_opt and runtime_options:
                runtime_options.pop("clear_site_data", None)

        elif step.type == "checkpoint":
            step_result = _execute_checkpoint_step(
                step, namespace, plan_run, plan.mode, callback,
                sorted_steps=sorted_steps,
                step_results_map=step_results_map,
            )

        elif step.type == "conditional":
            step_result = _evaluate_conditional_step(
                step, step_results_map,
            )

        else:
            step_result = StepResult(
                step_id=step.id,
                step_name=step.name,
                step_type=step.type,
                sequence=step.sequence,
                status="failed",
                error=f"Unknown step type: {step.type}",
            )

        # ── Timing ──
        step_result.started_at = step_result.started_at or _now_iso()
        step_result.finished_at = _now_iso()
        step_result.duration_ms = int((time.monotonic() - t_step) * 1000)

        # ── Merge produced variables into namespace ──
        if step_result.variables_produced:
            namespace.update(step_result.variables_produced)

        # ── Record result ──
        result.step_results.append(step_result)
        step_results_map[step.id] = step_result

        # ── Update counters ──
        if step_result.status == "passed":
            result.passed_steps += 1
        elif step_result.status == "failed":
            result.failed_steps += 1
        elif step_result.status == "skipped":
            result.skipped_steps += 1

        # ── Emit step done ──
        callback("plan:step_done", {
            "run_id": run_id,
            "step_id": step.id,
            "step_name": step.name,
            "step_type": step.type,
            "status": step_result.status,
            "duration_ms": step_result.duration_ms,
            "variables_produced": step_result.variables_produced,
            "error": step_result.error,
            # Drill-down data (script)
            "script_run_id": step_result.script_run_id,
            "script_exit_code": step_result.script_exit_code,
            "script_lines": step_result.script_lines[-100:],
            # Drill-down data (CDP test)
            "replay_run_id": step_result.replay_run_id,
            "replay_passed": step_result.replay_passed,
            "replay_failed": step_result.replay_failed,
            "replay_total": step_result.replay_total,
            "replay_step_results": step_result.replay_step_results,
            # Drill-down data (checkpoint)
            "checkpoint_message": step.checkpoint_message or "",
        })

        # ── Check failure ──
        if step_result.status == "failed" and not step.optional:
            result.status = "failed"
            result.error = (
                f"Step {step.sequence} ({step.name}) failed: "
                f"{step_result.error}"
            )
            break

        # ── Interactive mode: pause after every step (except the last) ──
        step_idx = sorted_steps.index(step)
        if (
            plan.mode == "interactive"
            and step.type != "checkpoint"
            and step_idx + 1 < len(sorted_steps)
        ):
            next_step_info = None
            if step_idx + 1 < len(sorted_steps):
                ns = sorted_steps[step_idx + 1]
                next_step_info = {
                    "id": ns.id,
                    "name": ns.name,
                    "type": ns.type,
                    "sequence": ns.sequence,
                    "consumes": ns.consumes,
                    "produces": ns.produces,
                }

            callback("plan:paused", {
                "run_id": run_id,
                "step_id": step.id,
                "step_name": step.name,
                "reason": "interactive",
                "message": f"Step {step.sequence} completed: {step_result.status}",
                "variables": namespace,
                "step_produced": step_result.variables_produced,
                "next_step": next_step_info,
            })

            plan_run.paused = True
            plan_run.resume_event.clear()
            plan_run.resume_event.wait()
            plan_run.paused = False

            # Apply any variable updates from the UI
            if plan_run.pending_var_updates:
                namespace.update(plan_run.pending_var_updates)
                plan_run.pending_var_updates = None

            if stop_event.is_set():
                result.status = "cancelled"
                break

            if plan_run.skip_requested:
                plan_run.skip_requested = False
                # Skip next step — handled on next iteration

            callback("plan:resumed", {
                "run_id": run_id,
                "step_id": step.id,
            })

    # ── Step 4: Finalize ──────────────────────────────────────

    # Determine final status
    if result.status == "running":
        if result.failed_steps > 0:
            result.status = "partial"
        else:
            result.status = "passed"

    result.variables = namespace
    result.finished_at = _now_iso()
    result.duration_ms = int((time.monotonic() - t_start) * 1000)

    # Kill browser if not keep_alive
    if chrome_info and not browser_config.keep_alive:
        try:
            _kill_plan_browser(chrome_info["port"])
            result.chrome_instance = None  # browser gone, don't show close button
        except Exception as exc:
            logger.warning("Failed to kill plan browser: %s", exc)

    # Update plan history
    try:
        from src.core.services.scripts.plan_storage import (
            get_plan as load_plan,
            save_plan,
        )
        stored_plan = load_plan(project_root, plan.id)
        if stored_plan:
            stored_plan.last_run_at = result.finished_at
            stored_plan.last_run_status = result.status
            stored_plan.run_count += 1
            save_plan(project_root, stored_plan)
    except Exception as exc:
        logger.warning("Failed to update plan history: %s", exc)

    # Save result
    try:
        from src.core.services.scripts.plan_storage import save_result
        save_result(project_root, result)
    except Exception as exc:
        logger.warning("Failed to save plan result: %s", exc)

    # Emit done event
    callback("plan:done", {
        "run_id": run_id,
        "plan_id": plan.id,
        "plan_name": plan.name,
        "status": result.status,
        "passed": result.passed_steps,
        "failed": result.failed_steps,
        "skipped": result.skipped_steps,
        "total": result.total_steps,
        "duration_ms": result.duration_ms,
        "variables": namespace,
    })

    logger.info(
        "Plan finished: run=%s plan=%s status=%s "
        "(%d/%d passed, %dms)",
        run_id, plan.name, result.status,
        result.passed_steps, result.total_steps,
        result.duration_ms,
    )

    return result


# ── Async Entry Point ──────────────────────────────────────────


def start_plan(
    project_root: Path,
    plan: ExecutionPlan,
    callback: callable,
    runtime_options: dict | None = None,
) -> str | PlanRunResult:
    """Start plan execution in a background thread.

    Returns the run_id string if started successfully.
    Returns a PlanRunResult with error status if startup failed.
    """
    global _active_plan

    with _plan_lock:
        if _active_plan is not None:
            if _active_plan.thread and _active_plan.thread.is_alive():
                return PlanRunResult(
                    plan_id=plan.id,
                    plan_name=plan.name,
                    status="error",
                    error="Another plan is already running",
                    finished_at=_now_iso(),
                )
            _active_plan = None

    run_id = str(uuid.uuid4())
    plan_run = _PlanRun(run_id, plan.id)

    def _run():
        global _active_plan
        try:
            execute_plan(
                project_root=project_root,
                plan=plan,
                callback=callback,
                stop_event=plan_run.stop_event,
                run_id=run_id,
                runtime_options=runtime_options,
            )
        except Exception as exc:
            logger.exception("Plan execution thread crashed: %s", exc)
            callback("plan:done", {
                "run_id": run_id,
                "plan_id": plan.id,
                "status": "failed",
                "error": f"Plan crashed: {exc}",
            })
        finally:
            with _plan_lock:
                global _active_plan
                if _active_plan and _active_plan.run_id == run_id:
                    _active_plan = None

    plan_run.thread = threading.Thread(
        target=_run,
        name=f"plan-exec-{run_id[:8]}",
        daemon=True,
    )

    with _plan_lock:
        _active_plan = plan_run

    plan_run.thread.start()
    return run_id
