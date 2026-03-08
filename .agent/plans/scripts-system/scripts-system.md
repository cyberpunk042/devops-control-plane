# Scripts System — Overview & Architecture

> **Status**: Planning — Iterating on design
> **Created**: 2026-03-07
> **Initiative**: New — Scripts, Automated Tests, and Execution Plans

---

## 0. Source of Truth — The User's Words (Verbatim)

Every design decision traces back to these exact statements.

### Message 1 — The Vision

> "We will also need to create script such as an audit script to produce class_diagrams and to detect stale documentation, outdated docs such as bad line count or bad line ref line(s) and whatnot."

> "Focus just on the first task but prepare for the two other tasks, that that any of those two following task is small or easy."

> "For the classes I did this once with java with a python tool that support almost all languages, I might be wrong but here is what it was, there was multiple file so you will able to see my scripts folder logic with the names prefix and stuff and tell me if I was right about the architecture diagram building ?"

> "it our case we would even be able to create mermaid version of the output if we chooe the mermaid output option and we usually sync this with a ./docs document properly located"

> "a script that would validate the quality of the routes and if they respect the standard and the RUN coverage and Audit / Trace and and auths and so on.... I want to study the pattern and be able to audit and produce a report that I can chose where it go even though it can have a default target."

> "audit when lazyness was used and routes or logics leaked into __init__ files..... and stuff like this..... those are all real case with real current examples"

> "Given the nature of the program we will: Build an entire system / integration for scripts, automated tests and execution plans of multiple type, fully_automated, semi_automated, interactive, ..."

> "This will be compatible with tool / integrations such as salt and ansible in the future."

### Message 2 — Clarifications

> "Its going to be a merge of two scripts folders in my case, scripts at the root is the default one for any project and can be updated via configuration but in reality like I said we are in dev and I dont even wanna have to import the template I just want to load them as if they were in the root scripts but they really are template scripts so they will go deeper."

> "Build an entire system / integration for scripts, automated tests and execution plans"

> "this will be super powerfull, even powershell script and execution through interop and such."

### Message 3 — Process

> "Scope everything but slip it into chunks and even sub chunks with details and do not forget a single thing I said."

> "the system itself is a milestone"

> "we need to actually be logical through and through from the bottom-up"

> "lets fold into another document for each chunks even if in the end we need 7 more documents"

---

## 1. The Big Picture

This is an **entire system** — not 3 scripts. The scripts (class diagrams, route audit, code hygiene) are **consumers** of the system. The system itself is the first milestone.

### 1.1 What the System Does

```
┌─────────────────────────────────────────────────────────────────────┐
│                         USERS                                        │
│                                                                      │
│    Developer           Admin Panel           CI / Automation         │
│    (CLI / TUI)         (Web UI)              (Salt / Ansible)        │
│        │                   │                       │                  │
├────────┼───────────────────┼───────────────────────┼──────────────────┤
│        ▼                   ▼                       ▼                  │
│   ┌───────────────────────────────────────────────────────────────┐  │
│   │                    INTERFACE LAYER                             │  │
│   │   CLI Commands        Web API Routes       Future: YAML API   │  │
│   └───────────────────────────┬───────────────────────────────────┘  │
│                               │                                      │
│   ┌───────────────────────────▼───────────────────────────────────┐  │
│   │                    EXECUTION FRAMEWORK                        │  │
│   │                                                               │  │
│   │   Registry ──▶ Executor ──▶ Event Stream ──▶ Output Router   │  │
│   │       │            │             │                │           │  │
│   │       │            │             │                │           │  │
│   │   Discovery    Subprocess    SSE/Events       File/API/      │  │
│   │   (Merge)      (py/sh/ps)    (live)          Stdout          │  │
│   │                                                               │  │
│   └───────────────────────────┬───────────────────────────────────┘  │
│                               │                                      │
│   ┌───────────────────────────▼───────────────────────────────────┐  │
│   │                    SCRIPT STORAGE                              │  │
│   │                                                               │  │
│   │   Layer 1: scripts/          ← Per-project (root, default)   │  │
│   │   Layer 2: templates/        ← Shipped with program          │  │
│   │                                                               │  │
│   │   Merged at runtime — templates appear as root in dev mode   │  │
│   └───────────────────────────────────────────────────────────────┘  │
│                                                                      │
│   ┌───────────────────────────────────────────────────────────────┐  │
│   │                    SCRIPT LIB (shared — M2)                   │  │
│   │                                                               │  │
│   │   code_analyzer    graph_builder    mermaid_generator         │  │
│   │   file_discovery   report_formatter                           │  │
│   │                                                               │  │
│   │              CO-LOCATED MODULES (per script):                  │  │
│   │   route_analyzer (M5)   init_analyzer (M6)                    │  │
│   │   doc_validator (M6)                                          │  │
│   └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

### 1.2 Reading the Diagram Bottom-Up

This is the logical order — each layer depends only on layers below it:

| Layer | What | Depends On |
|-------|------|------------|
| **Script Lib** | Shared: code_analyzer, graph_builder, mermaid_generator, file_discovery, report_formatter (M2). Co-located: route_analyzer (M5), init_analyzer + doc_validator (M6) | Nothing — pure logic |
| **Script Storage** | Where scripts live on disk. Two-layer merge (root + templates) | Nothing — pure filesystem |
| **Execution Framework** | Registry, Executor, Event Stream, Output Router | Script Storage, Script Lib |
| **Interface Layer** | CLI commands, Web API routes, Admin panel | Execution Framework |
| **Users** | Developer, Admin, CI/Automation | Interface Layer |

---

## 2. The Script Folder Architecture

### 2.1 Two-Layer Model

The user explicitly described a merge of two folders:

```
Layer 1: scripts/                           ← ROOT — per-project
    The user's own scripts for THIS project.
    Path is configurable (default: scripts/).
    This is where numbered permanent scripts (00_, 01_) live.
    Also where temporary/one-off scripts go (unnumbered).

Layer 2: <program_internal>/templates/      ← TEMPLATES — shipped with the program
    Template scripts that come with devops-control-plane itself.
    Organized by category (audit/, generators/, etc.).
    These are the "default" scripts that any project gets.
    In dev mode (project codeowner), they load automatically
    without any import step — they appear AS IF they were in root.
```

### 2.2 Merge Rules

| Scenario | Behavior |
|----------|----------|
| Script exists in root only | Loaded as-is |
| Script exists in templates only | Loaded, appears as if in root (in dev mode) |
| Script exists in BOTH root and templates | Root wins (user override) |
| Root path changed via config | System scans the configured path instead |
| Not in dev mode | Templates must be explicitly imported/enabled (TBD — needs further design) |

### 2.3 Naming Convention (Proven Pattern)

From the reference project (`the-virus-block-template/scripts/`):

```
NUMBERED (00_, 01_, ...) = PERMANENT, STABLE, CANONICAL
    → Part of the official toolkit
    → Documented, tested, maintained
    → Cannot be added without review

UNNUMBERED = TEMPORARY, ONE-OFF, SITUATIONAL
    → For immediate tasks, experiments, fixes
    → Can be deleted after use

PREFIX CATEGORIES:
    audit_    = Audit scripts (compliance, quality checks)
    debug_    = Debug helpers
    analyze_  = One-off analysis

SHARED LIBRARY:
    lib/      = Reusable modules imported by scripts
```

### 2.4 The Reference Project (Confirmed Architecture)

Location: `/mnt/c/Users/Jean/the-virus-block-template-1.21.6/scripts/`

The Java project had **36 scripts + lib/ with 9 modules**, following this pipeline:

```
java_parser.py (AST parse Java source)
    → graph_builder.py (ClassGraph — inheritance + dependency edges)
        → mermaid_generator.py (UML class diagrams in .mmd)
            → 09_generate_docs.py (writes diagrams to docs/)
```

**This is the correct architecture pattern.** For Python, we replace the Java parser with a Python AST parser (or pyreverse). Everything else — graph builder, mermaid generator, doc sync — follows the same flow.

---

## 3. Execution Framework Architecture

### 3.1 Core Concepts

| Concept | Definition |
|---------|-----------|
| **Script** | A registered executable unit — has metadata, lives in a known location, runs within the framework |
| **ScriptMeta** | Metadata about a script: id, name, category, language, mode, parameters, dependencies, default output target |
| **Execution Mode** | How the script runs: `fully_automated` (zero input), `semi_automated` (pauses at checkpoints), `interactive` (user drives each step) |
| **Execution Run** | A single instance of running a script — has a run ID, status, event history, result |
| **Event** | A structured message emitted during execution: type (progress/output/warning/error), timestamp, data |
| **Output Target** | Where the script's results go: filesystem path, stdout, API response. Default per script, overridable at runtime. |
| **Execution Plan** | A sequence of scripts with dependencies, mode, and checkpoint definitions. The composition unit. |

### 3.2 Execution Lifecycle (State Machine)

```
                 REGISTERED
                     │
                     ▼
    run()  ────▶ STARTING
                     │
                     ▼
                  RUNNING ◀──── resume() (from PAUSED)
                   │   │
          event()  │   │  checkpoint()
                   │   │
                   ▼   ▼
              COMPLETED  PAUSED ────── input() (semi_automated/interactive)
                   │         │
                   │    resume()/cancel()
                   │         │
                   ▼         ▼
               (results)  CANCELLED
                   │
                   ▼
                FAILED (on error at any point)
```

States:
- **REGISTERED**: Script is known to the system but not running
- **STARTING**: Process is being spawned
- **RUNNING**: Subprocess active, events being emitted
- **PAUSED**: Semi-automated mode — waiting for user input at a checkpoint
- **COMPLETED**: Finished successfully, results available
- **FAILED**: Error occurred, error details available
- **CANCELLED**: User or system stopped the run

### 3.3 Cross-Language Execution

The user explicitly said: "even powershell script and execution through interop"

| Language | Detection | Invocation | Notes |
|---------|-----------|-----------|-------|
| **Python** | `.py` extension | `{venv}/bin/python {script}` | MUST use project venv (user rule) |
| **Bash/Shell** | `.sh` extension or shebang `#!/bin/bash` | `bash {script}` or direct if executable | |
| **PowerShell** | `.ps1` extension | `pwsh {script}` | Cross-platform PowerShell Core |
| **Any executable** | No recognized extension + executable bit | Direct execution | Future extensibility |

### 3.4 Event Stream — Reuses Existing Infrastructure

M1 does NOT create new event models. It reuses the existing event infrastructure:

| Existing System | Events Published | M1 Integration |
|----------------|-----------------|----------------|
| `event_bus.py` | `script:started`, `script:completed`, `script:failed` | Executor publishes these |
| `stream_subprocess.py` | `stream:start`, `stream:line`, `stream:done` | Subprocess output streaming |
| `run_tracker.py` | `run:started`, `run:completed` | `tracked_run()` context manager |

All events flow through the existing SSE → admin panel pipeline. No new event types, no new models.

Future states (PAUSED, CANCELLED, checkpoint) are defined in §3.2 but implemented in **M7** (Execution Plans + Advanced Modes).

**Delivery**: SSE from web API, printed to terminal from CLI, logged to ledger for history.

### 3.5 Output Routing

Each script declares a default output target via `ScriptMeta.default_output`. The `OutputRouter` (M1) resolves the actual target:

```
Priority:
1. Explicit override (--output flag, API param)
2. ScriptMeta.default_output (from @script header)
3. ScriptConfig.default_output (from project.yml)
```

The router creates the directory if missing, injects `SCRIPT_OUTPUT_DIR` env var, and the script writes there.

Ledger logging is automatic via `tracked_run()` — not part of the output router.

---

## 4. Three Concrete Script Families

These are the CONSUMERS of the system. They are NOT the system.

### 4.1 Family 1: Class Diagram Generator (FOCUS)

**User's words**: "produce class_diagrams" / "mermaid version" / "sync this with a ./docs document"

**Pipeline**:
```
Python AST Parser
    → Class Graph Builder (inheritance + dependency edges)
        → Mermaid Generator (UML class diagrams in .mmd)
            → Docs Sync (write to docs/diagrams/)
```

**Shared lib modules needed**: `code_analyzer.py`, `graph_builder.py`, `mermaid_generator.py`, `report_formatter.py`, `file_discovery.py`

**Output**: Mermaid `.mmd` files + markdown wrappers → `docs/diagrams/` (default, configurable)

**Mode**: `fully_automated` — no user input needed

### 4.2 Family 2: Route Quality Audit (NOT SMALL)

**User's words**: "validate the quality of the routes" / "RUN coverage and Audit / Trace and auths" / "produce a report that I can chose where it go even though it can have a default target"

**Pipeline**:
```
Route Scanner (scan Flask blueprints)
    → Standard Checker (auth, trace, audit decorators, docstrings, RUN coverage)
        → Compliance Report (markdown with summary + detailed findings)
```

**Co-located module**: `route_analyzer.py` (in `audit/`, not shared lib). **Shared lib**: `file_discovery.py`, `report_formatter.py`

**Output**: Compliance report → configurable target (default + user choice)

**Mode**: `fully_automated` — scan and report

### 4.3 Family 3: Code Hygiene Audit (NOT SMALL)

**User's words**: "detect stale documentation, outdated docs such as bad line count or bad line ref line(s)" / "audit when lazyness was used and routes or logics leaked into __init__ files"

**Two sub-audits**:

```
Sub-audit A: __init__.py Logic Leak Detection
    → Scan all __init__.py files
    → Detect: function defs, class defs, business logic beyond re-exports
    → Report violations

Sub-audit B: Stale Documentation Detection
    → Scan markdown docs for line references
    → Detect: wrong line counts, outdated line refs, orphaned file references
    → Report violations
```

**Co-located modules**: `init_analyzer.py`, `doc_validator.py` (in `audit/`, not shared lib). **Shared lib**: `file_discovery.py`, `report_formatter.py`

**Output**: Hygiene report → configurable target

**Mode**: `fully_automated` — scan and report

---

## 5. Milestones — What Gets Built and When

### Milestone 0: Planning ✅
- This document (overview + architecture)
- Individual milestone documents (one per chunk)
- User review and iteration on each
- **Deliverable**: Approved plans ready for execution

### Milestone 1: The Script Execution Framework (THE SYSTEM) — 📋 Planned
- **Detailed plan**: `.agent/plans/scripts-system-M1-framework.md` (Iteration 2)
- **What**: Models, Registry (two-layer merge), Executor (subprocess, events), Output Router, Config I/O, **Wizard detection**, **project.yml `scripts:` section**
- **Result**: A working framework that can discover, register, and execute any script, stream events, route output, AND appear in the wizard as a detected integration
- **New since overview v1**: config.py (project.yml I/O), wizard/detect.py integration, _wizard_scripts_status helper, devops cards
- **Without this, nothing else works**

### Milestone 2: Shared Libraries (Script Lib) — 📋 Planned
- **Detailed plan**: `.agent/plans/scripts-system-M2-shared-lib.md` (Iteration 1)
- **What**: `code_analyzer.py`, `graph_builder.py`, `mermaid_generator.py`, `report_formatter.py`, `file_discovery.py`
- **Result**: Reusable modules that the class diagram script (and future scripts) import
- **Key decision**: Independent from audit parser — parallel AST extraction optimized for diagrams, not quality scoring
- **Depends on**: M1 (to know the contracts the lib modules must satisfy)

### Milestone 3: Class Diagram Script (First Consumer) — 📋 Planned
- **Detailed plan**: `.agent/plans/scripts-system-M3-class-diagrams.md` (Iteration 1)
- **What**: `generators/class_diagrams.py` template script — scoped Mermaid class diagram generation
- **Result**: Running the script produces mermaid class diagrams of the Python codebase, synced to output dir
- **Key feature**: Three output formats (mermaid, json, markdown), scope filtering by package
- **Depends on**: M1 + M2

### Milestone 4: Interface Integration (CLI + API + Admin Panel) — 📋 Planned
- **Detailed plan**: `.agent/plans/scripts-system-M4-interfaces.md` (Iteration 2)
- **What**: 🧩 Scripts card in Integrations tab (after Terraform in the card-grid), setup wizard (Detect → Adopt → Configure → Apply), CLI commands (`controlplane scripts ...`), Web API routes (`/api/scripts/...`), run modal with SSE streaming
- **Key UX**: Card in card-grid after Terraform. Setup wizard drives the user — detects existing scripts, offers adoption (add @script headers or take as-is), cherry-picks template scripts, writes project.yml. Follows the 📦 Artifacts pattern.
- **Coverage metrics**: Card displays language coverage (Python 100%, Shell 85%, PowerShell planned) so users see operability at a glance
- **Result**: Scripts can be run, monitored, and managed from CLI, API, and admin panel, with a guided setup experience
- **Depends on**: M1

### Milestone 5: Route Quality Audit Script
- **Detailed plan**: `.agent/plans/scripts-system-M5-route-audit.md`
- **What**: Route analyzer lib module + the audit script + report generation
- **Result**: Running the script produces a route quality report
- **Depends on**: M1, M2 (report_formatter)

### Milestone 6: Code Hygiene Audit Script
- **Detailed plan**: `.agent/plans/scripts-system-M6-code-hygiene.md`
- **What**: Init analyzer + doc validator lib modules + the hygiene audit script
- **Result**: Running the script detects `__init__` leaks and stale docs
- **Depends on**: M1, M2 (report_formatter)

### Milestone 7: Execution Plans + Advanced Modes
- **Detailed plan**: `.agent/plans/scripts-system-M7-plans.md`
- **What**: Execution plan model, plan sequencing, semi-automated checkpoints, interactive mode, plan persistence
- **Result**: Scripts can be composed into multi-step plans with dependency ordering
- **Depends on**: M1

### Milestone 8: Interop + Future Compatibility
- **Detailed plan**: `.agent/plans/scripts-system-M8-interop.md`
- **What**: PowerShell execution, Salt/Ansible YAML export, extended language support
- **Result**: Framework supports cross-platform scripts and exports execution plans for external automation tools
- **Depends on**: M1 + M7

---

## 6. Where Everything Lives (File Layout)

### 6.1 The Full Tree

```
devops-control-plane/
│
├── scripts/                                ← Layer 1: Per-project scripts (root)
│   ├── README.md                           ← Naming conventions, usage
│   ├── 00_class_diagrams.py                ← User override (numbered = permanent)
│   ├── 01_route_quality_audit.py           ← User override (numbered = permanent)
│   ├── quick_debug.py                      ← Temporary/one-off (no number)
│   └── output/                             ← Default output for reports (gitignored)
│
├── src/
│   ├── core/
│   │   ├── data/
│   │   │   └── script_templates/           ← Layer 2: Template scripts (shipped)
│   │   │       ├── lib/                    ← Shared lib modules (M2)
│   │   │       │   ├── __init__.py
│   │   │       │   ├── code_analyzer.py    ← Python AST class/field/method extraction
│   │   │       │   ├── graph_builder.py    ← Relationship graph construction
│   │   │       │   ├── mermaid_generator.py ← Mermaid syntax generation
│   │   │       │   ├── report_formatter.py ← Report output formatting
│   │   │       │   └── file_discovery.py   ← File walking and filtering
│   │   │       ├── audit/                  ← Audit script templates (M5, M6)
│   │   │       │   ├── __init__.py
│   │   │       │   ├── route_quality.py    ← Route Quality Audit script (M5)
│   │   │       │   ├── route_analyzer.py   ← Co-located: Flask route analysis (M5)
│   │   │       │   ├── code_hygiene.py     ← Code Hygiene Audit script (M6)
│   │   │       │   ├── init_analyzer.py    ← Co-located: __init__.py analysis (M6)
│   │   │       │   └── doc_validator.py    ← Co-located: Stale doc detection (M6)
│   │   │       ├── generators/             ← Generator templates (M3)
│   │   │       │   ├── __init__.py
│   │   │       │   └── class_diagrams.py   ← Class Diagram Generator (M3)
│   │   │       └── debug/                  ← Debug script templates (later)
│   │   │
│   │   └── services/
│   │       └── scripts/                    ← Backend service (the framework core)
│   │           ├── __init__.py             ← NO logic, re-exports only
│   │           ├── models.py              ← ScriptMeta, ScriptParameter, ScriptConfig
│   │           ├── config.py              ← project.yml I/O for scripts: section
│   │           ├── registry.py            ← Discovery, merge, list/filter
│   │           ├── executor.py            ← Subprocess execution, event streaming
│   │           ├── output_router.py       ← Output target routing
│   │           └── plans.py               ← Execution plan model (M7)
│   │
│   └── ui/
│       ├── cli/
│       │   └── scripts/                    ← CLI: controlplane scripts ...
│       │       ├── __init__.py             ← click.group + helpers
│       │       ├── list.py                 ← scripts list [--category] [--json]
│       │       ├── run.py                  ← scripts run <id> [--param K=V]
│       │       ├── info.py                 ← scripts info <id>
│       │       └── history.py              ← scripts history [--script-id]
│       │
│       └── web/
│           ├── routes/
│           │   └── scripts/                ← Web API: /api/scripts/...
│           │       ├── __init__.py          ← Blueprint definition
│           │       ├── registry.py          ← list, info, detect, templates
│           │       ├── execution.py         ← run, stream (SSE), adopt
│           │       └── history.py           ← run history
│           │
│           └── templates/
│               └── scripts/
│                   └── integrations/        ← Admin panel JS (card + wizard)
│                       ├── _scripts.html              ← Card: loadScriptsCard()
│                       ├── _scripts_run.html           ← Run modal + SSE stream
│                       └── setup/
│                           └── _scripts.html           ← Setup wizard (4 steps)
│
└── docs/
    └── diagrams/                           ← Default output for class diagrams
```

### 6.2 Layer-to-Directory Mapping

| Architecture Layer | Directory | Milestone |
|-------------------|-----------|-----------|
| Shared Lib | `src/core/data/script_templates/lib/` | M2 |
| Script Storage (Layer 1 — user) | `scripts/` | M1 |
| Script Storage (Layer 2 — templates) | `src/core/data/script_templates/` | M1 |
| Config I/O | `src/core/services/scripts/config.py` | M1 |
| Execution Framework | `src/core/services/scripts/` | M1 |
| Wizard Detection | `src/core/services/wizard/detect.py` (modified) | M1 |
| Wizard Helpers | `src/core/services/wizard/helpers.py` (modified) | M1 |
| CLI Interface | `src/ui/cli/scripts/` (5 files) | M4 |
| Web API Interface | `src/ui/web/routes/scripts/` (4 files) | M4 |
| Admin Panel Card + Wizard | `src/ui/web/templates/scripts/integrations/` (3 files) | M4 |
| Admin Panel Setup Wizard | `src/ui/web/templates/scripts/integrations/setup/` (1 file) | M4 |

---

## 7. Existing Architecture Constraints

From `docs/ARCHITECTURE.md` and `pyproject.toml`:

| Constraint | Impact on Scripts System |
|-----------|------------------------|
| **Layer model**: CLI ↔ TUI ↔ Web | Scripts must be accessible from all three interfaces |
| **Three-layer touch rule** | Scripts service + one UI layer per feature. Not three. |
| **Adapter pattern** | If scripts need to run shell commands, route through existing adapters |
| **Receipts, not exceptions** | Script execution produces `ExecutionResult`, never raw exceptions |
| **Audit ledger** | Every script run is logged to the ledger |
| **Python ≥ 3.11** | Can use modern Python features (match, dataclass slots, etc.) |
| **Project venv at `.venv/`** | Python scripts MUST execute via project venv |
| **No logic in `__init__.py`** | The scripts service `__init__.py` follows this rule |

---

## 8. Design Decisions — Answered

All questions from the original planning phase have been resolved:

| # | Question | Decision | Decided in |
|---|----------|----------|------------|
| 1 | UI placement | **Card in card-grid, after Terraform**. Not in a special section — same treatment as Docker/K8s/Terraform. Setup wizard follows Artifacts pattern (Detect → Adopt → Configure → Apply). | M4 |
| 2 | Script metadata format | **In-file `@script` header** — self-contained, grep-able, no orphans | M1 |
| 3 | Template script location | **`src/core/data/script_templates/`** — peer of catalogs/ and templates/ | M1 |
| 4 | Config in project.yml | **Yes — `scripts:` section** with root, template_source, default_output, history, execution, categories | M1 |
| 5 | pyreverse vs custom AST | **Custom AST** — independent code_analyzer using stdlib `ast`, parallel to audit parser | M2 |
| 6 | Template vs root | **Templates** — shipped with program, overridable via `@override` declaration in root scripts | M1, M3 |
| 7 | Override mechanism | **Explicit `@override: template_id`** — not filename-based | M1 |
| 8 | Shared lib location | **`src/core/data/script_templates/lib/`** — part of template ecosystem, not execution framework | M2 |
| 9 | Wizard integration | **Full integration** — files dict, devops cards, `_wizard_scripts_status()` helper | M1 |

---

## 9. Detailed Plan Documents (One per Milestone)

| Doc | Milestone | Status |
|-----|-----------|--------|
| `scripts-system.md` | Overview | **This file** — Iteration 2 |
| `scripts-system-M1-framework.md` | M1: Framework | ✅ **Planned** (Iteration 2) |
| `scripts-system-M2-shared-lib.md` | M2: Shared Lib | ✅ **Planned** (Iteration 1) |
| `scripts-system-M3-class-diagrams.md` | M3: Class Diagrams | ✅ **Planned** (Iteration 1) |
| `scripts-system-M4-interfaces.md` | M4: CLI + API + UI | ✅ **Planned** (Iteration 2) |
| `scripts-system-M5-route-audit.md` | M5: Route Quality | ✅ **Planned** (Iteration 1) |
| `scripts-system-M6-code-hygiene.md` | M6: Code Hygiene | ✅ **Planned** (Iteration 1) |
| `scripts-system-M7-plans.md` | M7: Execution Plans | Not started |
| `scripts-system-M8-interop.md` | M8: Interop | Not started |

---

## 10. Cross-References

| Reference | Location |
|-----------|----------|
| Reference project scripts | `/mnt/c/Users/Jean/the-virus-block-template-1.21.6/scripts/` |
| Reference lib/ modules | `/mnt/c/Users/Jean/the-virus-block-template-1.21.6/scripts/lib/` |
| Project architecture | `docs/ARCHITECTURE.md` |
| Artifacts system (similar pattern) | `.agent/plans/artifacts-implementation.md` |
| Route files (audit target) | `src/ui/web/routes/` — 34 blueprint packages |
| `__init__.py` files (audit target) | 53+ files under `src/core/services/` |
| Existing test infrastructure | `tests/` — 42 test files |
| Existing event streaming | `src/core/services/event_bus.py` |
| Existing subprocess handling | `src/core/services/stream_subprocess.py` |
| Existing audit ledger | `src/core/services/ledger/` |
