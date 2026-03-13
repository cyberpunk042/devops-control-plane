"""
Index Watcher — background FS polling → mediator cascade bridge.

Polls directory mtimes every POLL_INTERVAL_S seconds.  When any
directory's mtime changes (OS updates dir mtime on child create/modify/
delete), invalidates ``index.scan`` in the mediator.  The cascade then
propagates through::

    index.scan (invalidated)
      → index.delta  → detects changed files
        → index.symbols  → re-parses only changed .py files
          → index.peek   → re-peeks only affected .md files
      → index.files, index.dirs, index.paths  → recomputed

Design decisions
────────────────
1. **Dir-level mtime polling**: checking ~241 directory mtimes is ~5x
   cheaper than checking ~1,300 file mtimes.  OS updates dir mtime when
   children change, so we get file-change detection at 1/5th the stat cost.

2. **Polling, not inotify/watchdog**: zero external dependencies, works
   reliably on WSL/Docker/NFS/CIFS where inotify is unreliable.  Cost is
   ~241 stat() calls per cycle = ~2ms.  Acceptable for a dev tool.

3. **Mediator cascade does the work**: the watcher only invalidates
   ``index.scan``.  The mediator's dependency graph handles everything
   downstream.  The watcher doesn't know about symbols or peek.

4. **Daemon thread**: same pattern as ``staleness_watcher`` — dies with
   the process.  No cleanup needed.

5. **EventBus integration**: publishes ``index:watcher:change`` events
   so the UI can show live index status (e.g., "updating..." spinner).
"""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.services.mediator.core import QueryMediator

logger = logging.getLogger(__name__)

POLL_INTERVAL_S = 5.0
"""Seconds between poll cycles."""

# Same skip rules as the index scanner — don't poll these directories
_SKIP_DIRS = frozenset({
    ".git", ".hg", ".svn",
    "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    ".venv", "venv", "env",
    "node_modules", ".next", "__next",
    ".tox", ".nox",
    "build", "dist", ".eggs", "*.egg-info",
    ".terraform",
    ".state", ".agent", ".pages",
})


def start_index_watcher(
    project_root: Path,
    mediator: "QueryMediator",
    *,
    poll_interval: float = POLL_INTERVAL_S,
) -> threading.Thread:
    """Start the index watcher daemon thread.

    Parameters
    ----------
    project_root : Path
        Project root directory.
    mediator : QueryMediator
        The mediator instance to invalidate when files change.
    poll_interval : float
        Seconds between poll cycles (default 5.0).

    Returns
    -------
    threading.Thread
        The started daemon thread.
    """
    t = threading.Thread(
        target=_poll_loop,
        args=(project_root, mediator, poll_interval),
        daemon=True,
        name="index-watcher",
    )
    t.start()
    logger.info(
        "[IndexWatcher] started (poll every %.0fs, root=%s)",
        poll_interval, project_root,
    )
    return t


def scan_dir_mtimes(project_root: Path) -> dict[str, float]:
    """Scan directory mtimes for change detection.

    Walks the project tree collecting mtime of each non-skipped
    directory.  When a file is created/modified/deleted in a
    directory, the OS updates that directory's mtime.

    Parameters
    ----------
    project_root : Path
        Project root directory.

    Returns
    -------
    dict[str, float]
        Mapping of relative dir path → mtime.
    """
    dir_mtimes: dict[str, float] = {}

    for dirpath, dirnames, _filenames in os.walk(project_root):
        # Skip hidden and known-excluded directories (in-place)
        dirnames[:] = [
            d for d in dirnames
            if not d.startswith(".") and d not in _SKIP_DIRS
        ]

        try:
            rel = os.path.relpath(dirpath, project_root)
            if rel == ".":
                rel = ""
            dir_mtimes[rel] = os.stat(dirpath).st_mtime
        except OSError:
            continue

    return dir_mtimes


def _poll_loop(
    project_root: Path,
    mediator: "QueryMediator",
    poll_interval: float,
) -> None:
    """Main poll loop — runs forever until process exits.

    On each cycle:
    1. Scan directory mtimes (~2ms for ~241 dirs)
    2. Compare against previous snapshot
    3. If any directory's mtime changed → invalidate + recompute ALL nodes
    4. First cycle always triggers full computation (warm the cache)

    Computation strategy:
    - Index nodes (9): refreshed directly (scan ~25ms, rest <5ms each,
      except symbols ~42s cold / <1ms incremental, peek ~2s cold / <100ms)
    - Detect nodes (13): dispatched to background via executor
    - Devops nodes (14): dispatched to background via executor
    - Posture nodes (6): dispatched to background via executor
    """
    last_dir_mtimes: dict[str, float] = {}
    first_cycle = True

    # Index nodes split into two tiers:
    #   FAST — must run first, sequentially (~45ms total)
    #   SLOW — can run in parallel with detect/devops/posture
    _FAST_INDEX = [
        "index.scan",      # root — scans filesystem (~25ms)
        "index.delta",     # depends on scan — diffs against prev (~5ms)
        "index.files",     # depends on scan — filename→paths map (~2ms)
        "index.dirs",      # depends on scan — dirname→paths map (~2ms)
        "index.paths",     # depends on scan — flat path set (~1ms)
        "index.classify",  # depends on scan — language/framework detection (~10ms)
    ]
    _SLOW_INDEX = [
        "index.symbols",   # depends on delta — symbol index (cold ~30s, warm <1ms)
        "index.peek",      # depends on delta+symbols+scan — peek cache (cold ~2s, warm <100ms)
        "index.stats",     # depends on all index nodes (~1ms)
    ]
    _ALL_INDEX = _FAST_INDEX + _SLOW_INDEX

    # Initial snapshot — capture baseline mtimes.
    try:
        last_dir_mtimes = scan_dir_mtimes(project_root)
        logger.debug(
            "[IndexWatcher] initial snapshot: %d dirs", len(last_dir_mtimes),
        )
    except Exception as e:
        logger.warning("[IndexWatcher] initial scan failed: %s", e)

    while True:
        time.sleep(poll_interval)

        try:
            current_dir_mtimes = scan_dir_mtimes(project_root)

            # Find directories whose mtime changed
            changed_dirs: list[str] = []

            for d, mt in current_dir_mtimes.items():
                if last_dir_mtimes.get(d) != mt:
                    changed_dirs.append(d)

            for d in last_dir_mtimes:
                if d not in current_dir_mtimes:
                    changed_dirs.append(d)

            if not changed_dirs and not first_cycle:
                continue  # nothing changed, sleep again

            last_dir_mtimes = current_dir_mtimes

            if changed_dirs:
                logger.info(
                    "[IndexWatcher] %d dirs changed, refreshing tree",
                    len(changed_dirs),
                )
                _publish_change_event(changed_dirs)

                # Invalidate index.scan → cascade clears ALL downstream caches
                mediator.put("index.scan")

            _warm = False
            if first_cycle:
                first_cycle = False
                # Check if cache is warm from disk hydration
                # MUST use peek() — get() would COMPUTE the value,
                # making _warm always True even on cold start.
                try:
                    cached_scan = mediator.peek("index.scan")
                    if cached_scan and cached_scan.get("data"):
                        _warm = True
                except Exception:
                    pass

                if _warm:
                    # Count ALL cached nodes (from disk hydration)
                    all_cached = [
                        p for p in mediator.tree.all_paths()
                        if mediator.peek(p) is not None
                    ]
                    logger.info(
                        "[IndexWatcher] first cycle — cache warm from "
                        "disk shards (%d nodes cached), skipping "
                        "index recomputation",
                        len(all_cached),
                    )
                    # Publish status showing ALL cached nodes as done
                    _publish_progress("index:cycle:start", {
                        "phase": "index",
                        "total": len(all_cached),
                        "paths": all_cached,
                    })
                    for i, path in enumerate(all_cached):
                        _publish_progress("index:node:done", {
                            "path": path,
                            "step": i + 1,
                            "total": len(all_cached),
                            "elapsed_ms": 0,
                        })
                    _publish_progress("index:cycle:done", {
                        "phase": "index",
                        "ok": len(all_cached),
                        "total": len(all_cached),
                        "elapsed_ms": 0,
                    })
                    # Fall through to Phase 2 (dispatch bg nodes)
                else:
                    logger.info(
                        "[IndexWatcher] first cycle — cold start, "
                        "full computation"
                    )

            # ── Phase 1: Fast index nodes (sequential, ~45ms) ──
            # Skipped on warm start — index nodes already cached from disk.
            if not _warm:
                _publish_progress("index:cycle:start", {
                    "phase": "index",
                    "total": len(_ALL_INDEX),
                    "paths": list(_ALL_INDEX),
                })

                t0 = time.time()
                fast_ok = 0
                for i, path in enumerate(_FAST_INDEX):
                    _publish_progress("index:node:start", {
                        "path": path,
                        "step": i + 1,
                        "total": len(_ALL_INDEX),
                    })
                    node_t0 = time.time()
                    try:
                        result = mediator.get(path, force=True)
                        node_elapsed = time.time() - node_t0
                        fast_ok += 1

                        data = result.get("data")
                        size_info = _data_size(data)

                        _publish_progress("index:node:done", {
                            "path": path,
                            "step": i + 1,
                            "total": len(_ALL_INDEX),
                            "elapsed_ms": round(node_elapsed * 1000),
                            **size_info,
                        })
                    except Exception as exc:
                        node_elapsed = time.time() - node_t0
                        logger.warning(
                            "[IndexWatcher] index compute %s failed: %s",
                            path, exc,
                        )
                        _publish_progress("index:node:failed", {
                            "path": path,
                            "step": i + 1,
                            "total": len(_ALL_INDEX),
                            "elapsed_ms": round(node_elapsed * 1000),
                            "error": str(exc)[:200],
                        })

                fast_elapsed = time.time() - t0
                logger.info(
                    "[IndexWatcher] fast index: %d/%d nodes in %.1fms",
                    fast_ok, len(_FAST_INDEX), fast_elapsed * 1000,
                )

            # ── Phase 2: Dispatch background work ──────────────────────
            # Everything goes to the thread pool executor so no single
            # thread hogs the GIL.  The watcher thread is free.
            try:
                all_paths = mediator.tree.all_paths()
                bg_paths = [
                    p for p in all_paths
                    if p.startswith(("detect.", "devops.", "posture."))
                ]

                if _warm:
                    # Warm start: slow index nodes already cached from disk.
                    # Only dispatch detect/devops/posture.
                    all_dispatch = bg_paths
                else:
                    # Cold start: also dispatch slow index nodes
                    # (symbols is CPU-heavy). Essential nodes first.
                    slow_paths = list(_SLOW_INDEX)
                    all_dispatch = bg_paths + slow_paths

                if all_dispatch:
                    mediator.dispatch(*all_dispatch)
                    _publish_progress("index:dispatch", {
                        "phase": "all",
                        "paths": all_dispatch,
                        "count": len(all_dispatch),
                    })
                    logger.info(
                        "[IndexWatcher] dispatched %d nodes to background",
                        len(all_dispatch),
                    )
            except Exception as exc:
                logger.warning(
                    "[IndexWatcher] background dispatch failed: %s", exc,
                )

            # Cold path cycle summary (warm path already published its own)
            if not _warm:
                total_elapsed = time.time() - t0
                _publish_progress("index:cycle:done", {
                    "phase": "index",
                    "ok": fast_ok,
                    "total": len(_ALL_INDEX),
                    "elapsed_ms": round(total_elapsed * 1000),
                })
                logger.info(
                    "[IndexWatcher] cycle done: fast %d/%d in %.0fms, "
                    "%d nodes dispatched to background",
                    fast_ok, len(_FAST_INDEX), fast_elapsed * 1000,
                    len(all_dispatch) if 'all_dispatch' in dir() else 0,
                )

        except Exception as e:
            logger.warning("[IndexWatcher] poll error: %s", e)


def _publish_change_event(changed_dirs: list[str]) -> None:
    """Publish index:watcher:change event on the EventBus."""
    try:
        from src.core.services.event_bus import bus

        bus.publish(
            "index:watcher:change",
            data={
                "changed_dirs": changed_dirs[:10],
                "change_count": len(changed_dirs),
                "timestamp": time.time(),
            },
        )
    except Exception:
        pass  # observability must never crash the watcher


def _publish_progress(event_type: str, data: dict) -> None:
    """Publish an index progress event on the EventBus.

    These events drive the Live Events panel in the mediator dashboard,
    giving real-time visibility into what the index is doing.

    Event types:
        index:cycle:start  — beginning a computation cycle
        index:node:start   — starting computation of a single node
        index:node:done    — node computed successfully (with duration + size)
        index:node:failed  — node computation failed (with error)
        index:cycle:done   — cycle complete (with summary)
        index:dispatch     — dispatched detect/devops/posture to background
    """
    try:
        from src.core.services.event_bus import bus

        bus.publish(
            event_type,
            key=data.get("path", ""),
            data={"timestamp": time.time(), **data},
        )
    except Exception:
        pass  # observability must never crash the watcher


def _data_size(data: object) -> dict:
    """Extract size information from computed data for observability."""
    info: dict = {}
    if isinstance(data, dict):
        info["entries"] = len(data)
    elif isinstance(data, (list, set, frozenset)):
        info["entries"] = len(data)
    if hasattr(data, "empty"):
        info["empty"] = bool(data.empty)
    return info
