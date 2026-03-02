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

### [ci/](ci/README.md) — The CI Intelligence Layer

Detects 7 CI providers by scanning signature files, parses GitHub Actions
and GitLab CI workflow YAML (triggers, jobs, steps, issues), analyzes
per-module CI coverage using stack markers, and generates individual
workflows. The compose module takes full wizard state and produces
coherent multi-domain pipelines (test → build → deploy → post-deploy)
in unified or split strategies.

### [docker/](docker/README.md) — The Docker Engine

Docker container lifecycle, daemon detection, Dockerfile generation,
image management, and Kubernetes bridge. 6 files covering detection
(daemon, images, containers), generation (multi-stage Dockerfiles with
stack-aware templates), and orchestration (compose, bridge to K8s).

### [k8s/](k8s/README.md) — The Kubernetes Engine

Kubernetes cluster operations, manifest generation (Deployments, Services,
Ingresses, ConfigMaps, Secrets, HPAs), Helm chart scaffolding, validation
with 50+ check rules, and cluster status monitoring. The largest domain
in the codebase (19 files, 8,600+ lines).

### [content/](content/README.md) — Content Management

Content file management — CRUD operations, per-file encryption (AES-256-GCM),
image/video optimization (resize, compress, format conversion), release
artifact management, and bulk operations. 10 files covering the full
content lifecycle from creation to encrypted backup.

### [backup/](backup/README.md) — Archive & Restore

Archive creation with selective inclusion, restoration with conflict
resolution, extras management (supplementary files outside the main
content tree). 6 files covering the complete backup lifecycle.

### [terraform/](terraform/README.md) — Terraform Operations

Terraform actions (init, plan, apply, destroy), HCL generation for
common cloud patterns (AWS, GCP, Azure), and ops orchestration.
4 files, 1,463 lines.

### [security/](security/README.md) — Security Analysis

Security scanning (dependency vulnerabilities, secret detection,
configuration auditing), posture assessment with scoring, and common
utilities. 5 files covering multi-layer security analysis.

### [dns/](dns/README.md) — DNS & CDN

DNS record generation and CDN/proxy configuration. Produces zone files,
CNAME records, and reverse-proxy configs for Nginx/Caddy/Traefik.

### [env/](env/README.md) — Environment & Infrastructure

Two layers: (1) `.env` file detection, parsing, comparison, validation,
and generation, (2) IaC provider detection (Terraform, Kubernetes,
Pulumi, CloudFormation, Ansible) with resource inventory. Both feed
the dashboard environment card.

### [pages/](pages/README.md) — Pages Engine

Static site pipeline — discovery, build orchestration with streaming
output, CI integration (GitHub Pages deployment), and multi-builder
support (Docusaurus, Hugo via `pages_builders/`).

### [docs_svc/](docs_svc/README.md) — Documentation Generation

Documentation generation and ops — README scaffolding, API doc extraction,
and documentation quality analysis.

### [quality/](quality/README.md) — Code Quality

Code quality analysis — linter/formatter/typechecker detection, tool
configuration parsing, and quality scoring across stacks.

### [testing/](testing/README.md) — Test Analysis

Test framework detection (pytest, unittest, jest, vitest, go test,
cargo test), test inventory, and coverage measurement via multi-strategy
waterfall (pytest-cov → coverage.py → heuristic).

### [metrics/](metrics/README.md) — Project Health

Unified project health scoring with 7 probes (git, docker, CI, packages,
env, quality, structure). Produces a 0–100 score with letter grade,
per-probe findings, and prioritized recommendations.

### [packages_svc/](packages_svc/README.md) — Package Management

Multi-ecosystem package management — detects 9 package managers
(pip, npm, go, cargo, Maven, Gradle, .NET, Mix, Bundler), checks
outdated packages, runs security audits, lists installed packages,
and provides install/update actions.

### [devops/](devops/README.md) — Activity & Dashboard

Activity tracking and dashboard cache management. Records DevOps events,
maintains cached status for the dashboard cards, and provides the
activity log timeline.

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

### pages_builders/ — Static Site Builders

Builder framework for static site generation. Docusaurus and Hugo
builders with template support, build optimization, and theme
architecture. Used by the Pages pipeline for site deployment.

---

## Cross-Cutting Utilities

These are service-wide utilities used by multiple domains. They don't
belong to any single domain and remain as flat files at the `services/`
root:

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
| `audit_helpers.py` | Shared audit utilities (`make_auditor`) |
| `tool_requirements.py` | Tool requirement checking for missing CLI tools |

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

The codebase has been restructured from ~80 flat files into 27 domain
folders. Progress is tracked in `.agent/plans/refactor/`:

- **[Progress Tracker](../../.agent/plans/refactor/02-progress-tracker.md)** — per-domain status
- **[README Audit](../../.agent/plans/refactor/readme-audit.md)** — per-domain README verification

**All 27 domain packages** are complete with `__init__.py` re-exports,
internal SRP splits, backward-compat shims, and audited README documentation.

