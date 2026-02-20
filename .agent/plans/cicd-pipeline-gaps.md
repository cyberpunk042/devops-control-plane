# CI/CD Pipeline Generation — Gap Analysis & Plan

Created: 2026-02-18
Context: Expanding CI/CD wizard to produce real, functional pipelines

---

## Current Architecture

Three codepaths can generate CI workflows:

1. **`setup_ci()`** in `wizard_setup.py` — called by the wizard's `POST /wizard/setup {action: setup_ci}`.
   Generates a single `ci.yml` with test/Docker/K8s jobs using Python `yaml.dump()`.

2. **`ci_compose.py`** — cross-domain orchestrator that can produce unified or split workflows.
   Called by `POST /ci/generate/ci` (quick-generate from card toolbar).
   Produces `ci-cd.yml` using YAML string templates.

3. **`generators/github_workflow.py`** — per-stack templates (python, node, go, rust, java).
   Used by BOTH #1 (via `_build_test_jobs_from_stacks`) and #2 (via `_build_test_jobs`).

**Key difference**: #1 uses `yaml.dump()` (dict → YAML), while #2 and #3 use string templates.
The wizard calls #1 directly. The card toolbar calls #2 which calls #3.

---

## What `setup_ci()` Generates Today

```yaml
name: CI
on:
  push: {branches: [main, master]}
  pull_request: {branches: [main, master]}
permissions: {contents: read}
jobs:
  test:          # from stacks (matrix, caching) OR custom commands
  docker:        # build + push with Buildx (needs test)
  deploy-staging:   # per-environment K8s deploy (needs docker)
  deploy-production: # chained after staging
```

### What it handles:
- ✅ Stack-aware test jobs with matrix builds and caching (via generators)
- ✅ Custom test/lint/install commands (fallback when no stacks)
- ✅ Docker build/push with Buildx, layer caching (type=gha)
- ✅ Multi-registry login (GHCR, DockerHub, custom)
- ✅ Docker build args
- ✅ K8s deploy: kubectl / skaffold / helm
- ✅ Multi-environment deploys with chaining
- ✅ Per-env: branch filter, namespace, kubeconfig secret, skaffold profile, values file
- ✅ Overwrite guard
- ✅ Dry-run validation (kubectl)
- ✅ Rollout status wait (kubectl)

### What it does NOT handle:

| Gap | Category | Impact |
|-----|----------|--------|
| **Environment variables** per job/env | Config | Pipeline won't have the env vars apps need (APP_ENV, DATABASE_URL, etc.) |
| **Secrets mapping** beyond kubeconfig | Config | No way to pass DOCKER_PASSWORD, API_KEY, etc. to jobs |
| **Docker build args from UI** | UI gap | Backend supports `docker_build_args` but wizard doesn't expose it |
| **Concurrency control** | Safety | Parallel deploys to same env can conflict |
| **Trigger: workflow_dispatch** | Config | Manual trigger option exists in UI but isn't wired to YAML output |
| **Trigger: schedule (cron)** | Config | No scheduled runs |
| **Coverage upload** | Quality | UI checkbox exists but no step generated |
| **Type-check step** | Quality | UI checkbox exists but no step for custom commands mode |
| **Artifact upload/download** | Quality | No artifact passing between jobs |
| **Timeout** | Safety | No job/step timeout limits |
| **Environment protection rules** | Safety | No `environment:` key for GitHub Environments |
| **Notifications** | Ops | No Slack/email/Teams on failure |
| **Caching** (custom commands mode) | Perf | Stack mode has caching, custom mode doesn't |
| **Matrix builds** (custom commands mode) | Perf | Stack mode has matrix, custom mode doesn't |
| **GITHUB_TOKEN permissions** refinement | Security | Hardcoded `contents: read`, no per-job scoping |
| **Path filters** | Perf | Trigger on all changes, not relevant paths only |

---

## What the Wizard UI Does NOT Expose

Even where the backend HAS support, the wizard doesn't collect:

| Backend field | Wizard exposes? | Fix location |
|--------------|----------------|--------------|
| `docker_build_args` (dict) | ❌ | Step 3 (Build & Deploy) |
| `docker_registry` | ✅ | — |
| `lint_cmd` (custom) | ✅ (when no stacks) | — |
| `install_cmd` (custom) | ✅ (when no stacks) | — |
| `overwrite` | ✅ | — |

---

## Phased Plan

### Phase 1: Wire existing backend to UI (no backend changes)

**Scope**: Expose fields the backend already supports but the UI doesn't.

1. **Docker build args** — add key-value pair editor to Step 3
2. **Trigger mapping** — wire the trigger selector to actual YAML output
   - Currently: `push-pr | push | pr | manual` collected in UI
   - Backend: only generates `push + pull_request` with branch filter
   - Fix: map trigger type to correct `on:` structure in `setup_ci()`

### Phase 2: Essential pipeline features (backend + UI)

**Scope**: Make generated pipelines production-usable.

3. **Environment variables** — per-job env var editor (key-value pairs)
   - Backend: add `env` dict per job and per deploy-env
   - UI: key-value editor in Step 2 (Pipeline) and Step 4 (Environments)

4. **Secrets references** — per-job/env secret name list
   - Backend: add `secrets` as `env` entries with `${{ secrets.NAME }}` syntax
   - UI: secret name input in Step 4 (per environment)

5. **Concurrency control**
   - Backend: add `concurrency:` block to workflow
   - UI: checkbox "Cancel in-progress runs" + group name in Step 2

6. **Coverage upload step**
   - Backend: when `coverage=True`, add upload step (e.g., `codecov/codecov-action@v4`)
   - UI: already has checkbox, just needs backend wiring

7. **Type-check step** (custom commands mode)
   - Backend: when `typecheck=True`, add `mypy` or custom command step
   - UI: already has checkbox, needs `typecheck_cmd` field and backend wiring

8. **GitHub Environment protection**
   - Backend: add `environment:` key to deploy jobs (enables approval gates)
   - UI: toggle per-env "Require approval" in Step 4

### Phase 3: Nice-to-have (future)

9. **Path filters** — only trigger on relevant file changes
10. **Scheduled triggers** — cron expression
11. **Notifications** — Slack webhook step on failure
12. **Artifact management** — cross-job artifact passing
13. **Timeout configuration** — per-job timeout
14. **Caching in custom commands mode** — auto-detect from install command

---

## Implementation Order

**Phase 1** (UI-only, no backend changes):
- [x] P1.1: Docker build args editor in Step 3
- [x] P1.2: Fix trigger type → YAML mapping in `setup_ci()`

**Phase 2** (backend + UI, essential):
- [x] P2.1: Per-job environment variables (backend + Step 2 UI)
- [x] P2.2: Per-env secrets references (backend + Step 4 UI)
- [x] P2.3: Concurrency control (backend + Step 2 UI)
- [x] P2.4: Coverage upload step (backend, UI checkbox already exists)
- [x] P2.5: Type-check step for custom mode (backend + UI field)
- [x] P2.6: GitHub Environment protection (backend + Step 4 UI)

**Phase 3** (future):
- Deferred — not blocking real pipeline usage

---

## Backend Changes Required

### `setup_ci()` in `wizard_setup.py`

New data keys to accept:

```python
# Phase 1
trigger_type      – "push-pr" | "push" | "pr" | "manual" | "schedule"

# Phase 2
env_vars          – dict[str, str]            # global env vars for all jobs
env_vars_per_env  – dict[str, dict[str, str]] # per-environment env vars
secrets           – list[str]                 # secret names to map
coverage_tool     – "codecov" | "coveralls" | ""
typecheck         – bool
typecheck_cmd     – str  (default: "mypy src/ --ignore-missing-imports")
concurrency_group – str  (default: "ci-${{ github.ref }}")
cancel_in_progress – bool
docker_build_args – dict[str, str]            # ALREADY SUPPORTED, just needs UI

# Phase 2 (per-environment, inside environments list dicts)
environments[].env_vars         – dict[str, str]
environments[].secrets          – list[str]
environments[].require_approval – bool  (maps to `environment:` key)
```

### Workflow YAML additions:

```yaml
# Concurrency
concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

# Per-job env vars
jobs:
  test:
    env:
      APP_ENV: test
      DATABASE_URL: ${{ secrets.DATABASE_URL }}

  deploy-staging:
    environment: staging          # GitHub Environment protection
    env:
      APP_ENV: staging
      API_KEY: ${{ secrets.STAGING_API_KEY }}
```
