# M13–M17: Remaining Integration Work

---

## M13: Preview Before Apply

Every fix step MUST show a preview before modifying any file.

### What changes
- `handle_fix_compat_auto` preview mode: shows file list, before/after samples, finding count
- Frontend: Automate button opens preview modal, user clicks "Apply" to confirm
- No file is modified until user explicitly confirms

### Files
- `code_scanner.py` — `handle_fix_compat_auto` preview output
- `_system_posture.html` — preview rendering for fix steps

---

## M14: Unify Test Remediation

The test step failure remediation must use the same compat fix flow as step automation.
Remove the disconnected `_autoFixCompat` → `posture_module_compat_fix` path.

### What changes
- `_detect_compat_failures()` in test_env.py maps failures to compat database entries
- Remediation UI shows "Run fix step" button that routes through `handle_fix_compat_auto`
- Remove `_autoFixCompat` JS function
- Remove or repurpose `posture_module_compat_fix` endpoint

### Files
- `test_env.py` — map failures to compat entry IDs
- `_system_posture.html` — remediation UI uses step execution
- `posture.py` — clean up compat-fix endpoint

---

## M15: Deduplicate Database Entries

Duplicate entries produce duplicate findings and cause fix failures.

### What changes
- Merge `python.edge.import_aliasing` with `python.stdlib.datetime_utc` (or remove one)
- Merge `python.builtins.dict_merge_operator` with `python.builtins.dict_union_or`
- Audit for other duplicates across all 1000 entries
- Add dedup check to audit script

### Files
- YAML entries in `database/entries/python/`
- `audit_entries.py` — add duplicate detection

---

## M16: Implication Awareness

Steps explain what changes mean before applying.

### What changes
- Database entries get implication metadata (behavioral impact, reversibility)
- Preview shows: "This replaces `from datetime import UTC` with `from datetime import timezone`
  and changes all UTC references to timezone.utc. timezone.utc is functionally identical,
  available since Python 3.2. This change is safe and fully reversible."
- Fix results show what was changed with file diffs

### Files
- Database YAML entries — add `implications` field
- `code_scanner.py` — include implications in preview output
- `_system_posture.html` — render implications

---

## M17: Single Source of Truth Cleanup

Remove all duplicate knowledge sources.

### What changes
- Remove `_REWRITE_GUIDES` dict from code_scanner.py — use database test.before/after
- Remove `_COMPAT_PATTERNS` from test_env.py — query compat database for test failure mapping
- Guide handler reads before/after from database entries, not hardcoded dict

### Files
- `code_scanner.py` — remove `_REWRITE_GUIDES`, read from database
- `test_env.py` — remove `_COMPAT_PATTERNS`, query database
