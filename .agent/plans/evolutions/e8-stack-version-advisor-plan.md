# E8 — Stack Version Advisor & Annotated Decisions
> Status: AGREED — 2026-03-17
> Source discussion: .agent/docs/milestone-3-deep-exploration.md

---

## The Problem

The platform detects each module's stack and version. But module stack versions
are never surfaced in posture. A user has no visibility into what runtime versions
their modules target, how wide their compatibility is, or whether their floor
versions are still receiving security patches.

More importantly: a module's version constraint floor is a **deliberate choice**.
There are two fundamentally different strategies — tracking latest vs maximizing
compatibility — and the platform must understand the difference instead of
blindly treating a low floor as "outdated."

---

## The Solution

### Core Concept: Two Strategies

**Latest** — module targets current or near-current. Wants latest features.
- `requires-python = ">=3.12"` with current at 3.14
- What matters: how far behind current are you?

**Compatibility** — module targets wide range deliberately. Low floor = feature.
- `requires-python = ">=3.8"` with current at 3.14
- What matters: is the floor still alive? Any CVEs?

A module on `>=3.8` supporting 3.8 through 3.14 = 7 versions = strongest
compatibility. That's not "outdated." But if 3.8 is EOL with no security
patches, that's a factual exposure at the floor.

**Two separate signals, never collapsed into one color:**
- **Compatibility breadth** — how wide the range is. Wider = stronger.
- **Floor health** — is the lowest version still receiving patches?

### New Posture Pillar: 🧩 Modules (5th pillar)

```
  SystemPosture
  ├── platform   (💻)  OS, kernel, glibc, WSL         [scanner, TTL=∞]
  ├── toolchain  (🔧)  System tools: docker, kubectl   [scanner, TTL=5min]
  ├── project    (📦)  Health probes: git, ci, env...  [bridge, TTL=60s]
  ├── runtime    (⚡)  Circuit breakers, retry queue    [bridge, TTL=0]
  └── modules    (🧩)  Module stack health              [bridge, TTL=60s]
```

Bridge pattern — reads detection results + module lifecycle data, no new
subprocesses.

### UI: Matrix Table

```
┌─ 🧩 Module Stack Health ─────────────────────────────────────────────────────────┐
│                                                                                   │
│  Module       Stack      Floor   Current   Range        Compatibility  Floor      │
│  ─────────────────────────────────────────────────────────────────────────────────│
│  web          python     ≥3.11   3.14      3.11 — 3.14  ████░░░░ 4v   🟢         │
│  core         python     ≥3.8    3.14      3.8 — 3.14   ████████ 7v   🟡 📝      │
│  cli          python     ≥3.12   3.14      3.12 — 3.14  ███░░░░░ 3v   🟢         │
│  sdk          node       ≥16     22        16 — 22      ████░░░░ 4v   🔴         │
│  gateway      go         1.20    1.23      1.20 — 1.23  ████░░░░ 4v   🟡         │
│  docs         markdown   —       —         —             —            ⚪         │
│                                                                                   │
│  Strategy:                                                                        │
│  web: latest · cli: latest · core: compat. 📝 · sdk: compat.✱                   │
│  gateway: compat.✱ · docs: n/a                                                   │
│                                                                                   │
│  📝 core: "Supports client deployments on 3.8+"                                  │
│  ✱  sdk: strategy deduced from wide range — set explicitly                       │
│  ✱  gateway: strategy deduced — set explicitly                                   │
│                                                                                   │
│  Floor advisories:                                                                │
│  ⚠️ core: Python 3.8 no longer receives security patches (EOL Oct 2024)          │
│  ⚠️ sdk: Node 16 has known CVEs — deployments on 16 are exposed                 │
│  ⚠️ gateway: Go 1.20 no longer receives patches (EOL Feb 2024)                  │
│                                                                                   │
└───────────────────────────────────────────────────────────────────────────────────┘
```

**Columns:**
- **Compatibility** — range breadth. Wider = better. No judgment.
- **Floor** — floor version health only.
  🟢 = all supported versions still patched
  🟡 = floor EOL (no patches, no known CVEs)
  🔴 = floor has known CVEs
- **Strategy row** — 📝 = user set explicitly. ✱ = platform deduced, confirm.
- **Advisories** — factual ("3.8 doesn't receive patches"). Not prescriptive.

### Strategy Deduction

```
  Given: floor = 3.8, current = 3.14
  gap = current_minor - floor_minor

  gap <= 2  → deduce "latest"
  gap >= 4  → deduce "compatibility"
  gap == 3  → ambiguous, mark as deduced ✱

  User overrides in project.yml → version_strategy field.
```

### User Controls: project.yml

Two new fields on ModuleRef:

```yaml
  modules:
    - name: core
      path: src/core
      domain: library
      stack: python-lib
      version_strategy: compatibility          # "latest" | "compatibility" | ""
      version_note: "Supports client deployments on Python 3.8+"
```

- `version_strategy` — corrects the deduction. Explicit > deduced.
  Validated: must be `"latest"`, `"compatibility"`, or empty string.
- `version_note` — explains why. Free text, visible in posture.

Both optional. Both version-controlled. Both simple strings.

### Detection: Runtime Constraint Extraction

`detect_version()` already reads pyproject.toml, package.json, go.mod for the
app version. New function extracts the runtime constraint:

```
  detect_runtime_constraint(module_path, stack_name):

  Python:   pyproject.toml → requires-python = ">=3.8"      → floor "3.8"
            Also handles: ">=3.8,<4", "~=3.8", ">=3.8.0"
            Extracts the LOWEST version from the constraint.

  Node:     package.json   → engines.node: ">=18"           → floor "18"
            Also handles: ">=18.0.0", "^18", "18.x"

  Go:       go.mod         → go 1.21                        → floor "1.21"
            Direct — go.mod declares the exact version.

  Rust:     Cargo.toml     → rust-version = "1.75"          → floor "1.75"
            Direct — rust-version is always a minimum.

  If no constraint found → runtime_floor = None
  Module shows in table but with — in Floor/Range/Compat columns.
```

Stored on Module:
```python
  runtime_constraint: str | None    # ">=3.8" (raw from config)
  runtime_floor: str | None         # "3.8" (parsed lowest version)
```

### Bridge Logic

```
  bridge_modules(project_root) → PillarResult

  1. Load detection results (modules with runtime_floor)
  2. Load project config (version_strategy + version_note per module)
  3. Load module lifecycle data (see Data section below)
  4. For each module with a runtime_floor:
     a. Map language → lifecycle key (python, node, go, rust)
     b. Look up lifecycle data for that language
     c. Determine strategy:
        - If version_strategy set → use it (explicit)
        - If not → deduce from gap, mark ✱
     d. Compute:
        - Compatibility range: count versions between floor and current
        - Floor health: check_floor_health(floor, lifecycle)
     e. Create PostureItem with extended detail
  5. Build floor advisories (factual, not prescriptive)
  6. Return PillarResult(pillar="modules", ...)
```

### Floor Health Evaluation

This is the module pillar's own logic — NOT a reuse of `rank_tool_version()`.
Tool ranking answers "how far behind is this tool?" Module floor health answers
"is the floor version still alive?"

```
  check_floor_health(floor_version, lifecycle):

  1. Is floor_version in eol_versions?
     a. If yes + has CVEs → 🔴 "floor has known CVEs", list them
     b. If yes, no CVEs  → 🟡 "floor EOL, no longer receives patches"
     c. If no             → continue
  2. Is floor_version < min_supported?
     → 🟡 "Below minimum supported"
  3. Otherwise → 🟢 "All supported versions still patched"
```

---

## What Changes Where

### Backend

```
  src/core/services/detection.py
    + detect_runtime_constraint()     NEW function
      Extracts runtime version constraint from module config files.
      Parses constraint string to find floor version.
      Called by detect_modules() alongside detect_version().

  src/core/models/module.py
    + runtime_constraint: str | None  raw constraint from config (">=3.8")
    + runtime_floor: str | None       parsed lowest version ("3.8")

  src/core/models/project.py
    + version_strategy: str = ""      on ModuleRef, validated values
    + version_note: str = ""          on ModuleRef, free text

  src/core/services/system_posture/bridges/modules.py    (NEW FILE)
    + bridge_modules()                5th pillar bridge
    + deduce_strategy()               gap-based heuristic
    + check_floor_health()            module-specific floor evaluation
    + compute_compat_range()          count supported versions
    This is the module pillar's OWN logic. It follows the bridge
    pattern from bridges/project.py and bridges/runtime.py but does
    NOT reuse rank_tool_version(). Different domain, different question.

  src/core/services/system_posture/orchestrator.py
    + register "modules" pillar       in _assemble_posture()
    + cache key "modules"             TTL=60s
```

### Frontend

```
  _system_posture.html
    + pillarOrder: add 'modules'
    + pillarIcons: { modules: '🧩' }
    + pillarLabels: { modules: 'Modules' }
    + grid-template-columns: repeat(5, 1fr)     status bar CSS
    + renderModulePillar()            NEW renderer (not renderPillar)
      The module pillar uses a matrix table layout, not the standard
      item-list layout used by other pillars. This is a new render
      function, not a modification of the existing renderPillar().
      - 7 columns: Module, Stack, Floor, Current, Range, Compat, Floor
      - Strategy row with 📝 (explicit) and ✱ (deduced) markers
      - Floor advisories section (factual statements)
      - version_note display (📝 + text below annotated rows)
```

### Data

```
  src/core/services/system_posture/data/module_lifecycle.json    (NEW FILE)
    Module stack lifecycle data. Separate from tool_lifecycle.json.
    Same structure (current, eol_versions, min_supported) but this
    file is specifically for module runtime versions, not system tools.

    Even though tool_lifecycle.json happens to contain python/node/go
    entries, those are for ranking the SYSTEM TOOL (python --version).
    Module lifecycle tracks the LANGUAGE ECOSYSTEM versions that
    modules target. Keeping them separate means:
    - No coupling between tool posture and module posture
    - Can evolve independently (module lifecycle may need different
      granularity, e.g. per-LTS-track for Node)
    - Clear ownership: tool data serves toolchain pillar,
      module data serves modules pillar

    Initial entries: python, node, go, rust.
    Structure per entry:
    {
      "current": "3.14",
      "min_supported": "3.10",
      "eol_versions": {
        "3.9": "2025-10",
        "3.8": { "eol": "2024-10", "cves": ["CVE-2024-6232"] }
      }
    }

  project.yml
    + version_strategy on ModuleRef
    + version_note on ModuleRef
```

---

## Implementation Steps

```
  Step 1: Runtime constraint extraction
  ┌────────────────────────────────────────────────────────────────┐
  │  NEW function detect_runtime_constraint() in detection.py      │
  │  Parse constraint from: pyproject.toml, package.json,          │
  │    go.mod, Cargo.toml                                          │
  │  Handle real-world constraint formats:                         │
  │    ">=3.8", ">=3.8,<4", "~=3.8", "^18", "18.x", etc.         │
  │  Extract floor (lowest) version from constraint                │
  │  Add runtime_constraint + runtime_floor to Module model        │
  │  Wire into detect_modules() flow alongside detect_version()    │
  │                                                                │
  │  Before writing: READ detection.py to understand the existing  │
  │  detect_version() pattern. Follow it. Read Module model to     │
  │  understand existing fields.                                   │
  └────────────────────────────────────────────────────────────────┘

  Step 2: Project.yml schema extension
  ┌────────────────────────────────────────────────────────────────┐
  │  Add version_strategy + version_note to ModuleRef              │
  │  version_strategy validated: "latest" | "compatibility" | ""   │
  │  version_note: str, no validation needed                       │
  │  Both optional, both default ""                                │
  │                                                                │
  │  Before writing: READ project.py ModuleRef model. READ         │
  │  loader.py to understand validation. Follow existing patterns. │
  └────────────────────────────────────────────────────────────────┘

  Step 3: Module lifecycle data
  ┌────────────────────────────────────────────────────────────────┐
  │  Create module_lifecycle.json in system_posture/data/          │
  │  Separate file from tool_lifecycle.json                        │
  │  Same structure, different domain                              │
  │  Initial entries: python, node, go, rust                       │
  │  Source EOL dates from official ecosystem documentation        │
  └────────────────────────────────────────────────────────────────┘

  Step 4: Module posture bridge
  ┌────────────────────────────────────────────────────────────────┐
  │  Create bridges/modules.py (NEW FILE)                          │
  │  bridge_modules() → PillarResult                              │
  │  Own logic — does NOT reuse rank_tool_version()               │
  │  Functions:                                                    │
  │    deduce_strategy(floor, current) → strategy + deduced flag   │
  │    check_floor_health(floor, lifecycle) → health + detail      │
  │    compute_compat_range(floor, current) → count                │
  │  Register in orchestrator as 5th pillar, TTL=60s               │
  │                                                                │
  │  Before writing: READ bridges/project.py and bridges/runtime.py│
  │  to understand the bridge pattern. READ orchestrator.py to     │
  │  understand pillar registration. Follow existing patterns.     │
  └────────────────────────────────────────────────────────────────┘

  Step 5: Posture enrichment
  ┌────────────────────────────────────────────────────────────────┐
  │  Extend _enrich_posture_actions() for module items             │
  │  Attach: strategy (explicit/deduced), version_note,            │
  │    floor health, compatibility range, advisories               │
  │                                                                │
  │  Before writing: READ posture.py _enrich_posture_actions()     │
  │  to understand how other pillars are enriched. Follow pattern. │
  └────────────────────────────────────────────────────────────────┘

  Step 6: Frontend matrix table
  ┌────────────────────────────────────────────────────────────────┐
  │  Add modules to pillarOrder/Icons/Labels arrays                │
  │  NEW function renderModulePillar() — matrix table, not list    │
  │  7 columns: Module, Stack, Floor, Current, Range, Compat, Floor│
  │  Strategy row with 📝 and ✱ markers                           │
  │  Floor advisories section                                      │
  │  version_note display                                          │
  │  CSS: grid-template-columns update for 5th chip                │
  │                                                                │
  │  Before writing: READ _system_posture.html to understand       │
  │  renderPillar() and the pillar rendering loop. The module      │
  │  pillar needs its own renderer, not a reuse of renderPillar(). │
  └────────────────────────────────────────────────────────────────┘
```

---

## Pre-Implementation Checklist (from rules)

Before writing ANY code for this plan:

- [ ] READ `detection.py` — understand `detect_version()` pattern
- [ ] READ `module.py` — understand existing Module fields
- [ ] READ `project.py` — understand ModuleRef model + loader validation
- [ ] READ `bridges/project.py` — understand bridge pattern
- [ ] READ `bridges/runtime.py` — understand bridge pattern
- [ ] READ `orchestrator.py` — understand pillar registration + caching
- [ ] READ `ranking.py` — understand it but do NOT reuse it for modules
- [ ] READ `posture.py` — understand `_enrich_posture_actions()` enrichment
- [ ] READ `_system_posture.html` — understand `renderPillar()` and pillar loop
- [ ] READ `tool_lifecycle.json` — understand structure to replicate in module_lifecycle.json
- [ ] READ real `pyproject.toml` files — understand actual constraint formats

---

## What This Does NOT Include

- Automated upgrades or migration scripts
- System tool lifecycle changes (already handled by toolchain pillar)
- Lifecycle time tracking / events (that's E3)
- Nested project support (that's E2)
- Any reuse of `rank_tool_version()` — module floor health is its own logic
