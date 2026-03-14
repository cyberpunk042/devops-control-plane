"""
QueryMediator — central data hub for the trilateral system.

Mediates between Backend (demand), Cache (memory), and Index (truth).
Routes queries through the tree, checks cache freshness, calls
resolvers when needed, and cascades invalidations.

Thread safety
─────────────
- ``_lock`` protects ``_cache`` reads/writes.
- ``_compute_locks`` provides per-path locking so that only one thread
  computes a given path at a time (others wait and get the cached result).
- Follows the same pattern as ``system_posture/cache.py`` and
  ``devops/cache.py``.

Implemented phases
──────────────────
- Phase 0: get/put/diag, tree registry, cache management
- Phase 1–4: posture/detect/devops wiring, cascade engine
- Phase 5: delta protocol (since_seq, EventBus bridge, batch mode)
- Phase 6A: subscribe + stale-while-revalidate (pure, no threading)
- Phase 6B: refresh + bust + dispatch (executor-injected parallelism)

Not yet implemented
───────────────────
- explain()
"""

from __future__ import annotations

import os

import fnmatch
import logging
import math
import threading
import time
from collections.abc import Callable, Generator
from concurrent.futures import Executor, Future
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .tree import DataTree, TreeNode

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .work_queue import WorkQueue

logger = logging.getLogger(__name__)


# ── Cache entry ────────────────────────────────────────────────────


@dataclass
class CacheEntry:
    """A single cached value in the mediator.

    Stored in ``QueryMediator._cache``, keyed by path string.
    """

    data: Any               # the computed/cached value
    computed_at: float       # time.time() when computed
    seq: int                 # monotonic sequence number
    source: str              # "computed" | "cache" | "disk"
    elapsed_s: float = 0.0  # how long the computation took


# ── mtime staleness check ──────────────────────────────────────────

# Directories to skip during mtime walks (mirrors devops/cache.py)
_MTIME_WALK_SKIP = frozenset({
    ".git", ".backup", "node_modules", "__pycache__", ".venv", "venv",
    "build", "dist", ".tox", ".mypy_cache", ".ruff_cache",
    ".pytest_cache", ".next", ".nuxt", "site-packages", "_build",
})
_MTIME_WALK_MAX_DEPTH = 3


def _check_mtime(
    project_root: Path,
    mtime_paths: list[str],
    computed_at: float,
) -> bool:
    """Check if any watched path has been modified since computed_at.

    Returns True if the cached value is stale (a path was modified
    after the value was computed).  Returns False if everything is
    still fresh or if the paths don't exist.

    For directory entries (paths ending with ``/``), walks up to
    3 levels deep checking file mtimes — matching the same logic
    as ``devops/cache.py:_max_mtime``.
    """
    for rel in mtime_paths:
        p = project_root / rel
        try:
            if rel.endswith("/") and p.is_dir():
                mt = _walk_max_mtime(p)
            else:
                mt = os.stat(p).st_mtime
            if mt > computed_at:
                return True  # stale
        except (FileNotFoundError, OSError):
            pass
    return False  # still fresh


def _walk_max_mtime(directory: Path) -> float:
    """Walk a directory (depth-limited) and return the max file mtime."""
    max_mt = 0.0
    base = str(directory)
    for root, dirs, files in os.walk(directory):
        depth = root[len(base):].count(os.sep)
        if depth >= _MTIME_WALK_MAX_DEPTH:
            dirs.clear()
            continue
        dirs[:] = [
            d for d in dirs
            if d not in _MTIME_WALK_SKIP and not d.startswith(".")
        ]
        for fname in files:
            if fname.startswith("."):
                continue
            try:
                mt = os.stat(os.path.join(root, fname)).st_mtime
                if mt > max_mt:
                    max_mt = mt
            except (FileNotFoundError, OSError):
                pass
    return max_mt


# ── Subscription entry ─────────────────────────────────────────────


@dataclass
class _Subscription:
    """An in-process subscriber registered via ``subscribe()``."""

    id: str
    pattern: str
    callback: Callable[[dict], None]


# ── QueryMediator ──────────────────────────────────────────────────


class QueryMediator:
    """Central data hub — mediates between caches, indexes, and backend.

    Usage::

        mediator = QueryMediator(tree, project_root)
        result = mediator.get("posture.toolchain")
        mediator.put("posture.toolchain", cascade=True)
        info = mediator.diag()

    Phase 6A adds subscribe() and stale_ok::

        sub_id = mediator.subscribe("devops.*", my_callback)
        result = mediator.get("posture.toolchain", stale_ok=True)

    Phase 6B adds refresh(), bust(), and dispatch()::

        results = mediator.refresh("posture.toolchain", "posture.platform")
        mediator.bust(max_age=300, prefix="devops")
        task = mediator.dispatch("posture.toolchain")
    """

    def __init__(
        self,
        tree: DataTree,
        project_root: Path,
        *,
        on_stale: Callable[[str], None] | None = None,
        executor: Executor | None = None,
        work_queue: WorkQueue | None = None,
    ) -> None:
        self._tree = tree
        self._project_root = project_root
        self._cache: dict[str, CacheEntry] = {}
        self._lock = threading.Lock()
        self._compute_locks: dict[str, threading.Lock] = {}
        self._seq: int = 0

        # Phase 5: batch mode state
        self._batch_active: bool = False
        self._batch_writes: list[str] = []
        self._batch_invalidated: list[str] = []
        self._batch_seq: int = 0

        # Phase 6A: subscribe + stale-while-revalidate
        self._on_stale = on_stale
        self._refreshing: set[str] = set()
        self._subscriptions: dict[str, _Subscription] = {}
        self._sub_counter: int = 0

        # Phase 6B: executor + dispatch (legacy)
        self._executor = executor
        self._dispatch_counter: int = 0

        # Phase 7: priority work queue
        self._work_queue = work_queue

    # ── Properties ─────────────────────────────────────────────

    @property
    def tree(self) -> DataTree:
        """The data tree (read-only after init)."""
        return self._tree

    @property
    def project_root(self) -> Path:
        """Project root directory."""
        return self._project_root

    # ── GET ────────────────────────────────────────────────────

    def get(
        self,
        path: str,
        *,
        force: bool = False,
        max_age: float | None = None,
        stale_ok: bool = False,
        explain: bool = False,
        since_seq: int | None = None,
    ) -> dict[str, Any]:
        """Query a value by path.

        Parameters
        ----------
        path : str
            Dot-separated path (e.g. ``"posture.toolchain"``).
        force : bool
            Bypass cache, force recompute.
        max_age : float | None
            Maximum acceptable age in seconds.  If cached value
            is older, recompute.  None = use node's TTL.
        explain : bool
            Include resolution explanation in meta.
        stale_ok : bool
            If True and cached value is stale, return the stale data
            immediately instead of blocking on recompute.  The
            ``on_stale`` hook is called (if configured) to trigger
            background refresh.  Meta includes ``stale=True`` and
            ``refreshing=True/False``.
        since_seq : int | None
            If provided, check whether the node has changed since
            this sequence number.  If ``node.last_change_seq <= since_seq``,
            returns ``{"changed": False, ...}`` without computing.
            If ``None``, normal get behavior.

        Returns
        -------
        dict
            ``{"data": <value>, "meta": {...}}`` on normal get, or
            ``{"changed": False, "meta": {"current_seq": N}}`` when
            ``since_seq`` is provided and nothing changed.

        Raises
        ------
        KeyError
            If path is not registered in the tree.
        RuntimeError
            If the node has no resolver and no cached value.
        """
        node = self._tree.resolve(path)
        if node is None:
            raise KeyError(f"Path not found in tree: {path!r}")
        if not node.is_registered:
            raise KeyError(
                f"Path exists but is not registered (branch only): {path!r}"
            )

        # Phase 5: since_seq shortcut
        if since_seq is not None and node.last_change_seq <= since_seq:
            return {
                "changed": False,
                "meta": {
                    "path": path,
                    "current_seq": node.last_change_seq,
                },
            }

        explanation: list[str] = []

        # ── TTL=0 means always fresh — skip cache entirely ────
        if (
            not force
            and node.ttl is not None
            and node.ttl <= 0
            and node.resolver is not None
        ):
            if explain:
                explanation.append("ttl=0, always fresh, skipping cache")
            t0 = time.time()
            try:
                result = node.resolver()
            except Exception:
                logger.exception("resolver failed for %s", path)
                raise
            elapsed = time.time() - t0
            if explain:
                explanation.append(f"computed in {elapsed:.3f}s")
            return self._make_result(
                result, path, "computed", 0.0,
                self._next_seq(), explanation,
            )

        # ── Check cache (unless forced) ───────────────────────
        if not force:
            entry = self._get_cached(path)
            if entry is not None:
                age = time.time() - entry.computed_at
                effective_max = max_age if max_age is not None else node.ttl

                # TTL check
                fresh = True
                if effective_max is not None and effective_max != math.inf:
                    if age >= effective_max:
                        fresh = False

                # mtime_paths check — catches file changes the
                # FS watcher may miss (e.g. .git/HEAD)
                if fresh and node.mtime_paths:
                    if _check_mtime(
                        self._project_root,
                        node.mtime_paths,
                        entry.computed_at,
                    ):
                        fresh = False
                        if explain:
                            explanation.append(
                                "mtime_paths changed since last compute"
                            )

                if fresh:
                    if explain:
                        explanation.append(
                            f"cache hit, age {age:.1f}s"
                            + (f" (max_age={effective_max}s)" if effective_max else "")
                        )
                    return self._make_result(
                        entry.data, path, "cache", age,
                        entry.seq, explanation,
                    )
                else:
                    # Stale data — check stale_ok
                    if stale_ok:
                        if explain:
                            explanation.append(
                                f"cache stale, age {age:.1f}s > "
                                f"max_age {effective_max}s, "
                                f"stale_ok=True, returning stale"
                            )
                        # Call the stale hook (production: spawns bg thread)
                        if self._on_stale is not None:
                            try:
                                self._on_stale(path)
                            except Exception:
                                logger.exception(
                                    "on_stale hook failed for %s", path,
                                )
                        refreshing = path in self._refreshing
                        return self._make_result(
                            entry.data, path, "cache_stale", age,
                            entry.seq, explanation,
                            stale=True, refreshing=refreshing,
                        )
                    else:
                        if explain:
                            explanation.append(
                                f"cache stale, age {age:.1f}s > "
                                f"max_age {effective_max}s, recomputing"
                            )
        else:
            if explain:
                explanation.append("force=True, bypassing cache")

        # ── Compute ───────────────────────────────────────────
        if node.resolver is None:
            # No resolver — check if there's stale data to return
            entry = self._get_cached(path)
            if entry is not None:
                if explain:
                    explanation.append(
                        "no resolver, returning stale cached data"
                    )
                age = time.time() - entry.computed_at
                return self._make_result(
                    entry.data, path, "cache_stale", age,
                    entry.seq, explanation,
                )
            raise RuntimeError(
                f"No resolver and no cached data for: {path!r}"
            )

        # Per-path compute lock — only one thread computes at a time
        compute_lock = self._get_compute_lock(path)
        with compute_lock:
            # Double-check: another thread may have computed while we waited
            if not force:
                entry = self._get_cached(path)
                if entry is not None:
                    age = time.time() - entry.computed_at
                    effective_max = max_age if max_age is not None else node.ttl
                    fresh = True
                    if effective_max is not None and effective_max != math.inf:
                        if age >= effective_max:
                            fresh = False
                    # mtime_paths check (same as above)
                    if fresh and node.mtime_paths:
                        if _check_mtime(
                            self._project_root,
                            node.mtime_paths,
                            entry.computed_at,
                        ):
                            fresh = False
                    if fresh:
                        if explain:
                            explanation.append(
                                f"computed by another thread while waiting, "
                                f"age {age:.1f}s"
                            )
                        return self._make_result(
                            entry.data, path, "cache", age,
                            entry.seq, explanation,
                        )

            # Actually compute
            t0 = time.time()
            try:
                result = node.resolver()
            except Exception:
                logger.exception("resolver failed for %s", path)
                raise
            elapsed = time.time() - t0

            if explain:
                explanation.append(f"computed in {elapsed:.3f}s")

            # Store in cache
            seq = self._next_seq()
            entry = CacheEntry(
                data=result,
                computed_at=time.time(),
                seq=seq,
                source="computed",
                elapsed_s=elapsed,
            )
            self._set_cached(path, entry)
            node.last_change_seq = seq

            # Persist to disk — survives restarts.
            # Only save nodes that declared persist=True.
            if node.persist:
                try:
                    from src.core.services.mediator.persistence import persist_node
                    persist_node(self._project_root, path, result)
                except Exception:
                    pass  # persistence must never break computation

            # Publish compute event so SSE clients see activity
            self._publish_change(
                path, seq, [path], [],
            )
            # Notify in-process subscribers with compute metadata
            self._notify_subscribers(
                "computed", path, seq, [path],
                compute_meta={
                    "data": result,
                    "elapsed_s": elapsed,
                    "computed_at": entry.computed_at,
                },
            )

            return self._make_result(
                result, path, "computed", 0.0,
                seq, explanation,
            )

    # ── PEEK ───────────────────────────────────────────────────

    def peek(self, path: str) -> dict[str, Any] | None:
        """Return cached data without computation.

        Unlike ``get()``, this **NEVER** calls a resolver.  If the
        cache is empty for this path, returns ``None``.

        Intended for:
        - Context processors that must not block page load
        - Optimistic reads where stale/missing data is acceptable
        - Pre-flight checks ("is this data available?")

        Parameters
        ----------
        path : str
            Dot-separated path (e.g. ``"index.scan"``, ``"devops.docker"``).

        Returns
        -------
        dict | None
            ``{"data": <value>, "meta": {...}}`` if cached data exists,
            ``None`` if no data is available (cache miss).

        Raises
        ------
        KeyError
            If path is not registered in the tree.
        """
        node = self._tree.resolve(path)
        if node is None:
            raise KeyError(f"Path not found in tree: {path!r}")
        if not node.is_registered:
            raise KeyError(
                f"Path exists but is not registered (branch only): {path!r}"
            )

        entry = self._get_cached(path)
        if entry is None:
            return None

        age = time.time() - entry.computed_at
        return self._make_result(
            entry.data, path, "peek", age,
            entry.seq, [],
        )

    def peek_many(self, *paths: str) -> dict[str, dict[str, Any]]:
        """Peek at multiple paths at once.

        Returns a dict of path → result for all paths that have
        cached data.  Paths with no cached data are omitted.
        Unregistered paths are silently skipped (no KeyError).

        Parameters
        ----------
        *paths : str
            Dot-separated paths to peek at.

        Returns
        -------
        dict[str, dict]
            Map of ``path → {"data": <value>, "meta": {...}}`` for
            all paths that have cached data.
        """
        results: dict[str, dict[str, Any]] = {}
        for path in paths:
            try:
                result = self.peek(path)
                if result is not None:
                    results[path] = result
            except KeyError:
                continue  # Unregistered path — skip silently
        return results

    # ── PUT ────────────────────────────────────────────────────

    def put(
        self,
        path: str,
        data: Any = None,
        *,
        cascade: bool = True,
        cascade_depth: int = -1,
        notify: bool = True,
    ) -> dict[str, Any]:
        """Write or invalidate a path.

        Parameters
        ----------
        path : str
            Dot-separated path.
        data : Any
            If provided, store as the cached value.
            If None, invalidate (remove from cache).
        cascade : bool
            If True, also invalidate all dependents.
        cascade_depth : int
            Maximum cascade depth.  -1 = infinite.
        notify : bool
            If True, publish change event on EventBus.
            Set to False for internal operations (cache warming,
            test fixtures) that shouldn't broadcast.

        Returns
        -------
        dict
            ``{"invalidated": [...], "seq": N}``
        """
        node = self._tree.resolve(path)
        if node is None:
            raise KeyError(f"Path not found in tree: {path!r}")

        invalidated: list[str] = []
        writes: list[str] = []
        seq = self._next_seq()

        if data is not None:
            # Write
            entry = CacheEntry(
                data=data,
                computed_at=time.time(),
                seq=seq,
                source="computed",
            )
            self._set_cached(path, entry)
            node.last_change_seq = seq
            writes.append(path)
            logger.debug("put (write): %s seq=%d", path, seq)
        else:
            # Invalidate
            removed = self._remove_cached(path)
            if removed:
                invalidated.append(path)
                node.last_change_seq = seq
                logger.debug("put (invalidate): %s", path)

        # Cascade
        if cascade:
            dep_paths = self._tree.dependents(path, depth=cascade_depth)
            for dep_path in dep_paths:
                removed = self._remove_cached(dep_path)
                if removed:
                    invalidated.append(dep_path)
                    dep_node = self._tree.resolve(dep_path)
                    if dep_node is not None:
                        dep_node.last_change_seq = seq
                    logger.debug(
                        "cascade invalidate: %s (from %s)", dep_path, path,
                    )

        # Phase 5: EventBus publishing + Phase 6A: subscriber notification
        if notify and (writes or invalidated):
            if self._batch_active:
                # Accumulate for aggregate event
                self._batch_writes.extend(writes)
                self._batch_invalidated.extend(invalidated)
                self._batch_seq = seq
            else:
                self._publish_change(path, seq, writes, invalidated)
                # Notify in-process subscribers
                if writes:
                    self._notify_subscribers(
                        "write", path, seq, writes,
                    )
                if invalidated:
                    self._notify_subscribers(
                        "invalidated", path, seq, invalidated,
                    )

        return {
            "invalidated": invalidated,
            "seq": seq,
        }

    # ── DIAG ───────────────────────────────────────────────────

    def diag(self, path: str = "") -> dict[str, Any]:
        """Diagnostic info about the mediator state.

        Parameters
        ----------
        path : str
            If empty, return summary.  If specific, return detail
            for that node.

        Returns
        -------
        dict
            Tree stats, cache stats, and per-node details.
        """
        now = time.time()

        if path:
            # Detail for one node
            node = self._tree.resolve(path)
            if node is None:
                return {"error": f"path not found: {path!r}"}

            entry = self._get_cached(path)
            d: dict[str, Any] = {
                "path": path,
                "registered": node.is_registered,
                "has_resolver": node.resolver is not None,
                "ttl": None if (node.ttl is not None and node.ttl == math.inf) else node.ttl,
                "persist": node.persist,
                "depends_on": node.depends_on,
                "dependents": node.dependents,
                "is_branch": node.is_branch,
                "children": [c.path for c in node.children.values()],
                "last_change_seq": node.last_change_seq,
                "refreshing": path in self._refreshing,
            }
            if entry is not None:
                d["cached"] = True
                d["age_s"] = round(now - entry.computed_at, 1)
                d["source"] = entry.source
                d["seq"] = entry.seq
                d["elapsed_s"] = round(entry.elapsed_s, 3)
                # Staleness
                if node.ttl is not None and node.ttl != math.inf:
                    d["stale"] = (now - entry.computed_at) >= node.ttl
                    d["ttl_remaining_s"] = round(
                        max(0, node.ttl - (now - entry.computed_at)), 1
                    )
                else:
                    d["stale"] = False
            else:
                d["cached"] = False

            return d

        # Summary of all nodes
        tree_stats = self._tree.stats()

        with self._lock:
            cache_keys = set(self._cache.keys())

        cached_count = 0
        stale_count = 0
        entries: dict[str, dict] = {}

        for node_path in self._tree.all_paths():
            node = self._tree.resolve(node_path)
            if node is None:
                continue

            entry_info: dict[str, Any] = {
                "depends_on": node.depends_on,
                "dependents": node.dependents,
            }
            if node_path in cache_keys:
                entry = self._get_cached(node_path)
                if entry is not None:
                    cached_count += 1
                    entry_info["cached"] = True
                    age = now - entry.computed_at
                    entry_info["age_s"] = round(age, 1)
                    entry_info["source"] = entry.source
                    entry_info["seq"] = entry.seq

                    is_stale = False
                    if node.ttl is not None and node.ttl != math.inf:
                        is_stale = age >= node.ttl
                    entry_info["stale"] = is_stale
                    if is_stale:
                        stale_count += 1
            else:
                entry_info["cached"] = False

            entries[node_path] = entry_info

        return {
            "tree": tree_stats,
            "seq": self._seq,
            "cached": cached_count,
            "stale": stale_count,
            "batch_active": self._batch_active,
            "subscriptions": len(self._subscriptions),
            "refreshing": sorted(self._refreshing),
            "has_executor": self._executor is not None,
            "entries": entries,
        }

    # ── Internal helpers ───────────────────────────────────────

    def _get_cached(self, path: str) -> CacheEntry | None:
        """Thread-safe cache read."""
        with self._lock:
            return self._cache.get(path)

    def _set_cached(self, path: str, entry: CacheEntry) -> None:
        """Thread-safe cache write."""
        with self._lock:
            self._cache[path] = entry

    def _remove_cached(self, path: str) -> bool:
        """Thread-safe cache delete.  Returns True if entry existed."""
        with self._lock:
            return self._cache.pop(path, None) is not None

    def _get_compute_lock(self, path: str) -> threading.Lock:
        """Get or create a per-path compute lock."""
        with self._lock:
            if path not in self._compute_locks:
                self._compute_locks[path] = threading.Lock()
            return self._compute_locks[path]

    def _next_seq(self) -> int:
        """Increment and return the next sequence number."""
        with self._lock:
            self._seq += 1
            return self._seq

    @staticmethod
    def _make_result(
        data: Any,
        path: str,
        source: str,
        age_s: float,
        seq: int,
        explanation: list[str],
        *,
        stale: bool = False,
        refreshing: bool = False,
    ) -> dict[str, Any]:
        """Build the standard result dict."""
        meta: dict[str, Any] = {
            "path": path,
            "source": source,
            "age_s": round(age_s, 1),
            "seq": seq,
        }
        if stale:
            meta["stale"] = True
            meta["refreshing"] = refreshing
        if explanation:
            meta["explain"] = "; ".join(explanation)
        return {"data": data, "meta": meta}

    # ── Phase 5: EventBus bridge ───────────────────────────────

    def _publish_change(
        self,
        trigger: str,
        seq: int,
        writes: list[str],
        invalidated: list[str],
    ) -> None:
        """Publish mediator change events on the EventBus.

        Deferred import avoids circular dependency (EventBus does
        not import from mediator).
        """
        try:
            from src.core.services.event_bus import bus
        except Exception:
            logger.debug("EventBus not available, skipping publish")
            return

        if writes:
            bus.publish(
                "mediator:write",
                key=trigger,
                data={
                    "trigger": trigger,
                    "mediator_seq": seq,
                    "writes": writes,
                },
            )

        if invalidated:
            bus.publish(
                "mediator:invalidated",
                key=trigger,
                data={
                    "trigger": trigger,
                    "mediator_seq": seq,
                    "invalidated": invalidated,
                },
            )

    # ── Phase 5: Batch mode ────────────────────────────────────

    @contextmanager
    def batch(self) -> Generator[None, None, None]:
        """Accumulate changes and publish one aggregate event on exit.

        Usage::

            with mediator.batch():
                mediator.put("devops.git", data=git_data)
                mediator.put("devops.docker", data=docker_data)
            # → ONE aggregate event listing all affected paths

        During batch mode:
        - Individual ``put()`` calls do NOT publish events
        - Changes accumulate in ``_batch_writes`` / ``_batch_invalidated``
        - On ``__exit__``, one aggregate event publishes

        Raises
        ------
        RuntimeError
            If batch mode is already active (no nesting).
        """
        if self._batch_active:
            raise RuntimeError("Nested batch() is not supported")

        self._batch_active = True
        self._batch_writes = []
        self._batch_invalidated = []
        self._batch_seq = 0

        try:
            yield
        finally:
            # Grab accumulated state and reset
            writes = self._batch_writes
            invalidated = self._batch_invalidated
            seq = self._batch_seq
            self._batch_active = False
            self._batch_writes = []
            self._batch_invalidated = []
            self._batch_seq = 0

            # Publish aggregate event + notify subscribers
            if writes or invalidated:
                self._publish_change(
                    "batch", seq, writes, invalidated,
                )
                if writes:
                    self._notify_subscribers(
                        "write", "batch", seq, writes,
                    )
                if invalidated:
                    self._notify_subscribers(
                        "invalidated", "batch", seq, invalidated,
                    )

    # ── Phase 6A: subscribe ────────────────────────────────────

    def subscribe(
        self,
        pattern: str,
        callback: Callable[[dict], None],
    ) -> str:
        """Register a callback for path pattern changes.

        The callback is called synchronously from ``put()`` whenever
        a matching path is written or invalidated.  Callbacks must
        be fast (< 1ms) — log, queue work, update state.  Do NOT
        perform heavy computation.

        Parameters
        ----------
        pattern : str
            Glob pattern (fnmatch syntax).  E.g. ``"devops.*"``,
            ``"posture.toolchain"``, ``"*"``.
        callback : Callable[[dict], None]
            Called with ``{"type": ..., "trigger": ..., "seq": ...,
            "paths": [...]}``.

        Returns
        -------
        str
            Subscription ID for ``unsubscribe()``.
        """
        self._sub_counter += 1
        sub_id = f"sub-{self._sub_counter}"
        self._subscriptions[sub_id] = _Subscription(
            id=sub_id, pattern=pattern, callback=callback,
        )
        logger.debug(
            "subscribe: id=%s pattern=%s", sub_id, pattern,
        )
        return sub_id

    def unsubscribe(self, sub_id: str) -> bool:
        """Remove a subscription.

        Returns
        -------
        bool
            True if the subscription was found and removed.
        """
        removed = self._subscriptions.pop(sub_id, None)
        if removed is not None:
            logger.debug("unsubscribe: id=%s", sub_id)
            return True
        return False

    def _notify_subscribers(
        self,
        event_type: str,
        trigger: str,
        seq: int,
        paths: list[str],
        *,
        compute_meta: dict[str, Any] | None = None,
    ) -> None:
        """Call all matching subscribers.  Errors logged and swallowed.

        Parameters
        ----------
        compute_meta : dict | None
            Extra metadata included only for ``"computed"`` events.
            Contains ``data``, ``elapsed_s``, ``computed_at``.
            Subscribers that need compute details (e.g. activity
            logging) use this; others can ignore it.
        """
        if not self._subscriptions:
            return

        event: dict[str, Any] = {
            "type": event_type,
            "trigger": trigger,
            "seq": seq,
            "paths": paths,
        }
        if compute_meta is not None:
            event["compute_meta"] = compute_meta

        for sub in list(self._subscriptions.values()):
            # Check if any affected path matches this subscriber's pattern
            matched = any(
                fnmatch.fnmatch(p, sub.pattern) for p in paths
            )
            if not matched:
                continue

            try:
                sub.callback(event)
            except Exception:
                logger.exception(
                    "subscriber %s (pattern=%s) failed for %s",
                    sub.id, sub.pattern, trigger,
                )

    # ── Phase 6A: refreshing state ─────────────────────────────

    def mark_refreshing(self, path: str) -> None:
        """Mark a path as being refreshed in the background."""
        with self._lock:
            self._refreshing.add(path)

    def clear_refreshing(self, path: str) -> None:
        """Mark a path as done refreshing."""
        with self._lock:
            self._refreshing.discard(path)

    # ── Phase 6B: refresh / bust / dispatch ────────────────────

    def refresh(self, *paths: str) -> dict[str, Any]:
        """Force-recompute one or more paths.

        If an executor is configured and multiple paths are given,
        resolvers run concurrently.  Otherwise, sequential.

        Parameters
        ----------
        *paths : str
            One or more registered tree paths to recompute.

        Returns
        -------
        dict
            ``{"refreshed": {path: result_meta}, "errors": {path: str},
            "elapsed_s": float}``
        """
        if not paths:
            return {"refreshed": {}, "errors": {}, "elapsed_s": 0.0}

        t0 = time.time()
        refreshed: dict[str, Any] = {}
        errors: dict[str, str] = {}

        if self._executor is not None and len(paths) > 1:
            # Parallel via injected executor
            future_map: dict[Future, str] = {}
            for p in paths:
                fut = self._executor.submit(self.get, p, force=True)
                future_map[fut] = p

            for fut in future_map:
                p = future_map[fut]
                try:
                    result = fut.result()
                    refreshed[p] = result.get("meta", {})
                except Exception as exc:
                    errors[p] = str(exc)
        else:
            # Sequential
            for p in paths:
                try:
                    result = self.get(p, force=True)
                    refreshed[p] = result.get("meta", {})
                except Exception as exc:
                    errors[p] = str(exc)

        elapsed = round(time.time() - t0, 3)
        return {
            "refreshed": refreshed,
            "errors": errors,
            "elapsed_s": elapsed,
        }

    def refresh_branch(self, prefix: str) -> dict[str, Any]:
        """Recompute all registered nodes under a prefix.

        Parameters
        ----------
        prefix : str
            Dot-separated prefix, e.g. ``"posture"`` refreshes
            all ``posture.*`` nodes.

        Returns
        -------
        dict
            Same format as ``refresh()``.
        """
        paths = [
            p for p in self._tree.all_paths()
            if p.startswith(prefix + ".")
        ]
        return self.refresh(*paths)

    def refresh_stale(self, prefix: str = "") -> dict[str, Any]:
        """Recompute only nodes whose cache has expired.

        Parameters
        ----------
        prefix : str
            Optional prefix filter.  If empty, checks all nodes.

        Returns
        -------
        dict
            Same format as ``refresh()``.
        """
        now = time.time()
        stale_paths: list[str] = []

        for path in self._tree.all_paths():
            if prefix and not path.startswith(prefix + "."):
                continue
            node = self._tree.resolve(path)
            if node is None:
                continue
            entry = self._get_cached(path)
            if entry is None:
                continue  # not cached = nothing to refresh
            if node.ttl is not None and node.ttl != math.inf:
                if (now - entry.computed_at) >= node.ttl:
                    stale_paths.append(path)

        return self.refresh(*stale_paths)

    def bust(
        self,
        max_age: float,
        prefix: str = "",
        *,
        notify: bool = True,
    ) -> dict[str, Any]:
        """Invalidate cached entries older than ``max_age`` seconds.

        Parameters
        ----------
        max_age : float
            Entries older than this (in seconds) are invalidated.
        prefix : str
            Optional prefix filter.  If empty, checks all nodes.
        notify : bool
            Whether to publish events for each invalidation.

        Returns
        -------
        dict
            ``{"busted": [paths], "count": int}``
        """
        now = time.time()
        busted: list[str] = []

        for path in self._tree.all_paths():
            if prefix and not path.startswith(prefix + "."):
                continue
            entry = self._get_cached(path)
            if entry is not None and (now - entry.computed_at) >= max_age:
                self.put(path, notify=notify)
                busted.append(path)

        return {"busted": busted, "count": len(busted)}

    def bust_path(
        self,
        path: str,
        *,
        cascade: bool = True,
        cascade_depth: int = -1,
        notify: bool = True,
    ) -> dict[str, Any]:
        """Invalidate a specific path and optionally cascade.

        Convenience wrapper around ``put(path, data=None)``.
        Unlike ``bust()`` which is age-based across all nodes,
        this targets a specific path and removes its cache entry
        plus all transitive dependents.

        Parameters
        ----------
        path : str
            Dot-separated path to invalidate.
        cascade : bool
            Whether to cascade-invalidate all dependents.
        cascade_depth : int
            Maximum cascade depth.  -1 = infinite.
        notify : bool
            Whether to publish change events.

        Returns
        -------
        dict
            ``{"invalidated": [...], "seq": N}``
        """
        return self.put(
            path, data=None, cascade=cascade,
            cascade_depth=cascade_depth, notify=notify,
        )

    def dispatch(
        self,
        *paths: str,
        priority: int | None = None,
        on_complete: Callable[[], None] | None = None,
    ) -> dict[str, Any]:
        """Submit paths for background recompute.  Returns immediately.

        Uses the work queue (if available), executor (legacy), or
        the ``on_stale`` hook for background execution.  If none
        is configured, paths are marked as dispatched but no
        background work occurs.

        Parameters
        ----------
        *paths : str
            Paths to recompute in the background.
        priority : int | None
            Priority level for the work queue (see ``Priority``
            enum in ``work_queue.py``).  ``None`` uses LOW (3)
            as default.  Ignored when using legacy executor.
        on_complete : Callable | None
            Called when ALL paths in this dispatch have completed.
            Used for tiered dispatch gating.  Only works with
            the work queue.

        Returns
        -------
        dict
            ``{"task_id": str, "paths": list, "status": str}``
        """
        self._dispatch_counter += 1
        task_id = f"task-{self._dispatch_counter}"

        valid_paths: list[str] = []
        for p in paths:
            node = self._tree.resolve(p)
            if node is not None and node.is_registered:
                valid_paths.append(p)
                self.mark_refreshing(p)

        if not valid_paths:
            # Fire on_complete immediately for empty dispatch
            if on_complete is not None:
                try:
                    on_complete()
                except Exception:
                    logger.exception(
                        "dispatch %s: on_complete failed (empty)", task_id,
                    )
            return {
                "task_id": task_id,
                "paths": [],
                "status": "empty",
            }

        if self._work_queue is not None:
            # ── Work queue path (priority-aware) ─────────────
            from .work_queue import Priority, WorkItem

            default_priority = (
                priority if priority is not None else Priority.LOW
            )

            items: list[WorkItem] = []
            for p in valid_paths:
                node = self._tree.resolve(p)
                item_size = node.size if node is not None else 1

                items.append(WorkItem(
                    priority=default_priority,
                    size=item_size,
                    path=p,
                    resolver=lambda p=p: self._dispatch_worker(
                        task_id, [p],
                    ),
                    callback=None,
                    error_callback=lambda exc, p=p: logger.exception(
                        "dispatch %s: work_queue failed for %s",
                        task_id, p,
                    ),
                ))

            self._work_queue.submit_batch(
                items, on_complete=on_complete,
            )

        elif self._executor is not None:
            # ── Legacy executor path ─────────────────────────
            for p in valid_paths:
                self._executor.submit(
                    self._dispatch_worker, task_id, [p],
                )
        elif self._on_stale is not None:
            for p in valid_paths:
                try:
                    self._on_stale(p)
                except Exception:
                    logger.exception(
                        "dispatch on_stale failed for %s", p,
                    )
        else:
            logger.debug(
                "dispatch %s: no work_queue, executor, or on_stale hook",
                task_id,
            )

        return {
            "task_id": task_id,
            "paths": valid_paths,
            "status": "dispatched",
        }

    def _dispatch_worker(
        self,
        task_id: str,
        paths: list[str],
    ) -> None:
        """Background worker for dispatch().  Runs in the executor.

        Skips nodes whose cached data is still FRESH (age < TTL).
        Recomputes nodes that are stale or have no cached data.

        This is the delta principle applied to dispatch: only do
        work for data that actually needs refreshing.
        """
        for p in paths:
            try:
                entry = self._get_cached(p)
                if entry is not None:
                    # Check if the cached data is still fresh
                    node = self._tree.resolve(p)
                    if node is not None and node.ttl is not None:
                        age = time.time() - entry.computed_at
                        if node.ttl == math.inf or age < node.ttl:
                            logger.debug(
                                "dispatch %s: %s still fresh "
                                "(age=%.1fs, ttl=%s), skipping",
                                task_id, p, age, node.ttl,
                            )
                            continue
                    elif node is not None and node.ttl is None:
                        # No TTL = event-driven invalidation.
                        # If it has cached data, it's valid until
                        # explicitly invalidated via put/bust.
                        logger.debug(
                            "dispatch %s: %s cached (no TTL, "
                            "event-driven), skipping",
                            task_id, p,
                        )
                        continue
                self.get(p, force=True)
            except Exception:
                logger.exception(
                    "dispatch %s: recompute failed for %s", task_id, p,
                )
            finally:
                self.clear_refreshing(p)

