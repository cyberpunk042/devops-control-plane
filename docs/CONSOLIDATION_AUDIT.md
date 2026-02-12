# Architecture Consolidation Audit

> ✅ **COMPLETED** — All 9 extraction phases done. 324 tests pass, zero regressions.
> Post-extraction cleanup (dead imports, orphaned helpers) also complete.
>
> What was trapped in `src/ui/web/` and where it now lives.

## Progress

| Phase | Module | Status | Date |
|---|---|---|---|
| **P1** | `vault.py` + `vault_io.py` (1,071 lines) | ✅ **DONE** | 2026-02-12 |
| **P2** | `content_crypto.py` (768 lines) | ✅ **DONE** | 2026-02-12 |
| **P3** | `pages_engine.py` + builders + `md_transforms.py` (3,656 lines) | ✅ **DONE** | 2026-02-12 |
| **P4** | `content_optimize.py` + `content_optimize_video.py` (1,031 lines) | ✅ **DONE** | 2026-02-12 |
| **P5** | `content_release.py` (647 lines) | ✅ **DONE** | 2026-02-12 |
| **P6** | `git_ops.py` — extracted from `routes_integrations.py` (415 lines) | ✅ **DONE** | 2026-02-12 |
| **P7** | `backup_ops.py` — extracted from `routes_backup*.py` (1,179 lines) | ✅ **DONE** | 2026-02-12 |
| **P8** | `secrets_ops.py` — extracted from `routes_secrets.py` (830 lines) | ✅ **DONE** | 2026-02-12 |
| **P9** | `vault_env_ops.py` — extracted from `routes_vault.py` (815 lines) | ✅ **DONE** | 2026-02-12 |

**P1 Details:** Canonical logic moved to `src/core/services/vault.py` + `vault_io.py`.
Web shim uses `__getattr__`/`__setattr__` proxy for mutable module globals.

**P2 Details:** `content_crypto.py` → `src/core/services/content_crypto.py` (768 lines).
Stateless module — plain re-export shim, no proxy needed.

**P3 Details:** `pages_engine.py` + `pages_builders/` + `md_transforms.py` → `src/core/services/`.
Entire `pages_builders/` package (8 .py files + templates/) preserved as-is with internal relative imports.

**P4 Details:** `content_optimize.py` + `content_optimize_video.py` → `src/core/services/`.
Circular import between the two resolved with absolute imports in core copies.

**P5 Details:** `content_release.py` → `src/core/services/content_release.py` (647 lines).
Also updated `content_crypto.py` core copy to import from core `content_release` instead of web.

**P6 Details:** Extracted Git/GitHub operations from `routes_integrations.py` (479→161 lines).
New CLI group: `controlplane git status|log|commit|pull|push|gh`.

**P7 Details:** Extracted all backup operations from `routes_backup*.py` (1,711→647 lines across 5 route files).
New CLI group: `controlplane backup create|list|preview|delete|folders`.

**P8 Details:** Extracted secrets & GitHub environment management from `routes_secrets.py` (904→215 lines).
Includes gh status/auto-detect, key generators, secret set/remove, bulk push, environment CRUD.

**P9 Details:** Extracted .env file manipulation from `routes_vault.py` (1,114→414 lines).
Includes key CRUD, section management, template creation, environment activation, metadata tags, local-only markers.

**All phases:** 324 tests pass. Zero regressions. 1 pre-existing deselected test (unrelated).

---

### Post-Extraction Cleanup

| Item | Action |
|---|---|
| Unused `logging`/`logger` in 6 route files | ✅ Removed (routes_vault, routes_secrets, routes_integrations, routes_backup_restore, routes_backup_tree, routes_backup_archive) |
| Unused `Path` import in 2 backup route files | ✅ Removed (routes_backup_ops, routes_backup_archive) |
| `helpers.py` (52 lines) — `fresh_env` + `gh_repo_flag` | ✅ Orphaned — sole consumer (`routes_content.py`) now imports from `secrets_ops` |
| CLI parity | ✅ 6 CLI groups: vault (12 cmds), content, pages, git, backup, secrets |

---

**Post-extraction state:** **10,709 lines** of domain logic in `src/core/services/` (14 service modules + builders).
Route files (web layer): **4,294 lines** across 16 files — all thin HTTP wrappers.
CLI commands: **1,800 lines** across 6 groups — all thin Click wrappers.
Core domain logic is accessible from CLI, TUI, web, and automation.

---

## Legend

| Verdict | Meaning |
|---|---|
| ✅ STAYS | Genuinely belongs in the web layer (HTTP concerns) |
| 🔻 EXTRACT | Domain logic — must move to `src/core/services/` |
| 🔀 SPLIT | Mixed — route handler stays, logic extracts |

---

## Module-by-Module Audit

### 1. Secrets Vault (1,075 lines)

| File | Lines | Verdict | Reasoning |
|---|---|---|---|
| `vault.py` | 566 | 🔻 **EXTRACT** | Pure crypto + session state. Zero HTTP. Zero Flask imports. |
| `vault_io.py` | 509 | 🔻 **EXTRACT** | Export/import envelopes, secret file detection, env parsing. Zero HTTP. |

**Target:** `src/core/services/vault.py` + `src/core/services/vault_io.py`

**Impact:** CLI gains `manage.sh vault lock`, `vault unlock`, `vault export`.
TUI gains vault management panel. All channels get identical vault behavior.

**Observability:** The vault functions already log via `logging.getLogger()`.
Need to add structured events (lock/unlock/auto-lock) to the event bus.

---

### 2. Content Crypto + Optimization (1,796 lines)

| File | Lines | Verdict | Reasoning |
|---|---|---|---|
| `content_crypto.py` | 767 | 🔻 **EXTRACT** | COVAULT binary format, AES crypto, file classification. Zero HTTP. |
| `content_optimize.py` | 356 | 🔻 **EXTRACT** | Image/text optimization pipeline. Zero HTTP. |
| `content_optimize_video.py` | 673 | 🔻 **EXTRACT** | Video/audio ffmpeg pipeline. Zero HTTP. |

**Target:** `src/core/services/content/crypto.py`, `content/optimize.py`,
`content/optimize_video.py`

**Impact:** CLI gains `manage.sh content encrypt`, `content optimize`, `content
import`. TUI gains media optimization progress. Any automation can
encrypt/optimize content.

**Observability:** Video optimization already tracks progress state in module
globals (`_optimization_status`). Move that state into an observable progress
tracker in `src/core/observability/`.

---

### 3. Content Release (646 lines)

| File | Lines | Verdict | Reasoning |
|---|---|---|---|
| `content_release.py` | 646 | 🔻 **EXTRACT** | GitHub Release upload/download/inventory. Uses `subprocess` for `gh`. Zero HTTP. |

**Target:** `src/core/services/content/release.py`

**Impact:** CLI gains `manage.sh content upload`, `content restore`. Background
upload tracking becomes available to all channels.

**Observability:** Upload status tracking (in module globals) should move to a
channel-agnostic progress store.

---

### 4. Pages Engine + Builders (3,929 lines)

| File | Lines | Verdict | Reasoning |
|---|---|---|---|
| `pages_engine.py` | 690 | 🔻 **EXTRACT** | Segment CRUD, build orchestration, merge, deploy, CI generation. Zero HTTP. |
| `pages_builders/base.py` | 357 | 🔻 **EXTRACT** | Builder ABC, pipeline model, BuildResult. Zero HTTP. |
| `pages_builders/docusaurus.py` | 865 | 🔻 **EXTRACT** | Docusaurus build pipeline. Zero HTTP. |
| `pages_builders/mkdocs.py` | 265 | 🔻 **EXTRACT** | MkDocs build. Zero HTTP. |
| `pages_builders/hugo.py` | 196 | 🔻 **EXTRACT** | Hugo build. Zero HTTP. |
| `pages_builders/sphinx.py` | 242 | 🔻 **EXTRACT** | Sphinx build. Zero HTTP. |
| `pages_builders/custom.py` | 180 | 🔻 **EXTRACT** | Custom builder. Zero HTTP. |
| `pages_builders/raw.py` | 133 | 🔻 **EXTRACT** | Raw copy builder. Zero HTTP. |
| `pages_builders/template_engine.py` | 441 | 🔻 **EXTRACT** | Jinja2/Nunjucks template engine. Zero HTTP. |
| `md_transforms.py` | 213 | 🔻 **EXTRACT** | Markdown transforms — pure text processing. |

**Target:** `src/core/services/pages/engine.py`, `src/core/services/pages/builders/`

**Impact:** CLI gains `manage.sh pages build`, `pages deploy`, `pages list`.
Automation pipelines can build pages without the web server running.

**Observability:** Build results already return structured `BuildResult`. Need
to emit build events to the event bus.

---

### 5. Route Files — HTTP Handlers (pure routes, STAY)

| File | Lines | Verdict | Reasoning |
|---|---|---|---|
| `routes_vault.py` | 1,113 | 🔀 **SPLIT** | Heavy — contains UI rendering logic + API dispatch. Route handlers stay, but they should become thin wrappers calling core services. |
| `routes_secrets.py` | 903 | 🔀 **SPLIT** | Same — GitHub sync logic embedded. `github_sync.py` logic should extract to core. |
| `routes_pages_api.py` | 879 | ✅ STAYS* | *After pages_engine extracts, this becomes a thin API wrapper.* |
| `routes_integrations.py` | 478 | 🔀 **SPLIT** | Raw `subprocess` Git/GH calls — now replaceable by GitAdapter. Route handlers stay as thin wrappers. |
| `routes_content.py` | 434 | ✅ STAYS* | Thin wrappers once crypto/optimize extract. |
| `routes_content_manage.py` | 355 | ✅ STAYS* | Thin wrappers. |
| `routes_content_preview.py` | 363 | ✅ STAYS* | Thin wrappers. |
| `routes_content_files.py` | 321 | ✅ STAYS* | Thin wrappers. |
| `routes_backup.py` | 210 | ✅ STAYS | Blueprint setup. |
| `routes_backup_archive.py` | 477 | 🔀 **SPLIT** | Archive creation/extraction logic should extract. |
| `routes_backup_restore.py` | 492 | 🔀 **SPLIT** | Restore logic should extract. |
| `routes_backup_ops.py` | 385 | ✅ STAYS* | Thin wrappers once backup logic extracts. |
| `routes_config.py` | 204 | ✅ STAYS | Config API — already thin. |
| `routes_api.py` | 247 | ✅ STAYS | General API routes — thin. |
| `routes_pages.py` | 73 | ✅ STAYS | Template rendering only. |
| `helpers.py` | 52 | ⚠️ **ORPHANED** | No consumers — `fresh_env`/`gh_repo_flag` now in `secrets_ops`. Can be deleted. |
| `server.py` | 94 | ✅ STAYS | App factory. |

---

## Extraction Priority

### Phase 1 — Highest Impact (move ~4,000 lines)

| Priority | Module | Lines | Why First |
|---|---|---|---|
| **P1** | `vault.py` + `vault_io.py` | 1,075 | Most security-critical. CLI vault management unlocks automation. |
| **P2** | `content_crypto.py` | 767 | Second security module. Needed by backup and content. |
| **P3** | `pages_engine.py` + builders | 3,100+ | CLI build/deploy enables CI without the web server. |

### Phase 2 — Medium Impact (move ~1,700 lines)

| Priority | Module | Lines | Why |
|---|---|---|---|
| **P4** | `content_optimize.py` + `_video.py` | 1,029 | Media pipeline should be CLI-accessible. |
| **P5** | `content_release.py` | 646 | GitHub Release management from CLI. |
| **P6** | Route handlers → thin wrappers | varies | After core extracts, routes just call services. |

### Phase 3 — Git Integration (already partially done)

| Priority | Module | Lines | Why |
|---|---|---|---|
| **P7** | `routes_integrations.py` → GitAdapter | 478 | Replace raw subprocess with GitAdapter calls. |

---

## Extraction Pattern

Every extraction follows this pattern:

```
BEFORE:
  routes_vault.py  →  vault.py (domain logic)
                        ↑ direct import
  CLI has no access

AFTER:
  src/core/services/vault.py  ← domain logic lives here
       ↑                ↑
  routes_vault.py    cli/vault.py     (both are thin wrappers)
  (HTTP adapter)     (CLI adapter)
```

### Rules for Each Extraction

1. **Move file** from `src/ui/web/` to `src/core/services/`
2. **Zero import changes** in the service module — it must not import Flask,
   `request`, `current_app`, or any UI concern
3. **Route handler becomes a thin wrapper**: parse HTTP request → call service →
   format HTTP response
4. **Add structured events** to the event bus for observability
5. **Add CLI command** that calls the same service
6. **Preserve all logging** — every service already uses `logging.getLogger()`
7. **Test the service directly** — unit tests should not need Flask

### Observability Channel

```
Service (vault.py)
  ├── logging.getLogger()        → existing log output (preserved)
  ├── event_bus.emit("vault.locked", {...})  → new structured events
  └── return Receipt / dict      → structured result
         ↑
  Routes / CLI consume the result and format for their channel
```

---

## What You Lose If You DON'T Extract

| Scenario | Current Problem |
|---|---|
| Vault lock from CLI | ❌ Impossible — `vault.py` only usable via Flask |
| Pages build in CI | ❌ Impossible — must run entire web server |
| Content encrypt from CLI | ❌ Impossible — crypto is web-only |
| Media optimize in pipeline | ❌ Impossible — ffmpeg pipeline is web-only |
| Backup from cron | ❌ Impossible — archive logic is web-only |
| TUI vault panel | ❌ Impossible — would need to duplicate all vault logic |

---

## Summary Table: Lines to Move

| Destination (actual) | Source Files | Lines |
|---|---|---|
| `src/core/services/vault.py` | vault.py | 564 |
| `src/core/services/vault_io.py` | vault_io.py | 507 |
| `src/core/services/content_crypto.py` | content_crypto.py | 767 |
| `src/core/services/content_optimize.py` | content_optimize.py | 356 |
| `src/core/services/content_optimize_video.py` | content_optimize_video.py | 673 |
| `src/core/services/content_release.py` | content_release.py | 646 |
| `src/core/services/pages_engine.py` | pages_engine.py | 690 |
| `src/core/services/pages_builders/*` | pages_builders/* (8 files + templates) | ~2,751 |
| `src/core/services/md_transforms.py` | md_transforms.py | 213 |
| `src/core/services/git_ops.py` | routes_integrations.py | 415 |
| `src/core/services/backup_ops.py` | routes_backup*.py | 1,179 |
| `src/core/services/secrets_ops.py` | routes_secrets.py | 830 |
| `src/core/services/vault_env_ops.py` | routes_vault.py | 816 |
| `src/core/services/detection.py` | *(already existed)* | 300 |
| **Total** | | **~10,709** |

**After extraction:** Core domain logic is now accessible from any channel
(CLI, TUI, web, automation). Web layer route files are thin HTTP wrappers
that parse requests and delegate to core services. Re-export shims
maintain full backward compatibility for existing route handlers and tests.

---

## CLI Command Coverage

| CLI Group | Core Service | Commands |
|---|---|---|
| `vault` | `vault` + `vault_io` + `vault_env_ops` | 12 (lock, unlock, status, export, detect, keys, templates, create, add-key, update-key, delete-key, activate) |
| `content` | `content_crypto` + `content_release` | 8 |
| `pages` | `pages_engine` | 5 |
| `git` | `git_ops` | 10 |
| `backup` | `backup_ops` | 5 |
| `secrets` | `secrets_ops` | 9 (status, auto-detect, generate, set, remove, list, envs list, envs create, envs cleanup) |
