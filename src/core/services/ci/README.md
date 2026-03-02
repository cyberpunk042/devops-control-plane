# CI Domain

> **3 files · 1,163 lines · The CI/CD intelligence layer for the devops control plane.**
>
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

### Provider Registry

**Provider detection** checks 7 CI systems by looking for their
signature files and directories:

| Provider | ID | Detection Pattern | Type |
|----------|-----|------------------|------|
| GitHub Actions | `github_actions` | `.github/workflows/*.yml` | Directory scan |
| GitLab CI | `gitlab_ci` | `.gitlab-ci.yml`, `.gitlab-ci.yaml` | File check |
| Jenkins | `jenkins` | `Jenkinsfile` | File check |
| CircleCI | `circleci` | `.circleci/` | Directory scan |
| Travis CI | `travis` | `.travis.yml` | File check |
| Azure Pipelines | `azure_pipelines` | `azure-pipelines.yml`, `.yaml` | File check |
| Bitbucket Pipelines | `bitbucket_pipelines` | `bitbucket-pipelines.yml` | File check |

**Detection modes:**
- **File-based** providers (GitLab, Jenkins, Travis, Azure, Bitbucket):
  workflow_count = number of matching files found
- **Directory-based** providers (GitHub Actions, CircleCI):
  workflow_count = number of `.yml`/`.yaml` files in the directory

### Provider-Specific Parsing

Only GitHub Actions and GitLab CI get deep parsing. Others get
basic detection only:

| Provider | Parsing Depth | Triggers | Jobs | Steps | Issues |
|----------|--------------|----------|------|-------|--------|
| **GitHub Actions** | Full YAML parse | ✅ Extracted from `on:` | ✅ Job ID, name, runs-on, needs | ✅ Step count | ✅ Audited |
| **GitLab CI** | Full YAML parse | ✅ Default "push" | ✅ Top-level keys (non-reserved) | ✅ Script line count | ❌ No audit |
| **Jenkins** | Presence only | ✅ Default "push" | ❌ | ❌ | ❌ |
| **Others** | Not parsed | — | — | — | — |

### GitHub Actions Trigger Parsing

The `on:` key in GitHub Actions YAML has three valid formats.
All are handled:

```yaml
# Format 1: list
on: [push, pull_request]

# Format 2: dict (most common)
on:
  push:
    branches: [main]
  pull_request:

# Format 3: single string
on: push
```

**YAML quirk:** `on:` parses as the boolean `True` in Python's
yaml.safe_load. The parser checks both `data.get("on")` and
`data.get(True)` to handle this.

### Workflow Auditing

`_audit_github_workflow()` detects common issues in workflow files:

| Issue | Detection Rule | Example |
|-------|---------------|---------|
| No jobs | `jobs` block is empty or missing | Empty workflow file |
| No steps | Job has empty `steps` list | Placeholder job |
| Empty run command | `run:` with no value (after stripping comments) | Commented-out step |
| Unpinned actions | `uses: owner/action` without `@tag` or `@sha` | `uses: actions/checkout` (no `@v4`) |

**Note:** The auditor does NOT check for missing timeout, deprecated
syntax, or security issues beyond unpinned actions. These were
considered but excluded because they have high false-positive rates
for valid use cases.

### Coverage Analysis

**Coverage analysis** answers "which of my modules are covered by CI?"
by concatenating all CI file contents and searching for module paths,
module names, and stack-specific markers:

#### Coverage matching priority

```
For each module:
  1. Path match   — module.path appears literally in CI content
                    e.g., "src/web-app/" in workflow step
  
  2. Name match   — module.name appears literally in CI content
                    e.g., "web-app" in workflow step
  
  3. Stack match  — module.stack has a marker in CI content
                    e.g., stack="python" and "pytest" found
                    (first matching marker wins)
  
  4. No match     — module is uncovered
```

#### Stack CI Markers

| Stack | Markers (any match = covered) |
|-------|-------------------------------|
| `python` | `pytest`, `ruff`, `mypy`, `pip install`, `python -m` |
| `node` | `npm test`, `npm run`, `yarn test`, `jest`, `vitest` |
| `typescript` | `npm test`, `tsc`, `jest`, `vitest` |
| `go` | `go test`, `go vet`, `golangci-lint` |
| `rust` | `cargo test`, `cargo clippy`, `cargo check` |
| `java` | `mvn test`, `gradle test`, `maven`, `gradle` |
| `dotnet` | `dotnet test`, `dotnet build` |
| `elixir` | `mix test` |
| `ruby` | `bundle exec`, `rspec`, `rake test` |

**Prefix matching:** If `stack_name` starts with a known stack prefix
(e.g., `python-fastapi`), it matches the base stack markers.

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

### Strategy Comparison

| Feature | Unified | Split |
|---------|---------|-------|
| Files produced | 1 (`ci-cd.yml`) | 2-5 (per domain) |
| Job linking | `needs:` within file | `workflow_run` across files |
| GitHub UI | Single pipeline view | Separate workflow badges |
| Permissions | Shared across all jobs | Per-file permissions |
| Disable one step | Edit file | Delete file |
| Complexity | Lower | Higher |
| Default | ✅ | — |

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

### Compose Job Dependency Chain (Unified)

```
┌──────────────┐
│  test-python  │──┐
│  test-node    │──┤
└───────────────┘  │
                   ├── needs ──→ ┌──────────┐
                   │             │ terraform │ (parallel)
                   │             └──────────┘
                   │
                   └── needs ──→ ┌──────────┐
                                 │  docker   │
                                 └────┬─────┘
                                      │
                       ┌──────────────┼──────────────┐
                       │              │              │
                   (single)    (multi-env)    (multi-env)
                       │              │              │
                ┌──────▼──────┐ ┌────▼─────┐ ┌─────▼──────┐
                │   deploy     │ │ deploy-  │ │ deploy-    │
                │              │ │ staging  │ │ production │
                └──────┬──────┘ └────┬─────┘ └─────┬──────┘
                       │              │              │
                       └──────────────┼──────────────┘
                                      │
                               ┌──────▼──────┐
                               │ post-deploy  │
                               │ DNS + CDN    │
                               └─────────────┘
```

### Compose Job Builders

Each builder produces a YAML-serializable dict representing one job:

| Builder | Inputs | Output Key |
|---------|--------|-----------|
| `_build_test_jobs(stack_names)` | `["python", "node"]` | `test-python`, `test-node` |
| `_build_docker_job(services, needs)` | Docker service configs | `docker` |
| `_build_deploy_job(deploy_config, needs)` | K8s deploy config | `deploy` |
| `_build_terraform_job(tf_config, needs)` | Terraform config | `terraform` |
| `_build_post_deploy_steps(domains, cdn)` | Domain list + CDN provider | Additional steps on deploy job |
| `_build_env_deploy_jobs(config, envs, needs)` | Deploy config + env names | `deploy-staging`, `deploy-production` |

### Deploy Method Routing

The deploy job builder routes on `deploy_config.method`:

| Method | Generator | Config Keys Used |
|--------|-----------|-----------------|
| `kubectl` | `_kubectl_deploy_ci_job()` | `manifest_dir`, `namespace`, `app_name` |
| `skaffold` | `_skaffold_deploy_ci_job()` | `profile`, `default_repo`, `skaffold_file` |
| `helm` | `_helm_deploy_ci_job()` | `release_name`, `chart_path`, `namespace`, `values_file` |

### Multi-Environment Deploy

When `wizard_state.environments` contains multiple names, the compose
engine generates **per-environment deploy jobs**, each targeting a
different environment:

```
                  docker job
                      │
          ┌───────────┼───────────┐
          ▼           ▼           ▼
    deploy-dev  deploy-staging  deploy-prod
        │           │               │
        └───────────┼───────────────┘
                    ▼
             post-deploy
        (DNS verify + CDN purge)
```

Each environment deploy job:
- Uses `environment:` to lock to GitHub deployment environments
- Applies to the correct namespace (`kubectl --namespace <env>`)
- For Helm: uses per-environment values files (`values-<env>.yaml`)
- For Skaffold: uses the environment name as the profile

The compose layer doesn't generate YAML directly — it delegates to
the job builders in `generators/github_workflow.py` (`_resolve_job`,
`_docker_ci_job`, `_kubectl_deploy_ci_job`, etc.) and orchestrates
them into the right structure.

---

## Key Data Shapes

### ci_status response

```python
{
    "providers": [
        {"id": "github_actions", "name": "GitHub Actions", "workflows": 3},
        {"id": "gitlab_ci", "name": "GitLab CI", "workflows": 1},
    ],
    "total_workflows": 4,
    "has_ci": True,
    "missing_tools": [],      # from check_required_tools(["git", "gh"])
}
```

### ci_workflows response

```python
{
    "workflows": [
        {
            "file": ".github/workflows/ci.yml",
            "provider": "github_actions",
            "name": "CI",
            "triggers": ["push", "pull_request"],
            "jobs": [
                {
                    "id": "test",
                    "name": "Test Suite",
                    "steps_count": 5,
                    "runs_on": "ubuntu-latest",
                    "needs": [],
                },
                {
                    "id": "lint",
                    "name": "Lint",
                    "steps_count": 3,
                    "runs_on": "ubuntu-latest",
                    "needs": [],
                },
            ],
            "issues": ["Job 'deploy', step 3: action 'aws-actions/configure-credentials' not pinned to version"],
        },
        {
            "file": ".gitlab-ci.yml",
            "provider": "gitlab_ci",
            "name": ".gitlab-ci",
            "triggers": ["push"],
            "jobs": [
                {
                    "id": "test",
                    "name": "test",
                    "stage": "test",
                    "steps_count": 4,        # script lines
                },
            ],
            "issues": [],
        },
    ],
}
```

### ci_coverage response

```python
{
    "covered": ["web-app", "auth-service", "cli"],
    "uncovered": ["api-gateway", "worker"],
    "coverage_pct": 60.0,
    "details": {
        "web-app": {
            "covered": True,
            "reason": "Path 'src/web-app/' referenced in CI",
        },
        "auth-service": {
            "covered": True,
            "reason": "Module 'auth-service' referenced in CI",
        },
        "cli": {
            "covered": True,
            "reason": "Stack 'python' has CI coverage via pytest",
        },
        "api-gateway": {
            "covered": False,
            "reason": "Not referenced in any CI workflow",
        },
        "worker": {
            "covered": False,
            "reason": "Not referenced in any CI workflow",
        },
    },
}
```

### generate_ci_workflow response

```python
# Success
{
    "ok": True,
    "file": {
        "path": ".github/workflows/ci.yml",
        "content": "name: CI\non:\n  push:\n    branches: [main]\n...",
        "overwrite": False,
        "reason": "CI test workflow for python",
    },
}

# Failure
{
    "error": "No CI template available for detected stacks",
}
```

### generate_lint_workflow response

```python
# Success
{
    "ok": True,
    "file": {
        "path": ".github/workflows/lint.yml",
        "content": "name: Lint\non:\n  push:\n...",
        "overwrite": False,
        "reason": "Lint workflow for python",
    },
}

# Failure
{
    "error": "No lint template for detected stacks",
}
```

### generate_terraform_workflow response

```python
# Success
{
    "ok": True,
    "file": {
        "path": ".github/workflows/terraform.yml",
        "content": "name: Terraform\non:\n  push:\n...",
        "overwrite": False,
        "reason": "Terraform CI for aws",
    },
}

# Failure
{
    "error": "Failed to generate Terraform CI workflow",
}
```

### compose_ci_workflows response (unified)

```python
[
    GeneratedFile(
        path=".github/workflows/ci-cd.yml",
        content="# Generated by DevOps Control Plane\nname: MyProject CI/CD\n...",
        overwrite=False,
        reason="Unified CI/CD pipeline",
    ),
]
```

### compose_ci_workflows response (split)

```python
[
    GeneratedFile(
        path=".github/workflows/ci.yml",
        content="...",
        overwrite=False,
        reason="CI test workflow for 2 stack(s)",
    ),
    GeneratedFile(
        path=".github/workflows/docker.yml",
        content="...",
        overwrite=False,
        reason="Docker build workflow for 1 service(s)",
    ),
    GeneratedFile(
        path=".github/workflows/deploy.yml",
        content="...",
        overwrite=False,
        reason="K8s deploy via kubectl",
    ),
    GeneratedFile(
        path=".github/workflows/terraform.yml",
        content="...",
        overwrite=False,
        reason="Terraform CI for aws",
    ),
]
```

---

## Architecture

```
              CLI (ui/cli/ci.py)
              Routes (routes/ci/)
                     │
                     │ imports
                     │
          ┌──────────▼──────────┐
          │  ci_ops.py           │  backward-compat shim
          │  ci_compose.py       │  → imports from ci/
          └──────────┬──────────┘
                     │
          ┌──────────▼──────────────────────────┐
          │  ci/__init__.py                       │
          │  Public API — re-exports all symbols  │
          └────┬──────────────────┬──────────────┘
               │                  │
               ▼                  ▼
           ops.py            compose.py
           (detect,          (multi-domain
            parse,            pipeline
            generate)         orchestration)
               │                  │
               │                  │
               ▼                  ▼
      generators/           generators/
      github_workflow.py    github_workflow.py
      (individual jobs)     (job builders +
                             resolvers)
```

### Dependency Rules

| Rule | Detail |
|------|--------|
| `ops.py` and `compose.py` are independent | They don't import each other |
| Both delegate to `generators/github_workflow.py` | Shared job generation logic |
| `ops.py` uses lazy imports for config/detection | Inside function bodies |
| `compose.py` imports generators at module level | Performance — called once per compose |
| `ops.py` audits via `make_auditor("ci")` | Activity trail for generation events |

---

## File Map

```
ci/
├── __init__.py       Public API re-exports (27 lines)
├── ops.py            Detection, parsing, coverage, generation (592 lines)
├── compose.py        Multi-domain pipeline composition (544 lines)
└── README.md         This file
```

---

## Per-File Documentation

### `__init__.py` — Public API (27 lines, 7 exports)

| Export | From |
|--------|------|
| `ci_status`, `ci_workflows`, `ci_coverage` | `ops.py` |
| `generate_ci_workflow`, `generate_lint_workflow`, `generate_terraform_workflow` | `ops.py` |
| `compose_ci_workflows` | `compose.py` |

### `ops.py` — Detection + Parsing + Generation (592 lines)

Three concerns in one file, organized by section headers:

| Section | Functions | What They Do |
|---------|-----------|-------------|
| **Auto-detect** | `_auto_detect_modules(root)` | Load project config → detect modules |
| **Auto-detect** | `_auto_detect_stack_names(root)` | Modules → unique stack names + project name |
| **Detect** | `ci_status(root)` | Scan 7 providers, count workflows, check required tools |
| **Observe** | `ci_workflows(root)` | Parse all workflow files across all providers |
| **Observe** | `_parse_github_workflow(path, root)` | Parse single GitHub Actions YAML → structured dict |
| **Observe** | `_parse_gitlab_ci(path, root)` | Parse GitLab CI YAML → structured dict |
| **Observe** | `_audit_github_workflow(data, path)` | Detect issues in GitHub Actions workflow |
| **Observe** | `_parse_yaml_safe(path)` | Safe YAML loading with error handling |
| **Coverage** | `ci_coverage(root, modules?)` | Analyze module CI coverage |
| **Coverage** | `_gather_ci_content(root)` | Concatenate all CI file contents |
| **Coverage** | `_check_stack_coverage(stack, content)` | Match stack markers in CI content |
| **Generate** | `generate_ci_workflow(root, stacks?, name?)` | Generate test workflow from stacks |
| **Generate** | `generate_lint_workflow(root, stacks?)` | Generate lint workflow from stacks |
| **Generate** | `generate_terraform_workflow(config, name?)` | Generate Terraform plan/apply workflow |

**Module-level objects:**

| Object | Type | Purpose |
|--------|------|---------|
| `_CI_PROVIDERS` | `dict[str, dict]` | Provider registry with detection patterns |
| `_STACK_CI_MARKERS` | `dict[str, list[str]]` | Stack → CI tool marker mappings |
| `_audit` | `Auditor` | Activity log writer for generation events |

### `compose.py` — Pipeline Composition (544 lines)

| Function | What It Does |
|----------|-------------|
| `compose_ci_workflows(wizard_state, strategy, project_name)` | **Public API** — dispatch to unified or split strategy |
| `_compose_unified(wizard_state, project_name)` | Single ci-cd.yml with all jobs chained via `needs` |
| `_compose_split(wizard_state, project_name)` | Separate files linked via `workflow_run` triggers |
| `_build_test_jobs(stack_names)` | Resolve stack names → test job YAML blocks |
| `_build_docker_job(docker_services, needs)` | Docker build/push job from service configs |
| `_build_deploy_job(deploy_config, needs)` | K8s deploy job (kubectl / skaffold / helm) |
| `_build_terraform_job(terraform_config, needs)` | Terraform plan/apply job |
| `_build_post_deploy_steps(domains, cdn_provider)` | DNS verify + CDN purge post-deploy |
| `_build_env_deploy_jobs(deploy_config, environments, needs)` | Per-environment deploy jobs for multi-env setups |

**`compose_ci_workflows()` signature:**
```python
compose_ci_workflows(
    wizard_state: dict,
    *,
    strategy: str = "unified",     # or "split"
    project_name: str = "",
) -> list[GeneratedFile]
```

**Wizard state keys consumed:**

| Key | Type | Used By | Required |
|-----|------|---------|----------|
| `stack_names` | `list[str]` | Test job builder | No (skips test jobs) |
| `docker_services` | `list[dict]` | Docker job builder | No |
| `deploy_config` | `dict` | Deploy job builder | No |
| `deploy_config.method` | `str` | `kubectl` / `skaffold` / `helm` routing | If deploy_config present |
| `terraform_config` | `dict` | Terraform job builder | No |
| `domains` | `list[str]` | Post-deploy DNS verify | No |
| `cdn_provider` | `str` | Post-deploy CDN purge | No |
| `environments` | `list[str]` | Multi-env deploy fan-out | No |

**Module-level imports:**

| Import | Purpose |
|--------|---------|
| `GeneratedFile` (models/template) | Return type for composed workflows |
| `_resolve_job` (generators) | Stack → test job template resolver |
| `_docker_ci_job` (generators) | Docker build/push job template |
| `_kubectl_deploy_ci_job` (generators) | kubectl deploy template |
| `_skaffold_deploy_ci_job` (generators) | Skaffold deploy template |
| `_helm_deploy_ci_job` (generators) | Helm deploy template |
| `_terraform_ci_job` (generators) | Terraform plan/apply template |
| `_dns_verify_ci_step` (generators) | DNS verification step |
| `_cdn_purge_ci_step` (generators) | CDN cache purge step |
| `_kubeconfig_step` (generators) | Kubeconfig setup step |
| `_CDN_PURGE_COMMANDS` (generators) | CDN provider → purge command map |

---

## Dependency Graph

```
ops.py                    compose.py
  │                          │
  ├── yaml (parse)           ├── GeneratedFile (model)
  ├── re (patterns)          └── generators/github_workflow
  ├── pathlib                    ├── _resolve_job
  │                              ├── _docker_ci_job
  ├── audit_helpers              ├── _kubectl_deploy_ci_job
  │   └── make_auditor           ├── _skaffold_deploy_ci_job
  │                              ├── _helm_deploy_ci_job
  ├── generators/                ├── _terraform_ci_job
  │   github_workflow            ├── _dns_verify_ci_step
  │   ├── generate_ci            ├── _cdn_purge_ci_step
  │   ├── generate_lint          ├── _kubeconfig_step
  │   └── generate_terraform_ci  └── _CDN_PURGE_COMMANDS
  │
  ├── config/loader (lazy)
  ├── config/stack_loader (lazy)
  ├── detection (lazy)
  └── tool_requirements (lazy)
```

`ops.py` and `compose.py` are fully independent — they don't import
each other. Both delegate to `generators/github_workflow.py` for the
actual YAML generation, but each serves a different entry point:

- `ops.py` → called from CLI, routes, and other services for individual workflows
- `compose.py` → called from the wizard setup flow for full pipeline composition

---

## Error Handling Patterns

### ops.py — Observe functions

```python
# YAML parse failure → returns partial dict with issues
{
    "file": "ci.yml",
    "provider": "github_actions",
    "name": "ci",
    "triggers": [],
    "jobs": [],
    "issues": ["Failed to parse YAML"],
}
```

### ops.py — Generate functions

```python
# Success
{"ok": True, "file": {...}}

# Failure (no template available)
{"error": "No CI template available for detected stacks"}
```

### compose.py — Empty state

```python
# No wizard state keys set → returns empty list
[]
```

### ops.py — Coverage with no modules

```python
# No modules detected → returns zero coverage without error
{
    "covered": [],
    "uncovered": [],
    "coverage_pct": 0.0,
    "details": {},
}
```

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
| `routes/ci/status.py` | `ci_status`, `ci_workflows`, `ci_coverage` | `from src.core.services import ci_ops` |
| `routes/ci/generate.py` | `generate_ci_workflow`, `generate_lint_workflow` | `from src.core.services import ci_ops` |
| `routes/devops/__init__.py` | `ci_status` | `from src.core.services import ci_ops` (lazy) |
| `routes/devops/apply.py` | `compose_ci_workflows` | `from src.core.services.ci_compose import ...` (lazy) |
| `wizard/helpers.py` | `ci_status` | `from src.core.services.ci_ops import ...` (lazy) |
| `k8s/validate_cross_domain.py` | `ci_status`, `ci_workflows` | `from src.core.services.ci_ops import ...` (top-level) |
| `metrics/ops.py` | `ci_status`, `ci_workflows` | `from src.core.services.ci_ops import ...` (lazy) |
| `ui/cli/ci/__init__.py` | `ci_status`, `ci_workflows`, `ci_coverage`, `generate_ci_workflow`, `generate_lint_workflow` | `from src.core.services.ci_ops import ...` (lazy) |

---

## API Endpoints

| Route | Method | Purpose |
|-------|--------|---------|
| `/ci/status` | GET | Detected CI providers + workflow count |
| `/ci/workflows` | GET | Parsed workflow structure + issues |
| `/ci/coverage` | GET | Module CI coverage analysis |
| `/ci/generate/ci` | POST | Generate CI test workflow |
| `/ci/generate/lint` | POST | Generate lint workflow |

---

## Output Format — GeneratedFile

Both `ops.py` generators and `compose.py` return `GeneratedFile`
objects (from `models/template.py`):

```python
GeneratedFile(
    path=".github/workflows/ci-cd.yml",
    content="name: CI/CD\non:\n  push:\n    branches: [main]\n...",
    overwrite=False,
    reason="Unified pipeline: test → build → deploy",
)
```

**Compose unified output example:**
```python
[
    GeneratedFile(
        path=".github/workflows/ci-cd.yml",
        content="...",      # single file, all jobs
        overwrite=False,
        reason="Test + Docker + Deploy pipeline",
    ),
]
```

**Compose split output example:**
```python
[
    GeneratedFile(path=".github/workflows/ci.yml", ...),
    GeneratedFile(path=".github/workflows/docker.yml", ...),
    GeneratedFile(path=".github/workflows/deploy.yml", ...),
    GeneratedFile(path=".github/workflows/terraform.yml", ...),
]
```

---

## Generated Workflow Structure (Unified)

A complete unified workflow for a Python + Docker + K8s project:

```yaml
# Generated by DevOps Control Plane
name: MyProject CI/CD

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

permissions:
  contents: read
  packages: write

jobs:
  test-python:            # ← from _build_test_jobs
    name: Test (Python)
    runs-on: ubuntu-latest
    steps: [...]

  docker:                 # ← from _build_docker_job
    needs: [test-python]  # ← auto-chained
    name: Build & Push
    runs-on: ubuntu-latest
    steps: [...]

  deploy:                 # ← from _build_deploy_job
    needs: [docker]       # ← auto-chained
    name: Deploy
    runs-on: ubuntu-latest
    steps: [...]

  post-deploy:            # ← from _build_post_deploy_steps
    needs: [deploy]       # ← auto-chained
    name: Post-Deploy Checks
    runs-on: ubuntu-latest
    steps: [...]
```

---

## Audit Trail

All generation events are logged via `make_auditor("ci")`:

| Event | Title | Detail |
|-------|-------|--------|
| CI workflow generated | `"⚙️ CI Workflow Generated"` | `{stacks, project}` |
| Lint workflow generated | `"⚙️ Lint Workflow Generated"` | `{stacks}` |
| Terraform CI generated | `"⚙️ Terraform CI Workflow Generated"` | `{provider, project}` |

The compose layer does **not** audit individually — auditing happens
when the wizard writes files via `write_generated_file()`.

---

## Advanced Feature Showcase

### 1. YAML `on:` → Boolean `True` Quirk (ops.py)

Python's `yaml.safe_load` parses the YAML key `on:` as the boolean
`True`, not the string `"on"`. This is a well-known YAML 1.1 quirk
that would silently break trigger parsing for every workflow file.
The parser defensively checks both:

```python
# ops.py — _parse_github_workflow(), line 232
on_block = data.get("on", data.get(True, {}))  # YAML parses `on:` as True

if isinstance(on_block, list):       # on: [push, pull_request]
    triggers = on_block
elif isinstance(on_block, dict):     # on: {push: {branches: [main]}}
    triggers = list(on_block.keys())
elif isinstance(on_block, str):      # on: push
    triggers = [on_block]
```

Three valid YAML formats → three code paths, plus the `True` fallback.
Without this, every GitHub Actions workflow would report zero triggers.

---

### 2. Automatic Dependency Chaining (compose.py)

The unified compose strategy builds jobs incrementally and chains them
via `needs:` automatically. The `last_jobs` tracker propagates
dependencies through the pipeline:

```python
# compose.py — _compose_unified(), lines 208-245
job_blocks: list[str] = []
last_jobs: list[str] = []

# Test jobs → set last_jobs to ["test-python", "test-node"]
test_blocks = _build_test_jobs(stack_names)
if test_blocks:
    job_blocks.extend(test_blocks)
    for block in test_blocks:
        for line in block.splitlines():
            stripped = line.rstrip()
            if stripped.startswith("  ") and stripped.endswith(":") \
               and not stripped.startswith("    "):
                last_jobs.append(stripped.strip().rstrip(":"))
                break

# Docker job → receives needs from last_jobs
build_needs = last_jobs[:] if last_jobs else ["test"]
docker_block = _build_docker_job(docker_services, build_needs)
if docker_block:
    # Now last_jobs becomes ["docker"] for the next stage
    last_jobs = ["docker"]
```

No hardcoded dependency chain. The pipeline shape adapts to which
domains are enabled — skip Docker, and deploy chains directly
to tests. Add Terraform, and it runs in parallel with Docker.

---

### 3. Multi-Environment Deploy Fan-Out (compose.py)

When the wizard configures multiple environments (`staging`, `production`),
the compose engine fans out into per-environment deploy jobs,
each targeting different namespaces and values files:

```python
# compose.py — _build_env_deploy_jobs(), lines 145-187
for env_name in environments:
    if method == "kubectl":
        job = _kubectl_deploy_ci_job(
            namespace=deploy_config.get("namespace", env_name),  # ← env as namespace
            ...
        )
    elif method == "helm":
        job = _helm_deploy_ci_job(
            namespace=deploy_config.get("namespace", env_name),
            values_file=f"charts/{release}/values-{env_name}.yaml",  # ← per-env values
            ...
        )
    elif method == "skaffold":
        job = _skaffold_deploy_ci_job(
            profile=env_name,  # ← env as Skaffold profile
            ...
        )
    
    # Make job name unique: deploy → deploy-staging, deploy-production
    job = job.replace("  deploy:", f"  deploy-{env_name}:", 1)
```

One `deploy_config` + N environments = N parallel deploy jobs, each with
the right namespace, values file, or profile. The post-deploy job
then waits for ALL of them: `needs: [deploy-staging, deploy-production]`.

---

### 4. Workflow Auditing — 4 Detection Rules (ops.py)

The auditor scans GitHub Actions workflows for common issues.
Each rule targets a specific anti-pattern:

```python
# ops.py — _audit_github_workflow(), lines 269-309
issues: list[str] = []

# Rule 1: No jobs defined
if not jobs_block:
    issues.append("No jobs defined")

# Rule 2: Job has no steps
if not isinstance(steps, list) or not steps:
    issues.append(f"Job '{job_id}' has no steps")

# Rule 3: Empty run command (after stripping comments)
lines = [ln for ln in stripped.splitlines()
         if ln.strip() and not ln.strip().startswith("#")]
if not lines and "run" in step:
    issues.append(f"Job '{job_id}', step {i + 1} ... empty run command")

# Rule 4: Unpinned actions (no @tag or @sha)
uses = step.get("uses", "")
if isinstance(uses, str) and uses and "@" not in uses:
    issues.append(f"... action '{uses}' not pinned to version")
```

The empty-run-command rule strips comments before checking — a step
with only `# TODO` is flagged as empty. The unpinned-action rule
catches `uses: actions/checkout` (should be `@v4`).

---

### 5. Split Strategy with `workflow_run` Linking (compose.py)

The split strategy produces separate files that trigger each other
via GitHub's `workflow_run` event. This creates cross-file DAG
dependencies without sharing a `needs:` graph:

```python
# compose.py — _compose_split(), lines 370-410
# Docker workflow triggers when CI completes
if trigger_on:
    on_block = f"""\
on:
  workflow_run:
    workflows: ["{ci_wf_name}"]   # ← "MyProject CI"
    types: [completed]
    branches: [main]
"""
# Deploy workflow triggers when Docker completes
if trigger_from:
    on_block = f"""\
on:
  workflow_run:
    workflows: ["{docker_wf_name}"]  # ← "MyProject Docker"
    types: [completed]
    branches: [main]
"""
```

Each file is self-contained — you can delete `docker.yml` and the
deploy workflow simply never triggers. The Terraform workflow is
fully independent (path-filtered, runs on terraform changes only).

---

### 6. Coverage Prefix Matching (ops.py)

Stack detection supports composite stack names like `python-fastapi`
by falling back to prefix matching against known stacks:

```python
# ops.py — _check_stack_coverage(), lines 473-488
def _check_stack_coverage(stack_name: str, ci_content: str) -> str | None:
    # Exact match first
    markers = _STACK_CI_MARKERS.get(stack_name, [])
    for marker in markers:
        if marker in ci_content:
            return marker

    # Prefix match — "python-fastapi" matches "python" markers
    for prefix, markers in _STACK_CI_MARKERS.items():
        if stack_name.startswith(prefix + "-") or stack_name.startswith(prefix):
            for marker in markers:
                if marker in ci_content:
                    return marker
    return None
```

A project with stack `python-fastapi` won't find `python-fastapi`
in the markers dict, but it WILL match `python` via prefix and check
for `pytest`, `ruff`, `mypy`, etc. No configuration needed —
composite stacks inherit their base coverage markers automatically.

---

## Design Decisions

### Why ops.py has three concerns?

Detection, parsing, and generation all operate on the same data
(CI workflow files) and share helpers (`_parse_yaml_safe`,
`_auto_detect_stack_names`). Splitting into three files would
create three 200-line modules with shared imports — not worth
the indirection for a domain this size.

### Why compose.py is separate from ops.py?

`compose.py` serves a fundamentally different use case: it takes
wizard state (a UI concept) and produces multi-file pipeline output.
`ops.py` observes and generates individual files. Different inputs,
different outputs, zero shared state. They also delegate to different
parts of `generators/github_workflow.py`.

### Why two compose strategies?

Some teams want one file (simple to understand, single pipeline
view). Others want separate files (separate badges, separate
permissions, easier to disable). The wizard lets the user choose.
Both strategies produce identical CI behavior — only the file
structure differs.

### Why text-search for coverage instead of YAML parsing?

CI coverage doesn't need structured data. It needs to answer
"does the word 'pytest' appear anywhere in any CI file?" Text
concatenation + `in` operator is 100x faster than parsing every
YAML file and walking the AST. False positives are acceptable
because coverage is advisory, not enforced.

### Why only GitHub Actions and GitLab CI get deep parsing?

These are the two providers where the control plane can take
meaningful action: generating workflows, auditing steps, checking
trigger coverage. For Jenkins, CircleCI, Travis, etc., detection
is sufficient — the control plane can tell you "you have Jenkins"
but can't generate a Jenkinsfile or audit pipeline stages. Investing
in parsers for limited-use providers would violate the 80/20 rule.

### Why does compose.py import generators at module level?

Unlike `ops.py` (which lazy-imports to avoid circular deps),
`compose.py` is only called from the wizard setup flow. It's a
terminal consumer — nothing imports from it except `__init__.py`.
Module-level imports are safe and avoid the performance cost of
repeated lazy imports during the compose process.

### Why does `_build_docker_job` use string replacement for `needs`?

The job builders in `generators/github_workflow.py` return YAML
strings (not dicts) with placeholder `needs` values. Rather than
parsing the YAML, modifying the dict, and re-serializing (which
would lose formatting), the compose layer does a simple string
replace: `needs: [test]` → `needs: [test-python, test-node]`.
This preserves the generator's formatting and avoids a YAML
round-trip.
