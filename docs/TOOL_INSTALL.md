# Tool Install System

> Automated tool installation with recipes, platform detection, failure
> remediation, and rollback support.

---

## Overview

The tool-install system manages the installation of CLI tools required by
the DevOps Control Plane. When the Audit system detects a missing tool
(e.g., `docker`, `kubectl`, `terraform`), the tool-install system can:

1. **Detect** the target platform (OS, architecture, package managers)
2. **Resolve** the best installation method for that environment
3. **Execute** the installation with progress tracking
4. **Verify** the tool is working after installation
5. **Remediate** failures automatically when possible
6. **Rollback** if installation leaves the system in a bad state

---

## How It Works

```
Missing tool detected (by Audit L0)
        │
        ▼
   ┌─────────┐
   │ Resolver │  Select best recipe for this platform
   └────┬────┘
        │
        ▼
   ┌─────────────┐
   │ Plan Builder │  Build ordered install steps with deps
   └──────┬──────┘
          │
          ▼
   ┌────────────┐
   │  Executor  │  Run steps, track progress, verify
   └─────┬──────┘
         │
    ┌────┴────┐
    │ Success │ → Verify tool works → Done
    │ Failure │ → Remediation handler → Retry or rollback
    └─────────┘
```

---

## Recipes

A **recipe** defines how to install a tool on a specific platform.
Recipes are organized by domain:

```
data/recipes/
├── core/              # Essential system tools
│   ├── shell.py       #   jq, ripgrep, fd, bat, eza, fzf
│   └── system.py      #   curl, wget, git, make
│
├── languages/         # Programming language runtimes
│   ├── jvm.py         #   java, gradle, maven
│   ├── ruby.py        #   ruby, bundler, gem
│   └── wasm.py        #   wasm toolchains
│
├── devops/            # DevOps tooling
│   ├── containers.py  #   docker, docker-compose, podman, buildx
│   ├── k8s.py         #   kubectl, helm, helmfile, k9s, kustomize
│   ├── monitoring.py  #   prometheus, grafana
│   ├── cicd.py        #   act, argocd-cli, gh
│   └── cloud.py       #   aws-cli, az-cli, gcloud
│
├── security/          # Security tools
│   ├── scanners.py    #   trivy, grype, semgrep, snyk, gitleaks
│   └── crypto.py      #   mkcert, step-cli, age
│
├── data_ml/           # Data and ML
│   ├── databases.py   #   psql, mongosh, redis-cli, sqlite3
│   ├── data_packs.py  #   data processing tools
│   ├── gpu.py         #   CUDA, GPU toolchains
│   └── ml.py          #   ML frameworks
│
├── network/           # Network tools
│
└── specialized/       # Specialized tools
    ├── devtools.py    #   tmux, starship, zoxide
    ├── build_tools.py #   cmake, ninja, meson
    ├── media_docs.py  #   ffmpeg, pandoc, imagemagick
    └── config.py      #   Configuration tools
```

Each recipe specifies:
- **Platform conditions** — which OS/arch/package managers it supports
- **Install steps** — ordered commands to run
- **Verification** — how to check the tool was installed correctly
- **Dependencies** — other tools that must be installed first

---

## Remediation Handlers

When installation fails, **remediation handlers** analyze the error and
attempt corrective action:

```
data/remediation_handlers/        # 25 handlers
data/tool_failure_handlers/       # 13 tool-specific failure handlers
```

Remediation strategies include:
- **Retry with different method** — try an alternative recipe
- **Fix prerequisites** — install missing system dependencies first
- **Clear caches** — purge corrupted package caches
- **Adjust permissions** — fix file/directory permission issues
- **Rollback** — undo partial installations

---

## Architecture

```
src/core/services/tool_install/
├── __init__.py              # Public API
├── path_refresh.py          # PATH refresh after installation
│
├── detection/               # Platform analysis
│   ├── environment.py       #   OS, distro, package managers
│   ├── hardware.py          #   CPU architecture, memory
│   ├── network.py           #   Network availability
│   ├── tool_version.py      #   Installed tool version detection
│   ├── system_deps.py       #   System dependency checking
│   ├── recipe_deps.py       #   Recipe dependency resolution
│   ├── install_failure.py   #   Failure analysis
│   ├── service_status.py    #   Service health checking
│   ├── condition.py         #   Platform condition evaluation
│   └── deep.py              #   Extended detection
│
├── resolver/                # Method selection
│   ├── plan_resolution.py   #   Build install plan from recipe
│   ├── method_selection.py  #   Choose best install method
│   ├── choice_resolution.py #   Resolve user choices
│   ├── dependency_collection.py # Collect all dependencies
│   └── dynamic_dep_resolver.py  # Runtime dependency resolution
│
├── domain/                  # Business logic
│   ├── dag.py               #   Dependency graph ordering
│   ├── risk.py              #   Installation risk assessment
│   ├── rollback.py          #   Rollback support
│   ├── restart.py           #   Service restart management
│   ├── remediation_planning.py # Failure remediation
│   ├── handler_matching.py  #   Match failures to handlers
│   ├── error_analysis.py    #   Error classification
│   ├── input_validation.py  #   Input sanitization
│   ├── download_helpers.py  #   File download utilities
│   └── version_constraint.py #  Version comparison/matching
│
├── execution/               # Runtime
│   ├── step_executors.py    #   Execute install steps
│   ├── subprocess_runner.py #   Subprocess management
│   ├── plan_state.py        #   Track plan progress
│   ├── chain_state.py       #   Multi-step chain state
│   ├── config.py            #   Execution configuration
│   ├── backup.py            #   Pre-install backups
│   ├── download.py          #   File downloads
│   ├── build_helpers.py     #   Build-from-source support
│   ├── offline_cache.py     #   Offline package caching
│   ├── script_verify.py     #   Script verification
│   └── tool_management.py   #   Tool lifecycle management
│
├── orchestration/           # End-to-end flow
│   ├── orchestrator.py      #   Install orchestrator
│   └── stream.py            #   SSE progress streaming
│
└── data/                    # Static data
    ├── constants.py         #   System constants
    ├── profile_maps.py      #   Platform profiles
    ├── recipe_schema.py     #   Recipe validation schema
    ├── restart_triggers.py  #   Post-install restart triggers
    ├── undo_catalog.py      #   Rollback recipes
    ├── cuda_matrix.py       #   CUDA version compatibility
    ├── recipes/             #   44 recipe modules (by domain)
    ├── remediation_handlers/#   25 error-specific handlers
    └── tool_failure_handlers/ # 13 tool-specific failure handlers
```

---

## Tool Specification Sheets

Each tool has a comprehensive spec sheet in `docs/tool_install/tools/`:

- **94 tool specs** covering all supported tools
- ~17,600 total lines of documentation
- Each spec includes: identity, recipe coverage, verification methods,
  remediation strategies, scenario coverage, and data shapes

See `docs/tool_install/tools/<tool-id>.md` for any specific tool.

---

## Integration Points

| Consumer | How It Uses tool_install |
|----------|------------------------|
| **Audit Tab** | Detects missing tools → offers install buttons |
| **CLI** | `./manage.sh audit install` for headless installation |
| **Web Routes** | `/api/audit/install-plan/*` endpoints |
| **Wizard** | Suggests tool installations during setup |

---

## See Also

- [AUDIT.md](AUDIT.md) — Audit system (triggers tool detection)
- [STACKS.md](STACKS.md) — Stack definitions (declare tool requirements)
- `docs/tool_install/tools/` — Individual tool specification sheets
