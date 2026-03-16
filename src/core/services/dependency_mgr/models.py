"""
Data models for dependency management.

All scanner, tree, pipeline, and state models live here.
Follows the project's existing patterns:
  - ``@dataclass(frozen=True)`` for immutable records (matches ``Event``)
  - ``@dataclass`` (mutable) only for builder-constructed objects (``TreeNode``)
  - ``to_dict()`` / ``from_dict()`` for JSON serialization
  - Inline comments on fields describing purpose

Frozen dataclasses use tuples (not lists) for hashability.
Mutable dataclasses use lists for builder convenience.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Literal


# ═════════════════════════════════════════════════════════════════
#  Scanner output
# ═════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ManifestInfo:
    """Phase 1 scanner output — lightweight, no file I/O beyond stat().

    Produced by ``EcosystemAdapter.detect()``.  One per manifest file
    found in a directory.  Multiple manifests per ecosystem are possible
    (monorepo: requirements.txt at root AND in workers/).
    """

    ecosystem: str             # "pip", "npm", "go", "cargo", ...
    manifest_file: str         # "requirements.txt", "package.json"
    manifest_path: str         # Relative dir from project root: ".", "frontend/"
    lock_file: str | None      # "package-lock.json" if present, else None
    cli: str                   # Primary CLI tool: "pip", "npm", "go"
    cli_available: bool        # shutil.which() result
    mtime: float               # Manifest file mtime (cache invalidation key)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ecosystem": self.ecosystem,
            "manifest_file": self.manifest_file,
            "manifest_path": self.manifest_path,
            "lock_file": self.lock_file,
            "cli": self.cli,
            "cli_available": self.cli_available,
            "mtime": self.mtime,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ManifestInfo:
        return cls(
            ecosystem=d["ecosystem"],
            manifest_file=d["manifest_file"],
            manifest_path=d["manifest_path"],
            lock_file=d.get("lock_file"),
            cli=d.get("cli", ""),
            cli_available=d.get("cli_available", False),
            mtime=d.get("mtime", 0.0),
        )


@dataclass(frozen=True)
class DeclaredDep:
    """Phase 2 scanner output — one parsed dependency from a manifest.

    Produced by ``EcosystemAdapter.parse_manifest()``.
    """

    name: str                  # "requests", "react", "serde"
    version_spec: str          # "==2.31.0", "^18.2.0", "~5.3", ""
    pinned_version: str        # Resolved from lock file or spec: "2.31.0"
    group: str                 # "main", "dev", "optional", "build", "peer"
    source_file: str           # "requirements.txt", "package.json"
    source_path: str           # Relative dir: ".", "frontend/"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version_spec": self.version_spec,
            "pinned_version": self.pinned_version,
            "group": self.group,
            "source_file": self.source_file,
            "source_path": self.source_path,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DeclaredDep:
        return cls(
            name=d["name"],
            version_spec=d.get("version_spec", ""),
            pinned_version=d.get("pinned_version", ""),
            group=d.get("group", "main"),
            source_file=d.get("source_file", ""),
            source_path=d.get("source_path", "."),
        )


@dataclass(frozen=True)
class ParsedManifest:
    """Phase 2 scanner output — fully parsed manifest with dependencies.

    Produced by ``EcosystemAdapter.parse_manifest()``.
    Uses tuples (not lists) because frozen dataclasses require hashable fields.
    """

    info: ManifestInfo
    dependencies: tuple[DeclaredDep, ...]
    dev_dependencies: tuple[DeclaredDep, ...]
    total: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "info": self.info.to_dict(),
            "dependencies": [d.to_dict() for d in self.dependencies],
            "dev_dependencies": [d.to_dict() for d in self.dev_dependencies],
            "total": self.total,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ParsedManifest:
        info = ManifestInfo.from_dict(d["info"])
        deps = tuple(DeclaredDep.from_dict(x) for x in d.get("dependencies", ()))
        dev = tuple(DeclaredDep.from_dict(x) for x in d.get("dev_dependencies", ()))
        return cls(
            info=info,
            dependencies=deps,
            dev_dependencies=dev,
            total=d.get("total", len(deps) + len(dev)),
        )


# ═════════════════════════════════════════════════════════════════
#  Tree model
# ═════════════════════════════════════════════════════════════════


@dataclass
class TreeNode:
    """Scope tree node — mutable, built incrementally by the tree builder.

    Three levels::

        Global (root)
          ├── Ecosystem (pip:., npm:frontend)
          │     └── Package (pip:.:requests)
          ...

    Mutable because the tree builder enriches nodes in phases:
    Phase 1 (detection) → ecosystem nodes only.
    Phase 2 (parsing) → adds package children.
    Version intel → sets status, latest_version.
    Notes → sets note text.
    """

    id: str                    # "global", "pip:.", "pip:workers", "npm:frontend:react"
    label: str                 # "Global", "Python (.)", "react 2.31.0"
    level: Literal["global", "ecosystem", "package"]
    ecosystem: str | None = None   # "pip", "npm", etc. (None for global)
    path: str | None = None        # Relative dir (None for global)
    children: list[TreeNode] = field(default_factory=list)
    # Package-level fields (None for global/ecosystem nodes)
    version: str | None = None
    installed_version: str | None = None  # Actually installed in active venv
    latest_version: str | None = None
    status: str | None = None      # "current", "outdated", "deprecated", "eol", "yanked", "unknown"
    group: str | None = None       # "main", "dev", etc.
    note: str | None = None        # User annotation text

    def to_dict(self) -> dict[str, Any]:
        """Serialize — omits None/empty fields for clean JSON."""
        d: dict[str, Any] = {
            "id": self.id,
            "label": self.label,
            "level": self.level,
        }
        if self.ecosystem is not None:
            d["ecosystem"] = self.ecosystem
        if self.path is not None:
            d["path"] = self.path
        if self.children:
            d["children"] = [c.to_dict() for c in self.children]
        if self.version is not None:
            d["version"] = self.version
        if self.installed_version is not None:
            d["installedVersion"] = self.installed_version
        if self.latest_version is not None:
            d["latestVersion"] = self.latest_version
        if self.status is not None:
            d["status"] = self.status
        if self.group is not None:
            d["group"] = self.group
        if self.note is not None:
            d["note"] = self.note
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TreeNode:
        children = [cls.from_dict(c) for c in d.get("children", [])]
        return cls(
            id=d["id"],
            label=d["label"],
            level=d["level"],
            ecosystem=d.get("ecosystem"),
            path=d.get("path"),
            children=children,
            version=d.get("version"),
            installed_version=d.get("installedVersion"),
            latest_version=d.get("latestVersion"),
            status=d.get("status"),
            group=d.get("group"),
            note=d.get("note"),
        )


# ═════════════════════════════════════════════════════════════════
#  Operation events (yielded by the pipeline generator)
# ═════════════════════════════════════════════════════════════════


# Event types the pipeline yields
OP_EVENT_TYPES = frozenset({
    # Batch envelope (Global scope)
    "batch_start",             # Starting multi-ecosystem operation
    "batch_done",              # All ecosystems finished
    # Per-ecosystem lifecycle
    "snapshot_created",        # Lock/manifest files backed up
    "operation_start",         # Command about to run
    "log",                     # Raw output line from subprocess
    "package_resolved",        # Parsed: package X installed/updated
    "warning",                 # Parsed: deprecation, conflict, etc.
    "error",                   # Parsed: failure, missing dep, etc.
    "progress",                # Parsed: N/M packages (if detectable)
    "operation_done",          # Command finished (ok or error)
    # Rollback
    "rollback_start",          # Restoring snapshot files
    "rollback_done",           # Snapshot restored + reinstall done
})


@dataclass(frozen=True)
class OpEvent:
    """Single event in the operation pipeline stream.

    Transport-agnostic — the SSE route serializes these to JSON,
    the CLI prints them, tests collect them.  Same approach as
    ``docker_action_stream()`` yielding event dicts, but typed.
    """

    type: str                  # One of OP_EVENT_TYPES
    ts: float = field(default_factory=time.time)
    scope: str = ""            # TreeNode.id this event belongs to
    # Content fields (optional depending on type)
    line: str = ""             # Raw output line (for "log")
    package: str = ""          # Package name (for "package_resolved", "warning", "error")
    version: str = ""          # Version (for "package_resolved")
    action: str = ""           # "installed", "updated", "removed" (for "package_resolved")
    category: str = ""         # "deprecated", "conflict", "missing_dep" (for "warning"/"error")
    message: str = ""          # Human-readable (for "warning", "error", "done")
    severity: str = "info"     # "info", "warning", "error"
    status: str = ""           # "ok", "error" (for "done" events)
    command: str = ""          # The command being run (for "operation_start")
    count: int = 0             # Packages resolved (for "done" events)
    duration_ms: int = 0       # Elapsed milliseconds (for "done" events)
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize — omits empty/default fields for clean SSE JSON."""
        d: dict[str, Any] = {"type": self.type, "ts": self.ts}
        for key in ("scope", "line", "package", "version", "action",
                     "category", "message", "severity", "status",
                     "command"):
            val = getattr(self, key)
            if val:
                d[key] = val
        if self.count:
            d["count"] = self.count
        if self.duration_ms:
            d["duration_ms"] = self.duration_ms
        if self.detail:
            d["detail"] = self.detail
        return d


# ═════════════════════════════════════════════════════════════════
#  Streaming subprocess
# ═════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class SubprocessChunk:
    """One unit of streaming subprocess output.

    Yielded by ``stream_subprocess()`` — either a line of output
    or a completion sentinel.
    """

    type: Literal["line", "done"]
    line: str = ""                    # For type="line": the output text
    stream: Literal["stdout", "stderr", "merged"] = "merged"
    # For type="done"
    ok: bool = True
    exit_code: int = 0
    elapsed_ms: int = 0
    error: str = ""                   # Timeout or exception message


# ═════════════════════════════════════════════════════════════════
#  Version intelligence
# ═════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class VersionIntel:
    """Version health for one declared dependency.

    Produced by ``EcosystemAdapter.fetch_latest_version()`` and
    ``check_deprecated()``, combined by the version intelligence layer.
    """

    package: str
    ecosystem: str
    installed: str             # Currently installed/declared version
    latest: str | None         # Latest available (None if lookup failed)
    status: Literal[
        "current",             # Installed == latest
        "outdated",            # Newer version available
        "deprecated",          # Ecosystem reports deprecated
        "eol",                 # End-of-life per known databases
        "yanked",              # Version pulled from registry
        "unknown",             # Could not determine
    ]
    eol_date: str | None       # ISO date if known
    successor: str | None      # Replacement package if deprecated
    breaking: bool             # True if latest is a major version bump
    detail: str                # Human-readable explanation

    def to_dict(self) -> dict[str, Any]:
        return {
            "package": self.package,
            "ecosystem": self.ecosystem,
            "installed": self.installed,
            "latest": self.latest,
            "status": self.status,
            "eol_date": self.eol_date,
            "successor": self.successor,
            "breaking": self.breaking,
            "detail": self.detail,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> VersionIntel:
        return cls(
            package=d["package"],
            ecosystem=d["ecosystem"],
            installed=d.get("installed", ""),
            latest=d.get("latest"),
            status=d.get("status", "unknown"),
            eol_date=d.get("eol_date"),
            successor=d.get("successor"),
            breaking=d.get("breaking", False),
            detail=d.get("detail", ""),
        )


# ═════════════════════════════════════════════════════════════════
#  Rollback snapshots
# ═════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class Snapshot:
    """Record of a pre-operation state backup.

    Created before install/update operations.  Stores copies of
    manifest and lock files in ``.state/dependency_snapshots/``.
    """

    id: str                    # Timestamp-based: "2026-03-16T14-30-00"
    ts: float                  # time.time() when created
    operation: str             # "install", "update"
    scope: str                 # TreeNode.id that triggered the snapshot
    ecosystems: tuple[str, ...]  # Ecosystem IDs included
    files: tuple[tuple[str, str], ...]  # (original_path, snapshot_path) pairs

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "ts": self.ts,
            "operation": self.operation,
            "scope": self.scope,
            "ecosystems": list(self.ecosystems),
            "files": [{"src": s, "dst": d} for s, d in self.files],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Snapshot:
        files_raw = d.get("files", [])
        files = tuple(
            (f["src"], f["dst"]) if isinstance(f, dict) else (f[0], f[1])
            for f in files_raw
        )
        return cls(
            id=d["id"],
            ts=d.get("ts", 0.0),
            operation=d.get("operation", ""),
            scope=d.get("scope", ""),
            ecosystems=tuple(d.get("ecosystems", ())),
            files=files,
        )
