"""
Scripts executor — command building, validation, and script execution.

Takes a script ID + parameters, validates prerequisites, builds the
subprocess command, wraps in tracked_run() for ledger integration,
and calls stream_run() for real-time output streaming via event bus.

Uses existing infrastructure:
  - stream_subprocess.stream_run() for subprocess + SSE
  - run_tracker.tracked_run() for run lifecycle
  - event_bus for real-time events
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
from pathlib import Path
from typing import Any

from src.core.services.scripts.config import load_scripts_config
from src.core.services.scripts.models import ScriptConfig, ScriptMeta
from src.core.services.scripts.output_router import (
    inject_output_env,
    resolve_output_target,
)
from src.core.services.scripts.registry import get_script

logger = logging.getLogger(__name__)


# ── Command Building ────────────────────────────────────────────────


def _build_command(
    meta: ScriptMeta,
    params: dict[str, str],
    config: ScriptConfig | None = None,
) -> list[str]:
    """Build the subprocess command for a script.

    Language → Command mapping:
        python      → [sys.executable, script_path, --param1, val1, ...]
        bash        → ["bash", script_path, --param1, val1, ...]
        powershell  → ["pwsh", "-File", script_path, -param1, val1, ...]
        executable  → [script_path, --param1, val1, ...]

    IMPORTANT: For Python scripts, sys.executable is the project venv's python.
    This satisfies the hard rule: "NEVER USE PYTHON OUTSIDE THE VENV OF THE PROJECT"

    config.execution_venv_python can override sys.executable.
    If "auto", use sys.executable. Otherwise, use the explicit path.
    """
    cfg = config or ScriptConfig()
    script_path = meta.path

    # Determine Python executable
    if cfg.execution_venv_python == "auto":
        python_exe = sys.executable
    else:
        python_exe = cfg.execution_venv_python

    # Build base command by language
    if meta.language == "python":
        cmd = [python_exe, script_path]
    elif meta.language == "bash":
        cmd = ["bash", script_path]
    elif meta.language == "powershell":
        cmd = ["pwsh", "-File", script_path]
    elif meta.language == "executable":
        cmd = [script_path]
    else:
        # Fallback — treat as python
        cmd = [python_exe, script_path]

    # Build a lookup of parameter types from metadata
    param_types = {p.name: p.type for p in meta.parameters}

    # Append parameters as CLI flags
    for key, value in params.items():
        # Skip empty/null-like values — lets the script use its own default
        if value is None or value == "" or value.lower() == "none":
            continue

        # Normalize: underscores to dashes for CLI convention
        flag_name = key.replace("_", "-")

        # Boolean params → store_true flags (present or absent, no value)
        if param_types.get(key) == "boolean" or param_types.get(flag_name) == "boolean":
            if value.lower() in ("true", "1", "yes"):
                # Just the flag, no value (argparse store_true)
                if meta.language == "powershell":
                    cmd.append(f"-{flag_name}")
                else:
                    cmd.append(f"--{flag_name}")
            # "false" → don't add the flag at all
            continue

        if meta.language == "powershell":
            # PowerShell uses -param format
            cmd.extend([f"-{flag_name}", value])
        else:
            cmd.extend([f"--{flag_name}", value])

    return cmd


# ── Tool Availability ───────────────────────────────────────────────


def _check_tools(meta: ScriptMeta) -> tuple[bool, list[str]]:
    """Check that all required external tools are available.

    Returns (all_ok, missing_tools).

    Checks:
    - python: always available (we ARE the venv)
    - bash: shutil.which("bash")
    - pwsh: shutil.which("pwsh")
    - Any tool name: shutil.which(tool_name)
    """
    if not meta.requires_tools:
        return True, []

    missing: list[str] = []
    for tool in meta.requires_tools:
        tool_lower = tool.lower().strip()
        # Skip markers like "(none)"
        if not tool_lower or tool_lower.startswith("("):
            continue
        # Python is always available in the venv
        if tool_lower in ("python", "python3"):
            continue
        if not shutil.which(tool_lower):
            missing.append(tool)

    return len(missing) == 0, missing


# ── Parameter Validation ────────────────────────────────────────────


def _validate_params(
    meta: ScriptMeta,
    params: dict[str, str],
) -> tuple[bool, list[str]]:
    """Validate that required parameters are provided.

    Returns (all_ok, missing_params).
    """
    missing: list[str] = []
    for param_def in meta.parameters:
        if param_def.required and param_def.name not in params:
            missing.append(param_def.name)
    return len(missing) == 0, missing


# ── Execution ───────────────────────────────────────────────────────


def execute_script(
    project_root: Path,
    script_id: str,
    *,
    params: dict[str, str] | None = None,
    output_target: str | None = None,
) -> dict[str, Any]:
    """Execute a registered script.

    Flow:
    1. Load config from project.yml
    2. Resolve script from registry
    3. Validate prerequisites (tool availability, required params)
    4. Build command
    5. Resolve output target (OutputRouter)
    6. Build environment variables
    7. Wrap in tracked_run() (ledger integration)
    8. Call stream_run() (subprocess + event streaming)
    9. Return result dict

    Returns:
        {
            "ok": bool,
            "run_id": str,
            "stream_id": str,
            "exit_code": int,
            "output_path": str | None,
            "duration_ms": int,
            "lines": list[str],
            "error": str | None,
        }
    """
    params = params or {}

    # 1. Load config
    config = load_scripts_config(project_root)

    # 2. Resolve script
    meta = get_script(project_root, script_id)
    if meta is None:
        return {
            "ok": False,
            "run_id": "",
            "stream_id": "",
            "exit_code": -1,
            "output_path": None,
            "duration_ms": 0,
            "lines": [],
            "error": f"Script '{script_id}' not found in registry",
        }

    # 3a. Validate tools
    tools_ok, missing_tools = _check_tools(meta)
    if not tools_ok:
        return {
            "ok": False,
            "run_id": "",
            "stream_id": "",
            "exit_code": -1,
            "output_path": None,
            "duration_ms": 0,
            "lines": [],
            "error": f"Missing required tools: {', '.join(missing_tools)}",
        }

    # 3b. Validate params
    params_ok, missing_params = _validate_params(meta, params)
    if not params_ok:
        return {
            "ok": False,
            "run_id": "",
            "stream_id": "",
            "exit_code": -1,
            "output_path": None,
            "duration_ms": 0,
            "lines": [],
            "error": f"Missing required parameters: {', '.join(missing_params)}",
        }

    # 4. Build command
    cmd = _build_command(meta, params, config)

    # 5. Resolve output target
    output_path = resolve_output_target(project_root, meta, output_target, config)

    # 6. Generate stream ID
    from src.core.services.stream_subprocess import make_stream_id
    stream_id = make_stream_id("script")

    # Build environment — merge parent env with script-specific vars
    env = dict(os.environ)
    env = inject_output_env(env, output_path, meta, project_root)
    # run_id and stream_id will be patched after tracked_run creates them

    # 7 & 8. Execute with tracking
    from src.core.services.run_tracker import tracked_run
    from src.core.services.stream_subprocess import stream_run

    with tracked_run(
        project_root,
        "script",
        f"script:{script_id}",
        summary=meta.name,
    ) as run_bag:
        run_id = run_bag["run_id"]

        # Patch run_id and stream_id into env
        env["SCRIPT_RUN_ID"] = run_id
        env["SCRIPT_STREAM_ID"] = stream_id

        # Execute the subprocess
        stream_result = stream_run(
            cmd,
            cwd=project_root,
            stream_id=stream_id,
            timeout=meta.timeout,
            env=env,
            label=meta.name,
        )

        # Update run bag with results
        run_bag["status"] = "ok" if stream_result["ok"] else "failed"
        run_bag["summary"] = meta.name
        run_bag["metadata"] = {
            "script_id": script_id,
            "stream_id": stream_id,
            "output_path": str(output_path),
            "exit_code": stream_result.get("exit_code", -1),
            "parameters": params,
        }

    # 9. Return result
    return {
        "ok": stream_result["ok"],
        "run_id": run_id,
        "stream_id": stream_id,
        "exit_code": stream_result.get("exit_code", -1),
        "output_path": str(output_path),
        "duration_ms": run_bag.get("duration_ms", 0),
        "lines": stream_result.get("lines", []),
        "error": stream_result.get("error"),
    }
