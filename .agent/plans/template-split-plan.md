# Template Split & Cleanup Plan

> **Target**: No template file over 500 lines (700 max for justified exceptions)
> **Date**: 2026-02-12
> **Status**: Planning
> **Predecessor**: `.agent/artifacts/refactoring-plan.md` (Files 1–6 done Feb 11)

---

## Current State

### Previous work (Feb 11 — already done)

The original refactoring-plan.md covered Python + templates. Files 1–6 are complete:
- ✅ `_content.html` (4,011 → 12 files via loader pattern)
- ✅ `_secrets.html` (1,347 → 7 files via loader pattern)
- ✅ `routes_backup.py`, `routes_content.py`, `content_optimize.py`, `vault.py`

### What's left: Template files over 500 lines

| # | File | Lines | Ratio | Domain | Existing Split? |
|---|------|------:|------:|--------|----------------|
| 1 | `_integrations.html` | **4,358** | 8.7× | JS: Integrations tab | ❌ Monolith |
| 2 | `_devops.html` | **2,303** | 4.6× | JS: DevOps tab | ❌ Monolith |
| 3 | `_wizard.html` | **2,116** | 4.2× | JS: Setup Wizard | ❌ Monolith |
| 4 | `_audit.html` | **1,382** | 2.8× | JS: Audit tab | ❌ Monolith |
| 5 | `_secrets_keys.html` | **693** | 1.4× | JS: Secrets key mgmt | Already split child |
| 6 | `_content_browser.html` | **687** | 1.4× | JS: Content browser | Already split child |
| 7 | `_content_archive.html` | **624** | 1.2× | JS: Content archive | Already split child |
| 8 | `_content_upload.html` | **591** | 1.2× | JS: Content upload | Already split child |
| 9 | `_content_archive_modals.html` | **563** | 1.1× | JS: Archive modals | Already split child |
| 10 | `_secrets_render.html` | **533** | 1.1× | JS: Secrets rendering | Already split child |
| 11 | `_secrets_init.html` | **514** | 1.0× | JS: Secrets init | Already split child |
| 12 | `_content_preview_enc.html` | **514** | 1.0× | JS: Encrypted preview | Already split child |

### What's left: Python files over 500 lines

| # | File | Lines | Notes |
|---|------|------:|-------|
| 1 | `k8s_ops.py` | 1,447 | Service layer |
| 2 | `backup_ops.py` | 1,179 | Service layer |
| 3 | `security_ops.py` | 994 | Service layer |
| 4 | `docker_ops.py` | 892 | Service layer |
| 5 | `terraform_ops.py` | 880 | Service layer |
| 6 | `routes_pages_api.py` | 879 | Route handler |
| 7 | `docusaurus.py` × 2 | 865 | Duplicated! |
| 8 | `secrets_ops.py` | 830 | Service layer |
| 9 | `vault_env_ops.py` | 815 | Service layer |
| 10 | `content_crypto.py` | 767 | Already flagged |
| 11 | `testing_ops.py` | 750 | Service layer |
| 12 | `routes_devops.py` | 736 | Route handler |
| 13+ | 7 more files | 652–690 | Service layer |

**Total: ~24 files over 500 lines** (12 templates + 12+ Python).

---

## Template Architecture: Current vs Target

### Current Architecture

```
templates/
├── dashboard.html                 # Master layout — includes everything
├── partials/                      # HTML structure (one per tab)
│   ├── _head.html
│   ├── _nav.html
│   ├── _tab_dashboard.html
│   ├── _tab_wizard.html
│   ├── _tab_secrets.html
│   ├── _tab_commands.html
│   ├── _tab_content.html          # Includes _content_modals.html
│   ├── _tab_integrations.html
│   ├── _tab_devops.html
│   ├── _tab_audit.html
│   ├── _tab_debugging.html
│   └── _content_modals.html       # Extracted modals
└── scripts/                       # JS logic (FLAT — 32 files, mixed concerns)
    ├── _globals.html               #   Shared helpers
    ├── _theme.html                 #   Theme toggle
    ├── _tabs.html                  #   Tab switching
    ├── _boot.html                  #   Init
    ├── _lang.html                  #   i18n
    ├── _monaco.html                #   Monaco editor
    ├── _dashboard.html             #   Dashboard tab
    ├── _commands.html              #   Commands tab
    ├── _setup_wizard.html          #   Setup wizard
    ├── _debugging.html             #   Debugging tab
    ├── _content.html               #   Content LOADER (10 includes) ✅
    ├── _content_*.html (×10)       #   Content split children ✅
    ├── _secrets.html               #   Secrets LOADER (6 includes) ✅
    ├── _secrets_*.html (×6)        #   Secrets split children ✅
    ├── _wizard.html                #   ❌ MONOLITH (2,116 lines)
    ├── _integrations.html          #   ❌ MONOLITH (4,358 lines)
    ├── _devops.html                #   ❌ MONOLITH (2,303 lines)
    └── _audit.html                 #   ❌ MONOLITH (1,382 lines)
```

### Target Architecture

```
templates/
├── dashboard.html
├── partials/
│   └── (unchanged — 12 files, all under 200 lines)
└── scripts/
    ├── _globals.html              # Shared (457 lines — OK)
    ├── _theme.html                # (43 lines)
    ├── _tabs.html                 # (110 lines)
    ├── _boot.html                 # (15 lines)
    ├── _lang.html                 # (79 lines)
    ├── _monaco.html               # (310 lines)
    ├── _dashboard.html            # (270 lines — OK)
    ├── _commands.html             # (246 lines — OK)
    ├── _setup_wizard.html         # (328 lines — OK)
    ├── _debugging.html            # (472 lines — OK)
    │
    ├── _content.html              # LOADER ✅
    ├── _content_*.html (×10)      # Already split ✅ (some children need re-split)
    │
    ├── _secrets.html              # LOADER ✅
    ├── _secrets_*.html (×6)       # Already split ✅ (some children need re-split)
    │
    ├── _integrations.html         # → LOADER (new) — includes ~8 children
    ├── _integrations_init.html    # State, prefs, tab load
    ├── _integrations_github.html  # GitHub card + modals
    ├── _integrations_cicd.html    # CI/CD card + modals
    ├── _integrations_docker.html  # Docker card + live panels + modals
    ├── _integrations_k8s.html     # K8s card + live panels + modals
    ├── _integrations_terraform.html # Terraform card + actions + modals
    ├── _integrations_pages.html   # Pages card + builder config + SSE
    ├── _integrations_helpers.html # CI workflow gen, shared helpers
    │
    ├── _devops.html               # → LOADER (new) — includes ~8 children
    ├── _devops_init.html          # State, prefs, card cache, tab load
    ├── _devops_security.html      # Security card + live panels
    ├── _devops_testing.html       # Testing card + modals
    ├── _devops_docs.html          # Documentation card + live panels + modals
    ├── _devops_k8s.html           # K8s card + modals
    ├── _devops_terraform.html     # Terraform card + modals
    ├── _devops_dns.html           # DNS & CDN card + modals
    ├── _devops_quality.html       # Quality card + modals
    ├── _devops_packages.html      # Packages card + modals
    ├── _devops_env.html           # Environment & IaC card + live panels
    │
    ├── _wizard.html               # → LOADER (new) — includes ~4 children
    ├── _wizard_init.html          # Config load, state, render entry
    ├── _wizard_steps.html         # Step renderers (all 6 steps)
    ├── _wizard_helpers.html       # Module/domain/env/content helpers
    ├── _wizard_actions.html       # Form state, save, activate, navigation
    │
    ├── _audit.html                # → LOADER (new) — includes ~4 children
    ├── _audit_init.html           # Shared data, helpers, file links
    ├── _audit_scores.html         # Master scores rendering
    ├── _audit_cards.html          # All 7 analysis cards
    └── _audit_modals.html         # Drill-down modals, batch dismiss, filters
```

---

## Detailed Split Plans

### 1. `_integrations.html` (4,358 → ~8 files) — HIGHEST PRIORITY

This is the largest file. Natural section boundaries are already marked.

| New File | Lines (est) | Source Lines | Content |
|----------|------:|-----------|---------|
| `_integrations.html` | ~30 | — | **Loader**: `<script>` + 8× `{% include %}` |
| `_integrations_init.html` | ~375 | 1–375 | State vars, prefs, tab load, card metadata, `loadIntegrationsTab()`, `loadGitCard()` |
| `_integrations_github.html` | ~280 | 376–655 | GitHub card, live tabs, create env modal, push secrets |
| `_integrations_cicd.html` | ~230 | 655–870 | CI/CD card, live tabs, generate modal |
| `_integrations_docker.html` | ~490 | 928–1412 | Docker card, live tabs, logs, inspect, pull, exec, remove, generate modals |
| `_integrations_docker_compose.html` | ~460 | 1412–1868 | Compose wizard helpers + operational actions (big but cohesive) |
| `_integrations_k8s.html` | ~700 | 1869–2584 | K8s card, live panels, all modals (pod logs, apply, scale, describe, delete, generate, helm, wizard). **Exception: 700 lines** — K8s has many modals but they're tightly coupled. |
| `_integrations_terraform.html` | ~290 | 2585–2871 | Terraform card, live panels, workspace switch, generate modal |
| `_integrations_pages.html` | ~500 | 2872–3900 | Pages card, pipeline stages, builder config, feature toggles, custom CSS |
| `_integrations_pages_sse.html` | ~460 | 3902–4358 | SSE build streaming, batched log rendering, CI workflow gen, helpers |

### 2. `_devops.html` (2,303 → ~10 files) — HIGH PRIORITY

**Note**: This file currently has syntax errors from the earlier modal refactoring (4 missing close braces were patched but the old code remnants may still be present). The split will also serve as a **cleanup** — each child gets written clean.

| New File | Lines (est) | Source Lines | Content |
|----------|------:|-----------|---------|
| `_devops.html` | ~35 | — | **Loader**: `<script>` + 10× `{% include %}` |
| `_devops_init.html` | ~90 | 1–93 | State, prefs, card metadata, `loadDevopsTab()`, prefs modal |
| `_devops_security.html` | ~280 | 146–427 | Security card + live panels |
| `_devops_testing.html` | ~280 | 427–700 | Testing card + test gen modal |
| `_devops_docs.html` | ~190 | 700–886 | Documentation card + live panels |
| `_devops_k8s.html` | ~260 | 886–1145 | K8s card + validate/cluster/resources/generate modals |
| `_devops_terraform.html` | ~245 | 1145–1387 | Terraform card + validate/plan/state/workspaces/generate modals |
| `_devops_dns.html` | ~200 | 1387–1586 | DNS card + lookup/ssl/generate modals |
| `_devops_quality.html` | ~200 | 1586–1784 | Quality card + run/gen modals |
| `_devops_packages.html` | ~160 | 1784–1940 | Packages card + outdated/audit/list modals |
| `_devops_env.html` | ~360 | 1940–2303 | Environment card + drift modal + live panels + generate |

### 3. `_wizard.html` (2,116 → ~4 files)

| New File | Lines (est) | Source Lines | Content |
|----------|------:|-----------|---------|
| `_wizard.html` | ~25 | — | **Loader** |
| `_wizard_init.html` | ~165 | 1–165 | Config load, state vars, render entry point |
| `_wizard_steps.html` | ~640 | 166–800 | All 6 step renderers. **Exception: ~640** — one function `renderStep()` with a large switch. Could be split further (per-step) but the coupling is tight. |
| `_wizard_helpers.html` | ~500 | 800–1300 | Module helpers, domain helpers, environment helpers, content folder helpers, enc key helpers |
| `_wizard_actions.html` | ~500 | 1300–2116 | Form state, navigation, save/activate, advanced actions, review step logic |

### 4. `_audit.html` (1,382 → ~4 files)

| New File | Lines (est) | Source Lines | Content |
|----------|------:|-----------|---------|
| `_audit.html` | ~25 | — | **Loader** |
| `_audit_init.html` | ~100 | 1–99 | Shared data store, helpers, file links |
| `_audit_scores.html` | ~175 | 99–271 | Master score rendering |
| `_audit_cards.html` | ~500 | 271–1008 | 7 analysis cards (System Profile, Dependencies, Structure, Clients, Code Health, Repo Health, Risks). **Borderline** — could split into `_audit_cards_a.html` + `_audit_cards_b.html` if needed. |
| `_audit_modals.html` | ~380 | 1008–1382 | Drill-down modals, batch dismiss, checkbox helpers, category filters |

### 5. Already-split children over 500 (re-split if needed)

These are already extracted from the Content/Secrets splits but still exceed 500:

| File | Lines | Action |
|------|------:|--------|
| `_secrets_keys.html` | 693 | Split: key management (~350) + modals (~350) |
| `_content_browser.html` | 687 | Split: search/filtering (~350) + gallery/list rendering (~340) |
| `_content_archive.html` | 624 | Split: panel render (~350) + tree interactions (~280) |
| `_content_upload.html` | 591 | Split: upload logic (~300) + helpers/formatting (~290) |
| `_content_archive_modals.html` | 563 | Borderline — 6 modals, each ~90 lines. Could leave as exception. |
| `_secrets_render.html` | 533 | Borderline — state machine + form builder. Could leave as exception. |
| `_secrets_init.html` | 514 | Borderline — leave as exception. |
| `_content_preview_enc.html` | 514 | Borderline — leave as exception. |

**Recommendation**: Split 5-8 (files 500-570) can stay as justified exceptions since they're already well-focused. Priority is files 1-4 which are the true monoliths.

---

## Documentation Updates Needed

### 1. `docs/WEB_ADMIN.md` — Template Architecture section is stale

The current tree listing shows the pre-split structure. It needs:
- Updated tree showing all current files
- The loader pattern explained (`_content.html`, `_secrets.html`, and the new ones)
- File-per-card/domain naming convention documented
- The 500/700 line rule stated

### 2. Missing: `docs/DEVOPS.md`

The DevOps tab has no dedicated doc. Needs:
- Card inventory (Security, Testing, Docs, K8s, Terraform, DNS, Quality, Packages, Env)
- Card preference system (auto/manual/hidden)
- API endpoints per card
- Template file mapping

### 3. Missing: `docs/INTEGRATIONS.md`

The Integrations tab is referenced in `WEB_ADMIN.md` as a one-liner. Needs:
- Card inventory (Git, GitHub, CI/CD, Docker, K8s, Terraform, Pages)
- Builder system overview (or link to PAGES.md)
- SSE streaming architecture
- Compose wizard documentation

### 4. `docs/AUDIT_ARCHITECTURE.md` — may need update

Check if it still matches the current card structure and drill-down modals.

### 5. `.agent/artifacts/refactoring-plan.md` — needs update

Add this new template split work as Files 10–13. Mark the original plan entries as complete.

---

## Execution Order

| Phase | Files | Estimated Children | Priority |
|-------|-------|-------------------:|----------|
| **Phase 1** | `_integrations.html` | ~10 files | 🔴 Critical (4,358 lines) |
| **Phase 2** | `_devops.html` | ~10 files | 🔴 Critical (2,303 lines + broken) |
| **Phase 3** | `_wizard.html` | ~4 files | 🟡 High (2,116 lines) |
| **Phase 4** | `_audit.html` | ~4 files | 🟡 High (1,382 lines) |
| **Phase 5** | Content/Secrets re-splits | ~4 files | 🟢 Low (all under 700) |
| **Phase 6** | Documentation updates | ~4 doc files | 🟢 Low |

### Per-phase process

1. **Outline** the file's sections with `grep -n '// ── '`
2. **Extract** each section into its own file with header docstring
3. **Create** the loader file with `{% include %}` directives
4. **Update** `dashboard.html` if needed (shouldn't be — loader keeps same filename)
5. **Verify** the split is correct (concatenation test or server test)
6. **Update** docs

---

## Python Files (deferred — separate plan)

There are 12+ Python files over 500 lines (some over 1,000). These need their own analysis since the splitting pattern is different (imports, blueprints, service classes). The original refactoring-plan.md covers some but not the service layer files (`k8s_ops.py`, `docker_ops.py`, etc.).

**Recommendation**: Create a separate `python-split-plan.md` after templates are done.

---

## Open Questions

1. **Devops file cleanup**: The `_devops.html` currently has remnants from the botched modal refactoring. Should I fix the syntax errors first, or just do a clean split (each child written fresh from understanding the intended code)?
2. **Naming convention**: Content uses `_content_browser.html`, Secrets uses `_secrets_keys.html`. Should integrations follow `_integrations_docker.html` or something shorter?
3. **Compose wizard**: The Docker compose wizard (~400 lines) is a cohesive unit. Keep it with `_integrations_docker.html` (making it ~900 lines) or separate as `_integrations_docker_compose.html`?
