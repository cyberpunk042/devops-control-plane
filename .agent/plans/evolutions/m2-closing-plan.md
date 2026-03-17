# M2 Closing Plan — Polish, Quality, Documentation

> Status: PLAN
> Last updated: 2026-03-16

---

## Context

M2 is functionally complete:
- Backend: 31 files, 5500 lines — scanner, tree, pipeline, 9 adapters, 5 parsers, version intel, graph, venv detection
- Frontend: 3 templates (1966 lines), CSS, dashboard card, modal with 7 components
- Routes: 18 endpoints
- Mediator: 5 nodes (manifests, versions, installed, tree, summary, venvs)

What remains: polish, edge cases, quality, documentation.

---

## Remaining Items

### 1. State persistence across modal opens
**Problem:** Closing and reopening the modal loses expanded tree nodes, selected scope, terminal output.
**Fix:**
- Store `_depExpanded`, `_depSelectedScope`, `_depSelectedPkg` in sessionStorage
- On modal open, restore from sessionStorage before rendering
- Terminal output: store last operation's lines in a variable (not sessionStorage — too large)
- On reopen, if last terminal output exists, render it in the terminal area

**Scope:** `_dep_modal.html` — `depOpenModal()` + `depCloseModal()` + new `_depSaveState()`/`_depRestoreState()`
**Estimate:** ~30 lines

### 2. Tree search/filter
**Problem:** 49+ packages, finding one is tedious.
**Fix:**
- Search input at top of tree panel (below the "Scope" header)
- Filters tree nodes by name — hides non-matching packages and collapses ecosystems with no matches
- Debounced (200ms)
- Shows "N matches" indicator
- Clear button (✕) restores full tree

**Scope:** `_dep_modal.html` — new `_depFilterTree()`, CSS for `.dep-search-input`
**Estimate:** ~40 lines JS + ~10 lines CSS

### 3. Bulk selection shortcuts
**Problem:** Checkboxes exist but no quick way to "select all outdated" or "select all missing."
**Fix:**
- Small dropdown next to the Global checkbox: "Check all" | "Check outdated" | "Check missing" | "Uncheck all"
- Or: filter pills at the top of the tree: `[all] [outdated] [missing] [deprecated]`
- Clicking a filter checks those ecosystems that have matching packages

**Scope:** `_dep_modal.html` — extend tree header
**Estimate:** ~30 lines

### 4. Operation history in modal
**Problem:** Terminal shows LAST operation only. No history of what was done.
**Fix:**
- Small collapsible section below the terminal: "Recent operations"
- Pulls from timeline events (filter `dependency.*` event types)
- Shows last 5-10 operations with timestamp, action, scope, status
- Clicking one shows its detail

**Scope:** `_dep_modal.html` — new `_depLoadHistory()`, new API call to `/dependencies/history` or reuse timeline events
**Estimate:** ~50 lines JS, ~20 lines route (if new endpoint needed)

### 5. Graph view testing & polish
**Problem:** The graph view (E10 tab) exists but hasn't been tested in the actual running app.
**Fix:**
- Test the Graph tab with real data
- Fix any rendering issues (SVG sizing, edge positioning)
- Add click interaction: click a package → highlight consuming modules
- Add click interaction: click a module → highlight its packages
- Handle edge cases: single module (no bipartite needed), no shared deps

**Scope:** `_dep_graph.html` — testing + edge case fixes
**Estimate:** ~40 lines

### 6. README documentation
**Problem:** No README for the `dependency_mgr` service.
**Fix:**
- Write README to project standard (450+ lines)
- 8 required sections: title, how it works (ASCII diagrams), file map, per-file docs, dependency graph, consumers, design decisions, domain-specific sections
- Must read every file before writing (README standard rule)
- Key sections: adapter protocol, pipeline lifecycle, version intel flow, venv targeting, tree model

**Scope:** `src/core/services/dependency_mgr/README.md`
**Estimate:** 500+ lines

### 7. Update milestone plans
**Problem:** Plan files still say "SCAFFOLDED" or "DESIGN v1" — need to reflect actual status.
**Fix:**
- `milestone-2-dependency-intelligence.md` → Status: COMPLETE
- `m2-foundation-plan.md` → Status: COMPLETE
- `m2-adapters-plan.md` → Status: COMPLETE
- `m2-ui-plan.md` → Status: COMPLETE
- `INDEX.md` → Update M2 row
- Add a completion summary with actual file counts, line counts, feature list

**Scope:** 5 plan files
**Estimate:** ~50 lines of edits

---

## Execution order

```
1 → State persistence (small, immediate UX win)
2 → Tree search (high UX value, small code)
3 → Bulk selection (nice-to-have, builds on search)
4 → Operation history (medium effort, good observability)
5 → Graph polish (test + fix)
6 → README (big but mechanical — read everything, document)
7 → Update plans (last — reflects everything above)
```

Items 1-3 can be done in one pass. Item 4 needs a bit more thought. Items 5-7 are independent.

---

## Not in scope (future)

- Specialized output parsers for bundler/maven/gradle/mix/dotnet (currently use generic fallback — good enough)
- Version intel for go/cargo/bundler/maven/gradle/mix/dotnet (pip+npm cover the main need)
- Remediation engine extensions for ecosystem-specific issues (the UI shows remediations but the options are basic)
- E10 deep graph analysis (transitive deps, CVE propagation)
- Package lock file generation/management
