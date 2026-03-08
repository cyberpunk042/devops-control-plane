# Scripts System — Milestone 7: Data Layer Leak Detection

> **Status**: Planning — Iteration 1
> **Parent**: `.agent/plans/scripts-system.md`
> **Milestone**: M7 — Data Layer Leaks
> **Depends on**: M1 (Execution Framework), M6 (code_hygiene patterns)
> **Unlocks**: Architectural boundary enforcement, refactoring roadmap

---

## 0. What This Milestone Delivers

After M7 is complete:

1. A **Data Layer Leak Audit** template script exists at `audit/data_layer_leaks.py`
2. It detects **4 tiers of data leaks** — from catastrophic (inline data in wrong place)
   to advisory (lateral service coupling)
3. It produces a **layered markdown report** with severity tiers, dependency flow
   visualization, and an actionable fix checklist
4. It uses the same execution framework (M1) and follows the same script template
   patterns as `code_hygiene.py` and `route_quality.py`

**What you can do after M7**: Run `controlplane scripts run audit/data_layer_leaks`
and see exactly where data lives that shouldn't, who imports what from where, and
what the refactoring priority order is.

---

## 1. The Problem This Script Solves

### Data layer violations are invisible until they bite

In a layered architecture, data belongs in specific layers:
- **Static catalogs / registries** → `core/data/`
- **Domain models / schemas** → `core/models/`
- **Persistence I/O** → `core/persistence/`
- **Config structures** → `core/config/`

But laziness, urgency, and organic growth cause data to leak:
- A route handler hardcodes a 20-entry dict instead of reading from a catalog
- A service defines a 54-item constant set that should be in `core/data/`
- A CLI command constructs domain objects directly

These leaks cause:
- **Duplication**: the same data defined in 3 places, drifting silently
- **Untestability**: data embedded in function bodies can't be unit-tested
- **Coupling**: when data lives in the wrong layer, refactoring breaks everything
- **Invisibility**: no one knows the canonical source of truth

### Real data from THIS codebase (discovery scan, March 2026)

| Tier | Count | Example |
|------|-------|---------|
| **T1 — Inline data** | 20+ functions with dicts ≥ 5 keys | `wizard_detect()` has 26-key dict on L338 |
| **T2 — Wrong-layer definitions** | 20+ module constants in services | `peek.py` has 54-item set `_COMMON_KEYWORDS` |
| **T3 — Import direction violations** | 1 (clean!) | `audit.py` imports from persistence directly |
| **T4 — Lateral service coupling** | 211 imports, 104 unique pairs | `backup → content` (12), `wizard → devops` (10) |

---

## 2. Architecture: The Layer Model

### 2.1 Layer definitions (auto-detected)

The script auto-detects layers from the directory structure:

```
Layer 0 — DATA (canonical home for data):
  src/core/data/          → catalogs, templates, registries
  src/core/models/        → domain models (dataclasses, Pydantic)
  src/core/persistence/   → file I/O, state serialization
  src/core/config/        → configuration structures

Layer 1 — SERVICES (business logic):
  src/core/services/      → orchestration, processing
  src/core/use_cases/     → high-level operations

Layer 2 — UI (presentation):
  src/ui/web/routes/      → Flask route handlers
  src/ui/cli/             → Click CLI commands
  src/ui/web/templates/   → Jinja templates (not Python-scanned)

Layer X — ADAPTERS (external integrations):
  src/adapters/           → email, SMS, Reddit, etc.
```

### 2.2 Allowed dependency directions

```
  UI ─────→ Use Cases ─→ Services ─→ Models / Data / Persistence
  │                        │
  │                        ├──→ Adapters (for external calls)
  │                        │
  └────────────────────────┘
         NOT ALLOWED:
         UI → Data (skip services)
         UI → Persistence (skip services)
         UI → Models (constructing objects)
         Services/X → Services/Y internals (lateral)
```

### 2.3 User-configurable layer map

The script accepts a `--layers` param or reads from a `layers.yml` config.
Default layers are auto-detected from directory structure:

```yaml
# Auto-generated layer map (overridable)
data:
  - core/data
  - core/models
  - core/persistence
  - core/config
services:
  - core/services
  - core/use_cases
ui:
  - ui/web/routes
  - ui/cli
adapters:
  - adapters
```

---

## 3. Leak Taxonomy — 4 Tiers

### 3.1 Tier 1: Inline Data (🔴 Critical)

**What**: Data literals (dict, list, set) defined **inside** functions or methods
in non-data-layer files, above a significance threshold.

**Why it matters**: This data is invisible, untestable, and unreusable. It's the
worst kind of leak because it has no name, no module, no way for anyone to find it.

**Detection strategy** (AST):

```python
for node in ast.walk(tree):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        for child in ast.walk(node):
            if isinstance(child, ast.Dict) and len(child.keys) >= threshold:
                # Found inline data
```

**Smart heuristics** — not all inline dicts are leaks:

| Pattern | Classification | Reason |
|---------|---------------|--------|
| Dict with ≥ 5 keys, all string keys | 🔴 **Data leak** | Looks like a mapping/catalog |
| Dict assigned to `UPPER_CASE` local | 🔴 **Data leak** | Named constant in wrong scope |
| Dict returned as API response | ⚪ **Response construction** | Building JSON payloads is expected |
| Dict passed as kwargs to a function | ⚪ **Config passing** | Structural, not data |
| Dict in a `return jsonify({...})` | ⚪ **Response** | API response building |
| Dict assigned to a descriptive var AND all values are str/int/bool | 🔴 **Data leak** | Static lookup table |
| Dict with computed values (function calls as values) | 🟡 **Maybe** | It's building a result, not storing data |
| List of strings ≥ 10 items | 🔴 **Data leak** | Probably an enum/whitelist |
| Set of strings ≥ 5 items | 🔴 **Data leak** | Probably a filter/allowlist |

**Key insight**: The heuristic isn't about hiding things — ALL inline data above
threshold is shown. The classification just determines severity coloring. The user
sees everything; the script tells them what's likely noise vs. likely real.

**AST markers for response construction detection**:
- Parent node is `ast.Return` → likely response
- Value argument to `jsonify()`, `json.dumps()`, `Response()` → response
- Assigned to variable then immediately returned → likely response

### 3.2 Tier 2: Wrong-Layer Definitions (🟠 Major)

**What**: Properly named module-level constants, dataclasses, or TypedDicts that
live in the wrong package — typically in `services/` instead of `data/` or `models/`.

**Detection strategy** (AST):

```python
for node in ast.iter_child_nodes(tree):  # top-level only
    # Module-level UPPER_CASE dict/list/set assignments
    if isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id.isupper():
                if isinstance(node.value, (ast.Dict, ast.List, ast.Set)):
                    if file_layer not in data_layers:
                        # → Wrong-layer definition
    
    # Dataclass / TypedDict outside models/
    if isinstance(node, ast.ClassDef):
        has_dataclass = any(...)
        inherits_typeddict = any(...)
        if (has_dataclass or inherits_typeddict) and file_layer != 'core-models':
            # → Wrong-layer type definition
```

**What's NOT a violation**:
- Small constants (`TIMEOUT = 30`, `MAX_RETRIES = 3`) — these are config, not data
- Constants in `__init__.py` that are re-exports
- Private helpers (`_FOO = ...`) with ≤ 2 items — too small to matter

**Suggested target** — where should each leak move?

| Current location | Data type | Suggested home |
|-----------------|-----------|---------------|
| `services/peek.py` `_COMMON_KEYWORDS` (54 items) | Set of strings | `core/data/catalogs/code_keywords.py` |
| `services/peek.py` `_CODE_EXTS` (41 items) | Set of extensions | `core/data/catalogs/file_extensions.py` |
| `services/content/crypto.py` `CODE_EXTS` (41 items) | Set of extensions | `core/data/catalogs/file_extensions.py` ← **duplicate!** |
| `services/run_tracker.py` `RUN_TYPES` (16 items) | Dict mapping | `core/data/catalogs/run_types.py` |

**Key detection**: when the same data appears in multiple places (like `CODE_EXTS`
in both `peek.py` and `crypto.py`), the script should flag it as a **duplication
leak** — the worst kind of Tier 2 because it proves the data has no canonical home.

### 3.3 Tier 3: Import Direction Violations (🟡 Moderate)

**What**: A module in a higher layer imports directly from a lower data layer,
skipping the service layer.

**Detection strategy** (AST):

```python
for node in ast.walk(tree):  # walk all depths (catches lazy imports)
    if isinstance(node, ast.ImportFrom) and node.module:
        src_layer = classify_file(filepath)
        tgt_layer = classify_import(node.module)
        if is_violation(src_layer, tgt_layer):
            # → Import direction violation
```

**Violation matrix**:

| Source → Target | Verdict | Reason |
|----------------|---------|--------|
| UI → Data | 🟡 **Violation** | Should go through services |
| UI → Models | 🟡 **Soft violation** | Acceptable for type hints, not for construction |
| UI → Persistence | 🟡 **Violation** | Should go through services |
| Services → Data | ⚪ **OK** | Services are allowed to read data |
| Services → Models | ⚪ **OK** | Services operate on models |
| Services → Persistence | ⚪ **OK** | Services can persist |
| Adapters → Services | ⚪ **OK** | Adapters call services |
| UI → Services | ⚪ **OK** | The happy path |

**Special case**: Imports inside `TYPE_CHECKING` blocks are always OK — they're
for type annotations only, not runtime dependency.

### 3.4 Tier 4: Lateral Service Coupling (🟢 Advisory)

**What**: Services importing from sibling service sub-packages' internals.

**Detection strategy** (AST):

```python
src_pkg = get_service_subpackage(filepath)  # e.g., "docker"
tgt_pkg = get_service_subpackage(import_target)  # e.g., "generators"
if src_pkg != tgt_pkg:
    # → Lateral coupling
```

**Severity modifiers**:
- Importing a **public function** from a sibling → 🟢 advisory
- Importing a **private** (`_name`) from a sibling → 🟡 moderate
- **Circular** mutual imports between two packages → 🟠 major
- More than 5 imports from same sibling → 🟡 suggests missing abstraction

**Not violations**:
- Importing from `__init__.py` of a sibling (public API)
- Importing shared utils (`event_bus`, `config_ops`)

**What the report shows**: Coupling pairs sorted by import count, with
a dependency graph showing which services are tightly coupled.

---

## 4. Smart Detection: Separating Signal from Noise

### 4.1 Response construction detector

The biggest source of Tier 1 false positives is API response dicts. The script
needs to distinguish:

```python
# This is a RESPONSE (not a leak):
return jsonify({
    "ok": True,
    "status": "running",
    "metrics": {...}
})

# This is a LEAK (data that should be elsewhere):
TOOL_NAMES = {"docker": "Docker Engine", "k8s": "Kubernetes", ...}
```

**Heuristic**: Trace the dict's usage:
1. Is it the argument to `jsonify()`, `json.dumps()`, `Response()`? → **response**
2. Is it the return value of the function? → **response** (likely)
3. Does it contain computed values (function calls, f-strings)? → **constructed result**
4. Are all values static literals (strings, ints, bools)? → **data leak**
5. Is it assigned to an `UPPER_CASE` variable? → **data leak** (certain)

### 4.2 Duplication detector

When two module-level constants in different files contain overlapping data:

```python
# In peek.py
_CODE_EXTS = {".py", ".js", ".ts", ...}

# In crypto.py  
CODE_EXTS = {".py", ".js", ".ts", ...}
```

The script should:
1. Hash the literal content of each constant
2. Group constants with identical or >80% overlapping values
3. Flag duplicates as **duplication leaks** — proof that data has no canonical home

### 4.3 Structural pattern exclusions

Some patterns look like data but are architectural boilerplate:

| Pattern | Exclusion reason |
|---------|-----------------|
| `__all__ = [...]` | Re-export list, not data |
| `Blueprint(...)` definitions | Framework boilerplate |
| `click.group()` definitions | Framework boilerplate |
| `logging.getLogger(__name__)` | Infrastructure |
| Small dicts (≤ 2 keys) | Config, not data |
| `TYPE_CHECKING` imports | Type hints only |

---

## 5. File Inventory

### 5.1 New files

| File | Purpose | Lines (est) |
|------|---------|-------------|
| `audit/data_layer_leaks.py` | Main script — args, orchestration, report | ~600 |
| `audit/layer_analyzer.py` | AST analysis — imports, constants, inline data | ~400 |

### 5.2 Existing files (no changes)

| File | Why no changes |
|------|---------------|
| `audit/init_analyzer.py` | Different concern (init file hygiene) |
| `audit/doc_validator.py` | Different concern (doc freshness) |
| `lib/` helpers | May reuse `report_formatter` if it exists |

---

## 6. Data Models

### 6.1 LayerConfig

```python
@dataclass
class LayerConfig:
    """Defines the architectural layer map."""
    name: str                           # "data", "services", "ui", "adapters"
    packages: list[str]                 # ["core/data", "core/models", ...]
    allowed_imports: list[str]          # which layers this layer may import from
```

### 6.2 InlineDataLeak (Tier 1)

```python
@dataclass
class InlineDataLeak:
    """Data literal found inside a function body."""
    file: str
    function_name: str
    lineno: int
    data_type: str                      # "dict", "list", "set"
    item_count: int                     # number of keys/elements
    classification: str                 # "data_leak", "response", "constructed"
    reason: str                         # why it was classified this way
    assigned_to: str | None             # variable name if assigned
    is_upper_case: bool                 # UPPER_CASE = True → almost certainly data
```

### 6.3 WrongLayerDefinition (Tier 2)

```python
@dataclass
class WrongLayerDefinition:
    """Module-level constant or type defined outside its canonical layer."""
    file: str
    symbol_name: str
    lineno: int
    data_type: str                      # "Dict", "List", "Set", "dataclass", "TypedDict"
    item_count: int
    current_layer: str                  # "core-services"
    suggested_layer: str                # "core-data"
    suggested_path: str                 # "core/data/catalogs/code_keywords.py"
    duplicates: list[str]               # other files with overlapping content
```

### 6.4 ImportViolation (Tier 3)

```python
@dataclass
class ImportViolation:
    """Import that crosses an architectural boundary."""
    file: str
    lineno: int
    import_module: str                  # "src.core.persistence.audit"
    imported_names: list[str]           # ["AuditWriter"]
    source_layer: str                   # "ui-routes"
    target_layer: str                   # "core-persistence"
    is_lazy: bool                       # True if inside a function body
    is_type_checking: bool              # True if inside TYPE_CHECKING block
    severity: str                       # "violation", "soft_violation"
```

### 6.5 LateralCoupling (Tier 4)

```python
@dataclass
class LateralCoupling:
    """Service importing from a sibling service."""
    file: str
    lineno: int
    source_package: str                 # "docker"
    target_package: str                 # "generators"
    import_module: str
    imported_names: list[str]
    is_private: bool                    # imports _private names
    severity: str                       # "advisory", "moderate", "major"
```

### 6.6 LayerAuditResult (top-level)

```python
@dataclass
class LayerAuditResult:
    """Complete results of a data layer leak scan."""
    project_root: str
    timestamp: str
    files_scanned: int
    layers: dict[str, int]              # layer_name → file count
    inline_leaks: list[InlineDataLeak]
    wrong_layer_defs: list[WrongLayerDefinition]
    import_violations: list[ImportViolation]
    lateral_couplings: list[LateralCoupling]
    duplicates: list[tuple[str, list[str]]]  # (content_hash, [file1, file2, ...])
```

---

## 7. Report Structure

### 7.1 Smart report sections

```
# Data Layer Leak Audit

> Generated: YYYY-MM-DD HH:MM UTC  |  Style: smart

## Table of Contents
1. Executive Summary
2. Architecture Map (detected layers)
3. 🔴 Inline Data Leaks (Tier 1)
4. 🟠 Wrong-Layer Definitions (Tier 2)
5. 🔄 Data Duplication Map
6. 🟡 Import Direction Violations (Tier 3)
7. 🟢 Lateral Service Coupling (Tier 4)
8. Dependency Flow Diagram
9. Fix Checklist
```

### 7.2 Executive Summary

```markdown
## Executive Summary

> Your data architecture is **fair**. 45 data leaks detected across 4 tiers.
> 20 inline data blobs in function bodies (5 are real leaks, 15 are response/result
> construction). 20 module constants live in services instead of core/data.
> 2 duplication groups prove missing canonical homes. 1 import boundary violation.
> 211 lateral service couplings (advisory).

| Tier | Count | Severity |
|------|-------|----------|
| 🔴 Inline data (in functions) | 20 (5 real, 15 structural) | Critical |
| 🟠 Wrong-layer definitions | 20 | Major |
| 🔄 Duplicated data | 2 groups | Major |
| 🟡 Import violations | 1 | Moderate |
| 🟢 Lateral coupling | 211 (104 pairs) | Advisory |
```

### 7.3 Tier 1 section — show everything, classify everything

```markdown
## 🔴 Inline Data Leaks (Tier 1)

> Data literals found inside function bodies. Sorted by item count.
> Classification: 🔴 = data leak, ⚪ = response/result construction.

### Real Leaks

| File | Function | Type | Items | Assigned To | Why it's a leak |
|------|----------|------|-------|-------------|-----------------|
| services/wizard/detect.py | wizard_detect() | Dict | 26 | (inline) | All static str keys/values, not a return |
| services/detection.py | detect_language() | Dict | 20 | (inline) | Extension→language mapping, belongs in data/ |

### Response / Result Construction (not leaks)

| File | Function | Type | Items | Why it's OK |
|------|----------|------|-------|-------------|
| services/git/ops.py | git_status() | Dict | 16 | Returned as API result |
| services/k8s/detect.py | k8s_status() | Dict | 16 | Returned as detection result |
```

### 7.4 Duplication Map section

```markdown
## 🔄 Data Duplication Map

> Same or overlapping data found in multiple files. Proves these need a canonical home.

### Group 1: Code File Extensions (41 items, 95% overlap)

| File | Symbol | Items | Overlap |
|------|--------|-------|---------|
| `services/peek.py` | `_CODE_EXTS` | 41 | baseline |
| `services/content/crypto.py` | `CODE_EXTS` | 41 | 95% |

Suggested canonical home: `core/data/catalogs/file_extensions.py`
```

### 7.5 Dependency Flow Diagram

```markdown
## Dependency Flow Diagram

> Actual import flow between layers, showing violations.

     ┌─────────────┐
     │   UI Layer   │
     │  (routes,    │
     │   cli)       │
     └──────┬───────┘
            │ ✅ 847 imports
            ↓
     ┌─────────────┐     ┌──────────────┐
     │  Services    │────→│  Data Layer   │
     │  Layer       │     │  (data,       │
     │              │     │   models,     │
     │              │     │   persistence)│
     └──────────────┘     └──────────────┘
         │      ↑
         │  211 lateral
         └──────┘

     ❌ UI → Persistence: 1 violation (audit.py:L15)
```

---

## 8. Script Parameters

```python
"""
@script
name: Data Layer Leak Audit
category: audit
mode: fully_automated
tags: architecture, layers, data, coupling, quality, python
default_output: docs/audits/
output_formats: markdown, json
requires_tools: (none)
timeout: 120
description: Audits architectural layer boundaries for data leaks.
    Detects four tiers of violations: (1) inline data in function bodies,
    (2) data definitions in wrong layers, (3) import direction violations,
    (4) lateral service coupling. Observes and reports — does not judge.

@param source-dir: string = src | Source directory to analyze
@param output: path = docs/audits/ | Output directory for the report
@param format: choice = markdown [markdown, json] | Output format
@param style: choice = smart [raw, smart] | Report style
@param scope: string = none | Limit analysis to a directory
@param min-dict-size: string = 5 | Minimum dict/list/set size to flag (Tier 1)
@param min-const-size: string = 3 | Minimum constant size to flag (Tier 2)
@param tier: choice = all [all, 1, 2, 3, 4] | Which tier(s) to analyze
"""
```

---

## 9. Implementation Order

### Step 1: `layer_analyzer.py` — the detection engine

Build the AST analysis engine that:
1. Classifies files into layers from directory structure
2. Scans for inline data literals (Tier 1) with smart classification
3. Scans for module-level constants in wrong layers (Tier 2)
4. Scans for import direction violations (Tier 3) — including lazy imports
5. Scans for lateral service coupling (Tier 4)
6. Detects data duplication across files

Data models: all 6 dataclasses from Section 6.

### Step 2: `data_layer_leaks.py` — the script

Wire up:
1. Script header (@script metadata)
2. Argument parsing
3. Call `layer_analyzer` with config
4. Format and write report (smart + raw + JSON)
5. Test with real codebase data

### Step 3: Smart report renderer

Build `_render_smart_markdown()`:
1. Executive summary with health verdict
2. All 9 sections from Section 7
3. Fix checklist with priority ordering
4. Duplication map with overlap percentages

---

## 10. Quality Bars

Before declaring this done:

- [ ] Running against THIS codebase produces a valid report
- [ ] Tier 1 correctly classifies response construction vs. real data leaks
- [ ] Tier 2 catches the known `_CODE_EXTS` duplication
- [ ] Tier 3 catches the known `audit.py → persistence` violation
- [ ] Tier 4 shows the 104 lateral coupling pairs
- [ ] The fix checklist is actually actionable
- [ ] JSON output matches markdown content
- [ ] Script runs in < 30 seconds on the full codebase
- [ ] No false positives on `__all__`, blueprints, or TYPE_CHECKING imports

---

## 11. What This Does NOT Do

- **Does not auto-fix** — it reports, the human decides
- **Does not scan templates** — Jinja HTML is a different concern
- **Does not enforce** — no CI gate, just visibility
- **Does not analyze runtime behavior** — pure static analysis
- **Does not replace code_hygiene** — that script checks init files and doc freshness,
  this script checks architectural boundaries. Complementary, not overlapping.

---

## 12. Relationship to Other Audits

| Audit | Focus | Overlap |
|-------|-------|---------|
| `code_hygiene` | Init file leaks + doc staleness | None — different files |
| `route_quality` | Route handler quality (docs, error handling) | None — different analysis |
| `data_layer_leaks` | Architectural boundary violations | Complements both |

The three audits together give a complete picture:
- **code_hygiene**: "Is your code organized?" (init files clean?)
- **route_quality**: "Are your routes well-built?" (docs, validation, error handling?)
- **data_layer_leaks**: "Is your architecture sound?" (data in right layers?)
