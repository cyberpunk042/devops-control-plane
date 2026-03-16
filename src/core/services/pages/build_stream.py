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

import uuid

from src.core.services.events.emit import emit_event
from src.core.services.pages_builders import get_builder
from .engine import (
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
        emit_event("pages.build.failed", summary=f"Build failed: {name} — segment not found",
                    status="error", detail={"segment": name, "error": "segment not found"})
        yield {"type": "error", "message": f"Segment not found: {name}"}
        return

    builder = get_builder(segment.builder)
    if builder is None or not builder.detect():
        emit_event("pages.build.failed",
                    summary=f"Build failed: {name} — builder '{segment.builder}' not available",
                    status="error",
                    detail={"segment": name, "builder": segment.builder, "error": "builder not available"})
        yield {"type": "error", "message": f"Builder '{segment.builder}' not available"}
        return

    source_path = (project_root / segment.source).resolve()
    if not source_path.is_dir():
        # Check if this is a standalone smart folder (virtual source)
        from src.core.services.config_ops import read_config
        cfg = read_config(project_root).get("config", {})
        smart_list = cfg.get("smart_folders", [])
        is_virtual = any(
            sf.get("name") == segment.source and sf.get("target") == sf.get("name")
            for sf in smart_list
        )
        if not is_virtual:
            emit_event("pages.build.failed",
                        summary=f"Build failed: {name} — source not found: {segment.source}",
                        status="error",
                        detail={"segment": name, "error": f"source not found: {segment.source}"})
            yield {"type": "error", "message": f"Source not found: {segment.source}"}
            return
        # Virtual source — builder will stage from smart folder sources
        source_path = project_root / segment.source

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

    # Set segment on builder so dynamic pipeline_stages() works
    # (CustomBuilder reads stages from segment config)
    if hasattr(builder, '_segment'):
        builder._segment = segment

    stages_info = builder.pipeline_stages()
    chain_id = f"pages-build:{uuid.uuid4().hex[:8]}"

    emit_event(
        "pages.build.started", chain_id,
        f"Build started: {name} ({segment.builder})",
        detail={"segment": name, "builder": segment.builder,
                "stages": len(stages_info)},
    )

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
            emit_event(
                "pages.build.stage.done", chain_id,
                f"Stage done: {si.label} ({stage_ms}ms)",
                detail={"segment": name, "stage": si.name,
                        "label": si.label, "duration_ms": stage_ms},
                duration_ms=stage_ms,
            )
            yield {
                "type": "stage_done", "stage": si.name,
                "label": si.label, "duration_ms": stage_ms,
            }
        else:
            emit_event(
                "pages.build.stage.failed", chain_id,
                f"Stage failed: {si.label} — {error[:80]}",
                detail={"segment": name, "stage": si.name,
                        "label": si.label, "error": error[:200],
                        "duration_ms": stage_ms},
                status="error", duration_ms=stage_ms,
            )
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

    completed_stages = [s for s in stage_results if s["status"] == "done"]
    failed_stages = [s for s in stage_results if s["status"] == "error"]

    if all_ok:
        summary = f"Build complete: {name} — {len(completed_stages)} stages ({total_ms}ms)"
    else:
        fail_name = failed_stages[0]["label"] if failed_stages else "?"
        summary = f"Build failed: {name} — {fail_name}"

    emit_event(
        "pages.build.completed" if all_ok else "pages.build.failed",
        chain_id, summary,
        detail={
            "segment": name, "builder": segment.builder,
            "stages_completed": len(completed_stages),
            "stages_failed": len(failed_stages),
            "total_stages": len(stages_info),
            "duration_ms": total_ms,
            "serve_url": serve_url,
        },
        status="ok" if all_ok else "error",
        duration_ms=total_ms,
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
