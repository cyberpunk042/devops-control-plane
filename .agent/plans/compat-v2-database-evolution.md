# Compat V2 Database Evolution

> The engine now has the matchers. The database entries need to be evolved
> to use them. This is not a quickfix — it's a systematic review of ALL
> entries to make the detection accurate and the fixes actionable.

---

## Context

The engine now supports:
- `has_keyword` — check specific keyword arguments on Call nodes
- `has_keyword_value` — check keyword argument has specific constant value
- `func_value_id` — check what object a method is called on
- `func_value_attr` — check deeper attribute chains
- `min_args` — minimum positional argument count
- `left_is_dict` / `right_is_dict` — distinguish dict ops from bitwise ops

443 Python entries loaded. 368 match "above 3.8" for downgrade.
Of those 368:
- 259 import-based (usually accurate)
- 36 good specificity (value_id checks)
- 35 BROAD (func_attr without object check) — produce ~2300 false positives
- 38 other (BinOp, func_id without kwargs) — produce ~500 false positives

---

## The Evolution Process

### Step 1: Automated validation script

Build a script that:
1. Loads all entries
2. For each entry, checks the detection rule quality:
   - Does it use `func_attr` without `func_value_id`? → FLAG as broad
   - Does it use `func_id` for a decorator/call without `has_keyword`? → FLAG
   - Does it use `op_type: BitOr` without context? → FLAG
   - Is the detection inherently unachievable via AST? → FLAG for removal
3. Reports: entry ID, current quality, suggested fix, estimated false positive rate

This script becomes a CI check — any new entry with a broad detection rule fails CI.

### Step 2: Categorize entries by fixability

**Category A: Fix with new matchers** (~25 entries)
- Path methods: add `func_value_id: Path` or detect via import
- dataclass kwargs: add `has_keyword: slots` / `has_keyword: kw_only`
- field kwargs: add `has_keyword: kw_only`
- specific stdlib methods: add `func_value_id` for the module

**Category B: Remove — undetectable via AST** (~10 entries)
- `re possessive quantifiers` — feature is in regex pattern STRING content
- `re atomic groups` — same
- `Path.match() case sensitivity` — behavioral change, not syntax
- `datetime.fromisoformat() improvements` — accepts more formats, behavioral
- `csv strict mode` — behavioral parameter change
- `sqlite3 autocommit` — behavioral

These should move to a separate "manual audit checklist" or be removed entirely.

**Category C: Downgrade severity** (~15 entries)
- `BinOp BitOr` entries that can't distinguish dict|dict from int|int
  → Change from `error` to `info` or add `context: runtime` check
- Method calls that are common names (.match, .compile, .connect)
  → Add `func_value_id` where possible, downgrade to `info` where not

**Category D: Upgrade fix strategy** (~30 entries)
- Entries marked `manual` that COULD have mechanical transforms:
  - `Path.is_relative_to()` → try/except or os.path.relpath
  - `str.removeprefix()` → slicing (already have this as auto-fix!)
  - `zip(strict=True)` → remove kwarg + add length assertion
  - `dataclass(slots=True)` → remove kwarg for 3.8 compat

### Step 3: Execute the fixes

Go through each category systematically:
- A: Update detection rules in YAML
- B: Remove or recategorize entries
- C: Change severity
- D: Add fix transforms

### Step 4: Verify

Run the analysis on module "core" before and after:
- Before: 4974 findings, 2481 "actionable" (mostly false positives)
- After: should be ~150-200 findings, almost all real
- Each auto-fixable finding should have a working transform
- Each manual finding should have clear instructions

Run the validator (`database/validator.py`) on every modified entry to verify
the detection + fix cycle works.

---

## Execution

This is a multi-session task. The database has 157 YAML files. Each entry
needs individual review. The process:

1. Write the validation script (this session)
2. Run it to get the full categorized report
3. Fix Category A entries (new matchers)
4. Handle Category B (remove undetectable)
5. Handle Category C (severity downgrades)
6. Handle Category D (fix strategy upgrades)
7. Verify with full analysis run
8. Add CI check for detection quality

Each step is verifiable independently.
