"""Docker shared helpers — low-level command runners.

Provides both synchronous (``run_docker``, ``run_compose``) and streaming
(``run_docker_stream``, ``run_compose_stream``) command runners.

The streaming variants use ``subprocess.Popen`` and yield output lines in
real time, suitable for SSE endpoints that need to stream progress to the
browser as docker commands execute.
"""

from __future__ import annotations

import selectors
import subprocess
from collections.abc import Generator
from pathlib import Path
from typing import Literal
import logging

logger = logging.getLogger(__name__)


# ── Synchronous runners ────────────────────────────────────────────


def run_docker(
    *args: str,
    cwd: Path,
    timeout: int = 60,
) -> subprocess.CompletedProcess[str]:
    """Run a docker command and return the result."""
    return subprocess.run(
        ["docker", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def run_compose(
    *args: str,
    cwd: Path,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    """Run a docker compose command and return the result."""
    return subprocess.run(
        ["docker", "compose", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


# ── Streaming runners (Popen-based) ───────────────────────────────
#
# Yield (source, line) tuples where source is "stdout", "stderr", or
# "exit".  The final yield is always ("exit", <returncode>).
#
# Docker compose sends progress to stderr, so we must read both
# streams concurrently using selectors to avoid deadlocks.

StreamLine = tuple[Literal["stdout", "stderr", "exit"], str | int]


def _popen_stream(
    cmd: list[str],
    *,
    cwd: Path,
    timeout: int = 600,
) -> Generator[StreamLine, None, None]:
    """Run *cmd* via Popen and yield lines from stdout/stderr in real time.

    Yields:
        ("stdout", line)  — a line from stdout (trailing newline stripped)
        ("stderr", line)  — a line from stderr (trailing newline stripped)
        ("exit", code)    — process exit code (always last)
    """
    logger.debug("Streaming command: %s (cwd=%s, timeout=%ss)", cmd, cwd, timeout)
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,  # line-buffered
    )

    sel = selectors.DefaultSelector()
    try:
        if proc.stdout:
            sel.register(proc.stdout, selectors.EVENT_READ, "stdout")
        if proc.stderr:
            sel.register(proc.stderr, selectors.EVENT_READ, "stderr")

        open_streams = 2
        while open_streams > 0:
            events = sel.select(timeout=timeout)
            if not events:
                # Timeout waiting for output — kill the process
                proc.kill()
                proc.wait()
                yield ("stderr", f"⏰ Timed out after {timeout}s — process killed")
                yield ("exit", -1)
                return

            for key, _ in events:
                source: str = key.data  # "stdout" or "stderr"
                line = key.fileobj.readline()  # type: ignore[union-attr]
                if not line:
                    # EOF on this stream
                    sel.unregister(key.fileobj)
                    open_streams -= 1
                    continue
                yield (source, line.rstrip("\n"))  # type: ignore[misc]
    finally:
        sel.close()

    proc.wait()
    yield ("exit", proc.returncode)


def run_docker_stream(
    *args: str,
    cwd: Path,
    timeout: int = 300,
) -> Generator[StreamLine, None, None]:
    """Stream a ``docker <args>`` command, yielding lines in real time."""
    yield from _popen_stream(["docker", *args], cwd=cwd, timeout=timeout)


def run_compose_stream(
    *args: str,
    cwd: Path,
    timeout: int = 600,
) -> Generator[StreamLine, None, None]:
    """Stream a ``docker compose <args>`` command, yielding lines in real time."""
    yield from _popen_stream(["docker", "compose", *args], cwd=cwd, timeout=timeout)
