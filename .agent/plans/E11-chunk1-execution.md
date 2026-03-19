# E11 Chunk 1 — Core Logic Fixes

> Fix the 3 P0 bugs + warning accuracy.
> Status: EXECUTION PLAN

---

## Step 1: Fix dep pinning `==` → `>=`

**File:** `src/ui/web/routes/posture.py` — `posture_module_pin_deps()`

Change all `f"{pkg}=={version}"` to `f"{pkg}>={version}"`.

## Step 2: Fix direction detection

**File:** `src/core/services/module_upgrade/context.py` — `_compute_direction()`

Change: target == current → return "downgrade" (not "upgrade").
Change: target < current → already returns "downgrade". Good.
Change: target > current → already returns "upgrade". Good.

This means when targeting 3.8 with current floor 3.8, the downgrade recipe
runs. The downgrade recipe includes `add_future_annotations` (condition:
target_lt 3.10) and `scan_incompatible_features`.

## Step 3: Code scan remediation in wizard_batch

**File:** `src/core/services/module_upgrade/automation/wizard.py` — `wizard_batch()`

When a code scan step (`scan_breaking_changes` or `scan_incompatible_features`)
returns findings, classify them:

- Annotation features (fixable): offer "Add __future__ annotations" remediation
- Runtime features (unfixable): offer "Raise target version" remediation

Currently code scan findings set `incompat = 0` and move on. Instead:
- Check if any findings have version > target
- If annotation-only: emit remediation with "Add __future__" option
- If has runtime features: emit remediation with "Raise target" option

## Step 4: Fix warning accuracy — gap contributors

**File:** `src/ui/web/routes/posture.py` — peek panel content or enrichment

The gap warning lists ALL deps/features in the effective floor calculation.
After remediation, some are no longer contributors. Filter to only show
deps/features where their individual floor > declared floor.

---

## Verification

1. Delete existing plan for core
2. Create new plan targeting 3.8
3. Verify downgrade recipe generated (includes add_future_annotations step)
4. Run batch → dep check should pin with >= not ==
5. Code scan should offer __future__ remediation
6. After remediation, warnings should only show actual gap contributors
