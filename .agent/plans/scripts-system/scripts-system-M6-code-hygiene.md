# Scripts System — Milestone 6: Code Hygiene Audit Script

> **Status**: Planning — Iteration 1
> **Parent**: `.agent/plans/scripts-system.md`
> **Milestone**: M6 — Code Hygiene Audit
> **Depends on**: M1 (Execution Framework), M2 (report_formatter, file_discovery)
> **Unlocks**: Automated code hygiene enforcement

---

## 0. What This Milestone Delivers

After M6 is complete:

1. A **Code Hygiene Audit** template script exists — two sub-audits in one script
2. **Sub-audit A**: `__init__.py` logic leak detection — finds code that shouldn't be in init files
3. **Sub-audit B**: Stale documentation detection — finds doc references that are wrong
4. It produces a **hygiene report** with violations and recommendations
5. It uses M1 for execution and tracking, M2's `report_formatter` for output
6. It has its own **init analyzer** and **doc validator** helper modules (M6-specific)

**What you can do after M6**: Run `controlplane scripts run audit/code_hygiene` and see which `__init__.py` files have leaked logic and which docs reference wrong line numbers.

---

## 1. The Problem This Script Solves

From the user's words:
> "audit when laziness was used and routes or logics leaked into __init__ files..... and stuff like this..... those are all real case with real current examples"
> "detect stale documentation, outdated docs such as bad line count or bad line ref line(s) and whatnot"

Two real problems:

### 1.1 Problem A: `__init__.py` Logic Leaks

The project rule: **no logic in `__init__.py`** — only re-exports, blueprint definitions, and registration imports. But laziness happens. Current real examples exist:
- `src/core/services/artifacts/builders/__init__.py` — has a `get_builder()` function with logic (registry dict + lookup)
- `src/core/services/audit/parsers/__init__.py` — may have parser registry logic
- `src/core/services/pages_builders/__init__.py` — may have builder logic

### 1.2 Problem B: Stale Documentation

Documentation references code by line number. As code evolves:
- "See line 42 in `executor.py`" — but the function moved to line 78
- "This module has 150 lines" — but it now has 280
- "The function `_parse_header` starts at line 12" — but it was renamed
- File references to files that no longer exist
- README examples that reference functions that were removed or renamed

---

## 2. Sub-audit A: `__init__.py` Logic Leak Detection

### 2.1 What Constitutes a Leak

An `__init__.py` file is **clean** if it contains ONLY:
- Module docstring
- Import statements (both regular and re-export `from .x import Y`)
- `__all__` assignment
- Blueprint / group definitions (e.g., `Blueprint(...)`, `click.group()`)
- Registration calls (e.g., `from . import module  # noqa`)
- Type aliases (`X = TypeAlias`)
- Constants that are pure config (ALL_CAPS names with simple values)

An `__init__.py` has **leaked logic** if it contains:
- Function definitions (`def foo():`) that aren't trivial re-exports
- Class definitions (`class Foo:`)
- Complex logic (if/else, loops, try/except that aren't import guards)
- Business logic (calculations, data transformation, API calls)

### 2.2 Detection Strategy

```python
@dataclass
class InitFileAnalysis:
    """Analysis of a single __init__.py file."""
    file_path: str                     # Relative path
    total_lines: int
    code_lines: int                    # Excluding blank + comments + docstrings
    
    # What we found
    functions: list[str]               # Function names defined
    classes: list[str]                 # Class names defined
    has_logic: bool                    # Non-trivial code detected
    
    # Detail
    complexity_score: int              # How far from "clean" (0 = clean)
    violations: list[str]              # Specific violations
    
    # Judgment
    is_clean: bool                     # Passes all checks
```

Detection using AST:
1. Parse `__init__.py` with `ast.parse()`
2. Walk top-level nodes:
   - `ast.FunctionDef` → violation (unless body is a single return/pass)
   - `ast.ClassDef` → violation
   - `ast.If` that isn't `if TYPE_CHECKING:` → possible violation
   - `ast.For`, `ast.While`, `ast.With` → violation
   - `ast.Try` that wraps more than just imports → possible violation
3. Count complexity: more top-level statements beyond imports = higher complexity
4. Flag specific violations with file/line references

### 2.3 Severity Levels

| Level | Description | Example |
|-------|-------------|---------|
| **Critical** | Full function/class with business logic | `get_builder()` in builders/__init__ |
| **Warning** | Simple utility function that could be moved | Small helper that belongs in a module |
| **Info** | Slightly complex import logic | Try/except around optional import |
| **Clean** | Only imports, re-exports, docstring | Standard init file |

---

## 3. Sub-audit B: Stale Documentation Detection

### 3.1 What Constitutes Staleness

References in markdown docs that are wrong:
- **Line references**: "`line 42`" or "`L42`" — checked against actual file
- **Line counts**: "this file has 150 lines" — checked against actual line count
- **Line ranges**: "lines 10-25" — checked: do those lines still contain the described content?
- **File references**: "`src/core/services/foo.py`" — file doesn't exist
- **Function references**: "`_parse_header()`" — grep: function doesn't exist in referenced file
- **Symbol references**: "`class EventBus`" — checked: class exists in referenced file

### 3.2 Detection Strategy

```python
@dataclass
class DocReference:
    """A reference found in a documentation file."""
    doc_file: str                      # Path to the doc that contains the reference
    doc_line: int                      # Line number in the doc
    reference_type: str                # "line" | "line_count" | "line_range" | "file" | "function" | "class"
    reference_text: str                # The original text in the doc
    target_file: str                   # The file being referenced
    target_detail: str | None          # e.g., line number, function name
    is_valid: bool                     # True if reference is still accurate
    issue: str | None                  # Description of the problem if invalid


@dataclass
class DocAnalysis:
    """Analysis of staleness in documentation files."""
    doc_file: str
    total_references: int
    valid_references: int
    stale_references: list[DocReference]
    freshness_score: float             # 0.0–1.0, % of references still valid


@dataclass
class DocHygieneResult:
    """Complete documentation hygiene result."""
    docs_scanned: int
    total_references: int
    stale_references: int
    overall_freshness: float
    worst_docs: list[str]
    stale_details: list[DocReference]
```

Detection using regex + file verification:
1. Scan markdown files (`.md`) under `docs/`, `.agent/plans/`, `README.md`
2. For each markdown file, extract references using patterns:
   - `` `src/path/to/file.py` `` → file reference
   - `line 42`, `L42`, `line(s) 10-25` → line reference  
   - `` `function_name()` `` → function reference (if preceded by file ref)
   - "N lines" near a file reference → line count reference
3. For each reference, verify:
   - File exists
   - Line number is within file range
   - Function/class exists in file (grep or AST)
   - Line count matches

### 3.3 Scope Limits

What this audit does **NOT** check:
- Content accuracy (we verify the reference points to the right thing, not that the description is accurate)
- Spelling and grammar
- Link validity (URLs — that's a different tool)
- Cross-doc reference consistency

---

## 4. Script Implementation

### 4.1 Script Header

```python
"""
@script
name: Code Hygiene Audit
category: audit
mode: fully_automated
tags: hygiene, init, documentation, stale, compliance
default_output: docs/audits/
output_formats: markdown, json
requires_tools: (none)
timeout: 120
description: Audits code hygiene — detects __init__.py logic leaks and stale
    documentation references. Two sub-audits in one script.

@param sub-audit: choice = all [all, init, docs] | Which sub-audit to run
@param scope: string | Scope — limit to specific directory (e.g., "core/services")
@param output: path = docs/audits/ | Output directory for the report
@param format: choice = markdown [markdown, json] | Output format
@param severity: choice = warning [critical, warning, info] | Minimum severity to report
@param strict: boolean = false | Strict mode — fail on any violation
"""
```

### 4.2 Script Pipeline

```
1. Read parameters
2. If sub-audit == "all" or "init":
   a. Discover __init__.py files (file_discovery)
   b. For each, run init analysis (init_analyzer)
   c. Collect violations
3. If sub-audit == "all" or "docs":
   a. Discover markdown files (file_discovery)
   b. For each, extract references (doc_validator)  
   c. Verify each reference against actual files
   d. Collect stale references
4. Aggregate results
5. Generate report (report_formatter)
6. Write to output directory
7. Exit code: 0 if no critical violations (or score meets threshold), 1 otherwise
```

### 4.3 Where the Helpers Live

```
src/core/data/script_templates/audit/
├── __init__.py                  ← Package init (also used by M5)
├── code_hygiene.py              ← The script
├── init_analyzer.py             ← __init__.py analysis module
├── doc_validator.py             ← Stale doc reference validator
└── route_quality.py             ← M5's script (already there)
```

Co-located with the script — same pattern as M5.

### 4.4 Output Format

```markdown
# Code Hygiene Audit

> Generated by Code Hygiene Audit on 2026-03-08T12:00:00Z

## Summary

| Metric | Value |
|--------|-------|
| __init__.py files scanned | 53 |
| Clean init files | 49 |
| Init files with logic leaks | 4 |
| Documentation files scanned | 12 |
| Total references found | 87 |
| Stale references | 14 |
| Overall freshness | 83.9% |

---

## Sub-audit A: __init__.py Logic Leaks

### Critical Violations

| File | Violation | Line |
|------|-----------|------|
| `services/artifacts/builders/__init__.py` | Function `get_builder()` — 24 lines of logic | 18 |
| `services/pages_builders/__init__.py` | Class `PageBuilder` — should be in own module | 5 |

### Warning Violations

| File | Violation | Line |
|------|-----------|------|
| `services/audit/parsers/__init__.py` | Complex import logic with try/except block | 12 |

### Clean Files (49/53)

All other __init__.py files contain only imports, re-exports, and docstrings. ✅

---

## Sub-audit B: Stale Documentation

### Stale References

| Doc File | Line | Reference | Issue |
|----------|------|-----------|-------|
| `docs/ARCHITECTURE.md` | 42 | `line 150 in executor.py` | File is now 280 lines; content at line 150 has changed |
| `.agent/plans/M1.md` | 88 | `_parse_header()` in `models.py` | Function no longer exists |
| `docs/routes.md` | 15 | `src/ui/web/routes/auth/` | Directory does not exist |

### Fresh References (73/87)

Most documentation references are up to date. ✅
```

---

## 5. What M6 Reuses From M2

| From M2 | Used by M6 | How |
|---------|-----------|-----|
| `file_discovery.discover_files()` | Find `__init__.py` and `.md` files | Filter by extension |
| `file_discovery.discover_python_files()` | Find all init files | Scoped scanning |
| `report_formatter.markdown_report()` | Generate report | Build markdown with sections |
| `report_formatter.summary_table()` | Tables in report | Render violation tables |
| `report_formatter.json_report()` | JSON output | Raw hygiene data as JSON |
| `report_formatter.write_report()` | Save report | Write to output directory |
| `code_analyzer` | **NOT USED** | Init analysis is simpler — doesn't need class extraction |
| `graph_builder` | **NOT USED** | No graph relationships |
| `mermaid_generator` | **NOT USED** | No diagrams |

Same pattern as M5: uses `file_discovery` + `report_formatter` only.

---

## 6. File Inventory

| File | Lines (est.) | Purpose |
|------|-------------|---------|
| `src/core/data/script_templates/audit/code_hygiene.py` | ~180 | The script |
| `src/core/data/script_templates/audit/init_analyzer.py` | ~200 | __init__.py analysis module |
| `src/core/data/script_templates/audit/doc_validator.py` | ~250 | Stale doc reference validator |

**Total new code**: ~630 lines across 3 files

(Note: `audit/__init__.py` is created in M5 — shared by both scripts)

---

## 7. Orthogonality — The Full Picture

Now that M4, M5, and M6 are planned alongside M1, M2, M3, here's the complete orthogonality map:

### 7.1 Module Dependency Matrix

```
                    M1           M2            M3         M4         M5         M6
                   framework    shared-lib    class-dgm  interfaces  routes     hygiene
                   ─────────    ──────────    ─────────  ──────────  ──────────  ──────
M1 framework       ■            ·             ·          ·           ·          ·
M2 shared-lib      contracts    ■             ·          ·           ·          ·
M3 class-diagrams  executor     ALL 5 modules ■          ·           ·          ·
M4 interfaces      registry+    ·             ·          ■           ·          ·
                    executor
M5 route-audit     executor     file_disc +   ·          ·           ■          ·
                                report_fmt
M6 code-hygiene    executor     file_disc +   ·          ·           ·          ■
                                report_fmt
```

### 7.2 What Each Milestone Owns Exclusively

| Milestone | Exclusive Modules | Shared With |
|-----------|-------------------|-------------|
| M1 | models, config, registry, executor, output_router | → all others import |
| M2 | code_analyzer, graph_builder, mermaid_generator | → only M3 uses all 5 |
| M2 | file_discovery, report_formatter | → M3, M5, M6 use these 2 |
| M3 | generators/class_diagrams.py | → standalone |
| M4 | CLI commands, API routes, admin panel template | → standalone |
| M5 | audit/route_quality.py, audit/route_analyzer.py | → standalone |
| M6 | audit/code_hygiene.py, audit/init_analyzer.py, audit/doc_validator.py | → standalone |

### 7.3 Zero Overlap Validation

- M3 (class diagrams) and M5 (routes): **No overlap** — different analyzers, different outputs
- M3 (class diagrams) and M6 (hygiene): **No overlap** — different analyzers, different outputs  
- M5 (routes) and M6 (hygiene): **No overlap** — different analyzers, different targets
- M4 (interfaces) and M5/M6: **No overlap** — M4 is UI, M5/M6 are scripts
- M2's split: `code_analyzer + graph_builder + mermaid_generator` are M3-exclusive; `file_discovery + report_formatter` are generic

### 7.4 Build Order Options

The dependency chain allows these parallel tracks:

```
Sequential:   M1 → M2 → M3 → M4 → M5 → M6

Parallel A:   M1 → M2 → M3
                ↘ M4 (parallel with M2/M3)
                    → M5 → M6

Parallel B:   M1 → M2 → M3
                ↘ M4
                ↘ M5 (only needs M2: file_discovery + report_formatter)
                ↘ M6 (only needs M2: file_discovery + report_formatter)
```

**Maximum parallelism**: After M1, everything else can theoretically run in parallel:
- M2 + M4 in parallel
- Then M3 + M5 + M6 in parallel (once M2 is done)

This validates the orthogonality: milestones don't step on each other.
