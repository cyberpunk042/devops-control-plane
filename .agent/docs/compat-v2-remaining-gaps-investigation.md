# Compat V2 — Remaining Gaps Investigation

> What's still broken, missing, or wrong after all the milestones so far.

---

## Bug 1: Files modified without user action

### What happened
When a plan is created for module "core" targeting 3.8, `@dataclass(slots=True)` in
`src/core/services/mediator/registrations/index.py` was modified to `@dataclass(frozen=True)`
— removing `slots=True`. The user did NOT click any fix button.

### Root cause investigation needed
- Is the compat engine auto-applying fixes during analysis? (It shouldn't)
- Is `fix_module()` being called from somewhere during plan creation?
- Is the `posture_module_plan()` route triggering fixes as a side effect?
- Does `mediator.dispatch("compat.analysis.{module}")` trigger fixes? (It shouldn't —
  analysis only DETECTS, doesn't fix)

### Investigation result
Grep shows fix functions are ONLY called from user-initiated handlers (fix_compat_auto,
add_future_annotations, posture_module_compat_fix). Analysis DOES NOT call fix functions.

The user likely clicked "Automate" on a fix step, which applied the fix. The issue is
that the fix applied WITHOUT PREVIEW — the user expected a preview modal but got
immediate execution. This is because `handle_fix_compat_auto` in execute mode applies
fixes without showing the user what will change first.

The `@dataclass(frozen=True, slots=True)` → `@dataclass(frozen=True)` change is the
`remove_keyword_arg` transform working correctly on the program's own code. The module
IS `src/core` — the compat engine correctly found `slots=True` which is Python 3.10+.

---

## Bug 2: Auto-fix button fails with "Failed" toast

### What happens
1. User runs isolated tests → tests fail with "cannot import name 'UTC' from 'datetime'"
2. `_detect_compat_failures()` in test_env.py matches the error pattern
3. UI shows "Compatibility issues detected" with auto-fix buttons
4. User clicks "Auto-fix: datetime.UTC → datetime.timezone.utc"
5. `_autoFixCompat()` calls `/api/posture/module-compat-fix` with `{search: "datetime.UTC", replace: "datetime.timezone.utc"}`
6. Endpoint fails → "Failed" toast

### Root cause
The compat-fix endpoint:
1. Searches registry for entries matching "datetime.UTC" → finds entries
2. Gets cached analysis → filters to matching findings
3. Calls `fix_module()` → fix engine applies transforms
4. Verification runs (re-detect + syntax check)
5. If verification fails → "Fix failed, rolled back"

### Investigation result
The datetime.UTC fix WORKS correctly:
```
BEFORE: from datetime import UTC, datetime → now = datetime.now(UTC)
AFTER:  from datetime import timezone, datetime → now = datetime.now(timezone.utc)
```

Result: "1 verified, 1 failed" — the failure is because TWO entries match the same
pattern (python.stdlib.datetime_utc AND python.edge.import_aliasing). Both have
identical transforms. The first applies successfully, the second fails because
the code was already modified.

The "Failed" toast in the UI comes from the `_autoFixCompat` → `posture_module_compat_fix`
path which calls `fix_module()` and gets `failed_fixes > 0` (from the duplicate entry)
even though the actual fix worked.

Root cause: **duplicate database entries** that match the same pattern. The fix engine
tries to apply both, the second one fails on already-fixed code, and the endpoint
reports failure even though the fix actually worked.

Fix: deduplicate database entries OR change the result logic to report success
when verified_fixes > 0 (even if some duplicates failed).

---

## Bug 3: No implication explanation to user

### What's missing
When a step says "Fix datetime.UTC (17 files)", the user doesn't know:
- WHICH 17 files
- WHAT the change looks like (before → after)
- WHAT the implications are (e.g., "timezone.utc is identical to UTC, available since Python 3.2")
- WHETHER the fix is reversible
- WHETHER it affects behavior

### What's needed
The step preview (when user clicks "Automate" but before clicking "Apply") should show:
- File list with line numbers
- Before/after code preview for representative examples
- Implication summary (behavioral impact, compatibility notes)
- Risk level (low/medium/high)
- Reversibility note

---

## Bug 4: _autoFixCompat is disconnected from compat engine

### What's wrong
The `_autoFixCompat()` JS function comes from the OLD compat hint system in test_env.py.
It sends `{search: "datetime.UTC", replace: "datetime.timezone.utc"}` — a STRING search/replace.
But the compat engine uses AST-based transforms with `fix_module()`.

The endpoint tries to bridge both worlds:
1. Search registry for "datetime.UTC" → finds AST-based entry
2. Get analysis → find findings
3. Call `fix_module()` with those findings → AST transforms

But the AST transforms might not map to what the simple string suggests. The
"datetime.UTC" search matches the feature NAME in the registry, but the actual fix
involves replacing `from datetime import UTC` with `from datetime import timezone`
AND replacing all usages of `UTC` with `timezone.utc` — two-step transform.

### What should happen
The test failure remediation should use the same compat engine fix path as the step
automation. Not a separate `_autoFixCompat` → `posture_module_compat_fix` path.
When the test detects a compat failure, it should show the compat fix step and let
the user run it through the normal step execution flow.

---

## Bug 5: Test remediation still uses hardcoded patterns

### What's wrong
`_detect_compat_failures()` in test_env.py uses hardcoded `_COMPAT_PATTERNS` list
with 7 regex patterns. These duplicate the compat database entries and produce
a separate remediation UI that's disconnected from the step flow.

### What should happen
When tests fail with compat errors, the system should:
1. Detect the compat failure (from test output patterns — this part works)
2. Map the failure to a compat database entry (by feature name)
3. Show the SAME fix UI as the step automation (not a separate _autoFixCompat button)
4. The fix runs through `handle_fix_compat_auto` → `fix_module()` → verification

---

## Bug 6: Duplicate dict merge entries produce duplicate steps

### What's still wrong
`dict merge operator (|)` and `dict | dict merge` both match `BinOp BitOr` and
produce the same 53 findings on the same 30 files. This creates two identical
fix steps in the plan:
```
Fix dict merge operator (|) (30 file(s))
Fix dict | dict merge (30 file(s))
```

These should be deduplicated into one step.

---

## Bug 7: `_REWRITE_GUIDES` dict not accessible from compat path

### What's still in the code
The `_REWRITE_GUIDES` dict in code_scanner.py contains before/after examples for
features. The compat guide handler uses it for rendering rewrite hints. But the
YAML database entries also have `test.before` and `test.after` fields that serve
the same purpose.

The guide should read from the database entries, not from a hardcoded dict.

---

## What Needs to Happen — Next Milestones

### Milestone A: Fix the auto-fix pipeline
1. Debug WHY `fix_module()` verification fails for datetime.UTC
2. Test each transform type (replace_import_and_usages, rewrite_expression,
   conditional_import, remove_keyword_arg) end-to-end
3. Ensure fixes work → re-detect finds 0 matches → verification passes

### Milestone B: Preview before apply
1. Every fix step shows a preview before applying:
   - File list with line numbers
   - Before/after code samples
   - Implication summary
   - Risk level
2. User explicitly confirms before any file is modified
3. No auto-applying during analysis or plan creation

### Milestone C: Unify test remediation with step flow
1. `_detect_compat_failures()` maps test errors to compat database entries
2. Remediation UI shows the same fix actions as step automation
3. Remove `_autoFixCompat` → `posture_module_compat_fix` separate path
4. Test failures route through `handle_fix_compat_auto`

### Milestone D: Deduplicate and clean up
1. Merge duplicate BinOp entries (dict merge + dict | dict merge → one entry)
2. Remove `_REWRITE_GUIDES` dict — use database entry test.before/after
3. Remove `_COMPAT_PATTERNS` from test_env.py — query compat database
4. Single source of truth for all feature knowledge

### Milestone E: Implication awareness
1. Each database entry gets an `implications` field:
   - Behavioral impact: "none" / "minor" / "significant"
   - Reversibility: "fully reversible" / "requires manual review"
   - Compatibility note: "timezone.utc is identical to UTC, available since 3.2"
2. Fix preview shows implications before apply
3. Risk-based ordering: safe fixes first, risky ones last with confirmation

---

## Execution Order

```
A (fix pipeline) → B (preview) → C (unify test remediation) → D (cleanup) → E (implications)
```

A first — nothing else works if the fix transforms don't actually work.
B before C — users need to see what will change before applying.
C and D can overlap — both are cleanup/unification.
E last — enrichment after the core pipeline works.
