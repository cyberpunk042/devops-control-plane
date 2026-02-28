# Revolution Plan — Refactor Roadmap

> Created: 2026-02-28
> Constraint: <500 lines per file. ~700 absolute max exception.
> Pattern: SRP. Onion folders. Domain grouping.
> Process: Refactor first, document each domain README AFTER it lands.

---

## Execution Order

Refactor from **inside out** (core first, then routes, then frontend).
Each domain is an atomic unit: move → split → fix imports → verify → doc.

---

## Phase 1: Backend `core/services/` — Domain Folders

Create domain folders, move files, add `__init__.py` re-exports so external
imports don't break. Split oversized files.

### 1A. docker/

**Move** (no split needed, all <700):
```
docker_common.py     → docker/common.py
docker_containers.py → docker/containers.py  (733, borderline — evaluate)
docker_detect.py     → docker/detect.py
docker_generate.py   → docker/generate.py
docker_k8s_bridge.py → docker/k8s_bridge.py
docker_ops.py        → docker/ops.py
```

**Split if needed**: `docker_containers.py` at 733 — may split manage vs inspect.

### 1B. k8s/

**Move + SPLIT** (k8s_validate.py is 4,004 lines):
```
k8s_cluster.py         → k8s/cluster.py
k8s_common.py          → k8s/common.py
k8s_detect.py          → k8s/detect.py
k8s_generate.py        → k8s/generate.py
k8s_helm.py            → k8s/helm.py
k8s_helm_generate.py   → k8s/helm_generate.py
k8s_ops.py             → k8s/ops.py
k8s_pod_builder.py     → k8s/pod_builder.py
k8s_wizard.py          → k8s/wizard.py
k8s_wizard_detect.py   → k8s/wizard_detect.py
k8s_wizard_generate.py → k8s/wizard_generate.py (1,012 → SPLIT)
```

**CRITICAL SPLIT**: `k8s_validate.py` (4,004) → `k8s/validate/`:
- `k8s/validate/__init__.py` — public API
- `k8s/validate/schema.py` — schema rules
- `k8s/validate/security.py` — security rules
- `k8s/validate/resources.py` — resource rules
- `k8s/validate/networking.py` — networking rules
- `k8s/validate/report.py` — report generation
- (exact split TBD after reading the file's internal structure)

**SPLIT**: `k8s_wizard_generate.py` (1,012) → two files TBD

### 1C. vault/

**Move** (all reasonable size):
```
vault.py           → vault/core.py
vault_io.py        → vault/io.py
vault_env_crud.py  → vault/env_crud.py
vault_env_ops.py   → vault/env_ops.py
```

### 1D. secrets/

**Move**:
```
secrets_env_ops.py → secrets/env_ops.py
secrets_gh_ops.py  → secrets/gh_ops.py
secrets_ops.py     → secrets/ops.py
```

### 1E. content/

**Move**:
```
content_crypto.py         → content/crypto.py
content_crypto_ops.py     → content/crypto_ops.py
content_file_advanced.py  → content/file_advanced.py
content_file_ops.py       → content/file_ops.py
content_listing.py        → content/listing.py
content_optimize.py       → content/optimize.py
content_optimize_video.py → content/optimize_video.py (677 — exception OK)
content_release.py        → content/release.py
content_release_sync.py   → content/release_sync.py
```

### 1F. git/

**Move + SPLIT**:
```
git_auth.py    → git/auth.py
git_ops.py     → git/ops.py
git_gh_ops.py  → git/gh_ops.py (951 → SPLIT into gh_repos.py + gh_actions.py or similar)
```

### 1G. ci/

**Move**:
```
ci_compose.py → ci/compose.py
ci_ops.py     → ci/ops.py
```

### 1H. terraform/

**Move**:
```
terraform_actions.py  → terraform/actions.py
terraform_generate.py → terraform/generate.py (657 — OK)
terraform_ops.py      → terraform/ops.py
```

### 1I. wizard/

**Move + SPLIT**:
```
wizard_ops.py      → wizard/ops.py (748 → SPLIT)
wizard_setup.py    → wizard/setup.py (1,568 → MUST SPLIT by integration)
wizard_validate.py → wizard/validate.py
```

**CRITICAL SPLIT**: `wizard_setup.py` (1,568) — one handler per integration:
- `wizard/setup/__init__.py` — dispatcher
- `wizard/setup/git.py`
- `wizard/setup/github.py`
- `wizard/setup/docker.py`
- `wizard/setup/k8s.py`
- `wizard/setup/cicd.py`
- `wizard/setup/dns.py`
- `wizard/setup/terraform.py`
- `wizard/setup/pages.py`
- (exact split TBD after reading internal structure)

### 1J. backup/

**Move**:
```
backup_archive.py → backup/archive.py (600 — OK)
backup_common.py  → backup/common.py
backup_extras.py  → backup/extras.py
backup_ops.py     → backup/ops.py
backup_restore.py → backup/restore.py (574 — OK)
```

### 1K. devops/

**Move**:
```
devops_activity.py → devops/activity.py (864 → SPLIT)
devops_cache.py    → devops/cache.py (700 — borderline)
env_infra_ops.py   → devops/infra_ops.py
env_ops.py         → devops/env_ops.py
```

**SPLIT**: `devops_activity.py` (864) — separate activity tracking from scoring

### 1L. security/

**Move**:
```
security_common.py  → security/common.py
security_ops.py     → security/ops.py
security_posture.py → security/posture.py
security_scan.py    → security/scan.py
```

### 1M. pages/

**Move** (pages_builders/ already grouped, keep as-is):
```
pages_build_stream.py → pages/build_stream.py
pages_ci.py           → pages/ci.py
pages_discovery.py    → pages/discovery.py
pages_engine.py       → pages/engine.py
pages_install.py      → pages/install.py
pages_preview.py      → pages/preview.py
```

### 1N. Remaining flat files → shared/

**Move**:
```
detection.py        → shared/detection.py
identity.py         → shared/identity.py
event_bus.py        → shared/event_bus.py
project_probes.py   → shared/project_probes.py
staleness_watcher.py → shared/staleness_watcher.py
run_tracker.py      → shared/run_tracker.py
md_transforms.py    → shared/md_transforms.py
config_ops.py       → shared/config_ops.py
terminal_ops.py     → shared/terminal_ops.py
dev_overrides.py    → shared/dev_overrides.py
dev_scenarios.py    → shared/dev_scenarios.py (902 → SPLIT)
```

### 1O. Already-grouped subdomains — VERIFY only

These already follow the onion pattern. Just verify no file exceeds 700:
- `audit/` — `l0_detection.py` (1,601!), `catalog.py` (~1,100) → MUST SPLIT
- `chat/` — `chat_refs.py` (1,280), `chat_ops.py` (731) → MUST SPLIT chat_refs
- `generators/` — `github_workflow.py` (1,081) → MUST SPLIT
- `ledger/` — `worktree.py` (609) — OK
- `trace/` — `trace_recorder.py` (720) — borderline
- `pages_builders/` — `docusaurus.py` (749) — borderline, `base.py` (400) — OK
- `tool_install/` — `recipes.py` (7,435!), `remediation_handlers.py` (3,724), `tool_failure_handlers.py` (3,227) → MUST SPLIT

---

## Phase 2: Routes — Package + Split

### 2A. Move to `ui/web/routes/` package

All `routes_*.py` → `routes/` subdirectory with `__init__.py` that registers blueprints.

### 2B. Split oversized

| File | Lines | Action |
|---|---|---|
| `routes_audit.py` | 1,781 | SPLIT into routes/audit/__init__.py + per-concern files |
| `routes_integrations.py` | 600 | Borderline — evaluate |

---

## Phase 3: Frontend scripts/ — Domain Folders + God File Split

### 3A. Split `_globals.html` (3,606 → 10+ files)

Extract into `globals/` folder:
```
_globals.html (3,606) → globals/
├── _api.html           — api(), apiPost(), esc(), debounce()
├── _modal.html         — modalOpen(), modalClose(), modalError()
├── _toast.html         — toast system
├── _card_helpers.html  — cardCached(), cardStore(), cardInvalidate()
├── _ops_modal.html     — _showOpsModal(), ops auth flow
├── _tool_install_ui.html — installWithPlan(), renderMissingTools()
├── _refresh.html       — refresh-after-install helpers
├── _wizard_shared.html — wizStore(), wizInvalidate(), shared wizard utils
├── _format.html        — formatBytes(), formatDate(), escHtml() etc.
└── _init.html          — global state vars, DOMContentLoaded glue
```

### 3B. Domain-group remaining files

Move files into domain folders (mirrors backend structure):
```
scripts/
├── globals/            — from _globals.html split
├── auth/               — _git_auth.html, _gh_auth.html
├── integrations/       — _integrations_*.html
│   └── setup/          — _integrations_setup_*.html
├── content/            — _content_*.html
├── secrets/            — _secrets_*.html
├── audit/              — _audit_*.html
├── devops/             — _devops_*.html
├── wizard/             — _wizard_*.html, _setup_wizard.html
│   ├── docker/         — docker_wizard/ (already grouped)
│   └── k8s/            — k8s_wizard/ (already grouped)
├── assistant/          — _assistant_*.html
├── dashboard/          — _dashboard.html
├── debug/              — _debugging.html, _stage_debugger.html
├── _boot.html          — stays at root
├── _tabs.html          — stays at root
├── _theme.html         — stays at root
├── _commands.html      — stays at root
├── _lang.html          — stays at root
├── _dev_mode.html      — stays at root
├── _monaco.html        — stays at root
└── _event_stream.html  — stays at root
```

### 3C. Split oversized frontend files

Each file >700 lines needs per-file analysis and SRP split.
Priority order (worst first):
1. `_globals.html` (3,606) — Phase 3A
2. `_wizard_integrations.html` (2,051) — split per integration
3. `_assistant_resolvers_docker.html` (1,256) — split per resolver group
4. `_integrations_setup_cicd.html` (1,231) — split per step
5. `_content_chat.html` (1,159) — split chat UI vs sync vs rendering
6. `_debugging.html` (1,145) — split per debug tool
7. `_assistant_engine.html` (1,117) — split engine vs rendering
8. `_wizard_integration_actions.html` (958) — split per integration
9. `_content_chat_refs.html` (955)
10. All others 700-900

---

## Phase 4: CSS Split

`admin.css` (5,948) → domain-scoped CSS files if needed.
Lower priority — CSS doesn't confuse AI navigability as much.

---

## Phase 5: Tests Follow Source

After each domain refactors, its test file(s) get moved/renamed to match.
No test changes BEFORE their source moves.

---

## Phase 6: Stale Documentation

Update `docs/ARCHITECTURE.md` and other stale docs to reflect the new structure.
This is LAST because the structure needs to stabilize first.

---

## Execution Rules

1. **One domain at a time.** Complete it fully before starting the next.
2. **Verify app runs** after each domain refactor.
3. **Fix ALL imports** in that same pass (grep for old paths).
4. **Write domain README.md** immediately after that domain lands.
5. **Never split a file without reading it first** — internal structure dictates the split.
6. **Dashboard include list** (`dashboard.html`) must be updated with each frontend move.
7. **No scope drift** — refactor only, no new features during this phase.
