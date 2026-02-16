"""
Pages build stream — SSE streaming for segment builds.

Runs the builder pipeline with real-time SSE event streaming,
yielding stage-by-stage progress and results.
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from src.core.services.pages_builders import get_builder
from src.core.services.pages_engine import (
    PAGES_WORKSPACE,
    ensure_gitignore,
    get_segment,
)


def build_segment_stream(
    project_root: Path,
    name: str,
    *,
    clean: bool = False,
    wipe: bool = False,
    no_minify: bool = False,
):
    """Generator that yields SSE event dicts for a build pipeline.

    Caller wraps events in ``data: {json}\\n\\n`` for SSE transport.

    Args:
        project_root: Project root.
        name: Segment name.
        clean: If True, pass clean=True to builder config.
        wipe: If True, nuke entire workspace before building.
        no_minify: If True, set build_mode to no-minify.

    Yields:
        Dicts with 'type' key: pipeline_start, stage_start, log,
        stage_done, stage_error, pipeline_done, error.
    """
    ensure_gitignore(project_root)

    segment = get_segment(project_root, name)
    if segment is None:
        yield {"type": "error", "message": f"Segment not found: {name}"}
        return

    builder = get_builder(segment.builder)
    if builder is None or not builder.detect():
        yield {"type": "error", "message": f"Builder '{segment.builder}' not available"}
        return

    source_path = (project_root / segment.source).resolve()
    if not source_path.is_dir():
        yield {"type": "error", "message": f"Source not found: {segment.source}"}
        return

    segment.source = str(source_path)
    workspace = project_root / PAGES_WORKSPACE / name

    if wipe and workspace.is_dir():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True, exist_ok=True)

    if clean:
        segment.config["clean"] = True
    if no_minify:
        segment.config["build_mode"] = "no-minify"

    pipeline_start = time.monotonic()
    stages_info = builder.pipeline_stages()

    yield {
        "type": "pipeline_start",
        "segment": name,
        "builder": segment.builder,
        "stages": [{"name": s.name, "label": s.label} for s in stages_info],
    }

    stage_results = []
    all_ok = True

    for si in stages_info:
        yield {"type": "stage_start", "stage": si.name, "label": si.label}

        stage_start = time.monotonic()
        error = ""

        try:
            for line in builder.run_stage(si.name, segment, workspace):
                yield {"type": "log", "line": line, "stage": si.name}
            status = "done"
        except RuntimeError as e:
            error = str(e)
            status = "error"
            all_ok = False
        except Exception as e:
            error = f"Unexpected: {e}"
            status = "error"
            all_ok = False

        stage_ms = int((time.monotonic() - stage_start) * 1000)
        stage_results.append({
            "name": si.name,
            "label": si.label,
            "status": status,
            "duration_ms": stage_ms,
            "error": error,
        })

        if status == "done":
            yield {
                "type": "stage_done", "stage": si.name,
                "label": si.label, "duration_ms": stage_ms,
            }
        else:
            yield {
                "type": "stage_error", "stage": si.name,
                "label": si.label, "error": error, "duration_ms": stage_ms,
            }
            remaining = stages_info[stages_info.index(si) + 1:]
            for rem in remaining:
                stage_results.append({
                    "name": rem.name, "label": rem.label,
                    "status": "skipped", "duration_ms": 0, "error": "",
                })
            break

    total_ms = int((time.monotonic() - pipeline_start) * 1000)

    serve_url = ""
    if all_ok:
        output = builder.output_dir(workspace)
        serve_url = f"/pages/site/{name}/"

        meta = {
            "segment": name,
            "builder": segment.builder,
            "built_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "duration_ms": total_ms,
            "output_dir": str(output),
            "serve_url": serve_url,
        }
        (workspace / "build.json").write_text(
            json.dumps(meta, indent=2), encoding="utf-8",
        )

    yield {
        "type": "pipeline_done",
        "ok": all_ok,
        "segment": name,
        "total_ms": total_ms,
        "serve_url": serve_url,
        "stages": stage_results,
        "duration_ms": total_ms,
        "error": stage_results[-1]["error"] if not all_ok else "",
    }
