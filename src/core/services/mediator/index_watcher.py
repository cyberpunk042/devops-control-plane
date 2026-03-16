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
from src.core.services.mediator.core import _check_mtime

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.services.mediator.core import QueryMediator

logger = logging.getLogger(__name__)

POLL_INTERVAL_S = 5.0
"""Seconds between poll cycles."""

# ── Runtime-mutable watcher state ───────────────────────────────
# Read by the poll loop each iteration so config changes take effect
# without restarting the thread.
watcher_state: dict[str, object] = {
    "poll_interval": POLL_INTERVAL_S,
    "smart_dispatch": True,
    "enabled": True,
    "last_scan_ts": None,
    "changed_dirs_count": 0,
}

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
    #   Peek + symbols are gated by server setting (checked each cycle)
    _FAST_INDEX = [
        "index.scan",      # root — scans filesystem (~25ms)
        "index.delta",     # depends on scan — diffs against prev (~5ms)
        "index.files",     # depends on scan — filename→paths map (~2ms)
        "index.dirs",      # depends on scan — dirname→paths map (~2ms)
        "index.paths",     # depends on scan — flat path set (~1ms)
        "index.classify",  # depends on scan — language/framework detection (~10ms)
    ]
    _SLOW_INDEX_ALWAYS = [
        "index.stats",     # depends on all index nodes (~1ms)
    ]
    _SLOW_INDEX_PEEK = [
        "index.symbols",   # depends on delta — symbol index (cold ~30s, warm <1ms)
        "index.peek",      # depends on delta+symbols+scan — peek cache (cold ~2s, warm <100ms)
    ]

    def _get_slow_index():
        """Return SLOW_INDEX list, excluding peek+symbols if disabled."""
        from src.core.services.server_settings import is_peek_symbols_enabled
        if is_peek_symbols_enabled(project_root):
            return _SLOW_INDEX_PEEK + _SLOW_INDEX_ALWAYS
        else:
            logger.debug("[IndexWatcher] Peek & Symbols disabled — skipping index.symbols + index.peek")
            return _SLOW_INDEX_ALWAYS



    # Initial snapshot — capture baseline mtimes.
    try:
        last_dir_mtimes = scan_dir_mtimes(project_root)
        logger.debug(
            "[IndexWatcher] initial snapshot: %d dirs", len(last_dir_mtimes),
        )
    except Exception as e:
        logger.warning("[IndexWatcher] initial scan failed: %s", e)

    while True:
        # Read runtime config each cycle
        _interval = float(watcher_state.get("poll_interval", poll_interval))
        time.sleep(_interval)

        # Skip cycle if watcher is disabled
        if not watcher_state.get("enabled", True):
            continue

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

            # Update watcher state with scan info
            watcher_state["last_scan_ts"] = time.time()
            watcher_state["changed_dirs_count"] = len(changed_dirs)

            if not changed_dirs and not first_cycle:
                continue  # nothing changed, sleep again

            last_dir_mtimes = current_dir_mtimes

            # Smart dispatch sentinel — set to None if no snapshot taken.
            _prev_classify = None

            if changed_dirs:
                logger.info(
                    "[IndexWatcher] %d dirs changed, refreshing tree",
                    len(changed_dirs),
                )
                from src.core.observability.console import console_fs_change
                console_fs_change(changed_dirs)
                _publish_change_event(changed_dirs)

                # Snapshot classify output BEFORE invalidation.
                # We'll compare after recomputation to decide
                # whether downstream detect/devops nodes need dispatch.
                _prev_classify = None
                try:
                    _pc = mediator.peek("index.classify")
                    if _pc is not None:
                        _prev_classify = _pc.get("data")
                except Exception:
                    pass

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
                _slow_index = _get_slow_index()
                _all_index = _FAST_INDEX + _slow_index

                # Start a tracked index cycle
                import datetime as _dt
                _cycle_id = f"cycle-{_dt.datetime.now(_dt.timezone.utc).strftime('%Y%m%d-%H%M%S')}"
                _cycle_start_t = time.time()
                from src.core.observability.console import console_cycle_start
                console_cycle_start(_cycle_id)
                _cycle_op = None
                try:
                    tracker = mediator._tracker
                    if tracker:
                        _cycle_op = tracker.begin(
                            "system", _cycle_id,
                            chain_id=_cycle_id,
                        )
                except Exception:
                    pass
                # Set correlation context for event sourcing
                try:
                    from src.core.services.events.correlation import set_correlation
                    set_correlation(_cycle_id)
                except Exception:
                    pass
                # Emit cycle started event
                try:
                    _es = mediator._event_store
                    if _es:
                        from src.core.services.events.models import Event as _Evt
                        _es.append(_Evt(
                            id="", ts=time.time(),
                            type="index.cycle.started",
                            correlation_id=_cycle_id,
                            source="watcher",
                            path="",
                            summary=f"Index cycle started: {len(_all_index)} fast nodes",
                        ))
                except Exception:
                    pass
                # Also set legacy operation_id for backward compat
                try:
                    from src.core.engine.operation_context import set_operation_id
                    set_operation_id(_cycle_id)
                except Exception:
                    pass

                _publish_progress("index:cycle:start", {
                    "phase": "index",
                    "total": len(_all_index),
                    "paths": list(_all_index),
                })

                t0 = time.time()
                fast_ok = 0
                for i, path in enumerate(_FAST_INDEX):
                    _publish_progress("index:node:start", {
                        "path": path,
                        "step": i + 1,
                        "total": len(_all_index),
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
                            "total": len(_all_index),
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
                            "total": len(_all_index),
                            "elapsed_ms": round(node_elapsed * 1000),
                            "error": str(exc)[:200],
                        })

                fast_elapsed = time.time() - t0
                logger.info(
                    "[IndexWatcher] fast index: %d/%d nodes in %.1fms",
                    fast_ok, len(_FAST_INDEX), fast_elapsed * 1000,
                )

             # ── Phase 2: Tiered background dispatch ──────────────────
            # Instead of submitting all paths at once, dispatch them
            # in graduated tiers.  Each tier waits for the previous
            # to complete before starting.  This ensures:
            #   - Fast data appears in the UI within seconds
            #   - Heavy tasks don't block light ones
            #   - Aggregates run last (they depend on card data)
            #
            # Tier definitions:
            #   T1 (instant)  — light devops + catalog (user-visible first)
            #   T2 (medium)   — infrastructure devops + github
            #   T3 (heavy)    — heavy scans (security, testing)
            #   T4 (index)    — slow index nodes (symbols, peek, stats)
            #                   These are background metadata — heavy but
            #                   NOT user-visible on page load.
            #                   On warm start: index.delta/stats/view
            #   T5 (aggregate)— devops.status + posture.* + audit L0/L1
            #   T6 (deep)     — audit L2 + enriched (heavy, TTL=600s)
            #
            # NOTE: detect.* nodes are intentionally NOT dispatched.
            # They use the same compute functions as devops.* and exist
            # solely for cascade invalidation.  Dispatching both would
            # duplicate work.
            try:
                from .config import (
                    TIER_PATHS, AUDIT_L0L1, AUDIT_L2, INDEX_PASSIVE,
                )
                from .work_queue import Priority

                # ── Build tier path lists ────────────────────────────
                _T1_PATHS = TIER_PATHS["T1:visible"]
                _T2_PATHS = TIER_PATHS["T2:infra"]
                _T3_PATHS = TIER_PATHS["T3:heavy"]
                _T5_PATHS = TIER_PATHS["T5:aggregate"]

                all_paths = mediator.tree.all_paths()
                posture_paths = [
                    p for p in all_paths if p.startswith("posture.")
                ]
                catalog_paths = [
                    p for p in all_paths if p.startswith("catalog.")
                ]
                github_paths = [
                    p for p in all_paths if p.startswith("github.")
                ]

                # T1: user-visible devops data (light, fast)
                tier1_paths = (
                    [p for p in all_paths if p in _T1_PATHS]
                    + catalog_paths
                )
                # T2: infrastructure devops + github
                tier2_paths = (
                    [p for p in all_paths if p in _T2_PATHS]
                    + github_paths
                )
                # T3: heavy scans
                tier3_paths = [p for p in all_paths if p in _T3_PATHS]

                # T4: slow index nodes (background metadata)
                # Excludes peek/symbols — those go to T7.
                if _warm:
                    # Warm start: index nodes already cached from disk.
                    # Still dispatch delta/stats/view — content may
                    # differ from persisted shards.
                    tier4_paths: list[str] = [
                        "index.delta", "index.stats", "index.view",
                    ]
                else:
                    # Cold start: slow index nodes (exclude passive)
                    tier4_paths = [
                        p for p in list(_get_slow_index()) + ["index.view"]
                        if p not in INDEX_PASSIVE
                    ]

                # T5: aggregates (exclude timeline.data — computed after all tiers)
                timeline_paths = [
                    p for p in all_paths
                    if p.startswith("timeline.") and p != "timeline.data"
                ]
                tier5_paths = (
                    [p for p in all_paths if p in _T5_PATHS]
                    + posture_paths
                    + timeline_paths
                    + [p for p in all_paths if p in AUDIT_L0L1]
                )
                # T6: deep audit
                tier6_paths = [p for p in all_paths if p in AUDIT_L2]

                # T7: passive heavy index (dead last)
                tier7_paths = [p for p in all_paths if p in INDEX_PASSIVE]

                # ── Smart dispatch: filter by classify change ──
                # If classify didn't change, narrow dispatch scope.
                # Skip smart dispatch entirely if disabled in config.
                _classify_changed = True
                if watcher_state.get("smart_dispatch", True) and changed_dirs and _prev_classify is not None:
                    try:
                        new_classify = mediator.peek("index.classify")
                        if (
                            new_classify is not None
                            and new_classify.get("data") == _prev_classify
                        ):
                            _classify_changed = False
                    except Exception:
                        pass

                if not _classify_changed:
                    # Only dispatch detect nodes whose mtime_paths
                    # indicate file-level staleness.
                    cycle_ts = time.time() - poll_interval
                    stale_set: set[str] = set()

                    for tier_list in (tier1_paths, tier2_paths, tier3_paths):
                        for p in tier_list:
                            node = mediator.tree.resolve(p)
                            if node is None or not node.mtime_paths:
                                continue
                            if _check_mtime(
                                project_root, node.mtime_paths, cycle_ts,
                            ):
                                stale_set.add(p)
                                # Include downstream dependents
                                for dep in mediator.tree.dependents(p.replace("devops.", "detect.", 1)):
                                    if dep.startswith(("devops.", "posture.")):
                                        stale_set.add(dep)

                    tier1_paths = [p for p in tier1_paths if p in stale_set]
                    tier2_paths = [p for p in tier2_paths if p in stale_set]
                    tier3_paths = [p for p in tier3_paths if p in stale_set]
                    # Tier 5/6 always run if any downstream changed
                    if not stale_set:
                        tier5_paths = []
                        tier6_paths = []

                    logger.info(
                        "[IndexWatcher] smart dispatch: classify unchanged, "
                        "stale nodes: %s",
                        ", ".join(sorted(stale_set)) or "(none)",
                    )

                # ── Define tiers with priorities ─────────────────
                tiers: list[tuple[str, list[str], int]] = [
                    ("T1:visible",   tier1_paths, Priority.HIGH),
                    ("T2:infra",     tier2_paths, Priority.NORMAL),
                    ("T3:heavy",     tier3_paths, Priority.NORMAL),
                    ("T4:index",     tier4_paths, Priority.LOW),
                    ("T5:aggregate", tier5_paths, Priority.IDLE),
                    ("T6:deep",      tier6_paths, Priority.IDLE),
                    ("T7:passive",   tier7_paths, Priority.BACKGROUND),
                ]

                # Filter out empty tiers
                tiers = [
                    (name, paths, pri)
                    for name, paths, pri in tiers
                    if paths
                ]

                total_dispatched = [0]

                if not tiers:
                    logger.debug(
                        "[IndexWatcher] no tiers to dispatch",
                    )
                    # End the tracked cycle operation — no tiers
                    try:
                        tracker = mediator._tracker
                        if tracker and _cycle_op:
                            tracker.end(_cycle_op, "ok", "Index cycle: fast only")
                    except Exception:
                        pass
                    # Clear legacy operation context
                    try:
                        from src.core.engine.operation_context import set_operation_id
                        set_operation_id(None)
                    except Exception:
                        pass
                else:
                    # ── Chain tiers via on_complete callbacks ─────
                    # Each tier's on_complete dispatches the next tier.
                    # This creates a sequential pipeline:
                    #   T1 complete → dispatch T2
                    #   T2 complete → dispatch T3
                    #   ... etc.

                    def _make_tier_dispatcher(
                        remaining_tiers: list[tuple[str, list[str], int]],
                        _cid: str = _cycle_id,
                        _cstart: float = _cycle_start_t,
                    ) -> None:
                        """Dispatch the first tier in the list, chain the rest."""
                        if not remaining_tiers:
                            _publish_progress("index:tiers:done", {
                                "total_dispatched": total_dispatched[0],
                            })
                            # End the tracked cycle operation
                            try:
                                tracker = mediator._tracker
                                if tracker and _cycle_op:
                                    tracker.end(
                                        _cycle_op, "ok",
                                        f"Index cycle: {total_dispatched[0]} nodes",
                                    )
                            except Exception:
                                pass
                            # Emit cycle completed event
                            try:
                                _es = mediator._event_store
                                if _es:
                                    from src.core.services.events.models import Event as _Evt
                                    _es.append(_Evt(
                                        id="", ts=time.time(),
                                        type="index.cycle.completed",
                                        correlation_id=_cid,
                                        source="watcher",
                                        summary=f"Index cycle: {total_dispatched[0]} nodes dispatched",
                                    ))
                            except Exception:
                                pass
                            # Console: cycle done
                            try:
                                from src.core.observability.console import console_cycle_done
                                _cycle_elapsed = int((time.time() - _cstart) * 1000)
                                console_cycle_done(_cid, total_dispatched[0], _cycle_elapsed)
                            except Exception:
                                pass
                            # Force recompute timeline.data so SSE pushes new events.
                            try:
                                mediator.get("timeline.data", force=True)
                                logger.info("[IndexWatcher] timeline.data recomputed for SSE push")
                            except Exception as _tl_exc:
                                logger.warning("[IndexWatcher] timeline.data recompute failed: %s", _tl_exc)
                            # Clear correlation context
                            try:
                                from src.core.services.events.correlation import clear_correlation
                                clear_correlation()
                            except Exception:
                                pass
                            # Clear legacy operation context
                            try:
                                from src.core.engine.operation_context import set_operation_id
                                set_operation_id(None)
                            except Exception:
                                pass
                            return

                        tier_name, tier_paths, tier_priority = (
                            remaining_tiers[0]
                        )
                        rest = remaining_tiers[1:]

                        _publish_progress("index:tier:start", {
                            "tier": tier_name,
                            "paths": tier_paths,
                            "count": len(tier_paths),
                        })

                        logger.info(
                            "[IndexWatcher] dispatching %s: %d paths "
                            "(priority=%d)",
                            tier_name, len(tier_paths), tier_priority,
                        )

                        def _on_tier_complete() -> None:
                            # Resume tracker on this thread for the next tier dispatch
                            try:
                                tracker = mediator._tracker
                                if tracker and _cycle_op:
                                    tracker.resume(_cycle_op)
                            except Exception:
                                pass
                            # Re-set correlation for event sourcing
                            try:
                                from src.core.services.events.correlation import set_correlation
                                set_correlation(_cid)
                            except Exception:
                                pass
                            # Re-set legacy cycle_id so next tier's dispatch captures it
                            try:
                                from src.core.engine.operation_context import set_operation_id
                                set_operation_id(_cid)
                            except Exception:
                                pass

                            _publish_progress("index:tier:done", {
                                "tier": tier_name,
                                "count": len(tier_paths),
                            })
                            logger.info(
                                "[IndexWatcher] %s complete (%d paths), "
                                "dispatching next tier",
                                tier_name, len(tier_paths),
                            )
                            # Dispatch next tier
                            _make_tier_dispatcher(rest)

                        total_dispatched[0] += len(tier_paths)

                        mediator.dispatch(
                            *tier_paths,
                            priority=tier_priority,
                            on_complete=_on_tier_complete,
                        )

                    # Start the chain with all tiers
                    _make_tier_dispatcher(tiers)

                    _publish_progress("index:dispatch", {
                        "phase": "tiered",
                        "tiers": [
                            {"name": n, "count": len(p)}
                            for n, p, _ in tiers
                        ],
                        "total": total_dispatched[0],
                    })
                    logger.info(
                        "[IndexWatcher] dispatched %d nodes across %d tiers",
                        total_dispatched[0], len(tiers),
                    )

            except Exception as exc:
                logger.warning(
                    "[IndexWatcher] tiered dispatch failed: %s", exc,
                )

            # Cold path cycle summary (warm path already published its own)
            if not _warm:
                total_elapsed = time.time() - t0
                _publish_progress("index:cycle:done", {
                    "phase": "index",
                    "ok": fast_ok,
                    "total": len(_all_index),
                    "elapsed_ms": round(total_elapsed * 1000),
                })
                logger.info(
                    "[IndexWatcher] cycle done: fast %d/%d in %.0fms, "
                    "%d nodes dispatched to background",
                    fast_ok, len(_FAST_INDEX), fast_elapsed * 1000,
                    total_dispatched[0] if isinstance(total_dispatched, list) else 0,
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
