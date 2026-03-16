"""
Console output — human-friendly status messages.

Uses click.echo/secho for direct console output, independent of the
logging system. These messages always appear regardless of log level.

Keep messages concise and non-alarming. The console is for awareness,
not diagnostics — use logging for that.
"""

from __future__ import annotations

import sys
import time
from datetime import datetime


def _ts() -> str:
    """Short timestamp for console lines."""
    return datetime.now().strftime("%H:%M:%S")


def _write(msg: str, **kw) -> None:
    """Write to stderr (same stream as logging)."""
    try:
        import click
        click.secho(msg, err=True, **kw)
    except Exception:
        print(msg, file=sys.stderr)


# ── File system watcher ──────────────────────────────────────────

def console_fs_change(changed_dirs: list[str]) -> None:
    """FS watcher detected changes."""
    n = len(changed_dirs)
    dirs = ", ".join(changed_dirs[:3])
    suffix = f" +{n - 3} more" if n > 3 else ""
    _write(f"  {_ts()}  📂 {n} dir(s) changed: {dirs}{suffix}", fg="cyan")


def console_cycle_start(cycle_id: str) -> None:
    """Index cycle started."""
    _write(f"  {_ts()}  🔄 Index cycle started", fg="bright_black")


def console_cycle_done(cycle_id: str, nodes: int, elapsed_ms: int) -> None:
    """Index cycle completed."""
    secs = elapsed_ms / 1000
    _write(f"  {_ts()}  ✓  Index cycle done — {nodes} nodes, {secs:.1f}s", fg="green")


# ── Work queue ───────────────────────────────────────────────────

def console_worker_slow(
    worker_id: int,
    path: str,
    elapsed_s: int,
    size: int,
) -> None:
    """A worker has been running for a long time (>30s)."""
    _write(
        f"  {_ts()}  ⏳ W{worker_id} computing {path} ({elapsed_s}s, size={size})",
        fg="yellow",
    )


def console_worker_stall(
    worker_id: int,
    waiting_for: str,
    wait_s: int,
    active_workers: list[str],
) -> None:
    """Workers are blocked on capacity for an extended time (>60s)."""
    active = ", ".join(active_workers) if active_workers else "unknown"
    _write(
        f"  {_ts()}  ⚠  W{worker_id} waiting for capacity ({wait_s}s) "
        f"to run {waiting_for} — active: {active}",
        fg="red",
    )
