# M2 Foundation Plan — Infrastructure & Patterns

> Status: DESIGN v1 — iterating
> Parent: [milestone-2-dependency-intelligence.md](milestone-2-dependency-intelligence.md)
> Last updated: 2026-03-16

---

## Why a foundation plan

The M2 design doc describes **what** the system does. This plan describes
**how** it's built — the patterns, primitives, and infrastructure that
every feature in E1/E10 sits on top of.

Without this foundation, we repeat the mistakes of `tool_install` (11K lines,
tangled concerns, switch statements everywhere). With it, adding a new ecosystem
is one file, not twenty.

---

## Existing patterns we align with

| Pattern | Where it exists | How we use it |
|---------|-----------------|---------------|
| **Adapter protocol** | `src/adapters/base.py` (86 lines) | Our EcosystemAdapter follows the same shape: name, is_available, validate/detect, execute |
| **Registry dispatch** | `src/adapters/registry.py` (215 lines) | Our EcosystemRegistry follows the same pattern: register, get, list, status |
| **Streaming subprocess** | `tool_install/execution/subprocess_runner.py:128` | We extract a reusable version: same Popen + line-by-line + done sentinel |
| **Generator-based streaming** | `docker/containers.py:docker_action_stream()` | Our pipeline is a generator that yields typed events — transport-agnostic |
| **Event model** | `events/models.py` (77 lines) | All operations emit `Event` records via `emit_event()` |
| **State directory** | `.state/` (events/, mediator_index/, etc.) | Snapshots and notes go in `.state/dependency_*` |
| **Mediator nodes** | `mediator/registrations/*.py` | New `dependency.*` nodes with depends_on + TTL |
| **Two-phase data** | `packages_svc/ops.py` (detection fast) vs `actions.py` (operations slow) | Scanner phase 1 (detect manifests) vs phase 2 (parse contents) |

---

## What we do NOT reuse

| Component | Why not |
|-----------|---------|
| `packages_svc/actions.py` execution | Uses `subprocess.run` (blocking, no streaming). We need `Popen` streaming. We import detection from `ops.py`, but operations are new. |
| `tool_install/orchestration/stream.py` | Tied to plan steps, plan state, restart detection. Too coupled. We take the **pattern** (generator + event dicts) but not the code. |
| `src/adapters/base.py` directly | It's for action execution (Adapter → Receipt). Our adapters serve a different role (ecosystem knowledge). We follow the **shape** but define our own protocol. |

---

## Architecture overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Chunk 2: Assembly Layer                    │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────┐ │
│  │   Scanner     │  │ Tree Builder │  │ Operation Pipeline│ │
│  │ (2-phase)     │  │ (scope model)│  │ (generator)       │ │
│  └──────┬───────┘  └──────┬───────┘  └──────┬────────────┘ │
│         │                  │                  │              │
│         │    uses          │   uses           │   uses       │
│         ▼                  ▼                  ▼              │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │                 Chunk 1: Core Primitives                 │ │
│  │                                                          │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐ │ │
│  │  │ Ecosystem    │  │  Streaming   │  │  Output       │ │ │
│  │  │ Adapter      │  │  Subprocess  │  │  Parser       │ │ │
│  │  │ Protocol +   │  │  (reusable)  │  │  Protocol +   │ │ │
│  │  │ Registry     │  │              │  │  Base         │ │ │
│  │  └──────────────┘  └──────────────┘  └───────────────┘ │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐ │ │
│  │  │ Data Models  │  │  State Layer │  │  Operation    │ │ │
│  │  │ (frozen DCs) │  │  (.state/)   │  │  Event Types  │ │ │
│  │  └──────────────┘  └──────────────┘  └───────────────┘ │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

---

# Chunk 1 — Core Primitives

Everything in Chunk 2 depends on Chunk 1. Nothing in Chunk 1 depends on
Chunk 2. These are the building blocks.

---

## 1A. Data Models

**File:** `src/core/services/dependency_mgr/models.py`

All frozen dataclasses (same convention as `events/models.py`). Immutable
records that flow through the system. Serializable to JSON.

```python
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Literal

# ── Scanner output ────────────────────────────────────────────

@dataclass(frozen=True)
class ManifestInfo:
    """Phase 1 output — lightweight, no file I/O beyond stat()."""
    ecosystem: str             # "pip", "npm", "go", "cargo", ...
    manifest_file: str         # "requirements.txt", "package.json"
    manifest_path: str         # Relative dir: ".", "frontend/", "workers/"
    lock_file: str | None      # "package-lock.json" if exists, else None
    cli: str                   # "pip", "npm", "go", "cargo"
    cli_available: bool        # shutil.which() check
    mtime: float               # manifest file mtime (cache invalidation key)


@dataclass(frozen=True)
class DeclaredDep:
    """Phase 2 output — one parsed dependency from a manifest."""
    name: str                  # "requests", "react", "serde"
    version_spec: str          # "==2.31.0", "^18.2.0", "~5.3", ""
    pinned_version: str        # Resolved from lock or spec: "2.31.0"
    group: str                 # "main", "dev", "optional", "build", "peer"
    source_file: str           # "requirements.txt"
    source_path: str           # "." or "frontend/"


@dataclass(frozen=True)
class ParsedManifest:
    """Phase 2 output — a fully parsed manifest with its dependencies."""
    info: ManifestInfo
    dependencies: tuple[DeclaredDep, ...]    # frozen → tuple not list
    dev_dependencies: tuple[DeclaredDep, ...]
    total: int


# ── Tree model ────────────────────────────────────────────────

@dataclass
class TreeNode:
    """Mutable — built by the tree builder, serialized for the frontend."""
    id: str                    # "global", "pip:.", "pip:workers", "npm:frontend:react"
    label: str                 # "Global", "Python (.)", "react 18.2.0"
    level: Literal["global", "ecosystem", "package"]
    ecosystem: str | None      # "pip", "npm", etc.
    path: str | None           # Relative dir
    children: list[TreeNode] = field(default_factory=list)
    # Package-level (None for global/ecosystem nodes)
    version: str | None = None
    latest_version: str | None = None
    status: str | None = None  # "current", "outdated", "deprecated", "eol", "yanked", "unknown"
    group: str | None = None   # "main", "dev", etc.
    note: str | None = None    # User annotation text

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id,
            "label": self.label,
            "level": self.level,
        }
        if self.ecosystem: d["ecosystem"] = self.ecosystem
        if self.path is not None: d["path"] = self.path
        if self.children: d["children"] = [c.to_dict() for c in self.children]
        if self.version: d["version"] = self.version
        if self.latest_version: d["latestVersion"] = self.latest_version
        if self.status: d["status"] = self.status
        if self.group: d["group"] = self.group
        if self.note: d["note"] = self.note
        return d


# ── Operation events (yielded by pipeline generator) ─────────

@dataclass(frozen=True)
class OpEvent:
    """Single event in the operation pipeline stream.

    Transport-agnostic. The SSE route serializes these to JSON.
    The CLI prints them. Tests collect them.
    """
    type: str                  # See _OP_EVENT_TYPES below
    ts: float                  # time.time()
    scope: str = ""            # TreeNode.id that this event belongs to
    # Content fields (optional depending on type)
    line: str = ""             # Raw output line (for "log")
    package: str = ""          # Package name (for "package_resolved", "warning", "error")
    version: str = ""          # Version (for "package_resolved")
    action: str = ""           # "installed", "updated", "removed" (for "package_resolved")
    category: str = ""         # "deprecated", "conflict", "missing_dep" (for "warning"/"error")
    message: str = ""          # Human-readable (for "warning", "error", "done")
    severity: str = "info"     # "info", "warning", "error"
    status: str = ""           # "ok", "error" (for "done")
    command: str = ""          # The command being run (for "start")
    count: int = 0             # Packages resolved (for "done")
    duration_ms: int = 0       # Elapsed (for "done")
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize — omits empty fields for clean JSON."""
        d: dict[str, Any] = {"type": self.type, "ts": self.ts}
        for k in ("scope", "line", "package", "version", "action",
                   "category", "message", "severity", "status",
                   "command", "count", "duration_ms"):
            v = getattr(self, k)
            if v: d[k] = v
        if self.detail: d["detail"] = self.detail
        return d


# Event types the pipeline yields
_OP_EVENT_TYPES = {
    # Batch envelope (Global scope)
    "batch_start",             # Starting multi-ecosystem operation
    "batch_done",              # All ecosystems finished
    # Per-ecosystem
    "snapshot_created",        # Lock files backed up
    "operation_start",         # Command about to run
    "log",                     # Raw output line
    "package_resolved",        # Parsed: package X installed/updated
    "warning",                 # Parsed: deprecation, conflict, etc.
    "error",                   # Parsed: failure, missing dep, etc.
    "progress",                # Parsed: N/M packages (if detectable)
    "operation_done",          # Command finished (ok or error)
    "rollback_start",          # Restoring snapshot
    "rollback_done",           # Snapshot restored
}


# ── Version intelligence ──────────────────────────────────────

@dataclass(frozen=True)
class VersionIntel:
    """Version health for one declared dependency."""
    package: str
    ecosystem: str
    installed: str             # Currently installed/declared version
    latest: str | None         # Latest available (None if unknown)
    status: Literal["current", "outdated", "deprecated", "eol", "yanked", "unknown"]
    eol_date: str | None       # ISO date if known
    successor: str | None      # Replacement package if deprecated
    breaking: bool             # True if latest is a major version bump
    detail: str                # Human-readable explanation


# ── Snapshot (rollback) ───────────────────────────────────────

@dataclass(frozen=True)
class Snapshot:
    """Record of a pre-operation state backup."""
    id: str                    # Timestamp-based: "2026-03-16T14-30-00"
    ts: float
    operation: str             # "install", "update", "rollback"
    scope: str                 # TreeNode.id
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
```

**Design decisions:**
- Frozen dataclasses for all data that flows through the system (immutability = thread safety)
- `TreeNode` is mutable because it's built incrementally by the tree builder
- `OpEvent` is the pipeline's output type — not the same as `Event` from the event store. `OpEvent` is streaming/granular. The pipeline emits `Event` records to the store at start/done boundaries only.
- `to_dict()` on everything — same pattern as `events/models.py`
- Tuples instead of lists on frozen dataclasses (hashable)

---

## 1B. Ecosystem Adapter Protocol + Registry

**File:** `src/core/services/dependency_mgr/ecosystem.py`

The EcosystemAdapter is the **single abstraction** that encapsulates all
ecosystem-specific knowledge. Everything that differs between pip and npm
lives behind this protocol. Nothing else in the system uses `if ecosystem == "pip"`.

### Protocol

```python
from __future__ import annotations
from typing import Protocol, Iterator, Literal
from pathlib import Path

class EcosystemAdapter(Protocol):
    """Everything the system needs to know about one package ecosystem.

    One class per ecosystem. All ecosystem-specific logic is here.
    The rest of the system talks to adapters through the registry,
    never through ecosystem-specific code.

    Contract:
    - Methods NEVER raise. Failures return empty results or False.
    - detect() and parse_manifest() are pure (no side effects).
    - Commands return argument lists, never execute them.
    """

    # ── Identity ──────────────────────────────────────────────

    @property
    def id(self) -> str:
        """Ecosystem identifier: 'pip', 'npm', 'go', 'cargo', etc."""
        ...

    @property
    def name(self) -> str:
        """Human label: 'Python (pip)', 'Node (npm)', etc."""
        ...

    @property
    def cli(self) -> str:
        """Primary CLI tool: 'pip', 'npm', 'go', 'cargo'."""
        ...

    # ── Detection (Phase 1 — fast, no file reads) ────────────

    def detect(self, directory: Path) -> list[ManifestInfo]:
        """Check if this ecosystem has manifests in the given directory.

        Fast: only checks file existence and stat(). No parsing.
        Returns empty list if ecosystem not present.
        """
        ...

    def is_available(self) -> bool:
        """Check if the CLI tool is installed and accessible."""
        ...

    # ── Parsing (Phase 2 — reads file contents) ──────────────

    def parse_manifest(self, manifest: Path, lock_file: Path | None) -> ParsedManifest:
        """Parse a manifest file into declared dependencies.

        Reads file contents. Uses lock file for pinned versions if available.
        Returns ParsedManifest with dependencies and dev_dependencies.
        """
        ...

    # ── Commands (return args, never execute) ─────────────────

    def install_cmd(self, directory: Path, *, dev: bool = False, frozen: bool = True) -> list[str]:
        """Command to install all dependencies in this directory.

        frozen=True → use lock file (npm ci, pip install -r).
        frozen=False → resolve fresh (npm install, pip install).
        dev=True → include dev dependencies.
        """
        ...

    def update_cmd(self, directory: Path, packages: list[str] | None = None) -> list[str]:
        """Command to update dependencies. None = update all."""
        ...

    def update_single_cmd(self, directory: Path, package: str, version: str | None = None) -> list[str]:
        """Command to update one specific package. version=None → latest."""
        ...

    # ── Rollback (which files to snapshot) ────────────────────

    def snapshot_files(self, directory: Path) -> list[Path]:
        """Files to backup before an operation (manifest + lock files).

        Returns absolute paths. Empty list if nothing to snapshot.
        """
        ...

    def restore_cmd(self, directory: Path) -> list[str]:
        """Command to run after restoring snapshot files.

        e.g., 'pip install -r requirements.txt' or 'npm ci'
        to sync installed packages with restored lock file.
        """
        ...

    # ── Output parsing ────────────────────────────────────────

    def create_output_parser(self) -> OutputParser:
        """Create a fresh output parser for this ecosystem.

        Each operation gets its own parser instance (stateful).
        """
        ...

    # ── Version intelligence ──────────────────────────────────

    def fetch_latest_version(self, package: str) -> str | None:
        """Query the ecosystem registry for the latest version.

        Network call. Returns None on failure. Caller handles caching.
        """
        ...

    def check_deprecated(self, package: str, version: str) -> tuple[bool, str]:
        """Check if a package version is deprecated/yanked.

        Returns (is_deprecated, detail_message).
        """
        ...
```

### Why this shape

| Method | Why it's on the adapter |
|--------|------------------------|
| `detect()` | File patterns differ: pip has 5 manifest types, npm has 1, dotnet uses glob patterns |
| `parse_manifest()` | Parsing logic is entirely different: TOML vs JSON vs line-based vs XML |
| `install_cmd()` / `update_cmd()` | Commands differ: `pip install -r` vs `npm ci` vs `go mod download` |
| `snapshot_files()` | Different files matter: pip needs requirements.txt, npm needs package-lock.json AND package.json |
| `create_output_parser()` | Output format is completely different across ecosystems |
| `fetch_latest_version()` | Registry APIs differ: PyPI JSON vs npm registry vs crates.io |

### Registry

```python
class EcosystemRegistry:
    """Central lookup for ecosystem adapters.

    Same pattern as src/adapters/registry.py but simpler —
    no circuit breakers, no mock mode, no execution dispatch.
    Just registration and lookup.
    """

    def __init__(self) -> None:
        self._adapters: dict[str, EcosystemAdapter] = {}

    def register(self, adapter: EcosystemAdapter) -> None:
        self._adapters[adapter.id] = adapter

    def get(self, ecosystem_id: str) -> EcosystemAdapter | None:
        return self._adapters.get(ecosystem_id)

    def all(self) -> list[EcosystemAdapter]:
        return list(self._adapters.values())

    def available(self) -> list[EcosystemAdapter]:
        return [a for a in self._adapters.values() if a.is_available()]

    def ids(self) -> list[str]:
        return list(self._adapters.keys())

    def status(self) -> dict[str, dict]:
        return {
            a.id: {"name": a.name, "cli": a.cli, "available": a.is_available()}
            for a in self._adapters.values()
        }
```

### Adapter registration (boot time)

```python
# src/core/services/dependency_mgr/__init__.py

_registry = EcosystemRegistry()

def _register_adapters() -> None:
    from .adapters.pip_adapter import PipAdapter
    from .adapters.npm_adapter import NpmAdapter
    from .adapters.go_adapter import GoAdapter
    from .adapters.cargo_adapter import CargoAdapter
    from .adapters.bundler_adapter import BundlerAdapter
    from .adapters.maven_adapter import MavenAdapter
    from .adapters.mix_adapter import MixAdapter
    from .adapters.generic_adapter import GenericAdapter  # fallback

    for cls in (PipAdapter, NpmAdapter, GoAdapter, CargoAdapter,
                BundlerAdapter, MavenAdapter, MixAdapter):
        _registry.register(cls())

_register_adapters()

def get_registry() -> EcosystemRegistry:
    return _registry
```

### Adapter file structure

```
src/core/services/dependency_mgr/adapters/
├── __init__.py
├── pip_adapter.py         # PipAdapter — Python
├── npm_adapter.py         # NpmAdapter — Node
├── go_adapter.py          # GoAdapter — Go modules
├── cargo_adapter.py       # CargoAdapter — Rust
├── bundler_adapter.py     # BundlerAdapter — Ruby
├── maven_adapter.py       # MavenAdapter — Java
├── mix_adapter.py         # MixAdapter — Elixir
└── generic_adapter.py     # GenericAdapter — fallback for unknown PMs
```

**Adding a new ecosystem = one new file + one line in `_register_adapters()`.**
Zero changes to scanner, pipeline, tree builder, or UI.

### Relationship to existing `packages_svc`

`packages_svc/ops.py` has `_PACKAGE_MANAGERS` and `_detect_pm_for_dir()`.
The adapters **replace** this data — each adapter knows its own manifest patterns.
We do NOT import from `packages_svc` for detection.

`packages_svc/actions.py` has individual operations (`_pip_outdated`, `_npm_list`).
These stay — they serve the existing packages card. The dependency manager's
executor runs **grouped** operations with streaming, which is different.

The two systems coexist. `packages_svc` = lightweight status checks.
`dependency_mgr` = scope-aware operations with full observability.

---

## 1C. Output Parser Protocol + Base

**File:** `src/core/services/dependency_mgr/parsers/base.py`

The output parser receives raw stdout/stderr lines during command execution
and emits structured `OpEvent`s. Each ecosystem has its own parser because
pip output looks nothing like npm output.

### Protocol

```python
class OutputParser(Protocol):
    """Stateful parser for ecosystem command output.

    One instance per operation. Feed lines as they arrive.
    Call finalize() when the subprocess exits.

    The parser accumulates state (e.g., counting resolved packages)
    and emits events as it recognizes patterns.
    """

    def feed_line(self, line: str, stream: Literal["stdout", "stderr"] = "stdout") -> list[OpEvent]:
        """Process one output line. Return zero or more parsed events.

        Most lines produce nothing (raw log). Pattern matches produce
        package_resolved, warning, error, or progress events.
        """
        ...

    def finalize(self, exit_code: int) -> list[OpEvent]:
        """Called after subprocess exits. Emit final summary events.

        Use this for parsers that accumulate state (e.g., npm reports
        total added count only at the end).
        """
        ...

    @property
    def resolved_count(self) -> int:
        """Number of packages resolved so far (for progress tracking)."""
        ...

    @property
    def warnings(self) -> list[OpEvent]:
        """All warning events emitted so far."""
        ...

    @property
    def errors(self) -> list[OpEvent]:
        """All error events emitted so far."""
        ...
```

### Base implementation

```python
class BaseOutputParser:
    """Shared logic for all ecosystem parsers.

    Subclasses override:
    - _match_line() → ecosystem-specific pattern matching
    - _finalize() → ecosystem-specific summary

    Base class handles:
    - Event construction with timestamps
    - Warning/error accumulation
    - Resolved count tracking
    - Generic fallback patterns (ERROR, WARNING, FAIL in any output)
    """

    def __init__(self, scope: str, ecosystem: str):
        self._scope = scope
        self._ecosystem = ecosystem
        self._resolved: list[OpEvent] = []
        self._warnings: list[OpEvent] = []
        self._errors: list[OpEvent] = []

    def feed_line(self, line: str, stream: str = "stdout") -> list[OpEvent]:
        events = self._match_line(line, stream)
        if not events:
            events = self._match_generic(line, stream)
        for ev in events:
            if ev.type == "package_resolved":
                self._resolved.append(ev)
            elif ev.type == "warning":
                self._warnings.append(ev)
            elif ev.type == "error":
                self._errors.append(ev)
        return events

    def _match_line(self, line: str, stream: str) -> list[OpEvent]:
        """Override in subclass. Return empty list for unrecognized lines."""
        return []

    def _match_generic(self, line: str, stream: str) -> list[OpEvent]:
        """Fallback: detect ERROR/WARNING/FAIL patterns in any output."""
        upper = line.upper()
        if stream == "stderr" or "ERROR" in upper or "FATAL" in upper:
            if any(kw in upper for kw in ("ERROR", "FATAL", "FAILED", "EXCEPTION")):
                return [OpEvent(type="error", ts=time.time(), scope=self._scope,
                                message=line.strip(), severity="error")]
        if "WARNING" in upper or "WARN " in upper or "DEPRECATED" in upper:
            return [OpEvent(type="warning", ts=time.time(), scope=self._scope,
                            message=line.strip(), severity="warning")]
        return []

    @property
    def resolved_count(self) -> int:
        return len(self._resolved)

    @property
    def warnings(self) -> list[OpEvent]:
        return list(self._warnings)

    @property
    def errors(self) -> list[OpEvent]:
        return list(self._errors)
```

### What each ecosystem parser detects

| Parser | Resolved pattern | Warning patterns | Error patterns |
|--------|-----------------|------------------|----------------|
| **PipParser** | `Successfully installed X-1.2.3`, `Requirement already satisfied: X` | `DEPRECATION:`, `WARNING:`, `X is yanked` | `ERROR:`, `No matching distribution`, `subprocess-exited-with-error` |
| **NpmParser** | `added N packages` (summary), individual lines from `--verbose` | `npm WARN deprecated`, `npm WARN peer dep`, `npm WARN optional` | `npm ERR!`, `ERESOLVE`, `ENOENT` |
| **GoParser** | `go: downloading X v1.2.3` | `go: module X: retracted` | `go: X: not found`, checksum mismatch |
| **CargoParser** | `Compiling X v1.2.3`, `Downloaded X v1.2.3` | `warning:` lines | `error[E...]`, `could not compile` |
| **GenericParser** | None (uses base fallback) | `WARNING`, `WARN `, `DEPRECATED` | `ERROR`, `FATAL`, `FAILED` |

### Parser file structure

```
src/core/services/dependency_mgr/parsers/
├── __init__.py
├── base.py               # OutputParser protocol + BaseOutputParser
├── pip_parser.py          # PipParser
├── npm_parser.py          # NpmParser
├── go_parser.py           # GoParser
├── cargo_parser.py        # CargoParser
└── generic_parser.py      # GenericParser (fallback)
```

---

## 1D. Streaming Subprocess (reusable)

**File:** `src/core/services/dependency_mgr/subprocess_stream.py`

The existing `_run_subprocess_streaming` in `tool_install` is good but tied
to that module (sudo handling, tool_install imports). We need a **clean,
reusable** version that the dependency pipeline uses.

### Design

```python
def stream_subprocess(
    cmd: list[str],
    *,
    cwd: Path | str | None = None,
    env: dict[str, str] | None = None,
    timeout: int = 300,
    merge_stderr: bool = True,
) -> Iterator[SubprocessChunk]:
    """Run a command and yield output line-by-line.

    Generator-based. No HTTP dependency. No Flask dependency.
    The pipeline wraps this; the SSE route wraps the pipeline.

    Args:
        cmd: Command to run.
        cwd: Working directory.
        env: Full environment dict (not overrides — caller merges).
        timeout: Process timeout in seconds.
        merge_stderr: If True, stderr merges into stdout stream.
            If False, stderr lines are yielded separately.

    Yields:
        SubprocessChunk — either a line or a done sentinel.
    """
```

**SubprocessChunk:**

```python
@dataclass(frozen=True)
class SubprocessChunk:
    """One unit of subprocess output."""
    type: Literal["line", "done"]
    line: str = ""                    # For type="line"
    stream: Literal["stdout", "stderr", "merged"] = "merged"
    # For type="done"
    ok: bool = True
    exit_code: int = 0
    elapsed_ms: int = 0
    error: str = ""                   # Timeout or exception message
```

**Why not reuse `_run_subprocess_streaming` from tool_install:**
1. It has sudo handling baked in (we don't need sudo for package operations)
2. It imports from `tool_install` (coupling)
3. It merges stderr unconditionally (we sometimes want separate streams for parser accuracy)
4. It yields dicts (we yield typed dataclasses)

**What we keep from its approach:**
- `Popen` with `bufsize=1` for line buffering
- Iterate `proc.stdout` for real-time lines
- `proc.wait(timeout=...)` with kill on timeout
- Elapsed time tracking via `time.monotonic()`

---

## 1E. State Layer

**File:** `src/core/services/dependency_mgr/state.py`

Manages persistent state in `.state/`. Three concerns:

### Snapshots

```python
SNAPSHOT_DIR = ".state/dependency_snapshots"
MAX_SNAPSHOTS = 10

def create_snapshot(project_root: Path, scope: str, ecosystems: list[str],
                    files: list[tuple[str, str]]) -> Snapshot:
    """Backup files before an operation.

    Creates a timestamped directory, copies files, writes manifest.json.
    Auto-prunes oldest snapshots beyond MAX_SNAPSHOTS.
    """

def restore_snapshot(project_root: Path, snapshot_id: str) -> Snapshot:
    """Restore files from a snapshot to their original locations."""

def list_snapshots(project_root: Path) -> list[Snapshot]:
    """List available snapshots, newest first."""

def prune_snapshots(project_root: Path) -> int:
    """Remove snapshots beyond MAX_SNAPSHOTS. Returns count removed."""
```

### Notes

```python
NOTES_FILE = ".state/dependency_notes.json"

def get_notes(project_root: Path) -> dict[str, dict]:
    """Load all notes. Key format: '{ecosystem}:{package}:{version}'."""

def set_note(project_root: Path, ecosystem: str, package: str,
             version: str, note: str, dismiss_until: str | None = None) -> None:
    """Add or update a note. Emits timeline event."""

def remove_note(project_root: Path, ecosystem: str, package: str, version: str) -> bool:
    """Remove a note. Returns True if existed. Emits timeline event."""

def get_active_notes(project_root: Path) -> dict[str, dict]:
    """Notes that haven't expired (dismiss_until not passed)."""
```

### Atomic writes

Same pattern as `mediator/persistence.py` — write to tmp file, then rename:

```python
def _atomic_write_json(path: Path, data: Any) -> None:
    """Write JSON atomically (tmp + rename). Never corrupts on crash."""
```

---

## 1F. Operation Event Types

**File:** additions to `src/core/services/events/tracked.py`

New entries in `_EVENT_LABELS`:

```python
# Dependency operations
"dependency.scan.completed": "Dependency scan",
"dependency.install.started": "Dependency install",
"dependency.install.completed": "Dependencies installed",
"dependency.install.failed": "Dependency install failed",
"dependency.update.started": "Dependency update",
"dependency.update.completed": "Dependencies updated",
"dependency.update.failed": "Dependency update failed",
"dependency.rollback.started": "Dependency rollback",
"dependency.rollback.completed": "Dependencies rolled back",
"dependency.rollback.failed": "Dependency rollback failed",
"dependency.note.added": "Dependency note added",
"dependency.note.removed": "Dependency note removed",
```

---

# Chunk 2 — Assembly Layer

Uses Chunk 1 primitives to build the functional pipelines.

---

## 2A. Two-Phase Scanner

**File:** `src/core/services/dependency_mgr/scanner.py`

The scanner is the entry point for building the dependency tree.
Two phases because detection is fast and parsing is slow.

### Phase 1 — Detection (fast, no file reads)

```python
def detect_manifests(project_root: Path, modules: list[dict]) -> list[ManifestInfo]:
    """Scan project for dependency manifests.

    Walks each module directory + project root.
    Calls adapter.detect() for each registered ecosystem.
    Returns lightweight ManifestInfo objects (no file parsing).

    Fast: ~5ms for a typical project. Cacheable by directory mtime.
    """
    registry = get_registry()
    manifests: list[ManifestInfo] = []

    # Directories to scan: project root + each module path
    dirs = {Path(".")}  # Always scan root
    for mod in modules:
        p = mod.get("path", "")
        if p and p != ".":
            dirs.add(Path(p))

    for rel_dir in sorted(dirs):
        abs_dir = project_root / rel_dir
        if not abs_dir.is_dir():
            continue
        for adapter in registry.all():
            found = adapter.detect(abs_dir)
            for info in found:
                # Adjust path to be relative to project root
                manifests.append(ManifestInfo(
                    ecosystem=info.ecosystem,
                    manifest_file=info.manifest_file,
                    manifest_path=str(rel_dir),
                    lock_file=info.lock_file,
                    cli=info.cli,
                    cli_available=info.cli_available,
                    mtime=info.mtime,
                ))

    return manifests
```

### Phase 2 — Parsing (lazy, reads file contents)

```python
def parse_manifests(project_root: Path, manifests: list[ManifestInfo]) -> list[ParsedManifest]:
    """Parse manifest files to extract declared dependencies.

    Calls adapter.parse_manifest() for each detected manifest.
    Slower than detection: reads and parses file contents.

    Can be called selectively (e.g., only parse expanded ecosystems
    in the UI, not all at once).
    """
    registry = get_registry()
    parsed: list[ParsedManifest] = []

    for info in manifests:
        adapter = registry.get(info.ecosystem)
        if not adapter:
            continue
        manifest_path = project_root / info.manifest_path / info.manifest_file
        lock_path = (project_root / info.manifest_path / info.lock_file) if info.lock_file else None
        result = adapter.parse_manifest(manifest_path, lock_path)
        parsed.append(result)

    return parsed
```

### Cache invalidation

Phase 1 result cached in mediator (`dependency.manifests`, TTL 5min).
Phase 2 result cached per-manifest by `(ecosystem, path, mtime)` key.
If manifest mtime changes → phase 2 cache invalidated for that manifest only.

---

## 2B. Tree Builder

**File:** `src/core/services/dependency_mgr/tree.py`

Constructs the `TreeNode` hierarchy from scanner output.

```python
def build_tree(
    manifests: list[ManifestInfo],
    parsed: list[ParsedManifest] | None = None,
    notes: dict[str, dict] | None = None,
    version_intel: dict[str, VersionIntel] | None = None,
) -> TreeNode:
    """Build the scope tree from scanner output.

    Args:
        manifests: Phase 1 output (always present)
        parsed: Phase 2 output (optional — tree works without it,
                 just no package-level children)
        notes: User annotations (optional)
        version_intel: Version health data (optional)

    Returns:
        Root TreeNode (level="global") with ecosystem and package children.
    """
```

**Tree construction logic:**

1. Create root node `TreeNode(id="global", level="global", label="Global")`
2. Group manifests by `(ecosystem, path)` → each group = one ecosystem node
3. For each group:
   - `TreeNode(id=f"{ecosystem}:{path}", level="ecosystem", label=f"{adapter.name} ({path})")`
   - If `parsed` available → add package children
   - If `version_intel` available → set `status`, `latest_version` on package nodes
   - If `notes` available → set `note` on package nodes
4. Return root

**Key property:** The tree is buildable incrementally. Phase 1 only → tree has
ecosystem nodes but no package children. Phase 2 adds package children.
Version intel adds status badges. Notes add annotations. Each enrichment
is additive — no full rebuild needed.

### Ecosystem node ID convention

```
"pip:."              → Python at project root
"pip:workers"        → Python in workers/
"npm:frontend"       → Node in frontend/
"go:services/api"    → Go in services/api/
```

### Package node ID convention

```
"pip:.:requests"     → requests in root Python
"npm:frontend:react" → react in frontend Node
```

---

## 2C. Operation Pipeline

**File:** `src/core/services/dependency_mgr/pipeline.py`

The core of E1. A **generator** that orchestrates the full operation lifecycle:

```
Snapshot → Validate → Execute → Parse → Report
```

The pipeline yields `OpEvent`s. It doesn't know about HTTP, SSE, or Flask.
The route wraps it in SSE framing. Tests collect the events. CLI prints them.

### Single-ecosystem pipeline

```python
def run_operation(
    project_root: Path,
    scope: str,                           # TreeNode.id: "pip:.", "npm:frontend"
    action: Literal["install", "update", "rollback"],
    *,
    packages: list[str] | None = None,    # For update: specific packages
    dev: bool = False,
    frozen: bool = True,
    snapshot_id: str | None = None,       # For rollback: which snapshot
) -> Iterator[OpEvent]:
    """Execute a dependency operation and stream events.

    This is the ONLY place where dependency commands are executed.
    All routes, CLI, and automation call this function.

    Lifecycle:
    1. Resolve adapter from scope
    2. Snapshot (unless rollback)
    3. Build command via adapter
    4. Execute via stream_subprocess()
    5. Parse output via adapter's parser
    6. Yield events throughout
    7. Emit timeline event at boundaries

    Yields:
        OpEvent — typed, transport-agnostic events.
    """
```

**Pipeline stages (pseudocode):**

```python
def run_operation(...) -> Iterator[OpEvent]:
    # 1. Resolve
    ecosystem_id, path = _parse_scope(scope)  # "pip:." → ("pip", ".")
    adapter = get_registry().get(ecosystem_id)
    if not adapter:
        yield OpEvent(type="error", message=f"Unknown ecosystem: {ecosystem_id}")
        return
    if not adapter.is_available():
        yield OpEvent(type="error", message=f"{adapter.cli} not available")
        return

    directory = project_root / path
    t0 = time.monotonic()

    # 2. Snapshot (before install/update, not rollback)
    if action != "rollback":
        files_to_snap = adapter.snapshot_files(directory)
        if files_to_snap:
            snapshot = create_snapshot(project_root, scope, [ecosystem_id], ...)
            yield OpEvent(type="snapshot_created", scope=scope, message=f"Backed up {len(files_to_snap)} files")

    # 3. Build command
    if action == "install":
        cmd = adapter.install_cmd(directory, dev=dev, frozen=frozen)
    elif action == "update":
        if packages and len(packages) == 1:
            cmd = adapter.update_single_cmd(directory, packages[0])
        else:
            cmd = adapter.update_cmd(directory, packages)
    elif action == "rollback":
        restore_snapshot(project_root, snapshot_id)
        cmd = adapter.restore_cmd(directory)
        yield OpEvent(type="rollback_start", scope=scope)

    yield OpEvent(type="operation_start", scope=scope, command=" ".join(cmd))

    # 4. Execute + parse
    parser = adapter.create_output_parser()
    for chunk in stream_subprocess(cmd, cwd=directory, timeout=300):
        if chunk.type == "line":
            # Always yield raw log
            yield OpEvent(type="log", scope=scope, line=chunk.line)
            # Parse for structured events
            for parsed_event in parser.feed_line(chunk.line, chunk.stream):
                yield parsed_event
        elif chunk.type == "done":
            # Finalize parser
            for final_event in parser.finalize(chunk.exit_code):
                yield final_event
            # Summary
            elapsed = int((time.monotonic() - t0) * 1000)
            status = "ok" if chunk.ok else "error"
            yield OpEvent(
                type="operation_done" if action != "rollback" else "rollback_done",
                scope=scope,
                status=status,
                count=parser.resolved_count,
                duration_ms=elapsed,
                message=f"{parser.resolved_count} packages {'installed' if action == 'install' else 'updated'}" if chunk.ok else chunk.error,
                detail={"warnings": len(parser.warnings), "errors": len(parser.errors)},
            )
            # Emit timeline event
            _emit_timeline_event(action, scope, status, elapsed, parser)
```

### Batch pipeline (Global scope)

```python
def run_batch_operation(
    project_root: Path,
    scopes: list[str],                    # ["pip:.", "npm:frontend", "go:api"]
    action: Literal["install", "update"],
    **kwargs,
) -> Iterator[OpEvent]:
    """Run an operation across multiple ecosystems sequentially.

    Wraps individual run_operation() calls in batch_start/batch_done.
    """
    yield OpEvent(type="batch_start", detail={"ecosystems": scopes})
    t0 = time.monotonic()
    total_resolved = 0
    total_warnings = 0
    total_errors = 0
    failed = []

    for scope in scopes:
        for event in run_operation(project_root, scope, action, **kwargs):
            yield event
            if event.type == "operation_done":
                total_resolved += event.count
                total_warnings += event.detail.get("warnings", 0)
                total_errors += event.detail.get("errors", 0)
                if event.status == "error":
                    failed.append(scope)

    elapsed = int((time.monotonic() - t0) * 1000)
    yield OpEvent(
        type="batch_done",
        status="error" if failed else "ok",
        count=total_resolved,
        duration_ms=elapsed,
        detail={"warnings": total_warnings, "errors": total_errors, "failed": failed},
    )
```

### Why the pipeline is a generator

Three consumers, same pipeline:

```python
# 1. SSE route
@dep_bp.route("/dependencies/install/stream", methods=["POST"])
def dep_install_stream():
    body = request.get_json() or {}
    def sse():
        for event in run_operation(project_root, body["scope"], "install"):
            yield f"data: {json.dumps(event.to_dict())}\n\n"
    return Response(sse(), mimetype="text/event-stream")

# 2. Synchronous route (non-streaming, for simple cases)
@dep_bp.route("/dependencies/install", methods=["POST"])
def dep_install():
    events = list(run_operation(project_root, body["scope"], "install"))
    last = events[-1] if events else None
    return jsonify({"ok": last and last.status == "ok", "events": len(events)})

# 3. Future CLI or automation
for event in run_operation(root, "pip:.", "install"):
    if event.type == "log":
        print(event.line)
    elif event.type == "error":
        print(f"ERROR: {event.message}", file=sys.stderr)
```

---

## 2D. Mediator Nodes + Route Scaffolding

### Mediator registration

**File:** `src/core/services/mediator/registrations/dependencies.py`

```python
def register_dependency_nodes(mediator):
    """Register dependency-related mediator nodes.

    Called during mediator bootstrap (server.py).
    """
    # Phase 1: manifest detection (fast, depends on module list)
    mediator.register(
        "dependency.manifests",
        resolver=_resolve_manifests,
        depends_on=["index.scan"],
        ttl=300,         # 5 min
        weight=1,        # lightweight
    )

    # Phase 2: full tree with parsed deps (heavier)
    mediator.register(
        "dependency.tree",
        resolver=_resolve_tree,
        depends_on=["dependency.manifests"],
        ttl=300,
        weight=2,
    )

    # Summary for dashboard card (derived from tree)
    mediator.register(
        "dependency.summary",
        resolver=_resolve_summary,
        depends_on=["dependency.tree"],
        ttl=300,
        weight=1,
    )

    # Rollback snapshots
    mediator.register(
        "dependency.snapshots",
        resolver=_resolve_snapshots,
        ttl=60,
        weight=1,
    )
```

**Resolvers:**

```python
def _resolve_manifests(mediator, path, context):
    """Resolve dependency.manifests — Phase 1 detection."""
    index_data = mediator.get("index.scan")
    modules = index_data["data"].get("modules", []) if index_data else []
    project_root = _get_project_root()
    manifests = detect_manifests(project_root, modules)
    return [m.__dict__ for m in manifests]  # Serializable for mediator cache

def _resolve_tree(mediator, path, context):
    """Resolve dependency.tree — full tree with parsed deps."""
    manifests_raw = mediator.get("dependency.manifests")["data"]
    manifests = [ManifestInfo(**m) for m in manifests_raw]
    project_root = _get_project_root()
    parsed = parse_manifests(project_root, manifests)
    notes = get_active_notes(project_root)
    tree = build_tree(manifests, parsed=parsed, notes=notes)
    return tree.to_dict()

def _resolve_summary(mediator, path, context):
    """Resolve dependency.summary — counts for dashboard card."""
    tree = mediator.get("dependency.tree")["data"]
    ecosystems = len(tree.get("children", []))
    total_pkgs = sum(len(eco.get("children", [])) for eco in tree.get("children", []))
    outdated = _count_by_status(tree, "outdated")
    deprecated = _count_by_status(tree, "deprecated")
    return {
        "ecosystems": ecosystems,
        "total_packages": total_pkgs,
        "outdated": outdated,
        "deprecated": deprecated,
    }
```

### Route scaffolding

**File:** `src/ui/web/routes/dependencies/__init__.py`

```python
from flask import Blueprint
dep_bp = Blueprint("dependencies", __name__)

from . import api  # noqa: E402, F401
```

**File:** `src/ui/web/routes/dependencies/api.py`

```python
# Read endpoints (mediator-backed)
GET  /api/dependencies/tree           → mediator.get("dependency.tree")
GET  /api/dependencies/summary        → mediator.get("dependency.summary")
GET  /api/dependencies/snapshots      → mediator.get("dependency.snapshots")

# Write endpoints (pipeline-backed, SSE streaming)
POST /api/dependencies/install/stream  → SSE wrapper around run_operation(action="install")
POST /api/dependencies/update/stream   → SSE wrapper around run_operation(action="update")
POST /api/dependencies/rollback/stream → SSE wrapper around run_operation(action="rollback")

# Non-streaming write endpoints (for simple/programmatic use)
POST /api/dependencies/install         → collect run_operation(), return summary
POST /api/dependencies/update          → collect run_operation(), return summary
POST /api/dependencies/rollback        → collect run_operation(), return summary

# Notes
POST   /api/dependencies/note          → set_note()
DELETE /api/dependencies/note          → remove_note()
```

All write endpoints decorated with `@tracked("dependency.{action}.started")`.
Completion events emitted inside the pipeline via `emit_event()`.

### Blueprint registration

In `server.py`, alongside existing blueprints:

```python
from src.ui.web.routes.dependencies import dep_bp
app.register_blueprint(dep_bp, url_prefix="/api")
```

---

## 2E. Live Execution View (SSE Client)

**File:** `src/ui/web/templates/scripts/dependencies/_dep_stream.html`

This is the **frontend SSE consumer** — the live terminal component in the
dependency modal that renders streaming operation output. Without this, the
pipeline produces events that nobody sees.

### Streaming pattern

The project uses **fetch + ReadableStream** for operation streaming
(not EventSource — that's for the global push bus). Same pattern as
`_pages_sse.html`, `_artifacts_sse.html`, `_scripts_run.html`.

```javascript
function depRunOperation(scope, action, opts) {
    // ── 1. UI setup ──────────────────────────────────────────
    const termEl = document.getElementById('dep-terminal');
    const statusEl = document.getElementById('dep-op-status');
    const progressEl = document.getElementById('dep-op-progress');
    const abortCtrl = new AbortController();

    termEl.textContent = '';
    statusEl.innerHTML = '⏳ Starting…';
    _depSetRunning(true);

    // ── 2. Batched line rendering (prevents UI freeze) ───────
    //    Same pattern as _pages_sse.html _addStageLine()
    const _lineBuf = [];
    let _flushScheduled = false;

    function _bufferLine(line, cls) {
        _lineBuf.push({ line, cls });
        if (!_flushScheduled) {
            _flushScheduled = true;
            requestAnimationFrame(_flushLines);
        }
    }

    function _flushLines() {
        _flushScheduled = false;
        if (!_lineBuf.length) return;
        const frag = document.createDocumentFragment();
        for (const { line, cls } of _lineBuf) {
            const div = document.createElement('div');
            div.textContent = line;
            if (cls) div.className = cls;
            frag.appendChild(div);
        }
        _lineBuf.length = 0;
        termEl.appendChild(frag);
        termEl.scrollTop = termEl.scrollHeight;
    }

    // ── 3. Warning/error tracking ────────────────────────────
    let resolvedCount = 0;
    let warningCount = 0;
    let errorCount = 0;

    function _updateProgress() {
        let parts = [`${resolvedCount} resolved`];
        if (warningCount) parts.push(`${warningCount} ⚠`);
        if (errorCount) parts.push(`${errorCount} ✗`);
        progressEl.textContent = parts.join(' · ');
    }

    // ── 4. Fetch streaming ───────────────────────────────────
    const url = `/api/dependencies/${action}/stream`;
    fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scope, ...opts }),
        signal: abortCtrl.signal,
    })
    .then(response => {
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        function read() {
            reader.read().then(({ done, value }) => {
                if (done) {
                    _flushLines();
                    if (statusEl.textContent.includes('Starting'))
                        statusEl.innerHTML = '⚠ Stream ended unexpectedly';
                    _depSetRunning(false);
                    return;
                }

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop(); // keep incomplete line

                for (const raw of lines) {
                    if (!raw.startsWith('data: ')) continue;
                    let evt;
                    try { evt = JSON.parse(raw.slice(6)); } catch(e) { continue; }

                    _depHandleEvent(evt);
                }
                read();
            }).catch(err => {
                if (err.name === 'AbortError') {
                    statusEl.innerHTML = '⛔ Aborted';
                } else {
                    statusEl.innerHTML = `⚠ Stream error: ${err.message}`;
                }
                _depSetRunning(false);
            });
        }
        read();
    });

    // ── 5. Event dispatcher ──────────────────────────────────
    function _depHandleEvent(evt) {
        switch (evt.type) {
            case 'snapshot_created':
                _bufferLine(`📸 ${evt.message}`, 'dep-line-info');
                break;

            case 'operation_start':
                _bufferLine(`$ ${evt.command}`, 'dep-line-cmd');
                statusEl.innerHTML = `⏳ Running: ${evt.scope || scope}`;
                break;

            case 'log':
                _bufferLine(evt.line, '');
                break;

            case 'package_resolved':
                _bufferLine(`  ✓ ${evt.package} ${evt.version}`, 'dep-line-ok');
                resolvedCount++;
                _updateProgress();
                break;

            case 'warning':
                _bufferLine(`  ⚠ ${evt.message}`, 'dep-line-warn');
                warningCount++;
                _updateProgress();
                // Add to remediation queue (if category is actionable)
                if (evt.category) _depAddWarning(evt);
                break;

            case 'error':
                _bufferLine(`  ✗ ${evt.message}`, 'dep-line-error');
                errorCount++;
                _updateProgress();
                if (evt.category) _depAddError(evt);
                break;

            case 'progress':
                progressEl.textContent = evt.message;
                break;

            case 'operation_done':
            case 'rollback_done':
                _flushLines();
                const ok = evt.status === 'ok';
                const icon = ok ? '✅' : '❌';
                const dur = (evt.duration_ms / 1000).toFixed(1);
                statusEl.innerHTML = `${icon} ${evt.message} — ${dur}s`;
                _depSetRunning(false);
                // Refresh tree (operation may have changed versions)
                _depRefreshTree();
                break;

            case 'batch_start':
                statusEl.innerHTML = `⏳ Batch: ${evt.detail?.ecosystems?.length || '?'} ecosystems`;
                break;

            case 'batch_done':
                _flushLines();
                const bOk = evt.status === 'ok';
                const bDur = (evt.duration_ms / 1000).toFixed(1);
                statusEl.innerHTML = bOk
                    ? `✅ All done — ${evt.count} packages — ${bDur}s`
                    : `❌ Batch failed — ${evt.detail?.failed?.length || '?'} ecosystems`;
                _depSetRunning(false);
                _depRefreshTree();
                break;
        }
    }

    // Return abort function for the cancel button
    return () => abortCtrl.abort();
}
```

### Terminal styling

```css
/* In the modal CSS */
.dep-terminal {
    font-family: var(--font-mono);
    font-size: 0.78rem;
    line-height: 1.5;
    background: var(--bg-tertiary);
    border: 1px solid var(--border-subtle);
    border-radius: 6px;
    padding: 8px 12px;
    max-height: 320px;
    overflow-y: auto;
    white-space: pre-wrap;
    word-break: break-all;
}
.dep-line-cmd   { color: var(--text-muted); font-weight: 600; }
.dep-line-info  { color: var(--text-secondary); }
.dep-line-ok    { color: var(--success); }
.dep-line-warn  { color: var(--warning); background: rgba(255,170,0,0.06); }
.dep-line-error { color: var(--error); background: rgba(255,60,60,0.06); }
```

### Key design decisions

1. **fetch + ReadableStream, not EventSource** — POST body needed (scope, options).
   EventSource is GET-only. Same choice as pages/artifacts/scripts.

2. **Batched DOM rendering via requestAnimationFrame** — pip can produce hundreds
   of lines per second. Direct DOM writes per line would freeze the UI. Buffer
   lines, flush once per frame. Same pattern as `_pages_sse.html`.

3. **DocumentFragment for batch insert** — single reflow per flush, not per line.

4. **Parsed events rendered inline** — warnings/errors get colored background
   directly in the terminal flow. No separate panel during execution. The
   Version Intelligence panel shows aggregated warnings/errors AFTER completion.

5. **Abort support** — AbortController wired to the cancel button. Pipeline
   sees the connection drop and stops the subprocess.

6. **Tree refresh on completion** — after install/update, the tree data is
   stale. `_depRefreshTree()` re-fetches `dependency.tree` from the mediator
   to update version status badges.

### Integration with the modal

The modal's Operation Panel contains:
- Scope label (from tree selection)
- Action buttons (Install / Update / Rollback)
- `<div id="dep-terminal" class="dep-terminal"></div>` — the live output
- `<div id="dep-op-progress"></div>` — resolved/warning/error counters
- `<div id="dep-op-status"></div>` — current status line
- Cancel button (calls the abort function returned by `depRunOperation`)

When the user clicks an action button:
1. Button calls `depRunOperation(selectedScope, 'install', { dev: false, frozen: true })`
2. Returns an abort function stored for the cancel button
3. Terminal fills with live output
4. On completion, tree refreshes and status shows summary

---

## Implementation order (sub-chunks within each chunk)

### Chunk 1 — Core Primitives (build order)

| Step | File | Depends on | Deliverable |
|------|------|-----------|-------------|
| **1A** | `models.py` | Nothing | All data models: ManifestInfo, DeclaredDep, ParsedManifest, TreeNode, OpEvent, VersionIntel, Snapshot |
| **1B** | `ecosystem.py` | 1A (models) | EcosystemAdapter protocol + EcosystemRegistry + registration wiring |
| **1C** | `parsers/base.py` | 1A (OpEvent) | OutputParser protocol + BaseOutputParser with generic fallback |
| **1D** | `subprocess_stream.py` | 1A (SubprocessChunk) | Reusable streaming subprocess generator |
| **1E** | `state.py` | 1A (Snapshot) | Snapshot create/restore/list/prune + notes read/write + atomic JSON |
| **1F** | `tracked.py` additions | Nothing | Event labels for dependency.* types |

**After Chunk 1:** All primitives exist. Nothing is wired together yet.
You can write adapters, parsers, and test them in isolation.

### Chunk 2 — Assembly Layer (build order)

| Step | File | Depends on | Deliverable |
|------|------|-----------|-------------|
| **2A** | `scanner.py` | 1A, 1B | detect_manifests() + parse_manifests() two-phase scanner |
| **2B** | `tree.py` | 1A, 2A | build_tree() constructs TreeNode hierarchy from scanner output |
| **2C** | `pipeline.py` | 1A, 1B, 1C, 1D, 1E | run_operation() + run_batch_operation() generators |
| **2D** | `registrations/dependencies.py` + `routes/dependencies/` | 2A, 2B, 2C | Mediator nodes + route scaffolding + blueprint registration |
| **2E** | `templates/scripts/dependencies/_dep_stream.html` | 2D (routes) | SSE client: fetch streaming, batched rendering, live terminal, abort support |

**After Chunk 2:** The full pipeline works end-to-end. You can scan, build
a tree, run operations with streaming, see live output in the browser terminal,
and get timeline events. But only with the GenericAdapter — no ecosystem-specific
intelligence yet.

### After foundation — feature work

With Chunk 1 + Chunk 2 complete, feature work is **per-adapter**:

| Phase | Work | Files |
|-------|------|-------|
| **Adapters Phase 1** | PipAdapter + PipParser (most common ecosystem) | `adapters/pip_adapter.py`, `parsers/pip_parser.py` |
| **Adapters Phase 2** | NpmAdapter + NpmParser | `adapters/npm_adapter.py`, `parsers/npm_parser.py` |
| **Adapters Phase 3** | GoAdapter, CargoAdapter + parsers | 4 files |
| **Adapters Phase 4** | BundlerAdapter, MavenAdapter, MixAdapter + parsers | 6 files |
| **UI Phase 1** | Dashboard card update + basic modal with tree | `_dashboard.html`, `_dependencies_modal.html` |
| **UI Phase 2** | Operation panel + SSE terminal in modal | modal JS |
| **UI Phase 3** | Version intelligence panel + notes | modal JS |
| **E10** | Graph builder + impact analysis + visualization | `graph.py`, modal graph tab |

Each adapter is **one file implementing the protocol**. Each parser is
**one file extending BaseOutputParser**. No changes to pipeline, scanner,
tree builder, or routes when adding a new ecosystem.

---

## Files created by this foundation

```
src/core/services/dependency_mgr/
├── __init__.py                        # Registry boot + get_registry()
├── models.py                          # 1A: All data models
├── ecosystem.py                       # 1B: EcosystemAdapter protocol + registry
├── subprocess_stream.py               # 1D: Reusable streaming subprocess
├── state.py                           # 1E: Snapshots + notes + atomic writes
├── scanner.py                         # 2A: Two-phase scanner
├── tree.py                            # 2B: Tree builder
├── pipeline.py                        # 2C: Operation pipeline (generator)
├── parsers/
│   ├── __init__.py
│   ├── base.py                        # 1C: OutputParser protocol + base
│   └── generic_parser.py              # Fallback parser
├── adapters/
│   ├── __init__.py
│   └── generic_adapter.py             # Fallback adapter
└── README.md                          # Service documentation

src/core/services/mediator/registrations/
└── dependencies.py                    # 2D: Mediator node registration

src/ui/web/routes/dependencies/
├── __init__.py                        # 2D: Blueprint
└── api.py                             # 2D: Route scaffolding

src/ui/web/templates/scripts/dependencies/
└── _dep_stream.html                   # 2E: Live execution view (SSE client)

# Modified files
src/core/services/events/tracked.py    # 1F: Event labels
src/ui/web/server.py                   # 2D: Blueprint registration
```

Total new files: **16**
Total modified files: **2**
