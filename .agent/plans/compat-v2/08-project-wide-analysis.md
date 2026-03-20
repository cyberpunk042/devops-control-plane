# 08 — Project-Wide Analysis Spec

> **Document**: 8 of 37
> **Milestone**: M3 — Import chain resolution
> **Status**: Draft

---

## 1. Purpose

Individual module analysis is necessary but not sufficient. A project is a graph of modules that import each other. The project-wide analysis layer sits above individual module analysis and provides:

- Full dependency graph between project modules
- Correct ordering for version plan execution
- Cross-module incompatibility detection
- Project-level compatibility report
- Identification of "root cause" modules — where the actual incompatible code lives vs where the symptoms appear

This is the layer that would have told the user: "don't start with web — start with core. Core has 14 `datetime.UTC` usages. Web's failures are caused by importing core."

---

## 2. Module Dependency Graph

### 2.1 Building the graph

```python
class ProjectAnalyzer:
    """Analyze compatibility across all modules in a project."""

    def __init__(
        self,
        detection_engine: DetectionEngine,
        import_resolver: ImportResolver,
        registry: FeatureRegistry,
    ):
        self._detection = detection_engine
        self._resolver = import_resolver
        self._registry = registry

    def build_module_graph(
        self,
        project_root: Path,
        modules: list[ModuleConfig],
    ) -> ModuleGraph:
        """Build the dependency graph between project modules.

        For each module:
        1. Build import graph (document 04)
        2. Identify cross-module edges
        3. Create module-level dependency edges

        Returns a directed graph where:
        - Nodes are modules (core, cli, web, etc.)
        - Edges mean "module A imports from module B"
        """
```

### 2.2 ModuleGraph data model

```python
@dataclass
class ModuleDependency:
    """A dependency from one module to another."""
    source_module: str          # Module that imports: "web"
    target_module: str          # Module being imported: "core"
    import_count: int           # How many import edges cross this boundary
    files_importing: int        # How many files in source import from target
    files_imported: int         # How many files in target are imported
    sample_imports: list[str]   # Example import paths for display

@dataclass
class ModuleGraph:
    """Dependency graph between project modules."""
    modules: list[str]                          # All module names
    dependencies: list[ModuleDependency]        # Directed edges
    _adjacency: dict[str, set[str]]             # module → set of modules it depends on

    def depends_on(self, module: str) -> set[str]:
        """Modules that this module imports from."""

    def depended_on_by(self, module: str) -> set[str]:
        """Modules that import from this module."""

    def topological_order(self) -> list[str] | None:
        """Modules in dependency order (fix these first).
        Returns None if circular dependency exists."""

    def fix_order(self, modules_with_plans: list[str]) -> list[list[str]]:
        """Optimal fix order — returns tiers.

        Tier 0: modules with no dependencies on other planned modules (fix first)
        Tier 1: modules that only depend on tier 0
        Tier 2: modules that only depend on tier 0 and 1
        etc.

        Modules in the same tier can be fixed in parallel.

        Example:
          core depends on: nothing
          cli depends on: core
          web depends on: core
          → Tier 0: [core]
          → Tier 1: [cli, web]  (can be parallel after core is done)
        """

    def circular_dependencies(self) -> list[tuple[str, str]]:
        """Find circular module dependencies."""

    def dependency_depth(self, module: str) -> int:
        """How deep in the dependency chain is this module?
        Leaf modules (no deps) → 0. Deepest dependent → max depth."""
```

### 2.3 Example for this project

```
project.yml modules:
  core (src/core)      — domain models, services, engine
  adapters (src/adapters) — tool bindings
  cli (src/ui/cli)     — CLI interface
  web (src/ui/web)     — Flask admin web interface
  docs (docs)          — documentation

Module dependency graph:
  core → (no project deps — leaf module)
  adapters → core
  cli → core, adapters
  web → core, adapters

Fix order for Python 3.8 target:
  Tier 0: [core]         ← fix first, everything depends on it
  Tier 1: [adapters]     ← fix after core
  Tier 2: [cli, web]     ← fix last, can be parallel
```

---

## 3. Project-Wide Compatibility Report

### 3.1 Full scan

```python
def analyze_project(
    self,
    project_root: Path,
    modules: list[ModuleConfig],
    target_version: str,
    language: str,
    direction: str = "downgrade",
) -> ProjectAnalysisResult:
    """Analyze the entire project for version compatibility.

    For each module:
    1. Run detection engine (direct findings)
    2. Build import graph
    3. Trace transitive findings

    Then:
    4. Build module dependency graph
    5. Compute fix order
    6. Attribute each finding to its root cause module
    7. Generate project-level report
    """
```

### 3.2 ProjectAnalysisResult

```python
@dataclass
class ProjectAnalysisResult:
    project_root: str
    target_version: str
    language: str
    direction: str
    scan_time: str

    # Per-module results
    module_results: dict[str, AnalysisResult]  # module_name → result

    # Project-level aggregation
    module_graph: ModuleGraph
    fix_order: list[list[str]]                 # Tiered fix order

    # Cross-module attribution
    root_cause_map: dict[str, list[RootCause]]  # module → root causes in other modules

    # Totals
    total_findings: int
    total_direct: int
    total_transitive: int
    total_fixable: int
    total_manual: int
    modules_affected: int
    modules_clean: int

    def report(self) -> str:
        """Generate human-readable project report."""

    def module_summary(self, module_name: str) -> str:
        """Generate summary for a single module."""

@dataclass
class RootCause:
    """A transitive incompatibility attributed to its source."""
    feature_id: str
    source_file: str            # Where the incompatible code actually is
    source_module: str          # Module the source file belongs to
    affected_modules: list[str] # Modules that are affected via import chains
    import_chains: list[list[str]]  # How the incompatibility reaches each affected module
    fix_available: bool
```

### 3.3 Example report

```
Project Compatibility Report
Target: Python 3.8 (downgrade)
Scanned: 4 modules, 847 files
Duration: 2.3s

═══════════════════════════════════════════════════════════

Module: core (src/core) — Tier 0 (fix first)
  ❌ 15 direct incompatibilities
     14× datetime.UTC (3.11+) — auto-fixable
      1× StrEnum (3.11+) — manual fix
  Dependencies: none
  Status: NEEDS FIXING

Module: adapters (src/adapters) — Tier 1
  ✅ 0 direct incompatibilities
  ⚠️ 3 transitive (from core)
  Dependencies: core
  Status: BLOCKED by core

Module: cli (src/ui/cli) — Tier 2
  ✅ 0 direct incompatibilities
  ⚠️ 0 transitive (cli doesn't import core's datetime-using files)
  Dependencies: core, adapters
  Status: CLEAN

Module: web (src/ui/web) — Tier 2
  ❌ 1 direct incompatibility
      1× datetime.UTC in routes/metrics/health.py — auto-fixable
  ⚠️ 14 transitive (from core)
  Dependencies: core, adapters
  Status: BLOCKED by core + 1 direct fix needed

═══════════════════════════════════════════════════════════

Root causes:
  datetime.UTC (14 occurrences in core, 1 in web):
    → Affects: core, adapters, web
    → Fix core first, then web's direct occurrence
    → cli is unaffected (doesn't import these files)

  StrEnum (1 occurrence in core):
    → Affects: core (only modules importing core's executor.py)
    → Manual rewrite required

═══════════════════════════════════════════════════════════

Recommended fix order:
  1. Fix core (15 findings — 14 auto-fixable, 1 manual)
  2. Fix web (1 finding — auto-fixable)
  3. adapters and cli — no direct fixes needed, transitive resolved by step 1
```

---

## 4. Root Cause Attribution

### 4.1 The problem

Without root cause attribution, the user sees:
```
Module web: 15 incompatible features found!
  14 in src/core/...
  1 in src/ui/web/...
```

This is confusing — "why is `src/core` showing up in web's scan?" The user doesn't know if they should fix these files, where to fix them, or what module's plan covers them.

### 4.2 The solution

Root cause attribution traces each finding to its source module and builds a map:

```python
def attribute_root_causes(
    project_result: ProjectAnalysisResult,
    module_graph: ModuleGraph,
) -> dict[str, list[RootCause]]:
    """For each module, identify root causes of transitive findings.

    Algorithm:
    1. For each module M with transitive findings:
    2. Group transitive findings by source module
    3. For each source module S:
       a. Get all findings in S that affect M
       b. Trace the import chain(s) from M to S
       c. Create a RootCause entry:
          - feature_id
          - source_file (in S)
          - source_module (S)
          - affected_modules (M and any others)
          - import_chains (how M reaches S)
    """
```

### 4.3 Deduplication

A single incompatible file in `core` might be imported by multiple modules. The root cause is ONE entry, not duplicated per affected module:

```
RootCause: python.stdlib.datetime_utc
  Source: src/core/models/action.py (module: core)
  Affected modules:
    - web (via src/ui/web/routes/backup/archive.py → src/core/models/action)
    - adapters (via src/adapters/git_adapter.py → src/core/models/action)
  Fix: Fix in core's plan → resolves for both web and adapters
```

---

## 5. Plan Generation from Analysis

### 5.1 Automatic plan creation

The project analysis can generate version plans automatically:

```python
def generate_plans(
    self,
    project_result: ProjectAnalysisResult,
    target_version: str,
) -> dict[str, VersionPlan]:
    """Generate version plans for all affected modules.

    For each module with direct findings:
    1. Create analysis steps (scan, guide)
    2. Create fix steps (per finding type)
    3. Create verification steps (test env, run tests)
    4. Order steps correctly
    5. Add dependency info (blocked_by)

    Returns a plan per module.
    """
```

### 5.2 Plan ordering based on module graph

```python
def order_module_plans(
    plans: dict[str, VersionPlan],
    module_graph: ModuleGraph,
) -> list[tuple[str, VersionPlan]]:
    """Order plans by dependency tier.

    Tier 0 plans should be executed first.
    Plans in the same tier can be executed in parallel.
    Later tier plans may start with BLOCKED steps that
    unblock when earlier tier plans complete.
    """
```

### 5.3 Dynamic step generation

Unlike v1's static recipe (same steps for every module), v2 generates steps based on what the analysis actually finds:

```
Module: core
Analysis found: 14× datetime.UTC, 1× StrEnum

Generated plan:
  1. Scan for incompatible features                    [analysis]
  2. Fix datetime.UTC (14 files) — auto-fix available  [transform]
  3. Fix StrEnum (1 file) — manual                     [manual]
  4. Verify fixes                                      [verification]
  5. Run compatibility tests                           [test]
  6. Re-scan and confirm                               [analysis]

Module: web
Analysis found: 1× datetime.UTC (direct), 14× datetime.UTC (transitive from core)

Generated plan:
  1. Scan for incompatible features                    [analysis]
  2. Wait for core's plan to complete                  [blocked]
  3. Fix datetime.UTC (1 file) — auto-fix              [transform]
  4. Verify fixes                                      [verification]
  5. Run compatibility tests                           [test]
  6. Re-scan and confirm                               [analysis]
```

Step 2 in web's plan is BLOCKED until core's plan completes. This is dynamic — it wouldn't exist if core had no issues.

---

## 6. Cross-Module State Tracking

### 6.1 Blocker resolution

When a blocking module's plan completes, dependent modules' BLOCKED steps should unblock:

```python
def on_plan_completed(
    self,
    completed_module: str,
    all_plans: dict[str, VersionPlan],
    module_graph: ModuleGraph,
) -> list[tuple[str, str]]:
    """Handle a module's plan completing.

    Find all steps in other modules that were BLOCKED by this module.
    Transition them from BLOCKED → PENDING.

    Returns: list of (module_name, step_id) that were unblocked.
    """
    unblocked = []
    dependent_modules = module_graph.depended_on_by(completed_module)

    for dep_module in dependent_modules:
        plan = all_plans.get(dep_module)
        if not plan:
            continue
        for step in plan.steps:
            if step.state == StepState.BLOCKED and step.blocked_by == completed_module:
                step.transition(StepState.PENDING)
                unblocked.append((dep_module, step.step_id))

    return unblocked
```

### 6.2 Re-analysis after blocker resolution

When a BLOCKED step unblocks, the system should re-analyze to confirm the transitive issues are resolved:

```
core plan completed → web's BLOCKED step unblocks
→ Re-run transitive analysis for web
→ If core's fixes resolved all transitive findings → web's step is PENDING (ready to run)
→ If some transitive findings remain → web's step stays BLOCKED with updated reason
```

---

## 7. Multi-Language Projects

### 7.1 Language detection per module

A project can have modules in different languages:

```yaml
modules:
  - name: core
    path: src/core
    stack: python-lib       # → language: python
  - name: web
    path: src/ui/web
    stack: python-flask     # → language: python
  - name: frontend
    path: src/frontend
    stack: typescript-react # → language: typescript
  - name: api-gateway
    path: services/gateway
    stack: go-service       # → language: go
```

### 7.2 Cross-language boundaries

Modules in different languages don't import each other directly (Python doesn't import Go). Cross-language dependencies happen at:
- API boundaries (HTTP calls, gRPC, message queues)
- Shared configuration (JSON schemas, protobuf definitions)
- Shared infrastructure (Docker compose, Kubernetes)

The project-wide analysis handles these by:
- Analyzing each language independently
- Not creating import edges across language boundaries
- Noting cross-language dependencies in the report as informational

### 7.3 Per-language target versions

Different modules may target different versions:

```yaml
modules:
  - name: core
    version_plan:
      target: "3.8"         # Python 3.8
  - name: frontend
    version_plan:
      target: "ES2018"      # JavaScript ES2018
  - name: api-gateway
    version_plan:
      target: "1.19"        # Go 1.19
```

The project analysis respects per-module targets. A module's findings are based on ITS target, not a global target.

---

## 8. Caching and Incremental Analysis

### 8.1 Full analysis caching

A full project scan can be expensive (10,000+ files). Cache results:

```python
@dataclass
class CachedProjectAnalysis:
    result: ProjectAnalysisResult
    file_hashes: dict[str, str]     # file_path → content hash at scan time
    timestamp: str
    target_version: str

    def is_stale(self, project_root: Path) -> bool:
        """Check if any scanned files have changed since the analysis."""
```

### 8.2 Incremental re-analysis

When files change, only re-analyze affected modules:

```python
def incremental_analyze(
    self,
    cached: CachedProjectAnalysis,
    changed_files: list[str],
    project_root: Path,
) -> ProjectAnalysisResult:
    """Re-analyze only modules affected by file changes.

    1. Determine which modules contain the changed files
    2. Re-analyze those modules
    3. Re-build module graph edges involving those modules
    4. Re-attribute root causes
    5. Merge with cached results for unchanged modules
    """
```

---

## 9. Integration Points

### 9.1 With Detection Engine (Document 03)
- Project analyzer calls detection engine per module
- Aggregates per-module results into project result

### 9.2 With Import Resolver (Document 04)
- Uses import graphs to build module dependency graph
- Cross-module edges become module dependencies

### 9.3 With Lifecycle (Document 06)
- Module graph determines BLOCKED states
- Plan completion triggers blocker resolution
- Fix order determines which plans to run first

### 9.4 With API/UI (Documents 30-31)
- Project report endpoint returns full analysis
- UI shows module dependency graph
- UI shows fix order tiers
- UI shows per-module status with blockers
