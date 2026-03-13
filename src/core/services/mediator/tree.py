"""
DataTree — hierarchical namespace for mediator data nodes.

The tree is a registry of METADATA, not data.  Each node describes:
- what resolver function produces its value
- how it expires (TTL or mtime)
- what it depends on (for cascade invalidation)
- whether it persists to disk

The actual data (cache entries) lives in the QueryMediator, not here.

Thread safety
─────────────
The tree is built at startup (registration phase) and then read-only
during normal operation.  No locking is needed — the tree structure
is immutable after ``init()``.

Path format
───────────
Dot-separated strings:  ``"posture.toolchain.items.go"``

Each segment is either a BRANCH (has children) or a REGISTERED NODE
(has a resolver).  A branch can also be a registered node — e.g.
``"posture.toolchain"`` is both a node with a resolver AND a branch
with children like ``"posture.toolchain.items"``.
"""

from __future__ import annotations

import fnmatch
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ── Data structures ────────────────────────────────────────────────


@dataclass
class TreeRegistration:
    """Input for tree.register() — what the caller provides.

    Parameters
    ----------
    path : str
        Dot-separated path (e.g. ``"posture.toolchain"``).
    resolver : Callable | None
        Function that produces the value.  Signature varies by node:
        some take ``project_root``, some take no args.  The mediator
        wraps the call.
    ttl : float | None
        Seconds before the cached value expires.  ``None`` means
        mtime-based (use ``mtime_paths`` instead).  ``math.inf``
        means never expires.
    mtime_paths : list[str] | None
        Relative paths to watch for changes (if mtime-based).
        Mutually exclusive with ``ttl`` in most cases, though a
        node CAN have both (TTL with mtime as early-invalidation).
    persist : bool
        If True, cache entry is saved to disk and survives restart.
    depends_on : list[str] | None
        Paths that this node depends on.  Supports glob patterns
        (e.g. ``"detect.tools.*"``).  When a dependency is invalidated,
        this node is also invalidated (cascade).
    """

    path: str
    resolver: Callable[..., Any] | None = None
    ttl: float | None = None
    mtime_paths: list[str] | None = None
    persist: bool = False
    depends_on: list[str] | None = None


@dataclass
class TreeNode:
    """A single node in the data tree.

    Created by ``DataTree.register()``.  Branch nodes (auto-created
    intermediates) have ``resolver=None``.
    """

    path: str
    resolver: Callable[..., Any] | None = None
    ttl: float | None = None
    mtime_paths: list[str] | None = None
    persist: bool = False
    depends_on: list[str] = field(default_factory=list)
    dependents: list[str] = field(default_factory=list)
    children: dict[str, TreeNode] = field(default_factory=dict)
    parent: str | None = None
    is_registered: bool = False  # False for auto-created branches
    last_change_seq: int = 0     # seq of last write/invalidation (Phase 5)

    @property
    def is_branch(self) -> bool:
        """True if this node has children."""
        return bool(self.children)

    @property
    def is_leaf(self) -> bool:
        """True if this node has no children."""
        return not self.children

    @property
    def segment(self) -> str:
        """Last segment of the path (e.g. 'toolchain' for 'posture.toolchain')."""
        return self.path.rsplit(".", 1)[-1]

    def __repr__(self) -> str:
        kind = "branch" if self.is_branch else "leaf"
        reg = " [registered]" if self.is_registered else ""
        return f"TreeNode({self.path!r}, {kind}{reg})"


# ── DataTree ───────────────────────────────────────────────────────


class DataTree:
    """Hierarchical namespace for data nodes.

    Usage::

        tree = DataTree()
        tree.register(TreeRegistration(
            path="posture.toolchain",
            resolver=scan_toolchain,
            ttl=300,
            persist=True,
            depends_on=["detect.tools.*"],
        ))

        node = tree.resolve("posture.toolchain")
        # node.resolver == scan_toolchain
        # node.ttl == 300
    """

    def __init__(self) -> None:
        self._root: dict[str, TreeNode] = {}
        self._flat: dict[str, TreeNode] = {}  # path → node (fast lookup)

    # ── Registration ───────────────────────────────────────────

    def register(self, reg: TreeRegistration) -> TreeNode:
        """Register a data node.

        Creates intermediate branch nodes as needed.  For example,
        registering ``"posture.toolchain.items"`` auto-creates
        ``"posture"`` and ``"posture.toolchain"`` as branch nodes
        (if they don't already exist).

        Raises
        ------
        ValueError
            If the path is already registered (has a resolver).
            Auto-created branch nodes CAN be promoted to registered
            nodes by calling register with a resolver.
        """
        if not reg.path:
            raise ValueError("Path cannot be empty")

        segments = reg.path.split(".")
        if not all(segments):
            raise ValueError(f"Invalid path (empty segment): {reg.path!r}")

        # Walk/create intermediate branches
        current_children = self._root
        parent_path: str | None = None

        for i, seg in enumerate(segments[:-1]):
            partial_path = ".".join(segments[: i + 1])

            if seg not in current_children:
                # Auto-create intermediate branch
                branch = TreeNode(path=partial_path, parent=parent_path)
                current_children[seg] = branch
                self._flat[partial_path] = branch
                logger.debug("auto-created branch: %s", partial_path)

            current_children = current_children[seg].children
            parent_path = partial_path

        # Create or promote the target node
        last_seg = segments[-1]
        target_path = reg.path

        if last_seg in current_children:
            existing = current_children[last_seg]
            if existing.is_registered:
                raise ValueError(
                    f"Path already registered: {target_path!r}"
                )
            # Promote auto-created branch to registered node
            existing.resolver = reg.resolver
            existing.ttl = reg.ttl
            existing.mtime_paths = reg.mtime_paths
            existing.persist = reg.persist
            existing.depends_on = list(reg.depends_on or [])
            existing.is_registered = True
            node = existing
        else:
            node = TreeNode(
                path=target_path,
                resolver=reg.resolver,
                ttl=reg.ttl,
                mtime_paths=reg.mtime_paths,
                persist=reg.persist,
                depends_on=list(reg.depends_on or []),
                parent=parent_path,
                is_registered=True,
            )
            current_children[last_seg] = node
            self._flat[target_path] = node

        # Update reverse dependencies
        self._recompute_dependents()

        logger.debug(
            "registered: %s (ttl=%s, persist=%s, deps=%s)",
            target_path, reg.ttl, reg.persist, node.depends_on,
        )
        return node

    # ── Path resolution ────────────────────────────────────────

    def resolve(self, path: str) -> TreeNode | None:
        """Find a node by dot-separated path.

        Returns None if the path doesn't exist in the tree.
        """
        return self._flat.get(path)

    def children(self, path: str = "") -> list[TreeNode]:
        """Return direct children of a branch node.

        If path is empty, returns top-level nodes.
        """
        if not path:
            return list(self._root.values())

        node = self._flat.get(path)
        if node is None:
            return []
        return list(node.children.values())

    # ── Dependency graph ───────────────────────────────────────

    def dependents(self, path: str, *, depth: int = -1) -> list[str]:
        """Return all paths that depend on the given path.

        Walks the dependency graph transitively.

        Parameters
        ----------
        path : str
            The path to find dependents of.
        depth : int
            Maximum cascade depth.  -1 = infinite.  0 = direct only.
        """
        result: list[str] = []
        visited: set[str] = set()
        self._walk_dependents(path, result, visited, depth, 0)
        return result

    def _walk_dependents(
        self,
        path: str,
        result: list[str],
        visited: set[str],
        max_depth: int,
        current_depth: int,
    ) -> None:
        """Recursively collect dependents."""
        if path in visited:
            return
        visited.add(path)

        node = self._flat.get(path)
        if node is None:
            return

        for dep_path in node.dependents:
            if dep_path not in visited:
                result.append(dep_path)
                if max_depth == -1 or current_depth < max_depth:
                    self._walk_dependents(
                        dep_path, result, visited,
                        max_depth, current_depth + 1,
                    )

    def _recompute_dependents(self) -> None:
        """Rebuild all reverse dependency lists.

        Called after each registration.  O(N*M) where N = nodes,
        M = avg depends_on list length.  Fine for <1000 nodes.
        """
        # Clear all dependents
        for node in self._flat.values():
            node.dependents = []

        # Rebuild from depends_on
        for node in self._flat.values():
            for dep_pattern in node.depends_on:
                if "*" in dep_pattern or "?" in dep_pattern:
                    # Glob pattern — match against all paths
                    for candidate_path, candidate_node in self._flat.items():
                        if fnmatch.fnmatch(candidate_path, dep_pattern):
                            if node.path not in candidate_node.dependents:
                                candidate_node.dependents.append(node.path)
                else:
                    # Exact path
                    dep_node = self._flat.get(dep_pattern)
                    if dep_node is not None:
                        if node.path not in dep_node.dependents:
                            dep_node.dependents.append(node.path)

    # ── Glob matching ──────────────────────────────────────────

    def match(self, pattern: str) -> list[TreeNode]:
        """Return all nodes matching a glob pattern.

        Examples::

            tree.match("posture.*")       # direct children of posture
            tree.match("posture.**")      # all descendants of posture
            tree.match("detect.tools.*")  # all tool detections
        """
        results: list[TreeNode] = []
        for path, node in self._flat.items():
            if fnmatch.fnmatch(path, pattern):
                results.append(node)
        return results

    # ── Diagnostics ────────────────────────────────────────────

    def all_paths(self) -> list[str]:
        """Return all registered paths (sorted)."""
        return sorted(
            p for p, n in self._flat.items() if n.is_registered
        )

    def all_nodes(self) -> list[TreeNode]:
        """Return all nodes including auto-created branches."""
        return list(self._flat.values())

    def subtree(self, path: str = "") -> dict:
        """Return tree structure from a node down (for diagnostics).

        Returns a nested dict suitable for JSON serialization::

            {
                "path": "posture",
                "registered": false,
                "children": {
                    "toolchain": {
                        "path": "posture.toolchain",
                        "registered": true,
                        "ttl": 300,
                        ...
                    }
                }
            }
        """
        if not path:
            return {
                "path": "",
                "children": {
                    seg: self._node_to_dict(node)
                    for seg, node in self._root.items()
                },
            }

        node = self._flat.get(path)
        if node is None:
            return {}
        return self._node_to_dict(node)

    def stats(self) -> dict:
        """Summary statistics about the tree."""
        all_nodes = list(self._flat.values())
        registered = [n for n in all_nodes if n.is_registered]
        branches = [n for n in all_nodes if n.is_branch]
        leaves = [n for n in registered if n.is_leaf]
        persistent = [n for n in registered if n.persist]

        return {
            "total_nodes": len(all_nodes),
            "registered": len(registered),
            "branches": len(branches),
            "leaves": len(leaves),
            "persistent": len(persistent),
        }

    def _node_to_dict(self, node: TreeNode) -> dict:
        """Serialize a node for diagnostics."""
        d: dict = {
            "path": node.path,
            "registered": node.is_registered,
        }
        if node.is_registered:
            d["has_resolver"] = node.resolver is not None
            if node.ttl is not None:
                d["ttl"] = node.ttl
            if node.mtime_paths:
                d["mtime_paths"] = node.mtime_paths
            d["persist"] = node.persist
            if node.depends_on:
                d["depends_on"] = node.depends_on
            if node.dependents:
                d["dependents"] = node.dependents
        if node.children:
            d["children"] = {
                seg: self._node_to_dict(child)
                for seg, child in node.children.items()
            }
        return d
