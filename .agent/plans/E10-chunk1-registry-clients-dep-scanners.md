# E10 Chunk 1 — Registry Clients + Dep Scanners

> Query package registry APIs for all languages + scan dependency files.
> Architecture: `.agent/docs/E10-wizard-automation-architecture.md`
> Status: READY FOR EXECUTION

---

## What This Chunk Delivers

Every language with a public registry API gets a dep compatibility checker.
When the user clicks "🔧 Automate" on a "Check dependency compatibility" step,
it scans the module's dependency file, queries the registry for each dep,
and returns a compatibility report — same as Python's `check_dep_compat_pypi`
but for npm, crates.io, rubygems, packagist, and hex.pm.

---

## Execution Steps

### Step 1: Create registry_clients.py

**File:** `src/core/services/module_upgrade/automation/registry_clients.py`

Shared HTTP query functions for all package registries.
Each function takes a package name and returns version metadata.

Functions:
- `query_npm(package) → {name, version, engines_node, requires_python?}`
- `query_crates(crate) → {name, version, rust_version}`
- `query_rubygems(gem) → {name, version, required_ruby_version}`
- `query_packagist(vendor_pkg) → {name, version, require_php}`
- `query_hex(package) → {name, version, elixir_requirement}`

All queries:
- Use `urllib.request` (no external deps, same as existing PyPI pattern)
- 10s timeout per request
- Return `None` on failure (graceful degradation)
- Include proper User-Agent header (required by crates.io and hex.pm)
- Cache results in `.state/registry_cache/` with 1-hour TTL

### Step 2: Create dep_scanner.py

**File:** `src/core/services/module_upgrade/automation/dep_scanner.py`

Per-language dependency file parsers. Each function reads the module's
dependency file and returns a list of package names.

Functions:
- `scan_npm_deps(module_dir) → list[str]` — parse package.json dependencies + devDependencies
- `scan_go_deps(module_dir) → list[str]` — parse go.mod require blocks
- `scan_rust_deps(module_dir) → list[str]` — parse Cargo.toml [dependencies] + [dev-dependencies]
- `scan_ruby_deps(module_dir) → list[str]` — parse Gemfile gem entries
- `scan_php_deps(module_dir) → list[str]` — parse composer.json require
- `scan_elixir_deps(module_dir) → list[str]` — parse mix.exs deps function

Each parser:
- Returns empty list on missing file (not an error)
- Handles common formats (JSON, TOML-like, Ruby DSL, Elixir DSL)
- Filters out stdlib/framework deps where possible
- Returns normalized package names

### Step 3: Add dep checker handlers to dep_checker.py

**File:** `src/core/services/module_upgrade/automation/dep_checker.py`

New handlers following the same pattern as `handle_check_dep_compat_pypi`:

- `handle_check_dep_compat_npm(ctx, mode)` — scan package.json → query npm → report
- `handle_check_dep_compat_crates(ctx, mode)` — scan Cargo.toml → query crates.io → report
- `handle_check_dep_compat_rubygems(ctx, mode)` — scan Gemfile → query rubygems → report
- `handle_check_dep_compat_packagist(ctx, mode)` — scan composer.json → query packagist → report
- `handle_check_dep_compat_hex(ctx, mode)` — scan mix.exs → query hex.pm → report

Each handler:
- Both preview and execute return the same report (read-only)
- Returns: `{ok, findings: [...], compatible_count, incompatible_count, all_compatible}`
- Handles scoped packages (npm @scope/pkg)
- Graceful on registry failures (marks as unknown, doesn't stop)

### Step 4: Update recipes with new automation_ids

**Files:** All recipe JSON files

For each language, change the dep check step from:
```json
{"automatable": false, "automation_id": ""}
```
to:
```json
{"automatable": true, "automation_id": "check_dep_compat_npm"}
```

Also add `update_deps_interactive` equivalent handlers for non-Python that
find alternative versions (same pattern as Python's `handle_update_deps_interactive`):

- `handle_update_deps_npm` — find compatible npm versions
- `handle_update_deps_crates` — find compatible crate versions
- `handle_update_deps_rubygems` — find compatible gem versions
- `handle_update_deps_packagist` — find compatible Packagist versions
- `handle_update_deps_hex` — find compatible hex versions

### Step 5: Update handler registry

**File:** `src/core/services/module_upgrade/automation/__init__.py`

Add all new handlers to the registry dict.

### Step 6: Validate

- All recipe JSON files parse correctly
- All handlers import and register
- Automation coverage audit shows improvement

---

## Files Summary

| Action | File | Est. Lines |
|--------|------|-----------|
| CREATE | `automation/registry_clients.py` | ~250 |
| CREATE | `automation/dep_scanner.py` | ~200 |
| EDIT | `automation/dep_checker.py` | +250 (5 check handlers + 5 update handlers) |
| EDIT | `automation/__init__.py` | +15 (registry entries) |
| EDIT | 7 recipe JSON files | ~5 lines each (mark deps automatable) |

**Total new code:** ~700 lines
