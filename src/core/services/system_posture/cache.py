"""
File-backed TTL cache for system posture data.

Caches results to ``.state/posture_cache.json`` for persistence
across server restarts.  Follows the same pattern as
``src/core/services/devops/cache.py``.

Each cache key has its own TTL::

    platform    → session (until server restart)
    toolchain   → 5 minutes (tool could be installed/updated)
    project     → 60 seconds (bridges to existing mtime-cached data)
    runtime     → 0 seconds (always fresh — in-memory state)
    full        → 60 seconds (assembled full posture)
    summary     → 30 seconds (nav badge summary)

Thread-safe via a single lock.  Compute functions run OUTSIDE the
lock to avoid blocking parallel requests for different keys.

File persistence:
    - On every compute, the cache entry is serialized and saved to disk.
    - On startup (first access), existing entries are loaded from disk
      and served if still within TTL.
    - Model objects (PillarResult, SystemPosture) are serialized via
      to_dict() and deserialized via from_dict().
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

# ── File path ───────────────────────────────────────────────────

_CACHE_FILE = ".state/posture_cache.json"
_cache_dir: Path | None = None  # Set by init()


def init(project_root: Path) -> None:
    """Initialize the cache with the project root for file persistence."""
    global _cache_dir
    _cache_dir = project_root
    _load_from_disk()


# ── Internal state ──────────────────────────────────────────────

_cache: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()
_file_lock = threading.Lock()

# Per-key compute locks — prevent duplicate concurrent computation
# for the same key (same pattern as devops/cache.py _key_locks).
_compute_locks: dict[str, threading.Lock] = {}
_compute_locks_guard = threading.Lock()


def _get_compute_lock(key: str) -> threading.Lock:
    """Get or create a per-key lock for computing a cache entry."""
    with _compute_locks_guard:
        if key not in _compute_locks:
            _compute_locks[key] = threading.Lock()
        return _compute_locks[key]


# ── Default TTLs (seconds) ──────────────────────────────────────

TTLS: dict[str, float] = {
    "platform": float("inf"),  # Until restart — OS/kernel don't change
    "toolchain": 300,          # 5 minutes
    "project": 60,             # 1 minute (underlying data is mtime-cached)
    "runtime": 0,              # Always fresh (in-memory state)
    "full": 1200,              # 20 min — cascade handles real changes
    "summary": 600,            # 10 min — cascade handles real changes
}

# Keys whose data is a model object (needs to_dict/from_dict).
# Keys not listed here are assumed to store plain dicts.
_MODEL_KEYS = {
    "platform": "PillarResult",
    "toolchain": "PillarResult",
    "project": "PillarResult",
    "runtime": "PillarResult",
    "full": "SystemPosture",
}

# Keys worth persisting to disk.  Runtime is always fresh (TTL=0),
# so there's no point saving it.
_PERSIST_KEYS = {"platform", "toolchain", "project", "full", "summary"}


# ── File I/O (follows devops/cache.py pattern) ─────────────────


def _cache_path() -> Path | None:
    """Return the cache file path, or None if not initialized."""
    if _cache_dir is None:
        return None
    return _cache_dir / _CACHE_FILE


def _load_from_disk() -> None:
    """Load persisted cache entries from disk into memory.

    Called once on init().  Entries past their TTL are discarded.
    Model objects are deserialized via from_dict().
    """
    path = _cache_path()
    if path is None or not path.exists():
        return

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, IOError) as exc:
        logger.warning("posture cache: failed to load %s: %s", path, exc)
        return

    now = time.time()
    loaded = 0

    with _lock:
        for key, entry in raw.items():
            computed_at = entry.get("computed_at", 0)
            ttl = TTLS.get(key, 60)

            # Skip entries past TTL (inf TTL = always valid)
            if ttl != float("inf"):
                age = now - computed_at
                if age >= ttl:
                    continue

            # Deserialize model objects
            data = entry.get("data")
            model_type = _MODEL_KEYS.get(key)
            if model_type and isinstance(data, dict):
                try:
                    data = _deserialize(model_type, data)
                except Exception as exc:
                    logger.warning(
                        "posture cache: failed to deserialize %s: %s",
                        key, exc,
                    )
                    continue

            _cache[key] = {
                "data": data,
                "computed_at": computed_at,
                "elapsed_s": entry.get("elapsed_s", 0),
            }
            loaded += 1

    if loaded:
        logger.info("posture cache: loaded %d entries from disk", loaded)


def _save_to_disk() -> None:
    """Persist current cache entries to disk.

    Only saves keys in _PERSIST_KEYS.  Model objects are serialized
    via to_dict().  Caller should NOT hold _lock (we acquire _file_lock).
    """
    path = _cache_path()
    if path is None:
        return

    # Snapshot the persistable entries under _lock
    with _lock:
        snapshot: dict[str, dict[str, Any]] = {}
        for key in _PERSIST_KEYS:
            entry = _cache.get(key)
            if entry is None:
                continue

            data = entry["data"]
            model_type = _MODEL_KEYS.get(key)
            if model_type and hasattr(data, "to_dict"):
                serialized = data.to_dict()
            else:
                serialized = data

            snapshot[key] = {
                "data": serialized,
                "computed_at": entry["computed_at"],
                "elapsed_s": entry.get("elapsed_s", 0),
            }

    # Write under file lock (not holding _lock)
    with _file_lock:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(snapshot, default=str),
                encoding="utf-8",
            )
        except IOError as exc:
            logger.warning("posture cache: failed to save: %s", exc)


def _deserialize(model_type: str, data: dict) -> Any:
    """Deserialize a dict back into a model object."""
    from .models import PillarResult, SystemPosture

    if model_type == "PillarResult":
        return PillarResult.from_dict(data)
    elif model_type == "SystemPosture":
        return SystemPosture.from_dict(data)
    return data


# ── Public API ──────────────────────────────────────────────────


def get_or_compute(
    key: str,
    compute_fn: Callable[[], Any],
    *,
    ttl: float | None = None,
    force: bool = False,
) -> Any:
    """Return cached value or compute and cache it.

    Thread-safe.  A per-key compute lock ensures that concurrent
    requests for the same key don't duplicate work.  Different
    keys can compute in parallel.

    Args:
        key:        Cache key (e.g. ``"platform"``, ``"toolchain"``).
        compute_fn: Zero-arg callable that produces the cached value.
        ttl:        Override TTL in seconds.  Defaults to ``TTLS[key]``
                    or 60s if the key is not in the defaults.
        force:      If ``True``, bypass cache and recompute.

    Returns:
        The cached or freshly computed value.
    """
    if ttl is None:
        ttl = TTLS.get(key, 60)

    # TTL 0 = always fresh, skip cache entirely
    if ttl <= 0 and not force:
        return compute_fn()

    # Check cache under the global lock (fast path)
    if not force:
        with _lock:
            entry = _cache.get(key)
            if entry is not None:
                age = time.time() - entry["computed_at"]
                if age < ttl:
                    logger.debug("posture cache HIT: %s (age %.0fs)", key, age)
                    return entry["data"]

    # Compute under per-key lock (slow path)
    compute_lock = _get_compute_lock(key)
    with compute_lock:
        # Double-check after acquiring compute lock — another thread
        # may have computed while we waited.
        if not force:
            with _lock:
                entry = _cache.get(key)
                if entry is not None:
                    age = time.time() - entry["computed_at"]
                    if age < ttl:
                        return entry["data"]

        # Actually compute
        t0 = time.time()
        data = compute_fn()
        elapsed = time.time() - t0

        # Store result in memory
        with _lock:
            _cache[key] = {
                "data": data,
                "computed_at": time.time(),
                "elapsed_s": round(elapsed, 3),
            }

        # Persist to disk (outside _lock)
        if key in _PERSIST_KEYS:
            _save_to_disk()

        logger.debug(
            "posture cache MISS: %s (computed in %.2fs)", key, elapsed,
        )
        return data


def invalidate(key: str | None = None) -> list[str]:
    """Invalidate a specific key or all keys.

    Args:
        key: Key to invalidate, or ``None`` to clear all.

    Returns:
        List of keys that were invalidated.
    """
    with _lock:
        if key is not None:
            if key in _cache:
                del _cache[key]
                busted = [key]
            else:
                busted = []
        else:
            busted = list(_cache.keys())
            _cache.clear()

    # Update disk file to reflect invalidation
    if busted:
        _save_to_disk()

    return busted


def get_age(key: str) -> float | None:
    """Return age in seconds for a cached key, or ``None`` if absent."""
    with _lock:
        entry = _cache.get(key)
        if entry is not None:
            return time.time() - entry["computed_at"]
    return None


def get_stats() -> dict[str, Any]:
    """Return cache statistics for diagnostics.

    Returns a dict with key info for each cached entry:
    age, TTL, whether it's fresh, and computation time.
    """
    with _lock:
        now = time.time()
        stats: dict[str, Any] = {}
        for key, entry in _cache.items():
            age = now - entry["computed_at"]
            ttl = TTLS.get(key, 60)
            stats[key] = {
                "age_s": round(age, 1),
                "ttl_s": ttl if ttl != float("inf") else "inf",
                "fresh": age < ttl,
                "elapsed_s": entry.get("elapsed_s", 0),
            }
        return stats
