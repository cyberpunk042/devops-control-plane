"""
Scripts execution endpoints — run, stream, packages, status.

Routes registered on ``scripts_bp`` from the parent package.

Endpoints:
    POST /scripts/run               — execute a script (synchronous result)
    POST /scripts/run/stream        — SSE streamed execution (same pattern as
                                      artifacts build/stream)
    GET  /scripts/packages          — list Python packages for scope picker
    GET  /scripts/status/<run_id>   — run status (poll alternative)
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path

from flask import Response, jsonify, request

from src.core.services.events.tracked import tracked
from src.ui.web.helpers import project_root as _project_root

from . import scripts_bp

logger = logging.getLogger(__name__)


# ── Run a script (synchronous) ────────────────────────────────


@scripts_bp.route("/scripts/run", methods=["POST"])
@tracked("script.executed")
def scripts_run():
    """Execute a script with parameters (synchronous).

    Request body (JSON):
        {
            "script_id": "generators/class_diagrams",
            "params": {"scope": "core.services.vault"},
            "output": "docs/diagrams/"  // optional override
        }
    """
    from src.core.services.scripts.executor import execute_script

    root = _project_root()
    data = request.get_json(silent=True) or {}

    script_id = data.get("script_id")
    if not script_id:
        return jsonify({"ok": False, "error": "script_id is required"}), 400

    params = data.get("params", {})
    output_target = data.get("output")

    result = execute_script(
        root,
        script_id,
        params=params,
        output_target=output_target,
    )

    status_code = 200 if result["ok"] else 500
    return jsonify(result), status_code


# ── Run a script (SSE streaming) ──────────────────────────────


@scripts_bp.route("/scripts/run/stream", methods=["POST"])
def scripts_run_stream():
    """Execute a script with SSE streaming output.

    Same pattern as ``/api/artifacts/build/<name>/stream``:
    - POST with json body ``{script_id, params, output}``
    - Returns ``text/event-stream``
    - Events: pipeline_start, log, pipeline_done

    The client connects with ``fetch()`` + ``response.body.getReader()``
    and receives line-by-line output as ``data: {JSON}\n\n`` frames.
    """
    from src.core.services.scripts.executor import execute_script
    from src.core.services.scripts.registry import get_script

    root = _project_root()
    data = request.get_json(silent=True) or {}

    script_id = data.get("script_id")
    if not script_id:
        return jsonify({"ok": False, "error": "script_id is required"}), 400

    meta = get_script(root, script_id)
    if meta is None:
        return jsonify({"ok": False, "error": f"Script '{script_id}' not found"}), 404

    params = data.get("params", {})
    output_target = data.get("output")

    def _sse(event_type: str, **kw) -> str:
        """Format one SSE frame."""
        payload = {"type": event_type, **kw}
        return f"data: {json.dumps(payload)}\n\n"

    def generate():
        # ── pipeline_start ──
        stages = [
            {"name": "validate", "label": "Validating parameters"},
            {"name": "execute", "label": f"Running {meta.name}"},
            {"name": "capture", "label": "Capturing output"},
        ]
        yield _sse("pipeline_start", stages=stages, script_id=script_id,
                    label=meta.name)

        pipeline_start = time.monotonic()
        pipeline_start_wall = time.time()    # wall-clock for mtime comparison

        # ── validate stage ──
        yield _sse("stage_start", stage="validate",
                    label="Validating parameters")

        from src.core.services.scripts.executor import (
            _validate_params,
            _check_tools,
        )

        tools_ok, missing_tools = _check_tools(meta)
        if not tools_ok:
            yield _sse("log", stage="validate",
                       line=f"❌ Missing tools: {', '.join(missing_tools)}")
            yield _sse("stage_error", stage="validate",
                       error=f"Missing tools: {', '.join(missing_tools)}")
            total_ms = int((time.monotonic() - pipeline_start) * 1000)
            yield _sse("pipeline_done", ok=False, total_ms=total_ms,
                       error=f"Missing tools: {', '.join(missing_tools)}")
            return

        params_ok, missing_params = _validate_params(meta, params)
        if not params_ok:
            yield _sse("log", stage="validate",
                       line=f"❌ Missing params: {', '.join(missing_params)}")
            yield _sse("stage_error", stage="validate",
                       error=f"Missing params: {', '.join(missing_params)}")
            total_ms = int((time.monotonic() - pipeline_start) * 1000)
            yield _sse("pipeline_done", ok=False, total_ms=total_ms,
                       error=f"Missing params: {', '.join(missing_params)}")
            return

        yield _sse("log", stage="validate", line="✓ All parameters valid")
        yield _sse("log", stage="validate",
                   line=f"✓ Script: {meta.name} ({meta.language})")
        yield _sse("stage_done", stage="validate", duration_ms=0)

        # ── execute stage (the actual script run) ──
        yield _sse("stage_start", stage="execute",
                    label=f"Running {meta.name}")

        exec_start = time.monotonic()

        # Run the script — execute_script calls stream_run internally
        # which publishes to event_bus, but we also need the result
        result = execute_script(
            root,
            script_id,
            params=params,
            output_target=output_target,
        )

        exec_ms = int((time.monotonic() - exec_start) * 1000)

        # Stream captured output lines
        lines = result.get("lines", [])
        for line in lines:
            yield _sse("log", stage="execute", line=line)

        if result["ok"]:
            yield _sse("stage_done", stage="execute", duration_ms=exec_ms)
        else:
            yield _sse("stage_error", stage="execute",
                       error=result.get("error", "Script failed"),
                       duration_ms=exec_ms)

        # ── capture stage (report results) ──
        yield _sse("stage_start", stage="capture", label="Capturing output")

        output_path = result.get("output_path")
        if output_path:
            yield _sse("log", stage="capture",
                       line=f"📁 Output: {output_path}")
        run_id = result.get("run_id", "")
        if run_id:
            yield _sse("log", stage="capture",
                       line=f"📋 Run ID: {run_id}")
        stream_id = result.get("stream_id", "")
        if stream_id:
            yield _sse("log", stage="capture",
                       line=f"🔗 Stream ID: {stream_id}")

        yield _sse("stage_done", stage="capture", duration_ms=0)

        # ── pipeline_done ──
        total_ms = int((time.monotonic() - pipeline_start) * 1000)

        # Build relative output path + list files for frontend navigation
        output_relative = ""
        output_files = []
        if output_path:
            try:
                abs_out = Path(output_path).resolve()
                output_relative = str(abs_out.relative_to(root.resolve()))
                # Only report files created/modified by THIS run
                if abs_out.is_dir():
                    output_files = sorted(
                        str(f.relative_to(root.resolve()))
                        for f in abs_out.iterdir()
                        if f.is_file() and f.stat().st_mtime >= pipeline_start_wall
                    )
            except (ValueError, OSError):
                pass

        yield _sse("pipeline_done",
                    ok=result["ok"],
                    total_ms=total_ms,
                    exit_code=result.get("exit_code", -1),
                    output_path=output_path,
                    output_relative=output_relative,
                    output_files=output_files,
                    run_id=run_id,
                    line_count=len(lines),
                    error=result.get("error"),
                    stages=[
                        {"name": "validate", "status": "done"},
                        {"name": "execute",
                         "status": "done" if result["ok"] else "error"},
                        {"name": "capture", "status": "done"},
                    ])

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── Python packages (for scope picker) ────────────────────────


@scripts_bp.route("/scripts/packages")
def scripts_packages():
    """List Python packages under src/ for the scope picker.

    Returns a flat list of dotted package paths (e.g. core.services.vault)
    and a nested tree structure for tree-based UI pickers.
    """
    root = _project_root()
    src_dir = root / "src"

    packages = []
    tree: dict = {}

    if src_dir.is_dir():
        for init in sorted(src_dir.rglob("__init__.py")):
            try:
                pkg = init.parent.relative_to(src_dir)
            except ValueError:
                continue
            dotted = str(pkg).replace("/", ".")
            if dotted == ".":
                continue
            packages.append(dotted)

            # Build tree
            parts = dotted.split(".")
            node = tree
            for part in parts:
                if part not in node:
                    node[part] = {}
                node = node[part]

    return jsonify({
        "ok": True,
        "packages": packages,
        "tree": tree,
        "total": len(packages),
    })


# ── Run status (poll) ──────────────────────────────────────────


@scripts_bp.route("/scripts/status/<run_id>")
def scripts_status(run_id: str):
    """Get status of a running or completed script execution."""
    from src.core.services.run_tracker import get_run_local

    root = _project_root()
    run = get_run_local(root, run_id)

    if run is None:
        return jsonify({"ok": False, "error": f"Run '{run_id}' not found"}), 404

    return jsonify({
        "ok": True,
        "run": run,
    })
