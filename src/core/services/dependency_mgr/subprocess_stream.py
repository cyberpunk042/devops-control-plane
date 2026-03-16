"""
Streaming subprocess — run a command and yield output line-by-line.

Generator-based.  No HTTP, Flask, or event_bus dependency.
The pipeline wraps this; the SSE route wraps the pipeline.

Similar to ``tool_install/execution/subprocess_runner.py:_run_subprocess_streaming``
but without sudo handling, with typed output (``SubprocessChunk`` instead of
raw dicts), and optional separate stderr streaming.

Usage::

    for chunk in stream_subprocess(["pip", "install", "-r", "requirements.txt"],
                                   cwd=project_root):
        if chunk.type == "line":
            print(chunk.line)
        elif chunk.type == "done":
            print(f"exit={chunk.exit_code} ok={chunk.ok}")
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Iterator

from .models import SubprocessChunk

logger = logging.getLogger(__name__)


def stream_subprocess(
    cmd: list[str],
    *,
    cwd: Path | str | None = None,
    env: dict[str, str] | None = None,
    timeout: int = 300,
    merge_stderr: bool = True,
) -> Iterator[SubprocessChunk]:
    """Run a command and yield output line-by-line.

    Generator-based, transport-agnostic.  The pipeline calls this;
    the SSE route wraps the pipeline.

    Args:
        cmd: Command argument list (for ``subprocess.Popen``).
        cwd: Working directory.  ``None`` = inherit.
        env: Full environment dict.  ``None`` = inherit ``os.environ``.
            Caller is responsible for merging overrides before passing.
        timeout: Maximum runtime in seconds.  Process is killed on timeout.
        merge_stderr: If ``True``, stderr merges into the stdout stream
            (all chunks have ``stream="merged"``).  If ``False``, stderr
            lines are yielded separately with ``stream="stderr"``.

    Yields:
        ``SubprocessChunk`` — either ``type="line"`` for each output line,
        or ``type="done"`` as the final sentinel with exit code and timing.
    """
    cwd_str = str(cwd) if cwd is not None else None

    # ── Launch process ────────────────────────────────────────
    start = time.monotonic()
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT if merge_stderr else subprocess.PIPE,
            text=True,
            bufsize=1,           # Line-buffered
            cwd=cwd_str,
            env=env,
        )
    except FileNotFoundError:
        yield SubprocessChunk(
            type="done", ok=False, exit_code=-1,
            error=f"Command not found: {cmd[0]}",
            elapsed_ms=int((time.monotonic() - start) * 1000),
        )
        return
    except OSError as exc:
        yield SubprocessChunk(
            type="done", ok=False, exit_code=-1,
            error=f"Failed to start: {exc}",
            elapsed_ms=int((time.monotonic() - start) * 1000),
        )
        return

    # ── Stream stdout ─────────────────────────────────────────
    try:
        if proc.stdout:
            for raw_line in proc.stdout:
                # Timeout check inside the read loop (same pattern
                # as stream_subprocess.py:stream_run)
                elapsed = time.monotonic() - start
                if elapsed > timeout:
                    proc.kill()
                    proc.wait()
                    yield SubprocessChunk(
                        type="done", ok=False, exit_code=-1,
                        error=f"Timed out after {timeout}s",
                        elapsed_ms=int(elapsed * 1000),
                    )
                    return

                yield SubprocessChunk(
                    type="line",
                    line=raw_line.rstrip("\n\r"),
                    stream="merged" if merge_stderr else "stdout",
                )

        # ── Stream stderr separately (if not merged) ──────────
        if not merge_stderr and proc.stderr:
            for raw_line in proc.stderr:
                yield SubprocessChunk(
                    type="line",
                    line=raw_line.rstrip("\n\r"),
                    stream="stderr",
                )

        # ── Wait for exit ─────────────────────────────────────
        remaining = max(1, timeout - int(time.monotonic() - start))
        proc.wait(timeout=remaining)

    except subprocess.TimeoutExpired:
        try:
            proc.kill()
            proc.wait()
        except Exception:
            pass
        yield SubprocessChunk(
            type="done", ok=False, exit_code=-1,
            error=f"Timed out after {timeout}s",
            elapsed_ms=int((time.monotonic() - start) * 1000),
        )
        return
    except Exception as exc:
        logger.exception("Streaming subprocess error: %s", cmd)
        try:
            proc.kill()
            proc.wait()
        except Exception:
            pass
        yield SubprocessChunk(
            type="done", ok=False, exit_code=-1,
            error=str(exc),
            elapsed_ms=int((time.monotonic() - start) * 1000),
        )
        return

    # ── Done sentinel ─────────────────────────────────────────
    elapsed_ms = int((time.monotonic() - start) * 1000)
    exit_code = proc.returncode
    yield SubprocessChunk(
        type="done",
        ok=exit_code == 0,
        exit_code=exit_code,
        elapsed_ms=elapsed_ms,
        error="" if exit_code == 0 else f"Exit code {exit_code}",
    )
