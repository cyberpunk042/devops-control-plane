# 01 — System Architecture Overview

> **Document**: 1 of 37
> **Milestone**: M1 — Feature database & data model
> **Status**: Draft
> **Replaces**: `src/core/services/module_upgrade/automation/` (entire directory)

---

## 1. Problem Statement

The v1 system has systemic failures across every layer:

### 1.1 Detection failures
- Regex-based pattern matching produces false positives (matches inside strings/comments) and false negatives (misses patterns that don't match the regex)
- `_RUNTIME_FEATURES` and `_ANNOTATION_FEATURES` are hardcoded lists with incomplete coverage
- `datetime.UTC` was missing entirely from the pattern list — the scan and guide steps passed, marked themselves done, and the incompatibility was only discovered at test time
- No import chain awareness — scanning `src/ui/web` doesn't find `from datetime import UTC` in `src/core` even though web imports core

### 1.2 Fix failures
- Detection and fix are separate systems with different search strings
- `_COMPAT_PATTERNS` in `test_env.py` uses `"search": "datetime.UTC"` but the actual code pattern is `from datetime import UTC` — completely different string
- Fix endpoint only searches within the module directory, not across the project. Of course not accross the prohect. that would be stupid... a module is no a module for nothing...
- No verification that a fix actually resolved the detected issue

### 1.3 Lifecycle failures
- `executor.py` and `wizard.py` have different auto-mark-done logic
- Read-only steps (scan, guide, update_ci) return `ok: True` and get auto-marked done even when they show findings that need attention
- `_check_already_done` marks steps done based on file existence, not correctness
- `can_apply: False` steps get marked done without user action
- No state machine — steps are either done or not, with no FAILED or NEEDS_ATTENTION states

### 1.4 Scope failures
- Each module is analyzed in isolation
- No awareness that `src/ui/web` depends on `src/core` at import time
- A module can "pass" all scans and have its plan completed while its transitive dependencies contain incompatible code
- The core module completed its entire version plan without detecting `from datetime import UTC` in 14+ files

---

## 2. Design Goals

### 2.1 Correctness over speed
Every detection must be provably correct. No regex guessing. AST parsing gives exact node types, exact locations, and zero false positives from strings/comments.

### 2.2 Detection-fix unity
A detection and its fix are ONE object. You cannot have a detection without a fix. You cannot have a fix without a detection. The fix uses the EXACT information from the detection — same file, same line, same AST node. No separate search string.

### 2.3 Verification closed loop
Every fix must prove itself:
1. Detect → record finding
2. Fix → transform code
3. Re-detect → finding must be gone
4. Import check → file must still be importable
5. Only then → mark as fixed

### 2.4 Project-wide awareness
The system understands the full dependency graph:
- Module A imports Module B imports Module C
- An incompatibility in C affects A and B
- Fixing C's incompatibility resolves A and B's transitive failures
- The plan for A shows: "blocked by C — fix C first"

### 2.5 Honest state
Step state reflects reality:
- PENDING → not started
- RUNNING → in progress
- PASSED → verified success
- FAILED → verified failure
- NEEDS_ATTENTION → findings exist, user must act
- BLOCKED → depends on another step/module
- Never auto-mark done on failure. Never.

### 2.6 All languages, all directions
- 10 languages: Python, JavaScript, TypeScript, Go, Rust, Ruby, Java, C#/.NET, PHP, Elixir
- Upgrade: moving to a newer version (can use new features, remove backports)
- Downgrade: moving to an older version (must replace new features with backports)
- Same architecture for all — pluggable language backends

---

## 3. System Layers

```
┌─────────────────────────────────────────────────────────┐
│                    USER INTERFACE                        │
│         Web UI  ·  CLI  ·  API endpoints                │
├─────────────────────────────────────────────────────────┤
│                   ORCHESTRATION                          │
│    Plan Engine  ·  Step Lifecycle  ·  Batch Runner       │
├─────────────────────────────────────────────────────────┤
│                   ANALYSIS ENGINE                        │
│  AST Parser  ·  Import Resolver  ·  Dep Analyzer        │
├─────────────────────────────────────────────────────────┤
│                    FIX ENGINE                            │
│  Transform Pipeline  ·  Verification  ·  Rollback       │
├─────────────────────────────────────────────────────────┤
│                  FEATURE DATABASE                        │
│  Per-language feature entries  ·  Fix strategies         │
│  Edge cases  ·  Backport registry                       │
├─────────────────────────────────────────────────────────┤
│                 LANGUAGE BACKENDS                         │
│  Python · JS/TS · Go · Rust · Ruby · Java · C# · PHP · Elixir │
└─────────────────────────────────────────────────────────┘
```

### 3.1 Feature Database (bottom layer)
The foundation. Every version-specific language feature has an entry:

```yaml
- id: python.datetime.UTC
  language: python
  feature_name: datetime.UTC
  introduced: "3.11"
  removed: null
  category: stdlib
  detection:
    type: ast
    node: ImportFrom
    match:
      module: datetime
      names: [UTC]
    also_detect:
      - type: ast
        node: Attribute
        match:
          value: datetime
          attr: UTC
  fix:
    strategy: replace_import_and_usages
    transforms:
      - find_import: "from datetime import UTC"
        replace_import: "from datetime import timezone"
      - find_usage: "UTC"
        replace_usage: "timezone.utc"
        scope: "imported_name"  # only replace UTC that came from this import
    backport: null
  verification:
    re_detect: true  # after fix, re-run detection — must find 0 matches
    import_check: true  # after fix, file must still be importable
  edge_cases:
    - "UTC imported alongside other names: from datetime import datetime, UTC"
    - "UTC used as type annotation only (TYPE_CHECKING block)"
    - "UTC aliased: from datetime import UTC as utc"
  test:
    before: |
      from datetime import UTC, datetime
      now = datetime.now(UTC)
    after: |
      from datetime import timezone, datetime
      now = datetime.now(timezone.utc)
```

This is NOT a regex pattern. This is a structured entry that tells the AST detection engine exactly what to look for, tells the fix engine exactly what to transform, and tells the verification engine how to confirm the fix worked.

1000+ entries like this across all 10 languages.

### 3.2 Language Backends
Each language provides:

| Component | Purpose |
|-----------|---------|
| AST Parser | Parse source files into AST nodes |
| Node Matcher | Match feature database detection rules against AST |
| Import Resolver | Trace import/require/use chains across files |
| Fix Transformer | Apply fix transforms to AST nodes |
| Code Emitter | Write modified AST back to source code |
| Dep Analyzer | Check package registry (PyPI, npm, etc.) for version support |

Each backend implements the same interface. The orchestration layer doesn't know which language it's working with — it just calls the backend.

**Python backend**:
- Parser: `ast` stdlib module
- Import resolver: follow `import` / `from X import Y` statements, resolve relative imports, handle `__init__.py`
- Dep analyzer: PyPI JSON API for `requires-python`

**JavaScript/TypeScript backend**:
- Parser: tree-sitter-javascript / tree-sitter-typescript
- Import resolver: follow `import`/`require`/`export`, resolve `node_modules`, handle `index.js`
- Dep analyzer: npm registry API for `engines.node`

**Go backend**:
- Parser: `go/parser` via subprocess or tree-sitter-go
- Import resolver: follow `import` statements, resolve module paths
- Dep analyzer: `go.mod` version constraints

(Similar for Rust, Ruby, Java, C#, PHP, Elixir — detailed in their respective language module documents)

### 3.3 Analysis Engine
Sits above the language backends. Provides:

**AST Analysis**:
- Takes a file → parses to AST via language backend
- Matches feature database entries against AST nodes
- Returns findings: `[{feature_id, file, line, col, ast_node, severity}]`

**Import Chain Resolution**:
- Takes a module entry point → traces all imports recursively
- Builds a dependency graph of files
- Identifies transitive incompatibilities
- Answers: "if I import module A, what incompatible features will I hit?"

**Dependency Analysis**:
- Takes a package manifest (requirements.txt, package.json, etc.)
- Queries package registries for version support
- Identifies packages that don't support the target version
- Suggests alternative versions or replacements

### 3.4 Fix Engine
Applies fixes and verifies them:

**Transform Pipeline**:
1. Read the finding from the analysis engine
2. Look up the fix strategy from the feature database entry
3. Parse the file's AST (or reuse cached AST)
4. Apply transforms to the AST nodes identified by the finding
5. Emit the modified source code
6. Write the file

**Verification**:
1. Re-run the detection on the modified file
2. The original finding must no longer match
3. Run an import check (language-specific) — file must still parse/import
4. If verification fails → rollback the fix, report failure

**Rollback**:
- Before any fix, capture the original file content
- If verification fails, restore the original
- Never leave a file in a half-fixed state

### 3.5 Orchestration Layer
Manages the plan execution flow:

**Plan Engine**:
- Reads the version plan from project.yml
- Generates steps based on what the analysis engine finds
- Steps are dynamic — not a static recipe, but generated from actual findings

**Step Lifecycle**:
- State machine: PENDING → RUNNING → PASSED/FAILED/NEEDS_ATTENTION/BLOCKED
- Only PASSED marks done in project.yml
- FAILED stops execution, shows what failed and why
- NEEDS_ATTENTION shows findings, waits for user
- BLOCKED shows what's blocking (another module, a dependency)

**Batch Runner**:
- Runs multiple steps in sequence
- Stops on FAILED or BLOCKED
- NEEDS_ATTENTION can be configured to stop or continue
- Same logic for individual and batch execution — ONE code path

### 3.6 User Interface Layer
Web UI, CLI, and API endpoints all call the same orchestration layer:

**API**:
- `POST /api/compat/analyze` — run analysis on a module
- `POST /api/compat/fix` — apply a specific fix
- `POST /api/compat/verify` — verify a fix worked
- `POST /api/compat/plan` — generate/get a version plan
- `POST /api/compat/step/execute` — execute a plan step
- `GET /api/compat/features` — browse the feature database
- `GET /api/compat/import-graph` — get import dependency graph

**Web UI**:
- Plan modal with honest step states (colored: green/red/yellow/grey)
- Fix modal showing exact code before/after with AST-highlighted changes
- Import graph visualization
- One-click fix with verification feedback
- Batch execution with real-time progress

**CLI**:
- `controlplane compat analyze <module> --target <version>`
- `controlplane compat fix <module> --target <version>`
- `controlplane compat plan <module> --target <version>`

---

## 4. Data Flow

### 4.1 Analysis flow
```
User requests analysis for module "web" targeting Python 3.8
    │
    ▼
Orchestration: load module config from project.yml
    │
    ▼
Analysis Engine: get all .py files in src/ui/web/
    │
    ▼
Import Resolver: trace all imports from web's files
    → web/routes/backup/archive.py imports src.core.models.action
    → src.core.models.action imports datetime.UTC
    → record: transitive dependency on datetime.UTC via core
    │
    ▼
AST Parser: parse each file (both direct and transitive)
    │
    ▼
Node Matcher: match feature database entries against AST nodes
    → MATCH: src/core/models/action.py:11 — ImportFrom(datetime, [UTC]) — python.datetime.UTC
    → MATCH: src/core/models/state.py:14 — ImportFrom(datetime, [UTC]) — python.datetime.UTC
    → MATCH: src/core/engine/executor.py:18 — ImportFrom(datetime, [UTC]) — python.datetime.UTC
    → ... 14 more matches in src/core/
    → MATCH: src/ui/web/routes/metrics/health.py:6 — ImportFrom(datetime, [UTC]) — python.datetime.UTC
    │
    ▼
Results: 15 findings, 14 in src/core/ (transitive), 1 in src/ui/web/ (direct)
    → Summary: "15 files use datetime.UTC (Python 3.11+). 14 are in src/core (dependency)."
    → Recommendation: "Fix src/core first, then src/ui/web"
```

### 4.2 Fix flow
```
User clicks "Fix all datetime.UTC occurrences"
    │
    ▼
Fix Engine: for each finding
    │
    ▼
    1. Read feature database entry for python.datetime.UTC
    2. Get fix strategy: replace_import_and_usages
    3. Parse file AST
    4. Find ImportFrom node matching (datetime, [UTC])
    5. Transform: replace UTC with timezone, add timezone.utc usage
    6. Emit modified source
    7. Write file
    │
    ▼
Verification: for each fixed file
    │
    ▼
    1. Re-parse AST
    2. Re-run detection for python.datetime.UTC
    3. Finding count: 0 → PASS
    4. Import check: python -c "import src.core.models.action" → PASS
    5. Mark finding as FIXED
    │
    ▼
Results: "15/15 files fixed and verified"
```

### 4.3 Step lifecycle flow
```
Step: "Scan for incompatible features"
    │
    ▼
State: PENDING → RUNNING
    │
    ▼
Analysis Engine runs, finds 15 incompatible features
    │
    ▼
Findings exist → State: NEEDS_ATTENTION
    → NOT marked done
    → User sees: "15 incompatible features found"
    → User can: fix them, review them, skip
    │
    ▼
User clicks "Fix all"
    │
    ▼
Fix Engine runs, fixes 15/15, verification passes
    │
    ▼
Re-scan: 0 incompatible features found
    │
    ▼
State: PASSED → marked done in project.yml
```

---

## 5. File Structure

```
src/core/services/compat/                    ← NEW top-level service
├── __init__.py
├── README.md
│
├── database/                                ← Feature database
│   ├── __init__.py
│   ├── schema.py                            ← Entry data model
│   ├── loader.py                            ← Load entries from YAML/JSON
│   ├── registry.py                          ← Global feature registry
│   └── entries/                             ← Per-language feature entries
│       ├── python/
│       │   ├── stdlib.yml                   ← datetime.UTC, tomllib, etc.
│       │   ├── syntax.yml                   ← match/case, walrus, etc.
│       │   ├── typing.yml                   ← X|Y union, generics, etc.
│       │   └── builtins.yml                 ← str.removeprefix, dict|, etc.
│       ├── javascript/
│       │   ├── es2015.yml
│       │   ├── es2016.yml
│       │   ├── es2017.yml
│       │   └── ...
│       ├── typescript/
│       ├── go/
│       ├── rust/
│       ├── ruby/
│       ├── java/
│       ├── csharp/
│       ├── php/
│       └── elixir/
│
├── analysis/                                ← Analysis engine
│   ├── __init__.py
│   ├── engine.py                            ← Main analysis orchestrator
│   ├── import_resolver.py                   ← Cross-file import tracing
│   ├── dep_analyzer.py                      ← Package registry queries
│   └── finding.py                           ← Finding data model
│
├── fix/                                     ← Fix engine
│   ├── __init__.py
│   ├── engine.py                            ← Main fix orchestrator
│   ├── transformer.py                       ← AST transforms
│   ├── verifier.py                          ← Post-fix verification
│   └── rollback.py                          ← Rollback on failure
│
├── backends/                                ← Language backends
│   ├── __init__.py
│   ├── base.py                              ← Abstract backend interface
│   ├── python_backend.py
│   ├── javascript_backend.py
│   ├── typescript_backend.py
│   ├── go_backend.py
│   ├── rust_backend.py
│   ├── ruby_backend.py
│   ├── java_backend.py
│   ├── csharp_backend.py
│   ├── php_backend.py
│   └── elixir_backend.py
│
├── lifecycle/                               ← Step lifecycle & orchestration
│   ├── __init__.py
│   ├── state_machine.py                     ← Step state transitions
│   ├── plan_engine.py                       ← Plan generation & management
│   ├── batch_runner.py                      ← Batch execution
│   └── step_types.py                        ← Step type definitions
│
└── edge_cases/                              ← Edge case handling
    ├── __init__.py
    ├── conditional_imports.py               ← try/except imports
    ├── type_checking.py                     ← TYPE_CHECKING blocks
    ├── dynamic_imports.py                   ← importlib usage
    ├── star_imports.py                      ← from X import *
    ├── reexports.py                         ← __all__ handling
    └── version_gates.py                     ← sys.version_info checks
```

---

## 6. What Gets Replaced

| v1 Component | Location | Replacement |
|---|---|---|
| `_RUNTIME_FEATURES` | `module_intel.py` | `database/entries/python/*.yml` |
| `_ANNOTATION_FEATURES` | `module_intel.py` | `database/entries/python/typing.yml` |
| `_COMPAT_PATTERNS` | `test_env.py` | `database/entries/python/*.yml` (fix section) |
| `_REWRITE_GUIDES` | `code_scanner.py` | `database/entries/python/*.yml` (fix section) |
| `handle_scan_incompatible_features` | `code_scanner.py` | `analysis/engine.py` |
| `handle_guide_incompatible_syntax` | `code_scanner.py` | `analysis/engine.py` + `fix/engine.py` |
| `handle_add_future_annotations` | `code_scanner.py` | `fix/transformer.py` |
| `handle_update_ci_matrix` | `code_scanner.py` | `analysis/engine.py` (CI-specific analyzer) |
| `handle_check_dep_compat_pypi` | `dep_checker.py` | `analysis/dep_analyzer.py` |
| `handle_setup_test_env` | `test_env.py` | `lifecycle/step_types.py` |
| `handle_run_isolated_tests` | `test_env.py` | `lifecycle/step_types.py` |
| `execute_step` | `executor.py` | `lifecycle/plan_engine.py` |
| `_mark_step_done` | `executor.py` | `lifecycle/state_machine.py` |
| `_check_already_done` | `executor.py` | Removed — state machine handles this |
| `wizard_batch` | `wizard.py` | `lifecycle/batch_runner.py` |
| `wizard_subprocess` | `wizard.py` | `lifecycle/step_types.py` |
| `wizard_dep_scan` | `wizard.py` | `analysis/dep_analyzer.py` + `lifecycle/batch_runner.py` |
| `posture_module_compat_fix` | `posture.py` | `fix/engine.py` via new API routes |
| `posture_module_step_execute` | `posture.py` | `lifecycle/plan_engine.py` via new API routes |
| `posture_module_wizard` | `posture.py` | `lifecycle/batch_runner.py` via new API routes |

---

## 7. Interfaces Between Layers

### 7.1 Language Backend Interface

Every language backend implements:

```python
class LanguageBackend(ABC):
    """Abstract interface for language-specific operations."""

    @abstractmethod
    def parse_file(self, path: Path) -> ASTNode:
        """Parse a source file into an AST."""

    @abstractmethod
    def match_feature(self, ast: ASTNode, detection_rule: DetectionRule) -> list[Finding]:
        """Match a feature database detection rule against an AST."""

    @abstractmethod
    def resolve_imports(self, file_path: Path, project_root: Path) -> list[ImportEdge]:
        """Trace imports/requires/uses from a file. Returns edges in the import graph."""

    @abstractmethod
    def apply_transform(self, ast: ASTNode, finding: Finding, fix_rule: FixRule) -> ASTNode:
        """Apply a fix transform to the AST at the finding's location."""

    @abstractmethod
    def emit_source(self, ast: ASTNode) -> str:
        """Convert modified AST back to source code."""

    @abstractmethod
    def check_importable(self, file_path: Path) -> bool:
        """Verify a file can still be imported/compiled after modification."""

    @abstractmethod
    def query_package_registry(self, package: str, target_version: str) -> DepResult:
        """Check if a package supports the target language version."""
```

### 7.2 Feature Database Entry Schema

```python
@dataclass
class FeatureEntry:
    id: str                          # "python.datetime.UTC"
    language: str                    # "python"
    feature_name: str                # "datetime.UTC"
    introduced: str                  # "3.11"
    removed: str | None              # null for still-present features
    deprecated: str | None           # version when deprecated
    category: str                    # "stdlib" | "syntax" | "typing" | "builtin"
    description: str                 # human-readable description
    detection: list[DetectionRule]   # how to find this in AST
    fix: FixStrategy                 # how to fix it
    verification: VerificationRule   # how to verify the fix
    edge_cases: list[str]            # documented edge cases
    test: TestCase                   # before/after code proving fix works
    direction: str                   # "downgrade" | "upgrade" | "both"
```

### 7.3 Finding Data Model

```python
@dataclass
class Finding:
    feature_id: str                  # "python.datetime.UTC"
    file: str                        # "src/core/models/action.py"
    line: int                        # 11
    col: int                         # 0
    source_line: str                 # "from datetime import UTC, datetime"
    ast_node_type: str               # "ImportFrom"
    severity: str                    # "error" | "warning" | "info"
    is_transitive: bool              # True if found via import chain
    imported_by: str | None          # "src/ui/web/routes/backup/archive.py"
    fix_available: bool              # True
    fix_strategy: str                # "replace_import_and_usages"
    status: str                      # "detected" | "fixed" | "verified" | "failed"
```

### 7.4 Step State Machine

```python
class StepState(Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    NEEDS_ATTENTION = "needs_attention"
    BLOCKED = "blocked"
    SKIPPED = "skipped"

# Valid transitions:
# PENDING → RUNNING
# RUNNING → PASSED | FAILED | NEEDS_ATTENTION | BLOCKED
# NEEDS_ATTENTION → RUNNING (user chose to fix)
# NEEDS_ATTENTION → SKIPPED (user chose to skip)
# BLOCKED → PENDING (blocker resolved)
# FAILED → RUNNING (user retries)
#
# Only PASSED writes done:true to project.yml
# FAILED never marks done — NEVER
```

---

## 8. Migration Strategy

### Phase 1: Build new system alongside v1
- New code in `src/core/services/compat/`
- Old code stays in `src/core/services/module_upgrade/`
- New API routes under `/api/compat/`
- Old routes stay under `/api/posture/`

### Phase 2: Feature parity
- New system handles everything v1 handles
- All v1 test cases pass on new system
- All v1 bugs are resolved in new system

### Phase 3: Switchover
- UI routes point to new system
- CLI routes point to new system
- Old system removed

### Phase 4: Extended coverage
- 1000+ feature database entries
- 100+ edge case tests
- All 10 languages fully covered

---

## 9. Open Questions

These need discussion before proceeding to document 2:

1. **Feature database format**: YAML files (human-readable, easy to contribute) or Python dataclasses (type-safe, IDE support)? Or both — YAML source of truth, loaded into dataclasses at runtime?

2. **AST caching**: Parse each file once, cache the AST, reuse across multiple feature checks? Or re-parse per check? Caching is faster but uses more memory.

3. **Import resolver depth**: How deep to follow transitive imports? Unlimited? Or configurable max depth? Circular import handling?

4. **Fix granularity**: Fix one finding at a time, or batch all findings in a file? Per-file or per-project?

5. **project.yml schema**: Keep current `version_plan.checklist` structure or redesign? Current structure has `done: true/false` — new system needs richer states.

6. **Concurrency**: Should the analysis engine be able to analyze multiple files in parallel? Multiple modules?
