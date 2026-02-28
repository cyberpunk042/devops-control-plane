# Wizard Domain

> The setup experience for the devops control plane.
> Scans the project, detects what's there, suggests what to enable,
> and generates production-ready configuration — Dockerfiles, CI workflows,
> K8s manifests, Terraform scaffolding, DNS zones, proxy configs —
> all from a single wizard flow.

---

## How It Works

The wizard operates in three phases, each handled by a different part
of this domain:

### Phase 1: Detection — What Does This Project Have?

When the wizard opens, `wizard_detect()` runs once. It does NOT ask
the user anything. It reads the machine and the project, then delivers
a comprehensive snapshot so the frontend can pre-populate every form.

```
┌─────────────────────────────────────────────────────────────┐
│                     wizard_detect()                          │
│                                                              │
│  1. TOOL SCAN                                                │
│     shutil.which() for 15 CLI tools:                         │
│     git, gh, docker, docker-compose, kubectl, terraform,     │
│     helm, node, npm, ruff, mypy, pytest, pip-audit,          │
│     bandit, safety                                           │
│                                                              │
│  2. FILE SCAN                                                │
│     Checks for: .git/, Dockerfile, docker-compose.yml,       │
│     k8s/, terraform/, .github/workflows/, pyproject.toml,    │
│     package.json, project.yml, dns/, cdn/, CNAME             │
│                                                              │
│  3. CONNECTIVITY PROBES                                      │
│     Docker daemon alive? K8s cluster reachable? Terraform     │
│     CLI working?  (subprocess with 5s timeout each)          │
│                                                              │
│  4. INTEGRATION MAPPING                                      │
│     Combines tool+file+connectivity into per-integration      │
│     status:  ready | installed | not_installed                │
│     suggestion:  auto | manual | hidden                       │
│     Missing tools → install suggestions                       │
│                                                              │
│  5. STACK DEFAULTS                                           │
│     Detected language stacks → form defaults.                 │
│     Go project → base image golang:1.22-alpine, port 8080    │
│     Python Flask → python:3.12-slim, port 5000               │
│     No stacks detected → generic Python defaults              │
│                                                              │
│  6. EMBEDDED STATUS (one-stop-shop)                          │
│     Calls 15 helper functions that reach into other services  │
│     (docker_ops, k8s_detect, terraform_ops, git_ops, etc.)   │
│     and embeds the results so the frontend NEVER needs a      │
│     second API call.                                          │
│                                                              │
│  OUTPUT: One dict. Everything the wizard UI needs.            │
└─────────────────────────────────────────────────────────────┘
```

**Why embed everything?** Because the wizard opens once and presents
7+ steps. If each step needed a separate API call to get status data,
the UX would be sluggish and the backend would do redundant work. The
detection response is cached at the HTTP layer — one scan per wizard
open.

### Phase 2: Validation — Is This Safe to Generate?

Before any generation runs, `validate_wizard_state()` checks the
submitted data for mistakes the generator would silently produce
broken output for:

- K8s namespace format (RFC 1123 — lowercase alphanumeric + hyphens)
- Docker registry URL shape (`host[:port][/path]`)
- Deploy method whitelist (`kubectl | skaffold | helm`)
- Terraform provider whitelist (`aws | google | azurerm`)
- Helm chart path existence (warning, not hard error)
- CI secret reference advisories (can't verify, but can remind)

`check_required_tools()` also runs here — it checks if the CLI tools
needed by the wizard state are actually installed, and whether install
recipes are available for any missing ones.

### Phase 3: Generation — Write the Files

Each setup handler follows the same contract:

```python
def setup_X(root: Path, data: dict) -> dict:
    """
    1. Parse inputs from data dict
    2. Guard: check if output exists + overwrite flag
    3. Generate content (inline or delegate to generator module)
    4. Write files to disk
    5. Record activity event via devops_cache
    6. Return {"ok": True, "message": "...", "files_created": [...]}
    """
```

The dispatcher routes action strings to handlers:

```
"setup_git"       → setup_git.setup_git()
"setup_github"    → setup_git.setup_github()
"setup_docker"    → setup_infra.setup_docker()
"setup_k8s"       → setup_infra.setup_k8s()
"setup_terraform" → setup_infra.setup_terraform()
"setup_pages"     → setup_infra.setup_pages()
"setup_ci"        → setup_ci.setup_ci()
"setup_dns"       → setup_dns.setup_dns()
```

**Why a dispatcher?** The web route doesn't care which handler runs.
It receives `{"action": "setup_docker", "data": {...}}`, passes it
to `wizard_setup()`, and returns whatever the handler returns. One
route, eight handlers.

---

## Stack Defaults — Concrete Example

Same project structure, different detected stacks:

**Python Flask project detected:**
```
docker.base_image  = "python:3.12-slim"
docker.port        = "5000"
docker.install_cmd = "pip install -e ."
ci.test_cmd        = "pytest"
ci.lint_cmd        = "ruff check ."
ci.language_key    = "python-version"
```

**Go Gin project detected:**
```
docker.base_image  = "golang:1.22-alpine"
docker.port        = "8080"
docker.install_cmd = "go build -o /app ./..."
ci.test_cmd        = "go test ./..."
ci.lint_cmd        = "golangci-lint run"
ci.language_key    = "go-version"
```

**Node Express project detected:**
```
docker.base_image  = "node:20-alpine"
docker.port        = "3000"
docker.install_cmd = "npm ci"
ci.test_cmd        = "npm test"
ci.lint_cmd        = "npm run lint"
ci.language_key    = "node-version"
```

The user sees appropriate defaults in every form field. If no stacks
are detected, everything falls back to generic Python defaults — the
most common case for this project.

---

## CI Generation — The Complex One

`setup_ci.py` is the largest module (~530 lines) because CI workflow
generation is an irreducible single concern with combinatorial branches.
A single CI workflow can contain:

1. **Trigger** — push / PR / manual / schedule / push+PR
2. **Test jobs** — three modes:
   - Stack-aware (delegates to `generators/github_workflow.py` per stack)
   - Explicit command (user provides test/lint/typecheck commands)
   - Default Python fallback (pytest)
3. **Docker build/push** — three registry types:
   - GHCR (uses `GITHUB_TOKEN`)
   - DockerHub (uses `DOCKERHUB_USERNAME` / `DOCKERHUB_TOKEN`)
   - Custom registry (generic credentials)
   - Plus: Buildx caching, multi-tag (SHA + latest), build args
4. **K8s deploy** — three methods × single or multi-environment:
   - kubectl: dry-run → apply → rollout wait
   - Skaffold: install skaffold → skaffold run (with profile support)
   - Helm: upgrade --install with value files and image overrides
   - Multi-env: chained jobs with branch constraints, approval gates,
     per-environment secrets

Each combination produces a different YAML structure. The module uses
`yaml.dump()` for reliable output instead of string templates.

---

## DNS Generation — The Broad One

`setup_dns.py` generates a full DNS/CDN configuration suite from a
single domain name. What comes out depends on what the user enabled:

| Feature | Output Files |
|---------|-------------|
| DNS records | `dns/{domain}.zone` (BIND format) + `dns/records.json` |
| Subdomains | CNAME records appended to zone + JSON |
| Mail (Google/Proton/etc.) | MX + SPF + DMARC records |
| GitHub Pages | `CNAME` file in project root |
| Nginx proxy | `cdn/nginx.conf` |
| Caddy proxy | `cdn/Caddyfile` |
| Traefik proxy | `cdn/traefik.yml` |
| Cloudflare Tunnel | `cdn/cloudflared.yml` |
| K8s Ingress | `k8s/ingress.yaml` with annotations |
| cert-manager | `k8s/cert-manager/cluster-issuer.yaml` + `certificate.yaml` |

All files are written to disk. Existing files are skipped unless the
overwrite flag is set — never silently replaced.

---

## File Map

```
wizard/
├── __init__.py      Public API re-exports
├── detect.py        Environment scanner + stack defaults (~400 lines)
├── helpers.py       Data collection wrappers for detect.py (~230 lines)
├── validate.py      Pre-generation validation (~175 lines)
├── setup_git.py     Git init + GitHub environments (~200 lines)
├── setup_infra.py   Docker + K8s + Terraform + Pages (~280 lines)
├── setup_ci.py      CI workflow generation + deploy steps (~530 lines)
├── setup_dns.py     DNS zones + proxy configs + K8s ingress (~400 lines)
├── dispatch.py      Action router + config deletion (~130 lines)
└── README.md        This file
```

### Why `helpers.py` exists separately from `detect.py`

`wizard_detect()` embeds data from 15 other services. Each call needs
a try/except with a safe fallback. If those 15 wrappers lived inline
in `detect.py`, the detection logic would be buried under error handling
noise. The helpers are a private implementation detail — consumed only
by `detect.py`, never imported by anything else.

Each helper follows the exact same shape:

```python
def _wizard_docker_status(root: Path) -> dict:
    try:
        from src.core.services.docker_ops import docker_status
        return docker_status(root)
    except Exception:
        return {"available": False}
```

Lazy imports inside the function body, not at module top. This prevents
circular import chains and keeps the wizard bootable even if optional
services are broken.

---

## Design Invariants

| Invariant | Why |
|-----------|-----|
| **One scan, zero follow-up calls** | Detection embeds all status data so the frontend never needs a second request |
| **Every handler returns `{"ok": bool}`** | Uniform contract. Success has `message` + `files_created`. Failure has `error`. |
| **Overwrite is always opt-in** | Existing files are NEVER silently replaced. The user must check "Overwrite". |
| **Every success records an event** | `devops_cache.record_event()` is called on every success path so the activity feed stays current |
| **Handlers are pure functions of (root, data)** | No global state. No session. No Flask. Testable from CLI, TUI, or web. |
| **Validation runs before generation** | The web route calls `validate_wizard_state()` before `wizard_setup()`. Generators can assume validated input. |

---

## Dependency Graph

```
dispatch.py ──→ setup_git.py     (imports handlers)
     │     ──→ setup_infra.py
     │     ──→ setup_ci.py
     │     ──→ setup_dns.py
     │
     │     Each handler imports from its domain:
     │       setup_git.py   → secrets_ops, security_scan
     │       setup_infra.py → k8s_ops, k8s_helm_generate, terraform_generate, pages_discovery
     │       setup_ci.py    → generators/github_workflow
     │       setup_dns.py   → dns_cdn_ops
     │
detect.py ──→ helpers.py  (data collection)
     │         │
     │         └──→ docker_ops, k8s_detect, terraform_ops, dns_cdn_ops,
     │              git_ops, ci_ops, env_ops, security_ops, pages_engine, ...
     │
     └──→ config/loader, config/stack_loader, detection (for stack defaults)

validate.py ──→ tool_install (for recipe availability check)
```

---

## Backward Compatibility

The original files are now thin shims that re-export from this directory:

| Old path | Re-exports from |
|----------|----------------|
| `services/wizard_setup.py` | All `setup_*` handlers + `wizard_setup` + `delete_generated_configs` |
| `services/wizard_ops.py` | `wizard_detect` + all setup re-exports |
| `services/wizard_validate.py` | `validate_wizard_state` + `check_required_tools` |

For new code, import from the specific submodule:

```python
# ✅ Narrow — import what you need from where it lives
from src.core.services.wizard.detect import wizard_detect
from src.core.services.wizard.setup_ci import setup_ci

# ✅ Package-level — convenient for multiple imports
from src.core.services.wizard import wizard_detect, wizard_setup

# ⚠️ Legacy shim — still works, avoid in new code
from src.core.services.wizard_ops import wizard_detect
```

---

## Consumers

| Consumer | What It Imports | Why |
|----------|----------------|-----|
| `routes_devops_detect.py` | `wizard_detect` | Powers the wizard detection API endpoint |
| `routes_devops_apply.py` | `wizard_setup`, `delete_generated_configs` | Powers the wizard apply + delete endpoints |
| `routes_devops_apply.py` | `validate_wizard_state`, `check_required_tools` | Pre-generation validation |

---

## API Endpoints

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/devops/detect` | GET | Run `wizard_detect()` — full environment scan |
| `/api/devops/apply` | POST | Run `wizard_setup()` — generate config for action |
| `/api/devops/delete-configs` | POST | Run `delete_generated_configs()` — remove generated files |
| `/api/devops/validate` | POST | Run `validate_wizard_state()` — pre-generation check |
| `/api/devops/check-tools` | POST | Run `check_required_tools()` — CLI availability |
