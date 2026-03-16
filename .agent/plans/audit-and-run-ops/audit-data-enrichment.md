# Audit Data Enrichment — Analysis & Plan

> Created: 2026-02-18  
> Status: **Phase 1-3 complete. Phase 4 parked.**

---

## 1. Problem Statement

Audit snapshots (both pending and saved) are missing detailed operational data.
The root cause is **not** in the staging or saving mechanism — those correctly
persist whatever the compute function returns.  The issue is that several
compute functions return **detection/summary** data only, not the full
operational payload the audit should capture.

Additionally, there is a **compute registry mismatch**: the `routes_devops.py`
registry binds some card keys to lightweight functions, while the browser
route handlers call richer variants.  This means the cache (and thus audit
snapshots) contain the thin version.

---

## 2. Current State — Per Card Analysis

### 2.1. 🔴 `packages` — 282 bytes (CRITICAL)

| Aspect | Value |
|---|---|
| **Registered compute** | `package_ops.package_status(root)` |
| **Browser route** | `routes_packages.py → get_cached("packages", lambda: package_ops.package_status(root))` |
| **Returns** | `managers`, `total_managers`, `has_packages` |
| **Missing** | Actual installed package list, versions, outdated packages |
| **Available function** | `package_actions.package_list(root)` → `{ok, manager, packages: [...]}` |

**Proposed fix:** Enrich `package_status()` to optionally append a `packages`
key with the installed package list from `package_list()`.  Keep it behind a
flag or create a new `package_status_enriched()` that wraps both.

---

### 2.2. 🔴 `testing` — 553 bytes

| Aspect | Value |
|---|---|
| **Registered compute** | `testing_ops.testing_status(root)` |
| **Returns** | `has_tests`, `frameworks`, `coverage_tools`, `stats` |
| **Missing** | Test file list, last run results, per-file counts |
| **Stats included** | `test_files` count, `test_functions` count, `test_classes` count, `source_files`, `test_ratio` |

**Assessment:** The stats are decent (file/function/class counts, ratio), but
the actual test file list is computed internally by `_count_tests()` and
discarded.  Only counts are returned.

**Proposed fix:** Include the list of test files (paths) in the stats output.
This gives the snapshot actionable data without running tests (which is
an "act" operation, not "observe").

---

### 2.3. 🟡 `quality` — 1128 bytes

| Aspect | Value |
|---|---|
| **Registered compute** | `quality_ops.quality_status(root)` |
| **Returns** | `tools[]` (each: id, name, category, cli_available, config_found, config_file, relevant, install_hint), `categories`, `has_quality` |
| **Missing** | Actual lint/quality scan output (but that's an "act" operation) |

**Assessment:** This is actually a DETECTION card, not a SCAN card.  It tells
you what tools are available, configured, and relevant.  Running the actual
tools (ruff, mypy, eslint) is an "act" operation done via run_tracker.

**Proposed fix:** This is adequate for audit purposes.  The data captures
what quality tools are configured.  Running scans is out of scope for
the observe layer.  **No change needed** unless we want to add a `quality:scan`
audit card that runs tools and captures output.

---

### 2.4. 🟡 `env` — 642 bytes (MISMATCH)

| Aspect | Value |
|---|---|
| **Registered compute** | `env_ops.env_status(root)` → thin: `files`, `has_env`, `has_example`, `total_vars` |
| **Browser route** | `routes_infra.py → get_cached("env", lambda: env_ops.env_card_status(root))` |
| **Browser data** | Rich: `environments[]` (with vault state, local keys, GH secrets, sync status), `active`, `github`, `env_files`, `has_env`, `total_vars` |

**Root cause:** The compute registry uses `env_ops.env_status()` (thin),
but the browser route uses `env_ops.env_card_status()` (rich).  The cache
key is `"env"` in both cases, so **whichever writes first wins**.  If the
background recompute runs first, the cache has thin data.  If the browser
route hits first, the cache has rich data.  **This is a race condition.**

**Proposed fix:** Change the registry to use `env_ops.env_card_status(root)`
so both paths produce identical rich data.

---

### 2.5. 🟢 `docs` — 1078 bytes

| Returns | `readme`, `doc_dirs`, `root_doc_files`, `api_specs`, `changelog`, `license`, `contributing`, `code_of_conduct`, `security_policy` |
|---|---|

**Assessment:** Adequate.  Captures documentation presence/absence with
specific file paths.  No enrichment needed.

---

### 2.6. 🟢 `wiz:detect` — 10,341 bytes

**Assessment:** Very rich.  Includes tools, files, config data, docker/gh/ci
status, gitignore analysis, codeowners.  No changes needed.

---

### 2.7. 🟢 Audit cards (`audit:deps`, `audit:scores:enriched`, `audit:l2:repo`)

These are purpose-built for audit snapshots and contain appropriate detail.
No changes needed.

---

## 3. Summary of Issues

| # | Card | Severity | Issue | Fix |
|---|---|---|---|---|
| 1 | `packages` | 🔴 Critical | Only returns manager detection, no package list | Enrich with `package_list()` data |
| 2 | `testing` | 🟡 Medium | Returns counts but discards file list | Expose test file paths in stats |
| 3 | `env` | 🔴 Critical | Registry/route mismatch → race condition | Align registry to `env_card_status` |
| 4 | `quality` | ✅ OK | Detection-only by design | No change (or add separate scan card) |
| 5 | `docs` | ✅ OK | Adequate | No change |

---

## 4. Proposed Implementation Order

### Phase 1: Fix the mismatch (no new code, just alignment) ✅ DONE
- [x] **`env` registry fix** — Changed `routes_devops.py` line 173 from
  `env_ops.env_status(root)` to `env_ops.env_card_status(root)`.

### Phase 2: Enrich `packages` compute ✅ DONE
- [x] Created `package_ops.package_status_enriched(root)` (282 → 1698 bytes)
- [x] Updated registry and browser route to use enriched version
- [x] Fixed `pip` detection: uses `sys.executable -m pip` instead of bare `pip`
- [x] Fixed `_pip_cmd()` helper for all pip subprocess calls
- Verified: 33 packages now captured with names and versions

### Phase 3: Enrich `testing` compute ✅ DONE
- [x] Modified `_count_tests()` to return `test_file_paths` (capped at 500)
- [x] No route mismatch — both registry and route use `testing_status()`

### Phase 4 (Optional): Add `quality:scan` card
- [ ] Create a separate audit card `quality:scan` that actually runs
  detected quality tools and captures output
- [ ] This would be a heavier operation, similar to `audit:scores:enriched`
- [ ] **Parking lot** — only do this if user explicitly requests it

---

## 5. Impact Assessment

| Change | Risk | Data size increase |
|---|---|---|
| `env` registry fix | Low — uses existing tested function | ~0 (same data, just consistent) |
| `packages` enrichment | Medium — depends on CLI tool availability | +2-10 KB per snapshot |
| `testing` file paths | Low — data already computed internally | +1-5 KB per snapshot |

---

## 6. Files to Modify

| File | Change |
|---|---|
| `src/ui/web/routes_devops.py:173` | Fix env compute registration |
| `src/core/services/package_ops.py` | Add `package_status_enriched()` |
| `src/ui/web/routes_devops.py:166` | Update packages compute registration |
| `src/core/services/testing_ops.py` | Expose test file paths in `_count_tests()` |

---

## 7. Decision Required

Before proceeding:
1. ✅ Approve Phase 1 (env fix) — zero risk, pure alignment
2. ✅/❌ Approve Phase 2 (packages) — moderate effort, high value
3. ✅/❌ Approve Phase 3 (testing) — low effort, moderate value
4. ✅/❌ Park Phase 4 (quality:scan) — for future consideration
