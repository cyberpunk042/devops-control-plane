"""
Streaming subprocess — runs commands with real-time line-by-line SSE output.

Long-running operations (git gc, history reset, filter-repo) use this
instead of ``subprocess.run()`` so the UI can show real-time progress
in an inline terminal panel.

Usage::

    from src.core.services.stream_subprocess import stream_run

    result = stream_run(
        ["git", "gc", "--aggressive"],
        cwd=project_root,
        stream_id="git-gc-1709500000",
        timeout=300,
    )
    # result = {"ok": True, "exit_code": 0, "stream_id": "...", "lines": [...]}
"""

from __future__ import annotations

import logging
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def make_stream_id(prefix: str = "op") -> str:
    """Generate a unique stream ID for a streaming operation.

    Format: ``<prefix>-<timestamp>-<short_uuid>``
    Example: ``git-gc-1709500000-a1b2``
    """
    ts = int(time.time())
    short = uuid.uuid4().hex[:4]
    return f"{prefix}-{ts}-{short}"


def stream_run(
    cmd: list[str],
    *,
    cwd: Path,
    stream_id: str | None = None,
    timeout: int = 300,
    env: dict[str, str] | None = None,
    label: str = "",
) -> dict[str, Any]:
    """Run a command with real-time line-by-line SSE streaming.

    Each line of stdout/stderr is published as a ``stream:line`` event
    on the event bus.  When the command finishes, a ``stream:done``
    event is published with the exit code.

    Args:
        cmd: Command to run (e.g. ``["git", "gc", "--aggressive"]``).
        cwd: Working directory.
        stream_id: Unique stream identifier (auto-generated if not provided).
        timeout: Maximum runtime in seconds (default 300).
        env: Optional environment variables (merged with parent env).
        label: Human-readable label for the operation (e.g. "Git GC").

    Returns::

        {"ok": True,  "exit_code": 0, "stream_id": "...", "lines": [...]}
        {"ok": False, "exit_code": 1, "stream_id": "...", "error": "...", "lines": [...]}
    """
    from src.core.services.event_bus import bus

    if stream_id is None:
        stream_id = make_stream_id()

    lines: list[str] = []
    label = label or " ".join(cmd[:3])

    # Publish start event
    bus.publish("stream:start", key=stream_id, data={
        "stream_id": stream_id,
        "label": label,
        "cmd": " ".join(cmd),
    })

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # merge stderr into stdout
            stdin=subprocess.DEVNULL,
            text=True,
            bufsize=1,  # line-buffered
            env=env,
        )
    except FileNotFoundError:
        error = f"Command not found: {cmd[0]}"
        bus.publish("stream:done", key=stream_id, data={
            "stream_id": stream_id,
            "exit_code": -1,
            "ok": False,
            "error": error,
        })
        return {"ok": False, "exit_code": -1, "stream_id": stream_id, "error": error, "lines": []}
    except OSError as exc:
        error = f"Failed to start command: {exc}"
        bus.publish("stream:done", key=stream_id, data={
            "stream_id": stream_id,
            "exit_code": -1,
            "ok": False,
            "error": error,
        })
        return {"ok": False, "exit_code": -1, "stream_id": stream_id, "error": error, "lines": []}

    start = time.monotonic()

    try:
        assert proc.stdout is not None  # guaranteed by PIPE
        for raw_line in proc.stdout:
            elapsed = time.monotonic() - start
            if elapsed > timeout:
                proc.kill()
                proc.wait()
                error = f"Timeout after {timeout}s"
                bus.publish("stream:line", key=stream_id, data={
                    "stream_id": stream_id,
                    "line": f"⚠ {error}",
                    "n": len(lines),
                })
                bus.publish("stream:done", key=stream_id, data={
                    "stream_id": stream_id,
                    "exit_code": -1,
                    "ok": False,
                    "error": error,
                })
                return {
                    "ok": False, "exit_code": -1,
                    "stream_id": stream_id, "error": error, "lines": lines,
                }

            line = raw_line.rstrip("\n\r")
            lines.append(line)

            bus.publish("stream:line", key=stream_id, data={
                "stream_id": stream_id,
                "line": line,
                "n": len(lines),
            })

        proc.wait(timeout=max(1, timeout - int(time.monotonic() - start)))

    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        error = f"Timeout after {timeout}s"
        bus.publish("stream:done", key=stream_id, data={
            "stream_id": stream_id,
            "exit_code": -1,
            "ok": False,
            "error": error,
        })
        return {
            "ok": False, "exit_code": -1,
            "stream_id": stream_id, "error": error, "lines": lines,
        }

    exit_code = proc.returncode
    ok = exit_code == 0

    bus.publish("stream:done", key=stream_id, data={
        "stream_id": stream_id,
        "exit_code": exit_code,
        "ok": ok,
        "line_count": len(lines),
    })

    result: dict[str, Any] = {
        "ok": ok,
        "exit_code": exit_code,
        "stream_id": stream_id,
        "lines": lines,
    }
    if not ok:
        result["error"] = "\n".join(lines[-5:]) if lines else f"Exit code {exit_code}"

    logger.info(
        "stream_run complete: stream_id=%s exit=%d lines=%d",
        stream_id, exit_code, len(lines),
    )
    return result
