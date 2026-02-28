# Core Services

> The business logic layer of the devops control plane.
> Every operation — scanning, provisioning, encrypting, generating,
> deploying — lives here. Routes are thin HTTP dispatchers. CLI commands
> are thin terminal dispatchers. **Services are the application.**

---

## How It Works

The control plane manages a software project's entire DevOps lifecycle
from a single admin panel. The services layer is where that lifecycle
is implemented — not as scripts, but as composable domain functions
that any transport layer (web, CLI, TUI) can call.

### The Big Picture

```
User opens admin panel / runs CLI command
       │
       ▼
┌──────────────────────────────────────────────────────────────────┐
│ TRANSPORT (routes_*.py / cli/*.py)                                │
│  Thin. Parses HTTP/CLI args, calls a service, returns response.  │
│  No logic. No decisions. No state.                               │
└─────────────┬────────────────────────────────────────────────────┘
              │ calls
              ▼
┌──────────────────────────────────────────────────────────────────┐
│ SERVICES (this layer — src/core/services/)                       │
│                                                                  │
│  Where ALL business logic lives:                                 │
│                                                                  │
│  "What tools are available?"     → audit/l0_detection            │
│  "Install cargo-audit"          → tool_install (resolve+execute) │
│  "Generate a Dockerfile"        → wizard + docker_generate       │
│  "Lock my secrets"              → vault/core (AES-256-GCM)       │
│  "Push secrets to GitHub"       → secrets + git/gh_api           │
│  "What's my project made of?"   → audit/l1_classification        │
│  "Is my code healthy?"          → audit/l2_quality + scoring     │
│  "Deploy to K8s"                → k8s_generate + k8s_validate    │
│                                                                  │
│  Services call other services. Never routes.                     │
│  Services produce dicts. Never HTML.                             │
└─────────────┬────────────────────────────────────────────────────┘
              │ reads/writes
              ▼
┌──────────────────────────────────────────────────────────────────┐
│ SYSTEM (filesystem, subprocess, git, package managers)           │
│  Config files, .env, .vault, .state/, subprocess.run(),         │
│  shutil.which(), /etc/os-release, git, gh, docker, kubectl...   │
└──────────────────────────────────────────────────────────────────┘
```

### Why Services, Not Controllers

This is NOT an MVC web app. The web panel is ONE consumer among three
(web, CLI, TUI). Services return plain dicts — they never touch Flask,
never render templates, never access `request`. A service function must
work identically whether called from `routes_audit.py`, `cli/audit.py`,
or a unit test with no server running.

This constraint enables:
- **CLI parity** — every web action has a CLI equivalent using the same logic
- **Testability** — test a service function by calling it with a `Path` argument
- **TUI future** — the terminal UI will call the same functions without any adapter

---

## Domain Relationships

Services don't exist in isolation. The wizard calls docker, K8s, and
terraform generators. The tool installer reads the audit detection engine.
Vault encrypts the secrets that the secrets domain pushes to GitHub.

```
                    ┌─────────────┐
                    │   wizard/   │  The orchestrator — ties everything together
                    └──────┬──────┘
                           │ calls during setup
         ┌────────┬────────┼────────┬──────────┬─────────┐
         ▼        ▼        ▼        ▼          ▼         ▼
     docker_*  k8s_*  terraform_*  ci_*    dns_cdn    pages_*
     generate  generate  generate  compose  ops       engine
     detect    validate                               builder
     ops       ops

                    ┌─────────────┐
                    │   audit/    │  The scanner — knows what's on the machine
                    └──────┬──────┘
                           │ system profile feeds
                    ┌──────▼──────┐
                    │tool_install/│  The provisioner — installs anything
                    └─────────────┘
                      300 recipes
                      adaptive resolution
                      failure remediation

     ┌──────────┐        ┌──────────┐
     │  vault/  │◄──────►│ secrets/ │
     │ encrypt  │ vault  │ push to  │
     │ .env     │ holds  │ GitHub   │
     │ at rest  │ the    │ secrets  │
     └──────────┘ data   └──────────┘

     ┌──────────┐
     │   git/   │  Foundation for sync, auth, GitHub integration
     └──────────┘
       auth state shared with: chat/, ledger/, content_*
```

### Key Domain Interactions

| When the user... | Services involved | How they compose |
|------------------|-------------------|------------------|
| Opens the wizard | `wizard/detect` → calls into `docker_detect`, `k8s_detect`, `terraform_ops`, `git/ops`, `ci_ops` | One scan, all status embedded in response |
| Installs a tool | `audit/l0_detection` → `tool_install/resolver` → `tool_install/execution` | Detection feeds system profile, resolver picks method, executor runs commands |
| Locks a secret | `vault/core` encrypts with AES-256-GCM, secure-deletes plaintext | Standalone — no other service involved |
| Pushes secrets to GitHub | `secrets/ops` reads `.env`, classifies keys, calls `git/gh_api` for `gh secret set` | Vault must be unlocked first, secrets reads the decrypted `.env` |
| Generates CI workflow | `wizard/setup_ci` → `generators/github_workflow` | Wizard collects user choices, generator produces YAML |
| Scans code quality | `audit/l1_classification` + `audit/l2_quality` + `audit/scoring` | L1 parses manifests, L2 analyzes AST, scoring computes composites |
| Generates K8s manifests | `wizard/setup_infra` → `k8s_generate` + `k8s_validate` | Wizard collects config, generator writes YAML, validator checks it |

---

## Domain Architecture

Each domain follows the same structural principles, whether it's already
packaged into a folder or still flat:

### The Service Contract

Every service function follows these rules:

1. **Input**: `(project_root: Path, ...)` — the project path is always explicit, never global
2. **Output**: `dict` with `ok: bool` for operations, or structured data for queries
3. **Error handling**: return `{"ok": False, "error": "..."}` for expected failures, raise for bugs
4. **Side effects**: clearly identified — subprocess calls, file writes, network access
5. **Lazy imports**: cross-service imports happen inside function bodies to prevent circular chains
6. **Activity recording**: operations that change state record events via `devops_cache`

### Naming Conventions

| Suffix | Meaning | Example |
|--------|---------|---------|
| `_ops.py` | Orchestration — composes lower-level calls | `docker_ops.py` dispatches to detect/generate/containers |
| `_detect.py` | Read-only inspection — returns system/project state | `docker_detect.py` checks daemon, images, containers |
| `_generate.py` | Pure generation — produces config files, manifests | `docker_generate.py` creates Dockerfiles |
| `_validate.py` | Input validation — returns error lists | `k8s_validate.py` checks manifest schemas |
| `_common.py` | Shared utilities within a domain | `docker_common.py` has shared constants |

### The Lazy Import Pattern

Services import from each other **inside function bodies**, not at module top.
This is intentional — it prevents circular import chains and keeps each service
bootable even if optional dependencies are broken:

```python
# ✅ Correct — lazy import inside function
def wizard_docker_status(root: Path) -> dict:
    try:
        from src.core.services.docker_ops import docker_status
        return docker_status(root)
    except Exception:
        return {"available": False}

# ❌ Wrong — top-level cross-service import
from src.core.services.docker_ops import docker_status  # circular risk
```

The wizard uses this pattern for all 15 of its status calls. The audit
engine uses it for all L2 risk data sources. It's not a workaround —
it's the intentional decoupling strategy.

---

## Packaged Domains

These domains have been refactored into folders with `__init__.py`
re-exports, internal SRP splits, and documentation.

### [audit/](audit/README.md) — The Scanner

The multi-layered code analysis engine. Scans the machine (L0), classifies
dependencies (L1), analyzes code quality and risks (L2), and computes
composite scores with trend tracking. 450+ library catalog, 35 CLI
tool probes, 8 manifest parsers. The L0 system profile is the foundation
that `tool_install` builds on for platform-adaptive installs.

### [tool_install/](tool_install/README.md) — The Provisioner

Adaptive provisioning engine for 300+ tools. Reads a recipe, reads the
system profile, resolves dependencies transitively, picks the right
install method per platform, produces an executable plan, and runs it
with streaming output, failure detection, and remediation options.
6 internal layers (L0 data → L5 orchestration).

### [git/](git/README.md) — The Git Interface

Everything that touches `git` or `gh` CLI. SSH/HTTPS auth detection with
agent management, GitHub device-flow authentication (PTY-based state
machine), repository operations, PR/Actions queries. Auth state cached
at module level — unlock once per server start.

### [vault/](vault/README.md) — The Secrets Safe

AES-256-GCM encryption for `.env` files. Lock/unlock with passphrase
sessions, auto-lock on inactivity (configurable timer), progressive
rate limiting on failed unlock attempts (30s → 5min → 15min). Plus
full `.env` CRUD — key management, sections, templates, multi-environment
activation.

### [secrets/](secrets/README.md) — The Secrets Bridge

Pushes local `.env` values to GitHub Secrets and Variables via `gh` CLI.
Automatic classification: keys matching `SECRET`, `TOKEN`, `PASSWORD`
patterns go to `gh secret set`, everything else goes to `gh variable set`.
Generates cryptographic values (passwords, SSH keys, TLS certs).

### [wizard/](wizard/README.md) — The Setup Experience

Three-phase setup flow: detect (scan machine + project → pre-populated
forms), validate (check inputs before generation), generate (write
Dockerfiles, CI workflows, K8s manifests, Terraform scaffolding, DNS
zones, proxy configs). One dispatch endpoint, eight handlers. The
detection response embeds status from 15 other services so the
frontend never needs follow-up calls.

### chat/ — Conversation Persistence

Git-backed chat synchronization. Stores conversation threads, manages
references between chat messages and code artifacts, syncs via git
push/pull with conflict resolution. Depends on `git/auth` for SSH
agent state.

### generators/ — Code Generators

GitHub workflow generation with stack-aware templates (Python, Go, Node,
Rust, Ruby, Elixir). Produces valid YAML via `yaml.dump()`, not string
concatenation. Consumed by `wizard/setup_ci` and the CLI.

### ledger/ — Work Tracking

Activity ledger and git worktree management. Tracks what happened when
(tool installs, config changes, deployments) for the activity feed.

### trace/ — Execution Tracing

Records command execution traces for debugging. Captures subprocess
calls, timing, output, and exit codes for replay and post-mortem analysis.

### [ci/](ci/README.md) — The CI Intelligence Layer

Detects 7 CI providers by scanning signature files, parses GitHub Actions
and GitLab CI workflow YAML (triggers, jobs, steps, issues), analyzes
per-module CI coverage using stack markers, and generates individual
workflows. The compose module takes full wizard state and produces
coherent multi-domain pipelines (test → build → deploy → post-deploy)
in unified or split strategies.

### pages_builders/ — Static Site Builders

Builder framework for static site generation. Docusaurus and Hugo
builders with template support, build optimization, and theme
architecture. Used by the Pages pipeline for site deployment.

---

## Flat Domains (Awaiting Refactor)

These groups are still flat `prefix_*.py` files at the `services/` root.
Each will become its own folder during the ongoing refactor. They work
correctly — they just don't have the folder structure yet.

| Domain | What It Does |
|--------|-------------|
| **k8s_\*** (12 files) | Kubernetes cluster ops, manifest generation, Helm charts, validation (includes `k8s_validate.py` at 4,004 lines — the largest file in the codebase) |
| **docker_\*** (6 files) | Docker container lifecycle, daemon detection, Dockerfile generation, K8s bridge |
| **content_\*** (9 files) | Content file management — CRUD, encryption, optimization (image/video), releases |
| **backup_\*** (5 files) | Archive creation, restoration, extras management |
| **devops_\*** + env_\* (4 files) | Activity tracking, dashboard cache, environment/infra operations |
| **security_\*** (4 files) | Security scanning, posture assessment, common utilities |
| **pages_\*** (6 files) | Pages engine, build streaming, CI integration, discovery |
| **terraform_\*** (3 files) | Terraform actions, HCL generation, ops |
| **testing_\*** (2 files) | Test execution and reporting |
| **docs_\*** (2 files) | Documentation generation and ops |
| **package_\*** (2 files) | Package management actions (pip-audit, outdated checks) |
| **dns_cdn_ops** (1 file) | DNS record generation, CDN/proxy configuration |
| **quality_ops** (1 file) | Code quality analysis |
| **metrics_ops** (1 file) | Metrics collection |

### Cross-Cutting Utilities (remain at root)

These are service-wide utilities used by multiple domains. They don't
belong to any single domain:

| File | What It Does |
|------|-------------|
| `detection.py` | OS/environment detection shared across services |
| `event_bus.py` | Event pub/sub for cross-service communication |
| `project_probes.py` | Project structure probing — language, framework, config detection |
| `config_ops.py` | Configuration file CRUD (`project.yml`, `devops_prefs.json`) |
| `identity.py` | Machine/user identity |
| `run_tracker.py` | Command execution tracking |
| `staleness_watcher.py` | File staleness tracking for cache invalidation |
| `terminal_ops.py` | Terminal session management |
| `md_transforms.py` | Markdown transformation utilities |

---

## Backward Compatibility — Re-Export Shims

When a domain gets refactored from flat files into a folder, the old
file paths become thin shims that re-import from the new location.
This means existing consumers (routes, CLI, other services) don't break:

```python
# services/vault.py (9 lines) — the shim
from src.core.services.vault.core import (     # ← re-export from package
    lock_vault, unlock_vault, vault_status, ...
)

# Consumer code — unchanged, still works
from src.core.services.vault import lock_vault
```

New code should import from the package directly. Shims exist for
backward compatibility during the refactor — they'll be cleaned up
once all consumers are migrated.

---

## Refactor Status

The codebase is being restructured from ~80 flat files into domain
folders. Progress is tracked in `.agent/plans/refactor/`:

- **[Progress Tracker](../../.agent/plans/refactor/02-progress-tracker.md)** — per-domain status
- **[Revolution Plan](../../.agent/plans/refactor/01-revolution-plan.md)** — execution order and rules

**Done**: audit, git, vault, secrets, wizard, tool_install/data (recipes, remediation_handlers, tool_failure_handlers)
**Next**: ci, routes, frontend scripts
