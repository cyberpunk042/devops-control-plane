# CI Domain

> The CI/CD intelligence layer for the devops control plane.
> Detects which CI providers a project uses, parses workflow files
> across 7 providers, analyzes CI coverage per module, generates
> GitHub Actions workflows from detected stacks, and composes
> multi-domain pipelines from wizard state.

---

## How It Works

The CI domain has two distinct halves that serve different use cases:

### ops.py — Observe and Generate

`ops.py` answers questions about existing CI and generates individual
workflow files:

```
                    Project Root
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
    .github/workflows  .gitlab-ci.yml  Jenkinsfile  ...
          │              │              │
          └──────────────┼──────────────┘
                         │
              ┌──────────▼──────────┐
              │     ci_status()     │  "What CI do you have?"
              │  Scan 7 providers   │
              │  Count workflows    │
              └──────────┬──────────┘
                         │
              ┌──────────▼──────────┐
              │   ci_workflows()    │  "What's in those workflows?"
              │  Parse YAML         │
              │  Extract triggers,  │
              │  jobs, steps        │
              │  Audit for issues   │
              └──────────┬──────────┘
                         │
              ┌──────────▼──────────┐
              │   ci_coverage()     │  "Which modules have CI?"
              │  Text-scan CI files │
              │  Match module paths │
              │  Match stack markers│
              └─────────────────────┘
```

**Provider detection** checks 7 CI systems by looking for their
signature files and directories:

| Provider | Detection |
|----------|-----------|
| GitHub Actions | `.github/workflows/*.yml` |
| GitLab CI | `.gitlab-ci.yml` |
| Jenkins | `Jenkinsfile` |
| CircleCI | `.circleci/` |
| Travis CI | `.travis.yml` |
| Azure Pipelines | `azure-pipelines.yml` |
| Bitbucket Pipelines | `bitbucket-pipelines.yml` |

**Workflow parsing** goes deeper for GitHub Actions and GitLab CI —
YAML is parsed, triggers extracted, jobs enumerated with step counts
and runner info, and common issues detected (empty run commands,
unpinned actions).

**Coverage analysis** answers "which of my modules are covered by CI?"
by concatenating all CI file contents and searching for module paths,
module names, and stack-specific markers:

```python
_STACK_CI_MARKERS = {
    "python": ["pytest", "ruff", "mypy", "pip install", "python -m"],
    "node":   ["npm test", "npm run", "yarn test", "jest", "vitest"],
    "go":     ["go test", "go vet", "golangci-lint"],
    "rust":   ["cargo test", "cargo clippy", "cargo check"],
    ...
}
```

If a module's stack is "python" and the CI files contain "pytest",
that module is considered covered.

**Generation** produces individual GitHub Actions workflow files:
- `generate_ci_workflow()` — test workflow per detected stack
- `generate_lint_workflow()` — lint workflow per detected stack
- `generate_terraform_workflow()` — Terraform plan/apply workflow

Each delegates to `generators/github_workflow.py` for the actual
YAML production — `ops.py` handles auto-detection and audit logging.

### compose.py — Multi-Domain Pipeline Orchestration

`compose.py` is the sophisticated half. It takes the **full wizard state**
(stacks, Docker services, K8s deploy config, Terraform config, DNS domains,
CDN provider, environments) and produces a coherent set of workflow files
with correct job dependencies.

Two strategies:

```
                       wizard_state
                           │
            ┌──────────────┼──────────────┐
            ▼                             ▼
     ┌─────────────┐              ┌─────────────┐
     │   unified    │              │    split     │
     │  strategy    │              │  strategy    │
     │              │              │              │
     │ Single       │              │ Separate     │
     │ ci-cd.yml    │              │ ci.yml       │
     │ with all     │              │ docker.yml   │
     │ jobs chained │              │ deploy.yml   │
     │ via `needs`  │              │ terraform.yml│
     │              │              │ linked via   │
     │              │              │ workflow_run │
     └──────┬──────┘              └──────┬──────┘
            │                            │
            └────────────┬───────────────┘
                         ▼
                 List[GeneratedFile]
```

**Unified** (default) — produces one `ci-cd.yml` with all jobs. The
dependency chain is built automatically:

```
test jobs (per stack)
  → terraform job (parallel with docker)
  → docker build/push job (needs: test)
  → deploy job (needs: docker)
    → per-environment deploys if multi-env
  → post-deploy (DNS verify + CDN purge)
```

**Split** — produces separate files linked via `workflow_run` triggers.
Each file is self-contained. The deploy workflow triggers when the
docker workflow succeeds. Used when teams prefer separate pipeline
visibility.

The compose layer doesn't generate YAML directly — it delegates to
the job builders in `generators/github_workflow.py` (`_resolve_job`,
`_docker_ci_job`, `_kubectl_deploy_ci_job`, etc.) and orchestrates
them into the right structure.

---

## File Map

```
ci/
├── __init__.py     Public API re-exports (27 lines)
├── ops.py          Detection, parsing, coverage, generation (593 lines)
├── compose.py      Multi-domain pipeline composition (545 lines)
└── README.md       This file
```

### `ops.py` — Detection + Parsing + Generation (593 lines)

Three concerns in one file, organized by section headers:

| Section | Functions | What They Do |
|---------|-----------|-------------|
| **Detect** | `ci_status()` | Scan 7 providers, count workflows, check required tools |
| **Observe** | `ci_workflows()`, `_parse_github_workflow()`, `_parse_gitlab_ci()`, `_audit_github_workflow()` | Parse workflow YAML, extract structure, detect issues |
| **Observe** | `ci_coverage()`, `_gather_ci_content()`, `_check_stack_coverage()` | Analyze which modules have CI coverage |
| **Generate** | `generate_ci_workflow()`, `generate_lint_workflow()`, `generate_terraform_workflow()` | Produce individual workflow files via `generators/` |

### `compose.py` — Pipeline Composition (545 lines)

| Function | What It Does |
|----------|-------------|
| `compose_ci_workflows()` | **Public API** — dispatch to unified or split strategy |
| `_compose_unified()` | Single ci-cd.yml with all jobs chained via `needs` |
| `_compose_split()` | Separate files linked via `workflow_run` triggers |
| `_build_test_jobs()` | Resolve stack names → test job YAML blocks |
| `_build_docker_job()` | Docker build/push job from service configs |
| `_build_deploy_job()` | K8s deploy job (kubectl / skaffold / helm) |
| `_build_terraform_job()` | Terraform plan/apply job |
| `_build_post_deploy_steps()` | DNS verify + CDN purge post-deploy |
| `_build_env_deploy_jobs()` | Per-environment deploy jobs for multi-env setups |

---

## Dependency Graph

```
ops.py       standalone — uses generators/github_workflow for generation
                          uses audit_helpers for activity logging
                          uses config/loader + detection for auto-detect

compose.py   standalone — uses generators/github_workflow for job builders
                          uses models/template for GeneratedFile
```

`ops.py` and `compose.py` are fully independent — they don't import
each other. Both delegate to `generators/github_workflow.py` for the
actual YAML generation, but each serves a different entry point:

- `ops.py` → called from CLI, routes, and other services for individual workflows
- `compose.py` → called from the wizard setup flow for full pipeline composition

---

## Backward Compatibility

The original files are now thin shims:

| Old path | Re-exports from |
|----------|----------------|
| `services/ci_ops.py` | `ci/ops.py` — all 6 public functions |
| `services/ci_compose.py` | `ci/compose.py` — `compose_ci_workflows` |

Two import patterns used by consumers:

```python
# Module-level import (routes_ci.py, routes_devops.py)
from src.core.services import ci_ops
ci_ops.ci_status(root)

# Function-level import (wizard/helpers.py, k8s_validate.py, CLI)
from src.core.services.ci_ops import ci_status
```

Both still work through the shims. New code should use:

```python
from src.core.services.ci import ci_status, compose_ci_workflows
```

---

## Consumers

| Consumer | What It Uses | Import Style |
|----------|-------------|--------------|
| `routes_ci.py` | `ci_status`, `ci_workflows`, `ci_coverage`, `generate_ci_workflow`, `generate_lint_workflow` | `from src.core.services import ci_ops` |
| `routes_devops.py` | `ci_status` | `from src.core.services import ci_ops` (lazy) |
| `routes_devops_apply.py` | `compose_ci_workflows` | `from src.core.services.ci_compose import ...` (lazy) |
| `wizard/helpers.py` | `ci_status` | `from src.core.services.ci_ops import ...` (lazy) |
| `k8s_validate.py` | `ci_status`, `ci_workflows` | `from src.core.services.ci_ops import ...` (top-level) |
| `metrics_ops.py` | `ci_status`, `ci_workflows` | `from src.core.services.ci_ops import ...` (lazy) |
| `ui/cli/ci.py` | `ci_status`, `ci_workflows`, `ci_coverage`, `generate_ci_workflow`, `generate_lint_workflow` | `from src.core.services.ci_ops import ...` (lazy) |

---

## API Endpoints

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/ci/status` | GET | Detected CI providers + workflow count |
| `/api/ci/workflows` | GET | Parsed workflow structure + issues |
| `/api/ci/coverage` | GET | Module CI coverage analysis |
| `/api/ci/generate` | POST | Generate CI test workflow |
| `/api/ci/generate-lint` | POST | Generate lint workflow |
