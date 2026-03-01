# Revolution Progress Tracker

> Started: 2026-02-28
> Rule: <500 lines per file. ~700 absolute max exception. SRP. Onion folders.
> Process: Refactor → fix imports → verify → document README per domain.

---

## Status Legend

- ⬜ Not started
- 🔵 Planned (chunk scoped)
- 🟡 In progress
- 🟢 Complete
- ⏸️ Blocked / Parked

---

## Chunk 1 — Recent Concerns (Priority)

These are the domains we've been actively working in. They hurt the most
because every session touches them and gets lost.

### Backend `core/services/`

| # | Domain | Current State | Target | Status |
|---|--------|--------------|--------|--------|
| 1 | **git/** | `git_auth.py`, `git_ops.py`, `git_gh_ops.py` (951) flat | `git/` folder, split `gh_ops.py` | 🟢 |
| 2 | **wizard/** | `wizard_ops.py` (748), `wizard_setup.py` (1,568), `wizard_validate.py` flat | `wizard/` folder, split `setup.py` by integration | 🟢 |
| 3 | **vault/** | `vault.py` (630), `vault_io.py`, `vault_env_crud.py`, `vault_env_ops.py` flat | `vault/` folder | 🟢 |
| 4 | **secrets/** | `secrets_env_ops.py`, `secrets_gh_ops.py`, `secrets_ops.py` flat | `secrets/` folder | 🟢 |
| 5 | **audit/** (existing) | Already grouped but `l0_detection.py` (1,601), `catalog.py` (~1,100) | Split oversized files | 🟢 |
| 6 | **tool_install/data/** | `recipes.py` **✅ DONE** → `recipes/` (29 files). `remediation_handlers.py` **✅ DONE** → `remediation_handlers/` (25 files). `tool_failure_handlers.py` **✅ DONE** → `tool_failure_handlers/` (13 files) | All data files split | 🟢 |
| 7 | **ci/** | `ci_compose.py` (544), `ci_ops.py` (592) flat → `ci/` package (ops.py + compose.py + __init__.py + README) | `ci/` folder | 🟢 |

### Routes `ui/web/`

| # | Domain | Current State | Target | Status |
|---|--------|--------------|--------|--------|
| 8 | **routes/ package** | ~~33 flat `routes_*.py` in `ui/web/`~~ → 5 sub-packages + 23 standalone in `routes/` | `routes/` package (Option B: domain grouping) | 🟢 |
| 9 | **routes_audit.py** | ~~1,781 lines~~ → 7 sub-modules in `routes/audit/` (1,840 lines) | Split into `routes/audit/` | 🟢 |
| 10 | **routes_integrations.py** | 520 lines, 27 routes — all git/GitHub thin dispatchers | Evaluated: stays as-is (single domain, under threshold) | 🟢 |

### Frontend `templates/scripts/`

| # | Domain | Current State | Target | Status |
|---|--------|--------------|--------|--------|
| 11 | **globals/ split** | ~~`_globals.html` (3,606)~~ → 7 files in `globals/` (api, cache, card_builders, modal, missing_tools, ops_modal, auth_modal) | Split into `globals/` folder | 🟢 |
| 12 | **auth/ group** | ~~flat~~ → 2 files in `auth/` | `auth/` folder | 🟢 |
| 13 | **integrations/ group** | ~~22 flat~~ → 13 + `setup/` (10) in `integrations/` | `integrations/` + `setup/` folders | 🟢 |
| 14 | **secrets/ group** | ~~6 flat~~ → 7 files in `secrets/` | `secrets/` folder | 🟢 |
| 15 | **audit/ group** | ~~6 flat~~ → 6 files in `audit/` (manager stays in devops) | `audit/` folder | 🟢 |
| 16 | **wizard/ group** | ~~8 flat~~ → 9 files in `wizard/` (incl. modal + setup) | `wizard/` folder | 🟢 |
| 17 | **assistant/ group** | ~~6 flat~~ → 6 files in `assistant/` | `assistant/` folder | 🟢 |
| 17b | **content/ group** | ~~14 flat~~ → 14 files in `content/` | `content/` folder | 🟢 |
| 17c | **devops/ group** | ~~11 flat~~ → 12 files in `devops/` (incl. audit_manager) | `devops/` folder | 🟢 |

---

## Chunk 2 — Remaining Backend Domains

| # | Domain | Current State | Target | Status |
|---|--------|--------------|--------|--------|
| 18 | **docker/** | ~~6 flat files (~2,600 lines)~~ → `docker/` package (5 modules + `__init__` + README), `docker_ops.py` compat shim | `docker/` folder | 🟢 |
| 19 | **k8s/** | ~~12 flat files (~10,500), `k8s_validate.py` (4,004!)~~ → `k8s/` package (19 modules + `__init__` + README), validate split into 7 layers, `k8s_ops.py` compat shim | `k8s/` folder, split validate | 🟢 |
| 20 | **content/** | ~~9 flat files (~3,680)~~ → `content/` package (9 modules + `__init__`), no facade needed (consumers import directly) | `content/` folder | 🟢 |
| 21 | **terraform/** | ~~3 flat files (~1,420)~~ → `terraform/` package (3 modules + `__init__`), 3 backward-compat shims | `terraform/` folder | 🟢 |
| 22 | **backup/** | ~~5 flat files (~1,700)~~ → `backup/` package (5 modules + `__init__`), 5 backward-compat shims | `backup/` folder | 🟢 |
| 23 | **devops/** | ~~2 flat files (~1,560)~~ → `devops/` package (2 modules + `__init__`), 2 backward-compat shims | `devops/` folder | 🟢 |
| 24 | **security/** | 4 flat files (~1,300) | `security/` folder | ⬜ |
| 25 | **pages/** | 6 flat files (~1,700) | `pages/` folder | ⬜ |
| 26 | **dns/** | 1 file (564) | `dns/` folder | ⬜ |
| 27 | **docs/** (service) | 2 files (~730) | `docs/` folder | ⬜ |
| 28 | **quality/** | 1 file (500) | `quality/` folder | ⬜ |
| 29 | **testing/** | 2 files (~900) | `testing/` folder | ⬜ |
| 30 | **metrics/** | 1 file (570) | `metrics/` folder | ⬜ |
| 31 | **shared/** | 10+ cross-cutting files (~3,000) | `shared/` folder | ⬜ |
| 32 | **chat/** (existing) | `chat_refs.py` (1,280), `chat_ops.py` (731) | Split oversized | ⬜ |
| 33 | **generators/** (existing) | `github_workflow.py` (1,081) | Split oversized | ⬜ |

---

## Chunk 3 — Remaining Frontend + Polish

| # | Domain | Current State | Target | Status |
|---|--------|--------------|--------|--------|
| 34 | **content/ group** | ~~duplicate of #17b~~ | Done in Chunk 1 | 🟢 |
| 35 | **devops/ group** | ~~duplicate of #17c~~ | Done in Chunk 1 | 🟢 |
| 36 | **debug/ group** | `_debugging.html` (1,145), `_stage_debugger.html` (702) | `debug/` folder, split debugging | ⬜ |
| 37 | **CSS split** | `admin.css` (5,948) single file | Domain-scoped CSS files | ⬜ |
| 38 | **Tests follow** | Large test files mirror old paths | Rename/split to match new structure | ⬜ |
| 39 | **Stale docs** | `docs/ARCHITECTURE.md` etc. outdated | Update to reflect new structure | ⬜ |

---

## Completion Summary

| Chunk | Items | Done | Remaining |
|-------|-------|------|-----------|
| Chunk 1 (Recent Concerns) | 19 | 19 | 0 |
| Chunk 2 (Remaining Backend) | 16 | 0 | 16 |
| Chunk 3 (Remaining FE + Polish) | 6 | 2 | 4 |
| **Total** | **39** | **21** | **18** |
