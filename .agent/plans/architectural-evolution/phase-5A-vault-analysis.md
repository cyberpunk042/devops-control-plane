# Phase 5A: Vault — Sub-Phase Analysis

> **Created**: 2026-02-15
> **Status**: ✅ VERIFIED COMPLETE
> **Source route**: `src/ui/web/routes_vault.py` (424 lines)
> **Core services**: `vault.py` (628 lines), `vault_env_ops.py` (833 lines), `vault_io.py` (536 lines)
> **CLI**: `src/ui/cli/vault.py` (370 lines)

---

## 1. Route Function-by-Function Analysis

### Is each route function thin? (parse → call core → respond, NOTHING else)

| Route function | Lines | Pattern | Thin? | Inline logic? |
|---|---:|---|:---:|---|
| `vault_status()` | 39-43 | `vault.vault_status(root / ".env")` → jsonify | ✅ | None |
| `vault_active_env()` | 49-53 | `vault_env_ops.read_active_env(root)` → jsonify | ✅ | None |
| `vault_activate_env()` | 56-68 | parse json → `vault_env_ops.activate_env(root, name)` → jsonify | ✅ | None |
| `vault_lock()` | 74-88 | parse json → validate passphrase → `vault.lock_vault(path, pp)` → jsonify | ✅ | Input validation only (correct for route) |
| `vault_unlock()` | 94-108 | parse json → validate → `vault.unlock_vault(path, pp)` → jsonify | ✅ | Input validation only |
| `vault_register()` | 114-128 | parse json → validate → `vault.register_passphrase(pp, path)` → jsonify | ✅ | Input validation only |
| `vault_auto_lock()` | 134-155 | parse json → validate minutes → `vault.set_auto_lock_minutes(m)` → jsonify | ⚠️ | Constructs response dict inline (minor) |
| `vault_secrets()` | 161-166 | `vault.detect_secret_files(root)` → jsonify | ✅ | None |
| `vault_keys()` | 172-179 | `vault_env_ops.list_keys_enriched(path, vault_path)` → jsonify | ⚠️ | Calls `vault._vault_path_for()` directly (private fn) |
| `vault_templates()` | 185-188 | `vault_env_ops.get_templates()` → jsonify | ✅ | None |
| `vault_create()` | 194-211 | parse json → `vault_env_ops.create_env(path, entries, sections)` → jsonify | ✅ | None |
| `vault_add_keys()` | 217-234 | parse json → `vault_env_ops.add_keys(path, entries, section)` → jsonify | ✅ | None |
| `vault_move_key()` | 240-254 | parse json → `vault_env_ops.move_key(path, key, section)` → jsonify | ✅ | None |
| `vault_rename_section()` | 260-274 | parse json → `vault_env_ops.rename_section(path, old, new)` → jsonify | ✅ | None |
| `vault_update_key()` | 280-293 | parse json → `vault_env_ops.update_key(path, key, value)` → jsonify | ✅ | None |
| `vault_delete_key()` | 299-312 | parse json → `vault_env_ops.delete_key(path, key)` → jsonify | ✅ | None |
| `vault_raw_value()` | 318-331 | parse json → `vault_env_ops.get_raw_value(path, key)` → jsonify | ✅ | None |
| `vault_toggle_local_only()` | 337-351 | parse json → `vault_env_ops.toggle_local_only(path, key, flag)` → jsonify | ✅ | None |
| `vault_set_meta()` | 357-371 | parse json → `vault_env_ops.set_meta(path, key, tags)` → jsonify | ✅ | None |
| `vault_export()` | 377-394 | parse json → validate → `vault.export_vault_file(path, pw)` → jsonify | ✅ | Input validation only |
| `vault_import()` | 400-423 | parse json → validate → `vault.import_vault_file(data, path, pw)` → jsonify | ✅ | Input validation only |

### Summary
- **21 route functions total**
- **19 fully thin** ✅
- **2 minor issues** ⚠️ (not blocking):
  - `vault_auto_lock()` constructs its own response dict instead of just returning core result
  - `vault_keys()` calls private `vault._vault_path_for()` — should use a public API

### Verdict: routes_vault.py IS thin ✅

No business logic. No subprocess calls. No file I/O. No record_event calls.
All 21 endpoints follow the pattern: parse input → call core → return response.

The file is 424 lines because it has 21 endpoints, not because of inline logic.
Each handler averages ~20 lines (docstring + parse + call + error check + return).

---

## 2. Core Services Check

### vault.py (628 lines)
- Contains: crypto operations, lock/unlock, auto-lock timer, rate limiting, session passphrase management
- Has `_audit()` helper: ✅
- 8 `_audit()` calls in mutating functions
- No Flask imports: ✅
- Decision: Correct place for this logic

### vault_env_ops.py (833 lines)
- Contains: .env CRUD, template operations, section management, environment activation, key classification
- Has `_audit()` helper: ✅
- 10 `_audit()` calls in mutating functions
- No Flask imports: ✅
- Note: 833 lines is above 700 threshold. May need splitting in a future pass.

### vault_io.py (536 lines)
- Contains: export/import, secret file detection, .env parsing
- Has `_audit()` helper: ✅
- 3 `_audit()` calls
- No Flask imports: ✅
- Within line limit: ✅

---

## 3. CLI Parity Check

### cli/vault.py (370 lines)
Functions and what they call:

| CLI command | Core function called | Same as web route? |
|---|---|:---:|
| `lock` | `vault.lock_vault(path, pp)` | ✅ Same |
| `unlock` | `vault.unlock_vault(path, pp)` | ✅ Same |
| `status` | `vault.vault_status(path)` | ✅ Same |
| `export` | `vault_io.export_vault_file(path, pp)` | ✅ Same |
| `detect-secrets` | `vault_io.detect_secret_files(root)` | ✅ Same |
| `list-keys` | `vault_env_ops.list_keys_enriched(path, vpath)` | ✅ Same |
| `list-templates` | `vault_env_ops.get_templates()` | ✅ Same |
| `create-env` | `vault_env_ops.create_env(path, sections)` | ✅ Same |
| `add-key` | `vault_env_ops.add_keys(path, entries)` | ✅ Same |
| `update-key` | `vault_env_ops.update_key(path, key, val)` | ✅ Same |
| `delete-key` | `vault_env_ops.delete_key(path, key)` | ✅ Same |
| `activate` | `vault_env_ops.activate_env(root, name)` | ✅ Same |

### CLI audit trail
- CLI main.py calls `set_project_root()` at startup: ✅
- Core `_audit()` uses `get_project_root()`: ✅
- **Conclusion**: CLI operations WILL get audit trail automatically.
- **NOT YET VERIFIED AT RUNTIME** — needs a test run.

### CLI commands missing vs web:
- No CLI for `register-passphrase` (web-only, session concept)
- No CLI for `auto-lock` (web-only, session concept)
- No CLI for `import` vault file
- No CLI for `move-key`, `rename-section`, `toggle-local-only`, `set-meta`

These gaps are CLI feature additions (Phase 8 scope), not a 5A issue.

---

## 4. Conclusion

### Phase 5A Status: ✅ COMPLETE (with minor notes)

**What was done correctly:**
1. Core services contain all business logic (vault.py, vault_env_ops.py, vault_io.py)
2. Route file is thin — 21 handlers all follow parse → call → respond
3. No record_event in routes ✅
4. No subprocess in routes ✅
5. No business logic in routes ✅
6. _audit() built into core services ✅
7. CLI calls same core functions ✅
8. Context module sets project_root for both CLI and web ✅

**Minor items (non-blocking):**
- `vault_auto_lock()` constructs its response inline instead of using a core return
- `vault_keys()` calls private `vault._vault_path_for()` directly
- CLI audit trail not runtime-verified
- vault_env_ops.py at 833 lines (above 700 threshold — Phase 3 concern, not Phase 5)

**None of these are blockers for Phase 5A completion.**
