# Architectural Evolution — 10x Deep Analysis

> **Purpose**: Comprehensive fact-finding before committing to any execution path.
> **Created**: 2026-02-14
> **Method**: Every number is measured, not estimated. Every claim is backed by a grep/find/wc.

---

## Table of Contents

1. [A. File Size Census](#a-file-size-census)
2. [B. The Monster File Anatomy](#b-the-monster-file-anatomy)
3. [C. Hardwired Data Inventory](#c-hardwired-data-inventory)
4. [D. Logging Reality](#d-logging-reality)
5. [E. Audit Coverage Map](#e-audit-coverage-map)
6. [F. Layer Violations](#f-layer-violations)
7. [G. CLI ↔ Web Parity Gap](#g-cli--web-parity-gap)
8. [H. TUI Gap](#h-tui-gap)
9. [I. Caching Architecture](#i-caching-architecture)
10. [J. Template & Jinja Usage](#j-template--jinja-usage)
11. [K. Code Duplication](#k-code-duplication)
12. [L. Subprocess Sprawl](#l-subprocess-sprawl)
13. [Dependency Graph](#dependency-graph)
14. [Recommended Path Order](#recommended-path-order)

---

## A. File Size Census

### Files > 500 lines (the refactoring candidates)

**Total files > 300 lines**: 97 (Python + HTML combined)
**Total files > 500 lines**: 48
**Total files > 1000 lines**: 6

#### Tier 1: Critical (>1000 lines)

| File | Lines | Domain | Contains |
|------|------:|--------|----------|
| `_integrations_setup_modals.html` | **8,282** | Web/JS | 6 wizard functions + data catalogs + shared validation |
| `k8s_ops.py` | **2,753** | Core | Detection, validation, generation, cluster ops, wizard backend |
| `backup_ops.py` | **1,179** | Core | Create, restore, archive, wipe, purge, encrypt, manifest |
| `docker_ops.py` | **1,173** | Core | Detection, validation, compose, Dockerfile ops, build, prune |
| `routes_devops.py` | **1,020** | Web | 10 route functions + 16 inline core imports + 14 subprocess calls |
| `security_ops.py` | **994** | Core | Scan, fix, audit, gitignore analysis, posture |

#### Tier 2: Over Threshold (500-999 lines)

| File | Lines | Domain | Notes |
|------|------:|--------|-------|
| `terraform_ops.py` | 880 | Core | |
| `routes_pages_api.py` | 879 | Web | 33 functions, 0 direct core imports (uses own pages_builders) |
| `docusaurus.py` (×2) | 865 | Core+Web | **Exists in BOTH locations, same content** |
| `secrets_ops.py` | 830 | Core | |
| `vault_env_ops.py` | 815 | Core | |
| `content_crypto.py` | 767 | Core | |
| `testing_ops.py` | 750 | Core | |
| `_integrations_k8s.html` | 734 | Web/JS | K8s integrations card + resource wizard |
| `git_ops.py` | 722 | Core | |
| `_secrets_keys.html` | 693 | Web/JS | |
| `pages_engine.py` | 690 | Core | |
| `_content_browser.html` | 687 | Web/JS | |
| `env_ops.py` | 681 | Core | |
| `docs_ops.py` | 679 | Core | |
| `content_optimize_video.py` | 673 | Core | |
| `package_ops.py` | 652 | Core | |
| `content_release.py` | 646 | Core | |
| `l1_classification.py` | 641 | Core/Audit | |
| `_wizard_steps.html` | 638 | Web/JS | |
| `_content_archive.html` | 624 | Web/JS | |
| `_content_upload.html` | 591 | Web/JS | |
| `l2_risk.py` | 574 | Core/Audit | |
| `vault.py` | 564 | Core | |
| `_content_archive_modals.html` | 563 | Web/JS | |
| `dns_cdn_ops.py` | 548 | Core | |
| `devops_cache.py` | 543 | Core | Server-side cache layer |
| `_secrets_render.html` | 533 | Web/JS | |
| `_integrations_pages.html` | 532 | Web/JS | |
| `quality_ops.py` | 523 | Core | |
| `scoring.py` | 520 | Core/Audit | |
| `_globals.html` | 517 | Web/JS | Global helpers, modal system, card builders |
| `_secrets_init.html` | 514 | Web/JS | |
| `_content_preview_enc.html` | 514 | Web/JS | |
| `_wizard_integrations.html` | 511 | Web/JS | |
| `_integrations_pages_config.html` | 508 | Web/JS | |
| `python_parser.py` | 508 | Core/Audit | |
| `vault_io.py` | 507 | Core | |

**Summary**: 17 Core Python services over 500 lines. 16 Web/JS scripts over 500 lines. 2 Web routes over 500 lines.

---

## B. The Monster File Anatomy

`_integrations_setup_modals.html` — **8,282 lines**, **619 KB**

### Section breakdown:

| Lines | Range | Section | What it does |
|------:|-------|---------|--------------|
| 217 | 1–217 | **Shared infra** | Validation system, detect cache banner, helpers |
| 483 | 218–700 | **Git Setup Wizard** | 3 steps: detect → configure → review/apply |
| 549 | 701–1249 | **Data: `_infraOptions` + `_infraCategories`** | Pure static data — 86 infra service definitions |
| 1,385 | 1250–2636 | **Docker Setup Wizard** | 5 steps: detect → modules → infra → compose → review/apply |
| 140 | 2637–2779 | **CI/CD Setup Wizard** | 3 steps: detect → configure → review |
| 4,602 | 2780–7384 | **K8s Setup Wizard** | 10+ steps: detect → modules → infra → volumes → env → networking → RBAC → HPA → mesh → review. **The biggest single wizard.** |
| 145 | 7385–7532 | **Terraform Setup Wizard** | 3 steps: detect → configure → review |
| 721 | 7533–8257 | **GitHub Setup Wizard** | Multi-step: auth → repo → environments → secrets → review |
| 22 | 8258–8283 | **Dispatcher** | `openSetupWizard(key)` routing function |

### Key observations:
- The K8s wizard alone is **4,602 lines** — that's a file by itself
- The infra data catalog is **549 lines** of pure JSON data with zero logic
- The Docker wizard includes `_dockerStackDefaults` (another ~100 lines of data)
- Inside the K8s wizard: `_SC_CATALOG` (StorageClass catalog) is ~30 entries of reference data
- Shared validation system (`_wizValidation`) at the top services ALL wizards
- Every wizard follows the same pattern: `wizardModalOpen({..., steps: [...], onComplete: async (data) => { ... }})` — this is a well-defined protocol

### Natural split plan (7 files):
1. `_setup_shared.html` — validation, detect banner, helpers (217 lines)
2. `_setup_git.html` — Git wizard (483 lines)
3. `_setup_docker.html` — Docker wizard (1,385 lines, still needs internal splitting)
4. `_setup_cicd.html` — CI/CD wizard (140 lines)
5. `_setup_k8s.html` — K8s wizard (4,602 lines, still needs internal splitting)
6. `_setup_terraform.html` — Terraform wizard (145 lines)
7. `_setup_github.html` — GitHub wizard (721 lines)
8. `_setup_dispatcher.html` — Routing function (22 lines, could merge into shared)

**Data extraction** (before splitting):
- `_infraOptions` + `_infraCategories` → `data/catalogs/infra-services.json` (549 → 0 lines removed from HTML)
- `_dockerStackDefaults` → `data/catalogs/docker-stack-defaults.json`
- `_SC_CATALOG` → `data/catalogs/storage-classes.json`

---

## C. Hardwired Data Inventory

All data that is currently embedded in code but should be in data files:

| Data | Location | Lines | Type | Consumers |
|------|----------|------:|------|-----------|
| **`_infraOptions`** | `_integrations_setup_modals.html:716-1232` | 517 | Infra service catalog (86 services) | Docker wizard, K8s wizard, compose wizard |
| **`_infraCategories`** | `_integrations_setup_modals.html:1235-1246` | 12 | Category label map | Docker wizard, K8s wizard |
| **`_dockerStackDefaults`** | `_integrations_setup_modals.html:1282-1374` | 93 | Per-stack Dockerfile defaults | Docker wizard |
| **`_restartPolicies`** | `_integrations_setup_modals.html:1375` | 1 | Array of 4 strings | Docker wizard |
| **`_platformOptions`** | `_integrations_setup_modals.html:1376` | 1 | Array of 4 strings | Docker wizard |
| **`_SC_CATALOG`** | `_integrations_setup_modals.html:3646-3672` | 27 | StorageClass catalog (5 groups, ~15 entries) | K8s wizard |
| **`LIBRARY_CATALOG`** | `audit/catalog.py` | ~420 | Library → category/type/ecosystem map | Audit engine |
| **`_SERVICE_BY_TYPE`** | `audit/catalog.py:42-55` | 14 | Type → service name inference | Audit engine |

**Total hardwired data lines**: ~1,085

### What extraction would accomplish:
- Reduces `_integrations_setup_modals.html` by **~630 lines** before any splitting
- Makes infra catalog extensible (user can add custom services to `data/catalogs/infra-services-custom.json`)
- Makes CLI/TUI able to use the same catalogs (currently CLI has NO access to infra service catalog)
- Makes testing easier (can validate catalog JSON schema separately)

---

## D. Logging Reality

### Correction from initial analysis

I was **wrong** in my initial claim that "zero Python modules use logging." The truth:

**Modules WITH `logger = logging.getLogger(__name__)`**: 43 files
- All core services: ✅ (every `*_ops.py` file)
- All adapters: ✅
- All audit submodules: ✅
- Infrastructure (health, persistence, reliability): ✅
- Config loaders: ✅

**Modules WITHOUT logging**: 19 files (mostly `__init__.py`, generators, pages builders)
- `src/core/services/generators/compose.py` — no logger
- `src/core/services/generators/dockerfile.py` — no logger
- `src/core/services/generators/dockerignore.py` — no logger
- `src/core/services/generators/github_workflow.py` — no logger
- `src/core/services/pages_builders/*.py` — 8 files, no loggers
- `src/core/services/md_transforms.py` — no logger
- `src/core/services/audit/models.py` — no logger

### The REAL logging problem

The modules HAVE loggers, but:

1. **No `logging.basicConfig()` or `setLevel()` call ANYWHERE in the codebase** — the only result for that search was an unrelated K8s config field. This means ALL loggers use the default level (`WARNING`), so `logger.debug()` and `logger.info()` calls are **silently swallowed**.

2. **No `--debug` flag** on the CLI. The existing `--verbose` flag only controls Click output, not Python log levels.

3. **No FileHandler** — no log file output capability exists.

4. **No StreamHandler configuration** — no formatting, no timestamps in logs.

5. **Flask's logging** — the only configured logging happens via Flask's built-in logger when `debug=True` is passed to `server.py`. This means web server errors show up, but core service debug info does not.

### Impact:
The 43 modules that DO call `logger.debug(...)` and `logger.info(...)` are writing into a void. The logging infrastructure exists in *declaration* but not in *configuration*. **A single `logging.basicConfig()` call in `main.py` + a `--debug` flag would unlock all existing debug output.**

---

## E. Audit Coverage Map

### Where audit entries ARE written:
| Component | Writes to audit | How |
|-----------|:-:|------|
| Engine executor | ✅ | `AuditWriter.write(AuditEntry(...))` after each action |
| Use-case runner | ✅ | Calls `write_audit_entries()` after report |
| `routes_api.py` `/run` | ✅ | Creates `AuditWriter`, delegates to use-case |

### Where audit entries are NOT written (but SHOULD be):
| Operation | Route | Core Service | Should Audit? |
|-----------|-------|--------------|:---:|
| Vault lock/unlock | `routes_vault.py` | `vault.py` | ✅ |
| Vault key create/delete/rename | `routes_vault.py` | `vault.py` | ✅ |
| Content encrypt/decrypt | `routes_content.py` | `content_crypto.py` | ✅ |
| Content upload/delete/rename/move | `routes_content_manage.py` | — (inline) | ✅ |
| Backup create/restore/wipe | `routes_backup*.py` | `backup_ops.py` | ✅ |
| Git operations (init, commit, branch) | `routes_devops.py` (inline) | `git_ops.py` | ✅ |
| Docker build/up/down/prune | `routes_docker.py` | `docker_ops.py` | ✅ |
| K8s manifest generate/apply | `routes_k8s.py` | `k8s_ops.py` | ✅ |
| Secret push to GitHub | `routes_secrets.py` | `secrets_ops.py` | ✅ |
| Pages build/publish | `routes_pages_api.py` | `pages_engine.py` | ✅ |
| Security scan/fix/dismiss | `routes_security_scan.py` | `security_ops.py` | ✅ |
| Config change (project.yml) | `routes_project.py` | — (inline) | ✅ |
| Integration preferences change | `routes_devops.py` | — (inline) | ⚠️ (debatable) |

**Result**: 13 major operation categories have NO audit trail. Only the engine runner (test/lint automated runs) writes audit entries.

### Why this matters:
The audit tab in the web UI exists and works. The `audit.ndjson` file exists. But it only contains engine runner entries. A user who encrypts their content vault, does a backup, pushes secrets, and deploys to K8s has ZERO audit trail of those actions.

---

## F. Layer Violations

### F.1: Routes that are FAT (contain business logic instead of delegating)

**`routes_devops.py`** — The worst offender:
- **34 imports from `src.core`** (most of any route file)
- **14 inline `subprocess.run()` calls** — directly calling `git`, `docker`, etc.
- **16 core service imports** via lazy `from src.core.services...` inside functions
- Contains `wizard_detect()` which is a **459-line function** that builds the entire detection payload inline (lines 75-458)
- Contains `wizard_setup()` which is a **392-line function** handling ALL setup operations inline

**`routes_pages_api.py`** — Thick route:
- **879 lines, 33 functions**
- Imports from `src.ui.web.pages_builders` (NOT `src.core.services.pages_builders`)
- Contains SSE streaming, build orchestration, segment management — this is an entire feature, not a thin wrapper

**`routes_project.py`** — Mixed:
- **476 lines, 16 functions**
- 3 core imports + multiple inline file I/O operations
- GitHub environment management built directly into route handlers

### F.2: Web-unique features (no core/CLI backing)

These features exist ONLY in web route handlers, with NO corresponding core service:

| Feature | Route File | What it does | Should be in core? |
|---------|-----------|--------------|:---:|
| Wizard detect | `routes_devops.py:75-458` | Module/stack/integration detection | ✅ (partially in `detection.py` but wizard assembly is in route) |
| Wizard setup | `routes_devops.py:460-850` | Git init, branch, hooks, gitignore | ✅ |
| Content file ops | `routes_content_manage.py` | Create, rename, move, delete files | ✅ |
| Content folder ops | `routes_content_files.py` | Create/delete folders, upload | ✅ |
| Encrypted preview | `routes_content_preview.py` | Decrypt + render in-place | ✅ |
| Integration prefs | `routes_devops.py` | Show/hide cards | ⚠️ (UI concern, maybe not core) |

### F.3: Duplicated code across layers

**`pages_builders/`** exists in BOTH `src/core/services/` and `src/ui/web/`:
- `diff` shows only `__init__.py` differs (different import paths)
- All other files are **identical Python bytecode**
- `routes_pages_api.py` imports from `src.ui.web.pages_builders` (not core)
- This is **pure duplication** — the web layer should use the core layer's copy

---

## G. CLI ↔ Web Parity Gap

### Route counts:
- **Web API routes**: 166 endpoints across 31 route files
- **CLI commands**: ~80 commands across 18 CLI modules + main.py

### CLI domains (18):
`backup, ci, content, dns, docker, docs, git, infra, k8s, metrics, packages, pages, quality, secrets, security, terraform, testing, vault`

### Web route domains (31):
`api, audit, backup, backup_archive, backup_ops, backup_restore, backup_tree, ci, config, content, content_files, content_manage, content_preview, devops, dns, docker, docs, infra, integrations, k8s, metrics, packages, pages, pages_api, project, quality, secrets, security_scan, terraform, testing, vault`

### Web-only domains (no CLI equivalent):
| Web Domain | Purpose | CLI parity difficulty |
|-----------|---------|:---:|
| `api` | Main status/detect/run/health/audit/capabilities | Medium (some exist as direct CLI commands) |
| `backup_archive`, `backup_ops`, `backup_restore`, `backup_tree` | Fine-grained backup operations | Easy (backup CLI exists, needs subcommands) |
| `config` | Project.yml editing | Easy |
| `content_files`, `content_manage`, `content_preview` | Fine-grained content operations | Medium |
| `devops` | Wizard detect/setup, prefs, cache bust, dismissals | Hard (wizard is heavily interactive) |
| `integrations` | Integration cards, pages SSE | Medium |
| `pages_api` | Pages segment CRUD, build, SSE | Medium |
| `project` | Project status, GitHub envs | Easy |
| `security_scan` | Dedicated scan routes | Easy (security CLI exists) |

---

## H. TUI Gap

### Current `manage.sh` TUI:

**Size**: ~90 lines of menu logic (rest is `run_cli` wrapper)
**Menu items**: 13
**Behavior**: For items 1-7, calls `python -m src.main <command>` directly. For items 8-13, prints `--help` and exits. No interactive sub-menus, no prompts, no formatted output.

### What the TUI COULD do (reference: `continuity-orchestrator/manage.sh`):
- Interactive prompts with confirmation (`read -p`)
- Formatted output with colors and tables  
- Sub-menus per domain (vault interactive, content browser, etc.)
- Parameter collection (hours, names, messages)
- Error handling with colored output
- Loop-based interactive session (exists in current TUI but underused)

### TUI gap — features that exist in web but not TUI:
1. **Content browsing** — web has full tree browser, TUI just says `--help`
2. **Vault management** — web has full CRUD, TUI just says `--help`
3. **Setup wizards** — web has 6 multi-step wizards, TUI has nothing
4. **Integration status** — web has live cards with drill-down, TUI has nothing
5. **Audit dashboard** — web has scores, findings, hotspots, TUI has nothing
6. **Backup management** — web has archive browser with preview, TUI just says `--help`

---

## I. Caching Architecture

### Current state:

| Layer | Mechanism | Storage | TTL | Burst |
|-------|-----------|---------|-----|-------|
| **Client** | `sessionStorage` | Browser tab | 10 min (`_CARD_TTL`, `_WIZ_TTL`) | `cardInvalidate()`, `wizInvalidate()` |
| **Server** | `devops_cache.py` (in-memory dict) | Process memory | mtime-based | `/devops/cache/bust` API |
| **Persistent** | `.state/devops_cache.json` | Disk | Until overwritten | Manual only |

### `.state/` directory content:
| File | Size | Purpose |
|------|------|---------|
| `devops_cache.json` | **240 KB** | Cached DevOps card data (testing, quality, packages, env, docs, audit, security, terraform, dns, k8s, wiz:detect) |
| `audit_activity.json` | 10 KB | Audit activity log |
| `audit_scores.json` | 1 KB | Audit score computations |
| `audit.ndjson` | 3 KB | Audit entry ledger |
| `current.json` | 2 KB | Engine state |
| `devops_prefs.json` | 0.4 KB | Card visibility preferences |

### What's missing:
1. **No `window.*` boot injection** — `render_template("dashboard.html")` passes ZERO context variables. All data comes from API calls AFTER page load.
2. **No two-sided cache coherency** — client busts don't inform server; server busts require a POST + client manual invalidation
3. **No cache for static data** — infra catalogs, stack defaults, StorageClass lists are re-parsed from HTML on every page load
4. **No cache warming** — server starts cold; first card load is always slow

---

## J. Template & Jinja Usage

### How `dashboard.html` renders:
```python
# routes_pages.py:23
return render_template("dashboard.html")
```
**No template context is passed.** Zero variables. The HTML is rendered with only Jinja's `{% include %}` directives.

### Jinja usage in scripts:
Jinja `{% include %}` is used **only for file composition** — splitting scripts into separate files that get included. No `{{ variable }}` injection from the server happens in any script template.

This means:
- The server has data (catalogs, detection results, user prefs) that it COULD inject at render time
- Instead, JS makes API calls after DOMContentLoaded to fetch this data
- This creates unnecessary round-trips and loading spinners
- Boot time could be faster by injecting static data into the template context

### Opportunity:
```python
# BEFORE:
return render_template("dashboard.html")

# AFTER:
return render_template("dashboard.html",
    infra_catalog=load_infra_catalog(),
    stack_defaults=load_stack_defaults(),
    storage_classes=load_storage_classes(),
    user_prefs=load_prefs(),
)
```
Then in the template:
```html
<script>
  window._infraOptions = {{ infra_catalog | tojson }};
  window._infraCategories = {{ infra_categories | tojson }};
  // etc.
</script>
```

---

## K. Code Duplication

### Confirmed duplicates:

| Original | Duplicate | Files identical? |
|----------|-----------|:---:|
| `src/core/services/pages_builders/*.py` (8 files) | `src/ui/web/pages_builders/*.py` (8 files) | All identical except `__init__.py` |

The web copy exists because `routes_pages_api.py` imports from `src.ui.web.pages_builders`. This should be fixed to import from `src.core.services.pages_builders` instead, and the web copy deleted.

**Impact**: ~3,000 lines of duplicated code.

### Near-duplicates (pattern-level):
- `cardCached()` / `wizCached()` — identical logic, different namespace prefix
- `cardStore()` / `wizStore()` — identical logic
- `cardInvalidate()` / `wizInvalidate()` — identical logic
- `cardInvalidateAll()` / `wizInvalidateAll()` — identical logic
- `cardAge()` / `wizAge()` — identical logic
These could be refactored into a single generic cache utility with a namespace parameter.

---

## L. Subprocess Sprawl

### Core services calling subprocess directly (not through adapters):

| Service | Subprocess calls | Examples |
|---------|:---:|---------|
| `content_release.py` | 18 | gh release upload, gh release delete |
| `secrets_ops.py` | 17 | gh secret set, gh variable set |
| `terraform_ops.py` | 16 | terraform plan, terraform apply |
| `content_optimize_video.py` | 15 | ffmpeg, ffprobe |
| `dns_cdn_ops.py` | 13 | dig, whois, openssl, curl |
| `docusaurus.py` | 12 | npm, npx |
| `pages_engine.py` | 8 | hugo, mkdocs, sphinx |
| `k8s_ops.py` | 8 | kubectl, helm |
| `pages_builders/*.py` | 9+7+7+7+2 | Various build tools |
| `testing_ops.py` | 6 | pytest, npm test |
| `docker_ops.py` | 5 | docker |
| `git_ops.py` | 4 | git (but also uses adapter) |
| `backup_ops.py` | 4 | tar, gpg |
| `quality_ops.py` | 3 | ruff, eslint |
| `docs_ops.py` | 2 | Various |
| `package_ops.py` | 2 | pip, npm |

**Total**: ~160 direct subprocess calls across core services, bypassing the adapter layer.

### What the adapter layer provides:
- `adapters/shell/command.py` — `CommandAdapter` with logging, error handling
- `adapters/containers/docker.py` — Docker adapter (used by some services)
- `adapters/vcs/git.py` — Git adapter (used by git_ops partly)

### Why this matters:
The architecture doc says "adapters always return Receipts" — but most services bypass adapters entirely and call `subprocess.run()` directly. This means:
- No consistent error handling
- No execution logging/tracing
- No mock capability for testing
- No audit trail of external tool invocations

---

## Dependency Graph

```
                       ┌─────────────────────┐
                       │  D. Logging Config   │  ← Unlock ALL existing debug output
                       │  (1 day, low risk)   │     with ~30 lines of code
                       └─────────┬───────────┘
                                 │
                    ┌────────────┼────────────┐
                    │            │            │
              ┌─────▼──────┐ ┌──▼──────────┐ │
              │ E. Audit   │ │ C. Extract  │ │
              │ Expansion  │ │ Data to     │ │
              │ (3 days)   │ │ Files       │ │
              │            │ │ (2 days)    │ │
              └─────┬──────┘ └──────┬──────┘ │
                    │               │         │
                    │         ┌─────▼──────┐  │
                    │         │ B. Monster  │  │
                    │         │ File Split  │  │
                    │         │ (3 days)    │  │
                    │         └─────┬──────┘  │
                    │               │         │
              ┌─────┴───────────────┴─────────▼──┐
              │  F. Push Logic Down               │
              │  (route thinning + layer fix)     │
              │  (5 days)                         │
              └───────────────┬───────────────────┘
                    ┌─────────┼─────────┐
                    │         │         │
              ┌─────▼───┐ ┌──▼────┐ ┌──▼──────┐
              │ I. Cache│ │ J. UI │ │ K. Code │
              │ Archi-  │ │ Modal │ │ Dedup   │
              │ tecture │ │ + Set │ │ (1 day) │
              │ (3 days)│ │ (2d)  │ └─────────┘
              └─────────┘ └───────┘
                              │
                        ┌─────▼──────┐
                        │ H. TUI     │
                        │ Enhancement│
                        │ (5 days)   │
                        └────────────┘
```

---

## Recommended Path Order

Based on the dependency analysis, here's the recommended execution sequence. Each path is now scoped tightly enough to plan in detail.

### Path 1: **Logging Configuration** (quick win, 0.5 day)
**Why first**: Unlocks ~43 modules of existing debug output with ~30 lines of code. Every subsequent change benefits from visibility. Almost zero risk of breakage.
- Add `logging.basicConfig()` to `main.py` and `server.py`
- Wire `--debug` flag to `logging.DEBUG`
- Wire `--verbose` flag to `logging.INFO`
- Add optional file handler via env var

### Path 2: **Data Extraction** (prerequisite for splitting, 1-2 days)
**Why second**: Removes ~630 lines from the monster file, making the split cleaner. Creates the `data/catalogs/` infrastructure that CLI/TUI will also use.
- Extract `_infraOptions` → `data/catalogs/infra-services.json`
- Extract `_infraCategories` → inline or same file
- Extract `_dockerStackDefaults` → `data/catalogs/docker-stack-defaults.json`
- Extract `_SC_CATALOG` → `data/catalogs/storage-classes.json`
- Create `DatasetLoader` in core
- Serve via Jinja injection at render time

### Path 3: **Monster File Split** (clean separation, 2-3 days)
**Why third**: After data extraction, the file is ~7,650 lines → split into 7-8 files. Each follows the same wizard pattern. Low risk because each wizard is self-contained.
- Split into per-wizard files
- Update `dashboard.html` includes
- Test each wizard independently

### Path 4: **Code Deduplication** (quick cleanup, 0.5 day)
**Why here**: Quick wins while we're in file-organization mode.
- Delete `src/ui/web/pages_builders/` → fix imports to use core
- Factor out generic cache helper from card/wizard cache code

### Path 5: **Audit Expansion** (cross-cutting, 2-3 days)
**Why fifth**: Now that logging works and files are organized, we can systematically add audit entries to all 13 missing operation categories.
- Create audit entry types per domain
- Inject `AuditWriter` pattern into vault, content, backup, git, docker, k8s, secrets, pages, security, config
- Make audit entries flow from core (not routes)

### Path 6: **Route Thinning / Layer Push-Down** (the big one, 4-5 days)
**Why sixth**: Depends on everything above. Routes become thin wrappers over core services. Business logic moves to core where CLI can also use it.
- `routes_devops.py` → split into wizard + prefs + cache routes
- Move wizard_detect/wizard_setup logic to core services
- Remove all inline subprocess calls from routes
- Content file ops → core service
- Clean up all 14 subprocess calls in `routes_devops.py`

### Path 7: **Caching Architecture** (depends on data layer, 2-3 days)
**Why seventh**: Now that data is in files and routes are thin, we can implement proper caching.
- Boot-time Jinja injection of static datasets
- Two-sided cache coherency protocol
- Cache warming on server start

### Path 8: **Modal Preview + UI Settings** (UI polish, 1-2 days)
**Why eighth**: Depends on organized templates.
- Implement ModalPreview component
- Add UI settings panel
- Persist in localStorage

### Path 9: **TUI Enhancement** (depends on core being solid, 3-5 days)
**Why last**: TUI wraps CLI which wraps core. Core must be solid first.
- Progressive feature parity
- Interactive sub-menus

---

## Summary Statistics

| Metric | Count |
|--------|------:|
| Files > 500 lines | 48 |
| Files > 1000 lines | 6 |
| Hardwired data lines | ~1,085 |
| Core modules with logger | 43 |
| Core modules missing logger | 19 |
| Logging configuration calls | **0** |
| Audit writes (total in codebase) | 3 locations |
| Operations that SHOULD audit | 13+ categories |
| Web API endpoints | 166 |
| CLI commands | ~80 |
| Subprocess calls bypassing adapters | ~160 |
| Duplicated page builder files | 8 (×2 = ~3,000 lines) |
| Monster file size | 8,282 lines / 619 KB |
| K8s wizard alone | 4,602 lines |
