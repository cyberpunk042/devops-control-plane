# Code Hygiene Smart Report — Upgrade Plan

> **Status**: Discussion
> **Parent**: `.agent/plans/scripts-system/scripts-system-M6-code-hygiene.md`
> **Scope**: Upgrade `_render_smart_markdown()` + enrich analyzer data models
> **Constraint**: Keep all existing sections — upgrade and inject new ones

---

## 0. What Exists Today

### Data Models (what the analyzers provide)

**InitFunctionInfo**:
- `name`, `lineno`, `end_lineno`, `body_lines`
- `has_docstring`, `is_trivial`

**InitClassInfo**:
- `name`, `lineno`, `end_lineno`, `body_lines`, `method_count`

**InitFileAnalysis**:
- `file_path`, `language`, `total_lines`, `code_lines`
- `functions: list[InitFunctionInfo]`
- `classes: list[InitClassInfo]`
- `import_count`, `has_all_export`, `has_complex_logic`
- Computed: `function_count`, `class_count`, `total_function_lines`, `total_class_lines`, `logic_lines`, `is_clean`

**DocReference**:
- `doc_file`, `doc_line`, `reference_type`, `reference_text`
- `target_file`, `target_detail`, `is_valid`, `issue`

**DocFileAnalysis**:
- `doc_file`, `total_references`, `valid_references`
- `stale_references`, `all_references`
- Computed: `freshness`

### Current Smart Report Sections

| # | Section | What it shows |
|---|---------|---------------|
| 1 | Executive Summary | Metric/value table |
| 2 | Severity Tiers | Init files by size bucket (🔴/🟡/🟢) |
| 3 | Domain Analysis | Init files by architectural layer |
| 4 | Doc Freshness Dashboard | Freshness bars per doc |
| 5 | Cross-Reference | Init ↔ stale docs overlap |

### Problems Identified

1. **Self-referential loop**: Doc validator scans `docs/audits/code_hygiene.md` — its own output. 39/52 stale refs are noise from this.
2. **Cross-Reference noise**: Same `mybuilder.py` stale ref appears 24 times. No dedup.
3. **Init analysis lacks WHAT**: Shows "966 lines, 22 functions" but not what KIND of functions (route handlers? CLI commands? utility helpers?).
4. **No function-level detail in report**: Functions are listed by name but you can't see patterns (all are `_resolve_project_root` boilerplate vs actual business logic).
5. **No actionability**: "37 files with logic" — so what? Which 3 should I fix first?
6. **Stale ref table is a wall**: 52 rows, no grouping, no dedup.

---

## 1. Analyzer Enhancements (init_analyzer.py)

### 1.1 New Fields on InitFunctionInfo

```python
@dataclass
class InitFunctionInfo:
    # ... existing fields ...
    
    # NEW — function classification
    decorators: list[str] = field(default_factory=list)     # @app.route, @click.command, etc.
    is_route_handler: bool = False      # Has @bp.route or similar
    is_cli_command: bool = False        # Has @click.command or similar
    is_registration: bool = False       # Registry pattern (get_X, register_X)
    calls: list[str] = field(default_factory=list)  # Top-level calls made (service deps)
```

**Why**: The report currently says "22 functions" — with these fields it can say "22 route handlers" or "8 CLI commands" or "3 registry helpers". This is the difference between a count and an insight.

### 1.2 New Fields on InitFileAnalysis

```python
@dataclass
class InitFileAnalysis:
    # ... existing fields ...
    
    # NEW — structural insight
    has_blueprint_def: bool = False     # Contains Blueprint() or click.group()
    re_export_count: int = 0           # "from .module import X" style re-exports
    has_type_checking: bool = False     # Has TYPE_CHECKING block
```

**Why**: Distinguishes "this init has a Blueprint definition + 22 route handlers" from "this init is just re-exports." The Blueprint is fine — the handlers aren't.

### 1.3 Detection Logic (in _analyze_function)

```python
# Already walking decorators — just extract names
for deco in node.decorator_list:
    deco_name = _parse_deco_name(deco)
    if deco_name:
        info.decorators.append(deco_name)
        if deco_name in {"route", "get", "post", "put", "delete"}:
            info.is_route_handler = True
        if deco_name in {"command", "group"}:
            info.is_cli_command = True
        if "register" in node.name.lower() or node.name.startswith("get_"):
            info.is_registration = True
```

Minimal AST work — we're already in the function node.

---

## 2. Doc Validator Enhancement (doc_validator.py)

### 2.1 Self-Exclusion

The doc validator must skip files it writes to. Two approaches:

**Option A**: Skip `docs/audits/` entirely (simple but broad)
**Option B**: Accept an `exclude_paths` parameter (precise)

→ **Go with Option B**: Add `exclude_paths: list[str]` to `DocValidator.analyze()`, default to `["docs/audits/"]`.

### 2.2 No new data model changes needed

The existing `DocReference` model has everything we need. The problem is in the REPORT, not the data.

---

## 3. Smart Report Upgrade (_render_smart_markdown)

### Upgraded Structure

Keep ALL existing sections. Upgrade them in-place. Inject 3 new ones.

| # | Section | Status | What changes |
|---|---------|--------|--------------|
| 1 | **Executive Summary** | ⬆ UPGRADE | Add health verdict paragraph, function classification counts |
| 2 | **Severity Tiers** | ⬆ UPGRADE | Add function-type breakdown per file, migration note |
| 3 | **Domain Analysis** | ⬆ UPGRADE | Add function classification, distinguish boilerplate from real |
| 4 | **Leaked Function Inventory** | 🆕 NEW | Per-file: every function with type, size, decorators |
| 5 | **Refactoring Impact** | 🆕 NEW | "Fix these 3 → eliminate 70% of debt" |
| 6 | **Doc Freshness Dashboard** | ⬆ UPGRADE | Exclude self-referential, add trust tiers |
| 7 | **Stale Reference Groups** | ⬆ UPGRADE | Group by root cause, dedup, show count |
| 8 | **Cross-Reference** | ⬆ UPGRADE | Dedup, group by init file |
| 9 | **Fix Checklist** | 🆕 NEW | Ordered action items |

### 3.1 Section 1: Executive Summary (UPGRADE)

**Current**: Just a metric/value table.

**Add**: A health verdict paragraph ABOVE the table.

```markdown
## Executive Summary

> **Health**: Your init hygiene is **poor** — 37/131 init files contain logic
> (3,454 lines). The worst offender is `tab_mesh/__init__.py` with 966 lines
> (28% of all init debt). Documentation freshness is **fair** at 69% — but
> 75% of stale refs are self-referential noise (the report scanning itself).
> Real staleness affects 4 documents with 13 broken references.

| Metric | Value |
...existing table...

| 🔧 Route handlers in init | **22** |
| ⌨️ CLI commands in init | **18** |
| 📋 Registration helpers in init | **6** |
| 🔩 Other functions in init | **117** |
```

**How**: After computing all values, generate a narrative paragraph. The function classification counts come from the new `is_route_handler`, `is_cli_command`, `is_registration` fields.

### 3.2 Section 2: Severity Tiers (UPGRADE)

**Current**: Table with file_path, total_lines, functions, classes.

**Add**: Function type breakdown + one-line migration note per file.

```markdown
### 🔴 Critical (12 files)

| File | Lines | Route Handlers | CLI Commands | Other | Migration |
|------|-------|---------------|--------------|-------|-----------|
| `tab_mesh/__init__.py` | 966 | 22 | 0 | 0 | → split to routes/*.py |
| `cli/docs/__init__.py` | 264 | 0 | 8 | 0 | → split to commands/*.py |
| `core/data/__init__.py` | 298 | 0 | 0 | 3+1cls | → move to registry.py |
```

**How**: Use the new `is_route_handler` / `is_cli_command` fields to produce the breakdown. The migration note is inferred from the dominant function type:
- Mostly route handlers → "→ split to routes/*.py"
- Mostly CLI commands → "→ split to commands/*.py"
- Mostly registry → "→ move to registry.py"
- Mixed → "→ refactor to sub-modules"

### 3.3 Section 3: Domain Analysis (UPGRADE)

**Current**: Groups by architectural layer, shows top 3 function names.

**Add**: Distinguish boilerplate from real leaks.

CLI domain has 20 files but 13 of them are the SAME boilerplate pattern
(`_resolve_project_root` + group definition). That's VERY different from
tab_mesh's 22 unique route handlers. The report should say so.

```markdown
### ⌨️ CLI Commands (20 files, 84 functions, 2038 lines)

> ⚠️ **Pattern**: 13/20 files follow the `_resolve_project_root + group` boilerplate
> pattern (34 lines avg). This is structural, not accidental.
> The remaining 7 files have substantial logic that should be split.

| File | Lines | Type | Note |
|------|-------|------|------|
| `cli/quality/__init__.py` | 221 | 11 CLI commands | → split to commands/*.py |
| `cli/ci/__init__.py` | 236 | 10 CLI commands | → split to commands/*.py |
| ...
```

**How**: Detect the boilerplate pattern by checking if functions match known patterns (`_resolve_project_root`, group names matching the module name). Count how many files follow the pattern vs how many have real unique logic.

### 3.4 Section 4: Leaked Function Inventory (NEW)

The missing piece. Shows WHAT is actually in each non-clean init file.

```markdown
## Leaked Function Inventory

> Every function and class defined in non-clean init files.
> Grouped by file, sorted by body size.

### src/ui/web/routes/tab_mesh/__init__.py (966 lines, 22 functions)

| Function | Lines | Type | Decorators |
|----------|-------|------|------------|
| `restart_chrome` | 85 | route handler | @route POST |
| `cdp_diagnose` | 62 | route handler | @route GET |
| `_modify_shortcut` | 48 | route handler | @route POST |
| `kill_chrome` | 42 | route handler | @route POST |
| ... |

### src/core/data/__init__.py (298 lines, 3 functions, 1 class)

| Item | Lines | Type | Decorators |
|------|-------|------|------------|
| `classify_key` | 120 | utility | — |
| `get_registry` | 85 | registration | — |
| `_load_json` | 35 | utility | — |
| class `ToolRegistry` | 58 | class (4 methods) | — |
```

**How**: Iterate non-clean files, print their functions with the new classification fields. Only show files above a threshold (e.g., > 50 lines) to keep it focused. Smaller files are already covered by severity tiers.

### 3.5 Section 5: Refactoring Impact (NEW)

The "so what?" section. Shows ROI of cleanup.

```markdown
## Refactoring Impact

> If you fix these files, here's the impact on your init debt.

| Priority | File | Lines | % of Debt | Cumulative |
|----------|------|-------|-----------|------------|
| 1 | `tab_mesh/__init__.py` | 966 | 28.0% | 28.0% |
| 2 | `core/data/__init__.py` | 298 | 8.6% | 36.6% |
| 3 | `audit/parsers/__init__.py` | 289 | 8.4% | 45.0% |
| 4 | `cli/docs/__init__.py` | 264 | 7.6% | 52.6% |
| 5 | `content/__init__.py` | 252 | 7.3% | 59.9% |

> 📊 **Fixing the top 5 files eliminates 60% of all init debt.**
> Fixing the top 3 eliminates 45%.
```

**How**: Sort non-clean files by `total_lines`, compute cumulative percentage. This is trivially computed from existing data — no new analyzer work needed.

### 3.6 Section 6: Doc Freshness Dashboard (UPGRADE)

**Current**: Shows freshness bars per doc.

**Changes**:
1. **Exclude self-referential refs** — filter out docs inside the output directory
2. **Add trust tier labels**: ✅ Trustworthy (100%) / ⚠️ Mostly OK (>80%) / 🔴 Unreliable (<80%)
3. **Show actual vs self-referential counts** — so the user knows the numbers are clean

```markdown
## Documentation Freshness Dashboard

> Freshness of documents containing code references.
> **Note**: Audit output files (`docs/audits/`) are excluded from scanning
> to avoid self-referential noise.

📚 **Overall**: `████████████████░░░░` 81.3% (101/124 valid)

### Trust Tiers

| Tier | Docs | Status |
|------|------|--------|
| ✅ Trustworthy (100%) | 115 | All references valid |
| ⚠️ Mostly OK (>80%) | 4 | Minor staleness |
| 🔴 Unreliable (<80%) | 4 | Significant staleness |

### Per-Document Freshness
(existing bars, but minus the self-referential docs)
```

### 3.7 Section 7: Stale Reference Groups (UPGRADE)

**Current**: One row per stale ref — wall of 52 identical-looking rows.

**Change to**: Group by root cause.

```markdown
### Stale References — Grouped by Root Cause

#### `mybuilder.py` (template example — 6 refs across 2 docs)
> This is a template/example file referenced in documentation.
> The file `src/core/services/pages_builders/mybuilder.py` does not exist.

- `docs/PAGES.md` — L208, L210 (5 function refs), L211
- `docs/DEVELOPMENT.md` — L149

#### Moved/deleted service files (6 refs across 1 doc)
> Files that were refactored into sub-modules.

- `docs/CONSOLIDATION_AUDIT.md`:
  - L25: `content_crypto.py` — moved
  - L34: `content_release.py` — moved
  - L273-276: 4 more in same cluster
```

**How**: Group stale refs by `target_file`. If multiple refs point to the same missing file, collapse them into one entry with line numbers listed. This turns 52 rows into ~5 groups.

### 3.8 Section 8: Cross-Reference (UPGRADE)

**Current**: Repeats same init file 24 times for each stale ref.

**Change to**: Group by init file, dedup refs.

```markdown
## Cross-Reference

> Areas where init leaks and stale documentation overlap.

### src/core/services/pages_builders/__init__.py

- **Init issue**: 74 lines, 3 functions (registration pattern)
- **Related stale docs**:
  - `docs/PAGES.md` references `mybuilder.py` (6 stale refs)
  - Total: 6 stale refs in 1 doc pointing into this package
```

### 3.9 Section 9: Fix Checklist (NEW)

Concrete, ordered action items.

```markdown
## Fix Checklist

> Ordered by impact. Each item is independent — fix any one without the others.

1. 🔴 **Split `tab_mesh/__init__.py`** (966L, 22 route handlers)
   → Move handlers to `routes/tab_mesh/handlers.py` or sub-modules
   → Impact: eliminates 28% of init debt

2. 🔴 **Split `core/data/__init__.py`** (298L, 3 funcs + 1 class)
   → Move `classify_key`, `get_registry`, `_load_json` to `core/data/registry.py`
   → Impact: eliminates 8.6% of init debt

3. 🟡 **Update `docs/PAGES.md`** (6 stale refs)
   → Remove or update `mybuilder.py` template references
   → Impact: eliminates 46% of stale doc refs

4. 🟡 **Update `docs/CONSOLIDATION_AUDIT.md`** (6 stale refs)
   → Update file paths for refactored services
   → Impact: eliminates 46% of stale doc refs

5. 🟢 **CLI boilerplate** (13 files, 34 lines avg)
   → Low priority — this is a consistent pattern, not accidental debt
```

**How**: Combine init debt (sorted by total_lines) with doc staleness (sorted by stale count). Assign severity icons based on size. Generate migration hints from function types.

---

## 4. Implementation Order

### Step 1: Analyzer enhancements (init_analyzer.py)
- Add `decorators`, `is_route_handler`, `is_cli_command`, `is_registration`, `calls` to InitFunctionInfo
- Add `has_blueprint_def`, `re_export_count`, `has_type_checking` to InitFileAnalysis
- Update `_analyze_function` and `_analyze_file` to populate new fields
- **No existing tests break**: all new fields have defaults

### Step 2: Doc validator self-exclusion (doc_validator.py)
- Add `exclude_dirs: list[str]` parameter to `DocValidator.analyze()`
- Default: `["docs/audits/"]`
- Pass through from `code_hygiene.py`

### Step 3: Smart report rewrite (code_hygiene.py → `_render_smart_markdown`)
- Upgrade sections 1-3, 6-8 in-place
- Inject sections 4, 5, 9
- All changes confined to `_render_smart_markdown()` — no other functions affected

### Step 4: Verify
- Run the script, compare old vs new output
- Ensure self-referential noise is gone
- Ensure function classification is accurate

---

## 5. Risk Assessment

| Risk | Mitigation |
|------|-----------|
| Function classification wrong for edge cases | Conservative: default to "other" if unsure |
| Migration hints too prescriptive | Frame as observations: "→ candidate for split" not "→ you must split" |
| Doc self-exclusion misses real issues in `docs/audits/` | Allow override via param; document the exclusion |
| CLI boilerplate detection false positives | Only flag as boilerplate if ≥3 files share the same pattern |

---

## 6. Not In Scope

- Trend/delta comparison between runs (future: would need stored baselines)
- Import depth analysis (separate concern — could be its own sub-audit)
- Auto-fix / auto-refactor (out of scope — this is observation, not action)
- New CLI params (all changes are internal to the smart report renderer)
