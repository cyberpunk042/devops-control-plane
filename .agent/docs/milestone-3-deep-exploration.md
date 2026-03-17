# Milestone 3 — Deep Exploration & Solution Design
> Written: 2026-03-17 | Status: DISCUSSION DRAFT

---

## Table of Contents

1. [E8 — Stack Version Advisor & Annotated Decisions](#e8)
2. [E3 — Module Lifecycle Ownership](#e3)
3. [E2 — Nested Project Support](#e2)

---

<a id="e8"></a>
## E8 — Stack Version Advisor & Annotated Decisions

### What exists today

**Detection finds module versions but posture never sees them.**

The detection system extracts a version per module:
- Python modules: reads `pyproject.toml` → `version = "x.y.z"`
- Node modules: reads `package.json` → `version` field
- Go modules: reads `go.mod` → `go x.y.z` (runtime version)
- Rust/Elixir/Helm: similar per-ecosystem extraction

These versions populate `Module.version` and are saved to `.state/current.json`.
But that's where it ends. The posture system never touches them.

**The posture system has 4 pillars today:**

```
  SystemPosture
  ├── platform   (💻)  OS, kernel, glibc, WSL         [scanner, TTL=∞]
  ├── toolchain  (🔧)  System tools: docker, kubectl   [scanner, TTL=5min]
  ├── project    (📦)  Health probes: git, ci, env...  [bridge, TTL=60s]
  └── runtime    (⚡)  Circuit breakers, retry queue    [bridge, TTL=0]
```

Each pillar returns a `PillarResult`:
```
  PillarResult
  ├── pillar: str                    "toolchain"
  ├── rank: RankLevel                OUTDATED (worst of items)
  ├── items: list[PostureItem]
  │     └── PostureItem
  │           ├── name: str          "docker"
  │           ├── value: str         "24.0.7"
  │           ├── rank: RankLevel    OUTDATED
  │           ├── detail: str        "3 releases behind"
  │           ├── current_version    "27.5.1"
  │           ├── eol_date           "2023-12" (if applicable)
  │           └── cves: list[str]    ["CVE-..."]
  ├── warnings: list[str]
  └── recommendations: list[str]
```

**The ranking engine is reusable.**

`rank_tool_version(installed, lifecycle)` in `ranking.py` is pure logic:
- Takes a version string + lifecycle dict
- Returns `(RankLevel, detail_string)`
- Supports two version schemes: `semver` and `semver_minor`
- Uses `tool_lifecycle.json` as its data source

The function doesn't care if the version belongs to a system tool or a module stack.
What it needs is lifecycle data — current version, EOL versions, min_supported.

**But there's no stack lifecycle data.**

`tool_lifecycle.json` covers system tools: docker, kubectl, terraform, go, node, python...
Wait — it DOES contain python, node, go as system tools. Those entries have `current`,
`eol_versions`, and `min_supported`.

The question: can we reuse the python/node/go entries in `tool_lifecycle.json` to rank
modules that run on those stacks?

```
  tool_lifecycle.json already has:
  ┌────────────────────────────────────────────────────────────────┐
  │  "python": {                                                   │
  │    "current": "3.14.1",                                        │
  │    "min_supported": "3.10.0",                                  │
  │    "version_scheme": "semver_minor",                           │
  │    "eol_versions": {                                           │
  │      "3.9": "2025-10",                                         │
  │      "3.8": { "eol": "2024-10", "cves": ["CVE-2024-6232"] }   │
  │    }                                                           │
  │  }                                                             │
  │                                                                │
  │  "node": {                                                     │
  │    "current": "22.14.0",                                       │
  │    "min_supported": "18.0.0",                                  │
  │    "version_scheme": "semver_minor",                           │
  │    "eol_versions": {                                           │
  │      "16": "2023-09",                                          │
  │      "14": "2023-04"                                           │
  │    }                                                           │
  │  }                                                             │
  │                                                                │
  │  "go": {                                                       │
  │    "current": "1.23.6",                                        │
  │    "min_supported": "1.21.0",                                  │
  │    "version_scheme": "semver_minor",                           │
  │    "eol_versions": {                                           │
  │      "1.20": "2024-02",                                        │
  │      "1.19": "2023-08"                                         │
  │    }                                                           │
  │  }                                                             │
  └────────────────────────────────────────────────────────────────┘
```

**But module versions ≠ runtime versions.**

`detect_version()` extracts the MODULE's own version (e.g. `0.1.0` from pyproject.toml).
That's the application version, not the Python/Node/Go version the module runs on.

For Go, `go.mod` contains the Go runtime requirement (`go 1.21`), which IS the
stack version. But for Python and Node, the detected version is the app version,
not the runtime version.

To rank a module's stack health, we need the **runtime/language version the module
targets**, not the module's own semver. That's a different piece of data.

```
  WHAT WE HAVE                        WHAT WE NEED
  ──────────────                       ────────────────
  Module: "core"                       Module: "core"
  Stack: python-flask                  Stack: python-flask
  Version: 0.1.0  ← app version       Runtime: 3.9  ← stack version
  Language: python                     Rank: OUTDATED (EOL 2025-10)
```

**Where does the stack/runtime version come from?**

Options:
1. **From stack requirements**: `stack.yml` has `requires: [{adapter: python, min_version: "3.8"}]`
   — but that's the MINIMUM, not what the module actually uses
2. **From the installed system tool**: posture already detects `python --version`
   — but that's the system-level version, shared across all modules
3. **From project config files**: `pyproject.toml` can declare `requires-python = ">=3.9"`,
   `package.json` can declare `engines.node`, `go.mod` declares `go 1.21`
   — this is the ACTUAL constraint the module declares

Option 3 is the right source. The module's own config file declares what
runtime version it targets.

```
  DETECTION EXTENSION:
  ┌────────────────────────────────────────────────────────────────┐
  │                                                                │
  │  detect_version() already reads:                               │
  │    pyproject.toml  → extracts app version                     │
  │    package.json    → extracts app version                     │
  │    go.mod          → extracts go runtime version              │
  │                                                                │
  │  NEW: detect_runtime_version() also reads:                    │
  │    pyproject.toml  → requires-python = ">=3.9"  → "3.9"      │
  │    package.json    → engines.node: ">=18"       → "18"       │
  │    go.mod          → go 1.21                    → "1.21"     │
  │    Cargo.toml      → rust-version = "1.75"      → "1.75"    │
  │                                                                │
  │  Stored on Module as:                                          │
  │    runtime_version: str | None                                │
  │                                                                │
  └────────────────────────────────────────────────────────────────┘
```

### The two version strategies

A module's constraint floor is a **deliberate choice**, not a deficiency.
There are two fundamentally different strategies:

**Strategy: Latest**
The module targets the current or near-current version. It uses the latest
features. When the ecosystem moves, the module should move too.
- `requires-python = ">=3.12"` with current at 3.14
- Signal: tight gap between floor and current
- What matters: **how far behind current are you?**

**Strategy: Compatibility**
The module targets a wide range deliberately. It wants to run on as many
environments as possible. A low floor is a feature, not a problem.
- `requires-python = ">=3.8"` with current at 3.14
- Signal: wide gap between floor and current
- What matters: **is the floor still alive? any CVEs?**

These are opposite postures. A module on `>=3.8` that works through 3.14
supports 7 versions — that's stronger compatibility than `>=3.12`. Flagging
it as "outdated" is wrong. But if 3.8 is EOL with no security patches,
that's a real exposure at the floor that the user should know about.

**The platform needs to:**
1. Deduce which strategy applies (from the constraint gap)
2. Let the user correct the deduction if it's wrong
3. Let the user annotate the reasoning
4. Present two separate signals: compatibility breadth AND floor health

### L1 Solution: New "Modules" section in System Posture

**Architecture: 5th pillar, bridge pattern.**

```
  SystemPosture (after E8)
  ├── platform   (💻)  OS, kernel, glibc, WSL
  ├── toolchain  (🔧)  System tools: docker, kubectl
  ├── project    (📦)  Health probes: git, ci, env...
  ├── runtime    (⚡)  Circuit breakers, retry queue
  └── modules    (🧩)  Module stack health                   ← NEW
```

The new pillar is a **bridge** (not a scanner) — it reads data that already
exists (detection results + lifecycle data), it doesn't run new subprocesses.

```
  bridges/modules.py

  bridge_modules(project_root) → PillarResult
  ┌────────────────────────────────────────────────────────────────┐
  │                                                                │
  │  1. Load detection results (from state or run fresh)           │
  │  2. Load project config (for version_strategy + version_note)  │
  │  3. For each module with a runtime_version:                    │
  │       a. Map module.language → lifecycle key                   │
  │          python → "python", node/typescript → "node",          │
  │          go → "go", rust → "rust"                              │
  │       b. Look up lifecycle in tool_lifecycle.json              │
  │       c. Compute:                                              │
  │          - constraint_floor: lowest version from constraint    │
  │          - current_version: from lifecycle data                │
  │          - range: all supported versions between floor/current │
  │          - strategy: from project.yml or deduced from gap      │
  │          - floor_health: is floor EOL? CVEs?                   │
  │       d. Create PostureItem with extended detail               │
  │                                                                │
  │  4. Build advisories for EOL/CVE floors                        │
  │  5. Return PillarResult(pillar="modules", ...)                │
  │                                                                │
  └────────────────────────────────────────────────────────────────┘
```

**Strategy deduction logic:**

```
  Given: floor = 3.8, current = 3.14

  gap = current_minor - floor_minor    (or major versions for node/go)

  If gap <= 2 → deduce "latest"        (tracking the ecosystem)
  If gap >= 4 → deduce "compatibility" (wide support is intentional)
  If gap == 3 → ambiguous              (mark as deduced, suggest user confirm)

  User can override in project.yml with version_strategy field.
  Deduced strategy shows a ✱ marker — "confirm or set explicitly."
```

**What the UI shows — matrix table:**

The module pillar renders as a table with separate columns for compatibility
breadth and floor health. These are two independent signals — wide compatibility
is a strength, EOL floor is a factual risk. They don't collapse into one color.

```
  System Posture Modal:
  ┌──────────────────────────────────────────────────────────────────────────┐
  │                                                                          │
  │  ┌───────┬──────────┬─────────┬─────────┬──────────┐                    │
  │  │💻 Plat│🔧 Tools  │📦 Proj  │⚡ Run   │🧩 Modules│                    │
  │  │  OK   │ Attention│  OK     │  OK     │ 2 notes  │                    │
  │  └───────┴──────────┴─────────┴─────────┴──────────┘                    │
  │                                                                          │
  │  ┌─ 🧩 Module Stack Health ──────────────────────────────────────────┐   │
  │  │                                                                    │   │
  │  │  Module    Stack    Floor  Current  Range        Compat.  Floor    │   │
  │  │  ──────────────────────────────────────────────────────────────── │   │
  │  │  web       python   ≥3.11  3.14    3.11 — 3.14  ████░░ 4  🟢    │   │
  │  │  core      python   ≥3.8   3.14    3.8 — 3.14   ██████ 7  🟡📝  │   │
  │  │  cli       python   ≥3.12  3.14    3.12 — 3.14  ███░░░ 3  🟢    │   │
  │  │  sdk       node     ≥16    22      16 — 22      ████░░ 4  🔴    │   │
  │  │  gateway   go       1.20   1.23    1.20 — 1.23  ████░░ 4  🟡    │   │
  │  │  docs      markdown —      —       —            —         ⚪    │   │
  │  │                                                                    │   │
  │  │  Strategy:                                                         │   │
  │  │  web: latest · cli: latest · core: compat. 📝 · sdk: compat.✱   │   │
  │  │  gateway: compat.✱ · docs: n/a                                    │   │
  │  │                                                                    │   │
  │  │  📝 core: "Supports client deployments on 3.8+"                   │   │
  │  │  ✱  sdk: strategy deduced from wide range — set explicitly        │   │
  │  │  ✱  gateway: strategy deduced — set explicitly                    │   │
  │  │                                                                    │   │
  │  │  Floor advisories:                                                 │   │
  │  │  ⚠️ core: Python 3.8 no longer receives security patches         │   │
  │  │     (EOL Oct 2024)                                                │   │
  │  │  ⚠️ sdk: Node 16 has known CVEs — deployments on 16 are exposed  │   │
  │  │  ⚠️ gateway: Go 1.20 no longer receives patches (EOL Feb 2024)   │   │
  │  │                                                                    │   │
  │  └────────────────────────────────────────────────────────────────────┘   │
  │                                                                          │
  └──────────────────────────────────────────────────────────────────────────┘
```

Key design decisions in this table:
- **Compatibility column** shows range breadth. Wider = better. No judgment.
- **Floor column** shows floor health. Only speaks to the floor version itself.
  🟢 = all supported versions still receive patches
  🟡 = floor is EOL (no patches, but no known CVEs)
  🔴 = floor has known CVEs
- **Strategy row** shows what lens the platform uses per module.
  `📝` = user set explicitly. `✱` = platform deduced, user should confirm.
- **Advisories** are factual: "3.8 doesn't receive patches." Not "upgrade."
  The user decides what to do with that information.
- A module with wide compatibility AND a healthy floor is the best state.
  A module with wide compatibility AND an EOL floor has a known exposure.
  Neither is "bad" — the table shows the facts, the user makes the call.

### L2 Solution: Annotated Decisions in project.yml

**Storage: on ModuleRef in project.yml.**

`.state/` is ephemeral — regenerated, not version-controlled. Annotations are
deliberate human decisions. They belong in `project.yml`, which is:
- Human-edited
- Version-controlled
- The source of truth for declared intent

**Current ModuleRef model** (5 fields):
```python
  class ModuleRef(BaseModel):
      name: str
      path: str
      domain: str = "service"
      stack: str = ""
      description: str = ""
```

**Extended ModuleRef** (2 new fields):
```python
  class ModuleRef(BaseModel):
      name: str
      path: str
      domain: str = "service"
      stack: str = ""
      description: str = ""
      version_strategy: str = ""    # ← NEW: "latest" | "compatibility" | ""
      version_note: str = ""        # ← NEW: human explanation
```

**In project.yml:**
```yaml
  modules:
    - name: core
      path: src/core
      domain: library
      stack: python-lib
      description: Domain models, services, engine
      version_strategy: compatibility
      version_note: "Supports client deployments on Python 3.8+"

    - name: web
      path: src/ui/web
      domain: ops
      stack: python-flask
      version_strategy: latest
      # no note needed — tracking latest is the default expectation

    - name: sdk
      path: src/sdk
      domain: library
      stack: node-lib
      # no strategy set → platform deduces from constraint gap
      # no note → deduced strategy shows ✱ marker

    - name: api-gateway
      path: src/gateway
      domain: service
      stack: node-express
      version_strategy: compatibility
      version_note: "Node 18 LTS — upgrading after payment SDK supports 20"
```

**Two fields, two purposes:**
- `version_strategy` — corrects the platform's deduction. Explicit > deduced.
  Valid values: `"latest"`, `"compatibility"`, or empty (let platform deduce).
- `version_note` — explains WHY. Free text, visible in posture view.
  Only meaningful when there's something to explain (usually with compatibility).

Both are optional. Both are version-controlled. Both are simple strings.

**How the bridge uses them:**

```
  bridge_modules() — strategy + annotation awareness:
  ┌────────────────────────────────────────────────────────────────┐
  │                                                                │
  │  For each module:                                              │
  │    1. Extract constraint floor from project config files       │
  │    2. Look up lifecycle data (current version, EOL dates)      │
  │    3. Determine strategy:                                      │
  │       a. If version_strategy set → use it (explicit)           │
  │       b. If not set → deduce from gap (mark as deduced ✱)     │
  │    4. Compute based on strategy:                               │
  │       - Compatibility range (floor → current, count versions)  │
  │       - Floor health (is floor EOL? CVEs?)                     │
  │    5. Attach version_note if present (📝 marker)              │
  │    6. Build advisories:                                        │
  │       - Floor EOL → factual advisory (not "upgrade")          │
  │       - Floor CVEs → risk advisory                             │
  │       - If version_note exists → advisory includes the note   │
  │                                                                │
  └────────────────────────────────────────────────────────────────┘
```

**What changes with strategy:**

```
  LATEST strategy:
  ┌────────────────────────────────────────────────────────────────┐
  │  Posture cares about: how close to current are you?            │
  │  Floor ≥3.12, current 3.14 → "1 behind" → normal              │
  │  Floor ≥3.10, current 3.14 → "2 behind" → still fine          │
  │  Floor ≥3.8, current 3.14  → this doesn't make sense for      │
  │    latest strategy — platform suggests switching to compat.    │
  └────────────────────────────────────────────────────────────────┘

  COMPATIBILITY strategy:
  ┌────────────────────────────────────────────────────────────────┐
  │  Posture cares about: is the floor still alive?                │
  │  Floor ≥3.11, all versions patched     → 🟢 healthy floor    │
  │  Floor ≥3.9, 3.9 EOL Oct 2025         → 🟡 floor EOL        │
  │  Floor ≥3.8, 3.8 has CVE-2024-6232    → 🔴 floor CVEs       │
  │  The RANGE is a strength — wider = more compatible.           │
  │  The floor health is a separate, factual signal.               │
  └────────────────────────────────────────────────────────────────┘
```

### What changes where — E8 summary

```
  BACKEND:
  ┌────────────────────────────────────────────────────────────────┐
  │                                                                │
  │  src/core/services/detection.py                                │
  │    + detect_runtime_constraint()  extract >=3.9 from configs  │
  │                                                                │
  │  src/core/models/module.py                                     │
  │    + runtime_constraint: str | None   ">=3.8" from config     │
  │    + runtime_floor: str | None        "3.8" (parsed lowest)   │
  │                                                                │
  │  src/core/models/project.py                                    │
  │    + version_strategy: str = ""   "latest" | "compatibility"  │
  │    + version_note: str = ""       human explanation            │
  │                                                                │
  │  src/core/services/system_posture/bridges/modules.py           │
  │    + bridge_modules()             new bridge, 5th pillar       │
  │    + strategy deduction logic     gap-based heuristic          │
  │    + floor health evaluation      EOL + CVE check              │
  │    + compatibility range calc     count supported versions     │
  │                                                                │
  │  src/core/services/system_posture/orchestrator.py              │
  │    + register "modules" pillar    in _assemble_posture()       │
  │                                                                │
  │  src/ui/web/routes/posture.py                                  │
  │    + enrich module items          strategy + note + advisories │
  │                                                                │
  └────────────────────────────────────────────────────────────────┘

  FRONTEND:
  ┌────────────────────────────────────────────────────────────────┐
  │                                                                │
  │  _system_posture.html                                          │
  │    + pillarOrder: add 'modules'                                │
  │    + pillarIcons: add modules: '🧩'                            │
  │    + pillarLabels: add modules: 'Modules'                      │
  │    + grid-template-columns: repeat(5, 1fr)                     │
  │    + Matrix table renderer (not item list)                     │
  │      - columns: Module, Stack, Floor, Current, Range,          │
  │        Compatibility, Floor Health                             │
  │    + Strategy row with 📝 (explicit) and ✱ (deduced) markers  │
  │    + Floor advisories section (factual, not prescriptive)      │
  │    + version_note display (📝 + text)                          │
  │                                                                │
  └────────────────────────────────────────────────────────────────┘

  DATA:
  ┌────────────────────────────────────────────────────────────────┐
  │                                                                │
  │  tool_lifecycle.json                                           │
  │    Already has python, node, go entries — reuse as-is          │
  │    May need: rust, ruby, elixir, java entries                  │
  │    Key data used: current version, eol_versions, cves          │
  │                                                                │
  │  project.yml                                                   │
  │    + version_strategy on ModuleRef (controls posture lens)     │
  │    + version_note on ModuleRef (human explanation)             │
  │                                                                │
  └────────────────────────────────────────────────────────────────┘
```

---

<a id="e3"></a>
## E3 — Module Lifecycle Ownership

### What E3 adds on top of E8

E8 gives us the snapshot: "module X is on runtime version Y, ranked Z."
E3 adds the **time dimension**: when did this happen, how long has it been,
what's the history?

### The problem E3 solves

Today, posture is a point-in-time scan. You see "core is OUTDATED" right now.
But you can't see:
- When did it become OUTDATED?
- How long has it been OUTDATED?
- Did it used to be CURRENT and degrade, or was it always behind?
- Did someone acknowledge it and then the acknowledgment expired?

### What E3 needs

**Lifecycle events emitted to the event store.**

The event store already exists (`src/core/services/events/`). Events are:
- Stored in hot deque (5000 events) + cold JSONL files per day
- Projected into timeline entries
- Grouped into chains by correlation_id
- Pushed via SSE to the frontend

E3 hooks into this by emitting events when module stack state changes:

```
  NEW EVENT TYPES:
  ┌────────────────────────────────────────────────────────────────┐
  │                                                                │
  │  module.stack.ranked                                           │
  │    When: posture scan produces a rank for a module             │
  │    Detail: { module, language, runtime_version, rank, prev }   │
  │    Only emitted when rank CHANGES (not on every scan)          │
  │                                                                │
  │  module.stack.degraded                                         │
  │    When: rank worsens (CURRENT→AGING, AGING→OUTDATED, etc.)   │
  │    Detail: { module, from_rank, to_rank, reason }              │
  │                                                                │
  │  module.stack.acknowledged                                     │
  │    When: user adds/updates version_note in project.yml         │
  │    Detail: { module, note_text, runtime_version, rank }        │
  │    Source: could be emitted by config reload or a dedicated    │
  │            API endpoint that edits project.yml                 │
  │                                                                │
  └────────────────────────────────────────────────────────────────┘
```

**Lifecycle state tracking.**

To know "when did it become OUTDATED", we need to persist state transitions.
Two options:

Option A — Derive from event history:
```
  Query event store: all module.stack.ranked events for "core"
  → Build timeline: CURRENT (2025-01) → AGING (2025-06) → OUTDATED (2025-10)
  → "core has been OUTDATED since October 2025 (5 months)"
```

Option B — Track in state:
```
  .state/current.json → ModuleState gains:
    rank: str = ""
    rank_since: str = ""   # ISO timestamp of last rank change
```

Option A is more powerful (full history) but depends on event retention.
Option B is simpler and always available. Both can coexist.

**What the timeline shows:**

```
  Timeline (existing view, new entries):
  ┌────────────────────────────────────────────────────────────────┐
  │                                                                │
  │  2026-03-17  🧩 module.stack.degraded                         │
  │              core: Python 3.9 → OUTDATED (EOL Oct 2025)       │
  │                                                                │
  │  2026-03-17  📝 module.stack.acknowledged                     │
  │              core: "vendor SDK constraint until Q3"            │
  │                                                                │
  │  2026-01-15  🧩 module.stack.degraded                         │
  │              core: Python 3.9 → AGING (approaching EOL)       │
  │                                                                │
  │  2025-06-01  🧩 module.stack.ranked                           │
  │              core: Python 3.9 → CURRENT                       │
  │                                                                │
  └────────────────────────────────────────────────────────────────┘
```

### What changes where — E3 summary

```
  BACKEND:
  ┌────────────────────────────────────────────────────────────────┐
  │                                                                │
  │  bridges/modules.py                                            │
  │    + compare current rank to previous rank                     │
  │    + emit module.stack.degraded when rank worsens              │
  │    + emit module.stack.ranked on first scan                    │
  │                                                                │
  │  src/core/models/state.py                                      │
  │    + ModuleState gains: rank, rank_since (optional)            │
  │                                                                │
  │  src/core/services/events/                                     │
  │    New event types registered in timeline projection           │
  │    Domain mapping: "module" → source MODULES                   │
  │                                                                │
  └────────────────────────────────────────────────────────────────┘

  FRONTEND:
  ┌────────────────────────────────────────────────────────────────┐
  │                                                                │
  │  Timeline view                                                 │
  │    + module.stack.* events render with 🧩 icon                 │
  │    + module.stack.acknowledged renders with 📝 icon            │
  │                                                                │
  │  Posture module items                                          │
  │    + "OUTDATED since October 2025" in detail text              │
  │    + Duration shown alongside rank                             │
  │                                                                │
  └────────────────────────────────────────────────────────────────┘
```

---

<a id="e2"></a>
## E2 — Nested Project Support

### What exists today

**Detection walks UP to find the root, then iterates declared modules.**

```
  find_project_file()
  ┌────────────────────────────────────────────────────────────────┐
  │  Start at cwd                                                  │
  │  Walk UP (max 20 levels)                                       │
  │  Find first project.yml                                        │
  │  That's THE project root                                       │
  │  Everything is relative to that root                           │
  └────────────────────────────────────────────────────────────────┘

  detect_modules(project, root, stacks)
  ┌────────────────────────────────────────────────────────────────┐
  │  For each ModuleRef in project.modules:                        │
  │    Check root/ref.path exists?                                 │
  │    Match stack detection rules                                 │
  │    Extract version                                             │
  │    Infer language                                              │
  │  Returns DetectionResult:                                      │
  │    modules: [Module, ...]                                      │
  │    unmatched_refs: [str, ...]     ← declared but path missing │
  │    extra_detections: [Module, ...]  ← found but undeclared     │
  └────────────────────────────────────────────────────────────────┘
```

A nested project (sub-directory with its own `.git` and `project.yml`) is
invisible. It's not in the parent's `modules` list, so detection never looks
at it. Its own `project.yml` is never loaded.

**The multi-module foundation IS solid:**
- 5 modules declared in this project's project.yml
- Different domains (library, ops, docs) per module
- Different stacks per module (python-lib, python-flask, python-cli, markdown)
- Stack inheritance (python-flask → python)
- Version detection per module
- Per-module health tracking
- 46 stack definitions with detection rules

What's missing: the concept that a directory can be its own project, not just
a module of the parent.

### The problem

```
  my-platform/
  ├── project.yml                      ← parent
  ├── src/api/                         ← module of parent (declared)
  ├── src/core/                        ← module of parent (declared)
  │
  ├── vendor/shared-lib/               ← sub-project
  │   ├── .git/                        ← its own git
  │   ├── project.yml                  ← its own config
  │   └── src/
  │       ├── utils/                   ← module of sub-project
  │       └── types/                   ← module of sub-project
  │
  └── experiments/new-thing/           ← sub-project (undeclared)
      ├── .git/
      ├── project.yml
      └── src/
```

`vendor/shared-lib` is a full project. It has its own git history, its own
modules, its own dependency tree. The parent platform should know about it
as a linked sub-project, not as a flat module.

### Solution: `sub_projects` in project.yml + auto-discovery

**project.yml gains a `sub_projects` key:**

```yaml
  # parent project.yml
  version: 1
  name: my-platform

  modules:
    - name: api
      path: src/api
      stack: python-flask
    - name: core
      path: src/core
      stack: python-lib

  sub_projects:                          # ← NEW
    - path: vendor/shared-lib
    - path: tools/internal-cli
```

Each sub-project path points to a directory that has its own `project.yml`.
The parent doesn't duplicate the sub-project's config — it just references it.

**Detection extends with two new phases:**

```
  run_detect() — extended:
  ┌────────────────────────────────────────────────────────────────┐
  │                                                                │
  │  Phase 1: EXISTING (unchanged)                                 │
  │    Load parent project.yml                                     │
  │    detect_modules() for parent's modules[]                     │
  │                                                                │
  │  Phase 2: DECLARED SUB-PROJECTS (new)                          │
  │    Read sub_projects[] from parent project.yml                 │
  │    For each:                                                   │
  │      ├── Check path exists                                     │
  │      ├── Check project.yml exists inside                       │
  │      ├── load_project() on sub's project.yml                   │
  │      ├── discover_stacks()                                     │
  │      ├── detect_modules() with sub's config                    │
  │      └── Return SubProject record                              │
  │                                                                │
  │  Phase 3: AUTO-DISCOVERY (new, optional)                       │
  │    Walk project tree (max depth 3)                              │
  │    Look for .git/ + project.yml in same directory              │
  │    Exclude paths already declared as modules or sub_projects   │
  │    Surface as discovered (not declared) sub-projects           │
  │                                                                │
  └────────────────────────────────────────────────────────────────┘
```

**New model:**

```python
  class SubProjectRef(BaseModel):
      path: str

  class Project(BaseModel):
      # ... existing fields ...
      sub_projects: list[SubProjectRef] = []   # ← NEW
```

**DetectionResult extends:**

```python
  class SubProjectResult:
      name: str                    # from sub's project.yml
      path: str                    # relative to parent root
      source: str                  # "declared" | "discovered"
      project: Project             # parsed sub project.yml
      detection: DetectionResult   # sub's own modules
      has_own_git: bool

  class DetectionResult:
      modules: list[Module]              # existing
      unmatched_refs: list[str]          # existing
      extra_detections: list[Module]     # existing
      sub_projects: list[SubProjectResult]  # ← NEW
```

**State persistence:**

```
  .state/current.json — extended:
  ┌────────────────────────────────────────────────────────────────┐
  │  {                                                             │
  │    "schema_version": 2,                                        │
  │    "modules": {                                                │
  │      "api": { ... },                                           │
  │      "core": { ... }                                           │
  │    },                                                          │
  │    "sub_projects": {                       ← NEW               │
  │      "shared-lib": {                                           │
  │        "path": "vendor/shared-lib",                            │
  │        "source": "declared",                                   │
  │        "has_own_git": true,                                    │
  │        "modules": {                                            │
  │          "utils": { "detected": true, "stack": "python-lib" }, │
  │          "types": { "detected": true, "stack": "typescript" }  │
  │        }                                                       │
  │      }                                                         │
  │    }                                                           │
  │  }                                                             │
  └────────────────────────────────────────────────────────────────┘
```

**UI: Sub-projects in the posture modules pillar:**

Sub-project modules appear in the same 🧩 Modules pillar, grouped:

```
  ┌─ 🧩 Modules ────────────────────────────────────────────┐
  │                                                          │
  │  my-platform                                             │
  │  🟢  web (python)     3.11    Current                   │
  │  🟡  core (python)    3.9     EOL October 2025   📝     │
  │       └─ "Python 3.9 — vendor SDK constraint"           │
  │  🟢  cli (python)     3.11    Current                   │
  │                                                          │
  │  vendor/shared-lib                                       │
  │  🟢  utils (python)   3.11    Current                   │
  │  🟢  types (typescript) 22    Current                   │
  │                                                          │
  │  ❓ experiments/new-thing (discovered, not declared)     │
  │                                                          │
  └──────────────────────────────────────────────────────────┘
```

**UI: Sub-projects in the wizard:**

```
  Wizard — Modules Step:
  ┌─────────────────────────────────────────────────────────────────┐
  │                                                                 │
  │  Modules                                                        │
  │  ────────                                                       │
  │  🐍  api          src/api        python-flask    service        │
  │  📦  core         src/core       python-lib      library        │
  │                                                                 │
  │  Sub-Projects                                                   │
  │  ────────────                                                   │
  │  📂  shared-lib   vendor/shared-lib              [declared]     │
  │       2 modules · own git repo                                  │
  │                                                                 │
  │  Discovered                                                     │
  │  ──────────                                                     │
  │  ❓  new-thing    experiments/new-thing           [discovered]   │
  │       [Declare] [Ignore]                                        │
  │                                                                 │
  └─────────────────────────────────────────────────────────────────┘
```

### What changes where — E2 summary

```
  BACKEND:
  ┌────────────────────────────────────────────────────────────────┐
  │                                                                │
  │  src/core/models/project.py                                    │
  │    + SubProjectRef model                                       │
  │    + sub_projects: list[SubProjectRef] on Project              │
  │                                                                │
  │  src/core/services/detection.py                                │
  │    + SubProjectResult model                                    │
  │    + discover_sub_projects() function                          │
  │    + DetectionResult gains sub_projects field                  │
  │                                                                │
  │  src/core/use_cases/detect.py                                  │
  │    + Phase 2: load declared sub-projects                       │
  │    + Phase 3: auto-discover undeclared sub-projects            │
  │    + Persist sub-project state                                 │
  │                                                                │
  │  src/core/models/state.py                                      │
  │    + sub_projects dict on ProjectState                         │
  │    + schema_version bump to 2                                  │
  │                                                                │
  └────────────────────────────────────────────────────────────────┘

  FRONTEND:
  ┌────────────────────────────────────────────────────────────────┐
  │                                                                │
  │  _system_posture.html                                          │
  │    + group module items by project/sub-project                 │
  │    + discovered sub-project indicator                          │
  │                                                                │
  │  Wizard templates                                              │
  │    + Sub-Projects section                                      │
  │    + Discovered section with Declare/Ignore actions            │
  │                                                                │
  └────────────────────────────────────────────────────────────────┘

  CONFIG:
  ┌────────────────────────────────────────────────────────────────┐
  │                                                                │
  │  project.yml                                                   │
  │    + sub_projects: [{path: "vendor/shared-lib"}, ...]          │
  │                                                                │
  └────────────────────────────────────────────────────────────────┘
```

---

## Implementation Order

```
  E8 first (foundation for E3):
  ┌────────────────────────────────────────────────────────────────┐
  │  1. detect_runtime_constraint() in detection.py                │
  │     Extract >=3.8 from pyproject.toml, package.json, go.mod   │
  │  2. runtime_constraint + runtime_floor fields on Module        │
  │  3. version_strategy + version_note on ModuleRef + project.yml │
  │  4. bridges/modules.py — new posture pillar                    │
  │     Strategy deduction, floor health, compatibility range     │
  │  5. Orchestrator registration                                  │
  │  6. Posture enrichment (strategy + note + advisories)          │
  │  7. Frontend: 5th pillar as matrix table                       │
  │     Columns: Module, Stack, Floor, Current, Range, Compat,    │
  │     Floor Health. Strategy row. Advisories section.            │
  └────────────────────────────────────────────────────────────────┘

  E3 next (builds on E8):
  ┌────────────────────────────────────────────────────────────────┐
  │  8. Emit module.stack.* events on rank changes                 │
  │  9. ModuleState gains rank + rank_since                        │
  │  10. Timeline projection for module events                     │
  │  11. Frontend: duration display on posture items               │
  └────────────────────────────────────────────────────────────────┘

  E2 (independent track, can parallel E3):
  ┌────────────────────────────────────────────────────────────────┐
  │  12. SubProjectRef model + project.yml schema                  │
  │  13. discover_sub_projects() in detection.py                   │
  │  14. Phase 2+3 in use_cases/detect.py                          │
  │  15. State persistence for sub-projects                        │
  │  16. Frontend: sub-project grouping in posture + wizard        │
  └────────────────────────────────────────────────────────────────┘
```

---

## Dependencies between evolutions

```
  E8 (stack advisor + annotations)
   │
   │  E8 produces the module posture pillar
   │  E3 adds time dimension to it
   │
   ▼
  E3 (lifecycle ownership)

  E2 (nested projects) ── independent, parallel track
   │
   │  E2 feeds MORE modules into the E8 pillar
   │  (sub-project modules appear alongside parent modules)
   │
   └──► E8 pillar renders them grouped
```
