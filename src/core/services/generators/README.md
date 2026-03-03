# Generators

> **11 files. ~1,975 lines. Config file generators for DevOps CI/CD pipelines.**
>
> Produces Dockerfiles, docker-compose.yml, GitHub Actions workflows (CI, Docker,
> K8s deploy, Terraform, post-deploy, lint), and .dockerignore from detected
> project context. Every generator returns `GeneratedFile` instances with
> suggested paths, content, and human-readable reasons.

---

## How It Works

### Mental Model

Generators are **pure template functions**. They take structured input
(stack names, service configs, deploy settings) and return strings of
valid YAML or Dockerfile content. No side effects. No file I/O. No
subprocess calls. The generator never writes files — it returns a
`GeneratedFile` proposal that the caller decides to write.

### Call Flow

```
┌─────────────────────────────────────────────────────────────────┐
│  Caller (wizard/setup_ci.py, ci/ops.py, docker/generate.py)    │
│                                                                 │
│  1. Detect stacks, services, deploy method, etc.                │
│  2. Call generator with structured config dict                  │
│  3. Receive GeneratedFile(path, content, overwrite, reason)     │
│  4. Write file if user approves                                 │
└────────┬────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Generator Module                              │
│                                                                 │
│  1. Resolve config → template/job blocks                        │
│  2. Assemble YAML header (name, on, permissions)                │
│  3. Concatenate job blocks into full workflow                   │
│  4. Return GeneratedFile with path + content                   │
└─────────────────────────────────────────────────────────────────┘
```

### Workflow Generation Pipeline

For GitHub Actions workflows, the generation follows a two-tier pattern:

```
                      ┌──────────────────────┐
                      │  ci/compose.py       │  Orchestrator
                      │  (unified or split)   │
                      └──────┬───────────────┘
                             │ imports job block builders
         ┌───────────┬───────┼───────┬────────────┬────────────┐
         ▼           ▼       ▼       ▼            ▼            ▼
    ┌─────────┐ ┌────────┐ ┌────┐ ┌──────────┐ ┌──────────┐ ┌──────┐
    │ci_jobs  │ │docker  │ │k8s │ │terraform │ │post_dep  │ │lint  │
    │ 6 lang  │ │ build  │ │3dep│ │ 3 cloud  │ │dns + cdn │ │2 lang│
    │ jobs    │ │ push   │ │meth│ │ provid.  │ │ purge    │ │steps │
    └────┬────┘ └───┬────┘ └──┬─┘ └─────┬────┘ └────┬─────┘ └──┬───┘
         │          │         │          │           │           │
         ▼          ▼         ▼          ▼           ▼           ▼
    ┌─────────────────────────────────────────────────────────────────┐
    │  Each returns a YAML fragment string (job block or step block)  │
    │  Orchestrator concatenates them with the right:                 │
    │    - needs: [...] dependency chains                             │
    │    - workflow_run triggers (split strategy)                     │
    │    - permissions blocks                                        │
    └─────────────────────────────────────────────────────────────────┘
```

**Two orchestration strategies:**

| Strategy | Output | Job Linking |
|----------|--------|-------------|
| `"unified"` | Single `ci-cd.yml` | `needs:` arrays between jobs |
| `"split"` | Separate `ci.yml`, `docker.yml`, `deploy.yml`, etc. | `workflow_run` triggers between files |

### Docker Generation Pipeline

Docker generators are simpler — direct call, no orchestrator:

```
docker/generate.py
    │
    ├── generate_dockerfile(project_root, stack_name)
    │       └── dockerfile.py._resolve_template(stack_name) → template string
    │
    ├── generate_dockerignore(project_root, stack_names)
    │       └── dockerignore.py → base + per-stack patterns
    │
    └── generate_compose(project_root, modules)
            └── compose.py._resolve_port(stack_name) → port mapping
```

### Stack Resolution Pattern

All resolvers follow the same two-step pattern:

```
1. Exact match:    _REGISTRY["python"]  → _python_ci_job
2. Prefix match:   "python-flask" starts with "python" → _python_ci_job
```

This applies to `_resolve_job` (CI), `_resolve_template` (Dockerfile),
`_resolve_port` (compose), and `_LINT_STEPS` (lint). The pattern allows
framework variants (e.g. `python-flask`, `node-express`, `go-gin`) to
automatically inherit from their base stack.

---

## Directory Layout

```
generators/
├── __init__.py              6 lines   — package docstring only
├── dockerfile.py          510 lines   — Dockerfile templates for 13 stacks
├── dockerignore.py        166 lines   — .dockerignore with stack-specific patterns
├── compose.py             105 lines   — docker-compose.yml from detected modules
├── github_workflow.py     127 lines   — backward-compat shim + generate_ci()
├── wf_ci_jobs.py          218 lines   — per-language CI job YAML generators
├── wf_docker.py           205 lines   — Docker build/push CI job
├── wf_k8s_deploy.py       213 lines   — kubectl/skaffold/helm deploy jobs
├── wf_terraform.py        145 lines   — Terraform init→plan→apply CI job
├── wf_post_deploy.py      157 lines   — DNS verify + CDN purge post-deploy
└── wf_lint.py             123 lines   — lightweight lint-only workflow
```

**Total:** ~1,975 lines across 11 files.

---

## Module Details

### `dockerfile.py` — Dockerfile Templates (510 lines)

Multi-stage Dockerfile templates for 13 technology stacks. Every template
follows production best practices: multi-stage builds, non-root users,
dependency caching, and minimal runtime images.

#### Supported Stacks

| Stack | Builder Image | Runtime Image | Features |
|-------|-------------|--------------|----------|
| `python` | `python:3.12-slim` | same | pip cache, non-root user (`app:1000`) |
| `node` | `node:20-alpine` | `node:20-alpine` | npm ci, non-root, multi-stage |
| `typescript` | `node:20-alpine` | `node:20-alpine` | npm ci + tsc build, multi-stage |
| `go` | `golang:1.22-alpine` | `alpine:3.19` | `CGO_ENABLED=0`, static binary |
| `rust` | `rust:1.76` | `debian:bookworm-slim` | `cargo build --release`, multi-stage |
| `java-maven` | `maven:3.9-eclipse-temurin-21` | `eclipse-temurin:21-jre` | mvn package, JRE runtime |
| `java-gradle` | `gradle:8-jdk21` | `eclipse-temurin:21-jre` | gradlew build, JRE runtime |
| `dotnet` | `mcr.microsoft.com/dotnet/sdk:8.0` | `aspnet:8.0` | dotnet publish, ASP.NET runtime |
| `elixir` | `elixir:1.16-alpine` | `alpine:3.19` | mix release |
| `ruby` | `ruby:3.3-slim` | same | bundle install, non-root |
| `c` | `gcc:13` | `alpine:3.19` | cmake/make auto-detect, static binary |
| `cpp` | `gcc:13` | `alpine:3.19` | cmake/make auto-detect, static binary |
| `php` | PHP-FPM base | same | composer install |

**Stack aliases:** `java-micronaut` → `java-maven` (Micronaut defaults to Maven).

#### Public API

| Function | Signature | Purpose |
|----------|-----------|---------|
| `generate_dockerfile` | `(project_root, stack_name, *, output_path="Dockerfile", base_image=None) → GeneratedFile?` | Generate Dockerfile for a stack. Returns `None` if no template matches. |
| `supported_stacks` | `() → list[str]` | Return all 13+ stack names with templates available |

#### Internal

| Symbol | Purpose |
|--------|---------|
| `_STACK_TEMPLATES` | `dict[str, str]` — maps stack name → Dockerfile template string |
| `_resolve_template(stack_name)` | Exact match → prefix match for Dockerfile template |
| `_PYTHON_DOCKERFILE`, `_NODE_DOCKERFILE`, ... | Individual template string constants |

---

### `dockerignore.py` — .dockerignore Generator (166 lines)

Combines a base exclusion set (version control, IDE, OS, CI files) with
stack-specific patterns. The base patterns alone handle the most common
exclusions; stack patterns add language-specific artifact directories.

#### Base Patterns

`.git`, `.gitignore`, `.vscode`, `.idea`, `*.swp`, `.DS_Store`,
`docker-compose*.yml`, `Dockerfile*`, `.dockerignore`, `.github`,
`.gitlab-ci.yml`, `Jenkinsfile`, `docs/`, `*.md`, `LICENSE`.

#### Stack-Specific Patterns

| Stack | Key Excludes |
|-------|-------------|
| `python` | `__pycache__`, `.venv`, `venv`, `*.egg-info`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`, `dist`, `build`, `.tox`, `.coverage` |
| `node` | `node_modules`, `npm-debug.log*`, `.npm`, `.yarn`, `dist`, `coverage` |
| `typescript` | `node_modules`, `dist`, `*.js.map`, `tsconfig.tsbuildinfo` |
| `go` | `vendor/`, `*.test`, `*.out` |
| `rust` | `target/`, `Cargo.lock` |
| `java` | `target/`, `build/`, `*.class`, `*.jar`, `*.war`, `.gradle` |
| `dotnet` | `bin/`, `obj/`, `*.user`, `*.suo` |
| `elixir` | `_build/`, `deps/`, `*.ez` |
| `ruby` | `.bundle`, `vendor/bundle`, `log/`, `tmp/` |

#### Public API

| Function | Signature | Purpose |
|----------|-----------|---------|
| `generate_dockerignore` | `(project_root, stack_names) → GeneratedFile` | Always returns a file (base patterns at minimum). Deduplicates via prefix matching. |

---

### `compose.py` — docker-compose.yml Generator (105 lines)

Produces a `docker-compose.yml` from detected modules. Each module becomes
a service with auto-detected port mapping and build context.

#### Port Resolution

| Stack | Default Port |
|-------|-------------|
| `python` | 8000 |
| `node`, `typescript`, `ruby` | 3000 |
| `go`, `rust`, `java`, `dotnet` | 8080 |
| `elixir` | 4000 |
| `static-site` | 80 |

Unrecognized stacks default to 8080.

#### Service Block Generation

For each module with a `name`, `path`, and `stack_name`:
- Checks if module has its own `Dockerfile` → uses module dir as context
- Otherwise → uses project root as context
- Adds `restart: unless-stopped` and `NODE_ENV=production`
- Skips `markdown` and `docs` domain modules

#### Public API

| Function | Signature | Purpose |
|----------|-----------|---------|
| `generate_compose` | `(project_root, modules, *, project_name="") → GeneratedFile?` | Returns `None` if no qualifying modules |

#### Internal

| Function | Purpose |
|----------|---------|
| `_resolve_port(stack_name)` | Exact match → prefix match for default port |

---

### `wf_ci_jobs.py` — CI Job Generators (218 lines)

Per-language GitHub Actions test/build job YAML blocks. Each function
returns a complete job YAML fragment ready to be inserted under `jobs:`.

#### Job Generators

| Function | Language | Matrix | Steps |
|----------|----------|--------|-------|
| `_python_ci_job(version_matrix)` | Python 3.11, 3.12 | ✅ | checkout → setup-python → pip install → ruff → mypy → pytest |
| `_node_ci_job(version_matrix)` | Node 18, 20 | ✅ | checkout → setup-node → npm ci → lint → test → build |
| `_go_ci_job(version_matrix)` | Go 1.21, 1.22 | ✅ | checkout → setup-go → vet → test -race → build |
| `_rust_ci_job()` | Rust stable | ❌ | checkout → toolchain → cargo cache → check → clippy → fmt → test |
| `_java_maven_ci_job()` | Java 21 (Maven) | ❌ | checkout → setup-java → mvn verify |
| `_java_gradle_ci_job()` | Java 21 (Gradle) | ❌ | checkout → setup-java → gradlew build |

All jobs:
- Use `ubuntu-latest` runner
- Pin action versions (`@v4`, `@v5`)
- Enable dependency caching where available

#### Stack Registry

```python
_CI_JOBS = {
    "python": _python_ci_job,
    "node": _node_ci_job,
    "typescript": _node_ci_job,   # shares Node runner
    "go": _go_ci_job,
    "rust": _rust_ci_job,
    "java-maven": _java_maven_ci_job,
    "java-gradle": _java_gradle_ci_job,
}
```

**Note:** `typescript` maps to `_node_ci_job` — TypeScript projects use
the same npm-based CI pipeline as Node.js.

#### Resolver

| Function | Purpose |
|----------|---------|
| `_resolve_job(stack_name)` | Exact match → prefix match. Returns the callable generator or `None`. E.g. `python-flask` → `_python_ci_job`. |

---

### `wf_docker.py` — Docker CI Job (205 lines)

Docker build + push CI job supporting three registry types with
automatic Buildx setup and GHA layer caching.

#### Registry Support

| Type | Login Action | Secrets Required |
|------|-------------|-----------------|
| `ghcr` | `docker/login-action@v3` | `GITHUB_TOKEN` (built-in) |
| `dockerhub` | `docker/login-action@v3` | `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN` |
| `custom` | `docker/login-action@v3` | `REGISTRY_USERNAME`, `REGISTRY_PASSWORD` |
| *(empty)* | No login | None — local build only |

#### Features

- **Buildx** — `docker/setup-buildx-action@v3` (optional, default on)
- **GHA layer caching** — `--cache-from type=gha`, `--cache-to type=gha,mode=max` (optional, default on)
- **Multi-tag** — `${{ github.sha }}` + `latest`
- **Custom build args** — any `dict[str, str]`
- **Push guard** — push only on `push` events, not PRs
- **Multi-service** — `generate_docker_ci` supports multiple services with unique job names (`docker-<name>`)

#### Public API

| Function | Signature | Purpose |
|----------|-----------|---------|
| `generate_docker_ci` | `(docker_services, *, project_name="", test_job="") → GeneratedFile?` | Full Docker CI workflow. Includes a test job placeholder if none provided. |

#### Internal

| Function | Purpose |
|----------|---------|
| `_docker_ci_job(*, image_name, registry, registry_type, build_args, use_buildx, use_cache, dockerfile, context)` | Single docker job YAML block |

---

### `wf_k8s_deploy.py` — K8s Deploy Jobs (213 lines)

Three deployment strategies, all sharing a common `_kubeconfig_step` for
cluster authentication via GHA secrets.

#### Strategies

| Method | Function | Pipeline |
|--------|----------|----------|
| `kubectl` | `_kubectl_deploy_ci_job` | kubeconfig → `kubectl apply --dry-run=server` → `kubectl apply` → `kubectl rollout status` |
| `skaffold` | `_skaffold_deploy_ci_job` | kubeconfig → download skaffold binary → `skaffold run` with optional profile/repo/file |
| `helm` | `_helm_deploy_ci_job` | kubeconfig → `helm upgrade --install` with optional namespace/values/create-namespace |

#### Common Step

| Function | Purpose |
|----------|---------|
| `_kubeconfig_step()` | Decodes base64 `KUBECONFIG` secret → `$HOME/.kube/config` with `chmod 600` |

All deploy jobs:
- Run only on `push` events (`if: github.event_name == 'push'`)
- Accept a `needs` list for dependency chaining
- Use `ubuntu-latest` runner

#### Public API

| Function | Signature | Purpose |
|----------|-----------|---------|
| `generate_k8s_deploy_ci` | `(deploy_config, *, project_name="") → GeneratedFile?` | Full deploy workflow. Dispatches to kubectl/skaffold/helm based on `method`. |

---

### `wf_terraform.py` — Terraform CI Job (145 lines)

Terraform workflow with provider-aware credential injection and
guarded apply (PR = plan only, push = plan + apply).

#### Provider Credentials

| Provider | Secrets Injected as `env:` |
|----------|--------------------------|
| `aws` | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` |
| `google` | `GOOGLE_CREDENTIALS` |
| `azurerm` | `ARM_CLIENT_ID`, `ARM_CLIENT_SECRET`, `ARM_TENANT_ID`, `ARM_SUBSCRIPTION_ID` |

#### Workflow Behavior

| Event | Pipeline |
|-------|----------|
| Pull request | `init -no-color` → `validate` → `plan` |
| Push to main | `init -no-color` → `validate` → `plan` → `apply -auto-approve` |

#### Optional Features

- **Workspace selection** — `terraform workspace select <name>` (creates if needed)
- **Working directory** — configurable (default: `terraform/`)

#### Public API

| Function | Signature | Purpose |
|----------|-----------|---------|
| `generate_terraform_ci` | `(terraform_config, *, project_name="") → GeneratedFile?` | Full Terraform CI workflow |

#### Internal

| Symbol | Purpose |
|--------|---------|
| `_TERRAFORM_CREDENTIALS` | `dict[provider → dict[env_name → secret_ref]]` |
| `_terraform_ci_job(*, provider, working_directory, workspaces)` | Job YAML block builder |

---

### `wf_post_deploy.py` — Post-Deploy Steps (157 lines)

Produces a workflow that triggers after the Deploy workflow completes
successfully, running DNS verification and CDN cache purge.

#### CDN Providers

| Provider | Purge Mechanism | Secrets Required |
|----------|----------------|-----------------|
| `cloudflare` | `curl -X POST .../purge_cache` with API token | `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ZONE_ID` |
| `cloudfront` | `aws cloudfront create-invalidation --paths "/*"` | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `CLOUDFRONT_DISTRIBUTION_ID` |
| `netlify` | `npx netlify-cli deploy --prod --dir=.` | `NETLIFY_AUTH_TOKEN`, `NETLIFY_SITE_ID` |

#### Step Builders

| Function | Purpose |
|----------|---------|
| `_dns_verify_ci_step(domains)` | Generates `dig +short <domain> A` for each domain with warning on missing A records |
| `_cdn_purge_ci_step(cdn_provider)` | Generates provider-specific cache purge step. Returns empty string for unknown providers. |

#### Workflow Trigger

```yaml
on:
  workflow_run:
    workflows: ["Deploy"]
    types: [completed]
```

Only runs when the Deploy workflow completes successfully
(`if: github.event.workflow_run.conclusion == 'success'`).

#### Public API

| Function | Signature | Purpose |
|----------|-----------|---------|
| `generate_deploy_post_steps` | `(deploy_config, *, project_name="") → GeneratedFile?` | Post-deploy workflow. Returns `None` if no domains and no CDN provider. |

#### Internal

| Symbol | Purpose |
|--------|---------|
| `_CDN_PURGE_COMMANDS` | `dict[provider → {run: str, secrets: dict}]` |

---

### `wf_lint.py` — Lint Workflow (123 lines)

Lightweight lint-only workflow, separate from the full CI pipeline.
Useful for fast PR feedback without running full test suites.

#### Lint Steps

| Stack | Setup | Tools |
|-------|-------|-------|
| `python` | `setup-python@v5` + `pip install ruff mypy` | `ruff check .`, `ruff format --check .`, `mypy src/` |
| `node`, `typescript` | `setup-node@v4` + `npm ci` | `npm run lint`, `npx prettier --check .` |

#### Public API

| Function | Signature | Purpose |
|----------|-----------|---------|
| `generate_lint` | `(project_root, stack_names) → GeneratedFile?` | Lint-only workflow. Returns `None` if no supported stacks. |

#### Internal

| Symbol | Purpose |
|--------|---------|
| `_LINT_STEPS` | `dict[stack → callable]` — maps stack to lint step generator |
| `_python_lint_steps()` | Returns ruff + mypy YAML steps |
| `_node_lint_steps()` | Returns eslint + prettier YAML steps |

---

### `github_workflow.py` — Backward Compatibility Shim (127 lines)

Re-exports everything from the 6 `wf_*.py` modules so existing consumer
imports continue to work unchanged. Also hosts `generate_ci()` — the CI
workflow assembler that ties the job registry to workflow output.

#### Re-Exported Symbols

| Source Module | Symbols |
|--------------|---------|
| `wf_ci_jobs` | `_CI_JOBS`, `_go_ci_job`, `_java_gradle_ci_job`, `_java_maven_ci_job`, `_node_ci_job`, `_python_ci_job`, `_resolve_job`, `_rust_ci_job` |
| `wf_docker` | `_docker_ci_job`, `generate_docker_ci` |
| `wf_k8s_deploy` | `_helm_deploy_ci_job`, `_kubeconfig_step`, `_kubectl_deploy_ci_job`, `_skaffold_deploy_ci_job`, `generate_k8s_deploy_ci` |
| `wf_terraform` | `_TERRAFORM_CREDENTIALS`, `_terraform_ci_job`, `generate_terraform_ci` |
| `wf_post_deploy` | `_CDN_PURGE_COMMANDS`, `_cdn_purge_ci_step`, `_dns_verify_ci_step`, `generate_deploy_post_steps` |
| `wf_lint` | `generate_lint` |

#### `generate_ci()` — The Glue Function

```python
generate_ci(
    project_root: Path,
    stack_names: list[str],
    *,
    project_name: str = "",
) -> GeneratedFile | None
```

1. Iterates `stack_names`, resolves each via `_resolve_job()`
2. Deduplicates by generator identity (`id(gen)`) — prevents duplicate
   jobs when e.g. `["python", "python-flask"]` both resolve to `_python_ci_job`
3. Assembles YAML header + job blocks
4. Returns `GeneratedFile` at `.github/workflows/ci.yml`

---

## Dependency Graph

```
wf_ci_jobs.py        ← standalone (no internal imports)
     ↑
wf_docker.py         ← standalone (imports GeneratedFile only)
     ↑
wf_k8s_deploy.py     ← standalone (imports GeneratedFile only)
     ↑
wf_terraform.py      ← standalone (imports GeneratedFile only)
     ↑
wf_post_deploy.py    ← standalone (imports GeneratedFile only)
     ↑
wf_lint.py           ← standalone (imports GeneratedFile only)
     ↑
github_workflow.py   ← imports ALL of the above (shim + generate_ci)

dockerfile.py        ← standalone
dockerignore.py      ← standalone
compose.py           ← standalone
```

**Key insight:** All 6 `wf_*.py` modules are fully independent of each other.
They share no code and have no cross-imports. The only file that ties them
together is the shim (`github_workflow.py`) and the orchestrator
(`ci/compose.py`, which lives outside this package).

---

## Consumers

### Internal Services

| Consumer | Imports | Purpose |
|----------|---------|---------|
| `ci/ops.py` | `generate_ci`, `generate_lint`, `generate_terraform_ci` | CI setup wizard handlers — lazy imports in 3 separate functions |
| `ci/compose.py` | `_resolve_job`, `_docker_ci_job`, `_kubectl_deploy_ci_job`, `_skaffold_deploy_ci_job`, `_helm_deploy_ci_job`, `_terraform_ci_job`, `_dns_verify_ci_step`, `_cdn_purge_ci_step`, `_kubeconfig_step`, `_CDN_PURGE_COMMANDS`, `generate_deploy_post_steps` | Cross-domain CI orchestration (top-level + lazy import) |
| `wizard/setup_ci.py` | `_resolve_job` | Wizard validates detected stacks against available CI job generators |
| `docker/generate.py` | `generate_dockerfile`, `supported_stacks`, `generate_dockerignore`, `generate_compose` | Docker file generation — all lazy imports |

### Tests

| Test File | Count | Covers |
|-----------|-------|--------|
| `tests/test_ci_generators.py` | 36 | `_resolve_job` (11 tests: exact + prefix + unknown), `generate_ci` (16 tests: per-stack, multi, dedup, YAML, pinning, permissions), `generate_lint` (7 tests) |
| `tests/test_docker_generators.py` | ~20 | `generate_dockerfile` (per-stack), `generate_dockerignore`, `generate_compose`, `_resolve_port` |
| `tests/integration/test_ci_terraform_chain.py` | integration | Terraform CI end-to-end with all 3 providers |
| `tests/integration/test_k8s_ci_chain.py` | 31 | K8s deploy CI: kubectl, skaffold, helm |
| `tests/integration/test_dns_ci_chain.py` | 14 | DNS verification + CDN purge for all 3 providers |
| `tests/integration/test_docker_ci_chain.py` | 18 | Docker CI: single + multi-service, all registry types |

---

## Dependencies

### Internal

| Dependency | Used By | Purpose |
|-----------|---------|---------|
| `models.template.GeneratedFile` | All modules | Standard return type — `(path, content, overwrite, reason)` |

### External

**None.** All generators are pure string template functions with zero
runtime dependencies beyond the standard library.

---

## Adding a New Generator

### Adding a New CI Language

1. **Create the job function** in `wf_ci_jobs.py`:

```python
def _ruby_ci_job(version_matrix: list[str] | None = None) -> str:
    """Ruby CI job: bundle, lint, test."""
    versions = version_matrix or ["3.2", "3.3"]
    matrix_str = ", ".join(f'"{v}"' for v in versions)
    return f"""\
  ruby:
    name: Ruby — lint, test
    runs-on: ubuntu-latest
    strategy:
      matrix:
        ruby-version: [{matrix_str}]

    steps:
      - uses: actions/checkout@v4
      # ... additional steps ...
"""
```

2. **Register it** in `_CI_JOBS`:

```python
_CI_JOBS["ruby"] = _ruby_ci_job
```

3. **Re-export** in `github_workflow.py` shim (for backward compat):

```python
from src.core.services.generators.wf_ci_jobs import _ruby_ci_job  # noqa: F401
```

4. **Add tests** in `tests/test_ci_generators.py`:

```python
def test_exact_ruby(self):
    assert _resolve_job("ruby") is _ruby_ci_job

def test_ruby(self, tmp_path: Path):
    r = generate_ci(tmp_path, ["ruby"])
    assert r is not None
    assert "bundle" in r.content
```

### Adding a New Dockerfile Template

1. Add template constant `_RUBY_DOCKERFILE = """..."""` in `dockerfile.py`
2. Register in `_STACK_TEMPLATES["ruby"] = _RUBY_DOCKERFILE`
3. Test: `generate_dockerfile(tmp_path, "ruby")` returns `GeneratedFile`

### Adding a New CDN Provider

1. Add entry to `_CDN_PURGE_COMMANDS` in `wf_post_deploy.py`:

```python
"bunny": {
    "run": "curl -X POST ...",
    "secrets": {"BUNNY_API_KEY": "${{ secrets.BUNNY_API_KEY }}"},
},
```

2. Update integration test `tests/integration/test_dns_ci_chain.py`

---

## Design Decisions

### Why Split `github_workflow.py`?

The original file was 1,082 lines covering 6 distinct CI/CD domains
(language CI, Docker, K8s deploy, Terraform, post-deploy, lint).
Each domain had its own data tables, job builders, and public API with
zero cross-references between domains. The split gives:

| File | Lines | Responsibility |
|------|-------|----------------|
| `wf_ci_jobs.py` | 218 | 6 language job generators + stack registry |
| `wf_docker.py` | 205 | Docker build/push with 3 registry types |
| `wf_k8s_deploy.py` | 213 | 3 deploy strategies sharing kubeconfig |
| `wf_terraform.py` | 145 | 3 cloud provider credential injection |
| `wf_post_deploy.py` | 157 | DNS verify + 3 CDN purge providers |
| `wf_lint.py` | 123 | 2 language lint step builders |

No file exceeds 220 lines. The backward-compat shim (127 lines)
means zero consumer changes were needed — all 6 consumers import
from `github_workflow` and continue to work identically.

### Why Keep `generate_ci()` in the Shim?

`generate_ci()` is the glue function that iterates stack names, calls
`_resolve_job()` from `wf_ci_jobs.py`, deduplicates by generator identity,
and assembles the final CI workflow YAML. It's only 30 lines and sits
naturally as the shim's "real content" beyond re-exports. Moving it to
`wf_ci_jobs.py` would introduce a `GeneratedFile` import there for a
single function, while every other file already has it.

### Why Not Split `dockerfile.py`?

At 510 lines, `dockerfile.py` is mostly template string constants —
13 multi-line Dockerfile templates that are structurally identical.
The only logic is `_resolve_template()` (15 lines) and `generate_dockerfile()`
(47 lines). Splitting templates into separate files would scatter related
content with no functional benefit. There is no complex logic to isolate.

### Why Not Split `compose.py`?

At 105 lines with a single public function and one helper, `compose.py`
is well under any splitting threshold. The entire module is cohesive
and self-contained.

### Why Are All `wf_*.py` Modules Independent?

The 6 workflow modules have zero cross-imports by design. This means:
- Any module can be tested, modified, or removed without affecting others
- The shim can selectively re-export without initialization order issues
- `ci/compose.py` can cherry-pick individual job builders without pulling
  in unrelated domains

### Why Does Every Generator Return `GeneratedFile | None`?

The `None` return signals "nothing to generate" (e.g., no matching stacks,
empty service list). This pushes the decision to the caller:
- Wizard UI can show "no CI config needed"
- Batch generators can filter out `None` results
- No file is ever written unnecessarily
