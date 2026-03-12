# System Health & Posture — Feature Plan

> **Status**: Planning
> **Created**: 2026-03-12
> **Scope**: New core feature — environment awareness, deprecation ranking, system health modal

---

## 1. Vision

The "Healthy" badge in the nav bar is currently a static lie — it always says green "Healthy"
regardless of actual system state. This feature replaces it with a **real-time aggregate
health indicator** backed by four pillars of system awareness.

The system should be able to tell the user:
- "Your OS is end-of-life and you're running dangerous tool versions"
- "kubectl install failed likely because your glibc is too old for the binary"
- "Your project scores B but your toolchain has 3 outdated components"

This is NOT audit. Audit is inward-looking (project quality). This is **outward-looking**
(environment capability). But it FEEDS audit with additional context and enriches
tool_install with blame attribution.

---

## 2. The Four Pillars

### 🖥️ Pillar 1: Platform
*"Is this system capable of running what I need?"*

**What it scans:**
| Signal | How to detect | Example |
|--------|--------------|---------|
| OS distribution | `/etc/os-release`, `sw_vers` (macOS), `wsl.exe` | Ubuntu 22.04 |
| OS version + EOL date | Hardcoded deprecation DB | EOL: April 2027 |
| Kernel version | `uname -r` | 5.15.0-91-generic |
| Architecture | `uname -m` | x86_64 / aarch64 |
| WSL version | `wsl.exe --version`, `/proc/version` | WSL2 |
| glibc version | `ldd --version` | 2.35 |
| OpenSSL version | `openssl version` | 3.0.2 |

**Deprecation data source:**
A structured JSON/YAML file (`deprecation_db.json`) mapping OS+version → EOL date + rank.
Updated manually or via a refresh mechanism. Covers:
- Ubuntu LTS releases (16.04 → 24.04)
- Debian stable releases
- macOS versions (Catalina → Sequoia)
- CentOS/RHEL/Rocky/Alma
- Windows via WSL (version of WSL itself)

**Ranking logic:**
```
if eol_date is None:          → Unknown
if eol_date > now + 2 years:  → Current (🟢)
if eol_date > now + 6 months: → Aging (🔵)
if eol_date > now:            → Outdated (🟡)
if eol_date > now - 1 year:   → Deprecated (🟠)
if eol_date <= now - 1 year:  → Dangerous (🔴)
```

### 🔧 Pillar 2: Toolchain
*"Are my tools current, compatible, and safe?"*

**What it scans:**
All tools from the existing 19 system presets, plus any detected binaries:

| Tool | Version detection | Current version source |
|------|------------------|----------------------|
| docker | `docker --version` | Hardcoded or API |
| kubectl | `kubectl version --client` | Hardcoded or API |
| terraform | `terraform version` | Hardcoded or API |
| python | `python3 --version` | Hardcoded |
| minikube | `minikube version` | Hardcoded or API |
| helm | `helm version` | Hardcoded or API |
| git | `git --version` | Hardcoded |
| node | `node --version` | Hardcoded |
| go | `go version` | Hardcoded |
| And 10+ more from presets | ... | ... |

**Version data source:**
A structured file (`tool_versions.json`) mapping tool → latest stable version + deprecation info.
```json
{
  "docker": {
    "current": "27.5.1",
    "min_supported": "24.0.0",
    "eol_versions": { "20.10": "2023-12", "19.03": "2022-01" },
    "known_cves": { "20.10": ["CVE-2024-21626"] }
  }
}
```

**Ranking logic:**
```
if not installed:                    → N/A
if version == current:               → Current (🟢)
if version >= current - 2 minor:     → Aging (🔵)
if version >= min_supported:         → Outdated (🟡)
if version < min_supported:          → Deprecated (🟠)
if version in eol_versions:          → Dangerous (🔴)
if version has known_cves:           → Dangerous (🔴) + CVE flag
```

**Integration with tool_install:**
When a tool installation fails, the system can query the toolchain pillar to provide
contextual blame:
- "terraform 1.9 requires glibc 2.31, your system has 2.27 (Ubuntu 18.04)"
- "This kubectl binary is for linux/amd64, your system is linux/arm64"

### 📦 Pillar 3: Project
*"Is the project itself well-structured and healthy?"*

**Already exists** as `/api/metrics/health` with 7 probes:
- git, docker, ci, packages, env, quality, structure

**Integration:**
- Reuse existing probe results (no new scanning needed)
- Map the grade/score to the ranking model:
  - A (90+) → Current 🟢
  - B (75+) → Aging 🔵
  - C (60+) → Outdated 🟡
  - D (40+) → Deprecated 🟠
  - F (<40) → Dangerous 🔴
- Link to "View full report in Audit tab" for details

### ⚡ Pillar 4: Runtime
*"Are integrations and infrastructure components working?"*

**What it monitors:**

1. **Circuit breakers** (already exists in `check_system_health()`):
   - All closed → Healthy
   - Half-open → Degraded
   - Open → Unhealthy

2. **Retry queue** (already exists):
   - Empty or pending → Healthy
   - Exhausted items → Degraded

3. **Integration adapters** (NEW):
   - Email (SMTP) → connection test
   - SMS (Twilio) → token validation
   - Reddit → auth check
   - Sentinel → reachability test
   - GitHub → token validity

**Ranking logic:**
```
if all_healthy and all_integrations_ok:  → Current 🟢
if one_degraded or one_adapter_stale:    → Aging 🔵
if circuit_open or adapter_failing:      → Outdated 🟡
if multiple_issues:                      → Deprecated 🟠
if critical_failures:                    → Dangerous 🔴
```

---

## 3. Data Model

### RankLevel (enum)
```python
class RankLevel(str, Enum):
    CURRENT    = "current"     # 🟢 Up to date, no issues
    AGING      = "aging"       # 🔵 Supported but nearing end
    OUTDATED   = "outdated"    # 🟡 End-of-life < 1 year, may work
    DEPRECATED = "deprecated"  # 🟠 End-of-life > 1 year, expect issues
    DANGEROUS  = "dangerous"   # 🔴 Known CVEs, no patches, high risk
    UNKNOWN    = "unknown"     # ⚪ Cannot determine
    NA         = "na"          # — Not applicable / not installed
```

### PostureItem
```python
@dataclass
class PostureItem:
    name: str                  # "Ubuntu", "docker", "kubectl"
    value: str                 # "22.04", "27.5.1", "1.24.0"
    rank: RankLevel            # Current, Aging, etc.
    detail: str = ""           # "EOL April 2027", "7 minor versions behind"
    current_version: str = ""  # Latest known version (for tools)
    eol_date: str = ""         # EOL date if known
    cves: list[str] = []       # Known CVEs for this version
```

### PillarResult
```python
@dataclass
class PillarResult:
    pillar: str                # "platform", "toolchain", "project", "runtime"
    rank: RankLevel            # Worst rank across items
    items: list[PostureItem]   # Individual findings
    warnings: list[str]        # Human-readable warnings
    recommendations: list[str] # Actionable recommendations
```

### SystemPosture
```python
@dataclass
class SystemPosture:
    overall_rank: RankLevel       # Worst rank across all pillars
    overall_status: str           # "healthy" | "attention" | "degraded" | "unhealthy"
    timestamp: str                # ISO timestamp
    pillars: dict[str, PillarResult]  # platform, toolchain, project, runtime
    summary: str                  # "2 warnings, 1 outdated tool, Score B"
```

---

## 4. Backend Architecture

### New service: `src/core/services/system_posture/`
```
system_posture/
├── __init__.py
├── models.py              # RankLevel, PostureItem, PillarResult, SystemPosture
├── platform_scanner.py    # OS, kernel, glibc, WSL detection
├── toolchain_scanner.py   # Tool version detection + ranking
├── project_bridge.py      # Bridge to existing /metrics/health
├── runtime_bridge.py      # Bridge to existing health.py + integration checks
├── ranking.py             # Version comparison, EOL date logic, rank computation
├── posture.py             # Orchestrator — runs all scanners, assembles SystemPosture
├── data/
│   ├── os_deprecation.json    # OS → EOL date mapping
│   └── tool_versions.json     # Tool → current version + deprecation info
└── README.md
```

### Key design decisions:

**Caching:**
- Platform data changes rarely → cache for session duration (or until explicit rescan)
- Toolchain data changes on install/update → cache with TTL (5 minutes?)
- Project data → reuse existing metrics/health cache
- Runtime data → fresh on each request (circuit breakers change in real-time)

**Scanning strategy:**
- Platform + Toolchain scans are **subprocess calls** (uname, docker --version, etc.)
- Must be non-blocking — run in thread pool
- Must be fault-tolerant — if a command fails, mark as Unknown, don't crash
- Must be fast — all tool version checks can run in parallel

**Integration with tool_install:**
- `toolchain_scanner` exposes a function: `get_tool_context(tool_name) → PostureItem`
- tool_install calls this when formatting error messages
- No circular dependency: system_posture is a data provider, tool_install is a consumer

### New API endpoints:

```
GET /api/posture
    → Full SystemPosture response (all 4 pillars)
    → Cached with TTL, bust with ?refresh=1

GET /api/posture/platform
    → PillarResult for platform only

GET /api/posture/toolchain
    → PillarResult for toolchain only

GET /api/posture/summary
    → Lightweight: overall_rank, overall_status, per-pillar ranks
    → Used by the nav badge (fast, minimal data)
```

---

## 5. Frontend Architecture

### Nav badge (always visible):
- On page load, fetch `GET /api/posture/summary` (lightweight)
- Update `#health-badge` with correct color + text
- Attach click handler to open the System Health modal

### System Health Modal:
- Opened by clicking the health badge
- Uses existing `modalOpen()` with `size: 'wide'`
- Summary bar at top (overall status + 4 pillar pills)
- 4 collapsible sections, one per pillar
- Each section shows items as a table/list with rank badges
- Warnings and recommendations shown inline
- "View Audit →" button links to the audit tab
- 🔄 Refresh button triggers `?refresh=1` and re-renders

### Files to create/modify:
```
NEW:  src/ui/web/templates/scripts/globals/_system_health.html
      → Modal rendering, badge update, pillar card rendering

MOD:  src/ui/web/templates/partials/_nav.html
      → Wire click handler to badge, update badge on load

MOD:  src/ui/web/templates/scripts/_dashboard.html
      → Optional: dashboard card linking to the modal
```

---

## 6. Deprecation Database Structure

### `os_deprecation.json`
```json
{
  "ubuntu": {
    "24.04": { "name": "Noble Numbat", "type": "LTS", "eol": "2029-04", "kernel": "6.8" },
    "22.04": { "name": "Jammy Jellyfish", "type": "LTS", "eol": "2027-04", "kernel": "5.15" },
    "20.04": { "name": "Focal Fossa", "type": "LTS", "eol": "2025-04", "kernel": "5.4" },
    "18.04": { "name": "Bionic Beaver", "type": "LTS", "eol": "2023-04", "kernel": "4.15" },
    "16.04": { "name": "Xenial Xerus", "type": "LTS", "eol": "2021-04", "kernel": "4.4" }
  },
  "debian": {
    "12": { "name": "Bookworm", "eol": "2028-06", "kernel": "6.1" },
    "11": { "name": "Bullseye", "eol": "2026-06", "kernel": "5.10" },
    "10": { "name": "Buster", "eol": "2024-06", "kernel": "4.19" }
  },
  "macos": {
    "15": { "name": "Sequoia", "eol": "2027-09" },
    "14": { "name": "Sonoma", "eol": "2026-09" },
    "13": { "name": "Ventura", "eol": "2025-09" },
    "12": { "name": "Monterey", "eol": "2024-09" },
    "11": { "name": "Big Sur", "eol": "2023-09" },
    "10.15": { "name": "Catalina", "eol": "2022-09" }
  },
  "centos": { ... },
  "rhel": { ... },
  "rocky": { ... },
  "alma": { ... },
  "windows_wsl": { ... }
}
```

### `tool_versions.json`
```json
{
  "docker": {
    "current": "27.5.1",
    "min_supported": "24.0.0",
    "version_scheme": "semver",
    "eol_versions": {
      "20.10": { "eol": "2023-12", "cves": ["CVE-2024-21626"] },
      "19.03": { "eol": "2022-01" }
    },
    "notes": "Docker Desktop vs Docker Engine have different versioning"
  },
  "kubectl": {
    "current": "1.31.4",
    "min_supported": "1.28.0",
    "version_scheme": "semver_minor",
    "skew_policy": "±3 minor versions from cluster",
    "notes": "kubectl supports ±1 minor version from the cluster it targets"
  },
  "terraform": {
    "current": "1.9.8",
    "min_supported": "1.5.0",
    "version_scheme": "semver",
    "eol_versions": {
      "0.14": { "eol": "2021-06" },
      "0.13": { "eol": "2021-01" }
    },
    "notes": "0.x → 1.x has breaking HCL syntax changes"
  },
  "python": {
    "current": "3.13.1",
    "min_supported": "3.10.0",
    "version_scheme": "semver_minor",
    "eol_versions": {
      "3.8": { "eol": "2024-10" },
      "3.7": { "eol": "2023-06" },
      "3.6": { "eol": "2021-12" }
    }
  },
  "minikube": { ... },
  "helm": { ... },
  "git": { ... },
  "node": { ... },
  "go": { ... },
  "curl": { ... }
}
```

---

## 7. Implementation Phases

### Phase 1: Data Model + Platform Scanner
- Create `src/core/services/system_posture/` package
- Implement `models.py` (RankLevel, PostureItem, PillarResult, SystemPosture)
- Implement `ranking.py` (version comparison, EOL date logic)
- Implement `platform_scanner.py` (OS, kernel, arch, WSL, glibc detection)
- Create `data/os_deprecation.json` with major distros
- Unit tests for ranking logic
- **Deliverable**: `platform_scanner.scan() → PillarResult`

### Phase 2: Toolchain Scanner
- Implement `toolchain_scanner.py`
- Parallel version detection for all known tools
- Create `data/tool_versions.json` with current versions
- Map to existing tool presets where possible
- **Deliverable**: `toolchain_scanner.scan() → PillarResult`

### Phase 3: Bridges + Orchestrator
- Implement `project_bridge.py` (wraps existing /metrics/health)
- Implement `runtime_bridge.py` (wraps existing health.py + integration status)
- Implement `posture.py` (orchestrator)
- Add caching layer (session-level for platform, TTL for toolchain)
- **Deliverable**: `posture.scan() → SystemPosture`

### Phase 4: API Endpoints
- Create `src/ui/web/routes/api/posture.py`
- Implement `GET /api/posture` (full), `/posture/summary` (lightweight)
- Wire caching (platform rarely changes, runtime always fresh)
- Register blueprint
- **Deliverable**: Working API returning full posture data

### Phase 5: Nav Badge (Live)
- Modify `_nav.html` to wire badge click handler
- Fetch `/api/posture/summary` on page load
- Update badge color + text based on overall_rank
- **Deliverable**: Badge shows real status

### Phase 6: System Health Modal
- Create `_system_health.html` script
- Implement modal layout (summary + 4 pillar cards)
- Each pillar renders its items as a ranked table
- Warnings, recommendations, links to audit
- Refresh button, auto-expand worst pillar
- **Deliverable**: Full modal working

### Phase 7: tool_install Integration
- Expose `get_tool_context(tool_name)` from toolchain_scanner
- Modify tool_install error handlers to include posture context
- Add "theoretical blame" when install fails
- **Deliverable**: Error messages enriched with system context

### Phase 8: Deprecation Database Refinement
- Expand OS and tool databases with more entries
- Add CVE cross-references for critical versions
- Consider optional refresh from a curated endpoint
- **Deliverable**: Comprehensive, accurate deprecation data

---

## 8. Performance Considerations

| Concern | Strategy |
|---------|----------|
| Platform scan is slow (subprocess calls) | Cache for session, scan once on first load |
| Tool version checks (19 tools × subprocess) | Parallel via ThreadPoolExecutor, cache 5m |
| Project health is slow (7 probes, 8s+) | Reuse existing cache from /metrics/health |
| Runtime checks | Fresh each time (fast — in-memory circuit breaker state) |
| Nav badge blocks page load | Fetch /posture/summary async after page renders |
| Modal load time | Show modal immediately with skeleton, load data async |

**Total cold-cache scan time estimate:**
- Platform: ~200ms (5 subprocess calls in parallel)
- Toolchain: ~500ms (19 subprocess calls in parallel)
- Project: reuse existing cache (0ms if cached, 8s if cold)
- Runtime: ~50ms (in-memory reads + quick integration pings)
- **Total: ~500ms warm, ~8s cold** (dominated by project health probes)

**Optimization:** The summary endpoint (`/api/posture/summary`) should return from cache
instantly and trigger a background rescan if stale. The badge should never block page load.

---

## 9. Open Questions

1. **Tool version freshness**: How do we keep `tool_versions.json` current?
   - Option A: Manual updates (simplest, risk of staleness)
   - Option B: GitHub API for release versions (requires network, rate limits)
   - Option C: Ship a curated snapshot, allow manual refresh command

2. **Integration health checks**: Should we actually ping SMTP/Twilio/Reddit on each
   posture scan? Or just check if credentials are configured?

3. **Notification triggers**: Should the system proactively warn when a tool becomes
   outdated (e.g., monthly background check + notification)?

4. **Scope of tool detection**: Only the 19 presets, or extensible?
   (What about npm, cargo, rustup, etc.?)

5. **CVE data**: Is a static known-CVE list sufficient, or do we need a live feed?

---

## 10. Dependencies

| Existing Module | How It's Used |
|----------------|---------------|
| `src/core/services/tool_manager/` | Tool presets, install logic, version detection |
| `src/core/observability/health.py` | Circuit breaker + retry queue health |
| `src/ui/web/routes/metrics/health.py` | Project health probes (7 domains) |
| `src/core/services/metrics/ops.py` | Probe implementations |
| `src/ui/web/templates/scripts/globals/_modal.html` | Modal system |
| `src/ui/web/templates/partials/_nav.html` | Health badge |

---

## 11. File Map (New + Modified)

### New Files
```
src/core/services/system_posture/__init__.py
src/core/services/system_posture/models.py
src/core/services/system_posture/ranking.py
src/core/services/system_posture/platform_scanner.py
src/core/services/system_posture/toolchain_scanner.py
src/core/services/system_posture/project_bridge.py
src/core/services/system_posture/runtime_bridge.py
src/core/services/system_posture/posture.py
src/core/services/system_posture/data/os_deprecation.json
src/core/services/system_posture/data/tool_versions.json
src/core/services/system_posture/README.md

src/ui/web/routes/api/posture.py
src/ui/web/templates/scripts/globals/_system_health.html
```

### Modified Files
```
src/ui/web/templates/partials/_nav.html          → Badge click handler
src/ui/web/templates/scripts/_dashboard.html      → Optional dashboard card
src/ui/web/server.py                              → Register posture blueprint
src/core/services/tool_manager/install.py         → Posture-enriched errors
```
