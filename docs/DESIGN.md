# Solution Control Plane — Design Document

> **Status:** Living document — reflects design philosophy and product direction.
> **Note:** For the current file layout, see [ARCHITECTURE.md](ARCHITECTURE.md).

---

## 1. Vision

Build a **general-purpose project control plane** — a platform that manages
project infrastructure, modules, stacks, and integrations through a unified
domain model.

The control plane is **not an application**. It is a *meta-tool*: a structured
way to discover what a solution is, what it needs, and how to act on it —
through any interface (CLI, Web, TUI), backed by pluggable tool bindings.

### What it replaces

The fragmented reality of most projects:
- Scattered shell scripts with duplicated logic
- Manual environment and secrets management
- Tool-specific knowledge locked in people's heads
- No unified view of project state
- No guided setup or evolution path

### What it enables

- **One platform, many interfaces** — CLI, Web Dashboard, and interactive
  terminal all drive the same core
- **Solution visibility** — see your entire project: stacks, environments,
  status, integrations, resources
- **Guided evolution** — detect what's there, suggest what's next
- **Secure by default** — encrypted vaults for secrets and content
- **Progressive complexity** — start simple, grow without refactoring

---

## 2. Core Pillars

These are the product capabilities that define the control plane.

### 2.1 Project Visibility & Observability

See your solution at a glance — what technologies are in use, what state
things are in, what needs attention.

- Technology detection (20 stack definitions)
- Unified project status
- Health checks and diagnostics
- Audit trail of all operations

### 2.2 Integrations

First-class integration with the tools and platforms your project depends on.

- **Git** — status, commit, push, pull, branch management
- **GitHub** — secrets, environments, pull requests, Actions, Releases
- **Docker** — container lifecycle management
- **Kubernetes** — orchestration support
- **CI/CD** — workflow triggering, run monitoring
- **Extensible** — pluggable adapter protocol for any new tool

### 2.3 Vaults

Two distinct vault systems for two different security concerns:

- **Secret / Variable Vault** — AES-256-GCM encrypted `.env` files,
  environment-specific configs, key CRUD, GitHub Secrets sync, auto-lock
  on inactivity, portable export/import
- **Content Vault** — per-file encryption for sensitive media and documents,
  binary envelope format, inline preview in the web admin

### 2.4 Project & Environment Management

Manage the project lifecycle — its configuration, environments,
documentation, and data safety.

- **Environment management** — create, switch, compare configurations
  across dev/staging/production
- **Backup system** — create, restore, export, and archive project state
- **Documentation sites** — build and deploy with 6 SSG builders
  (Docusaurus, MkDocs, Hugo, Sphinx, Raw, Custom)
- **Content management** — file browser, media optimization, GitHub Release
  uploads for large assets

### 2.5 Solution Evolution & Augmentation

The platform helps evolve your solution — not just manage what exists.

- Detect technologies and their versions
- Identify integration opportunities
- Analyze project structure and gaps
- Guide augmentation with new stacks and capabilities

### 2.6 Setup Wizard

Guided, step-by-step setup for configuring a project, its environments,
its secrets, and its integrations. Reduces onboarding from hours to minutes.

### 2.7 Debugging

Built-in debugging tools for diagnosing issues with the project, its
integrations, and its environment — accessible from the web dashboard.

### 2.8 Resource Links

Quick access to remote interfaces and resources — repositories, dashboards,
CI pipelines, deployed environments, monitoring. Everything your project
connects to, linked from one place.

### 2.9 Multi-Module & Multi-Stack

Handles the complexity of real-world solutions:

- Mono-repos with multiple services and modules
- Multiple technology stacks within a single solution
- Complex project structures with nested modules

---

## 3. Three-Interface Parity

Every capability is accessible from all three interfaces. They are
**functionally equivalent** — all driving the same core services.

| Interface | How | Best For |
|---|---|---|
| `./manage.sh` | Interactive terminal menu | Daily ops, guided workflows |
| CLI | `python -m src.main <command>` | Scripting, CI, automation |
| Web Dashboard | Flask SPA at localhost | Visual management, content, setup wizard |

**Iron rule:** No business logic in the interface layer. All actions route
through core services. CLI, Web, and manage.sh must remain functionally
equivalent.

---

## 4. Architecture Principles

### 4.1 Everything is a domain object first

If something cannot be expressed as a domain concept (Project, Module,
Stack, Environment, Action), it does not belong in the system.

### 4.2 Thin interfaces, thick core

Interface layers (CLI, Web, manage.sh) are thin wrappers. Core services
contain all domain logic and are channel-independent.

### 4.3 Dependency direction

```
Interfaces (ui/)  →  Core Services  →  Adapters
                         ↓
                      Models (shared types)
```

Core never imports from interfaces. Interfaces never skip core to call
adapters directly.

### 4.4 Pluggable integrations

New tools and platforms are added via the adapter protocol. No core changes
required — implement the adapter interface and register it.

### 4.5 Security by default

Sensitive data is encrypted at rest (AES-256-GCM). Vaults auto-lock on
inactivity. Secrets are masked in all interfaces.

---

## 5. Technology Choices

| Component | Technology | Why |
|---|---|---|
| Language | Python 3.12+ | Ecosystem breadth, proven in production |
| Models | Pydantic 2+ | Validation, serialization |
| CLI | Click 8+ | Composable command groups |
| Web | Flask 3+ | Blueprint architecture, local-only SPA |
| Templates | Jinja2 3+ | Web rendering and file generation |
| Config | YAML (PyYAML) | Human-readable configuration |
| Env | python-dotenv | .env loading |
| Test | pytest | Comprehensive test suite |
| Lint | ruff | Fast, comprehensive |
| Frontend | Vanilla JS | Zero npm dependencies, no build step |

---

## 6. The Pattern: Detect → Observe → Facilitate → Act

Every integration in the platform follows the same four-phase pattern:

1. **Detect** — Is it in the project? What version? What configuration?
2. **Observe** — What's its current state? What's healthy, what's broken?
3. **Facilitate** — Can we generate configs? Suggest improvements? Fill gaps?
4. **Act** — Provide the tools to operate it: build, deploy, manage, fix.

This pattern applies universally — from Git to Kubernetes, from secrets
to monitoring. Each integration deepens over time through these four phases.

---

## 7. Final Product Vision

The fully realized Solution Control Plane provides total solution intelligence
and acts as a universal integration hub.

### 7.1 Integration Matrix

Every integration is developed through the Detect → Observe → Facilitate → Act
pattern to full depth:

**Docker**
- Detect Dockerfiles, compose configs, .dockerignore
- Observe running containers, images, volumes, resource usage, logs
- Generate Dockerfiles from detected stacks, compose files from modules,
  suggest multi-stage builds
- Build, push to registry, start/stop/restart, view logs, exec, prune

**Kubernetes**
- Detect manifests, helm charts, kustomize
- Observe deployments, pods, services, ingresses, health
- Generate manifests from Docker setup, helm charts, suggest resource limits
- Apply, rollback, scale, port-forward, view pod logs

**CI/CD**
- Detect workflow files across providers (GitHub Actions, GitLab CI, etc.)
- Observe pipeline runs, test results, coverage, artifacts
- Generate workflows from detected stacks, suggest test/deploy steps
- Trigger, cancel, re-run, download artifacts

**Cloud Infrastructure**
- Detect AWS/GCP/Azure/Terraform configs
- Observe deployed resources, costs, health
- Generate infrastructure-as-code from needs
- Plan, apply, destroy

**Databases**
- Detect connection strings, ORMs, migration files
- Observe connection health, migration state, schema
- Generate migrations, suggest indexes
- Migrate, rollback, seed, backup

**Package Management**
- Detect dependency files across all stacks
- Observe outdated packages, vulnerabilities, licenses
- Suggest updates, find alternatives
- Install, update, audit, lock

**Monitoring**
- Detect prometheus/grafana/alerting configs
- Observe metrics, alerts, uptime
- Generate dashboards, suggest alert rules
- Configure, silence, acknowledge

**Security**
- Detect exposed secrets, misconfigs, vulnerabilities
- Observe security posture, compliance
- Suggest fixes, generate security configs
- Rotate secrets, fix vulnerabilities, update permissions

**Testing**
- Detect test frameworks and coverage
- Observe results, coverage trends, flaky tests
- Generate test templates, suggest cases
- Run, report, track

**DNS / CDN**
- Detect domain configs, CDN settings
- Observe records, SSL status
- Generate configs, suggest caching
- Update records, purge cache, renew certs

**Documentation**
- Detect docs, README, API specs
- Observe coverage, staleness, broken links
- Generate docs from code, generate API docs
- Build, deploy, validate

### 7.2 Platform Intelligence

Cross-cutting intelligence that works across all integrations:

- **Cross-integration analysis** — *"Your Docker image uses Python 3.11 but
  CI tests on 3.10"*
- **Gap detection** — *"You have Docker but no K8s — here's the path"*
- **Drift detection** — *"Staging is 3 secrets behind production"*
- **Template library** — community and custom templates for every integration
- **Plugin architecture** — anyone can add new integrations via the adapter
  protocol

### 7.3 Current State

The platform today covers:

| Integration | Detect | Observe | Facilitate | Act |
|---|---|---|---|---|
| Git | ✅ | ✅ | — | ✅ |
| GitHub | ✅ | ✅ | — | ✅ |
| Secrets / .env | ✅ | ✅ | ✅ | ✅ |
| Content | ✅ | ✅ | ✅ | ✅ |
| Pages / SSG | ✅ | ✅ | ✅ | ✅ |
| Backups | ✅ | ✅ | — | ✅ |
| Docker | ✅ | — | — | — |
| Kubernetes | ✅ | — | — | — |
| CI/CD | partial | partial | — | partial |
| Stacks (20) | ✅ | — | — | — |

Everything else in §7.1 is the growth path.

---

*This document defines what the Solution Control Plane is and where it's
going. For implementation details, see [ARCHITECTURE.md](ARCHITECTURE.md).*

