# Frontend Templates Refactor — scripts/ Directory

> Tracker items #11–#17. Split oversized files. Group related templates
> into sub-folders. Keep the same JS execution model.

---

## Conventions (learned from existing code)

### Template naming

| Prefix | Meaning | `<script>` wrapper? | Example |
|--------|---------|---------------------|---------|
| `_name.html` | Self-contained JS module | ✅ has `<script>…</script>` | `_boot.html`, `_globals.html` |
| `_raw_name.html` | Raw JS fragment | ❌ no wrapper tags | `_raw_step1_detect.html` (inside wizard step array) |

**Rule:** Files included directly by `dashboard.html` via `{% include %}` are
always wrapped modules (`_name.html`). Files included by other scripts (injected
inline into a JS data structure) use the `_raw_` prefix.

### When to use folders

A domain gets a subfolder when it has **3+ related files** that share a
functional boundary. The existing pattern:

```
scripts/
├── docker_wizard/       ← 3 step files for the Docker wizard
│   ├── _raw_step1_detect.html
│   ├── _raw_step2_configure.html
│   └── _raw_step3_preview.html
│
└── k8s_wizard/          ← 9 step files for the K8s wizard
    ├── _raw_step1_detect.html
    ├── _raw_step2_cluster.html
    └── ... 7 more
```

Standalone files that have no siblings stay flat (e.g., `_dashboard.html`,
`_tabs.html`, `_monaco.html`). We don't create a folder for a single file.

### Load order

`dashboard.html` includes scripts in execution order. Utilities load first
(`_settings` → `_globals`) so that all later scripts can call `api()`,
`toast()`, `modalOpen()`, etc. Splitting `_globals.html` into fragments means
all fragments replace the single `{% include 'scripts/_globals.html' %}` line
and load in the same position, maintaining availability for all downstream scripts.

---

## Before-State

```
scripts/
├── _globals.html                    3,606 lines  ← GOD FILE (7 concerns)
├── _globals_wizard_modal.html         404 lines
├── _wizard_integrations.html        2,051 lines  ← 2nd largest
├── _wizard_integration_actions.html   958 lines
├── _wizard_steps.html                 727 lines
├── _wizard_helpers.html               415 lines
├── _wizard_init.html                  200 lines
├── _wizard_nav.html                   151 lines
├── _wizard.html                        24 lines
├── _setup_wizard.html                 333 lines
├── _assistant_engine.html           1,117 lines
├── _assistant_resolvers_docker.html 1,256 lines
├── _assistant_resolvers_k8s.html      536 lines
├── _assistant_resolvers_misc.html     419 lines
├── _assistant_resolvers_shared.html   151 lines
├── _assistant_resolvers_dashboard.html 143 lines
├── _audit_cards_a.html                357 lines
├── _audit_cards_b.html                412 lines
├── _audit.html                         23 lines
├── _audit_init.html                   112 lines
├── _audit_manager.html                478 lines
├── _audit_modals.html                 306 lines
├── _audit_scores.html                 175 lines
├── _secrets_form.html                 179 lines
├── _secrets.html                       24 lines
├── _secrets_init.html                 514 lines
├── _secrets_keys.html                 693 lines
├── _secrets_render.html               537 lines
├── _secrets_sync.html                 372 lines
├── _secrets_vault.html                143 lines
├── _git_auth.html                     300 lines
├── _gh_auth.html                      178 lines
├── _integrations_*.html          (12 files, see below)
├── _integrations_setup_*.html    (10 files, see below)
├── _content_*.html               (11 files, see below)
├── _devops_*.html                (10 files, see below)
├── _debugging.html                  1,145 lines
├── _stage_debugger.html               702 lines
└── ... standalone files
```

**98 files, 11 have >500 lines, 3 have >1000 lines.**

---

## Phase 0 — Split `_globals.html` (3,606 → 7 fragments)

This is the critical path. Everything else depends on `_globals.html`
functions being available. The split produces 7 focused files in a
`globals/` subfolder (they have a shared domain: "framework utilities").

### Section Boundaries (from section markers in the file)

| Fragment | Lines | Content | Functions |
|----------|-------|---------|-----------|
| `_api.html` | 1–69 | API semaphore + `api()` + `apiPost()` + `toast()` + `esc()` + refresh bar | `api`, `apiPost`, `toast`, `esc`, `showRefreshBar`, `hideRefreshBar` |
| `_cache.html` | 93–313 | Card cache + wizard cache + cascade + `cardRefresh` + `cardLoad` + `openFileInEditor` | `cardCached`, `cardStore`, `cardAge`, `cardRefresh`, `cardLoad`, `wizCached`, `wizStore`, `wizAge`, `openFileInEditor` |
| `_card_builders.html` | 314–421 | HTML builders for card UI | `cardStatusGrid`, `cardDetectionList`, `cardDataTable`, `cardActionToolbar`, `cardEmpty`, `cardLivePanel`, `cardGenerateToolbar` |
| `_modal.html` | 423–595 | Generic modal system | `modalOpen`, `modalClose`, `modalSteps`, `modalFormField`, `modalPreview`, `mfVal`, `modalStatus`, `modalError` |
| `_missing_tools.html` | 597–747 | Missing tools banner + install-from-banner | `renderMissingTools`, `renderMissingToolsInline`, `installToolFromBanner`, `resumeToolFromBanner`, `_showSudoInstallModal` |
| `_ops_modal.html` | 749–2791 | Unified ops modal: install, remediation, step modal, SSE, choices, resume | `_showOpsModal`, `_showInstallModal`, `_showRemediationModal`, `showStepModal`, `installWithPlan`, `resumeWithPlan`, `streamSSE`, etc. |
| `_auth_modal.html` | 2792–3607 | Auth modal: browser flow, terminal spawn, token entry, polling, convenience helpers, after-install refresh | `_showAuthModal`, `_launchBrowserAuth`, `_launchTerminalAuth`, `_showGhAuthModal`, `_refreshAfterInstall` |

### Why these boundaries

- **`_api.html`** — The lowest-level primitives. Every other file calls these.
  Must load first.
- **`_cache.html`** — Session cache layer. Depends on `api()` from `_api.html`.
  Used by all card renderers and wizard steps.
- **`_card_builders.html`** — Pure HTML template functions. Depends on `esc()`.
  Used by dashboard, devops, audit card renderers.
- **`_modal.html`** — The modal framework. Depends on `esc()`. Used by ~30 files.
- **`_missing_tools.html`** — Depends on `esc()`, `api()`, `modalOpen()`.
  Used by audit and integrations.
- **`_ops_modal.html`** — The heaviest module (2,043 lines). Depends on
  `modalOpen`, `api`, `esc`, `streamSSE` (internal). This is the plan-based
  install flow — install, remediation, choices, step modal. Used by
  `_dashboard.html`, `_audit_modals.html`, `_stage_debugger.html`.
- **`_auth_modal.html`** — GitHub auth flows. Depends on `modalOpen`, `api`.
  Used by `_gh_auth.html`, `_integrations_github.html`,
  `_integrations_setup_github.html`, `_secrets_render.html`,
  `_wizard_integrations.html`.

### Include order in `dashboard.html`

Replace the single `_globals.html` include with 7 ordered includes:

```jinja
{% include 'scripts/globals/_api.html' %}
{% include 'scripts/globals/_cache.html' %}
{% include 'scripts/globals/_card_builders.html' %}
{% include 'scripts/globals/_modal.html' %}
{% include 'scripts/globals/_missing_tools.html' %}
{% include 'scripts/globals/_ops_modal.html' %}
{% include 'scripts/globals/_auth_modal.html' %}
```

**_ops_modal.html is still 2,043 lines.** This is the ops install flow —
splitting it further separates the SSE `yield` from its setup, making the
streaming logic unreadable. Same rationale as `tool_execution.py` in routes.
If it needs splitting later, the natural boundary is:
- Remediation modal (~800 lines)
- Step modal + SSE (~800 lines)
- Choice UI (~450 lines)

But that's Phase 0b, not Phase 0. We don't split speculatively.

---

## Phase 1 — Group `auth/` (#12)

Two files that share a domain but different blueprints: SSH auth and GitHub auth.

**Current:** `_git_auth.html` (300), `_gh_auth.html` (178)

**Target:** `scripts/auth/` subfolder.

```
scripts/auth/
├── _git_auth.html     300 lines — SSH key unlock
└── _gh_auth.html      178 lines — GitHub CLI auth
```

Update `dashboard.html`:
```jinja
{% include 'scripts/auth/_git_auth.html' %}
{% include 'scripts/auth/_gh_auth.html' %}
```

Simple move, no splitting. Combined = 478 lines, 2 files = qualifies for folder.

---

## Phase 2 — Group `integrations/` (#13)

12 flat `_integrations_*.html` plus 10 `_integrations_setup_*.html`.
22 files total. Obvious folder candidate.

**Current:** 22 files prefixed `_integrations_*` flat in `scripts/`.

**Target:** `scripts/integrations/` subfolder with `setup/` sub-subfolder.

```
scripts/integrations/
├── _integrations.html                 36 lines — tab loader (entry point)
├── _init.html                        253 lines — tab init
├── _cicd.html                        308 lines
├── _dns.html                         219 lines
├── _docker.html                      497 lines
├── _docker_compose.html              125 lines
├── _git.html                         319 lines
├── _github.html                      325 lines
├── _k8s.html                         806 lines  ← evaluate split later
├── _pages.html                       538 lines
├── _pages_config.html                509 lines
├── _pages_sse.html                   462 lines
├── _terraform.html                   306 lines
└── setup/
    ├── _shared.html                  222 lines
    ├── _git.html                     510 lines
    ├── _docker.html                   94 lines
    ├── _cicd.html                   1231 lines  ← evaluate split later
    ├── _k8s_helpers.html             135 lines
    ├── _k8s.html                      54 lines
    ├── _terraform.html               707 lines
    ├── _dns.html                     634 lines
    ├── _github.html                  760 lines
    └── _dispatch.html                 31 lines
```

**Note:** `_integrations_setup_cicd.html` at 1,231 lines should be evaluated
for splitting. But that's a Phase 2b concern — first we group, then we split.

Update `dashboard.html`: all 22 `{% include %}` paths updated from
`scripts/_integrations_*` to `scripts/integrations/...`.

---

## Phase 3 — Group `secrets/` (#14)

6 files prefixed `_secrets_*`.

```
scripts/secrets/
├── _secrets.html         24 lines — tab loader
├── _init.html           514 lines
├── _form.html           179 lines
├── _keys.html           693 lines
├── _render.html         537 lines
├── _sync.html           372 lines
└── _vault.html          143 lines
```

---

## Phase 4 — Group `audit/` (#15)

7 files prefixed `_audit_*`.

```
scripts/audit/
├── _audit.html          23 lines — tab loader
├── _init.html          112 lines
├── _cards_a.html       357 lines
├── _cards_b.html       412 lines
├── _manager.html       478 lines
├── _modals.html        306 lines
└── _scores.html        175 lines
```

---

## Phase 5 — Group `wizard/` (#16)

Currently 8 files: `_wizard.html`, `_wizard_*.html`, `_setup_wizard.html`,
`_globals_wizard_modal.html`.

The `_wizard_integrations.html` at 2,051 lines is the second-largest file.
It needs splitting. `_wizard_integration_actions.html` at 958 lines should
be evaluated too.

```
scripts/wizard/
├── _wizard.html                      24 lines — tab loader
├── _init.html                       200 lines
├── _nav.html                        151 lines
├── _steps.html                      727 lines  ← evaluate split later
├── _helpers.html                    415 lines
├── _modal.html                      404 lines  (was _globals_wizard_modal.html)
├── _setup.html                      333 lines  (was _setup_wizard.html)
├── _integrations.html             2,051 lines  ← MUST SPLIT (Phase 5b)
└── _integration_actions.html        958 lines  ← evaluate split later
```

**Phase 5b — Split `_wizard_integrations.html` (2,051 lines):**

Need to read the file to identify section boundaries. Will plan the exact
split when we reach Phase 5. The natural boundary is likely per-integration
(Docker, K8s, Terraform, Git, GitHub, CI/CD, DNS, Pages — 8 sections).

---

## Phase 6 — Group `assistant/` (#17)

6 files prefixed `_assistant_*`.

```
scripts/assistant/
├── _engine.html                   1,117 lines  ← evaluate split later
├── _resolvers_shared.html           151 lines
├── _resolvers_misc.html             419 lines
├── _resolvers_docker.html         1,256 lines  ← evaluate split later
├── _resolvers_k8s.html              536 lines
└── _resolvers_dashboard.html        143 lines
```

`_assistant_resolvers_docker.html` at 1,256 lines is the worst offender
here. But it might be a single coherent resolver — need to read it before
deciding.

---

## Phase Execution Order

| Phase | What | Files Moved | Files Split | Risk |
|-------|------|-------------|-------------|------|
| **0** | Split `_globals.html` | 0 | 1 → 7 | **High** — everything depends on it |
| **1** | Group `auth/` | 2 → folder | 0 | Low |
| **2** | Group `integrations/` | 22 → folder+sub | 0 | Medium (many paths) |
| **3** | Group `secrets/` | 6 → folder | 0 | Low |
| **4** | Group `audit/` | 7 → folder | 0 | Low |
| **5** | Group `wizard/` | 8 → folder | 1 (integrations) | Medium |
| **5b** | Split `_wizard_integrations.html` | 0 | 1 → ? | High (2,051 lines) |
| **6** | Group `assistant/` | 6 → folder | 0 | Low |

**Total:** ~52 files touched, 2 files split.

---

## Verification Strategy

After each phase:

1. **Syntax check** — grep for unclosed `<script>` tags, unmatched braces
2. **Include check** — verify `dashboard.html` has all includes in correct order
3. **Reference check** — grep for old paths to ensure no stale references
4. **Function availability** — verify that functions defined in split files are
   still callable from their consumers (same position in load order)

---

## Status Table

| Phase | Description | Status |
|-------|-------------|--------|
| Phase 0 — Split `_globals.html` (3,606 → 7 files in `globals/`) | 🟢 |
| Phase 1 — Group `auth/` (2 files) | 🟢 |
| Phase 2 — Group `integrations/` (22 files + `setup/` sub) | 🟢 |
| Phase 3 — Group `secrets/` (7 files) | 🟢 |
| Phase 4 — Group `audit/` (6 files; `_audit_manager` stays in devops) | 🟢 |
| Phase 5 — Group `wizard/` (9 files) | 🟢 |
| Phase 5b — Split `_wizard_integrations.html` | ⬜ (deferred) |
| Phase 6 — Group `assistant/` (6 files) | 🟢 |
| Phase 7 — Group `content/` (14 files) | 🟢 |
| Phase 8 — Group `devops/` (12 files incl. `_audit_manager`) | 🟢 |

**After-state:** 11 subfolders, 12 standalone flat files, 98 total `.html` files.
All include paths verified — zero stale references.
