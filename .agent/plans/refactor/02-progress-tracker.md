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
| 10 | **routes_integrations.py** | 520 lines | Evaluate split | ⬜ |

### Frontend `templates/scripts/`

| # | Domain | Current State | Target | Status |
|---|--------|--------------|--------|--------|
| 11 | **globals/ split** | `_globals.html` (3,606) god file | Split into `globals/` folder (10+ focused files) | ⬜ |
| 12 | **auth/ group** | `_git_auth.html`, `_gh_auth.html` flat | `auth/` folder | ⬜ |
| 13 | **integrations/ group** | 12 flat `_integrations_*.html` files, several >700 | `integrations/` + `integrations/setup/` folders | ⬜ |
| 14 | **secrets/ group** | 6 flat `_secrets_*.html` | `secrets/` folder | ⬜ |
| 15 | **audit/ group** | 6 flat `_audit_*.html` | `audit/` folder | ⬜ |
| 16 | **wizard/ group** | `_wizard_*.html` (5 files), `_setup_wizard.html`, `_wizard_integrations.html` (2,051) | `wizard/` folder, split `_wizard_integrations.html` | ⬜ |
| 17 | **assistant/ group** | 6 flat `_assistant_*.html`, engine (1,117), docker resolvers (1,256) | `assistant/` folder, split oversized | ⬜ |

---

## Chunk 2 — Remaining Backend Domains

| # | Domain | Current State | Target | Status |
|---|--------|--------------|--------|--------|
| 18 | **docker/** | 6 flat files (~2,600 lines) | `docker/` folder | ⬜ |
| 19 | **k8s/** | 12 flat files (~10,500), `k8s_validate.py` (4,004!) | `k8s/` folder, split validate | ⬜ |
| 20 | **content/** | 9 flat files (~4,800) | `content/` folder | ⬜ |
| 21 | **terraform/** | 3 flat files (~1,600) | `terraform/` folder | ⬜ |
| 22 | **backup/** | 5 flat files (~2,100) | `backup/` folder | ⬜ |
| 23 | **devops/** | 4 flat files (~2,600), `activity.py` (864) | `devops/` folder, split activity | ⬜ |
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
| 34 | **content/ group** | 10 flat `_content_*.html`, chat (1,159), refs (955) | `content/` folder, split oversized | ⬜ |
| 35 | **devops/ group** | 10 flat `_devops_*.html` | `devops/` folder | ⬜ |
| 36 | **debug/ group** | `_debugging.html` (1,145), `_stage_debugger.html` (702) | `debug/` folder, split debugging | ⬜ |
| 37 | **CSS split** | `admin.css` (5,948) single file | Domain-scoped CSS files | ⬜ |
| 38 | **Tests follow** | Large test files mirror old paths | Rename/split to match new structure | ⬜ |
| 39 | **Stale docs** | `docs/ARCHITECTURE.md` etc. outdated | Update to reflect new structure | ⬜ |

---

## Completion Summary

| Chunk | Items | Done | Remaining |
|-------|-------|------|-----------|
| Chunk 1 (Recent Concerns) | 17 | 9 | 8 |
| Chunk 2 (Remaining Backend) | 16 | 0 | 16 |
| Chunk 3 (Remaining FE + Polish) | 6 | 0 | 6 |
| **Total** | **39** | **9** | **30** |
