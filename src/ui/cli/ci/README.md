# CLI Domain: CI — Provider Detection, Workflow Analysis & Generation

> **1 file · 237 lines · 5 commands + 1 subgroup · Group: `controlplane ci`**
>
> Detects CI/CD providers (GitHub Actions, GitLab CI, Jenkins), parses
> and analyzes workflow files for issues, measures module-level CI coverage,
> and generates stack-aware CI/lint workflow files. Complements the
> runtime GitHub Actions commands in `cli/git` (`gh runs`, `gh dispatch`)
> with static-analysis and generation capabilities.
>
> Core service: `core/services/ci/ops.py`

---

## How It Works

```
┌──────────────────────────────────────────────────────────────────────┐
│                         controlplane ci                              │
│                                                                      │
│  ┌─ Detect ──┐   ┌─── Observe ───┐   ┌──── Generate ─────┐         │
│  │ status    │   │ workflows     │   │ generate ci       │         │
│  └───────────┘   │ coverage      │   │ generate lint     │         │
│                   └───────────────┘   └───────────────────┘         │
└──────────┬────────────────┬──────────────────┬──────────────────────┘
           │                │                  │
           ▼                ▼                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│                     core/services/ci/ops.py                         │
│                                                                      │
│  ci_status(root)         → has_ci, providers[], total_workflows     │
│  ci_workflows(root)      → workflows[] with jobs, triggers, issues  │
│  ci_coverage(root, mods) → coverage_pct, details per module         │
│  generate_ci_workflow()  → YAML file content                        │
│  generate_lint_workflow() → YAML file content                       │
└──────────────────────────────────────────────────────────────────────┘
```

### Detection-Observe-Generate Pattern

This domain follows the project-wide pattern used across Docker, K8s,
Security, Terraform, Testing, and Quality:

1. **Detect** (`status`) — "is this thing present?"
2. **Observe** (`workflows`, `coverage`) — "analyze what exists"
3. **Generate** (`generate ci`, `generate lint`) — "create config from context"

### Provider Detection

```
Project root
├── .github/workflows/   → GitHub Actions (*.yml, *.yaml)
├── .gitlab-ci.yml       → GitLab CI
├── Jenkinsfile          → Jenkins
└── (other locations)    → Additional providers
```

`ci_status()` scans for CI config files and returns which providers
are detected and how many workflows each has.

### Coverage Analysis

```
coverage(root, modules)
├── For each detected module:
│   ├── Check if any CI workflow references the module
│   │   (by path, test directory, or build step)
│   ├── covered = true  → module has CI
│   └── covered = false → module has no CI + reason why
└── Return overall percentage + per-module breakdown
```

The `coverage` command is unique in that it needs module detection
(project.yml + stack discovery) to know what modules exist.

### Generation Flow

```
generate ci / generate lint
├── _detect_stack_names(project_root)
│   ├── load_project(project.yml)
│   ├── discover_stacks(stacks/)
│   └── detect_modules() → unique stack names
├── generate_ci_workflow(root, stacks, name)  
│   └── → {file: {path, content, reason}}
└── _handle_generated(root, file_data, write)
    ├── --write → write_generated_file() → ✅ Written
    └── no flag → preview content + "(use --write to save)"
```

---

## Commands

### `controlplane ci status`

Show CI/CD integration status: detected providers and workflow count.

```bash
controlplane ci status
controlplane ci status --json
```

**Output example:**

```
⚙️  CI/CD Providers:
   ✅ github_actions (3 workflow(s))

   Total workflows: 3
```

**No-CI output:**

```
⚠️  No CI/CD configuration detected
   Run 'controlplane ci generate ci' to create one
```

---

### `controlplane ci workflows`

Parse and list all CI workflow files with structural analysis.

```bash
controlplane ci workflows
controlplane ci workflows --json
```

**Output example:**

```
🐙 CI Pipeline
   File: .github/workflows/ci.yml
   Triggers: push, pull_request
   📋 build (3 steps, ubuntu-latest)
   📋 test (5 steps, ubuntu-latest)

🐙 Deploy
   File: .github/workflows/deploy.yml
   Triggers: push
   📋 deploy (4 steps, ubuntu-latest)
   ⚠️  Issues (1):
      • No branch protection — deploys on every push
```

**Provider icons:**

| Icon | Provider |
|------|----------|
| 🐙 | GitHub Actions |
| 🦊 | GitLab CI |
| 🏗️ | Jenkins |
| ⚙️ | Other |

**Issue detection:** The core service analyzes workflows for common
problems (missing branch filters, no caching, missing secrets, etc.)
and returns them in the `issues[]` array.

---

### `controlplane ci coverage`

Analyze which project modules have CI coverage.

```bash
controlplane ci coverage
controlplane ci coverage --json
```

**Output example:**

```
📊 CI Coverage: 75%

   ✅ api                       Covered by ci.yml
   ✅ web                       Covered by ci.yml
   ✅ workers                   Covered by deploy.yml
   ❌ docs                      No workflow references this module
```

**How coverage is determined:** Each module is checked against all
workflow files. A module is "covered" if any workflow step references
its path, build command, or test directory. The percentage is
`covered_modules / total_modules * 100`.

**Note:** This command is heavier than others — it loads `project.yml`,
discovers stacks, and runs module detection to know what to check against.

---

### `controlplane ci generate ci`

Generate a GitHub Actions CI workflow from detected stacks.

```bash
# Preview the generated workflow
controlplane ci generate ci

# Write directly to .github/workflows/
controlplane ci generate ci --write
```

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--write` | flag | off | Write to disk (default: preview only) |

**Preview output example:**

```
📄 Preview: .github/workflows/ci.yml
   Reason: Generated from detected stacks: python, node
────────────────────────────────────────────────────────
name: CI
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      ...
────────────────────────────────────────────────────────
   (use --write to save to disk)
```

---

### `controlplane ci generate lint`

Generate a GitHub Actions lint workflow from detected stacks.

```bash
controlplane ci generate lint
controlplane ci generate lint --write
```

Same preview/write pattern as `generate ci`. The lint workflow
is separate from the CI workflow to allow independent scheduling
and faster feedback.

---

## File Map

```
cli/ci/
├── __init__.py    237 lines — group definition + 5 commands + generate subgroup
│                              + _resolve_project_root, _detect_stack_names,
│                              _handle_generated helpers
└── README.md               — this file
```

**Total: 237 lines of Python in 1 file.**

---

## Per-File Documentation

### `__init__.py` — Group + all commands (237 lines)

**Groups:**

| Symbol | Kind | What It Does |
|--------|------|-------------|
| `ci()` | Click group | Top-level `ci` group |
| `generate()` | Click group | `ci generate` subgroup |

**Commands:**

| Symbol | Kind | What It Does |
|--------|------|-------------|
| `status(ctx, as_json)` | command | Detect CI providers, report workflow counts |
| `workflows(ctx, as_json)` | command | Parse workflow files, show jobs/triggers/issues |
| `coverage(ctx, as_json)` | command | Load project modules, check CI coverage per module |
| `gen_ci(ctx, write)` | command (`generate ci`) | Generate CI workflow from stacks |
| `gen_lint(ctx, write)` | command (`generate lint`) | Generate lint workflow from stacks |

**Helpers:**

| Symbol | Kind | What It Does |
|--------|------|-------------|
| `_resolve_project_root(ctx)` | helper | Reads `config_path` from context, falls back to `find_project_file()` |
| `_detect_stack_names(root)` | helper | Loads project + stacks, runs `detect_modules()`, extracts unique stack names |
| `_handle_generated(root, file, write)` | helper | Preview (print content) or write (call `write_generated_file()`) |

**Core service imports (all lazy):**

| Import | From | Used For |
|--------|------|----------|
| `ci_status` | `ci_ops` | Provider detection |
| `ci_workflows` | `ci_ops` | Workflow parsing + analysis |
| `ci_coverage` | `ci_ops` | Module-level CI coverage |
| `generate_ci_workflow` | `ci_ops` | CI workflow YAML generation |
| `generate_lint_workflow` | `ci_ops` | Lint workflow YAML generation |
| `write_generated_file` | `docker_ops` | Write generated files to disk |
| `load_project` | `config.loader` | Load project.yml (for coverage + generate) |
| `discover_stacks` | `config.stack_loader` | Load stack definitions |
| `detect_modules` | `detection` | Module detection for coverage + stack names |

**Note on `docker_ops` import:** `write_generated_file` is a shared utility
that lives in `docker_ops` for historical reasons. It's used by CI, Docker,
Quality, Security, Testing, and Terraform generate commands.

---

## Dependency Graph

```
__init__.py
├── click                      ← click.group, click.command
├── core.config.loader         ← find_project_file (lazy, _resolve_project_root)
│                              ← load_project (lazy, coverage + generate)
├── core.config.stack_loader   ← discover_stacks (lazy, coverage + generate)
├── core.services.detection    ← detect_modules (lazy, coverage + generate)
├── core.services.ci_ops       ← ci_status, ci_workflows, ci_coverage,
│                                generate_ci_workflow, generate_lint_workflow
└── core.services.docker_ops   ← write_generated_file (lazy, _handle_generated)
```

---

## Consumers

### Who registers this CLI group

| Layer | Module | What It Does |
|-------|--------|-------------|
| CLI entry | `src/main.py:454` | `from src.ui.cli.ci import ci` |

### Who also uses the same core service

| Layer | Module | Core Service Used |
|-------|--------|------------------|
| Web routes | `routes/ci/` | `ci_ops` (status, workflows, coverage) |
| Core | `metrics/ops.py:132` | `ci_status`, `ci_workflows` (health probe input) |
| Core | `k8s/validate_cross_domain.py` | `ci_status`, `ci_workflows` (cross-domain validation) |
| Core | `wizard/helpers.py:121` | `ci_status` (wizard environment detection) |

---

## Design Decisions

### Why coverage needs module detection

CI coverage is per-module, not per-file. To know which modules exist,
the command loads `project.yml`, discovers stacks, and runs module
detection (`detect_modules`). This is heavier than a simple file scan
but gives meaningful coverage percentages.

### Why generate ci and generate lint are separate commands

CI and lint have different concerns (build/test vs. code quality),
different triggers (push/PR vs. PR only), and different runner
requirements. Separating them lets users generate one without the other
and avoids accidentally overwriting a manually-customized lint workflow.

### Why _handle_generated is shared

Both `generate ci` and `generate lint` use the same preview-or-write
logic. The helper in the same file avoids code duplication. The same
pattern appears in cli/docs, cli/security, cli/terraform, and cli/quality.

### Why all code is in __init__.py

With 237 lines and 5 commands, the domain is at the edge of
needing a split. The current layout keeps related CI commands
together for easy scanning. If a 6th+ command were added
(e.g., `ci deploy`, `ci artifacts`), a split into detect.py,
observe.py, and generate.py would be appropriate.

### Why provider icons differ

Each CI provider gets a recognizable icon (🐙 GitHub, 🦊 GitLab,
🏗️ Jenkins) to make multi-provider setups scannable at a glance.

---

## Relationship to `cli/git`

The CI and Git domains share the same external system (GitHub) but serve
different purposes:

| Concern | CLI Domain | What It Does |
|---------|-----------|-------------|
| **Static analysis** | `cli/ci` | Parse workflow YAML, check coverage, detect issues |
| **Generation** | `cli/ci` | Generate new CI/lint workflows from stacks |
| **Runtime actions** | `cli/git` | List runs, trigger dispatches, list workflows |
| **PR management** | `cli/git` | List pull requests |

The boundary is: `cli/ci` works with **files on disk** (workflow YAML),
while `cli/git gh *` works with the **GitHub API** (live runs, PRs).

A typical workflow:
1. `controlplane ci generate ci --write` → create workflow file
2. `git commit` + `git push` → push it to GitHub
3. `controlplane git gh runs` → observe the running workflow
4. `controlplane ci workflows` → analyze the workflow structure locally

---

## JSON Output Examples

### `ci status --json`

```json
{
  "has_ci": true,
  "providers": [
    {"name": "github_actions", "workflows": 3, "path": ".github/workflows/"}
  ],
  "total_workflows": 3
}
```

### `ci workflows --json`

```json
{
  "workflows": [
    {
      "name": "CI Pipeline",
      "file": ".github/workflows/ci.yml",
      "provider": "github_actions",
      "triggers": ["push", "pull_request"],
      "jobs": [
        {"name": "build", "steps_count": 3, "runs_on": "ubuntu-latest"},
        {"name": "test", "steps_count": 5, "runs_on": "ubuntu-latest"}
      ],
      "issues": ["No caching configured for dependencies"]
    }
  ]
}
```

### `ci coverage --json`

```json
{
  "coverage_pct": 75,
  "details": {
    "api": {"covered": true, "reason": "Covered by ci.yml"},
    "web": {"covered": true, "reason": "Covered by ci.yml"},
    "workers": {"covered": true, "reason": "Covered by deploy.yml"},
    "docs": {"covered": false, "reason": "No workflow references this module"}
  }
}
```
