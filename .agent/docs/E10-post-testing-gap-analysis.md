# E10 Post-Testing Gap Analysis

> Comprehensive analysis of gaps discovered during live testing of the
> module upgrade/downgrade system (E9 + E10).
> Date: 2026-03-18
> Status: ANALYSIS — no code changes yet

---

## Context

After building the full checklist generation + automation engine (E9 Chunk 1-3,
E10 Chunk 1-4), we tested a real scenario: module `core` targeting Python 3.8
compatibility. The testing revealed fundamental gaps in the system's intelligence,
remediation quality, and post-plan awareness.

**Test scenario:** core module, stack=python-lib, declared floor=3.8 (from stack),
effective floor=3.10 (from deps), target=3.8 (compatibility/downgrade).

**What happened:**
1. Plan generated with 7 steps
2. Deps remediated by pinning compatible versions → requirements.txt created
3. Code scan found 3.9+ features → logged but no remediation offered
4. Tests ran on 3.12, not 3.8 → proves nothing about compatibility
5. Plan marked "complete" — all 7 steps checked
6. Posture STILL shows gap warning with stale information
7. No post-plan summary, no version note prompted, no acknowledgment of what changed

---

## Gap 1: Dependency Pinning Uses `==` Instead of `>=`

### What happens now
The `POST /posture/module-pin-deps` endpoint writes `package==version` to
requirements.txt. For example: `pytest==8.3.5`.

### What's wrong
For a library/module claiming version compatibility, `==` is too restrictive.
It locks users to exactly one version. If a security patch comes out (8.3.6),
users can't upgrade without modifying the constraint.

### What it should do
Pin with a floor constraint, not exact pin:
- `pytest>=8.3.5,<9` — compatible range (same major, above the known-good version)
- Or `pytest>=8.3.5` — open-ended floor

The choice between `>=X,<Y` (bounded) and `>=X` (open) could be an option
presented to the user during remediation.

### Where to fix
`src/ui/web/routes/posture.py` — `posture_module_pin_deps()` endpoint.

---

## Gap 2: Code Scan Is Read-Only — No Remediation Offered

### What happens now
The `scan_breaking_changes` handler runs `compute_code_floor()`, finds version-specific
features (e.g., `dict[str, ...]` at line 24 of builders/__init__.py), logs them,
and marks the step done. No fix offered.

### What's wrong
The system detected that the code uses 3.9+ features incompatible with the 3.8 target.
It should have offered remediation:
- **Add `from __future__ import annotations`** to files using annotation-only features
  (builtin generics like `list[`, `dict[`, union `X | Y`)
- **Flag runtime features** that CAN'T be fixed with __future__ (match/case, walrus, etc.)
  and explain they require raising the target

The `add_future_annotations` handler EXISTS but was never triggered because the
direction was "upgrade" and that step is only in the downgrade recipe.

### Root cause
The direction detection treats 3.8 → 3.8 as "upgrade." It should be
"compatibility fix" which needs BOTH upgrade and downgrade remediation steps.

### What it should do
1. Code scan finds features above target
2. Split findings into: annotation features (fixable with __future__) vs runtime features (unfixable)
3. For annotation features: offer "Add __future__ annotations to N files" remediation
4. For runtime features: offer "Raise target to X.Y" or "Rewrite these patterns"
5. If ALL features are annotation-only and fixable: auto-apply and mark done

### Where to fix
- `wizard_batch` in `wizard.py` — add remediation path for code scan findings
- `python.json` recipe — add `add_future_annotations` to upgrade recipe when target < 3.10
- Direction detection in `context.py` — handle "same version" as compatibility verification

---

## Gap 3: Direction Detection — Same Version = "Compatibility Fix"

### What happens now
`_compute_direction()` in `context.py`: if target == current → returns "upgrade".

### What's wrong
When the declared floor is 3.8 and you target 3.8, you're not upgrading or downgrading.
You're verifying and fixing compatibility. The plan should include steps from BOTH
the upgrade and downgrade recipes — specifically:
- From upgrade: scan breaking changes, check deps, update CI, run tests
- From downgrade: add __future__ imports, scan incompatible features, check deps support target

### What it should do
Add a third direction: `"verify"` or treat same-version as downgrade (since the goal
is to ensure the floor actually works, which means checking for features above it).

### Where to fix
- `context.py` — `_compute_direction()` should return `"downgrade"` when target == current
  (the effective floor is higher, so we're trying to make the code match the declared floor)
- OR merge relevant downgrade steps into the upgrade recipe with appropriate conditions

---

## Gap 4: Warning Accuracy After Remediation

### What happens now
After pinning deps, the posture warning still says:
"• pytest requires Python ≥3.8"
This is listed as a GAP CONTRIBUTOR but ≥3.8 IS the target. That's compatible.

### What's wrong
The warning text is generated from `compute_verdict()` and the peek panel content.
It lists ALL deps/code that contributed to the effective floor. But after remediation,
pytest's contribution dropped from ≥3.10 to ≥3.8 — it's no longer a gap contributor.
The system still lists it because the dep detail says "floor=3.8" and the declared is 3.8,
which is technically "consistent" for that dep, but it's listed in the gap warning anyway.

### What it should do
The gap warning should only list ACTUAL gap contributors — deps/features where
the floor is HIGHER than the declared floor. If pytest floor=3.8 and declared=3.8,
pytest is NOT a contributor to the gap.

### Where to fix
- `bridges/modules.py` or `posture.py` enrichment — filter gap contributors to only
  those where the individual floor exceeds the declared floor
- Peek panel content builders — use filtered contributor list

---

## Gap 5: No Post-Plan Summary

### What happens now
After all plan steps are checked, the plan modal shows a "✅ All steps complete!"
banner. The posture table shows ✅ icon. But there's no summary of what changed.

### What's wrong
The user completed 7 steps. Some succeeded, some had findings, some had remediation.
There's no record of what happened. No summary saying:
- "3 dependency versions pinned (flask 3.0.3, pydantic 2.10.6, pytest 8.3.5)"
- "Code scan found 1 issue: builtin generics in builders/__init__.py (unresolved)"
- "Tests ran on Python 3.12 (not 3.8 — does not validate compatibility claim)"

### What it should do
When a plan completes (all steps done), generate a summary:
1. What was the target and what was the starting state
2. What each step accomplished (or found)
3. What remains unresolved
4. Prompt the user for a `version_note`

This summary could be:
- Shown in the plan modal completion banner
- Stored on the `version_note` field in project.yml
- Visible in the posture peek panels

### Where to fix
- Plan modal `_refreshPlanState` — when all done, show detailed summary
- Version note prompt — after plan completion
- Posture enrichment — show version_note context alongside warnings

---

## Gap 6: No Version Note Prompt

### What happens now
The `version_note` field exists on ModuleRef in project.yml. It can be set
via the remediation modal. But the plan flow never prompts for it.

### What's wrong
After completing a plan, the user has context about WHY the version is what it is.
"We target 3.8 for broad compatibility. Deps pinned. Code has one 3.9 usage in
builders/__init__.py which is deferred." This context is valuable for the team.

### What it should do
Plan completion should prompt: "Add a note about this version decision?"
with a text input. The note gets saved to project.yml and displayed in posture.

### Where to fix
- Plan modal completion banner — add note input
- POST to `/posture/module-note` on submit

---

## Gap 7: Test Step Doesn't Validate Compatibility

### What happens now
"Run test suite against Python 3.8" runs `pytest` in the module directory.
But it runs on whatever Python is active in the venv — which is 3.12.

### What's wrong
Running tests on 3.12 proves the code works on 3.12. It says nothing about 3.8.
The step label says "against Python 3.8" but the system has no mechanism to
run tests on a different Python version.

### What it should do
Option A: The step should acknowledge this limitation.
  - Label: "Run test suite (on current Python — does not validate 3.8 compat)"
  - Description: "To validate 3.8, use tox or CI with Python 3.8"

Option B: Detect available Python versions and offer to run on the target.
  - Check if `python3.8` binary exists
  - If yes, offer to run tests with it
  - If no, explain that CI testing is needed

Option C: Generate a tox.ini or CI config targeting the version.

### Where to fix
- Recipe description — make the limitation clear
- Subprocess handler — detect Python version mismatch and warn
- Possibly: generate tox.ini as a plan step

---

## Gap 8: Config File Generation

### What happens now
Dep pinning creates/updates `requirements.txt`. The module's floor comes from
the stack definition (no pyproject.toml in the module directory).

### What's wrong
The module has requirements.txt but no pyproject.toml. The user might want both.
More importantly, the requirements.txt format is just dep pins — it doesn't declare
the Python version requirement. A pyproject.toml with `requires-python = ">=3.8"`
AND `dependencies = ["pytest>=8.3.5,<9", ...]` is a more complete declaration.

### What it should do
After pinning deps in requirements.txt, offer to generate/update pyproject.toml:
- Create `[project]` section with `requires-python`
- Move deps from requirements.txt to `[project.dependencies]`
- Or create both (requirements.txt for pip, pyproject.toml for metadata)

### Where to fix
- Pin deps endpoint — offer pyproject.toml generation as follow-up
- Plan recipe — add a "Create module pyproject.toml" step

---

## Gap 9: Consolidated Warnings

### What happens now
The posture shows multiple warnings for related issues:
- "🟡 Floor approaching EOL" (about the effective floor)
- "⚠️ Compatibility gap" (about declared vs effective)
These are two symptoms of the same root cause.

### What's wrong
The user sees two separate alarms but they stem from one issue: the code uses
3.9+ features while claiming 3.8 support. If the code issue is fixed, BOTH
warnings change.

### What it should do
When warnings are related (same root cause), consolidate into one clear message:
"This module claims Python 3.8+ but code in builders/__init__.py uses 3.9+ syntax.
Fix: add `from __future__ import annotations` to that file, or raise the declared
floor to 3.9 (note: 3.9 reaches EOL in 2025-10)."

One message. One action. Clear consequences.

### Where to fix
- Posture peek panel content — detect related warnings and merge
- Or: make the gap warning include the EOL consequence inline

---

## Gap 10: Stale Plan After Re-targeting

### What happens now
If the user raises the target (e.g., from 3.8 to 3.10), the plan is recreated
with a new checklist. But the old requirements.txt pins from the previous plan
remain on disk.

### What's wrong
The old pins (`pytest==8.3.5`) might be unnecessary at the new target (3.10
is supported by pytest 9.0.2). The system doesn't clean up or re-evaluate
previous remediation artifacts.

### What it should do
When re-targeting, warn about existing artifacts from previous plans.
Or: the dep check step in the new plan will naturally find that everything
is compatible and skip remediation.

### Where to fix
Possibly nothing — the new plan's dep check will re-evaluate. But the stale
requirements.txt constraints could confuse users.

---

## Evolution Priority

| # | Gap | Impact | Effort | Priority |
|---|-----|--------|--------|----------|
| 1 | `==` → `>=` in dep pinning | High — wrong for libraries | Low | **P0** |
| 2 | Code scan remediation | High — plan doesn't fix the real issue | Medium | **P0** |
| 3 | Same-version direction | High — wrong recipe selected | Low | **P0** |
| 4 | Warning accuracy | Medium — confusing after remediation | Medium | **P1** |
| 5 | Post-plan summary | Medium — no closure | Medium | **P1** |
| 6 | Version note prompt | Medium — lost context | Low | **P1** |
| 7 | Test step honesty | Medium — misleading | Low | **P1** |
| 8 | Config file generation | Medium — incomplete output | Medium | **P2** |
| 9 | Consolidated warnings | Low — cosmetic but confusing | Medium | **P2** |
| 10 | Stale plan cleanup | Low — edge case | Low | **P3** |
