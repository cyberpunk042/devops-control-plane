# CI Routes — Workflow Analysis & Generation API

> **3 files · 88 lines · 5 endpoints · Blueprint: `ci_bp` · Prefix: `/api`**
>
> Thin HTTP wrappers over `src.core.services.ci.ops`.
> These routes expose CI/CD pipeline inspection: detected providers (GitHub
> Actions, GitLab CI, CircleCI, etc.), parsed workflow files with structural
> analysis and issue detection, module-level coverage analysis, and automated
> workflow generation (CI and lint) from detected technology stacks.
> All handlers are pure delegation — the route layer adds only caching
> via `devops_cache.get_cached()` on the status endpoint.

---

## How It Works

### Request Flow

```
Frontend (scripts/integrations/)
│
└── _cicd.html
     │
     ├── GET  /api/ci/status        → which CI providers are detected?
     │                                how many workflow files?
     │
     ├── GET  /api/ci/workflows     → parse and analyse every workflow file
     │                                return jobs, triggers, steps, issues
     │
     ├── GET  /api/ci/coverage      → which modules have CI coverage?
     │                                stack-based marker detection
     │
     ├── POST /api/ci/generate/ci   → generate CI workflow YAML
     │                                from detected stacks
     │
     └── POST /api/ci/generate/lint → generate lint workflow YAML
                                      from detected stacks
     │
     ▼
routes/ci/                              ← HTTP layer (this package)
├── status.py   — status (cached), workflows, coverage
└── generate.py — generate CI, generate lint
     │
     ▼
core/services/ci/ops.py (593 lines)    ← Business logic
├── ci_status()              — detect providers, count workflows
├── ci_workflows()           — parse workflow YAML, extract structure
├── ci_coverage()            — map modules → CI jobs via text markers
├── generate_ci_workflow()   — compose CI workflow from stacks
└── generate_lint_workflow() — compose lint workflow from stacks
     │
     ├── ci/compose.py        — workflow YAML composition engine
     └── via shim: core/services/ci_ops.py (backward-compat re-export)
```

### Provider Detection

```
ci_status(project_root)
     │
     ▼
Scan for known CI config locations:
     │
     ├── .github/workflows/*.yml   → GitHub Actions
     ├── .github/workflows/*.yaml  → GitHub Actions
     ├── .gitlab-ci.yml            → GitLab CI
     ├── .circleci/config.yml      → CircleCI
     ├── Jenkinsfile               → Jenkins
     ├── .travis.yml               → Travis CI
     ├── azure-pipelines.yml       → Azure Pipelines
     ├── bitbucket-pipelines.yml   → Bitbucket Pipelines
     └── .drone.yml                → Drone CI
                                      │
                                      ▼
                              { providers: [...], total_workflows: N }
```

### Coverage Analysis Pipeline

```
ci_coverage(project_root)
     │
     ├── 1. Auto-detect project modules (config + filesystem)
     │      → [{name: "docker", path: "docker/", stack_name: "docker"}, ...]
     │
     ├── 2. Gather all CI file contents into one string
     │      _gather_ci_content() → concatenated YAML text
     │
     ├── 3. For each module, check stack-based markers:
     │      _STACK_CI_MARKERS = {
     │          "python": ["pytest", "ruff", "mypy", "pip install"],
     │          "node":   ["npm test", "jest", "vitest"],
     │          "docker": ["docker build", "docker-compose"],
     │          "k8s":    ["kubectl", "helm"],
     │          "terraform": ["terraform plan", "terraform apply"],
     │          ...8 more stacks
     │      }
     │
     └── 4. Return coverage report:
            covered[], uncovered[], coverage_pct, details{}
```

### Caching Pattern

```
GET /api/ci/status
     │
     ├── ?bust=1  → force=True → bypass cache
     │
     ▼
devops_cache.get_cached(root, "ci", lambda: ci_ops.ci_status(root), force=force)
     │
     ├── Cache HIT  → return cached dict immediately
     │               (filesystem scan is expensive)
     │
     └── Cache MISS → call ci_ops.ci_status(root)
                      → scan 9 provider directories
                      → count workflow files
                      → store result → return
```

Only the `/ci/status` endpoint uses caching. Workflows and coverage
compute fresh every time (they read files that may have changed).
Generation endpoints are POST and never cached.

### Workflow Analysis Pipeline

```
ci_workflows(project_root)
     │
     ├── For each detected provider:
     │
     ├── GitHub Actions:
     │   └── _parse_github_workflow(path)
     │       ├── Parse YAML
     │       ├── Extract: name, triggers, jobs, steps, runs_on, matrix
     │       └── _audit_github_workflow(data)
     │           ├── Check for pinned actions (with SHA)
     │           ├── Check for deprecated features
     │           └── Return issues[]
     │
     └── GitLab CI:
         └── _parse_gitlab_ci(path)
             ├── Parse YAML
             └── Extract: stages, jobs, image, services, rules
```

---

## File Map

```
routes/ci/
├── __init__.py     18 lines  — blueprint definition + sub-module imports
├── status.py       36 lines  — status (cached), workflows, coverage
├── generate.py     34 lines  — generate CI and lint workflows
└── README.md                 — this file
```

---

## Per-File Documentation

### `__init__.py` — Blueprint Definition (18 lines)

```python
ci_bp = Blueprint("ci", __name__)
from . import status, generate  # noqa: E402, F401
```

Standard blueprint pattern — define, then import sub-modules to
register routes. The circular import guard follows the same pattern
as every other route package.

### `status.py` — CI Status & Analysis (36 lines)

| Function | Method | Route | What It Does |
|----------|--------|-------|-------------|
| `ci_status()` | GET | `/ci/status` | Detected CI providers and workflow count |
| `ci_workflows()` | GET | `/ci/workflows` | Parsed workflow files with structural analysis |
| `ci_coverage()` | GET | `/ci/coverage` | Module-level CI coverage analysis |

**Status with cache busting:**

```python
from src.core.services.devops.cache import get_cached

root = _project_root()
force = request.args.get("bust", "") == "1"  # ?bust=1 → bypass cache
return jsonify(get_cached(
    root, "ci",
    lambda: ci_ops.ci_status(root),
    force=force,
))
```

The `get_cached()` helper stores the result keyed by `("ci", root)`.
The `?bust=1` query param forces a fresh computation — used after
workflow files change or new CI providers are configured. Without
cache busting, status is returned from memory (no filesystem scan).

**Workflows — pure passthrough:**

```python
return jsonify(ci_ops.ci_workflows(_project_root()))
```

No caching, no parameters. The core function:
1. Scans for workflow files (`.github/workflows/*.yml`, `.gitlab-ci.yml`, etc.)
2. Parses each YAML file with safe loader
3. Extracts structural info (name, triggers, jobs, steps, matrix)
4. Audits for common issues (unpinned actions, deprecated features)
5. Returns workflow list with `issues[]` per workflow

**Coverage — pure passthrough:**

```python
return jsonify(ci_ops.ci_coverage(_project_root()))
```

The core function:
1. Auto-detects project modules from config or filesystem
2. Concatenates all CI file contents into searchable text
3. For each module's stack, checks for stack-specific markers
4. Returns coverage percentage and per-module details

### `generate.py` — Workflow Generation (34 lines)

| Function | Method | Route | What It Does |
|----------|--------|-------|-------------|
| `generate_ci()` | POST | `/ci/generate/ci` | Generate CI workflow from detected stacks |
| `generate_lint()` | POST | `/ci/generate/lint` | Generate lint workflow from detected stacks |

Both follow the same pattern:

```python
root = _project_root()
result = ci_ops.generate_ci_workflow(root)  # or generate_lint_workflow

if "error" in result:
    return jsonify(result), 400
return jsonify(result)
```

The core functions:
1. Auto-detect technology stacks (python, node, docker, k8s, terraform, etc.)
2. Compose workflow YAML using `ci/compose.py` (template engine)
3. Write file to `.github/workflows/` directory
4. Return the generated file contents and metadata

**No request body needed:** Generation uses auto-detection. The project's
detected stacks determine what goes into the workflow. No user input
required — the endpoint is a one-click action.

---

## Dependency Graph

```
__init__.py     ← defines ci_bp

status.py
├── ci_bp              ← from __init__
├── ci_ops             ← from core.services (via shim ci_ops.py)
│   └── ci/ops.py      ← real implementation (593 lines)
│       └── ci/compose.py ← workflow YAML composition
├── devops.cache       ← lazy import for get_cached
└── helpers            ← project_root

generate.py
├── ci_bp              ← from __init__
├── ci_ops             ← from core.services (via shim ci_ops.py)
│   └── ci/ops.py      ← real implementation
│       └── ci/compose.py ← workflow composition engine
└── helpers            ← project_root
```

**Import chain detail:**

```
routes/ci/status.py
     └── from src.core.services import ci_ops        # shim (10 lines)
              └── from src.core.services.ci.ops import *  # real logic (593 lines)
                       └── from ci.compose import *       # YAML templates
```

The shim exists because routes were created before the `ci/` domain
folder refactoring. Routes import `ci_ops` (flat name), which
re-exports from `ci.ops` (domain folder).

---

## Consumers

| Layer | Module | What It Uses |
|-------|--------|-------------|
| Server | `ui/web/server.py` | Imports `ci_bp`, registers at `/api` prefix |
| Frontend | `scripts/integrations/_cicd.html` | All 5 endpoints (detection, analysis, generation) |
| Wizard | `scripts/wizard/_integrations.html` | `/ci/status` (integration detection during setup) |
| Dashboard | `scripts/_dashboard.html` | `/ci/status` (CI card on dashboard) |

---

## Service Delegation Map

```
Route Handler       →   Core Service Function
──────────────────────────────────────────────────────────────────
ci_status()         →   devops_cache.get_cached("ci", ...)
                         └→ ci.ops.ci_status()
                              ├→ scan _CI_PROVIDERS (9 providers)
                              └→ count workflow files per provider

ci_workflows()      →   ci.ops.ci_workflows()
                         ├→ _parse_github_workflow() per file
                         │    └→ _audit_github_workflow() per file
                         └→ _parse_gitlab_ci() per file

ci_coverage()       →   ci.ops.ci_coverage()
                         ├→ _auto_detect_modules()
                         ├→ _gather_ci_content()
                         └→ _check_stack_coverage() per module

generate_ci()       →   ci.ops.generate_ci_workflow()
                         ├→ _auto_detect_stack_names()
                         └→ ci.compose.compose_ci_workflows()

generate_lint()     →   ci.ops.generate_lint_workflow()
                         ├→ _auto_detect_stack_names()
                         └→ ci.compose.compose_ci_workflows()
```

---

## Data Shapes

### `/api/ci/status` response

```json
{
    "providers": [
        {
            "id": "github_actions",
            "name": "GitHub Actions",
            "workflows": 3,
            "path": ".github/workflows"
        }
    ],
    "total_workflows": 3,
    "has_ci": true
}
```

### `/api/ci/status` response (no CI detected)

```json
{
    "providers": [],
    "total_workflows": 0,
    "has_ci": false
}
```

### `/api/ci/workflows` response

```json
{
    "workflows": [
        {
            "file": ".github/workflows/ci.yml",
            "provider": "github_actions",
            "name": "CI Pipeline",
            "triggers": ["push", "pull_request"],
            "jobs": [
                {
                    "name": "test",
                    "runs_on": "ubuntu-latest",
                    "steps_count": 8,
                    "services": ["postgres"],
                    "matrix": {"python-version": ["3.11", "3.12"]}
                },
                {
                    "name": "build-docker",
                    "runs_on": "ubuntu-latest",
                    "steps_count": 5,
                    "needs": ["test"]
                }
            ],
            "issues": [
                "Action 'actions/checkout' not pinned to SHA (uses v4 tag)"
            ]
        }
    ]
}
```

### `/api/ci/coverage` response

```json
{
    "covered": ["docker", "python"],
    "uncovered": ["terraform", "k8s"],
    "coverage_pct": 50.0,
    "details": {
        "docker": {
            "covered": true,
            "reason": "Found 'docker build' in .github/workflows/ci.yml"
        },
        "python": {
            "covered": true,
            "reason": "Found 'pytest' in .github/workflows/ci.yml"
        },
        "terraform": {
            "covered": false,
            "reason": "No terraform markers found in CI files"
        },
        "k8s": {
            "covered": false,
            "reason": "No kubectl/helm markers found in CI files"
        }
    }
}
```

### `/api/ci/generate/ci` response (success)

```json
{
    "ok": true,
    "file": {
        "path": ".github/workflows/ci.yml",
        "content": "name: CI Pipeline\non:\n  push:\n    branches: [main]\n...",
        "stacks": ["python", "docker"],
        "jobs_count": 3
    }
}
```

### `/api/ci/generate/ci` response (error — no stacks)

```json
{
    "error": "No stacks detected — run detection first"
}
```

### `/api/ci/generate/lint` response (success)

```json
{
    "ok": true,
    "file": {
        "path": ".github/workflows/lint.yml",
        "content": "name: Lint\non:\n  push:\n    branches: [main]\n...",
        "stacks": ["python"],
        "jobs_count": 1
    }
}
```

---

## Advanced Feature Showcase

### 1. Cache Busting for Status

The status endpoint is the only one with caching — provider detection
scans 9 directory patterns across the filesystem. The `?bust=1` param
forces recomputation:

```python
force = request.args.get("bust", "") == "1"
return jsonify(get_cached(root, "ci", lambda: ci_ops.ci_status(root), force=force))
```

The frontend calls `?bust=1` after:
- User generates a new workflow (files changed)
- User deletes a workflow file
- User runs detection (project state changed)

Without `?bust=1`, the cached result is returned instantly (no disk I/O).

### 2. Workflow Issue Auditing

The `ci_workflows()` response includes an `issues[]` array per
workflow. The core service runs `_audit_github_workflow()` which
checks for:

```python
# From ci/ops.py — issue detection
issues = []

# Check: unpinned actions (tag instead of SHA)
for step in steps:
    uses = step.get("uses", "")
    if uses and "@" in uses:
        ref = uses.split("@", 1)[1]
        if not re.match(r"^[0-9a-f]{40}$", ref):
            issues.append(f"Action '{uses.split('@')[0]}' not pinned to SHA")

# Check: deprecated features
# Check: missing timeout-minutes
# Check: missing cancel-in-progress for PR builds
```

This gives users immediate visibility into CI best practice violations.

### 3. Stack-Based Coverage Detection

Coverage analysis doesn't require explicit configuration — it
auto-detects which stacks the project uses, then searches CI file
contents for stack-specific markers:

```python
# From ci/ops.py — 13 supported stacks
_STACK_CI_MARKERS = {
    "python":    ["pytest", "ruff", "mypy", "pip install", "python -m"],
    "node":      ["npm test", "npm run", "yarn test", "jest", "vitest"],
    "docker":    ["docker build", "docker-compose", "docker push"],
    "k8s":       ["kubectl", "helm", "kustomize"],
    "terraform": ["terraform plan", "terraform apply", "terraform init"],
    "go":        ["go test", "go build", "golangci-lint"],
    "rust":      ["cargo test", "cargo clippy", "cargo check"],
    "java":      ["mvn test", "gradle test", "maven", "gradle"],
    "dotnet":    ["dotnet test", "dotnet build"],
    "elixir":    ["mix test"],
    "ruby":      ["bundle exec", "rspec", "rake test"],
    # ... more
}
```

### 4. Shim-Based Import for Backward Compatibility

Routes import `from src.core.services import ci_ops` — a 10-line
re-export shim. This avoids updating every import site when the
core module was refactored from `ci_ops.py` (flat file) to
`ci/ops.py` (domain folder):

```python
# ci_ops.py — backward-compat shim (10 lines)
"""Backward-compat shim — real implementation in ci/ops.py."""
from src.core.services.ci.ops import (  # noqa: F401
    ci_status,
    ci_workflows,
    ci_coverage,
    generate_ci_workflow,
    generate_lint_workflow,
    generate_terraform_workflow,
)
```

### 5. Auto-Detection for Generation (Zero Configuration)

Both generate endpoints work without any request body:

```python
# generate.py — no body parsing needed
root = _project_root()
result = ci_ops.generate_ci_workflow(root)
```

The core function auto-detects stacks via:
1. Reading `project.yml` for configured modules
2. Scanning filesystem for stack indicators (Dockerfile, package.json, etc.)
3. Extracting unique stack names from detected modules
4. Composing workflow YAML using templates for each stack

This means clicking "Generate CI" in the UI requires zero user input.

---

## Design Decisions

### Why only status uses caching

- **Status** scans the filesystem for CI config files across 9 provider
  directories — potentially expensive in large projects. Caching
  prevents repeated scans during dashboard rendering.
- **Workflows** and **coverage** are read-heavy views that users
  explicitly navigate to. They need fresh data because workflow files
  may have just been generated or edited.
- **Generate** endpoints are POST actions that produce side effects
  (file creation). Caching would be semantically wrong.

### Why this package exists with only 88 lines of source

CI/CD is a distinct domain with:
- Its own frontend panel (`_cicd.html`)
- Its own core service (`ci/ops.py` — 593 lines)
- Its own CLI commands (`cli/ci/`)
- Its own data model (providers, workflows, coverage)

Even though the routes are thin, they belong in their own package
for consistency with the 1:1 domain-to-route-package pattern.
The alternative — merging into a generic "integrations" route
package — would make the integrations package a catch-all that
violates SRP.

### Why generate endpoints are POST despite having no body

Workflow generation creates files on disk — it has side effects.
Using GET would violate HTTP semantics (GET must be safe and
idempotent). POST correctly signals that calling this endpoint
changes server state and is not idempotent (running it twice
may overwrite changes the user made to the first generated file).

### Why the error pattern uses dict keys instead of exceptions

```python
if "error" in result:
    return jsonify(result), 400
```

The core function returns `{"error": "..."}` on failure rather than
raising exceptions. This design:
1. Avoids try/except boilerplate in every route handler
2. Allows the core to include context alongside errors
   (e.g., `{"error": "...", "stacks_found": [], "suggestion": "run detect first"}`)
3. Keeps the route handler a pure passthrough — no error translation needed

---

## Coverage Summary

| Capability | Endpoint | File | Cached |
|-----------|----------|------|--------|
| Provider detection | GET `/ci/status` | `status.py` | ✅ (with `?bust=1` override) |
| Workflow parsing + auditing | GET `/ci/workflows` | `status.py` | ❌ (always fresh) |
| Module CI coverage | GET `/ci/coverage` | `status.py` | ❌ (always fresh) |
| CI workflow generation | POST `/ci/generate/ci` | `generate.py` | N/A (side effect) |
| Lint workflow generation | POST `/ci/generate/lint` | `generate.py` | N/A (side effect) |
