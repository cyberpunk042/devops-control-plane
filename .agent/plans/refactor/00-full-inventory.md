# Full Codebase Inventory — The Mountain Map

> Created: 2026-02-28
> Purpose: See EVERYTHING before cutting anything.
> Rule: <500 lines per file, ~700 exception max. SRP. Onion folders.

---

## Total Size

| Layer | Files | Lines | Status |
|---|---|---|---|
| **core/services/** (flat) | 88 `.py` | 78,465 | ❌ Flat bag, no domain folders |
| **core/services/audit/** | 11 `.py` | ~4,600 | ✅ Already grouped |
| **core/services/chat/** | 5 `.py` | ~2,800 | ✅ Already grouped |
| **core/services/generators/** | 5 `.py` | ~1,600 | ✅ Already grouped |
| **core/services/ledger/** | 4 `.py` | ~1,200 | ✅ Already grouped |
| **core/services/trace/** | 3 `.py` | ~950 | ✅ Already grouped |
| **core/services/pages_builders/** | 10 `.py` | ~3,300 | ✅ Already grouped |
| **core/services/tool_install/** | 59 children | ~18,000+ | ✅ Already grouped + own README |
| **core/models/** | 7 `.py` | ~500 | ✅ Clean |
| **core/config/** | 3 `.py` | ~350 | ✅ Clean |
| **core/engine/** | 2 `.py` | ~250 | ✅ Clean |
| **core/use_cases/** | 5 `.py` | ~650 | ✅ Clean |
| **core/observability/** | 4 `.py` | ~500 | ✅ Clean |
| **core/persistence/** | 3 `.py` | ~250 | ✅ Clean |
| **core/reliability/** | 3 `.py` | ~400 | ✅ Clean |
| **core/security/** | 1 `.py` | ~50 | ✅ Clean (stub) |
| **core/data/** | 19 JSON catalogs + 2 JSON | ~varies | ✅ Data files, OK |
| **core/context.py** | 1 | 40 | ✅ Clean |
| **adapters/** | 10 `.py` | ~1,500 | ✅ Clean, grouped |
| **ui/cli/** | 20 `.py` | 5,489 | ✅ Clean, all <500 |
| **ui/web/routes_*.py** (flat) | 33 `.py` | 8,759 | ⚠️ Flat, mostly OK size |
| **ui/web/server.py** | 1 | ~280 | ✅ Clean |
| **ui/web/templates/scripts/** (flat) | 92 `.html` | 46,276 | ❌ Flat bag, many >700 |
| **ui/web/templates/partials/** | 12 `.html` | ~2,800 | ✅ Clean |
| **ui/web/static/css/admin.css** | 1 | 5,948 | ⚠️ Large CSS, may need split |
| **main.py** | 1 | 489 | ✅ Clean |
| **manage.sh** | 1 | 166 | ✅ Clean |
| **stacks/** | 47 dirs, 1 yml each | ~1,666 | ✅ Clean, data |
| **tests/** | 42 `.py` + integration/ | 42,464 | ⚠️ Some huge test files |
| **.agent/** | 141 children | 60,900 | ℹ️ Plans/rules/workflows |
| **docs/** | 20 `.md` + 113 other | varies | ⚠️ Stale per ARCHITECTURE.md |
| **TOTAL** | ~450+ source files | **~146K lines** | |

---

## 1. BACKEND: `src/core/services/` — The Worst Offender

### Currently: 88 Python files in a FLAT directory

All business logic lives in one directory with no domain grouping.
Services that belong together are scattered alphabetically.

### Files > 700 Lines (HARD VIOLATIONS)

| File | Lines | What It Does | Problem |
|---|---|---|---|
| `k8s_validate.py` | **4,004** | K8s manifest validation | Monster. Multiple rule domains mixed |
| `wizard_setup.py` | **1,568** | Setup handlers for ALL integrations | God function. One file handles Git, GitHub, Docker, K8s, CI, DNS, Terraform, Pages |
| `k8s_wizard_generate.py` | **1,012** | K8s wizard YAML generation | Config + template + generation mixed |
| `git_gh_ops.py` | **951** | Git AND GitHub operations | Two domains in one file |
| `dev_scenarios.py` | **902** | Dev/demo scenarios | Not prod code, still oversized |
| `devops_activity.py` | **864** | Activity feed + scoring | Two concerns |
| `docker_containers.py` | **733** | Docker container management | Borderline |
| `devops_cache.py` | **700** | DevOps cache system | Borderline |
| `content_optimize_video.py` | **677** | Video optimization | Borderline (exception OK?) |
| `terraform_generate.py` | **657** | Terraform file generation | Borderline |
| `content_file_ops.py` | **651** | Content file operations | Borderline |
| `k8s_detect.py` | **641** | K8s detection | Borderline |
| `vault.py` | **630** | Vault core | Borderline |
| `ci_ops.py` | **592** | CI operations | OK |
| `docker_detect.py` | **584** | Docker detection | OK |
| `k8s_wizard.py` | **565** | K8s wizard | OK |
| `dns_cdn_ops.py` | **564** | DNS/CDN operations | OK |

### Already-Grouped Sub-Domains (GOOD — pattern to replicate)

| Sub-Domain | Dir | Files | Lines | Status |
|---|---|---|---|---|
| `audit/` | ✅ | 11 | ~4,600 | Has own models, layered (L0/L1/L2) |
| `chat/` | ✅ | 5 | ~2,800 | Has own models, crypto |
| `generators/` | ✅ | 5 | ~1,600 | compose, dockerfile, dockerignore, github_workflow |
| `ledger/` | ✅ | 4 | ~1,200 | Has own models |
| `trace/` | ✅ | 3 | ~950 | Has own models |
| `pages_builders/` | ✅ | 10 | ~3,300 | Has base ABC + plugins |
| `tool_install/` | ✅ | 59 | ~18K+ | Full onion: data/detection/domain/execution/orchestration/resolver |

### Flat Files That Need Domain Grouping

| Domain | Current Files | Combined Lines |
|---|---|---|
| **docker** | `docker_common.py`, `docker_containers.py`, `docker_detect.py`, `docker_generate.py`, `docker_k8s_bridge.py`, `docker_ops.py` | ~2,600 |
| **k8s** | `k8s_cluster.py`, `k8s_common.py`, `k8s_detect.py`, `k8s_generate.py`, `k8s_helm.py`, `k8s_helm_generate.py`, `k8s_ops.py`, `k8s_pod_builder.py`, `k8s_validate.py`, `k8s_wizard.py`, `k8s_wizard_detect.py`, `k8s_wizard_generate.py` | ~10,500 |
| **vault/secrets** | `vault.py`, `vault_io.py`, `vault_env_crud.py`, `vault_env_ops.py`, `secrets_env_ops.py`, `secrets_gh_ops.py`, `secrets_ops.py` | ~3,700 |
| **content** | `content_crypto.py`, `content_crypto_ops.py`, `content_file_advanced.py`, `content_file_ops.py`, `content_listing.py`, `content_optimize.py`, `content_optimize_video.py`, `content_release.py`, `content_release_sync.py` | ~4,800 |
| **git** | `git_auth.py`, `git_gh_ops.py`, `git_ops.py` | ~2,000 |
| **ci** | `ci_compose.py`, `ci_ops.py` | ~1,200 |
| **terraform** | `terraform_actions.py`, `terraform_generate.py`, `terraform_ops.py` | ~1,600 |
| **wizard** | `wizard_ops.py`, `wizard_setup.py`, `wizard_validate.py` | ~2,600 |
| **backup** | `backup_archive.py`, `backup_common.py`, `backup_extras.py`, `backup_ops.py`, `backup_restore.py` | ~2,100 |
| **devops** | `devops_activity.py`, `devops_cache.py`, `env_infra_ops.py`, `env_ops.py` | ~2,600 |
| **security** | `security_common.py`, `security_ops.py`, `security_posture.py`, `security_scan.py` | ~1,300 |
| **pages** | `pages_build_stream.py`, `pages_ci.py`, `pages_discovery.py`, `pages_engine.py`, `pages_install.py`, `pages_preview.py` | ~1,700 |
| **quality** | `quality_ops.py` | 500 |
| **testing** | `testing_ops.py`, `testing_run.py` | ~900 |
| **dns** | `dns_cdn_ops.py` | 564 |
| **docs** | `docs_generate.py`, `docs_ops.py` | ~730 |
| **metrics** | `metrics_ops.py` | 570 |
| **shared** | `detection.py`, `identity.py`, `event_bus.py`, `project_probes.py`, `staleness_watcher.py`, `run_tracker.py`, `md_transforms.py`, `config_ops.py`, `terminal_ops.py`, `dev_overrides.py` | ~3,000 |

---

## 2. ROUTES: `src/ui/web/routes_*.py`

### Currently: 33 Python files, flat in `ui/web/`

| File | Lines | Status |
|---|---|---|
| `routes_audit.py` | **1,781** | ❌ WAY over, needs split |
| `routes_integrations.py` | 600 | ⚠️ Borderline |
| `routes_docker.py` | 470 | OK |
| `routes_k8s.py` | 390 | OK |
| `routes_chat.py` | 370 | OK |
| `routes_vault.py` | 360 | OK |
| `routes_pages_api.py` | 380 | OK |
| `routes_content.py` | 290 | OK |
| `routes_secrets.py` | 220 | OK |
| All others | <200 each | ✅ OK |

### Structure Issue
Routes are flat in `ui/web/` mixed with `server.py`, `helpers.py`, and shim files.
Not terrible but could be `ui/web/routes/` as a package.

---

## 3. FRONTEND: `src/ui/web/templates/scripts/`

### Currently: 92 HTML files in a flat directory (+ 2 sub-dirs)

### Files > 700 Lines (HARD VIOLATIONS)

| File | Lines | What It Does | Problem |
|---|---|---|---|
| `_globals.html` | **3,606** | EVERYTHING: api, modal, toast, cards, install UI, ops modal, refresh, auth, tools, wizard framework | God file. 15+ concerns |
| `_wizard_integrations.html` | **2,051** | ALL integration rendering | One file for k8s, docker, git, github, cicd, terraform, dns |
| `_assistant_resolvers_docker.html` | **1,256** | Docker assistant resolvers | Many resolvers in one |
| `_integrations_setup_cicd.html` | **1,231** | CI/CD setup wizard | Complex wizard, multiple steps |
| `_content_chat.html` | **1,159** | Chat feature | Chat + UI + sync mixed |
| `_debugging.html` | **1,145** | Debug panel | Multiple debug tools |
| `_assistant_engine.html` | **1,117** | Assistant matching engine | Engine + rendering mixed |
| `_wizard_integration_actions.html` | **958** | Wizard action buttons | All integrations in one |
| `_content_chat_refs.html` | **955** | Chat references | |
| `_integrations_k8s.html` | **806** | K8s integration card | |
| `_integrations_setup_github.html` | **760** | GitHub setup wizard | |
| `_wizard_steps.html` | **727** | Wizard step rendering | |
| `_integrations_setup_terraform.html` | **707** | Terraform setup wizard | |
| `_stage_debugger.html` | **702** | Stage debugger tool | |
| docker_wizard/_raw_step2_configure.html | **1,017** | Docker wizard config step | |
| k8s_wizard/_raw_step2_cluster.html | **872** | K8s wizard cluster step | |
| k8s_wizard/_raw_step2_app_services.html | **735** | K8s wizard services step | |
| k8s_wizard/_raw_step2_collectors.html | **688** | K8s wizard collectors | Borderline |

### Already-Grouped (GOOD — pattern to replicate)

| Domain | Dir | Files |
|---|---|---|
| `docker_wizard/` | ✅ | 3 files |
| `k8s_wizard/` | ✅ | 9 files |

### Flat Files That Need Domain Grouping

Same domains as backend: integrations, content, secrets, audit, devops, wizard, assistant.

---

## 4. CLI: `src/ui/cli/`

| File | Lines | Status |
|---|---|---|
| `docker.py` | 431 | ✅ OK |
| All others | <370 each | ✅ ALL OK |

**CLI layer is clean.** 20 files, all under 500 lines, domain-per-file. No action needed.

---

## 5. ADAPTERS: `src/adapters/`

| File | Lines | Status |
|---|---|---|
| All files | <300 each | ✅ ALL OK |

**Adapter layer is clean.** Already onion-grouped (containers/, languages/, shell/, vcs/). No action needed.

---

## 6. CORE INFRASTRUCTURE: models, config, engine, use_cases, observability, persistence, reliability, security

| Package | Files | Lines | Status |
|---|---|---|---|
| `core/models/` | 7 | ~500 | ✅ Clean |
| `core/config/` | 3 | ~350 | ✅ Clean |
| `core/engine/` | 2 | ~250 | ✅ Clean |
| `core/use_cases/` | 5 | ~650 | ✅ Clean |
| `core/observability/` | 4 | ~500 | ✅ Clean |
| `core/persistence/` | 3 | ~250 | ✅ Clean |
| `core/reliability/` | 3 | ~400 | ✅ Clean |
| `core/security/` | 1 | ~50 | ✅ Clean (stub) |
| `core/data/` | 22 JSON | data | ✅ Clean |
| `core/context.py` | 1 | 40 | ✅ Clean |

**All clean.** These are the well-structured layers of the onion. No action needed.

---

## 7. TESTS: `tests/`

| File | Lines | Status |
|---|---|---|
| `test_k8s_validate.py` | **8,232** | ⚠️ Huge but test data OK? |
| `test_k8s_wizard_generate.py` | **3,078** | ⚠️ |
| `test_k8s_detect.py` | **1,786** | ⚠️ |
| `test_helm.py` | **1,462** | ⚠️ |
| `test_docker_generators.py` | **1,424** | ⚠️ |
| All others | <1,200 | Acceptable |

Tests are large but this is less critical — test files often contain bulky fixtures.
**Lower priority** — refactor test locations AFTER their source domains move.

---

## 8. CSS: `admin.css`

| File | Lines | Status |
|---|---|---|
| `admin.css` | **5,948** | ⚠️ Single CSS file for entire app |

May benefit from splitting by domain (base, modal, cards, tabs, wizard, content, audit...)
**Lower priority** — CSS doesn't cause AI confusion the way JS/Python does.

---

## 9. OTHER FILES

| Item | Status |
|---|---|
| `main.py` (489 lines) | ✅ Clean |
| `manage.sh` (166 lines) | ✅ Clean |
| `pyproject.toml` | ✅ Clean |
| `Makefile` | ✅ Clean |
| `project.yml` | ✅ Clean |
| `stacks/` (47 stack.yml) | ✅ Clean, data |
| `docs/` (20 .md) | ⚠️ ARCHITECTURE.md is stale |
| `.github/workflows/` | Needs audit after refactor |
| `.agent/` (plans, rules, workflows) | ✅ Meta, not code |
| `dashboard.html` (79 lines) | ✅ Clean (include list) |
| `partials/` (12 files) | ✅ Clean |

---

## Summary: What Needs the Revolution

### RED — Must Refactor (SRP violations, >700 lines, flat structure)

1. **`core/services/` flat bag** — 88 files need domain folders
2. **`_globals.html` god file** — 3,606 lines, 15+ concerns
3. **`_wizard_integrations.html`** — 2,051 lines
4. **`wizard_setup.py`** — 1,568 lines, every integration
5. **`k8s_validate.py`** — 4,004 lines
6. **`routes_audit.py`** — 1,781 lines
7. **`git_gh_ops.py`** — 951 lines, two domains
8. **Frontend scripts/ flat bag** — 92 files need domain folders
9. **15+ frontend files** over 700 lines each

### YELLOW — Should Improve

10. Routes flat in `ui/web/` — move to `routes/` package
11. CSS single file — 5,948 lines
12. Stale `docs/ARCHITECTURE.md`
13. Large test files (follows source refactor)

### GREEN — Already Clean, Don't Touch

14. `core/models/` ✅
15. `core/config/` ✅
16. `core/engine/` ✅
17. `core/use_cases/` ✅
18. `core/observability/` ✅
19. `core/persistence/` ✅
20. `core/reliability/` ✅
21. `core/security/` ✅
22. `core/data/` ✅
23. `adapters/` ✅
24. `ui/cli/` ✅
25. `main.py` ✅
26. `manage.sh` ✅
27. `partials/` ✅
28. `stacks/` ✅
29. Already-grouped: `audit/`, `chat/`, `generators/`, `ledger/`, `trace/`, `pages_builders/`, `tool_install/`, `docker_wizard/`, `k8s_wizard/`
