# Wizard Integrations Step — Evolution Plan

> Step 5: 🔌 Integrations
>
> **Root problem:** Sub-wizard config generation forms are hardcoded for
> Python. The system supports 47 stacks across 15+ languages, detects them
> via `detected_stacks`, but the forms ignore this entirely.

---

## The Problem In Detail

### What the backend already knows

`wizard_detect()` returns `detected_stacks` — a sorted list of resolved
stack names (e.g. `["python-flask"]`). It also returns `_python_version`
as a standalone field, which is the *only* stack-derived hint the
frontend uses.

Each stack in `stacks/<name>/stack.yml` has, after parent resolution:
- `name`: e.g. `python-flask`, `go-gin`, `rust-axum`
- `icon`: emoji
- `domain`: `service` | `library`
- `capabilities`: list of `{ name, command, description }`
  - Common names: `install`, `lint`, `format`, `test`, `build`, `serve`, `run`

### What the frontend hardcodes

**Docker sub-wizard** (`_wizSubForms['int:docker']`, L273–361):
```
Base Image:      python:${pyVer}-slim
Install Command: pip install -e . | pip install -r requirements.txt
Entry Command:   python -m src
Port:            8080
```

**CI/CD sub-wizard** (`_wizSubForms['int:ci']`, L421–518):
```
Python Version:  ${pyVer}
Install Command: pip install -e ".[dev]" || pip install -e .
Test Command:    python -m pytest tests/ -v --tb=short
Lint Command:    ruff check src/
```

**K8s sub-wizard**: No language-specific defaults — clean.
**Terraform sub-wizard**: No language-specific defaults — clean.

### What should happen

The sub-wizard forms should derive defaults from the detected stacks:
- Docker base image from the stack family (python→python:slim, go→golang:alpine, etc.)
- Install/test/lint/serve commands from stack capabilities
- Language version from the stack's requires field or system detection
- Domain awareness (library stacks don't need EXPOSE/CMD)

---

## Phase 0: Backend Evolution — Stack Defaults Endpoint

### Goal

Enrich the `wizard_detect` response with a new `stack_defaults` field
that pre-computes wizard-relevant defaults from detected stacks. The
frontend never loads stack.yml files — it reads pre-computed defaults.

### Shape of `stack_defaults`

```python
"stack_defaults": {
    "primary_stack": "python-flask",    # most specific detected stack
    "language_family": "python",         # base stack name (parent or self)
    "icon": "🐍",
    "domain": "service",                 # service | library
    "docker": {
        "base_image": "python:3.12-slim",
        "install_cmd": "pip install -e '.[dev]'",
        "entry_cmd": "flask run --host=0.0.0.0",  # from serve capability
        "workdir": "/app",
        "port": "5000",                  # framework-aware default
    },
    "ci": {
        "install_cmd": "pip install -e '.[dev]'",
        "test_cmd": "pytest",
        "lint_cmd": "ruff check .",
        "language_version": "3.12",
        "language_key": "python-version", # for CI matrix naming
    },
    "capabilities": {
        "install": "pip install -e '.[dev]'",
        "lint": "ruff check .",
        "format": "ruff format .",
        "test": "pytest",
        "serve": "flask run --debug",
    }
}
```

### Implementation

New helper function in `wizard_ops.py`:

```python
def _wizard_stack_defaults(root: Path, detected_stacks: list[str]) -> dict:
```

This function:
1. Takes the detected_stacks list (already computed in wizard_detect)
2. Loads resolved stacks via `discover_stacks`
3. Picks the primary (most specific) stack
4. Extracts capabilities → maps to wizard field defaults
5. Maps language family → Docker base image, CI version key
6. Returns the pre-computed dict

### Language family → Docker base image mapping

```python
_DOCKER_IMAGES = {
    "python":   "python:{version}-slim",
    "go":       "golang:{version}-alpine",
    "node":     "node:{version}-alpine",
    "rust":     "rust:{version}-slim",
    "java":     "eclipse-temurin:{version}-jdk-alpine",
    "dotnet":   "mcr.microsoft.com/dotnet/aspnet:{version}",
    "ruby":     "ruby:{version}-slim",
    "elixir":   "elixir:{version}-slim",
    "php":      "php:{version}-cli",
    "c":        "gcc:{version}",
    "cpp":      "gcc:{version}",
    "swift":    "swift:{version}",
    "zig":      "alpine:latest",
}
```

### Language family → CI version key mapping

```python
_CI_VERSION_KEYS = {
    "python": "python-version",
    "go":     "go-version",
    "node":   "node-version",
    "rust":   "toolchain",
    "java":   "java-version",
    "dotnet": "dotnet-version",
    "ruby":   "ruby-version",
    "elixir": "elixir-version",
}
```

### Where in the response

Added to `wizard_detect` return dict alongside `detected_stacks`:

```python
return {
    ...
    "detected_stacks": detected_stacks,
    "stack_defaults": _wizard_stack_defaults(root, detected_stacks),
    ...
}
```

---

## Phase 1–8: Per-Integration Updates (one at a time)

Each integration is a self-contained unit of work. We do NOT attempt
multiple in one pass.

### 1. Docker (`int:docker`) — HIGH PRIORITY

**What changes:**
- Base image default from `stack_defaults.docker.base_image`
- Install command from `stack_defaults.docker.install_cmd`
- Entry command from `stack_defaults.docker.entry_cmd` (serve capability)
- Port default from framework awareness (Flask=5000, Express=3000, etc.)
- Domain check: if `library`, hide port/CMD fields (no server)

**What stays:**
- Live panels (containers/images/compose) — operational, stack-independent
- Operational buttons (start/stop/build/prune) — stack-independent
- Delete config — stack-independent

**Files touched:**
- `_wizard_integrations.html` L273–361 (sub-wizard form)
- `wizard_ops.py` (stack_defaults computation)

---

### 2. CI/CD (`int:ci`) — ✅ DONE

**What changed:**
- **Header**: Stack badge + CI provider badge from `ci_status`
- **Status strip**: Enriched with workflow count, gh auth status + username, repo slug
- **Pipeline Connections dashboard**: New section showing every integration's
  detection status and CI relevance (Git, GitHub, Stacks, Docker, K8s,
  Terraform, Environments, Pages) — uses embedded data from `ci_status`,
  `gh_cli_status`, `gh_user`, `gh_repo_info`, `gh_environments`, `env_status`,
  `detected_stacks`
- **Basic Workflow form**: All 4 command fields now from `stack_defaults.ci`
  - Dynamic language label from `sd.language_label` (not "Python Version")
  - Version from `sd.language_version`
  - Install/test/lint commands from stack capabilities
  - Field ID renamed: `wiz-ci-python` → `wiz-ci-langver`
- **Compose Pipeline**: Capability pills replaced with "Pipeline Jobs"
  pills that include Test (with stack name), Lint, Docker Build, K8s Deploy,
  Terraform, Multi-env, Pages Deploy
  - Deploy Method and Registry fields conditionally shown only if K8s/Docker detected
  - `_wizComposeCi` now uses `d.detected_stacks` instead of hardcoded Python check
- **Payload**: `_wizApplySetup` sends both `language_version` + `python_version`
  (backward compat) and adds `stacks` + `language_family`

**What stays:**
- Trigger branches — universal
- Overwrite toggle — universal
- Compose Full Pipeline — enhanced, not replaced
- Delete config — unchanged

**Files touched:**
- `_wizard_integrations.html` (sub-wizard form — complete rewrite)
- `_wizard_integration_actions.html` (payload + _wizComposeCi stack_names fix)

---

### 3. Git (`int:git`) — ✅ DONE

**What changed:**
- **Card detail**: Now shows branch, short remote URL, .gitignore coverage %, hook count
- **Status strip**: 5 pills — git CLI (+ version), repo init (+ branch), remote count,
  .gitignore coverage %, hook count — all from `status_probes.git` + `gitignore_analysis`
- **Remotes section**: Collapsible `<details>` listing all remotes with URLs and
  per-remote delete button with confirmation. "Add remote" form with name + URL,
  auto-prefilled from `gh_cli_status.repo` if GitHub is linked.
  Uses live `/git/remote/add` and `/git/remote/remove` endpoints.
- **.gitignore section**: Shows coverage health — complete (✅), missing patterns
  (⚠️ with pattern pills), or missing (.gitignore not found). Offers generate/regenerate
  checkbox that triggers `generate_gitignore` flag → backend auto-generates from
  detected stacks via `security_scan.generate_gitignore()`.
- **Pre-commit hooks**: Shown only if stack has lint/format capabilities AND no hooks
  exist. Shows detected lint/format commands as pills. Offers install checkbox that
  sends `setup_hooks: true` + `hook_commands` from `stack_defaults.capabilities`.
- **Initial commit**: Shown only if repo not initialized or 0 commits. Checkbox +
  commit message field.
- **Default branch**: Field with current branch display.
- **Apply button**: Full payload now sends `default_branch`, `generate_gitignore`,
  `setup_hooks` + `hook_commands`, `create_initial_commit` + `commit_message`.
- **Backend**: `setup_git` now supports `generate_gitignore: true` flag — auto-detects
  stacks and generates content via `security_scan.generate_gitignore()`.

**Files touched:**
- `_wizard_integrations.html` (sub-wizard form — complete rewrite, card details enriched)
- `_wizard_integration_actions.html` (enriched payload for `int:git`)
- `wizard_setup.py` (added `generate_gitignore` auto-generation path)

---

### 4. GitHub (`int:github`) — ✅ DONE

**What changed:**
- **Card detail**: Now shows @username, repo slug, visibility, env count, CODEOWNERS ✓,
  workflow count. When not authenticated, shows "gh CLI installed but not authenticated."
- **Status strip**: 8+ pills — authenticated, @user, repo slug, visibility (🔒/🌐),
  default branch (🌿), env count, missing envs count, CODEOWNERS ✓/○, workflow count
- **User card**: Avatar image (from `gh_user.avatar_url`), username, display name,
  and Logout button (calls `/gh/auth/logout`).
- **Repository section**: Collapsible `<details>` showing slug, visibility badge
  (🔒/🌐), description, default branch, fork status, homepage URL, link to GitHub.
- **Environment alignment**: Alignment table showing local environments vs. GitHub
  environments. Each row shows ✅/⬜ status, environment name, and a checkbox for
  missing environments. "Create N Environment(s)" button calls `setup_github` with
  `create_environments` payload.
- **CODEOWNERS**: Collapsible section. If exists, shows scrollable preview of content.
  If missing, offers "Create CODEOWNERS" checkbox with inline textarea editor
  (pre-filled with `* @owner`). Uses `onchange` handler (not `<script>` tag).
- **Secrets overview**: Collapsible section with "Push vault secrets to GitHub now"
  checkbox. Links to Secrets tab and Full Setup for granular management.
- **Apply button**: New handler sends `create_environments`, `push_secrets`,
  `codeowners_content` to `setup_github` backend action.
- **Auth states**: Three distinct states — not installed (Install + Re-detect buttons),
  installed but not authenticated (Authenticate + Re-detect), authenticated (full dashboard).

**Files touched:**
- `_wizard_integrations.html` (sub-wizard form — complete rewrite, card details enriched)
- `_wizard_integration_actions.html` (new `int:github` handler)

---

### 5. Pages (`int:pages`) — ✅ DONE

**What changed:**
- **Card detail**: Now dynamic — shows segment count + builders + deploy branch if
  configured, "N content folders detected — auto-init available" if content exists
  but no segments, falls back to static description otherwise.
- **Backend embed**: New `_wizard_pages_status()` helper in `wizard_ops.py` returns
  `segments`, `meta` (base_url, deploy_branch), `content_folders` (with per-folder
  `best_builder` recommendation via `detect_best_builder()`), `builders_available`,
  and `can_auto_init` flag. Embedded as `pages_status` in `wizard_detect` response.
- **Status strip**: 5 pills — pages status (ready/partial/not configured), segment
  count, .pages/ workspace, deploy branch, content folder count (when no segments).
- **Segments section**: Collapsible `<details>` listing each segment with name,
  builder, and source→path mapping.
- **Content folders section**: Lists all detected content folders with file count,
  best builder recommendation, and segment status (✅ exists / ⬜ no segment).
  Shows builder suggestions for uninitialized folders. Includes "Auto-initialize N
  segments from content folders" checkbox with per-folder builder mapping.
- **Available builders**: Collapsible section showing all builders with availability
  status (✅ available / ○ not installed).
- **Deploy info**: Shows deploy branch and base URL when configured.
- **Auto-init action**: Apply button appears when `can_auto_init` is true. Calls
  `setup_pages` backend action with `auto_init: true`, which wraps
  `init_pages_from_project()` from `pages_discovery.py`.
- **Backend action**: New `setup_pages` in `wizard_setup.py`, registered in
  `_SETUP_ACTIONS`. Calls `init_pages_from_project()` to auto-create segments
  from detected content folders using best available builder.
- **Escalation**: Points to Pages tab for full management.

**Files touched:**
- `wizard_ops.py` (new `_wizard_pages_status` helper + embed in response)
- `wizard_setup.py` (new `setup_pages` action + registration)
- `_wizard_integrations.html` (card detail enriched + sub-wizard form rewrite)
- `_wizard_integration_actions.html` (new `int:pages` handler)

---

### 6. K8s (`k8s`) — CLEAN

Already stack-independent (app name, image, port, replicas, namespace).
**No changes needed** for stack-awareness.

---

### 7. Terraform (`terraform`) — CLEAN

Already stack-independent (provider, region, project, backend).
**No changes needed** for stack-awareness.

---

### 8. DNS (`dns`) — NEEDS SUB-WIZARD

Currently missing entirely. Backend `setup_dns` + `generate_dns_records`
exist. But this is net-new work, not an evolution of existing code.
**Decision:** separate task, not part of this evolution.

---

## Execution Order

1. **Phase 0: `_wizard_stack_defaults`** in `wizard_ops.py`
   — backend foundation, no frontend changes
2. **Phase 1: Docker sub-wizard** — highest impact, most hardcoded values
3. **Phase 2: CI/CD sub-wizard** — second highest impact
4. **Phase 3: Git sub-wizard** — enrichment from embedded data
5. **Phase 4: GitHub sub-wizard** — enrichment from embedded data
6. *(Phases 5-8 deferred or no-op)*

---

## Risks

| Risk | Mitigation |
|------|------------|
| Multi-module projects with mixed stacks | `primary_stack` picks most specific. Multi-stack defaults could be an array but forms take single values — pick first for defaults, user can change |
| Stacks with no serve capability (libraries) | Domain check: `domain === "library"` → no CMD/EXPOSE suggestion for Docker |
| Version detection for non-Python stacks | Stack `requires[].min_version` has the declared minimum. For actual installed version, would need runtime detection per language — defer to Phase 0 implementation |
| Stacks dir might not exist | Already wrapped in try/except in wizard_detect. `stack_defaults` returns sensible fallback (empty/generic) |
| Backward compat | `_python_version` stays. `stack_defaults` is additive. Sub-wizards fall back to existing defaults if `stack_defaults` is absent |
