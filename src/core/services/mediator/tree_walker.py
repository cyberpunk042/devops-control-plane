"""
Consolidated Tree Walker — single os.walk, multiple consumers.

Instead of N separate os.walk passes (one per ops function), this
module provides a single-walk-multiple-consumer pattern:

    1. Ops functions register ``TreeWalkCollector`` instances
    2. ``ConsolidatedWalker.walk()`` executes ONE os.walk
    3. Each collector receives matching (rel_dir, dirnames, filenames)
       tuples during the walk
    4. Collectors accumulate their results internally

This eliminates redundant I/O: 17 separate walks become 1 shared walk.

Usage
-----

Standalone (for ops functions that need file *content* during walk)::

    from src.core.services.mediator.tree_walker import (
        ConsolidatedWalker, TreeWalkCollector,
    )

    class SecurityCollector(TreeWalkCollector):
        name = "security"
        wants_full_tree = True

        def __init__(self):
            self.files: list[str] = []

        def on_dir(self, rel_dir, dirnames, filenames):
            for fname in filenames:
                self.files.append(os.path.join(rel_dir, fname))

    collector = SecurityCollector()
    walker = ConsolidatedWalker(project_root, _SKIP_DIRS)
    walker.walk([collector])
    # collector.files is now populated

Batched (via WorkQueue integration)::

    # The WorkQueue detects multiple pending tasks that need walks
    # and batches them into a single ConsolidatedWalker.walk() call.
    # See work_queue.py for details.

Notes
-----
- Collectors that only need file listings (by extension, by name)
  should use ``ScanView`` instead — it's even faster (O(1) lookups,
  no walk at all).  See ``registrations/index.py``.
- This module is for collectors that need the walk to do per-file
  processing (reading content, parsing AST, etc.) during the walk.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)

# Default directories to skip during tree walks
SKIP_DIRS: frozenset[str] = frozenset({
    ".git", ".venv", "venv", "node_modules", "__pycache__",
    ".mypy_cache", ".ruff_cache", ".pytest_cache", ".tox",
    "dist", "build", ".eggs", ".terraform", ".pages",
    "htmlcov", ".backup", "state",
})


# ── Collector Protocol ──────────────────────────────────────────


@runtime_checkable
class TreeWalkCollector(Protocol):
    """Interface that ops functions implement to participate in a
    consolidated tree walk.

    Each collector declares:
    - ``name``: identifier for logging and diagnostics
    - ``wants_full_tree``: whether it needs the entire project tree
    - ``scope_dirs``: if not full-tree, which root-relative dirs to walk
    - ``on_dir()``: callback invoked for each matching directory

    After the walk completes, the collector's accumulated state
    (whatever it stored in ``on_dir``) is its result.
    """

    name: str
    wants_full_tree: bool
    scope_dirs: list[str] | None

    def on_dir(
        self,
        rel_dir: str,
        dirnames: list[str],
        filenames: list[str],
    ) -> None:
        """Called for each directory in the walk.

        Parameters
        ----------
        rel_dir : str
            Directory path relative to project root (e.g. ``"src/core"``).
            Root itself is ``"."``.
        dirnames : list[str]
            Subdirectory names (already pruned of skip dirs).
        filenames : list[str]
            File names in this directory.
        """
        ...


# ── Concrete base class for collectors ──────────────────────────


@dataclass
class BaseCollector:
    """Convenience base class for collectors.

    Subclass this and override ``on_dir()`` to accumulate results.
    """

    name: str = ""
    wants_full_tree: bool = True
    scope_dirs: list[str] | None = None
    _files_seen: int = field(default=0, init=False, repr=False)

    def on_dir(
        self,
        rel_dir: str,
        dirnames: list[str],
        filenames: list[str],
    ) -> None:
        """Override in subclass."""
        raise NotImplementedError


# ── Consolidated Walker ─────────────────────────────────────────


class ConsolidatedWalker:
    """Executes ONE ``os.walk`` and feeds ALL registered collectors.

    The walker determines the minimal walk scope: if all collectors
    are scoped to specific subdirectories, only those dirs are walked.
    If any collector needs the full tree, the full tree is walked.

    Parameters
    ----------
    project_root : Path
        The project root directory.
    skip_dirs : frozenset[str] | None
        Directory names to skip.  Defaults to ``SKIP_DIRS``.
    """

    def __init__(
        self,
        project_root: Path,
        skip_dirs: frozenset[str] | None = None,
    ) -> None:
        self._root = project_root
        self._skip = skip_dirs if skip_dirs is not None else SKIP_DIRS

    def walk(self, collectors: list[TreeWalkCollector]) -> dict[str, int]:
        """Execute one walk, feed all collectors at each step.

        Parameters
        ----------
        collectors : list[TreeWalkCollector]
            The collectors to feed during the walk.

        Returns
        -------
        dict[str, int]
            Statistics: ``{"dirs_walked": N, "files_seen": N,
            "collectors": N}``.
        """
        if not collectors:
            return {"dirs_walked": 0, "files_seen": 0, "collectors": 0}

        # Determine walk scope
        full_tree_needed = any(c.wants_full_tree for c in collectors)

        if full_tree_needed:
            walk_roots = [self._root]
        else:
            # Union of all scoped dirs
            all_dirs: set[Path] = set()
            for c in collectors:
                if c.scope_dirs:
                    for d in c.scope_dirs:
                        candidate = self._root / d
                        if candidate.is_dir():
                            all_dirs.add(candidate)
            walk_roots = sorted(all_dirs) if all_dirs else [self._root]

        # Pre-classify collectors for faster dispatch
        full_collectors = [c for c in collectors if c.wants_full_tree]
        scoped_collectors = [c for c in collectors if not c.wants_full_tree]

        dirs_walked = 0
        files_seen = 0

        for walk_root in walk_roots:
            for dirpath, dirnames, filenames in os.walk(walk_root):
                # Prune skipped directories IN-PLACE
                dirnames[:] = [
                    d for d in dirnames
                    if d not in self._skip and not d.startswith(".")
                ]

                # Compute relative path once
                try:
                    rel_dir = os.path.relpath(dirpath, self._root)
                except ValueError:
                    # On Windows, relpath can fail across drives
                    rel_dir = str(dirpath)

                dirs_walked += 1
                files_seen += len(filenames)

                # Feed full-tree collectors (always match)
                for c in full_collectors:
                    try:
                        c.on_dir(rel_dir, dirnames, filenames)
                    except Exception:
                        logger.exception(
                            "Collector %s failed on dir %s",
                            c.name, rel_dir,
                        )

                # Feed scoped collectors (check if rel_dir is in scope)
                for c in scoped_collectors:
                    if self._in_scope(rel_dir, c.scope_dirs):
                        try:
                            c.on_dir(rel_dir, dirnames, filenames)
                        except Exception:
                            logger.exception(
                                "Collector %s failed on dir %s",
                                c.name, rel_dir,
                            )

        stats = {
            "dirs_walked": dirs_walked,
            "files_seen": files_seen,
            "collectors": len(collectors),
        }

        logger.debug(
            "ConsolidatedWalker: %d dirs, %d files, %d collectors",
            dirs_walked, files_seen, len(collectors),
        )

        return stats

    @staticmethod
    def _in_scope(
        rel_dir: str, scope_dirs: list[str] | None,
    ) -> bool:
        """Check if a relative directory is within the collector's scope."""
        if scope_dirs is None:
            return True  # no scope = match everything
        for sd in scope_dirs:
            if rel_dir == sd or rel_dir.startswith(sd + os.sep):
                return True
            # Also check forward slash  (cross-platform)
            if rel_dir.startswith(sd + "/"):
                return True
        return False


# ── Built-in collectors ─────────────────────────────────────────


class FileListCollector(BaseCollector):
    """Collects all file paths matching given extensions.

    This is a generic collector that accumulates relative file paths
    filtered by file extension.

    Parameters
    ----------
    name : str
        Identifier for this collector.
    extensions : frozenset[str]
        File extensions to match (WITH leading dot, e.g. ``".py"``).
    max_files : int
        Cap on total files collected.
    """

    def __init__(
        self,
        name: str,
        extensions: frozenset[str],
        *,
        max_files: int = 5000,
        wants_full_tree: bool = True,
        scope_dirs: list[str] | None = None,
    ) -> None:
        self.name = name
        self.extensions = extensions
        self.max_files = max_files
        self.wants_full_tree = wants_full_tree
        self.scope_dirs = scope_dirs
        self.files: list[str] = []

    def on_dir(
        self,
        rel_dir: str,
        dirnames: list[str],
        filenames: list[str],
    ) -> None:
        if len(self.files) >= self.max_files:
            return
        for fname in filenames:
            if len(self.files) >= self.max_files:
                return
            # Check extension
            dot_idx = fname.rfind(".")
            if dot_idx >= 0:
                ext = fname[dot_idx:]
                if ext in self.extensions:
                    path = (
                        os.path.join(rel_dir, fname)
                        if rel_dir != "."
                        else fname
                    )
                    self.files.append(path)


class FileNameCollector(BaseCollector):
    """Collects all file paths matching given exact filenames.

    Parameters
    ----------
    name : str
        Identifier for this collector.
    filenames : frozenset[str]
        Exact filenames to match (e.g. ``{"Dockerfile", "Chart.yaml"}``).
    """

    def __init__(
        self,
        name: str,
        target_filenames: frozenset[str],
        *,
        max_files: int = 100,
        wants_full_tree: bool = True,
        scope_dirs: list[str] | None = None,
    ) -> None:
        self.name = name
        self.target_filenames = target_filenames
        self.max_files = max_files
        self.wants_full_tree = wants_full_tree
        self.scope_dirs = scope_dirs
        self.files: list[str] = []

    def on_dir(
        self,
        rel_dir: str,
        dirnames: list[str],
        filenames: list[str],
    ) -> None:
        if len(self.files) >= self.max_files:
            return
        for fname in filenames:
            if fname in self.target_filenames:
                path = (
                    os.path.join(rel_dir, fname)
                    if rel_dir != "."
                    else fname
                )
                self.files.append(path)
                if len(self.files) >= self.max_files:
                    return
