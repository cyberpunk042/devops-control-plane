# Wizard Domain

> **9 files · 2,622 lines · Project setup wizard — detection, validation, dispatch, and generation.**
>
> Scans the environment, validates configuration, dispatches setup
> actions, and generates infrastructure configs (Git, Docker, K8s,
> CI, Terraform, DNS, Pages) from wizard state.

---

## How It Works

The wizard operates as a **detect → validate → dispatch → generate** pipeline:

```
┌──────────────────────────────────────────────────────────────────┐
│  1. DETECT — What does the project look like?                    │
│     wizard_detect(root) → comprehensive environment snapshot     │
│     ├── CLI tools (docker, kubectl, helm, terraform, gh, ...)    │
│     ├── Project files (.env, Dockerfile, k8s/, terraform/, ...)  │
│     ├── Git status (remote, branch, .gitignore)                  │
│     ├── CI status (workflows, providers)                         │
│     ├── Stack detection (Python, Node, Go, ...)                  │
│     └── Stack defaults (CI, Docker, K8s settings per stack)      │
├──────────────────────────────────────────────────────────────────┤
│  2. VALIDATE — Is the configuration valid?                       │
│     validate_wizard_state(state) → errors + warnings             │
│     check_required_tools(state) → missing tools + install info   │
├──────────────────────────────────────────────────────────────────┤
│  3. DISPATCH — Route to the correct handler                      │
│     wizard_setup(root, "setup_docker", data)                     │
│     _SETUP_ACTIONS = {                                           │
│         "setup_git":       setup_git,                            │
│         "setup_github":    setup_github,                         │
│         "setup_docker":    setup_docker,                         │
│         "setup_k8s":       setup_k8s,                            │
│         "setup_ci":        setup_ci,                             │
│         "setup_terraform": setup_terraform,                      │
│         "setup_dns":       setup_dns,                            │
│         "setup_pages":     setup_pages,                          │
│     }                                                            │
├──────────────────────────────────────────────────────────────────┤
│  4. GENERATE — Create files on disk                              │
│     Each handler writes config files to the project directory    │
│     and records the event in the activity log                    │
└──────────────────────────────────────────────────────────────────┘
```

### Detection Architecture

`detect.py` aggregates data from **10+ helper functions** (in `helpers.py`)
that each call into their respective service domain:

```
wizard_detect(root)
    │
    ├── _wizard_config_data(root)     → project config (modules, envs)
    ├── _wizard_docker_status(root)   → docker version, daemon, compose
    ├── _wizard_k8s_status(root)      → manifests, helm, kustomize, tools
    ├── _wizard_terraform_status(root)→ CLI, files, providers, modules
    ├── _wizard_dns_status(root)      → providers, domains, certs
    ├── _wizard_env_status(root)      → .env files, vars, validation
    ├── _wizard_gh_cli_status(root)   → gh version, auth, repo
    ├── _wizard_gh_environments(root) → GitHub deployment environments
    ├── _wizard_ci_status(root)       → CI providers, workflows
    ├── _wizard_gitignore_analysis(root)→ gitignore patterns, coverage
    ├── _wizard_gh_user(root)         → authenticated GitHub user
    ├── _wizard_gh_repo_info(root)    → repo visibility, description
    ├── _wizard_git_remotes(root)     → all git remotes
    ├── _wizard_codeowners_content(root)→ existing CODEOWNERS file
    ├── _wizard_pages_status(root)    → pages segments, meta, content
    └── _wizard_stack_defaults(root, stacks) → per-stack CI/Docker/K8s defaults
```

### Helpers Pattern

Every helper follows the same error-safe pattern:

```python
def _wizard_<domain>_status(root: Path) -> dict:
    try:
        from src.core.services.<domain> import <detect_fn>
        return <detect_fn>(root)
    except Exception:
        return {}
```

This ensures detection **never crashes** — a failure in one domain
(e.g., K8s detection timeout) doesn't prevent the wizard from loading.

---

## Key Data Shapes

### wizard_detect response (abbreviated)

```python
{
    "project": {
        "modules": [...],
        "environments": ["staging", "production"],
    },
    "docker": {
        "available": True,
        "version": "24.0.7",
        "compose_available": True,
    },
    "k8s": {
        "available": True,
        "manifest_count": 5,
        "helm_charts": [...],
    },
    "terraform": {
        "cli_available": True,
        "has_configs": True,
    },
    "git": {
        "remote": "git@github.com:owner/repo.git",
        "branch": "main",
    },
    "gh_cli": {
        "installed": True,
        "authenticated": True,
    },
    "ci": {
        "provider": "github_actions",
        "workflows": ["ci.yml"],
    },
    "stacks": ["python", "node"],
    "stack_defaults": {
        "ci": {"test_cmd": "pytest", "lint_cmd": "ruff check ."},
        "docker": {"base_image": "python:3.12-slim", "port": 8000},
    },
    "env": {
        "files": [".env"],
        "variable_count": 12,
    },
    "pages": {
        "segments": [...],
        "has_content": True,
    },
}
```

### validate_wizard_state response

```python
# Valid
{
    "ok": True,
    "warnings": [
        "CI deploy jobs will reference ${{ secrets.KUBECONFIG }}. "
        "Ensure this secret is configured in your GitHub repository.",
    ],
}

# Invalid
{
    "ok": False,
    "errors": [
        "Invalid K8s namespace: 'My App'. "
        "Must be lowercase alphanumeric with hyphens, 1–63 chars.",
    ],
    "warnings": [],
}
```

**Validation rules:**

| Field | Rule | Severity |
|-------|------|----------|
| K8s namespace | RFC 1123: `[a-z0-9][a-z0-9-]{0,61}[a-z0-9]` | error |
| Environment names | Same RFC 1123 pattern | error |
| Docker registry URL | `host[:port][/path]` pattern | error |
| Deploy method | `kubectl \| skaffold \| helm` | error |
| Helm chart path | Must exist if specified | warning |
| Terraform provider | `aws \| google \| azurerm` | error |
| CI secret references | Advisory: "Ensure KUBECONFIG is configured" | warning |
| Terraform AWS secrets | Advisory: "Ensure AWS_ACCESS_KEY_ID is configured" | warning |

### check_required_tools response

```python
{
    "ok": False,
    "tools": {
        "docker": {
            "installed": True,
            "required": True,
            "reason": "Docker services configured",
            "install_available": True,
        },
        "kubectl": {
            "installed": False,
            "required": True,
            "reason": "Kubernetes deployment configured",
            "install_available": True,
        },
    },
    "missing": ["kubectl"],
    "install_available": ["kubectl"],
}
```

### wizard_setup response (dispatch)

```python
# Success (all handlers)
{
    "ok": True,
    "message": "...",
    "files_created": ["Dockerfile", "docker-compose.yml"],
    "results": ["..."],
}

# Unknown action
{"ok": False, "error": "Unknown action: setup_foobar"}
```

### delete_generated_configs response

```python
{
    "ok": True,
    "deleted": ["Dockerfile", "docker-compose.yml", "k8s/"],
    "errors": [],
}
```

### setup_git response

```python
{
    "ok": True,
    "message": "Git repository configured",
    "files_created": [".git/", ".gitignore"],
    "results": [
        "Repository initialized",
        "Branch renamed: master → main",
        ".gitignore created (42 patterns)",
        "Remote set: origin → git@github.com:owner/repo.git",
        "Pre-commit hook installed (3 checks)",
        "Initial commit: abc1234",
    ],
}
```

### setup_github response

```python
{
    "ok": True,
    "message": "GitHub configuration applied",
    "results": {
        "environments_created": ["staging", "production"],
        "environments_failed": [],
        "secrets_pushed": 5,
        "codeowners_written": True,
    },
}
```

### setup_docker response

```python
{
    "ok": True,
    "message": "Docker configuration created",
    "files_created": ["Dockerfile", "docker-compose.yml", ".dockerignore"],
    "results": [...],
}
```

### setup_ci response

```python
{
    "ok": True,
    "message": "CI workflow(s) written",
    "files_created": [".github/workflows/ci.yml"],
    "results": {
        "jobs": ["test-python", "docker-build", "deploy-staging", "deploy-production"],
        "triggers": ["push", "pull_request"],
    },
}
```

---

## Architecture

```
                  CLI (ui/cli/wizard.py)
                  Routes (routes/wizard/)
                         │
                         │ imports
                         │
              ┌──────────▼──────────┐
              │  wizard_ops.py      │  backward-compat shim
              │  (re-exports all)   │  → imports from wizard/
              └──────────┬──────────┘
                         │
              ┌──────────▼──────────────────────────────────────────┐
              │  wizard/__init__.py                                   │
              │  Public API — re-exports all symbols                  │
              └──┬────┬────┬────┬────┬────┬────┬────┬───────────────┘
                 │    │    │    │    │    │    │    │
     ┌───────────┘    │    │    │    │    │    │    └──────┐
     ▼                ▼    ▼    ▼    ▼    ▼    ▼          ▼
  detect.py     helpers.py │ dispatch │ validate.py    setup_dns.py
  (env scan +   (safe       │ (route   │ (input
   stack        wrappers    │  to      │  checks)
   defaults)    for 15+     │  handler)│
                domains)    │          │
                         ┌──┘          │
                         │             │
                   setup_git.py   setup_ci.py   setup_infra.py
                   (git init,     (CI workflow   (docker, k8s,
                    .gitignore,    generation,    terraform,
                    remote, hooks, test jobs,     pages)
                    github envs)   deploy steps)
```

### Dependency Rules

| Rule | Detail |
|------|--------|
| `detect.py` imports `helpers.py` + all service domains | Heavy aggregation |
| `helpers.py` imports lazily (inside try/except) | Avoids import failures |
| `dispatch.py` imports `setup_*.py` functions | Static dispatch table |
| `validate.py` is standalone | Only uses `shutil.which` + `TOOL_RECIPES` |
| `setup_*.py` modules import their target service | `setup_ci` → `ci/`, etc. |
| No setup module imports another setup module | Independent handlers |

---

## File Map

```
wizard/
├── __init__.py        Public API re-exports (52 lines)
├── detect.py          Main detection — 280+ checks (521 lines)
├── helpers.py         Safe wrappers for 15+ service domains (259 lines)
├── dispatch.py        Action router + config deletion (144 lines)
├── validate.py        Input validation + tool checks (174 lines)
├── setup_git.py       Git + GitHub configuration (218 lines)
├── setup_ci.py        CI workflow generation (569 lines)
├── setup_infra.py     Docker, K8s, Terraform, Pages scaffolding (306 lines)
├── setup_dns.py       DNS & CDN configuration generation (414 lines)
└── README.md          This file
```

---

## Per-File Documentation

### `detect.py` — Environment Detection (521 lines)

| Function | What It Does |
|----------|-------------|
| `wizard_detect(root)` | **Main entry** — aggregates all detection data |
| `_wizard_stack_defaults(root, stacks)` | Derive CI/Docker/K8s defaults per detected stack |
| `_generic_stack_defaults()` | Fallback defaults when no stacks detected |

**Detection scope:**
- 6 infrastructure tools (Docker, K8s, Terraform, DNS, Pages, CI)
- 4 Git/GitHub dimensions (CLI, auth, environments, repo info)
- Stack detection with per-stack defaults
- Project config loading (modules, environments)

### `helpers.py` — Safe Service Wrappers (259 lines)

| Helper | Service Import | Returns On Failure |
|--------|---------------|-------------------|
| `_wizard_config_data(root)` | `config.loader` | `{}` |
| `_wizard_docker_status(root)` | `docker_ops` | `{}` |
| `_wizard_k8s_status(root)` | `k8s.detect` | `{}` |
| `_wizard_terraform_status(root)` | `terraform.ops` | `{}` |
| `_wizard_dns_status(root)` | `dns.cdn_ops` | `{}` |
| `_wizard_env_status(root)` | `env.ops` | `{}` |
| `_wizard_gh_cli_status(root)` | `git_ops` | `{}` |
| `_wizard_gh_environments(root)` | subprocess (`gh api`) | `{}` |
| `_wizard_ci_status(root)` | `ci_ops` | `{}` |
| `_wizard_gitignore_analysis(root)` | `security.ops` | `{}` |
| `_wizard_gh_user(root)` | `git_ops` | `{}` |
| `_wizard_gh_repo_info(root)` | `git_ops` | `{}` |
| `_wizard_git_remotes(root)` | `git_ops` | `{}` |
| `_wizard_codeowners_content(root)` | filesystem | `""` |
| `_wizard_pages_status(root)` | `pages.engine` + `pages.discovery` | `{}` |

### `dispatch.py` — Action Router (144 lines)

| Function | What It Does |
|----------|-------------|
| `wizard_setup(root, action, data)` | Route action string to handler |
| `delete_generated_configs(root, target)` | Clean up wizard-generated files |

**Dispatch table (`_SETUP_ACTIONS`):**

| Action | Handler | Module |
|--------|---------|--------|
| `setup_git` | `setup_git()` | `setup_git.py` |
| `setup_github` | `setup_github()` | `setup_git.py` |
| `setup_docker` | `setup_docker()` | `setup_infra.py` |
| `setup_k8s` | `setup_k8s()` | `setup_infra.py` |
| `setup_ci` | `setup_ci()` | `setup_ci.py` |
| `setup_terraform` | `setup_terraform()` | `setup_infra.py` |
| `setup_dns` | `setup_dns()` | `setup_dns.py` |
| `setup_pages` | `setup_pages()` | `setup_infra.py` |

**Deletion targets (for `delete_generated_configs`):**

| Target | Files Deleted |
|--------|-------------|
| `docker` | `Dockerfile`, `.dockerignore`, `docker-compose*.y*ml` |
| `k8s` | `k8s/` directory |
| `ci` | `.github/workflows/ci.yml`, `.github/workflows/lint.yml` |
| `terraform` | `terraform/` directory |
| `skaffold` | `skaffold.yaml` |
| `dns` | `dns/`, `cdn/`, `CNAME` |
| `all` | All above targets |

### `validate.py` — Input Validation (174 lines)

| Function | What It Does |
|----------|-------------|
| `validate_wizard_state(state, project_root)` | Check wizard state for configuration errors |
| `check_required_tools(state)` | Check which CLI tools are installed vs required |

### `setup_git.py` — Git & GitHub Setup (218 lines)

| Function | Steps |
|----------|-------|
| `setup_git(root, data)` | 1. `git init` → 2. Branch rename → 3. `.gitignore` → 4. Remote → 5. Hooks → 6. Initial commit |
| `setup_github(root, data)` | 1. Create environments → 2. Push secrets → 3. Write CODEOWNERS |

**`setup_git` data keys:**

| Key | Type | Purpose |
|-----|------|---------|
| `default_branch` | str | Target branch name (e.g., "main") |
| `gitignore_content` | str | Raw .gitignore content |
| `generate_gitignore` | bool | Auto-generate from detected stacks |
| `remote` | str | Git remote URL |
| `setup_hooks` | bool | Install pre-commit hook |
| `hook_commands` | list[str] | Commands for pre-commit hook |
| `create_initial_commit` | bool | Run git add + commit |
| `commit_message` | str | Commit message (default: "Initial commit") |

### `setup_ci.py` — CI Workflow Generation (569 lines)

The largest setup handler. Generates complete GitHub Actions workflows:

| Function | What It Does |
|----------|-------------|
| `setup_ci(root, data)` | **Main** — compose full CI YAML |
| `_build_test_jobs_from_stacks(stacks, resolve)` | Stack-specific test job generation |
| `_append_coverage_step(steps, tool)` | Add coverage upload to test job |
| `_build_deploy_steps(method, ns, ...)` | Build deploy steps per environment |

**Deploy method handling:**

| Method | Steps Generated |
|--------|----------------|
| `kubectl` | `kubectl apply -f <dir>` with optional `kubectl set image` |
| `helm` | `helm upgrade --install <release> <chart>` with values |
| `skaffold` | `skaffold deploy -p <profile>` |

### `setup_infra.py` — Infrastructure Scaffolding (306 lines)

| Function | What It Generates |
|----------|------------------|
| `setup_pages(root, data)` | Pages segments from detected content folders |
| `setup_docker(root, data)` | Dockerfile + docker-compose.yml + .dockerignore |
| `setup_k8s(root, data)` | K8s manifests (delegates to `k8s.generate_k8s_wizard`) |
| `setup_terraform(root, data)` | main.tf + variables.tf + outputs.tf + .gitignore |

### `setup_dns.py` — DNS & CDN Configuration (414 lines)

| Feature | What It Generates |
|---------|------------------|
| DNS records | Zone files, `records.json` |
| CNAME | GitHub Pages CNAME file |
| Proxy configs | nginx / caddy / traefik / cloudflared |
| K8s Ingress | Ingress + cert-manager Certificate manifests |
| Terraform | `dns.tf`, `cdn.tf`, `ssl.tf` modules |

---

## Audit Trail

All setup handlers record events via `devops_cache.record_event()`:

| Event | Icon | Title | Card |
|-------|------|-------|------|
| Git setup | 💻 | Git Setup | wizard |
| GitHub setup | 🐙 | GitHub Setup | wizard |
| Docker setup | 🐋 | Docker Setup | wizard |
| K8s setup | ☸️ | K8s Setup | wizard |
| CI setup | 🔄 | CI Setup | wizard |
| Terraform setup | 🏗️ | Terraform Setup | wizard |
| DNS setup | 🌐 | DNS Setup | wizard |
| Pages setup | 📄 | Pages Setup | wizard |
| Config deleted | 🗑️ | Wizard Config Deleted | wizard |

---

## Consumers

| Consumer | What It Uses |
|----------|-------------|
| **Routes** `routes/wizard/` | `wizard_detect`, `wizard_setup`, `validate_wizard_state`, `delete_generated_configs` |
| **CLI** `ui/cli/wizard.py` | `wizard_detect`, `wizard_setup` |
| **Frontend** `templates/scripts/wizard/` | Consumes detection data for UI rendering |
| **K8s domain** `k8s/wizard.py` | Called by `setup_k8s` for manifest generation |
| **CI domain** `ci/compose.py` | Called by `setup_ci` for workflow composition |

---

## Advanced Feature Showcase

### 1. Static Dispatch Table

All 8 setup actions are registered in a single dict. No auto-discovery,
no magic — one line per handler.

```python
# dispatch.py — _SETUP_ACTIONS
_SETUP_ACTIONS = {
    "setup_git": setup_git,
    "setup_github": setup_github,
    "setup_docker": setup_docker,
    "setup_k8s": setup_k8s,
    "setup_ci": setup_ci,
    "setup_terraform": setup_terraform,
    "setup_dns": setup_dns,
    "setup_pages": setup_pages,
}

def wizard_setup(root, action, data):
    fn = _SETUP_ACTIONS.get(action)
    if not fn:
        return {"ok": False, "error": f"Unknown action: {action}"}
    return fn(root, data)
```

One function call dispatches any setup action. Adding a new handler
is one dict entry + one import.

---

### 2. 4-Proxy Config Generation

`setup_dns` generates proxy configuration for 4 different reverse
proxy tools, each with its own config format.

```python
# setup_dns.py — proxy dispatch (simplified)
if proxy == "nginx":
    # Nginx server block with upstream, Host, X-Real-IP headers
    → writes cdn/nginx.conf

elif proxy == "caddy":
    # Caddyfile with per-host reverse_proxy directives
    → writes cdn/Caddyfile

elif proxy == "traefik":
    # YAML with router rules, load balancer, cert resolver
    → writes cdn/traefik.yml

elif proxy == "cloudflared":
    # Cloudflare Tunnel config with ingress rules + catch-all
    → writes cdn/cloudflared.yml
```

Same wizard state → different output per tool. All include subdomains
and TLS configuration when applicable.

---

### 3. 3-Deploy-Method CI Generation

`_build_deploy_steps()` generates GitHub Actions deploy steps for
3 different K8s deployment tools.

```python
# setup_ci.py — _build_deploy_steps()
if method == "kubectl":
    steps = [
        kubeconfig setup,
        "kubectl apply -f k8s/ --dry-run=client",     # validate
        "kubectl apply -f k8s/",                        # deploy
        "kubectl rollout status deployment --timeout=300s",  # wait
    ]

elif method == "skaffold":
    steps = [
        kubeconfig setup,
        install skaffold binary,
        f"skaffold run -f {file} -p {profile} --default-repo={registry}",
    ]

elif method == "helm":
    steps = [
        kubeconfig setup,
        f"helm upgrade --install {release} {chart} "
        f"--set image.repository={image} --set image.tag=${{{{ github.sha }}}}",
    ]
```

The image tag is always `github.sha` for traceability. kubectl
includes a dry-run validation step before the real apply.

---

### 4. Stack-Aware Test Job Composition

When the user selects project stacks (Python, Node, Go, …),
test job YAML fragments are generated per-stack and merged.

```python
# setup_ci.py — stack → test job pipeline
stacks = ["python", "node"]

# Each stack has a generator in generators/github_workflow.py
for stack_name in stacks:
    gen = resolve_job(stack_name)      # → function from registry
    fragment = gen()                    # → YAML string
    parsed = yaml.safe_load(fragment)   # → {"python": {runs-on, steps}}
    jobs.update(parsed)
```

Stack generators produce self-contained YAML fragments (checkout,
language setup, install, lint, test). The wizard merges them into
a single workflow with all jobs running in parallel.

---

### 5. K8s Ingress + cert-manager Manifest Generation

When `k8s_routes` are provided, the DNS wizard generates a full
networking stack: Kubernetes Ingress + TLS + cert-manager.

```python
# setup_dns.py — K8s manifest generation
# 1. Ingress with per-route rules
ingress_manifest = {
    "apiVersion": "networking.k8s.io/v1",
    "kind": "Ingress",
    "metadata": {
        "name": f"{domain}-ingress",
        "annotations": {"kubernetes.io/ingress.class": ingress_ctrl},
    },
    "spec": {
        "rules": ingress_rules,
        "tls": [{"hosts": tls_hosts, "secretName": f"{domain}-tls"}],
    },
}

# 2. ClusterIssuer for Let's Encrypt
if certmanager:
    → k8s/cert-manager/cluster-issuer.yaml

# 3. Certificate referencing the issuer
    → k8s/cert-manager/certificate.yaml
```

One wizard flow → 3 K8s manifests (Ingress + ClusterIssuer +
Certificate), ready to `kubectl apply`.

---

### 6. Multi-Domain Detection with {} Fallback

`wizard_detect()` calls 15 helper functions. Every helper returns
`{}` on error so the wizard always loads with a partial snapshot.

```python
# helpers.py — every detection helper follows this pattern
def _wizard_docker_status(root):
    try:
        # actual detection logic
        return {"installed": True, "compose": True, "daemon": True, ...}
    except Exception:
        return {}

# detect.py — consumed without error checks
result = {
    "tools": tools,
    "files": files,
    "docker": _wizard_docker_status(root),  # {} if Docker daemon down
    "k8s": _wizard_k8s_status(root),        # {} if kubectl missing
    "terraform": _wizard_terraform_status(), # {} if not installed
    ...
}
```

Wizard loads in \<500ms even when Docker is stopped, kubectl is missing,
`gh` is not authenticated, and Terraform is uninstalled. Each empty
dict degrades to "not detected" in the UI.

---

## Design Decisions

### Why separate detect.py from helpers.py?

`detect.py` contains the orchestration logic and stack-default
resolution. `helpers.py` contains the error-safe wrappers that
call into each service domain. Separating them means: (1) helpers
can be unit-tested in isolation, (2) the detection flow is readable
without 15 try/except blocks inlined, and (3) adding a new domain
detection only requires adding one helper function.

### Why does validation happen client-side AND server-side?

The frontend validates for immediate feedback (e.g., namespace format).
But the server-side `validate_wizard_state()` is the authoritative
check — it catches edge cases the frontend might miss and prevents
invalid data from reaching generators. This is defense-in-depth:
never trust client-side validation alone.

### Why is the dispatch table static instead of auto-discovered?

A static `_SETUP_ACTIONS` dict is explicit and auditable: you can
see exactly which actions exist by reading one line. Auto-discovery
(e.g., scanning modules for `setup_*` functions) would add magic
and make it harder to trace which handler runs for a given action.
Adding a new handler requires one dict entry — trivial overhead.

### Why does each setup handler record its own audit event?

Setup operations are user-facing actions with real consequences
(files created, GitHub environments configured). Recording events
per handler ensures: (1) the activity log shows what was set up,
(2) users can see which wizard step ran and when, and (3) forensic
debugging can trace which handler produced which files.

### Why is setup_ci.py the largest setup module at 569 lines?

CI workflow generation is inherently complex: it must compose YAML
that handles multiple test jobs (per stack), Docker build/push steps
(with registry auth), and multi-environment deploy pipelines (with
approval gates). Each combination multiplies the logic. The alternative
— splitting by concern (test, build, deploy) — was considered but
would scatter related workflow composition across files.

### Why does setup_dns generate so many output types?

DNS/CDN configuration touches many tools: DNS registrars need zone
files, container environments need proxy configs, K8s needs Ingress
manifests, and IaC needs Terraform modules. Generating all formats
from one wizard state means users don't need to manually translate
their DNS choices into each tool's format.

### Why do detection helpers return {} on failure instead of raising?

The wizard must always load, even if individual detections fail
(e.g., Docker daemon not running, kubectl not installed). Returning
empty dicts means the UI receives a partial snapshot and can
gracefully show "Docker: not detected" instead of failing entirely.
This is critical for first-time setup where most tools won't be
installed yet.
