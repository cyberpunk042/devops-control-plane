"""
Scripts output router — resolve output targets and inject env vars.

Decides WHERE script results go, following the priority chain:
  1. Explicit override (passed at execution time)
  2. Script's default_output (from ScriptMeta)
  3. System default (from ScriptConfig.default_output)

Also injects environment variables that scripts read to know
where to write and how to identify themselves.
"""

from __future__ import annotations

from pathlib import Path

from src.core.services.scripts.models import ScriptConfig, ScriptMeta


def resolve_output_target(
    project_root: Path,
    meta: ScriptMeta,
    override: str | None = None,
    config: ScriptConfig | None = None,
) -> Path:
    """Resolve the output directory for a script run.

    Priority:
    1. override (explicit) — if provided, use this
    2. meta.default_output — if script declares one
    3. config.default_output — system default from project.yml

    Creates the directory if it doesn't exist.
    Returns absolute path.
    """
    # 1. Explicit override
    if override:
        target = override
    # 2. Script-level default
    elif meta.default_output:
        target = meta.default_output
    # 3. System default
    else:
        cfg = config or ScriptConfig()
        target = cfg.default_output

    # Resolve relative to project root
    output_path = Path(target)
    if not output_path.is_absolute():
        output_path = project_root / output_path

    # Ensure directory exists
    output_path.mkdir(parents=True, exist_ok=True)

    return output_path


def inject_output_env(
    env: dict[str, str],
    output_path: Path,
    meta: ScriptMeta,
    project_root: Path,
    run_id: str = "",
    stream_id: str = "",
) -> dict[str, str]:
    """Inject output-related environment variables for the script subprocess.

    Sets:
      SCRIPT_OUTPUT_DIR    = absolute path to output directory
      SCRIPT_OUTPUT_FORMAT = default format (first in meta.output_formats, or "markdown")
      SCRIPT_PROJECT_ROOT  = project root path
      SCRIPT_ID            = script identifier
      SCRIPT_RUN_ID        = run identifier (for correlation)
      SCRIPT_STREAM_ID     = stream identifier (for event correlation)

    The script reads these to know where to write and how to identify itself.
    Does NOT mutate the input dict — returns a new dict with injected vars.
    """
    # Determine default output format
    output_format = meta.output_formats[0] if meta.output_formats else "markdown"

    result = dict(env)
    result["SCRIPT_OUTPUT_DIR"] = str(output_path.resolve())
    result["SCRIPT_OUTPUT_FORMAT"] = output_format
    result["SCRIPT_PROJECT_ROOT"] = str(project_root.resolve())
    result["SCRIPT_ID"] = meta.id
    result["SCRIPT_RUN_ID"] = run_id
    result["SCRIPT_STREAM_ID"] = stream_id

    return result
