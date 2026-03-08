# Scripts System — Milestone 5: Route Quality Audit Script

> **Status**: Planning — Iteration 1
> **Parent**: `.agent/plans/scripts-system.md`
> **Milestone**: M5 — Route Quality Audit
> **Depends on**: M1 (Execution Framework), M2 (report_formatter, file_discovery)
> **Unlocks**: Automated route quality enforcement

---

## 0. What This Milestone Delivers

After M5 is complete:

1. A **Route Quality Audit** template script exists — scans all Flask route modules
2. It checks each route against a compliance standard (docstrings, RUN coverage, auth, audit/trace hooks)
3. It produces a **quality report** with scores, violations, and recommendations
4. It uses M1 for execution and tracking, M2's `report_formatter` for output
5. It has its own **route analyzer** lib module (M5-specific, not in M2's shared lib)

**What you can do after M5**: Run `controlplane scripts run audit/route_quality` and get a report showing which routes have missing docstrings, no RUN tracking, no auth decorators, no audit hooks, etc.

---

## 1. The Problem This Script Solves

From the user's words:
> "a script that would validate the quality of the routes and if they respect the standard and the RUN coverage and Audit / Trace and and auths and so on.... I want to study the pattern and be able to audit and produce a report"

The project has **33 route blueprint packages** under `src/ui/web/routes/`. Each package contains multiple route files with Flask endpoints. Quality varies — some routes have full docstrings, RUN tracking, auth decorators, audit hooks. Others don't.

The audit checks:

| Check | Description | Why |
|-------|-------------|-----|
| **Docstring** | Every route function has a docstring | Documentation standard |
| **RUN coverage** | Route uses `tracked_run()` or `log_run()` | Observability |
| **Auth decorator** | Route has `@login_required` or auth check | Security |
| **Audit/Trace** | Route publishes events or integrates with trace | Auditability |
| **HTTP method** | Route specifies methods explicitly | Clarity |
| **Error handling** | Route has try/except or uses receipt pattern | Robustness |
| **Return type** | Route returns JSON (jsonify) or render_template | Consistency |
| **Blueprint structure** | Routes registered on blueprint correctly | Architecture |

---

## 2. Architecture — Route Analyzer

### 2.1 Why a Separate Module

The route analyzer is **M5-specific** — it understands Flask route patterns, decorator conventions, and this project's specific standards. It does NOT go into M2's shared lib because:
- M2's shared lib is language-generic (Python AST) and domain-generic (classes, graphs, reports)
- The route analyzer is **domain-specific**: it knows about Flask, `@blueprint.route()`, `tracked_run()`, etc.
- Other projects using this script system wouldn't have Flask routes

### 2.2 Where It Lives

```
src/core/data/script_templates/
├── lib/                              ← M2: Generic shared lib
│   └── ...
├── audit/
│   ├── __init__.py
│   ├── route_quality.py              ← The script itself
│   └── route_analyzer.py            ← Route analysis module (M5-specific)
└── ...
```

The `route_analyzer.py` is a helper module co-located with the script — not in the generic lib. Scripts can have their own helper modules in the same directory.

### 2.3 What the Route Analyzer Extracts

```python
@dataclass
class RouteInfo:
    """Information about a single Flask route."""
    function_name: str                 # e.g., "trace_start"
    endpoint: str                      # e.g., "/api/trace/start"
    methods: list[str]                 # e.g., ["POST"]
    file_path: str                     # Relative path to source file
    blueprint: str                     # Blueprint name
    lineno: int
    end_lineno: int
    
    # Quality checks
    has_docstring: bool = False
    docstring_lines: int = 0
    has_run_tracking: bool = False     # Uses tracked_run() or log_run()
    has_auth: bool = False             # Has @login_required or auth check
    has_audit_hook: bool = False       # Publishes events or trace integration
    has_error_handling: bool = False   # try/except or receipt pattern
    specifies_methods: bool = False    # methods=["GET"] explicit
    return_type: str = "unknown"       # "json" | "template" | "redirect" | "raw" | "unknown"
    
    decorators: list[str] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)


@dataclass
class BlueprintAnalysis:
    """Analysis of one route blueprint package."""
    name: str                          # Blueprint name
    package_path: str                  # Path to package directory
    routes: list[RouteInfo]
    total_routes: int = 0
    compliant_routes: int = 0
    score: float = 0.0                 # 0.0–1.0, percentage of checks passing
    init_imports_count: int = 0        # How many sub-modules imported in __init__


@dataclass 
class RouteAuditResult:
    """Complete route quality audit result."""
    blueprints: list[BlueprintAnalysis]
    total_routes: int = 0
    total_compliant: int = 0
    overall_score: float = 0.0
    violations_by_type: dict[str, int] = field(default_factory=dict)
    worst_blueprints: list[str] = field(default_factory=list)
    best_blueprints: list[str] = field(default_factory=list)
```

### 2.4 Detection Strategy

The route analyzer uses AST parsing (same `ast` stdlib, NOT importing code_analyzer — different data):

1. **Find blueprints**: Scan `src/ui/web/routes/*/` for `__init__.py` files with `Blueprint(...)` calls
2. **Find routes**: In each sub-module, find functions decorated with `@<bp>.route(...)` 
3. **Check quality**: For each route function:
   - `has_docstring` → check first body statement is a string constant
   - `has_run_tracking` → search function body for `tracked_run(` or `log_run(` calls
   - `has_auth` → check decorators for `login_required` or function body for auth checks
   - `has_audit_hook` → search for `event_bus.publish(` or `trace` calls
   - `has_error_handling` → check for `try/except` blocks or receipt pattern
   - `specifies_methods` → check `@route()` decorator `methods` keyword argument
   - `return_type` → check return statement for `jsonify(`, `render_template(`, `redirect(`

---

## 3. Script Implementation

### 3.1 Script Header

```python
"""
@script
name: Route Quality Audit
category: audit
mode: fully_automated
tags: routes, flask, quality, compliance, audit
default_output: docs/audits/
output_formats: markdown, json
requires_tools: (none)
timeout: 60
description: Audits Flask route quality against the project's standards.
    Checks for docstrings, RUN coverage, auth decorators, audit hooks,
    error handling, and structural compliance. Produces a scored report.

@param scope: string | Blueprint scope — limit to specific blueprint (e.g., "vault", "audit")
@param output: path = docs/audits/ | Output directory for the report
@param format: choice = markdown [markdown, json] | Output format
@param min-score: float = 0.0 | Minimum score threshold — exit code 1 if below
@param strict: boolean = false | Strict mode — fail on any violation
"""
```

### 3.2 Script Pipeline

```
1. Read parameters
2. Discover route blueprint packages (file_discovery for dir listing)
3. For each blueprint:
   a. Parse __init__.py for Blueprint definition
   b. Parse each sub-module for @route-decorated functions
   c. Run quality checks on each route
   d. Score the blueprint
4. Aggregate results
5. Generate report (report_formatter)
6. Write to output directory
7. Exit code: 0 if score >= min-score, 1 otherwise
```

### 3.3 Output Format

```markdown
# Route Quality Audit

> Generated by Route Quality Audit on 2026-03-08T12:00:00Z

## Summary

| Metric | Value |
|--------|-------|
| Blueprints scanned | 33 |
| Total routes | 142 |
| Compliant routes | 98 |
| Overall score | 69.0% |

## Violations by Type

| Violation | Count | % |
|-----------|-------|---|
| Missing docstring | 18 | 12.7% |
| No RUN tracking | 22 | 15.5% |
| No auth decorator | 8 | 5.6% |
| No audit/trace hook | 31 | 21.8% |
| No error handling | 14 | 9.9% |
| Methods not explicit | 5 | 3.5% |

## Worst Blueprints

| Blueprint | Routes | Score | Top Violations |
|-----------|--------|-------|----------------|
| dev | 8 | 25.0% | No auth (8), No RUN (6) |
| events | 3 | 33.3% | No docstring (2), No RUN (3) |

## Best Blueprints

| Blueprint | Routes | Score |
|-----------|--------|-------|
| vault | 12 | 100.0% |
| audit | 42 | 95.2% |
| trace | 9 | 88.9% |

## Full Blueprint Details

### vault (12 routes — 100.0%)

| Route | Method | Docstring | RUN | Auth | Audit | Score |
|-------|--------|-----------|-----|------|-------|-------|
| vault_list | GET | ✅ | ✅ | ✅ | ✅ | 100% |
| vault_create | POST | ✅ | ✅ | ✅ | ✅ | 100% |
| ... | ... | ... | ... | ... | ... | ... |
```

---

## 4. What M5 Reuses From M2

| From M2 | Used by M5 | How |
|---------|-----------|-----|
| `file_discovery.discover_files()` | Find route files | List .py files under routes/ |
| `report_formatter.markdown_report()` | Generate report | Build markdown with summary + sections |
| `report_formatter.summary_table()` | Tables in report | Render violation and blueprint tables |
| `report_formatter.json_report()` | JSON output | Raw audit data as JSON |
| `report_formatter.write_report()` | Save report | Write to output directory |
| `code_analyzer` | **NOT USED** | Route analysis is domain-specific, not class-diagram analysis |
| `graph_builder` | **NOT USED** | No graph relationships needed |
| `mermaid_generator` | **NOT USED** | No diagrams needed |

M5 uses **2 out of 5** M2 modules: `file_discovery` and `report_formatter`. These are the generic ones. The domain-specific analysis (route parsing, quality checking) is M5's own code.

---

## 5. File Inventory

| File | Lines (est.) | Purpose |
|------|-------------|---------|
| `src/core/data/script_templates/audit/__init__.py` | ~5 | Package init |
| `src/core/data/script_templates/audit/route_quality.py` | ~200 | The script |
| `src/core/data/script_templates/audit/route_analyzer.py` | ~300 | Route analysis module |

**Total new code**: ~505 lines across 3 files

---

## 6. Orthogonality

| Concern | M5 owns | M5 borrows |
|---------|---------|-----------|
| Route detection logic | `route_analyzer.py` — AST-based Flask-specific parsing | Nothing |
| Quality checks | `route_analyzer.py` — domain rules | Nothing |
| Scoring | `route_quality.py` — score aggregation | Nothing |
| File discovery | — | M2 `file_discovery` |
| Report formatting | — | M2 `report_formatter` |
| Execution | — | M1 `executor` |
| Tracking | — | M1 `run_tracker` |
| Events | — | M1 `event_bus` |

No overlap with M3 (class diagrams) — different analyzer, different output, different purpose. Shared only through M2's generic modules.
