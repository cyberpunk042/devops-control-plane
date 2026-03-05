# Remaining 6 Items — Analysis & Plan

> **Created:** 2026-03-02  
> **Status:** Draft — awaiting user approval before execution  
> **Context:** Progress tracker shows 84/90 done, 6 remaining

---

## Overview

| # | Item | Type | Risk | Effort |
|---|------|------|------|--------|
| 32 | `chat/` split + README | Backend refactor | Low | Medium |
| 33 | `generators/` split + README | Backend refactor | Low | Medium |
| 36 | `debug/` script split | Frontend refactor | Medium | Medium |
| 37 | CSS split | Frontend refactor | High | Large |
| 38 | Tests cleanup | Maintenance | Low | Medium |
| 39 | Stale docs | Cleanup | Low | Small |

---

## Item 32 — `chat/` Split + README

### Current State

```
chat/
├── __init__.py       59 lines  — re-exports from all sub-modules
├── models.py        100 lines  — ChatMessage, MessageFlags, Thread dataclasses
├── chat_crypto.py   139 lines  — encrypt_text, decrypt_text, is_encrypted
├── chat_ops.py      731 lines  — send, list, thread CRUD, push/pull, delete
├── chat_refs.py   1,280 lines  — @-reference parsing, resolution, autocomplete
└── Total          2,309 lines
```

### What the tracker says: "Split first"

### Analysis

**`chat_refs.py` (1,280 lines)** has three clear responsibility clusters:

1. **Parsing** (lines 25-110): `parse_refs()`, `parse_ref_parts()`, regex patterns
   - ~85 lines
2. **Resolution** (lines 113-462): `resolve_ref()` + 7 internal resolvers
   (`_resolve_run`, `_resolve_thread`, `_resolve_trace`, `_resolve_commit`,
   `_resolve_branch`, `_resolve_audit`, `_resolve_release`, `_resolve_code`)
   - ~350 lines
3. **Autocomplete** (lines 463-1280): `autocomplete()` + 11 internal
   autocompleters (`_autocomplete_runs`, `_autocomplete_threads`, etc.)
   - ~817 lines

**Natural split:**

```
chat/
├── __init__.py          (updated re-exports)
├── models.py            (unchanged)
├── chat_crypto.py       (unchanged)
├── chat_ops.py          (unchanged — 731 lines is borderline but coherent)
├── refs_parse.py        (~85 lines — parsing + regex)
├── refs_resolve.py      (~350 lines — resolution engine)
└── refs_autocomplete.py (~817 lines — autocomplete engine)
```

**`chat_ops.py` (731 lines)** — leave as-is. It's one coherent module
covering the full message/thread lifecycle. Splitting it would create
artificial boundaries.

### Consumer impact

9 consumer files. All import from `chat/__init__.py` except 2 that
reach into `chat_ops._thread_dir` (private, would need update) and
1 that reaches into `chat_crypto.decrypt_text`.

### Proposed approach

1. Split `chat_refs.py` → `refs_parse.py`, `refs_resolve.py`, `refs_autocomplete.py`
2. Update `__init__.py` re-exports (no consumer changes needed)
3. Create backward-compat re-export in old `chat_refs.py` (or update
   the 2 test files that import directly)
4. Write README (450+ lines)

### Risk: LOW

- Pure internal split, public API unchanged
- No route/CLI/web changes needed
- Tests import from package-level `__init__.py` mostly

---

## Item 33 — `generators/` Split + README

### Current State

```
generators/
├── __init__.py            6 lines  — empty
├── compose.py           105 lines  — docker-compose.yml generation
├── dockerfile.py        510 lines  — Dockerfile generation
├── dockerignore.py      166 lines  — .dockerignore generation
├── github_workflow.py 1,081 lines  — GitHub Actions workflow generation
└── Total              1,868 lines
```

### Analysis

**`github_workflow.py` (1,081 lines)** has 6 clear responsibility sections:

1. **Stack-specific CI jobs** (lines 19-224): Python, Node, Go, Rust, Java
   - ~205 lines, 7 functions + dispatch map
2. **Docker CI** (lines 225-421): `_docker_ci_job()`, `generate_docker_ci()`
   - ~196 lines
3. **K8s Deploy CI** (lines 422-623): kubectl, skaffold, helm deploy jobs
   - ~201 lines
4. **Terraform CI** (lines 624-760): terraform init/validate/plan/apply
   - ~136 lines
5. **DNS/CDN post-deploy** (lines 761-909): DNS verify + CDN purge
   - ~148 lines
6. **Public API + Lint** (lines 910-1081): `generate_ci()`, `generate_lint()`
   - ~171 lines

**Natural split:**

```
generators/
├── __init__.py          (updated — re-export public API)
├── compose.py           (unchanged)
├── dockerfile.py        (unchanged)
├── dockerignore.py      (unchanged)
├── ci_stacks.py         (~205 lines — per-language CI job defs)
├── ci_docker.py         (~196 lines — Docker build/push CI)
├── ci_k8s.py            (~201 lines — K8s deploy CI)
├── ci_terraform.py      (~136 lines — Terraform CI)
├── ci_deploy_post.py    (~148 lines — DNS verify + CDN purge)
└── ci_compose.py        (~171 lines — generate_ci, generate_lint, assembly)
```

### Consumer impact

10 consumer import statements across 4 files:
- `docker/generate.py` → imports from `generators.dockerfile`, `generators.dockerignore`, `generators.compose`
- `ci/ops.py` → imports `generate_ci`, `generate_lint`, `generate_terraform_ci` from `generators.github_workflow`
- `ci/compose.py` → imports from `generators.github_workflow`
- `wizard/setup_ci.py` → imports `_resolve_job` from `generators.github_workflow`

### Proposed approach

1. Split `github_workflow.py` into 6 files as described
2. Update `__init__.py` to re-export the public API
3. Update 3 consumer files to import from new locations
4. Keep `github_workflow.py` as backward-compat shim for any test imports
5. Write README (450+ lines)

### Risk: LOW

- Public API functions don't change signatures
- Docker generators (compose, dockerfile, dockerignore) untouched
- Consumer updates are straightforward import path changes

---

## Item 36 — `debug/` Script Split

### Current State

```
templates/scripts/
├── _debugging.html         1,145 lines  — Debug tools JS
├── _stage_debugger.html      702 lines  — Stage debugger JS
```

These are JavaScript files inside `.html` template includes (raw JS
within the shared `<script>` block opened by `_globals.html`).

### Analysis

These are frontend JavaScript files. Splitting them means:
- Understanding the function boundaries within each file
- Ensuring no global variable dependencies between splits
- Template inclusion order matters

**I have NOT read these files in detail yet.** Before proposing a split,
I need to read both files entirely to understand their internal structure.

### Proposed approach

1. Read both files fully
2. Identify function clusters and dependencies
3. Propose split plan for approval
4. Split with careful template include order
5. Test in browser that nothing breaks
6. Write README for the scripts/ directory

### Risk: MEDIUM

- Frontend JS changes require visual verification
- Template include order is critical
- Global scope dependencies between JS files are common
- User rule: NEVER TRY TO OPEN THE BROWSER — we can't visually verify

### Decision needed

Should we do this? Given we can't visually verify, this carries
more risk than backend splits. Alternative: document as-is (README
only, no split).

---

## Item 37 — CSS Split

### Current State

```
static/css/
└── admin.css    5,948 lines  — ALL CSS in one file
```

### Analysis

Splitting a 5,948-line CSS file carries the highest regression risk of
all remaining items. CSS has:
- Cascade order dependencies (later rules override earlier ones)
- Specificity interactions between sections
- Media query groupings that may span logical sections

### Proposed approach

1. Read the full file to identify logical sections
2. Propose a split into ~8-12 files (layout, cards, modals, forms,
   wizard, vault, debugging, animations, responsive)
3. Create an `admin-bundle.css` or update template to load in correct order
4. Test thoroughly

### Risk: HIGH

- CSS cascade order is fragile — wrong file loading order = visual bugs
- 5,948 lines means many hidden interactions
- Browser verification is needed but prohibited by user rules
- One wrong split = entire admin panel looks broken

### Decision needed

**Recommend: SKIP or DEFER.** This is the highest-risk item and
provides the least value. The CSS works. Splitting it is a nice-to-have
refactor but could easily introduce regressions we can't visually verify.

Alternative: Document the sections within the existing file (add CSS
comment headers) without splitting.

---

## Item 38 — Tests Cleanup

### Current State

```
tests/
├── 30+ test files
├── ~31,600 lines (tests/)
├── ~10,350 lines (tests/integration/)
└── Total: ~42,000 lines
```

### Analysis

The tracker says "large test files mirror old paths." This means tests
import from pre-refactor flat-file paths like:
- `from src.core.services.k8s_detect import ...` (shim)
- `from src.core.services.docker_containers import ...` (shim)
- `from src.core.services.terraform_ops import ...` (shim)

These all **still work** because backward-compat shims exist. The tests
are not broken — they're just importing via the compat layer.

### Proposed approach

1. Scan all test imports to find which use old flat paths vs new package paths
2. Batch-update imports to use the new package paths
3. Verify all tests still pass

### Risk: LOW

- Tests are not user-facing
- Import path updates are mechanical
- Tests can be run to verify

### Decision needed

Is this worth doing now? The shims make everything work. The benefit
is cleanliness — when we eventually remove shims, tests won't break.

**Recommend: DO IT** — it's mechanical, low risk, and prevents future
breakage when shims are removed.

---

## Item 39 — Stale Docs

### Current State

```
docs/
├── ADAPTERS.md               201 lines  (2026-02-16)
├── ANALYSIS.md               777 lines  (2026-02-16)
├── ARCHITECTURE.md           284 lines  (2026-02-15)
├── AUDIT_ARCHITECTURE.md     505 lines  (2026-02-15)
├── AUDIT_PLAN.md             667 lines  (2026-02-15)
├── CONSOLIDATION_AUDIT.md    303 lines  (2026-02-15)
├── CONTENT.md                136 lines  (2026-02-15)
├── DESIGN.md                 317 lines  (2026-02-15)
├── DEVELOPMENT.md            203 lines  (2026-02-15)
├── DEVOPS_UI_GAP_ANALYSIS.md 265 lines  (2026-02-15)
├── INTEGRATION_GAP_ANALYSIS.md 266 lines (2026-02-15)
├── PAGES.md                  222 lines  (2026-02-15)
├── QUICKSTART.md             118 lines  (2026-02-15)
├── STACKS.md                 206 lines  (2026-02-15)
├── VAULT.md                  139 lines  (2026-02-15)
├── WEB_ADMIN.md              241 lines  (2026-02-15)
└── Total: 16 files, ~4,849 lines
```

All dated Feb 15-16. The refactor happened after that. These docs may
reference old file paths, old architecture, or describe planned work
that's now complete.

### Proposed approach

1. Read each doc to assess accuracy
2. Categorize: still-accurate, needs-update, or archive-candidate
3. Update what's still relevant, archive what's obsolete
4. Create a docs/README.md index

### Risk: LOW — these are standalone documentation files

### Decision needed

How deep should we go? Options:
- **A) Full review + rewrite** — read every doc, update to current state
- **B) Triage only** — read, categorize, archive obsolete, leave accurate ones
- **C) Skip** — they're historical context, not actively harmful

**Recommend: B (triage)** — archive clearly obsolete docs, update still-relevant
ones, create an index. Don't rewrite from scratch unless needed.

---

## Proposed Execution Order

Based on risk and dependencies:

| Order | Item | Why this order |
|-------|------|---------------|
| 1 | **#32 chat/ split** | Cleanest backend split, low risk, self-contained |
| 2 | **#33 generators/ split** | Similar pattern, low risk, few consumers |
| 3 | **#38 tests cleanup** | Mechanical, verifiable, prepares for shim removal |
| 4 | **#39 stale docs triage** | Low effort, low risk |
| 5 | **#36 debug/ scripts** | Medium risk, needs your decision on approach |
| 6 | **#37 CSS split** | Highest risk, recommend DEFER |

---

## Awaiting Your Decisions

1. **chat/ split:** Agree with splitting `chat_refs.py` into 3 files while
   leaving `chat_ops.py` as-is?
2. **generators/ split:** Agree with splitting `github_workflow.py` into 6
   files while leaving Docker generators as-is?
3. **debug/ scripts:** Split (medium risk) or document-only (safe)?
4. **CSS split:** Defer or attempt?
5. **tests cleanup:** Do it or skip?
6. **stale docs:** Full review, triage, or skip?
7. **Execution order:** Agree with 32 → 33 → 38 → 39 → 36 → 37?
