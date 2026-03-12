# System Posture — Implementation Plan

> **Status**: Ready for execution
> **Created**: 2026-03-12
> **Design doc**: `.agent/plans/system-health-posture.md`
> **Approach**: Foundation → Infrastructure → Scanners → API → UI, one chunk at a time

---

## Existing Infrastructure (DO NOT REBUILD)

These modules already exist and MUST be reused:

| What | Location | Reuse How |
|------|----------|-----------|
| Tool version detection (35+ tools) | `src/core/services/tool_install/detection/tool_version.py` | Import `get_tool_version(tool)` and `VERSION_COMMANDS` |
| Kernel + hardware detection | `src/core/services/tool_install/detection/hardware.py` | Import `detect_kernel()`, `detect_hardware()` |
| Environment / sandbox detection | `src/core/services/tool_install/detection/environment.py` | Import `detect_sandbox()` |
| Project health probes (7 domains) | `src/ui/web/routes/metrics/health.py` | Call `/api/metrics/health` internally or import probe fns |
| Circuit breaker + retry health | `src/core/observability/health.py` | Import `check_system_health()` |
| Modal system | `src/ui/web/templates/scripts/globals/_modal.html` | Use `modalOpen()` |
| Card caching (mtime-based) | `src/core/services/devops/cache.py` | NOT reused for posture (wrong model) — separate TTL cache |

---

## Package Structure

```
src/core/services/system_posture/
├── __init__.py                    # Public API: scan_posture(), get_summary()
├── models.py                      # RankLevel, PostureItem, PillarResult, SystemPosture
├── ranking.py                     # Version comparison, EOL logic, rank computation
├── cache.py                       # TTL-based in-memory cache (separate from devops cache)
├── scanners/
│   ├── __init__.py
│   ├── platform.py                # OS distro, kernel, glibc, WSL, arch
│   └── toolchain.py               # Tool versions → rank using existing get_tool_version()
├── bridges/
│   ├── __init__.py
│   ├── project.py                 # Wraps existing /metrics/health probes
│   └── runtime.py                 # Wraps existing health.py + integration adapter status
├── data/
│   ├── os_lifecycle.json           # OS distro → version → EOL date
│   └── tool_lifecycle.json         # Tool → current version + min supported + EOL versions
└── README.md
```

**Why scanners/ and bridges/ are separate:**
- Scanners do NEW detection work (subprocess calls, OS parsing)
- Bridges wrap EXISTING systems (metrics health, circuit breakers)
- Different caching strategies: scanners are slow (parallel subprocess), bridges are fast (in-memory or already cached)

---

## Chunk 1: Foundation — Data Model + Ranking Engine

**Files created:**
- `src/core/services/system_posture/__init__.py`
- `src/core/services/system_posture/models.py`
- `src/core/services/system_posture/ranking.py`

### models.py

```python
"""Data model for system posture assessment."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class RankLevel(str, Enum):
    """Deprecation rank for a system component.

    Ordered from best to worst. The overall rank of a pillar
    or the entire system is the WORST rank among its items.
    """
    CURRENT    = "current"      # 🟢 Up to date, fully supported
    AGING      = "aging"        # 🔵 Supported but approaching EOL
    OUTDATED   = "outdated"     # 🟡 Past EOL < 1 year, likely still works
    DEPRECATED = "deprecated"   # 🟠 Past EOL > 1 year, expect breakage
    DANGEROUS  = "dangerous"    # 🔴 Known CVEs, critical risk
    UNKNOWN    = "unknown"      # ⚪ Cannot determine version/status
    NA         = "na"           # — Not applicable (not installed, not configured)

    @property
    def severity(self) -> int:
        """Numeric severity for comparison. Higher = worse."""
        return _SEVERITY[self]

    @property
    def emoji(self) -> str:
        return _EMOJI[self]

    @property
    def color_var(self) -> str:
        """CSS variable name for this rank's color."""
        return _COLOR_VAR[self]


_SEVERITY = {
    RankLevel.NA:         -1,
    RankLevel.UNKNOWN:     0,
    RankLevel.CURRENT:     1,
    RankLevel.AGING:       2,
    RankLevel.OUTDATED:    3,
    RankLevel.DEPRECATED:  4,
    RankLevel.DANGEROUS:   5,
}

_EMOJI = {
    RankLevel.CURRENT:    "🟢",
    RankLevel.AGING:      "🔵",
    RankLevel.OUTDATED:   "🟡",
    RankLevel.DEPRECATED: "🟠",
    RankLevel.DANGEROUS:  "🔴",
    RankLevel.UNKNOWN:    "⚪",
    RankLevel.NA:         "—",
}

_COLOR_VAR = {
    RankLevel.CURRENT:    "--success",
    RankLevel.AGING:      "--info",
    RankLevel.OUTDATED:   "--warning",
    RankLevel.DEPRECATED: "--warning-strong",
    RankLevel.DANGEROUS:  "--error",
    RankLevel.UNKNOWN:    "--text-muted",
    RankLevel.NA:         "--text-muted",
}


@dataclass
class PostureItem:
    """A single assessed component (e.g. "Ubuntu 22.04" or "kubectl 1.24")."""

    name: str                       # Display name: "Ubuntu", "kubectl"
    value: str                      # Detected value: "22.04", "1.24.0"
    rank: RankLevel                 # Computed rank
    detail: str = ""                # Human note: "EOL April 2027", "7 minor behind"
    current_version: str = ""       # Latest known version (tools only)
    eol_date: str = ""              # EOL date if known (YYYY-MM format)
    cves: list[str] = field(default_factory=list)  # Known CVEs

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "name": self.name,
            "value": self.value,
            "rank": self.rank.value,
            "detail": self.detail,
        }
        if self.current_version:
            d["current_version"] = self.current_version
        if self.eol_date:
            d["eol_date"] = self.eol_date
        if self.cves:
            d["cves"] = self.cves
        return d


@dataclass
class PillarResult:
    """Assessment result for one of the four pillars."""

    pillar: str                     # "platform", "toolchain", "project", "runtime"
    rank: RankLevel                 # Worst rank across items
    items: list[PostureItem] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pillar": self.pillar,
            "rank": self.rank.value,
            "items": [i.to_dict() for i in self.items],
            "warnings": self.warnings,
            "recommendations": self.recommendations,
        }


@dataclass
class SystemPosture:
    """Full system posture assessment across all pillars."""

    overall_rank: RankLevel = RankLevel.UNKNOWN
    overall_status: str = "unknown"  # healthy|attention|degraded|unhealthy
    timestamp: str = ""
    pillars: dict[str, PillarResult] = field(default_factory=dict)
    summary: str = ""
    scan_duration_ms: int = 0

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(UTC).isoformat()

    def recompute_overall(self) -> None:
        """Set overall_rank and overall_status from pillar ranks."""
        if not self.pillars:
            self.overall_rank = RankLevel.UNKNOWN
            self.overall_status = "unknown"
            return

        worst = max(
            (p.rank for p in self.pillars.values() if p.rank not in (RankLevel.NA, RankLevel.UNKNOWN)),
            key=lambda r: r.severity,
            default=RankLevel.UNKNOWN,
        )
        self.overall_rank = worst
        self.overall_status = _STATUS_MAP.get(worst, "unknown")

        # Build summary
        parts = []
        for p in self.pillars.values():
            if p.warnings:
                parts.append(f"{len(p.warnings)} {p.pillar} warning{'s' if len(p.warnings) != 1 else ''}")
        self.summary = " · ".join(parts) if parts else "All systems nominal"

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_rank": self.overall_rank.value,
            "overall_status": self.overall_status,
            "timestamp": self.timestamp,
            "summary": self.summary,
            "scan_duration_ms": self.scan_duration_ms,
            "pillars": {k: v.to_dict() for k, v in self.pillars.items()},
        }

    def to_summary_dict(self) -> dict[str, Any]:
        """Lightweight summary for the nav badge (no item details)."""
        return {
            "overall_rank": self.overall_rank.value,
            "overall_status": self.overall_status,
            "summary": self.summary,
            "timestamp": self.timestamp,
            "pillar_ranks": {k: v.rank.value for k, v in self.pillars.items()},
        }


_STATUS_MAP = {
    RankLevel.CURRENT:    "healthy",
    RankLevel.AGING:      "healthy",
    RankLevel.OUTDATED:   "attention",
    RankLevel.DEPRECATED: "degraded",
    RankLevel.DANGEROUS:  "unhealthy",
    RankLevel.UNKNOWN:    "unknown",
}
```

### ranking.py

```python
"""Ranking engine — computes deprecation rank from version/EOL data."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import RankLevel

_DATA_DIR = Path(__file__).parent / "data"


def load_os_lifecycle() -> dict[str, Any]:
    """Load OS lifecycle data from os_lifecycle.json."""
    path = _DATA_DIR / "os_lifecycle.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_tool_lifecycle() -> dict[str, Any]:
    """Load tool lifecycle data from tool_lifecycle.json."""
    path = _DATA_DIR / "tool_lifecycle.json"
    return json.loads(path.read_text(encoding="utf-8"))


def rank_by_eol(eol_str: str | None) -> RankLevel:
    """Compute rank from an EOL date string (YYYY-MM format).

    Thresholds:
        > now + 2 years:   Current
        > now + 6 months:  Aging
        > now:             Outdated (still supported but ending soon)
        > now - 1 year:    Deprecated (EOL within last year)
        <= now - 1 year:   Dangerous (EOL over a year ago)
    """
    if not eol_str:
        return RankLevel.UNKNOWN

    try:
        # Parse YYYY-MM to a date (first of that month)
        parts = eol_str.split("-")
        eol_date = datetime(int(parts[0]), int(parts[1]), 1, tzinfo=timezone.utc)
    except (ValueError, IndexError):
        return RankLevel.UNKNOWN

    now = datetime.now(timezone.utc)
    delta_months = (eol_date.year - now.year) * 12 + (eol_date.month - now.month)

    if delta_months > 24:
        return RankLevel.CURRENT
    elif delta_months > 6:
        return RankLevel.AGING
    elif delta_months > 0:
        return RankLevel.OUTDATED
    elif delta_months > -12:
        return RankLevel.DEPRECATED
    else:
        return RankLevel.DANGEROUS


def parse_semver(version_str: str) -> tuple[int, ...] | None:
    """Parse a version string into a tuple of integers.

    Handles: "1.31.4", "27.5.1", "3.13.1", "0.14.11"
    Returns None if unparseable.
    """
    m = re.match(r"(\d+)\.(\d+)(?:\.(\d+))?", version_str)
    if not m:
        return None
    parts = [int(m.group(1)), int(m.group(2))]
    if m.group(3) is not None:
        parts.append(int(m.group(3)))
    return tuple(parts)


def rank_tool_version(
    installed: str,
    lifecycle: dict[str, Any],
) -> tuple[RankLevel, str]:
    """Rank a tool's installed version against its lifecycle data.

    Args:
        installed: Installed version string (e.g. "1.24.0")
        lifecycle: Entry from tool_lifecycle.json for this tool

    Returns:
        (rank, detail_string)
    """
    current_str = lifecycle.get("current", "")
    min_supported_str = lifecycle.get("min_supported", "")
    eol_versions = lifecycle.get("eol_versions", {})

    installed_v = parse_semver(installed)
    current_v = parse_semver(current_str) if current_str else None

    if not installed_v:
        return RankLevel.UNKNOWN, f"Cannot parse version: {installed}"

    # Check if this exact version (major.minor) is in the EOL list
    major_minor = f"{installed_v[0]}.{installed_v[1]}"
    major_only = str(installed_v[0])
    eol_entry = eol_versions.get(installed) or eol_versions.get(major_minor) or eol_versions.get(major_only)

    if eol_entry:
        eol_date = eol_entry if isinstance(eol_entry, str) else eol_entry.get("eol", "")
        cves = eol_entry.get("cves", []) if isinstance(eol_entry, dict) else []
        if cves:
            return RankLevel.DANGEROUS, f"EOL {eol_date}, {len(cves)} known CVE(s)"
        rank = rank_by_eol(eol_date)
        if rank.severity >= RankLevel.DEPRECATED.severity:
            return rank, f"EOL since {eol_date}"
        return rank, f"EOL {eol_date}"

    # Compare against current version
    if current_v:
        if installed_v >= current_v:
            return RankLevel.CURRENT, "Up to date"

        # How far behind?
        scheme = lifecycle.get("version_scheme", "semver")

        if scheme == "semver_minor":
            # Only count minor version difference
            minor_diff = current_v[1] - installed_v[1]
            if installed_v[0] < current_v[0]:
                # Major version behind
                return RankLevel.DANGEROUS, f"Major version behind ({installed} → {current_str})"
            elif minor_diff <= 2:
                return RankLevel.AGING, f"{minor_diff} minor version(s) behind"
            elif minor_diff <= 4:
                return RankLevel.OUTDATED, f"{minor_diff} minor versions behind"
            else:
                return RankLevel.DEPRECATED, f"{minor_diff} minor versions behind"

        else:  # semver — check major, then minor
            if installed_v[0] < current_v[0]:
                major_diff = current_v[0] - installed_v[0]
                return RankLevel.DANGEROUS, f"{major_diff} major version(s) behind ({installed} → {current_str})"
            minor_diff = current_v[1] - installed_v[1]
            if minor_diff <= 2:
                return RankLevel.AGING, f"{minor_diff} minor version(s) behind"
            elif minor_diff <= 5:
                return RankLevel.OUTDATED, f"{minor_diff} minor versions behind"
            else:
                return RankLevel.DEPRECATED, f"{minor_diff} minor versions behind"

    # No current version to compare — check min_supported
    if min_supported_str:
        min_v = parse_semver(min_supported_str)
        if min_v and installed_v < min_v:
            return RankLevel.DEPRECATED, f"Below minimum supported ({min_supported_str})"

    return RankLevel.UNKNOWN, "No lifecycle data available"


def worst_rank(items: list) -> RankLevel:
    """Return the worst (highest severity) rank from a list of PostureItems."""
    ranks = [item.rank for item in items if item.rank not in (RankLevel.NA, RankLevel.UNKNOWN)]
    if not ranks:
        return RankLevel.UNKNOWN
    return max(ranks, key=lambda r: r.severity)
```

### __init__.py

```python
"""
System Posture — environment awareness and deprecation ranking.

Assesses four pillars:
  - Platform:  OS, kernel, glibc, WSL, architecture
  - Toolchain: Installed tool versions vs current/EOL
  - Project:   Code health score (bridges to /metrics/health)
  - Runtime:   Circuit breakers, retry queue, integration adapters

Public API:
    scan_posture()  → SystemPosture  (full scan, cached)
    get_summary()   → dict           (lightweight for nav badge)
"""
```

**Chunk 1 deliverable**: Pure data model + pure logic. No I/O, no subprocess calls. Fully unit-testable.

**Verification**: Import models, create instances, test ranking logic with known versions/dates.

---

## Chunk 2: Deprecation Databases

**Files created:**
- `src/core/services/system_posture/data/os_lifecycle.json`
- `src/core/services/system_posture/data/tool_lifecycle.json`

### os_lifecycle.json

Covers major distributions. Each entry has:
- `name`: Human-readable release name
- `type`: LTS / stable / rolling
- `eol`: End-of-life date (YYYY-MM)
- `kernel`: Default kernel version (informational)

**Distros to include:**
- Ubuntu: 16.04 through 24.04
- Debian: 10 through 12
- CentOS: 7, 8
- RHEL: 7 through 9
- Rocky Linux: 8, 9
- AlmaLinux: 8, 9
- Fedora: 38 through 41
- macOS: 10.15 (Catalina) through 15 (Sequoia)
- Arch: rolling (always Current)
- Alpine: 3.16 through 3.20

### tool_lifecycle.json

For each tool:
- `current`: Latest stable version
- `min_supported`: Minimum version that should work
- `version_scheme`: "semver" or "semver_minor"
- `eol_versions`: Map of version → EOL date (+ optional CVEs)
- `notes`: Human context for the AI/UI

**Tools to include (matches VERSION_COMMANDS in tool_version.py):**
docker, kubectl, helm, terraform, git, go, node, python, cargo, rustc,
minikube, k3s, k9s, argocd, ansible, hugo, trivy, gh, skaffold, kustomize,
containerd, podman, npm, pip, ruff, mypy, pytest

**Chunk 2 deliverable**: Two JSON files with accurate, researched data. No code changes needed.

**Verification**: `ranking.py` can load and parse both files. Spot-check 5 entries against official EOL pages.

---

## Chunk 3: TTL Cache

**Files created:**
- `src/core/services/system_posture/cache.py`

### Design

Simple in-memory TTL cache. NOT file-backed (posture is not project-specific the way devops cards are). Thread-safe.

```python
"""TTL-based in-memory cache for system posture data.

Unlike the devops card cache (mtime-based, file-backed), posture data
is system-level and changes rarely. Each pillar has its own TTL:

    Platform:   session (until server restart)
    Toolchain:  5 minutes (tool could be installed/updated)
    Project:    60 seconds (bridges to existing mtime-cached data)
    Runtime:    0 seconds (always fresh — in-memory state)
"""

import threading
import time
from typing import Any, Callable

_cache: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()

# TTLs in seconds
TTLS: dict[str, float] = {
    "platform":  float("inf"),   # Until restart
    "toolchain": 300,            # 5 minutes
    "project":   60,             # 1 minute (underlying data is mtime-cached)
    "runtime":   0,              # Always fresh
    "full":      60,             # Full posture assembly
    "summary":   30,             # Nav badge summary
}


def get_or_compute(
    key: str,
    compute_fn: Callable[[], Any],
    *,
    ttl: float | None = None,
    force: bool = False,
) -> Any:
    """Return cached value or compute and cache it.

    Thread-safe. If two threads request the same key simultaneously,
    one computes and the other waits.
    """
    if ttl is None:
        ttl = TTLS.get(key, 60)

    if ttl <= 0 and not force:
        # TTL 0 = always fresh
        return compute_fn()

    with _lock:
        entry = _cache.get(key)
        if entry and not force:
            age = time.time() - entry["computed_at"]
            if age < ttl:
                return entry["data"]

    # Compute outside lock (may be slow)
    data = compute_fn()

    with _lock:
        _cache[key] = {
            "data": data,
            "computed_at": time.time(),
        }

    return data


def invalidate(key: str | None = None) -> None:
    """Invalidate a specific key or all keys."""
    with _lock:
        if key:
            _cache.pop(key, None)
        else:
            _cache.clear()


def get_age(key: str) -> float | None:
    """Return age in seconds for a cached key, or None if not cached."""
    with _lock:
        entry = _cache.get(key)
        if entry:
            return time.time() - entry["computed_at"]
    return None
```

**Chunk 3 deliverable**: Working TTL cache. No external dependencies.

**Verification**: Unit test — store, retrieve, verify TTL expiry, verify `force` bypass.

---

## Chunk 4: Platform Scanner

**Files created:**
- `src/core/services/system_posture/scanners/__init__.py`
- `src/core/services/system_posture/scanners/platform.py`

### What it does

1. Detects OS distribution + version (parses `/etc/os-release`, `sw_vers`, etc.)
2. Looks up the detected OS in `os_lifecycle.json`
3. Computes rank from EOL date
4. Reuses `detect_kernel()` from existing hardware.py for kernel info
5. Detects glibc version (`ldd --version`)
6. Detects WSL version (if applicable)
7. Returns a `PillarResult` with all items ranked

### Key implementation detail

OS detection is the one NEW subprocess call. Everything else reuses existing detectors:

```python
def _detect_os() -> tuple[str, str, str]:
    """Detect OS distribution, version, and codename.

    Returns: (distro, version, codename)
    Examples: ("ubuntu", "22.04", "jammy"), ("macos", "14", "sonoma")
    """
    # Linux: parse /etc/os-release
    # macOS: sw_vers
    # WSL: also check wsl.exe --version
```

**Reuses from existing code:**
- `detect_kernel()` from `tool_install/detection/hardware.py`
- Platform detection from `platform` stdlib module

**Chunk 4 deliverable**: `scan_platform() → PillarResult`

**Verification**: Run on current system, verify OS/kernel/glibc are correctly detected and ranked.

---

## Chunk 5: Toolchain Scanner

**Files created:**
- `src/core/services/system_posture/scanners/toolchain.py`

### What it does

1. Gets list of all tools from `VERSION_COMMANDS` (existing) + `tool_lifecycle.json`
2. Runs `get_tool_version(tool)` for each (reuses existing detection)
3. Looks up lifecycle data from `tool_lifecycle.json`
4. Computes rank using `rank_tool_version()`
5. Runs all checks in parallel via `ThreadPoolExecutor`
6. Returns a `PillarResult` with all installed tools ranked

### Key implementation detail

```python
def scan_toolchain() -> PillarResult:
    """Scan all known tools and rank their versions."""
    lifecycle_db = load_tool_lifecycle()

    # Only scan tools that exist in VERSION_COMMANDS AND lifecycle DB
    tools_to_scan = [
        t for t in VERSION_COMMANDS
        if t in lifecycle_db
    ]

    # Parallel version detection
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {
            pool.submit(get_tool_version, tool): tool
            for tool in tools_to_scan
        }
        # ... collect results, rank each ...
```

**Reuses from existing code:**
- `get_tool_version(tool)` from `tool_install/detection/tool_version.py`
- `VERSION_COMMANDS` dict (35+ tools already configured)

**Chunk 5 deliverable**: `scan_toolchain() → PillarResult`

**Verification**: Run on current system. Verify detected tools are ranked. Check that uninstalled tools are skipped (N/A).

---

## Chunk 6: Project + Runtime Bridges

**Files created:**
- `src/core/services/system_posture/bridges/__init__.py`
- `src/core/services/system_posture/bridges/project.py`
- `src/core/services/system_posture/bridges/runtime.py`

### project.py

Wraps existing project health probes. Does NOT re-scan — reuses cached data.

```python
def bridge_project(project_root: Path) -> PillarResult:
    """Bridge existing /metrics/health data into posture format."""
    # Import the probe functions and run them
    # (they go through the existing devops card cache)
    # Map grade A-F → RankLevel
    # Map individual probe scores → PostureItems
```

### runtime.py

Wraps existing circuit breaker + retry queue health. Optionally checks integration adapter status.

```python
def bridge_runtime(project_root: Path) -> PillarResult:
    """Bridge runtime health into posture format."""
    # Import check_system_health() for CB + retry queue
    # Check integration adapter configuration status
    # (Phase 1: just check if configured, not if reachable)
```

**Integration adapter checks (Phase 1 — configuration only):**
- Email: check if SMTP settings exist in config
- Sentinel: check if sentinel URL is configured
- Git: check if git remote is configured
- GitHub: check if GH token exists

**NOT Phase 1:** Actually pinging SMTP, validating Twilio tokens, etc. That's a future enhancement.

**Chunk 6 deliverable**: `bridge_project() → PillarResult`, `bridge_runtime() → PillarResult`

**Verification**: Run on current system. Verify project grade is correctly mapped. Verify CB status is reported.

---

## Chunk 7: Posture Orchestrator

**Files modified:**
- `src/core/services/system_posture/__init__.py` (add public API)

### What it does

Orchestrates all 4 pillar scans, assembles `SystemPosture`, manages caching.

```python
def scan_posture(
    project_root: Path,
    *,
    force: bool = False,
) -> SystemPosture:
    """Run full system posture assessment.

    Uses TTL cache — returns instantly when data is fresh.
    When stale, runs platform + toolchain scanners in parallel
    (both are subprocess-heavy), then bridges project + runtime.

    Args:
        project_root: Project root for project/runtime bridges.
        force: Bypass cache and rescan everything.

    Returns:
        Full SystemPosture with all 4 pillars.
    """


def get_summary(project_root: Path) -> dict:
    """Lightweight summary for the nav badge.

    Returns from cache instantly. If cache is empty, triggers
    a background scan and returns a "scanning..." placeholder.
    """
```

### Parallel execution strategy

```
Thread pool:
  ├── Thread 1: scan_platform()     (~200ms)
  ├── Thread 2: scan_toolchain()    (~500ms, internally parallel)
  ├── Main:     bridge_project()    (~0ms if cached, reads card cache)
  └── Main:     bridge_runtime()    (~50ms, in-memory reads)

Total: ~500ms warm, dominated by toolchain subprocess calls
```

**Chunk 7 deliverable**: `scan_posture()` and `get_summary()` working end-to-end.

**Verification**: Call `scan_posture()` from Python REPL, print all 4 pillars. Verify caching (second call should be instant).

---

## Chunk 8: API Endpoints

**Files created:**
- `src/ui/web/routes/api/posture.py`

**Files modified:**
- `src/ui/web/server.py` (register blueprint)

### Endpoints

```python
@posture_bp.route("/api/posture")
def api_posture():
    """Full system posture assessment.

    Query params:
        refresh=1  — bypass cache and rescan

    Returns: SystemPosture.to_dict()
    """

@posture_bp.route("/api/posture/summary")
def api_posture_summary():
    """Lightweight summary for nav badge.

    Returns: SystemPosture.to_summary_dict()
    Always fast — returns from cache or placeholder.
    """
```

**Chunk 8 deliverable**: Two working API endpoints. Testable with curl.

**Verification**:
```bash
curl http://localhost:8000/api/posture/summary
curl http://localhost:8000/api/posture
curl http://localhost:8000/api/posture?refresh=1
```

---

## Chunk 9: Nav Badge (Live)

**Files modified:**
- `src/ui/web/templates/partials/_nav.html` (badge structure)
- `src/ui/web/templates/scripts/globals/_system_health.html` (NEW — badge update logic)

### What changes

1. Badge HTML stays similar but gets a click handler
2. On page load, fetch `GET /api/posture/summary`
3. Update badge dot color + text based on `overall_status`
4. On click → open System Health modal (Chunk 10)

### Badge update logic

```javascript
async function _updateHealthBadge() {
    try {
        const data = await api('/posture/summary');
        const badge = document.getElementById('health-badge');
        if (!badge) return;

        const dot = badge.querySelector('.status-dot');
        const label = badge.querySelector('span:last-child');

        // Map status to CSS class
        const classMap = {
            healthy: 'ok',
            attention: 'degraded',
            degraded: 'failed',
            unhealthy: 'failed',
        };
        badge.className = 'status-badge ' + (classMap[data.overall_status] || '');
        label.textContent = _statusLabel(data.overall_status);
    } catch (e) {
        console.warn('Health badge update failed:', e);
    }
}

// Call after page load (non-blocking)
setTimeout(_updateHealthBadge, 2000);
```

**Chunk 9 deliverable**: Badge shows real status. Clickable (opens modal in Chunk 10).

**Verification**: Load page, verify badge reflects actual system state. Resize to verify it works with responsive tab changes.

---

## Chunk 10: System Health Modal

**Files created/modified:**
- `src/ui/web/templates/scripts/globals/_system_health.html` (modal rendering)
- `src/ui/web/static/css/admin.css` (modal-specific styles)

### Modal layout

```
┌─────────────────────────────────────────────────────────────────┐
│  ✕  System Health                                               │
├─────────────────────────────────────────────────────────────────┤
│  Summary bar: overall status + 4 pillar pills + scan time       │
│                                                                 │
│  ┌─── 🖥️ Platform ──────────────────── 🟢 Current ────┐       │
│  │  OS / Kernel / glibc / WSL items with ranks          │       │
│  └──────────────────────────────────────────────────────┘       │
│                                                                 │
│  ┌─── 🔧 Toolchain ─────────────────── 🟡 Outdated ───┐       │
│  │  Tool list with installed vs current + ranks         │       │
│  │  Warnings and recommendations                        │       │
│  └──────────────────────────────────────────────────────┘       │
│                                                                 │
│  ┌─── 📦 Project ───────────────────── 🟢 Grade B ────┐       │
│  │  Score + probe breakdown                             │       │
│  │  Link to Audit tab                                   │       │
│  └──────────────────────────────────────────────────────┘       │
│                                                                 │
│  ┌─── ⚡ Runtime ───────────────────── 🟢 Healthy ────┐       │
│  │  Circuit breakers + retry queue + integrations       │       │
│  └──────────────────────────────────────────────────────┘       │
│                                                                 │
│                                        [ 🔄 Rescan ]    [ Close │]
└─────────────────────────────────────────────────────────────────┘
```

### Rendering approach

- Open modal with `modalOpen({ title: 'System Health', size: 'wide' })`
- Show skeleton/loading state immediately
- Fetch `GET /api/posture` (full data)
- Render 4 pillar cards with rank-colored headers
- Auto-expand the worst pillar
- Rescan button calls `GET /api/posture?refresh=1`

**Chunk 10 deliverable**: Full modal with all 4 pillars rendered. Rescan works.

**Verification**: Click badge → modal opens → shows real data → rescan updates data.

---

## Chunk 11: tool_install Integration

**Files modified:**
- `src/core/services/tool_install/execution/` (error formatting)

### What changes

When a tool install fails, the error message is enriched with posture context:

```python
# In error handler:
from src.core.services.system_posture.scanners.toolchain import get_tool_context
context = get_tool_context("terraform")
if context and context.rank.severity >= RankLevel.DEPRECATED.severity:
    error_msg += f"\n⚠️ Note: {context.detail}"
```

**Chunk 11 deliverable**: Richer error messages when tool installs fail on degraded systems.

---

## Chunk 12: README + Documentation

**Files created:**
- `src/core/services/system_posture/README.md`

Full README following the project's documentation standard.

---

## Execution Order & Dependencies

```
Chunk 1: models.py + ranking.py          (no deps)
  ↓
Chunk 2: os_lifecycle.json + tool_lifecycle.json  (no deps)
  ↓
Chunk 3: cache.py                         (no deps)
  ↓
Chunk 4: platform scanner                 (needs: Chunk 1, 2, existing hardware.py)
  ↓
Chunk 5: toolchain scanner               (needs: Chunk 1, 2, existing tool_version.py)
  ↓
Chunk 6: project + runtime bridges       (needs: Chunk 1, existing metrics + health)
  ↓
Chunk 7: orchestrator                     (needs: Chunk 3, 4, 5, 6)
  ↓
Chunk 8: API endpoints                    (needs: Chunk 7)
  ↓
Chunk 9: nav badge                        (needs: Chunk 8)
  ↓
Chunk 10: system health modal             (needs: Chunk 8, 9)
  ↓
Chunk 11: tool_install integration        (needs: Chunk 5)
  ↓
Chunk 12: README                          (needs: all above)
```

Chunks 4, 5, 6 can be done in parallel (independent scanners/bridges).
Chunks 9, 10 can potentially be merged if small enough.
Chunk 11 is independent of the UI work (9, 10).

---

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| Subprocess calls hang | All subprocess calls use `timeout=10`. Existing `get_tool_version()` already handles this. |
| Lifecycle data becomes stale | Static JSON files — user can update. Later: add a refresh command. |
| Slow page load from badge fetch | Badge fetch is async (`setTimeout`), never blocks rendering. Returns cached data or placeholder. |
| Thread contention with devops cache | Posture has its OWN cache (Chunk 3). No shared locks. |
| OS detection fails on exotic distro | Fallback to `platform.system()` + `platform.release()`. Rank = Unknown, not crash. |
| Modal too slow to open | Show skeleton immediately, load data async. |

---

## Testing Strategy

| Chunk | Test Type | What to Test |
|-------|-----------|-------------|
| 1 | Unit | RankLevel ordering, PostureItem serialization, SystemPosture.recompute_overall() |
| 1 | Unit | rank_by_eol() with dates in past/present/future |
| 1 | Unit | rank_tool_version() with various version gaps |
| 1 | Unit | parse_semver() with valid/invalid strings |
| 2 | Manual | Spot-check 5 OS entries, 5 tool entries against official sources |
| 3 | Unit | TTL cache: store/retrieve, expiry, force bypass, invalidation |
| 4 | Integration | scan_platform() returns valid PillarResult on current system |
| 5 | Integration | scan_toolchain() detects installed tools, ranks correctly |
| 7 | Integration | scan_posture() returns all 4 pillars, caching works |
| 8 | Integration | curl both endpoints, verify JSON structure |
| 9-10 | Manual | Visual inspection in browser |
