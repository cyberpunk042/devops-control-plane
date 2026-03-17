# E8 — Module Stack Intelligence
> Status: AGREED — 2026-03-17
> Supersedes: e8-stack-version-advisor-plan.md (flat single-floor model)
> Source discussion: .agent/docs/milestone-3-deep-exploration.md

---

## The Problem

A module is a composition of layers — language runtime, framework, dependencies,
and the code itself. Each layer has its own compatibility story. The platform
detects modules, knows their stacks, knows their dependencies, but never surfaces
the full picture of what runtime versions a module actually supports.

The old plan reduced this to a single "floor" from a config file. That's a grep,
not intelligence.

---

## The Vision

Per module, three layers of floor analysis:

**Layer 1 — Declared Floor**: what the module/stack/project SAYS the floor is.
This is intent, not necessarily truth.

**Layer 2 — Dependency Floor**: what the module's dependencies actually NEED.
If declared < deps → the declared floor is a lie.

**Layer 3 — Code Floor**: what language features the code actually USES.
If declared < code → the module WILL BREAK on the declared floor.

**Consistency Verdict**: compare all three floors.
- ✅ Consistent: declared ≥ code ≥ deps
- ⚠️ Gap: declared < code OR declared < deps (module claims compatibility it doesn't have)
- ℹ️ Could lower: declared > code AND > deps (wider compatibility is possible)

---

## Implementation Phases

### Phase 1 — Declared Floor (smart, layered detection)

Fix the detection to use the full knowledge the platform already has.

**Three-tier source hierarchy** (most specific wins):

```
  1. Module's own config file
     pyproject.toml in the module directory with requires-python
     package.json in the module directory with engines.node
     go.mod in the module directory with go directive
     → This is the module's own declaration. Strongest signal.

  2. Stack definition's requires
     python-flask inherits python ≥ 3.8 from parent
     node-express inherits node ≥ 18 from parent
     → Available for EVERY module that has a detected stack.
     → The technology's baseline floor.

  3. Project root config
     Root pyproject.toml with requires-python = ">=3.11"
     Root package.json with engines.node
     → Project-wide constraint. Weakest — shared by all modules.
     → Only used when tiers 1 and 2 produce nothing.
```

**Track the source**: the Module needs to know WHERE its floor came from
(own config, stack definition, or project root). This matters for the UI —
"inherited from stack" vs "declared by module" vs "inherited from project"
are different confidence levels.

**What changes:**

```
  detection.py:
    detect_runtime_constraint() becomes 3-tier:
      Tier 1: check module directory for config
      Tier 2: look up stack definition's requires
      Tier 3: fall back to project root
    Returns: (constraint, floor, source)
      source: "module" | "stack" | "project" | None

  module.py:
    runtime_constraint: str | None    ">=3.8"
    runtime_floor: str | None         "3.8"
    runtime_floor_source: str | None  "module" | "stack" | "project"

  bridge:
    Uses floor + source to compute strategy, range, health
    Source affects how the floor is displayed and how confident
    the platform is about it
```

**Stack integration**: the bridge loads stack definitions via `discover_stacks()`
and reads `requires[].min_version` for the module's effective stack. This is
the intelligence that was missing — the stack system knows what runtime each
technology needs, and the bridge uses that knowledge.

---

### Phase 2 — Dependency Floor

Leverage the existing `dependency_mgr` infrastructure.

**What exists already:**
- `dependency_mgr/scanner.py` — detects manifest files, parses dependencies
- `dependency_mgr/models.py` — DeclaredDep with version_spec per package
- `dependency_mgr/version_intel.py` — batch version lookups
- `dependency_mgr/graph.py` — shared dep detection, conflict analysis
- `dependency_mgr/subdeps.py` — sub-dependency traversal
- Mediator integration: `dependency.tree`, `dependency.versions`

**What needs to be built:**
- For each module's declared dependencies, look up each dep's own runtime
  constraint (e.g. flask 3.1 requires python ≥ 3.9)
- Find the HIGHEST min among all deps → that's the effective dep floor
- Surface when declared floor < dep floor (inconsistency)

**Where this data comes from:**
- PyPI metadata for Python packages (Requires-Python field)
- npm registry metadata for Node packages (engines.node)
- Each ecosystem's registry has this data

**What changes:**
- New function in bridge or new service: `compute_dependency_floor()`
- Reads from dependency_mgr's parsed manifests + registry metadata
- Adds "Deps" column to matrix table
- Flags inconsistencies

---

### Phase 3 — Code Floor

New static analysis capability.

**Approach**: scan module source files for version-specific language features.
Start with HIGH CONFIDENCE patterns only — features that are syntax errors
in earlier versions (no false positives).

**Python features detectable by regex (HIGH confidence):**

| Feature | Pattern | Min Version |
|---|---|---|
| f-strings | `f"...{...}..."` | 3.6 |
| walrus `:=` | `:=` | 3.8 |
| positional-only `/` | `def func(.../...)` | 3.8 |
| `list[]` type hints | `list[`, `dict[`, `set[`, `tuple[` (not from typing) | 3.9 |
| `match`/`case` | `match ...:` + `case ...:` | 3.10 |
| `except*` | `except*` | 3.11 |
| `type` statement | `type X = ...` | 3.12 |

**The highest feature version found = effective code floor.**

**What changes:**
- New service: `src/core/services/code_analysis/` or `version_features/`
- Scans `.py` files in module directory
- Returns: highest version feature detected + list of features found
- Adds "Code" column to matrix table
- Flags when declared < code floor

**Reference tools**: `vermin` (Python AST-based, 4140+ rules), `es-check` (Node)

---

### Phase 4 — Consistency Verdict

Compare all three floors per module, produce actionable verdicts.

```
  ✅ CONSISTENT: declared ≥ code ≥ deps
     "Everything works on the declared floor"

  ⚠️ DECLARED TOO LOW: declared < code OR declared < deps
     "Module says 3.8 but code uses match/case (3.10)"
     "Module WILL BREAK on 3.8"

  ℹ️ COULD LOWER: declared > code AND > deps
     "Module says 3.12 but nothing needs more than 3.9"
     "Could lower floor for wider compatibility"
```

**What changes:**
- Verdict logic in bridge
- "Status" column in matrix table
- Detailed explanations in status section below table

---

## The Matrix Table (Full Vision)

```
┌─ 🧩 Module Stack Health ────────────────────────────────────────────────────────────────┐
│                                                                                          │
│  Module    Stack         Declared   Deps    Code    Effective  Compat.    Floor   Status │
│  ────────────────────────────────────────────────────────────────────────────────────────│
│  web       python-flask  ≥3.11     ≥3.9    3.10    3.11       ███░░ 3v   🟢     ✅     │
│  core      python-lib    ≥3.8      ≥3.7    3.10    3.10       ████ 4v    🟢     ⚠️     │
│  cli       python-cli    ≥3.11     ≥3.9    3.8     3.11       ███░░ 3v   🟢     ✅     │
│  adapters  python-lib    ≥3.11     ≥3.8    3.8     3.11       ███░░ 3v   🟢     ✅     │
│  docs      markdown      —         —       —       —          —          ⚪     —      │
│                                                                                          │
│  Status:                                                                                 │
│  ✅ web: consistent — declared ≥ code ≥ deps                                            │
│  ⚠️ core: declared 3.8 but code uses match/case (3.10) — floor should be ≥3.10         │
│  ✅ cli: consistent                                                                     │
│  ✅ adapters: consistent                                                                │
│                                                                                          │
│  Strategy: web: latest · core: compat. 📝 · cli: latest · adapters: latest              │
│  📝 core: "Supports client deployments on 3.8+"                                         │
│                                                                                          │
│  Floor advisories:                                                                       │
│  (none — all effective floors are supported)                                             │
│                                                                                          │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

**Columns (full vision — phases 1-4):**
- **Module**: name
- **Stack**: detected stack (python-flask, node-express, etc.)
- **Declared**: what config says (from 3-tier hierarchy, phase 1)
- **Deps**: what dependencies need (phase 2)
- **Code**: what language features are used (phase 3)
- **Effective**: highest of all three = real floor
- **Compat.**: range breadth from effective floor to current. Wider = stronger.
- **Floor**: health of the effective floor (🟢 patched, 🟡 EOL, 🔴 CVEs)
- **Status**: consistency verdict (phase 4)

**Phase 1 table** (what we build first):
Only Declared, Compat, Floor columns populated.
Deps, Code, Effective, Status columns show "—" until phases 2-4.

---

## Phase 1 — Detailed Implementation

### Step 1: Fix detect_runtime_constraint() — 3-tier hierarchy

```
  detect_runtime_constraint(module_dir, stack_name, project_root, stacks)
    → (constraint, floor, source)

  Tier 1: Module's own config
    Check module_dir for pyproject.toml, package.json, go.mod, Cargo.toml
    If found with runtime constraint → return (constraint, floor, "module")

  Tier 2: Stack definition's requires
    Look up stacks[effective_stack]
    Read requires[].min_version for the runtime adapter
    Map: stack requires adapter "python" with min_version "3.8"
       → constraint ">=3.8", floor "3.8", source "stack"
    Need to map adapter name → config file ecosystem:
      python → python runtime
      node → node runtime
      docker → docker runtime
      shell → no runtime constraint (go, rust — use tier 1 instead)

  Tier 3: Project root config
    Check project_root for pyproject.toml, package.json, go.mod
    If found → return (constraint, floor, "project")

  Tier 4: Nothing found
    → return (None, None, None)
```

### Step 2: Add runtime_floor_source to Module model

```python
  runtime_floor_source: str | None = None   # "module" | "stack" | "project"
```

### Step 3: Update bridge to use stack definitions

```
  bridge_modules():
    Load stacks via discover_stacks()
    For each module:
      Look up stack = stacks[mod_state.stack]
      Pass stack's requires to detection
      Use floor_source to determine confidence:
        "module" → highest confidence (module's own declaration)
        "stack" → medium confidence (technology baseline)
        "project" → lower confidence (shared, may not reflect module)
```

### Step 4: Update enrichment to pass floor_source

```
  item["floor_source"] = "module" | "stack" | "project"
  Frontend shows this as a subtle indicator:
    "≥3.8 (from stack)" vs "≥3.11 (declared)" vs "≥3.11 (project)"
```

### Step 5: Update frontend table

Ensure all 7 original columns work with the improved data.
Add floor_source indicator.
Show stack name from detected_stack (not parsed from item name).

---

## What Each Phase Unlocks

```
  Phase 1 (declared floor)        → "what does the module say?"
     │
     │  This is the foundation. Gets the table working
     │  with real data from stack definitions.
     │
  Phase 2 (dependency floor)      → "what do the deps actually need?"
     │
     │  Leverages existing dependency_mgr.
     │  Catches declared floors that are lies.
     │
  Phase 3 (code floor)            → "what does the code actually use?"
     │
     │  New static analysis capability.
     │  Catches declared floors the code contradicts.
     │
  Phase 4 (consistency verdict)   → "is this module honest about its floor?"
     │
     │  The intelligence layer. Compares all three.
     │  Produces actionable verdicts.
     │
     ▼
  FULL MODULE STACK INTELLIGENCE
```

---

## What This Does NOT Include

- Automated upgrades or migration scripts
- System tool lifecycle changes (toolchain pillar handles that)
- Lifecycle time tracking / events (E3)
- Nested project support (E2)
- Full AST parsing (regex patterns for high-confidence features only in phase 3)
- Transitive dependency constraint solving (phase 2 reads direct deps only)

---

## Existing Infrastructure to Leverage

```
  Stack system:
    src/core/data/stacks/*/stack.yml       47 stacks with requires
    src/core/config/stack_loader.py        discover_stacks(), parent resolution
    src/core/models/stack.py               AdapterRequirement model

  Detection:
    src/core/services/detection.py         detect_modules(), match_stack()
    src/core/models/module.py              Module model

  Dependency manager (phase 2):
    src/core/services/dependency_mgr/      Full dep tree, version intel, graph
    Mediator keys: dependency.tree, dependency.versions

  Posture system:
    src/core/services/system_posture/      Pillar infrastructure
    bridges/modules.py                     Module bridge (needs update)
    orchestrator.py                        5th pillar registered
    mediator/registrations/posture.py      Mediator integration done

  UI:
    _system_posture.html                   renderModulePillar() exists
    admin.css                              Module table CSS exists
```

---

## Pre-Implementation Checklist (Phase 1)

Before writing code:

- [ ] READ detection.py — current detect_runtime_constraint()
- [ ] READ stack_loader.py — discover_stacks(), _resolve_parents()
- [ ] READ stack.py — AdapterRequirement model (adapter, min_version)
- [ ] READ several stack.yml files — python, python-flask, node, go
- [ ] READ module.py — current fields
- [ ] READ bridges/modules.py — current bridge logic
- [ ] READ posture.py — current enrichment
- [ ] READ _system_posture.html — current renderModulePillar()
- [ ] VERIFY: discover_stacks() returns resolved stacks with inherited requires
- [ ] VERIFY: which adapter names map to which runtime ecosystems
