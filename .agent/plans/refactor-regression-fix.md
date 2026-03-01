# Refactor Regression Fix Plan

**Created**: 2026-03-01  
**Root Cause**: AI used memory instead of mechanical transplant when splitting files.  
**Scope**: Core services, web routes, CLI routes — all uncommitted refactoring work.

---

## What Counts As A Regression

- Missing functions / commands
- Changed function signatures (args, options, decorators)
- Changed function body logic (different code paths, different service calls)
- Dropped re-exports that break consumers

## What Is NOT A Regression

- Blank line changes
- Import path updates (expected during refactoring)
- File/function reordering across sub-modules

---

## Fix Methodology (MANDATORY for every file)

1. Extract original from `git show HEAD:<path>`
2. For any MISSING or CHANGED function: copy the EXACT original body into the sub-module
3. Only allowed modification: import paths (absolute → relative within package)
4. Verify: function names, signatures, decorator args, and body logic match original

---

## Phase 1: Core Services (1 file)

### 1.1 `security/__init__.py` — restore dropped re-exports

**Problem**: Private symbols dropped from re-exports: `_SECRET_PATTERNS`, `_SKIP_DIRS`,
`_SKIP_EXTENSIONS`, `_EXPECTED_SECRET_FILES`, `_should_scan`, `_has_nosec`, `_NOSEC_RE`,
`_NOSEC_STRIP_RE` (from common), `_iter_files`, `_sensitive_patterns`, `_is_gitignored`
(from scan).

**Fix**: Add these back to the re-export lists in `security/__init__.py`.

**Source**: `git show HEAD:src/core/services/security_ops.py`

---

## Phase 2: CLI Routes — ALL 19 Domains (HIGHEST RISK)

All CLI work was written from memory. Cannot trust any of it.

For each domain: extract original from git, compare every command, fix mismatches.

### Confirmed broken (wrong commands/signatures):

| Domain | Problem |
|--------|---------|
| `content` | `encrypt`/`decrypt` wrong args, `classify`/`inspect` wrong args, `release restore` + `release inventory` MISSING, replaced with `stage`/`create` |
| `git` | `commit` missing `files` tuple arg (replaced with `stage_all`), `pull` missing `--rebase`, `push` missing `--force` |
| `infra` | ALL env/iac subcommands invented. Original: `env status/vars/diff/validate/generate-example/generate-env`, `iac status/resources`, `infra status`. New: completely different names. |
| `k8s` | `generate manifests` (1 command with `--type`) replaced with 3 separate commands (`deployment`/`service`/`ingress`). `validate` gained extra `path` arg. |
| `terraform` | `generate` was a direct command, turned into a subgroup with `scaffold`. |
| `testing` | `generate template` → `generate tests` (wrong name + wrong args). `generate coverage-config` → `generate config` (wrong name + wrong args). `run_tests` fn renamed to `run`. |

### Needs full body audit (not yet verified):

`audit`, `backup`, `ci`, `dns`, `docker`, `docs`, `metrics`, `packages`, `pages`,
`quality`, `secrets`, `security`, `vault`

### Fix process per domain:

1. `git show HEAD:src/ui/cli/<domain>.py` → extract all commands
2. Compare every `@group.command()` decorator + `def` signature + body against new sub-module
3. Fix any mismatch by pasting original code
4. Verify command count matches

---

## Phase 3: Web Routes — 12 Domains With Body Changes

### Real logic changes (must fix):

| Domain | Function | Problem |
|--------|----------|---------|
| `vault` | `vault_add_keys` | Multi-line function call reformatted to single line |
| `k8s` | `k8s_status` | Import reorganization changed function internals |
| `k8s` | `k8s_env_namespaces` | Import moved inside function body differently |
| `chat` | `chat_thread_create` | Comment replaced with `if is_auth_ok():` logic |
| `integrations` | `gh_auth_device_poll_route` | Comment replaced with if-block |

### Docstring compression (verify intent — may or may not need fixing):

`git_auth` (4 funcs), `metrics` (1), `security_scan` (1), `trace` (9),
`chat` (11), `integrations` (3), `api` (1), `docs` (verify)

### Fix process per domain:

1. `git show HEAD:src/ui/web/routes/<domain>.py` → extract function
2. Compare body logic only (skip blank lines, skip import paths)
3. If logic differs: paste original body, update imports only
4. Verify route count matches

---

## Phase 4: Verification

After each phase, run the function body diff script to confirm zero logic changes remain.

---

## Execution Order

1. **Phase 1** — 1 file, quick fix
2. **Phase 2** — CLI routes, highest risk, most breakage
3. **Phase 3** — Web routes, targeted fixes
4. **Phase 4** — After each phase
