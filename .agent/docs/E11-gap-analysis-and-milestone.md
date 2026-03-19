# E11 — Gap Analysis & Milestone Plan

> Comprehensive gaps discovered during live testing of E9+E10.
> Merged from: E10 post-testing gap analysis + deep sweep.
> Date: 2026-03-18
> Status: ANALYSIS COMPLETE — ready for milestone planning

---

## Test Scenario

Module `core`, stack=python-lib, declared floor=3.8 (stack), effective=3.10 (deps).
Target: 3.8 (verify/ensure compatibility with what the module claims to support).

**What the user expected:** Execute the plan → deps get compatible versions →
code gets __future__ fixes → posture shows green → system acknowledges the work done.

**What actually happened:** Plan "completed" but posture still shows gap warnings
with stale info, no explanation of what was accomplished, code issue unfixed,
dep pins too rigid, no pyproject.toml offered, test step misleading.

---

## Gaps (15 total, consolidated)

### TIER 0 — Core logic broken

| # | Gap | What happens | What should happen |
|---|-----|-------------|-------------------|
| 1 | **`==` vs `>=` in dep pinning** | Pins `pytest==8.3.5` | Should pin `pytest>=8.3.5,<9` (floor + bounded range). Offer format choice to user. |
| 2 | **Code scan has no remediation** | Finds 3.9+ features, logs them, marks step done | Should offer: add `__future__` for annotation features, flag runtime features as unfixable, offer to raise target |
| 3 | **Same-version direction wrong** | 3.8→3.8 = "upgrade" | Should be "verify" or "downgrade". Must include downgrade steps like `add_future_annotations` |

### TIER 1 — Missing intelligence

| # | Gap | What happens | What should happen |
|---|-----|-------------|-------------------|
| 4 | **Warning text stale after remediation** | "pytest requires ≥3.8" listed as gap contributor — but that's NOT a gap | Only list deps/features where floor > declared as gap contributors |
| 5 | **No re-check after pinning** | Pins written → step done → no verification | Add a "verify pins are compatible" step that re-runs dep check |
| 6 | **Warnings reference installed versions, not pinned** | Scanner reads .dist-info (installed) even when requirements.txt has pins | Already partially fixed (reads pins), but warnings still show stale installed info until pip install |
| 7 | **Test step misleading** | "Run test suite against Python 3.8" runs on Python 3.12 | Label should say current Python. If target binary available, use it. |

### TIER 2 — Missing UX flows

| # | Gap | What happens | What should happen |
|---|-----|-------------|-------------------|
| 8 | **No post-plan summary** | "✅ All steps complete!" — no detail | Show what changed: N packages pinned, M code files flagged, tests passed/failed on Python X.Y |
| 9 | **No version_note prompt** | Plan completes, no note captured | Prompt: "Add a note about this version decision?" → saves to project.yml |
| 10 | **No pyproject.toml generation** | Pins go to requirements.txt only | Offer a modal: generate/update pyproject.toml with requires-python + dependencies, pre-filled from stack/module config |
| 11 | **Consolidated warnings** | Two separate warnings (EOL + gap) for same root cause | Merge related warnings into one clear message with action |

### TIER 3 — Edge cases & polish

| # | Gap | What happens | What should happen |
|---|-----|-------------|-------------------|
| 12 | **No verify recipe** | target==current uses upgrade recipe | Create verify-focused recipe: check deps, check code, report status |
| 13 | **Stale artifacts after re-targeting** | Old requirements.txt pins remain when plan target changes | Warn about existing artifacts from previous plan |
| 14 | **Code scan doesn't separate fixable vs unfixable** | All findings treated equally | Split: annotation features (fixable with __future__) vs runtime features (need code rewrite or target raise) |
| 15 | **No pip install step in recipe** | After pinning, user must manually run pip install | Add step or offer it in remediation flow |

---

## Pyproject.toml Generation Modal (Gap #10 — Detail)

### The Flow

When the system creates or pins deps, it should offer to generate a proper
pyproject.toml for the module. This is a MODAL with pre-filled information.

```
┌─────────────────────────────────────────────────────┐
│  📄 Generate pyproject.toml for: core                │
├─────────────────────────────────────────────────────┤
│                                                     │
│  Pre-filled from stack/module config:               │
│                                                     │
│  Name:        [core                    ]            │
│  Description: [Domain models, services ] ← from ref │
│  Version:     [0.1.0                   ]            │
│  Requires-Python: [>=3.8               ] ← target   │
│                                                     │
│  Dependencies (from requirements.txt pins):         │
│  ┌─────────────────────────────────────────────┐    │
│  │ flask>=3.0.3,<4                             │    │
│  │ pydantic>=2.10.6,<3                         │    │
│  │ pytest>=8.3.5,<9                            │    │
│  │ pyyaml>=6.0                                 │    │
│  │ cryptography>=42.0                          │    │
│  └─────────────────────────────────────────────┘    │
│  [editable — user can modify before saving]         │
│                                                     │
│  Format:  ○ >= (compatible)  ○ == (exact)           │
│                                                     │
│  Preview:                                           │
│  ┌─────────────────────────────────────────────┐    │
│  │ [project]                                   │    │
│  │ name = "core"                               │    │
│  │ description = "Domain models, services"     │    │
│  │ version = "0.1.0"                           │    │
│  │ requires-python = ">=3.8"                   │    │
│  │ dependencies = [                            │    │
│  │     "flask>=3.0.3,<4",                      │    │
│  │     "pydantic>=2.10.6,<3",                  │    │
│  │ ]                                           │    │
│  └─────────────────────────────────────────────┘    │
│                                                     │
├─────────────────────────────────────────────────────┤
│  [Cancel]                    [📄 Generate]          │
└─────────────────────────────────────────────────────┘
```

### Pre-fill Sources

| Field | Source | Fallback |
|-------|--------|----------|
| name | ModuleRef.name from project.yml | module directory name |
| description | ModuleRef.description from project.yml | "" |
| version | existing pyproject.toml if any | "0.1.0" |
| requires-python | plan target or current declared floor | stack requires min_version |
| dependencies | requirements.txt pins | empty |

### When It Triggers

1. After dep pinning remediation → "Also generate pyproject.toml?" button
2. As a plan step → "Generate module pyproject.toml" in recipe
3. Manual → from remediation modal "Create module config" option

---

## Post-Plan Summary (Gap #8 — Detail)

### What It Shows

When all steps are done, the plan modal shows a structured summary:

```
┌─────────────────────────────────────────────────────┐
│  ✅ Plan Complete                                    │
│                                                     │
│  Target: Python ≥3.8                                │
│  Starting state: effective ≥3.10 (gap)              │
│  Current state: effective ≥3.8 (consistent) ← ideal │
│  OR: effective ≥3.9 (gap reduced) ← if code unfixed │
│                                                     │
│  What changed:                                      │
│  • 3 dependency versions pinned in requirements.txt │
│  • CI config updated with Python 3.8 in matrix      │
│  • Code scan: 1 finding (builtin generics) ← if any │
│                                                     │
│  What remains:                                      │
│  • Code floor 3.9 from builders/__init__.py:24      │
│    → Add __future__ import to fix                   │
│                                                     │
│  ┌──────────────────────────────────────────────┐   │
│  │ Add a note about this version decision:      │   │
│  │ [                                          ] │   │
│  └──────────────────────────────────────────────┘   │
│                                                     │
│  [Save note]  [Clear plan]  [Close]                 │
└─────────────────────────────────────────────────────┘
```

### Data Sources

- "Starting state" — captured at plan creation time (store effective_floor snapshot)
- "Current state" — live from posture after rescan
- "What changed" — tracked during batch execution (each step's result)
- "What remains" — diff between current state and target
- Version note — user input → saves to project.yml

---

## Code Scan Remediation (Gap #2 + #14 — Detail)

### The Split

When code scan finds features above the target, classify them:

**Annotation features (fixable with `__future__`):**
- `list[`, `dict[`, `set[`, `tuple[` — builtin generics (3.9+)
- `X | Y` in type hints — union syntax (3.10+)

These work on ANY Python with `from __future__ import annotations`
because annotations are deferred as strings.

**Runtime features (NOT fixable with `__future__`):**
- `match/case` — structural pattern matching (3.10+)
- `except*` — exception groups (3.11+)
- `:=` — walrus operator (3.8+)
- `type X = ...` — type statement (3.12+)

These execute at runtime. No import can defer them.

### The Remediation

When the code scan step finds features above target:

1. **All annotation-only?** → offer "Add __future__ annotations to N files" → auto-apply
2. **Mix of annotation + runtime?** → fix annotation features, flag runtime as manual work
3. **All runtime?** → offer "Raise target to X.Y" (the lowest version that covers all features)

---

## Milestone Chunking

### Chunk 1: Core Logic Fixes (P0)
- Fix `==` → `>=` in dep pinning (+ format choice UI)
- Fix direction detection (same version → "verify" or "downgrade")
- Fix code scan to offer remediation (add __future__ for annotation features)
- Fix warning text to only show actual gap contributors

### Chunk 2: Plan Completion Flow
- Post-plan summary with what changed / what remains
- Version note prompt on completion
- Posture auto-rescan on plan completion
- Consolidated warnings (merge related)

### Chunk 3: Pyproject.toml Generation Modal
- Modal with pre-filled info from stack/module config
- Dependency format choice (>=, ==)
- Live preview of generated file
- Save to module directory

### Chunk 4: Recipe & Step Improvements
- Verify recipe for target==current
- Re-check deps after pinning step
- Test step honesty (label + detection of target Python availability)
- pip install step in recipe after pinning
- Code scan split: annotation vs runtime features

---

## Decisions (Locked)

1. **Same-version direction:** target <= current = "downgrade". Downgrade recipe
   already has `add_future_annotations`. No new recipe file needed.

2. **pyproject.toml:** Coexist with requirements.txt. Both generated/updated.

3. **Starting state snapshot:** No. Git serves that purpose.

4. **Dep constraint format:** `>=` is the default. `==` was wrong. Just fix it.
