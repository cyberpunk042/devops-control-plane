# Remaining Bugs and Gaps — 2026-03-20

> Everything that's still broken after all the milestones.

---

## Bug 1: Pip install runs before venv setup

**What happens**: The batch runs "Install pinned dependency versions" (step ~15)
before "Set up test environment" (step ~17). Pip installs into the HOST Python,
not the target version venv.

**Root cause**: The step reordering in `_enrich_with_compat_analysis` puts
`run_pip_install` in `venv_steps` group, but the recipe order has it before
`setup_test_env`. The reordering logic puts install and venv in the same group
but doesn't enforce venv-first within the group.

**Fix**: In the reordering logic, `setup_test_env` must come BEFORE `run_pip_install`
within the `venv_steps` group. Sort the group: venv setup first, install second.

---

## Bug 2: Fixes not applied — batch ran with auto-fix OFF

**What happens**: User runs batch without checking the auto-fix checkbox.
Fix steps show preview. User then clicks Apply on individual fixes.
Then re-runs batch — shows old scan results as if nothing was fixed.

**Root cause**: After individual fixes are applied, the compat analysis cache
isn't invalidated. The batch re-reads the cached (stale) analysis.

**Fix**: After any fix is applied via `handle_fix_compat_auto`, the analysis
cache must be busted: `mediator.bust_path("compat.analysis.{module}")`.
This already exists in `fix_module()` in the fix engine — verify it's working.

Also: the batch should re-scan before showing fix step previews if fixes
were already applied since the last scan.

---

## Bug 3: Test failure shows "yaml Python ?+"

**What happens**: Test output has `import yaml` error. `_detect_compat_failures`
matches `No module named 'yaml'` but can't find it in the compat database because
yaml/pyyaml is not a Python version feature — it's a missing pip package.

**Fix**: The test failure detector should distinguish between:
- Version compat errors (datetime.UTC → needs 3.11) — show compat hint
- Missing package errors (yaml → needs `pip install pyyaml`) — show package hint

Check if the module name is in the compat database. If not, suggest `pip install`.

---

## Bug 4: Test failure shows datetime.UTC and StrEnum even after deps were pinned

**What happens**: Tests fail with datetime.UTC and StrEnum errors. But the code
fixes weren't applied (auto-fix was OFF). The test ran against unfixed code.

**Not a bug** — this is expected behavior. The fixes need to be applied before
tests will pass. The user needs to either:
- Enable auto-fix and re-run the batch
- Or apply fixes individually, then re-run tests

**But the UX should make this clear**: "Tests failed because code fixes haven't
been applied yet. Apply fixes first, then re-run tests."

---

## Bug 5: "Fix all detected issues" button still appears in test remediation

**What happens**: Test failure shows compat hints with "Fix all detected issues"
button. This was supposed to be fixed in M14 to route through step automation.

**Verify**: Check if the button routes through `_modalApplyStep` with
`fix_compat_auto:from_test` or still uses the old `_autoFixCompat` path.

---

## Bug 6: No feedback after applying individual fixes

**What happens**: User clicks Automate on "Fix datetime.UTC", sees preview,
clicks Apply. Fix runs. Toast shows. But the plan modal still shows the old
state — the fix step still shows as not done.

**Fix**: After `_modalApplyStep` succeeds for a fix step, refresh the plan
modal to show updated state. The `_wizardMarkDone` call should trigger
`_refreshPlanState()`.

---

## Bug 7: Batch modal shows stale results on re-run

**What happens**: User applies fixes individually, then re-runs the batch.
The batch shows the old scan count (118 findings) instead of the new count.

**Root cause**: The compat analysis cache wasn't busted when individual fixes
were applied. OR it was busted but the batch re-reads before the new analysis
completes.

**Fix**: Bust analysis cache after individual fixes. The batch should call
`mediator.bust_path()` for the analysis before starting.

---

## Bug 8: Re-scan shows "118 findings remain" but should show less

**What happens**: After fixes were supposedly applied (or previewed), the
re-scan still shows 118 findings. This is correct if fixes weren't applied.
But the count includes ALL actionable findings, not just remaining ones.

**Already fixed**: The rescan handler now filters to actionable. But if fixes
weren't applied, 118 is correct.

---

## Gap 1: Step order — venv before install

The `venv_steps` group needs internal ordering:
1. `setup_test_env` first
2. `run_pip_install` second

---

## Gap 2: Test step should know if fixes were applied

Before running tests, check if all fix steps are done. If not, warn:
"Code fixes haven't been applied. Tests may fail due to unfixed
incompatibilities. Apply fixes first?"

---

## Gap 3: Scan step shows 100 findings in batch log

The scan handler returns up to 100 findings in the `findings` array (capped).
The batch wizard logs all of them as individual lines. Should show a summary
instead of 100+ lines.

---

## Gap 4: Plan modal doesn't refresh after individual fix

After applying a fix via the Automate button, the plan modal should show
the step as done and update the progress bar.

---

## Priority Order

1. **Bug 1** (pip before venv) — wrong order causes real damage
2. **Bug 3** (yaml detection) — false compat hint for missing package
3. **Bug 6 + Gap 4** (no refresh after fix) — UX breaks flow
4. **Bug 2 + 7** (stale cache after fix) — analysis cache not busted
5. **Bug 4** (test without fixes) — UX should warn
6. **Gap 1** (venv order) — same as Bug 1
7. **Gap 3** (scan log verbosity) — cosmetic
