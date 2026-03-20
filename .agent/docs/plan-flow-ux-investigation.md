# Plan Flow UX — Full Investigation

> The automation batch ran 21 steps and accomplished almost nothing.
> Fix steps returned preview because auto-fix was off.
> Steps ran in wrong order. No awareness of what already exists.
> The flow needs complete rethinking.

---

## Problem 1: Fix steps did nothing

All fix steps returned "Preview: 118 findings — enable auto-fix to apply" and moved on.
The batch treated the preview return as "step completed" and continued to the next step.

**Root cause**: When `auto_fix=False`, fix handlers return `ok: True` with the preview.
The batch runner's `should_mark_done()` sees `ok: True` and marks it done. But nothing
was actually fixed.

**Fix**: When `auto_fix=False` and a fix handler returns a preview, the result should
have `ok: True` but `step_not_done: True` so the batch runner knows the step needs
attention. OR the batch should STOP at fix steps when auto_fix is off and show the
preview to the user.

---

## Problem 2: Steps in wrong order

Current order from the recipe + compat enrichment:
```
1. Update requires-python in pyproject.toml    ← config
2. Scan                                         ← analysis
3. Fix Path.is_relative_to                     ← fix (needs scan first ✓)
4. Fix aliased imports                          ← fix
5. Fix ast.unparse                              ← fix
6. Fix dataclass slots=True                     ← fix
7. Fix dict merge operator                      ← fix
8. Fix enum.StrEnum                             ← fix
9. Fix importlib.resources.files                ← fix
10. Fix str.removeprefix                        ← fix
11. Fix str.removesuffix                        ← fix
12. Review incompatible syntax guide            ← guide
13. Re-scan and verify                          ← verify
14. Check dependencies                          ← dep analysis
15. Install pinned dependencies                 ← dep install (NEEDS VENV!)
16. Update CI matrix                            ← CI
17. Scaffold tests                              ← test setup
18. Generate tests                              ← test setup
19. Integration tests                           ← test setup
20. Set up test environment                     ← VENV SETUP (should be BEFORE install!)
21. Run isolated tests                          ← test execution
```

**Problems**:
- Step 15 "Install pinned dependencies" comes BEFORE step 20 "Set up test environment"
  → you can't install into a venv that doesn't exist yet
- Step 14 "Check dependencies" finds incompatible deps AFTER all fixes → what if the
  fixes need different deps? Should check deps earlier
- Step 1 "Update requires-python" says "Change >=3.8 to >=3.8" → same value! No change needed.
  The condition check should catch that current == target means no update needed

**Correct logical order**:
```
1. Scan for incompatibilities                   ← know what we're dealing with
2. Fix all auto-fixable code issues             ← fix code first
3. Re-scan to verify fixes                      ← confirm code is clean
4. Check dependency compatibility               ← then check deps
5. Pin compatible dependency versions            ← update requirements
6. Update requires-python constraint             ← update config (only if different)
7. Set up test environment (venv)                ← create venv for target version
8. Install dependencies in venv                  ← install into the venv
9. Run isolated tests                            ← test everything
10. Update CI matrix                             ← CI last (after tests pass)
11. Scaffold tests (if missing)                  ← only if no tests exist
```

---

## Problem 3: No awareness of existing state

### "Generate pyproject.toml" offered when it already exists
The dep pinning step offers "Generate pyproject.toml" even though `src/core/pyproject.toml`
exists. The system should check `ctx.has_pyproject` and offer "Update pyproject.toml" instead.

### "Install pinned dependency versions" without a venv
The install step runs `pip install` in the host environment, not in the target version venv.
It should be aware of whether `setup_test_env` has been run and install into THAT venv.

### Steps don't know what already happened
Each step runs independently. The dep check doesn't know that fixes were applied.
The install step doesn't know about the venv. The test step doesn't know about the install.

---

## Problem 4: "Change >=3.8 to >=3.8"

The config update step says "Change >=3.8 to >=3.8 to widen compatibility range" —
current floor IS 3.8, target IS 3.8. The step shouldn't exist when current == target.

**Root cause**: The recipe condition `always: true` doesn't check if the change is a no-op.

---

## Problem 5: Scan shows 2403 findings in guide step

The guide step shows ALL 2403 findings including info-level noise
(PurePosixPath, logging improvements, json improvements). The filtering
from M11 applies to the scan step but NOT to the guide step.

The guide step should use the same filter: only error/warning, exclude no_fix_needed.

---

## Problem 6: Re-scan shows 2403 findings remain

After all fix steps returned preview (nothing was applied), the re-scan correctly
reports "2403 findings remain." But the batch continued past this — it should have
stopped here because the re-scan proves fixes weren't applied.

---

## Problem 7: Batch doesn't offer to continue

After the batch completes (or stops), the modal shows "Close" as the only option.
It should offer:
- "Continue from where we stopped" (if stopped at a failed step)
- "Re-run remaining steps" (if some steps were skipped)
- "Open plan" (to review results)

---

## Problem 8: Fix steps are individually listed instead of grouped

The plan shows 9 separate "Fix X" steps. From the user's perspective, they want
ONE "Fix all auto-fixable issues" step that handles everything. The individual
feature fixes are implementation detail, not user-facing steps.

---

## The Evolution

### E1: Logical step ordering

Rewrite `_generate_compat_steps()` to produce steps in the correct logical order:
1. Scan → 2. Fix all (one step) → 3. Verify → 4. Deps → 5. Config → 6. Venv → 7. Install → 8. Test → 9. CI

### E2: Single "Fix All" step instead of individual feature steps

Replace the N individual "Fix X" steps with ONE "Fix all auto-fixable issues" step
that calls `handle_fix_compat_auto`. The preview shows the grouped feature breakdown.
The execute applies all fixes in one pass.

### E3: Smart conditions

- Don't show "Update requires-python" when current == target
- Don't show "Generate pyproject.toml" when it already exists (show "Update" instead)
- Don't show "Install dependencies" before "Set up test environment"
- Skip completed steps (artifacts already exist)

### E4: Batch awareness

- When auto_fix is OFF, batch STOPS at fix steps and shows the preview
- Fix step returns `step_not_done: True` when auto_fix is off, not `ok: True`
- Batch modal offers "Continue" after stopping
- Re-scan failure stops the batch

### E5: Guide filtering

Guide step uses same filter as scan: only error/warning, exclude no_fix_needed.

### E6: Venv-aware install

Install step checks if test env venv exists. If not, tells the user to set up
the venv first. If yes, installs into the venv.

### E7: Recipe ordering fix

The Python recipe JSON's step order needs to match the logical flow.
OR the generator reorders steps regardless of recipe order.
