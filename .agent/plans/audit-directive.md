# Audit Directive — `:::audit-data`

## Objective

The `:::audit-data` directive renders a comprehensive, scoped health card for the
code path that the documentation lives in. When a reader opens a README for
`src/core/services/audit/`, they see a COMPLETE picture of that code's quality,
risks, dependencies, development activity, and test coverage — all scoped to
that exact path, using real data from audit cache, file system, git state, and
test analysis.

The directive is:
- **Auto-injected** by the preview endpoint for module files (no manual authoring)
- **Resolved server-side** to `<details>` HTML before returning to the frontend
- In **raw/source mode**: the user sees `:::audit-data\n:::`
- In **preview mode**: the user sees the fully rendered health card

---

## Data Sources & Scoping

All data is filtered by `source_prefix` — the file path prefix for the scope.
For `src/core/services/audit/README.md`, the prefix is `src/core/services/audit`.

### Source 1: `audit:l2:quality` (cache)

| Field | Structure | Scoping |
|-------|-----------|---------|
| `file_scores[]` | `{file, score, breakdown: {docstrings, function_length, nesting, comments, type_hints}}` | Filter by `file.startswith(prefix)` |
| `hotspots[]` | `{type, severity, file, symbol, lineno, detail, value}` | Filter by `file.startswith(prefix)` |
| `naming` | Project-wide naming analysis | Skip — not useful scoped |
| `summary` | Project aggregate | Skip — we compute our own scoped aggregates |

**What we extract:**
- Per-file scores with 5-subcategory breakdown
- Aggregated subcategory averages across scoped files
- Worst 3 files by total score
- All hotspots grouped by severity (critical first)

### Source 2: `audit:l2:risks` (cache)

| Field | Structure | Scoping |
|-------|-----------|---------|
| `findings[]` | `{severity, title, category, files[], description}` | Only include if `files[]` has entries matching prefix. If `files[]` is empty → project-wide → **EXCLUDE** |
| `by_category` | Grouped findings | Recompute from scoped findings |
| `posture` | Project-wide | Skip |
| `action_items` | Project-wide | Skip |

**What we extract:**
- Findings that reference files in this scope (severity + title + affected files)
- If zero scoped findings → **omit the entire section**
- Never show project-wide findings (they're noise — identical on every page)

### Source 3: `audit:l2:structure` (cache)

| Field | Structure | Scoping |
|-------|-----------|---------|
| `modules[]` | `{module, path, files, total_lines, total_functions, total_classes, exposure_ratio}` | Match module name |
| `cross_module_deps[]` | `{from_module, to_module, import_count, files_involved[], strength}` | See dedup logic below |
| `library_usage{}` | `{lib_name: {sites: [{file, lineno, names[]}]}}` | Filter sites by `file.startswith(prefix)` |

**Cross-module dep dedup logic:**
1. Only include deps where one side is INSIDE the scope module and the other is OUTSIDE
2. Both sides matching → internal dep → **skip**
3. Map dotted sub-path to configured module name using `modules[]` config
4. Dedup: collapse multiple deps to same external module into ONE pill with the strongest strength
5. Direction: if `from_module` is inside → outbound (→), if `to_module` is inside → inbound (←)

**Library usage scoping:**
For each library in the dict, filter `sites[]` by `file.startswith(prefix)`.
If any site matches → this scope uses this library. Show which libraries
this code imports and from which files.

### Source 4: `audit:scores` (cache) — Project Context

| Field | Structure | Use |
|-------|-----------|-----|
| `quality.score` | Project-wide quality score | Show as comparison: "Project avg: 8.2" |
| `complexity.score` | Project-wide complexity | Show alongside |
| `trend` | `{quality_trend, complexity_trend, quality_delta, complexity_delta}` | Note if improving/declining |

### Source 5: `testing` (cache) — Test Coverage

| Field | Structure | Scoping |
|-------|-----------|---------|
| `stats.test_file_paths[]` | List of all test file paths | Match test files that contain module/scope name in path |
| `stats.test_functions` | Total test count | Project-wide context |
| `stats.test_ratio` | Test-to-code ratio | Project-wide context |
| `frameworks[]` | Test framework info | Context |

**Scoping logic:**
Match test files by checking if the test file name or path contains the scope
module name or subpath. E.g., for scope `audit`:
- `tests/test_audit.py` → match
- `tests/test_audit_scoring.py` → match
- `tests/audit/test_l2.py` → match

### Source 6: Live File System — Real-Time Stats

Read directly from disk (we're in the backend):

| Data | How |
|------|-----|
| Python file count | `Path(prefix).rglob("*.py")` — count |
| Total lines | Sum of line counts |
| Per-file line counts | For worst-file ranking |
| Last modified dates | `os.path.getmtime()` per file |
| File type breakdown | Group by extension (.py, .md, .json, etc.) |
| README existence | Check if scope has its own README |

**Why live FS instead of cache:**
Cache data is from last scan. Live FS gives CURRENT state. The difference
matters — files may have been added, modified, or deleted since last audit.
If the live count differs significantly from cached count, NOTE it:
"16 files (cache shows 12 — re-scan recommended)"

### Source 7: `git` (cache) — Development Activity

| Field | Scoping |
|-------|---------|
| `modified[]` | Filter by `file.startswith(prefix)` |
| `staged[]` | Filter by `file.startswith(prefix)` |
| `untracked[]` | Filter by `file.startswith(prefix)` |
| `last_commit` | Project-wide context |

**What we show:**
- Are there uncommitted changes in this scope RIGHT NOW?
- How many files are modified/staged/untracked in this scope?
- This tells the reader "this code has active changes" vs "this code is stable"

---

## Rendered Sections

Eight sections, each only rendered if there is meaningful scoped data.
Empty sections are **omitted entirely** — no empty headings, no "no data" messages
for optional sections.

### Section 1: Summary Line (always shown)

The `<summary>` of the `<details>` element. One-line overview:

```
📊 Audit Data — Health: 8.3/10 · 22 hotspots · Source: Local
```

Components:
- Health score (scoped average of file_scores)
- Hotspot count (scoped)
- Finding count (scoped, ONLY if > 0)
- Source label (Local / Saved / N/A)

### Section 2: Module Health (always shown)

```
Module Health                                      16 files · 5,991 lines
██████████████████████░░░  8.3 / 10               Project avg: 8.2

Quality Breakdown
  docstrings ████████████████████  9.2    ← strongest
  function_length ██████████████░░  7.8
  nesting ██████████░░░░░░░░░░  5.4       ← weakest
  comments ████████████████████  9.4
  type_hints █████████████████░░  8.1

Weakest Files
  ⚠ models.py           7.8/10  (docstrings: 1.0, type_hints: 10.0)
  ⚠ __init__.py          7.8/10  (type_hints: 0.0)
  ⚠ l1_classification.py 8.1/10  (nesting: 2.0)
```

Data:
- `file_scores[]` filtered by prefix → average `score` and per-subcategory averages
- Live FS file count + line count (more accurate than cached)
- Bottom 3 files by score with their breakdown showing WHY they score low
- Project quality score from `audit:scores` for comparison

### Section 3: Hotspots (shown if any exist in scope)

Grouped by severity, showing file + function + metric:

```
Hotspots (22)

Critical
  ⚠ python_parser.py → parse_file — 172 lines (long function)
  ⚠ scoring.py → _quality_score — 151 lines (long function)
  ⚠ l1_classification.py → _extract_all_deps — depth 8 (deep nesting)
  ⚠ l0_detection.py → _detect_os — depth 7 (deep nesting)

Warning
  ⚠ l1_classification.py — 512 code lines (large file)
  ⚠ l1_classification.py → l1_structure — 131 lines (long function)
  ⚠ l2_risk.py → _security_findings — 116 lines (long function)
  ...and 15 more
```

Data:
- `hotspots[]` filtered by prefix
- Grouped by `severity` (critical → warning → info)
- Show `file` basename + `symbol` (if present) + `detail` + `type`
- Show all critical, limit warning/info to top 5 each with "and N more"

### Section 4: Risk Findings (shown ONLY if scoped findings exist)

```
Risk Findings (2)
  🔴 Critical: SQL injection in query builder (l2_risk.py:45)
  🟡 Medium: Missing input validation (scoring.py:130)
```

Data:
- `findings[]` where `files[].file.startswith(prefix)`
- If ALL findings have `files: []` (project-wide) → **omit entire section**
- Show severity emoji + severity label + title + affected file(s)

### Section 5: Dependencies (shown if any cross-boundary deps exist)

```
Dependencies

Outbound (this code imports from)
  → adapters (strong · 12 imports)
  → config (moderate · 5 imports)

Inbound (other code imports this)
  ← cli (strong · 18 imports)
  ← web (moderate · 8 imports)
  ← tests (weak · 3 imports)
```

Data:
- `cross_module_deps[]` filtered:
  - `from_inside = _module_matches(from_module, scope.module, scope.module_path)`
  - `to_inside = _module_matches(to_module, scope.module, scope.module_path)`
  - Skip if `from_inside AND to_inside` (internal)
  - `from_inside AND NOT to_inside` → outbound
  - `NOT from_inside AND to_inside` → inbound
- Dedup by target module: collapse all deps to `cli` into one pill
  - Strength = strongest among collapsed entries
  - Import count = sum of `import_count` across collapsed entries
- Label: map dotted path to configured module name. If no config match,
  use the last dotted segment as label.
- Show as pills with direction arrow + module name + strength + import count

### Section 6: Library Usage (shown if any libs used in scope)

```
Third-Party Libraries
  distro — l0_detection.py
  tomli — l1_classification.py
```

Data:
- `library_usage{}` dict: for each lib, filter `sites[]` by prefix
- If any site matches → show library name + which file(s) use it
- This tells the reader what third-party deps this code relies on

### Section 7: Test Coverage (shown if test data available)

```
Test Coverage
  Test files: tests/test_audit.py, tests/test_audit_scoring.py
  Test ratio: 0.12 (project-wide)
  Frameworks: pytest
```

OR if no test files match:

```
Test Coverage
  ⚠ No test files found for this scope
```

Data:
- `testing.stats.test_file_paths[]` filtered by scope name match
- `testing.stats.test_ratio` for context
- `testing.frameworks[]` for framework info
- Always show this section — "no tests" is important information

### Section 8: Development Activity (shown if any activity in scope)

```
Development Activity
  Modified: 2 files (l0_detection.py, l0_os_detection.py)
  Last modified: 2026-02-28 (4 days ago)
```

Data:
- Git cache `modified[]`, `staged[]`, `untracked[]` filtered by prefix
- Live FS modification timestamps — most recent file mod date
- If no git changes and no recent modifications → omit section

### Footer (always shown)

```
Last computed: 2026-02-15 23:35 UTC
```

From `audit:l2:quality._meta.timestamp` or similar.

---

## Architecture

### Two Rendering Contexts, Shared Data Layer

```
┌──────────────────────────────────────────────────────────────┐
│                    SHARED (Python)                            │
│                                                              │
│  audit_directive.py                                          │
│  ├── _resolve_scope(file_path, modules) → AuditScope         │
│  ├── _load_all_data(project_root, scope, source) → FullData  │
│  │     ├── audit cache (quality, risks, structure, scores)   │
│  │     ├── testing cache                                     │
│  │     ├── git cache                                         │
│  │     └── live file system scan                             │
│  ├── _filter_to_scope(full_data, scope) → ScopedData         │
│  └── render_html(scoped_data) → str                          │
│                                                              │
│  Called from:                                                 │
│  1. Preview endpoint (Python, in-process)                    │
│  2. Build enrichment pass (Python, writes data.json)         │
│                                                              │
├──────────────────────────────────────────────────────────────┤
│           DOCUSAURUS BUILD (JavaScript)                      │
│                                                              │
│  remark-audit-data.mjs                                       │
│  ├── Registered as beforeDefaultRemarkPlugin                 │
│  ├── Reads _audit_data.json (pre-computed by Python)         │
│  └── Transforms :::audit-data AST nodes → HTML nodes         │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### Context 1: Admin Preview (Python — fully in-process)

**Where:** `src/ui/web/routes/content/preview.py` → `content_preview()`

**Flow:**
1. Read file content
2. `auto_inject_directive()` — injects `:::audit-data\n:::` TEXT at top for module files
3. `resolve_audit_directives()` — replaces directive with rendered HTML in `preview_content`
4. Return `content` (with directive text for raw mode) + `preview_content` (with HTML for preview mode)

**Frontend:**
- Raw mode: shows `data.content` in Monaco → user sees `:::audit-data` text
- Preview mode: shows `renderMarkdown(data.preview_content || data.content)` → user sees rendered health card
- `<details>` HTML passes through `marked.js` as raw HTML

### Context 2: Docusaurus Build (Python staging + JS remark plugin)

**Phase A: Python pre-compute during staging**
- Pass 5.5 in `smart_folder_enrichment.py`: inject `:::audit-data` into module `index.md`
- `precompute_audit_data()`: for each file with directive, resolve scope + load + filter + render
- Write `_audit_data.json` to workspace root

**Phase B: JS remark plugin transforms AST**
- `remark-audit-data.mjs` reads `_audit_data.json`
- Visits `:::audit-data` container directive nodes
- Replaces with pre-computed HTML

---

## Data Structures

### `AuditScope` (unchanged)

```python
@dataclass
class AuditScope:
    module: str            # "core"
    sub_path: str          # "services/audit"
    source_prefix: str     # "src/core/services/audit"
    module_path: str       # "src/core"
```

### `ScopedAuditData` (expanded)

```python
@dataclass
class ScopedAuditData:
    # ── Identity ──
    scope: AuditScope
    source_label: str      # "Local" / "Saved" / "N/A"

    # ── Section 2: Module Health ──
    health_score: float    # Average of scoped file_scores
    file_count: int        # Live FS count
    total_lines: int       # Live FS total
    total_functions: int   # From structure module metadata
    total_classes: int     # From structure module metadata
    cached_file_count: int # From cache, for diff detection
    subcategory_averages: dict[str, float]  # {docstrings: 9.2, nesting: 5.4, ...}
    worst_files: list[dict]  # Bottom 3: [{file, score, breakdown}]

    # ── Context ──
    project_quality_score: float | None
    project_complexity_score: float | None
    quality_trend: str | None  # "stable" / "improving" / "declining"

    # ── Section 3: Hotspots ──
    hotspots: list[dict]   # Filtered, all severities
    hotspot_count: int     # Total (not just displayed)

    # ── Section 4: Risk Findings ──
    findings: list[dict]   # ONLY file-scoped findings matching prefix
    risk_summary: dict     # {total, critical, high, medium, info}

    # ── Section 5: Dependencies ──
    deps_outbound: list[dict]  # [{module_name, strength, import_count}] deduped
    deps_inbound: list[dict]   # [{module_name, strength, import_count}] deduped

    # ── Section 6: Library Usage ──
    libraries: list[dict]  # [{name, files: [basename1, basename2]}]

    # ── Section 7: Test Coverage ──
    test_files: list[str]  # Test file paths matching this scope
    test_ratio: float | None  # Project-wide ratio for context
    test_framework: str | None  # "pytest" etc.

    # ── Section 8: Development Activity ──
    git_modified: list[str]   # Modified files in scope
    git_staged: list[str]     # Staged files in scope
    git_untracked: list[str]  # Untracked files in scope
    last_modified_date: str | None  # Most recent file mod date
    last_modified_file: str | None  # Which file was most recently modified

    # ── Footer ──
    computed_at: str | None  # From cache _meta timestamp
```

---

## Scope Auto-Resolution

Uses `_match_module(file_path, modules)` from `smart_folders.py`:

| File path                            | Module | Sub-path        | Filter prefix          |
|--------------------------------------|--------|-----------------|------------------------|
| `src/ui/cli/audit/README.md`        | `cli`  | `audit`         | `src/ui/cli/audit`     |
| `src/ui/cli/README.md`              | `cli`  | (root)          | `src/ui/cli`           |
| `src/core/services/vault/README.md` | `core` | `services/vault`| `src/core/services/vault` |
| `src/core/services/audit/README.md` | `core` | `services/audit`| `src/core/services/audit` |
| `src/ui/web/README.md`              | `web`  | (root)          | `src/ui/web`           |
| `src/adapters/shell/README.md`      | `adapters` | `shell`     | `src/adapters/shell`   |

---

## Edge Cases

| Case | Behavior |
|------|----------|
| No audit data (never scanned) | Show: "📊 Audit data not available — run a scan" |
| File outside all modules | No directive injected, no rendering |
| No hotspots in scope | Omit Hotspots section |
| No scoped findings (all project-wide) | Omit Risk Findings section |
| No cross-boundary deps | Omit Dependencies section |
| No libraries used in scope | Omit Library Usage section |
| No test files matching scope | Show "⚠ No test files found for this scope" |
| No git changes in scope | Omit Development Activity section |
| Live FS file count ≠ cached count | Note: "16 files (cache: 12 — re-scan recommended)" |
| Multiple directives in one file | Each resolved independently |

---

## Rendered HTML Structure

```html
<details class="audit-data-block">
<summary>📊 <strong>Audit Data</strong> — Health: 8.3/10 · 22 hotspots
 · Source: Local</summary>

<div class="audit-data-content" style="padding:0.75rem;
 font-size:0.85rem;line-height:1.5">

<!-- Section 2: Module Health -->
<div style="margin-bottom:0.75rem">
<strong>Module Health</strong>
<span style="float:right;font-size:0.8rem;color:#888">
 16 files · 5,991 lines</span>
<div style="background:#333;border-radius:4px;height:8px;
 margin-top:0.4rem;overflow:hidden">
  <div style="width:83%;height:100%;
   background:linear-gradient(90deg,#4caf50,#8bc34a)"></div>
</div>
<span style="font-size:0.8rem">8.3 / 10</span>
<span style="font-size:0.75rem;color:#888;margin-left:1rem">
 Project avg: 8.2</span>
</div>

<div style="margin-bottom:0.5rem;font-size:0.8rem">
<strong style="font-size:0.85rem">Quality Breakdown</strong>
<table style="width:100%;font-size:0.8rem;margin-top:0.25rem">
<tr><td>docstrings</td><td>█████████░ 9.2</td></tr>
<tr><td>function_length</td><td>███████░░░ 7.8</td></tr>
<tr><td style="color:#e57373">nesting</td>
    <td style="color:#e57373">█████░░░░░ 5.4 ← weakest</td></tr>
<tr><td>comments</td><td>█████████░ 9.4</td></tr>
<tr><td>type_hints</td><td>████████░░ 8.1</td></tr>
</table>
</div>

<div style="margin-bottom:0.75rem;font-size:0.8rem">
<strong>Weakest Files</strong>
<ul style="margin:0.25rem 0;padding-left:1.2rem">
<li>⚠ <code>models.py</code> — 7.8/10 (docstrings: 1.0)</li>
<li>⚠ <code>__init__.py</code> — 7.8/10 (type_hints: 0.0)</li>
<li>⚠ <code>l1_classification.py</code> — 8.1/10 (nesting: 2.0)</li>
</ul>
</div>

<!-- Section 3: Hotspots -->
<div style="margin-bottom:0.75rem">
<strong>Hotspots</strong>
<span style="float:right;font-size:0.75rem;color:#888">22 total</span>
<div style="margin-top:0.25rem;font-size:0.8rem">
<div style="color:#e57373;font-weight:600;margin:0.25rem 0">Critical</div>
<ul style="margin:0;padding-left:1.2rem">
<li>⚠ <code>python_parser.py</code> → parse_file — 172 lines (long function)</li>
<li>⚠ <code>scoring.py</code> → _quality_score — 151 lines (long function)</li>
<li>⚠ <code>l1_classification.py</code> → _extract_all_deps — depth 8 (deep nesting)</li>
<li>⚠ <code>l0_detection.py</code> → _detect_os — depth 7 (deep nesting)</li>
</ul>
<div style="color:#ffb74d;font-weight:600;margin:0.5rem 0 0.25rem">Warning</div>
<ul style="margin:0;padding-left:1.2rem">
<li>⚠ <code>l1_classification.py</code> — 512 code lines (large file)</li>
<li>⚠ <code>l1_classification.py</code> → l1_structure — 131 lines (long function)</li>
<li>⚠ <code>l2_risk.py</code> → _security_findings — 116 lines (long function)</li>
<li>⚠ <code>l2_quality.py</code> → _detect_hotspots — 89 lines (long function)</li>
<li>⚠ <code>l2_repo.py</code> → _repo_health_score — 88 lines (long function)</li>
<li><em>...and 13 more</em></li>
</ul>
</div>
</div>

<!-- Section 4: Risk Findings (ONLY if scoped findings exist) -->
<!-- OMITTED if no findings have files matching prefix -->

<!-- Section 5: Dependencies -->
<div style="margin-bottom:0.75rem">
<strong>Dependencies</strong>
<div style="margin-top:0.25rem;font-size:0.8rem">
<div style="margin-bottom:0.25rem;color:#888">
 Outbound (this code imports from)</div>
<span class="dep-pill outbound">→ config (strong · 12 imports)</span>
<span class="dep-pill outbound">→ services (moderate · 5 imports)</span>
<div style="margin:0.25rem 0;color:#888">
 Inbound (other code imports this)</div>
<span class="dep-pill inbound">← cli (strong · 18 imports)</span>
<span class="dep-pill inbound">← web (moderate · 8 imports)</span>
</div>
</div>

<!-- Section 6: Library Usage -->
<div style="margin-bottom:0.75rem">
<strong>Third-Party Libraries</strong>
<ul style="margin:0.25rem 0;padding-left:1.2rem;font-size:0.8rem">
<li><code>distro</code> — l0_detection.py</li>
<li><code>tomli</code> — l1_classification.py</li>
</ul>
</div>

<!-- Section 7: Test Coverage -->
<div style="margin-bottom:0.75rem">
<strong>Test Coverage</strong>
<div style="font-size:0.8rem;margin-top:0.25rem">
⚠ No test files found for this scope
<br><span style="color:#888">Project test ratio: 0.12 · Framework: pytest</span>
</div>
</div>

<!-- Section 8: Development Activity -->
<div style="margin-bottom:0.75rem">
<strong>Development Activity</strong>
<div style="font-size:0.8rem;margin-top:0.25rem">
Last modified: 2026-03-01 (l2_risk.py) · 3 days ago
</div>
</div>

<!-- Footer -->
<div style="margin-top:0.5rem;font-size:0.75rem;color:#666;
 border-top:1px solid #333;padding-top:0.4rem">
Last computed: 2026-02-15 23:35 UTC</div>

</div>
</details>
```

All styles inline — no external CSS dependency. Works in marked.js,
Docusaurus MDX, and raw GitHub markdown.

---

## Files to Create / Modify

| File | Action | Purpose |
|------|--------|---------|
| `src/core/services/pages_builders/audit_directive.py` | **Rewrite** `_load_all_data()`, `_filter_to_scope()`, `render_html()` | Full data gathering from all 7 sources, proper filtering, rich rendering |
| `src/core/services/pages_builders/templates/docusaurus/src/plugins/remark-audit-data.mjs` | Exists | Remark plugin for Docusaurus build |

## No Changes Needed

| File | Why |
|------|-----|
| `preview.py` | Current flow is correct (inject directive text → resolve to preview_content) |
| `_preview.html` | Current change is correct (`data.preview_content \|\| data.content`) |
| `smart_folder_enrichment.py` | Pass 5.5 already injects directive for build |
| `docusaurus.py` | Precompute already wired |

---

## Implementation Order

1. **Expand `ScopedAuditData`** — add all new fields (subcategory averages, worst files, libraries, tests, git, live FS)
2. **Rewrite `_load_all_data()`** — pull from all 7 data sources, not just audit cache
3. **Rewrite `_filter_to_scope()`** — proper scoping for every data source
4. **Fix cross-dep dedup** — collapse, label with module names, sum import counts
5. **Fix findings** — only file-scoped, omit project-wide
6. **Add library_usage filtering** — scope by prefix
7. **Add test coverage matching** — find test files for scope
8. **Add live FS scan** — real file count, lines, modification dates
9. **Add git activity** — filter modified/staged/untracked by prefix
10. **Rewrite `render_html()`** — all 8 sections with rich formatting
11. **Verify end-to-end** — restart server, preview a module README, validate output

---

## NPM Dependencies for Build

| Package | Version | Why |
|---------|---------|-----|
| `remark-directive` | `^3.0.0` | Parses `:::` container directives into AST nodes |
| `unist-util-visit` | `^5.0.0` | Visits/transforms AST nodes in the remark plugin |
