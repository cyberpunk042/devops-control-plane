# Rules, Workflows & Documentation Overhaul Plan

> Created: 2026-03-05
> Trigger: Post-mortem #14 + glossary session failures
> Scope: FULL — rules, workflows, reference docs, general docs

---

## Problem Statement

14 AI instances have been obliterated on this project. Despite:
- 7 rule files (~12KB)
- 15 workflow files (~100KB)
- 14 post-mortems (~100KB)
- Comprehensive discipline protocols (800+ lines)

The same failures keep happening: AI abstracts instead of reading code,
guesses runtime state instead of tracing it, layers fixes instead of
understanding the problem, and conflates different concepts.

**Root causes identified:**

1. **`before-any-change.md` is backend-only** — no frontend coverage
2. **No code discovery workflow** — rules say "read code" but not HOW
3. **No project state reference** — JS globals, namespaces, path types undocumented
4. **Too many documents say the same thing** — 50+ pages of behavioral rules, diluted
5. **Discipline protocols are 800+ lines** — AI can't hold it all while coding
6. **No scope-specific routing** — all workflows flat, AI picks wrong ones
7. **No mandatory state trace** — AI can satisfy all checklists without knowing variable values
8. **General docs may have staleness** — specs, guides, READMEs may not reflect current state

---

## Phase 1: Rules Restructuring (Days 1-2)

### Goal
Consolidate, deduplicate, and add missing constraints.
Rules should be SHORT, ABSOLUTE, and IMMEDIATELY actionable.

### Current State (7 files, ~12KB)

| File              | Lines | Status         | Action    |
|-------------------|-------|----------------|-----------|
| `core.md`         | 37    | Mix of concerns | Refactor  |
| `main.md`         | 22    | Good, keep      | Keep      |
| `no-abstraction.md` | 34  | Good, keep      | Keep      |
| `meanings.md`     | 7     | Good, keep      | Keep      |
| `assistant.md`    | 20    | Scoped, keep    | Keep      |
| `refactoring-integrity.md` | 157 | Good, keep | Keep    |
| `STOP-CONTEXT-WAS-TRUNCATED.md` | 30 | Good | Keep     |

### New Rules to Create

#### 1.1 `read-before-write.md` — NEW
**Purpose:** Hard constraint preventing code changes without reading.

Core content:
```
ARTICLE 1: Before modifying ANY function, READ all callers (grep_search)
ARTICLE 2: Before calling ANY function, READ its definition (view_code_item)
ARTICLE 3: Before using ANY global variable, TRACE what sets it
ARTICLE 4: STATE the values you expect at the call site BEFORE writing code
ARTICLE 5: If you cannot state the value of a variable, you cannot write
           code that uses it
```

Self-test:
```
Q1: Did I read the function I'm modifying? (Not from memory — from view_file)
Q2: Did I read every caller of this function?
Q3: Can I state the exact value of every global variable at the call site?
Q4: Did I read every function I'm about to call?
→ If ANY answer is NO → STOP. Read first.
```

#### 1.2 `one-change-one-test.md` — NEW
**Purpose:** Prevent cascading fix-on-fix failures.

Core content:
```
ARTICLE 1: Make ONE change. Test it. Confirm it works. Then move on.
ARTICLE 2: If a change breaks, DO NOT add another change on top.
           Revert and understand why it broke.
ARTICLE 3: If you've made 3+ changes to fix the same thing, STOP.
           You don't understand the problem.
ARTICLE 4: Every change must be independently verifiable by the user.
```

### Rules to Refactor

#### 1.3 `core.md` — REFACTOR
**Problem:** Mixes truncation protocol, hierarchy, and domain architecture.
**Action:** Split into:
- Truncation stays (already has its own file, remove duplicate)
- Hierarchy stays (user is master, AI is slave)
- Domain architecture (`CLI <-> TUI <-> WEB`) → move to reference doc
- Remove duplicate cross-references that just list other files

---

## Phase 2: Workflows Restructuring (Days 2-4)

### Goal
Deduplicate, scope-route, and add missing technical workflows.
Workflows should be MECHANICAL STEPS, not prose.

### Current State (15 files + 14 post-mortems, ~200KB total)

| File                            | Lines | Status              | Action      |
|---------------------------------|-------|---------------------|-------------|
| `ai-discipline-protocol-0.md`  | 387   | Comprehensive, long | Consolidate |
| `ai-discipline-protocol-1.md`  | 343   | Overlaps with 0     | Consolidate |
| `ai-discipline-protocol-2-contract.md` | 73 | Good, compact | Keep (evolve)|
| `before-any-change.md`         | 125   | Backend only        | Refactor    |
| `think-before-acting.md`       | 118   | Good, keep          | Keep        |
| `debug-by-tracing.md`          | 85    | Good, keep          | Keep        |
| `no-abstraction.md`            | 219   | Overlaps with rule  | Consolidate |
| `why-do-AI-get-unplugged.md`   | 162   | Narrative, useful   | Archive     |
| `readme-standard.md`           | ~100  | Scoped, good        | Keep        |
| `tool-coverage-audit.md`       | ~200  | Scoped, good        | Keep        |
| `tool-remediation-audit.md`    | ~200  | Scoped, good        | Keep        |
| `tool-spec-self-check.md`      | ~100  | Scoped, good        | Keep        |
| `audit-evolution.md`           | ~250  | Scoped, good        | Keep        |
| `STOP-CONTEXT-WAS-TRUNCATED.md`| ~60   | Good, keep          | Keep        |
| `AI-POSTMORTEM-IMPORTANT-13.md`| 8     | Stub, points to failure | Keep   |
| `failures/` (14 files)         | ~1000 | Historical, keep    | Keep        |

### Consolidation Plan

#### 2.1 Merge Discipline Protocols → `discipline.md`
**Action:** Merge `protocol-0`, `protocol-1`, and `protocol-2` into ONE file.
**Why:** 800+ lines split across 3 files with significant duplication.
**Target:** ~300 lines, deduplicated, organized by topic not by part number.

Structure:
```
# AI Discipline Protocol (Consolidated)

## 1. Identity & Hierarchy (from Part 1) — ~20 lines
## 2. Listening Protocol (from Part 2) — ~30 lines
## 3. Stop Protocol (from Part 3) — ~20 lines
## 4. Request Processing (from Part 4) — ~30 lines
## 5. Anti-Rogue Safeguards (from Part 5) — ~30 lines
## 6. Code Change Protocol (from Part 6) — ~30 lines
## 7. Failure Patterns (from Part 7, deduplicated) — ~40 lines
## 8. Communication (from Part 8, trimmed) — ~20 lines
## 9. Recovery (from Part 10) — ~20 lines
## 10. Quick Reference Card (from Part 15) — ~20 lines
## 11. Contract (from Part 14) — ~20 lines
```

After merge: archive originals to `workflows/archive/`.

#### 2.2 Merge No-Abstraction Docs
**Current:** Rule (`rules/no-abstraction.md`, 34 lines) + Workflow (`workflows/no-abstraction.md`, 219 lines)
**Action:** Keep rule as-is (it's the summary). Trim workflow to remove
duplication with discipline protocol. Focus workflow on the PROCESSING
ALGORITHM (lines 147-157) and SELF-TEST (lines 169-183) — those are unique.
**Target:** Workflow goes from 219 → ~80 lines.

#### 2.3 Scope-Split `before-any-change.md`
**Current:** 125 lines, all backend (env vars, server patterns, pipeline).
**Action:** Split into scoped checklists:

```
workflows/before-change/
├── common.md          ← Shared steps (read callers, trace state, verify scope)
├── backend.md         ← Current content (env vars, server, pipeline)
├── frontend.md        ← NEW: JS globals, namespaces, template architecture
└── refactoring.md     ← Points to rules/refactoring-integrity.md
```

#### 2.4 Create `before-change/frontend.md` — NEW
**Purpose:** Frontend-specific pre-flight checklist for JS template changes.

Core content:
```
## Before ANY JS Template Change

### 1. Namespace Check
- [ ] Is `contentCurrentPath` a virtual path or real path at this call site?
- [ ] Is `_smartFolderActive` set or null?
- [ ] Is `previewCurrentPath` set or null?
- [ ] Am I comparing paths from the same namespace?

### 2. Caller Trace
- [ ] I have grep'd for ALL callers of the function I'm modifying
- [ ] I have read each caller and noted what arguments they pass
- [ ] I have verified the state of global variables at each call site

### 3. Function Verification
- [ ] Every function I'm calling EXISTS in the codebase (grep_search)
- [ ] I have read each function's definition (view_code_item)
- [ ] I know what each function returns

### 4. Template Architecture
- [ ] scripts/*.html files are RAW JS (no <script> tags)
- [ ] _globals.html opens the script block, _boot.html closes it
- [ ] I am not adding <script> tags inside a scripts/*.html file
```

#### 2.5 Create `code-discovery.md` — NEW
**Purpose:** Mechanical steps for understanding code BEFORE modifying it.

```
## The Discovery Protocol — BEFORE Writing Code

### Step 1: Find the function you need to modify
Use view_code_item or grep_search to locate it.

### Step 2: Read the function's full body
Use view_file with exact line numbers. Do NOT work from memory.

### Step 3: Find ALL callers
grep_search for the function name across the project.
Read EACH caller. Note the arguments and global state at each call site.

### Step 4: Find ALL functions it calls
For each function called inside the body, grep_search and read it.

### Step 5: State the global variables
For EACH global variable used in the function:
- What sets it?
- What is its value at this point in the lifecycle?
- Is it the type you think? (virtual path? real path? null?)

### Step 6: Write your state trace
BEFORE writing code, write out:
"At this call site, contentCurrentPath = 'code-docs/adapters' (virtual),
 _smartFolderActive = {...}, previewCurrentPath = null"

If you CANNOT write this trace → you CANNOT write the code.
```

#### 2.6 Archive Narrative Docs
**Action:** Move `why-do-AI-get-unplugged.md` to `workflows/archive/`.
**Why:** Valuable as history but the LESSONS it teaches are now captured in
the discipline protocol and post-mortems. Keeping it in the active workflow
directory adds noise. Still accessible from archive.

---

## Phase 3: Reference Documents (Days 3-5)

### Goal
Create project state reference docs that the AI can consult when
working in specific areas. These are FACTS, not rules.

### New Reference Docs

#### 3.1 `.agent/reference/frontend-state.md` — NEW
**Purpose:** Map of all frontend JS global variables, their namespaces,
and lifecycles.

Content:
```
# Frontend State Reference

## Global Variables — Content Tab

| Variable | Type | Namespace | Set By | When |
|----------|------|-----------|--------|------|
| contentCurrentPath | string | VIRTUAL or REAL | contentLoadFolder() | Every folder nav |
| previewCurrentPath | string | REAL (filesystem) | contentPreviewFile() | File open |
| contentFolders | array | N/A | _contentSetFolders() | Page load |
| _smartFolderActive | object|null | N/A | _smartFolderClick() | Smart folder click |
| _smartFolderTree | object|null | N/A | _smartFolderRender() | Smart folder load |
| _glossaryContextPath | string|null | REAL or @smart: | _glossaryDeriveContextPath() | Glossary init |
| _glossaryMode | string | N/A | _glossarySwitchMode() | Mode toggle |
| ... (complete inventory) |

## Path Namespaces

### Virtual Paths (Smart Folder Context)
When _smartFolderActive is set, contentCurrentPath uses the smart folder's
virtual namespace: "code-docs/adapters", "code-docs/core"

### Real Paths (Regular Context)
When no smart folder is active, contentCurrentPath is a real filesystem
path: "src/adapters", "docs"

### Translation
Virtual → Real: Use _smartFolderSubPath() to get the subpath,
                then look up module_path from the groups array.
```

#### 3.2 `.agent/reference/web-architecture.md` — NEW
**Purpose:** How the web admin template system works.

Content:
```
# Web Admin Template Architecture

## Template File Structure
templates/
├── partials/          ← HTML fragments (included in pages)
├── scripts/           ← Raw JS files (NOT HTML pages)
│   ├── _globals.html  ← Opens <script> block + global state init
│   ├── content/       ← Content tab JS modules
│   │   ├── _init.html
│   │   ├── _nav.html
│   │   ├── _preview.html
│   │   ├── _glossary.html
│   │   └── _smart_folders.html
│   └── _boot.html     ← Closes </script> block
└── index.html         ← Main SPA template

## CRITICAL: scripts/*.html are RAW JAVASCRIPT
They are concatenated into a single <script> block.
There are NO <script> tags inside these files.
Adding <script> tags causes syntax errors.

## API Routes
src/ui/web/routes/     ← Flask blueprints
├── content/
│   ├── browse.py      ← /api/content/list, /api/content/preview
│   ├── outline.py     ← /api/content/outline, /api/content/glossary
│   └── ...
```

#### 3.3 `.agent/reference/smart-folders.md` — NEW
**Purpose:** How smart folders work — the virtual/real path mapping.

Content:
```
# Smart Folders Reference

## What Smart Folders Are
A smart folder is a virtual grouping that maps a user-friendly path
(e.g., "code-docs") to multiple real filesystem paths (e.g., 
"src/adapters", "src/core", "src/ui/web").

## Path Namespaces
- Virtual: "code-docs/adapters" (what the user sees)
- Real: "src/adapters" (what the filesystem has)

## Key Variables
- _smartFolderActive: the current smart folder config (or null)
- _smartFolderActive._smartRoot: the virtual root (e.g., "code-docs")
- _smartFolderActive.groups[]: array of { module, module_path }
- contentCurrentPath: set to VIRTUAL path when in smart folder

## Translation Functions
- _smartFolderSubPath(path, sf): strips the virtual root → returns "adapters"
- groups.find(g => g.module === subPath): maps module name → real path
```

---

## Phase 4: Workflow Routing & MEMORY Block Updates (Day 4)

### Goal
Update the MEMORY blocks (injected into every conversation) to route
the AI to the RIGHT workflow based on what it's doing.

### 4.1 Update MEMORY[core.md]
Add routing instructions:
```
## Workflow Routing
- Modifying backend Python? → Read workflows/before-change/backend.md
- Modifying frontend JS templates? → Read workflows/before-change/frontend.md
- Refactoring files? → Read rules/refactoring-integrity.md
- Debugging a comparison? → Read workflows/debug-by-tracing.md
- First change in a session? → Read workflows/code-discovery.md
```

### 4.2 Ensure MEMORY blocks reference new consolidated locations
After merging the discipline protocols, update all MEMORY block references
to point to the new locations.

---

## Phase 5: General Docs Audit & Refresh (Days 5-7)

### Goal
Ensure all user-facing docs, specs, and READMEs are current and
accurate against the actual codebase.

### 5.1 Specs Audit

| File | Lines | Last Updated | Action |
|------|-------|--------------|--------|
| `PROJECT_SCOPE.md` | 227 | Unknown | Audit against current features |
| `TECHNOLOGY_SPEC.md` | 217 | Unknown | Audit against current stacks |

**Process:**
- Read each section
- Verify claims against actual source code
- Mark statuses (✅/❌/partial) correctly
- Update any stale references

### 5.2 `docs/` Guides Audit

| File | Lines | Focus |
|------|-------|-------|
| `ARCHITECTURE.md` | 284 | Verify directory layout matches reality |
| `DESIGN.md` | 317 | Verify principles match current practice |
| `WEB_ADMIN.md` | 241 | Verify tab descriptions match current UI |
| `CONTENT.md` | 136 | Verify features (peek, glossary, smart folders) |
| `QUICKSTART.md` | 118 | Verify install steps still work |
| `DEVELOPMENT.md` | 203 | Verify dev setup steps |

**Process per file:**
- Read entire file
- Read the corresponding source code it describes
- Flag discrepancies
- Propose updates (don't fabricate — verify first)

### 5.3 Module READMEs Audit

| File | Lines | Status |
|------|-------|--------|
| `src/adapters/README.md` | 682 | Recently created — verify |
| `src/core/README.md` | 664 | Recently created — verify |
| `src/core/services/README.md` | ? | Check existence/currency |
| `src/ui/cli/README.md` | 711 | Recently created — verify |
| `src/ui/web/README.md` | 594 | Recently created — verify |
| `docs/README.md` | 640 | Recently created — verify |

These were all created recently. Quick spot-check each against the
readme-standard workflow for completeness.

### 5.4 Plans Cleanup (137 files!)

The `.agent/plans/` directory has 137 files. Many may be:
- Completed plans that should be archived
- Outdated plans that reference old architecture
- Duplicate plans that overlap

**Action:**
- Inventory all 137 plans
- Categorize: Active | Completed | Outdated | Duplicate
- Archive completed/outdated plans to `.agent/plans/archive/`
- Keep only active plans in the main directory

---

## Phase 6: Post-Mortem Evolution (Day 7)

### Goal
The 14 post-mortems contain valuable patterns but are becoming noise.
Extract the PATTERNS into a consolidated reference, keep raw post-mortems
as archive.

### 6.1 Create `reference/failure-patterns.md` — NEW
Extract the recurring failure patterns from all 14 post-mortems into
a single reference:

```
# AI Failure Pattern Reference

## Pattern 1: Abstraction Disease
Frequency: 13/14 post-mortems
Symptom: AI reads user's words, abstracts them, solves the abstraction
Prevention: no-abstraction rule + self-test

## Pattern 2: Code-Before-Understand
Frequency: 14/14 post-mortems
Symptom: AI writes code without reading existing code first
Prevention: read-before-write rule + code-discovery workflow

## Pattern 3: Cascading Fixes
Frequency: 8/14 post-mortems
Symptom: Fix #1 breaks → Fix #2 on top → Fix #3 on top → all broken
Prevention: one-change-one-test rule

## Pattern 4: Wrong View/Namespace
Frequency: 5/14 post-mortems
Symptom: AI puts code in wrong view, uses wrong path namespace
Prevention: frontend checklist + state reference

## Pattern 5: API-Over-UI
Frequency: 3/14 post-mortems
Symptom: AI proves API works, assumes UI works
Prevention: discipline protocol §5.4 (tunnel vision trap)

## Pattern 6: Narrative Apology
Frequency: 6/14 post-mortems
Symptom: AI apologizes for 3 paragraphs instead of fixing
Prevention: discipline protocol §7.6 (apology loop)
```

---

## Execution Order

```
Phase 1: Rules (Days 1-2)
├── 1.1 Create read-before-write.md
├── 1.2 Create one-change-one-test.md
└── 1.3 Refactor core.md

Phase 2: Workflows (Days 2-4)
├── 2.1 Consolidate discipline protocols → discipline.md
├── 2.2 Trim no-abstraction workflow
├── 2.3 Create before-change/ directory structure
├── 2.4 Create before-change/frontend.md
├── 2.5 Create code-discovery.md
└── 2.6 Archive narrative docs

Phase 3: Reference Docs (Days 3-5)
├── 3.1 Create reference/frontend-state.md
├── 3.2 Create reference/web-architecture.md
└── 3.3 Create reference/smart-folders.md

Phase 4: Routing & MEMORY (Day 4)
├── 4.1 Update MEMORY[core.md] with routing
└── 4.2 Update all MEMORY references

Phase 5: General Docs Audit (Days 5-7)
├── 5.1 Audit specs (PROJECT_SCOPE, TECHNOLOGY_SPEC)
├── 5.2 Audit docs/ guides
├── 5.3 Spot-check module READMEs
└── 5.4 Plans cleanup (137 files → active/archive)

Phase 6: Post-Mortem Evolution (Day 7)
└── 6.1 Create reference/failure-patterns.md
```

---

## Success Criteria

1. **Rule count:** Max 10 rule files, each < 60 lines (except refactoring-integrity)
2. **Workflow count:** Max 15 active workflow files (excluding archived/scoped)
3. **No duplication:** Zero concepts explained in more than 2 locations
4. **Scope routing:** MEMORY blocks tell the AI which workflow to read for which task
5. **State reference:** AI can look up any frontend global's namespace in < 30 seconds
6. **Plans cleaned:** Active plans < 30 files (rest archived)
7. **Docs verified:** Every claim in docs/ verified against source code

---

## Risk: This Plan Itself

This plan proposes creating/modifying ~20 files. The risk is the same
disease: rushing through, fabricating content, not reading source before
writing reference docs.

**Mitigation:**
- Each reference doc (Phase 3) MUST be written by reading actual source code
- Each doc consolidation (Phase 2) MUST preserve all unique content
- Archiving NEVER deletes — only moves
- Each phase gets user review before proceeding to next
