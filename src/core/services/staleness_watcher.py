"""
Staleness Watcher — background mtime polling for proactive cache invalidation.

Periodically checks ``_WATCH_PATHS`` from ``devops_cache`` against the cached
``mtime`` values.  When a file changes *after* the cache was written, publishes
a ``state:stale`` event on the EventBus so the browser can show an "outdated"
badge on the affected card.

Design decisions
────────────────
1. **Mtime polling** (not inotify/watchdog): reuses existing ``_max_mtime()``,
   zero new dependencies, ~30 stat() calls per poll — negligible.
2. **Notify only, don't recompute**: avoids storm scenarios during active editing.
   The user clicks 🔄 or the next ``get_cached()`` call will recompute.
3. **Debounce via ``_last_stale``**: each key fires ``state:stale`` once per
   mtime change, not repeatedly every poll interval.
4. **Daemon thread**: stops automatically on server shutdown.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

POLL_INTERVAL_S = 5.0
"""Seconds between poll cycles.  5s is acceptable for a dev tool."""


def start_watcher(project_root: Path) -> threading.Thread:
    """Start a daemon thread that polls for file changes.

    The thread runs until the process exits (daemon=True).

    Args:
        project_root: Project root directory (same as Flask PROJECT_ROOT).

    Returns:
        The started daemon thread.
    """
    t = threading.Thread(
        target=_poll_loop,
        args=(project_root,),
        daemon=True,
        name="staleness-watcher",
    )
    t.start()
    logger.info("Staleness watcher started (poll every %.0fs)", POLL_INTERVAL_S)
    return t


def _poll_loop(project_root: Path) -> None:
    """Main poll loop — runs forever until process exits."""
    from src.core.services.devops_cache import _WATCH_PATHS, _load_cache, _max_mtime

    # Track the last mtime we fired state:stale for, per key.
    # This prevents re-firing every poll for the same change.
    last_stale: dict[str, float] = {}

    while True:
        time.sleep(POLL_INTERVAL_S)

        try:
            cache = _load_cache(project_root)
        except Exception:
            continue  # cache file unreadable — skip this cycle

        for key, watch_paths in _WATCH_PATHS.items():
            try:
                current_mtime = _max_mtime(project_root, watch_paths)
                if current_mtime == 0:
                    continue  # no watched files exist

                cached_mtime = cache.get(key, {}).get("mtime", 0)
                if cached_mtime == 0:
                    continue  # key not cached yet — nothing to be stale about

                # File changed AFTER the cache entry was written
                if current_mtime > cached_mtime:
                    # Only fire if we haven't already for this mtime
                    if last_stale.get(key) == current_mtime:
                        continue

                    last_stale[key] = current_mtime
                    _publish_stale(
                        key,
                        current_mtime=current_mtime,
                        cached_mtime=cached_mtime,
                    )
                else:
                    # Cache is fresh — clear the debounce tracker
                    last_stale.pop(key, None)

            except Exception:
                pass  # stat() failures etc. — skip this key


def _publish_stale(
    key: str,
    *,
    current_mtime: float,
    cached_mtime: float,
) -> None:
    """Publish a state:stale event on the EventBus (fail-safe)."""
    try:
        from src.core.services.event_bus import bus

        stale_by = round(current_mtime - cached_mtime, 1)
        bus.publish(
            "state:stale",
            key=key,
            data={
                "file_mtime": current_mtime,
                "cache_mtime": cached_mtime,
                "stale_by_s": stale_by,
            },
        )
        logger.debug("state:stale %s (stale by %.1fs)", key, stale_by)
    except Exception:
        pass  # observability must never crash the watcher
