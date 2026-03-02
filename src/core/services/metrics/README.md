# Metrics Domain

> **2 files · 509 lines · Unified project health scoring with 7 probes.**
>
> Aggregates health signals from Git, Docker, CI/CD, Packages,
> Environment, Quality, and Structure into a single project score
> (0–100) with letter grade, per-probe findings, and prioritized
> recommendations. Also provides a lightweight project summary
> for quick status checks.

---

## How It Works

### Architecture Overview

```
┌────────────────────────────────────────────────────────────────────┐
│ Single module, the "Total Solution Intelligence" layer              │
│                                                                      │
│  ops.py — OBSERVE tier (aggregation + scoring)                      │
│  ──────                                                              │
│  Runs 7 independent probes, each scoring 0.0–1.0                   │
│  Combines using configurable weights from DataRegistry              │
│  Produces unified score (0-100) with letter grade (A-F)            │
│                                                                      │
│  Also provides: project_summary (lightweight, no probes)            │
│                                                                      │
│  Pattern: Each probe is isolated — one crash doesn't                │
│  affect others. Probes use devops cache for fast re-queries.        │
└────────────────────────────────────────────────────────────────────┘
```

### Project Health Pipeline

```
project_health(root)
     │
     ├── Load weights from DataRegistry:
     │     └── _weights() → {git: 20, ci: 20, quality: 20,
     │                         docker: 15, packages: 10, env: 10,
     │                         structure: 5}
     │
     ├── Run 7 probes (each returns {score, findings, recommendations}):
     │     │
     │     ├── _probe_git(root):
     │     │     ├── get_cached("git", git_status)
     │     │     ├── Start: 1.0, deduct penalties
     │     │     │     ├── -0.3  uncommitted changes
     │     │     │     ├── -0.3  no remote
     │     │     │     └── -0.1  not on main/master
     │     │     └── Short-circuit: error → score 0
     │     │
     │     ├── _probe_docker(root):
     │     │     ├── get_cached("docker", docker_status)
     │     │     ├── Start: 0.0, add increments
     │     │     │     ├── +0.3  Docker CLI available
     │     │     │     ├── +0.2  daemon running
     │     │     │     ├── +0.3  Dockerfile(s) present
     │     │     │     └── +0.2  compose file found
     │     │     └── Short-circuit: not available → score 0
     │     │
     │     ├── _probe_ci(root):
     │     │     ├── get_cached("ci", ci_status)
     │     │     ├── Also calls ci_workflows (not cached)
     │     │     ├── Start: 0.0, add increments
     │     │     │     ├── +0.4  has CI configuration
     │     │     │     ├── +0.4  all workflows pass (+0.2 if issues)
     │     │     │     └── +0.2  push + PR triggers (+0.1 if partial)
     │     │     └── Short-circuit: no CI → score 0
     │     │
     │     ├── _probe_packages(root):
     │     │     ├── get_cached("packages", package_status)
     │     │     ├── Also calls package_outdated (not cached)
     │     │     ├── Start: 0.0, add increments
     │     │     │     ├── +0.3  package manager detected
     │     │     │     ├── +0.2  lock file present (per manager)
     │     │     │     ├── +0.3  all packages up to date
     │     │     │     ├── +0.2  ≤3 outdated packages
     │     │     │     └── +0.1  >3 outdated packages
     │     │     └── No managers → score 0.5 (baseline)
     │     │
     │     ├── _probe_env(root):
     │     │     ├── get_cached("env", env_status)
     │     │     ├── Also calls env_diff (not cached)
     │     │     ├── Start: 0.0, add increments
     │     │     │     ├── +0.3  .env files exist
     │     │     │     ├── +0.2  .env file present
     │     │     │     ├── +0.2  .env.example present
     │     │     │     └── +0.3  .env ↔ .env.example in sync
     │     │     └── No .env files → score 0.5 (baseline)
     │     │
     │     ├── _probe_quality(root):
     │     │     ├── get_cached("quality", _compute_quality)
     │     │     │     └── _compute_quality detects stacks first
     │     │     ├── Start: 0.0, add increments
     │     │     │     ├── +0.3   linter available
     │     │     │     ├── +0.25  type-checker available
     │     │     │     ├── +0.25  test framework available
     │     │     │     └── +0.2   formatter available
     │     │     └── Short-circuit: no quality tools → score 0
     │     │
     │     └── _probe_structure(root):
     │           ├── Pure file existence checks (no service imports)
     │           ├── Checks: project.yml (+0.3), README.md (+0.2),
     │           │     .gitignore (+0.2), LICENSE (+0.1),
     │           │     pyproject.toml (+0.1), Dockerfile (+0.1)
     │           └── No dependencies, always succeeds
     │
     ├── For each probe:
     │     ├── Compute: weighted_score = probe.score × weight
     │     ├── Accumulate into total_score
     │     └── On exception → {score: 0, findings: ["Error: ..."], recommendations: []}
     │
     ├── Determine grade:
     │     ├── ≥ 90 → A
     │     ├── ≥ 75 → B
     │     ├── ≥ 60 → C
     │     ├── ≥ 40 → D
     │     └── < 40 → F
     │
     ├── Gather recommendations:
     │     ├── Sort probes by weight (highest first)
     │     ├── Collect recommendations from each probe
     │     ├── Deduplicate
     │     └── Cap at 10
     │
     └── Return {score, max_score, grade, timestamp,
                  probes: {git: {...}, docker: {...}, ...},
                  recommendations}
```

### Project Summary Pipeline

```
project_summary(root)
     │
     ├── Load project metadata:
     │     ├── project.yml → name (fallback: "Unknown")
     │     ├── discover_stacks → unique stacks
     │     ├── detect_modules → module count
     │     └── All inside try/except — graceful degradation
     │
     ├── Quick integration checks (file/directory existence only):
     │     ├── git       → .git/ directory exists?
     │     ├── docker    → Dockerfile exists?
     │     ├── ci        → .github/workflows/ directory exists?
     │     ├── packages  → any of: pyproject.toml, package.json,
     │     │                        Cargo.toml, go.mod?
     │     └── env       → any of: .env, .env.example?
     │
     └── Return {name, root, stacks, modules, integrations}
```

---

## Architecture

```
             Routes (metrics/)
             DevOps Cache
                     │
                     │ imports
                     │
          ┌──────────▼──────────────────────────────┐
          │  metrics/__init__.py                      │
          │  Public API — re-exports 2 functions      │
          │  project_health · project_summary          │
          └──────────┬───────────────────────────────┘
                     │
                     ▼
                 ops.py
                 (All logic in one module)
                     │
    ┌────────────────┼─────────────────────────────┐
    │                │                              │
    ▼                ▼                              ▼
  7 Probes      DataRegistry                  project_summary
  (lazy imports) (weights)                    (config imports)
    │
    ├── devops/cache.py    ← get_cached() for mtime invalidation
    ├── git_ops            ← _probe_git
    ├── docker_ops         ← _probe_docker
    ├── ci_ops             ← _probe_ci
    ├── packages_svc/ops   ← _probe_packages
    ├── env/ops            ← _probe_env
    ├── quality/ops        ← _probe_quality
    ├──── config.loader    ← _compute_quality (inside quality probe)
    ├──── config.stack_loader
    └──── services.detection

             metrics_ops.py — backward-compat shim
```

### Dependency Rules

| Rule | Detail |
|------|--------|
| All service imports are lazy | Inside probe function bodies |
| Probes use devops cache | `get_cached()` for mtime-based invalidation |
| Weights from DataRegistry | Configurable without code changes |
| Full isolation per probe | One probe crash → score 0, others continue |
| No module-level service imports | `ops.py` imports only stdlib at module level |
| `project_summary` is independent | Does not run any probes, uses config imports only |

---

## File Map

```
metrics/
├── __init__.py        4 lines   — public API re-exports
├── ops.py           505 lines   — probes, health, summary
└── README.md                    — this file
```

---

## Per-File Documentation

### `ops.py` — Project Health (505 lines)

**Module-level objects:**

| Object | Type | Purpose |
|--------|------|---------|
| `_weights()` | `function → dict[str, int]` | Load health weights from DataRegistry |
| `_max_score()` | `function → int` | Sum of all weights (should be 100) |

**Private probe functions:**

| Function | Service Consumed | Cache Key | Scoring Model |
|----------|-----------------|-----------|--------------|
| `_probe_git(root)` | `git_ops.git_status` | `"git"` | Penalty-based (start at 1.0) |
| `_probe_docker(root)` | `docker_ops.docker_status` | `"docker"` | Additive (start at 0.0) |
| `_probe_ci(root)` | `ci_ops.ci_status`, `ci_workflows` | `"ci"` | Additive (start at 0.0) |
| `_probe_packages(root)` | `packages_svc.ops.package_status`, `package_outdated` | `"packages"` | Additive with baseline |
| `_probe_env(root)` | `env.ops.env_status`, `env_diff` | `"env"` | Additive with baseline |
| `_probe_quality(root)` | `quality.ops.quality_status` | `"quality"` | Additive per category |
| `_probe_structure(root)` | *(none — file checks only)* | — | Additive per file |

Each probe helper in `_probe_quality` also calls `_compute_quality`
which internally imports `config.loader`, `stack_loader`, and
`detection` to resolve stacks before calling `quality_status`.

**Public API:**

| Function | Parameters | Returns |
|----------|-----------|---------|
| `project_health(root)` | `Path` | `{score, max_score, grade, timestamp, probes, recommendations}` |
| `project_summary(root)` | `Path` | `{name, root, stacks, modules, integrations}` |

---

## Key Data Shapes

### project_health response

```python
{
    "score": 73.5,
    "max_score": 100,
    "grade": "B",
    "timestamp": "2026-02-28T19:30:00.000000+00:00",
    "probes": {
        "git": {
            "score": 0.7,
            "findings": [
                "Working tree has uncommitted changes",
                "On branch 'feature-auth' (not main)",
            ],
            "recommendations": [
                "Commit or stash changes",
            ],
        },
        "docker": {
            "score": 1.0,
            "findings": [
                "Docker 24.0.7 available",
                "2 Dockerfile(s)",
                "Compose file found",
            ],
            "recommendations": [],
        },
        "ci": {
            "score": 0.8,
            "findings": [
                "GitHub Actions: 3 workflow(s)",
                "1 workflow issue(s) detected",
                "CI triggers on push + PR",
            ],
            "recommendations": [
                "Run: controlplane ci workflows (to see details)",
            ],
        },
        "packages": {
            "score": 0.8,
            "findings": [
                "pip: pyproject.toml",
                "  Lock file: requirements.lock",
                "2 outdated package(s)",
            ],
            "recommendations": [],
        },
        "env": {
            "score": 1.0,
            "findings": [
                ".env: 12 variables",
                ".env.example: 12 variables",
                ".env ↔ .env.example: in sync",
            ],
            "recommendations": [],
        },
        "quality": {
            "score": 0.8,
            "findings": [
                "Linter available",
                "Type-checker available",
                "Test framework available",
            ],
            "recommendations": [],
        },
        "structure": {
            "score": 0.9,
            "findings": [
                "✓ Project configuration",
                "✓ README documentation",
                "✓ .gitignore",
                "✓ pyproject.toml",
                "✓ Dockerfile",
            ],
            "recommendations": [
                "Add LICENSE",
            ],
        },
    },
    "recommendations": [
        "Commit or stash changes",           # git (weight 20)
        "Run: controlplane ci workflows ...",  # ci (weight 20)
        "Add LICENSE",                        # structure (weight 5)
    ],
}
```

### project_summary response

```python
{
    "name": "devops-control-plane",
    "root": "/home/user/devops-control-plane",
    "stacks": ["python"],
    "modules": 5,
    "integrations": {
        "git": True,
        "docker": True,
        "ci": True,
        "packages": True,
        "env": True,
    },
}
```

### Individual probe response shape

Every probe returns the same shape:

```python
{
    "score": 0.7,                    # 0.0 (worst) to 1.0 (best)
    "findings": [                    # Human-readable observations
        "Working tree has uncommitted changes",
        "On branch 'feature-auth' (not main)",
    ],
    "recommendations": [             # Actionable suggestions
        "Commit or stash changes",
    ],
}
```

### Error case (probe failure)

When a probe throws an exception:

```python
{
    "score": 0,
    "findings": ["Docker probe error: ConnectionRefused(...)"],
    "recommendations": [],
}
```

The overall health still returns — the failed probe contributes
0 to the total score but doesn't block other probes.

---

## Consumers

| Layer | Module | What It Uses |
|-------|--------|-------------|
| **Routes** | `routes/metrics/` | `project_health`, `project_summary` |
| **Shims** | `metrics_ops.py` | Backward-compat re-export |

---

## Dependency Graph

```
ops.py                              ← aggregation layer
   │
   ├── datetime (stdlib)            ← timestamping
   ├── DataRegistry                 ← health weights (lazy)
   │
   ├── devops/cache                 ← get_cached (lazy, inside probes)
   │
   ├── git_ops                      ← _probe_git (lazy)
   ├── docker_ops                   ← _probe_docker (lazy)
   ├── ci_ops                       ← _probe_ci (lazy)
   ├── packages_svc/ops             ← _probe_packages (lazy)
   ├── env/ops                      ← _probe_env (lazy)
   ├── quality/ops                  ← _probe_quality (lazy)
   │   └── config.loader            ← stack detection (lazy, nested)
   │   └── config.stack_loader      ← stack discovery (lazy, nested)
   │   └── services.detection       ← module detection (lazy, nested)
   │
   └── config.loader (etc.)         ← project_summary (lazy)
```

Key: **Every service import is lazy** (inside function bodies).
This is critical — it prevents import-time circular dependencies
and ensures a missing service doesn't crash the entire module.

---

## Grading Scale

| Score Range | Grade | Description |
|-------------|-------|-------------|
| ≥ 90 | **A** | Excellent — all major aspects healthy |
| ≥ 75 | **B** | Good — minor improvements possible |
| ≥ 60 | **C** | Average — noticeable gaps |
| ≥ 40 | **D** | Below average — significant gaps |
| < 40 | **F** | Poor — requires attention |

---

## Default Health Weights

Loaded from DataRegistry via `_weights()`:

| Probe | Default Weight | Why This Weight |
|-------|---------------|----------------|
| `git` | 20 | Foundation — everything depends on version control |
| `ci` | 20 | Automation gate — ensures changes are validated |
| `quality` | 20 | Code health — linters, types, tests, formatters |
| `docker` | 15 | Containerization — needed for deployment |
| `packages` | 10 | Dependency management — important but secondary |
| `env` | 10 | Environment config — important but secondary |
| `structure` | 5 | Project skeleton — baseline files |
| **Total** | **100** | |

Weights are configurable via DataRegistry. Teams can adjust them
to match their priorities (e.g., increase `ci` weight for a CI-heavy
team, decrease `docker` weight for a library project).

---

## Score Formula

```
total_score = Σ (probe_score × probe_weight)

where:
  probe_score ∈ [0.0, 1.0]
  probe_weight ∈ integers (default total = 100)
  total_score ∈ [0, max_score]

grade = lookup(total_score, grading_scale)
```

The `max_score` is always the sum of all weights. When all
probes score 1.0, `total_score == max_score == 100`.

### Score example calculation

```
git:       0.7 × 20 = 14.0
ci:        0.8 × 20 = 16.0
quality:   0.8 × 20 = 16.0
docker:    1.0 × 15 = 15.0
packages:  0.8 × 10 =  8.0
env:       1.0 × 10 = 10.0
structure: 0.9 ×  5 =  4.5
                     ─────
                      83.5 → Grade B
```

---

## Probe Scoring Models

### Penalty-based (git)

```
score = 1.0
score -= 0.3  if dirty
score -= 0.3  if no remote
score -= 0.1  if not on main/master
score = max(0, score)
```

Git starts at perfect (1.0) because an initialized git repo
should be clean — penalties represent deviations from ideal.

### Additive (docker, ci, quality, structure)

```
score = 0.0
score += 0.3  if CLI available
score += 0.2  if daemon running
...
score = min(1.0, score)
```

Each capability contributes incrementally. Projects without
the integration start at 0 and earn points for each feature.

### Additive with baseline (packages, env)

```
if no_package_managers:
    return score=0.5    # baseline — not penalized
score = 0.0
score += ...
```

Some integrations are optional (packages, env). Projects
without them get 0.5 (neutral) rather than 0 (penalty).

---

## Probes in Detail

### `_probe_git` — Git Health (weight: 20)

| Condition | Score Change | Finding | Recommendation |
|-----------|-------------|---------|---------------|
| Not a git repo | **→ 0** | "Not a git repository" | "Initialize git: git init" |
| Dirty working tree | **−0.3** | "Working tree has uncommitted changes" | "Commit or stash changes" |
| No remote configured | **−0.3** | "No remote configured" | "Add GitHub remote: git remote add origin <url>" |
| Not on main/master | **−0.1** | "On branch 'feature-x' (not main)" | *(informational)* |
| Clean + main + remote | **= 1.0** | "Clean, on main, remote configured" | — |

### `_probe_docker` — Docker Health (weight: 15)

| Condition | Score Change | Finding | Recommendation |
|-----------|-------------|---------|---------------|
| Docker not available | **→ 0** | "Docker not available" | "Install Docker" |
| CLI available | **+0.3** | "Docker 24.0.7 available" | — |
| Daemon running | **+0.2** | *(included above)* | — |
| Daemon not running | — | "Docker daemon not running" | "Start Docker daemon" |
| Dockerfile(s) present | **+0.3** | "2 Dockerfile(s)" | — |
| No Dockerfiles | — | — | "Generate Dockerfile: controlplane docker generate..." |
| Compose file found | **+0.2** | "Compose file found" | — |
| No compose file | — | — | "Generate compose: controlplane docker generate compose" |

### `_probe_ci` — CI/CD Health (weight: 20)

| Condition | Score Change | Finding | Recommendation |
|-----------|-------------|---------|---------------|
| No CI configured | **→ 0** | "No CI/CD configured" | "Generate CI: controlplane ci generate ci" |
| Has CI | **+0.4** | "GitHub Actions: N workflow(s)" | — |
| All workflows pass | **+0.4** | "All workflows pass audit" | — |
| Workflow issues | **+0.2** | "N workflow issue(s) detected" | "Run: controlplane ci workflows" |
| Push + PR triggers | **+0.2** | "CI triggers on push + PR" | — |
| Partial triggers | **+0.1** | "CI triggers: push" | — |

### `_probe_packages` — Package Health (weight: 10)

| Condition | Score Change | Finding | Recommendation |
|-----------|-------------|---------|---------------|
| No package managers | **→ 0.5** | "No package managers detected" | — |
| Manager detected | **+0.3** | "pip: pyproject.toml" | — |
| Lock file present | **+0.2** | "Lock file: requirements.lock" | — |
| No lock file | — | — | "Generate lock file for pip" |
| All up to date | **+0.3** | "All packages up to date" | — |
| ≤3 outdated | **+0.2** | "2 outdated package(s)" | — |
| >3 outdated | **+0.1** | "8 outdated packages" | "Run: controlplane packages outdated" |

### `_probe_env` — Environment Health (weight: 10)

| Condition | Score Change | Finding | Recommendation |
|-----------|-------------|---------|---------------|
| No .env files | **→ 0.5** | "No .env files" | "Create .env for local configuration" |
| Files found | **+0.3** | ".env: 12 variables" | — |
| .env present | **+0.2** | *(included above)* | — |
| .env missing | — | — | "Create .env file" |
| .env.example present | **+0.2** | *(included above)* | — |
| .env.example missing | — | — | "Generate .env.example: controlplane infra env..." |
| In sync | **+0.3** | ".env ↔ .env.example: in sync" | — |
| Out of sync | — | "N var(s) missing" | "Run: controlplane infra env diff" |

### `_probe_quality` — Quality Tool Health (weight: 20)

| Condition | Score Change | Finding | Recommendation |
|-----------|-------------|---------|---------------|
| No quality tools | **→ 0** | "No quality tools available" | "Install quality tools: pip install ruff mypy pytest" |
| Linter available | **+0.3** | "Linter available" | — |
| No linter | — | — | "Add linter (ruff, eslint)" |
| Type-checker available | **+0.25** | "Type-checker available" | — |
| No type-checker | — | — | "Add type-checker (mypy, tsc)" |
| Test framework | **+0.25** | "Test framework available" | — |
| No test framework | — | — | "Add test framework (pytest, jest)" |
| Formatter available | **+0.2** | "Formatter available" | — |

### `_probe_structure` — Project Structure Health (weight: 5)

| File | Weight | Finding (present) | Recommendation (missing) |
|------|--------|-------------------|------------------------|
| `project.yml` | +0.3 | "✓ Project configuration" | "Add project.yml" |
| `README.md` | +0.2 | "✓ README documentation" | "Add README.md" |
| `.gitignore` | +0.2 | "✓ .gitignore" | "Add .gitignore" |
| `LICENSE` | +0.1 | "✓ License file" | "Add LICENSE" |
| `pyproject.toml` | +0.1 | "✓ pyproject.toml" | "Add pyproject.toml" |
| `Dockerfile` | +0.1 | "✓ Dockerfile" | "Add Dockerfile" |

---

## Integration Detection (Summary)

The `project_summary` function performs quick file existence
checks without running any service:

| Integration | Detection Check |
|-------------|----------------|
| `git` | `.git/` directory exists |
| `docker` | `Dockerfile` exists |
| `ci` | `.github/workflows/` directory exists |
| `packages` | Any of: `pyproject.toml`, `package.json`, `Cargo.toml`, `go.mod` |
| `env` | Any of: `.env`, `.env.example` |

---

## Probe Execution Order

Probes are executed in definition order (dict insertion order):

| Order | Probe | Typical Speed | Why This Speed |
|-------|-------|--------------|----------------|
| 1 | `git` | Fast | Reads cached git_status |
| 2 | `docker` | Fast | Reads cached docker_status |
| 3 | `ci` | Moderate | Parses workflow YAML files |
| 4 | `packages` | Moderate | May check outdated packages |
| 5 | `env` | Fast | File checks + simple diff |
| 6 | `quality` | Moderate | Tool detection + stack resolution |
| 7 | `structure` | Fastest | Pure file existence checks |

**Key:** Each probe is independent. If one probe throws an exception,
it receives score 0 and the remaining probes continue executing.

---

## Cache Integration

Probes use the devops cache for performance:

```python
result = get_cached(project_root, "git", lambda: git_status(project_root))
```

The cache uses **mtime-based invalidation** — if the project's
files haven't changed since the last call, the cached result
is returned. This means:

- `project_health()` is fast (~100ms) when the dashboard was viewed recently
- A health check **warms the cache** for subsequent card renders
- Cache is shared between health probes and DevOps tab cards

### Probes that bypass cache

Two probes make additional calls that are **not cached**:

| Probe | Uncached Call | Why |
|-------|-------------|-----|
| `_probe_ci` | `ci_workflows()` | Workflow audit is too heavy to pre-cache |
| `_probe_packages` | `package_outdated()` | Requires subprocess execution |
| `_probe_env` | `env_diff()` | Sync diff computed on demand |

---

## Health vs Summary Comparison

| Feature | `project_health` | `project_summary` |
|---------|------------------|-------------------|
| Runs probes | Yes (7 probes) | No |
| Produces score | Yes (0-100) | No |
| Produces grade | Yes (A-F) | No |
| Uses devops cache | Yes | No |
| Imports services | Yes (6 services, lazy) | Yes (config only, lazy) |
| Response time | ~1-5s (cached: <100ms) | <50ms |
| Recommendations | Yes (top 10) | No |
| Side effects | Warms cache | None |

---

## Recommendation Sorting

Recommendations are gathered from all probes and sorted by
probe weight (highest first), then deduplicated:

```python
for probe_id in sorted(weights, key=lambda k: weights[k], reverse=True):
    for rec in probe.get("recommendations", []):
        if rec not in all_recs:
            all_recs.append(rec)
```

This ensures that fixing Git issues (weight 20) appears before
fixing structure issues (weight 5) in the recommendation list.

**Cap:** Only the top 10 recommendations are returned.

---

## Timestamp Format

The health response includes an ISO 8601 timestamp:

```python
"timestamp": "2026-02-28T19:30:00.000000+00:00"
```

Generated via `datetime.now(UTC).isoformat()`. This allows:
- The UI to display "last checked" time
- Cache invalidation based on staleness
- Temporal comparison between health checks

---

## Error Handling

| Function | Can Fail? | Error Shape |
|----------|----------|-------------|
| `project_health` | No | Always returns `{score, grade, probes, ...}` |
| `project_summary` | No | Gracefully degrades (name="Unknown", etc.) |

**Per-probe error handling:**

Every probe is wrapped in a try/except. On failure:

```python
probes[probe_id] = {
    "score": 0,
    "findings": [f"Error: {e}"],
    "recommendations": [],
}
```

This means a Docker connection error, a missing git binary,
or an import failure does **not** crash the health check —
it just contributes 0 to the total score.

---

## Backward Compatibility

One shim file remains at the services root:

```python
# metrics_ops.py
from src.core.services.metrics.ops import *  # noqa
```

This shim allows old import paths to continue working
during the migration to the package structure.

---

## Advanced Feature Showcase

### 1. Penalty vs Additive Scoring Models — Two Mental Models, One API

Git uses penalty-based scoring; all others use additive:

```python
# ops.py — _probe_git (lines 52-76) — penalty model

score = 1.0                           # start at perfect
if result.get("dirty"):
    score -= 0.3                      # deduct for dirty tree
if not result.get("remote"):
    score -= 0.3                      # deduct for no remote
if result.get("branch") not in ("main", "master"):
    score -= 0.1                      # deduct for non-main branch
return {"score": max(0, score), ...}  # clamp at 0

# ops.py — _probe_docker (lines 91-121) — additive model

score = 0.0                           # start at zero
if result.get("available"):
    score += 0.3                      # add for CLI available
if result.get("daemon_running"):
    score += 0.2                      # add for running daemon
if result.get("dockerfiles"):
    score += 0.3                      # add for Dockerfiles
if result.get("compose_file"):
    score += 0.2                      # add for compose
return {"score": min(1.0, score), ...}  # clamp at 1.0
```

Why the difference? Git starts clean — a new repo is perfect. Docker
starts empty — capabilities must be added. The scoring model matches
the mental model: "how far from ideal" vs "how much is present."

### 2. Weight-Sorted Recommendation Deduplication — Priority-Based Ordering

Recommendations are gathered by probe weight (highest first):

```python
# ops.py — project_health (lines 434-441)

all_recs: list[str] = []
weights = _weights()
for probe_id in sorted(weights, key=lambda k: weights[k], reverse=True):
    probe = probes.get(probe_id, {})
    for rec in probe.get("recommendations", []):
        if rec not in all_recs:
            all_recs.append(rec)
```

This ensures git/ci/quality recommendations (weight 20 each) appear
before structure recommendations (weight 5). The `if rec not in all_recs`
guard deduplicates — if two probes generate the same recommendation
(unlikely but possible), it appears only once at its highest-weight
position. Final cap: top 10 only.

### 3. `_compute_quality` — Inline Stack Detection for Accurate Scoring

The quality probe doesn't just call `quality_status()` — it first
detects project stacks to avoid irrelevant tool mismatch:

```python
# ops.py — _probe_quality (lines 295-310)

def _compute_quality() -> dict:
    stack_names: list[str] = []
    try:
        from src.core.config.loader import load_project
        from src.core.config.stack_loader import discover_stacks
        from src.core.services.detection import detect_modules

        project = load_project(project_root / "project.yml")
        stacks = discover_stacks(project_root / "stacks")
        detection = detect_modules(project, project_root, stacks)
        stack_names = list({
            m.effective_stack for m in detection.modules
            if m.effective_stack
        })
    except Exception:
        pass
    return quality_status(project_root, stack_names=stack_names or None)

status = get_cached(project_root, "quality", _compute_quality)
```

Without stack detection, a Python-only project would be penalized for
not having eslint/prettier. With it, only Python-relevant tools (ruff,
mypy, pytest) are considered. The entire stack detection is inside
try/except — if config loading fails, `quality_status` runs without
stack filtering (showing all tools).

### 4. Probe Isolation — Per-Probe Exception Handling

Each probe is individually guarded:

```python
# ops.py — project_health (lines 412-420)

for probe_id, fn in probe_fns.items():
    try:
        result = fn(project_root)
        probes[probe_id] = result
        weighted = result.get("score", 0) * _weights().get(probe_id, 0)
        total_score += weighted
    except Exception as e:
        logger.debug("Probe %s failed: %s", probe_id, e)
        probes[probe_id] = {
            "score": 0,
            "findings": [f"Error: {e}"],
            "recommendations": [],
        }
```

If Docker's API is down, only `_probe_docker` scores 0 — the remaining
6 probes still execute normally. Each probe also has its own internal
try/except with a similar error shape, providing two layers of safety.
This means a health check **never crashes**, even if every service
dependency is broken.

### 5. Baseline Score for Optional Integrations — Neutral Treatment

Packages and environment provide "opt-out" baseline scoring:

```python
# ops.py — _probe_packages (lines 196-198)

if not status.get("has_packages"):
    findings.append("No package managers detected")
    return {"score": 0.5, "findings": findings, "recommendations": recommendations}

# ops.py — _probe_env (lines 248-251)

if not files:
    findings.append("No .env files")
    recommendations.append("Create .env for local configuration")
    return {"score": 0.5, "findings": findings, "recommendations": recommendations}
```

A library with no `.env` and no package manager scores 0.5 × 10 + 0.5 × 10
= 10 from these probes, which is neutral. Without baseline, it would score
0 + 0 = 0, unfairly penalizing projects that don't need these features.
The 0.5 threshold means these probes neither help nor hurt when absent.

### 6. Devops Cache Sharing — Bidirectional Warm-Up

Probes share cache with DevOps tab cards:

```python
# ops.py — _probe_git (line 50)

result = get_cached(project_root, "git", lambda: git_status(project_root))
```

The `get_cached()` function uses mtime-based invalidation. When the
DevOps dashboard renders a git card, it calls `get_cached("git", ...)`.
When `project_health()` runs later, the same cache key returns the
stored result without re-executing `git_status()`. Conversely, a
health check warms the cache for subsequent card renders. Six of seven
probes share this cache (structure probe doesn't use any service).

### 7. CI Workflow Quality Audit — Two-Level Analysis

The CI probe doesn't just check "has CI" — it audits workflow quality:

```python
# ops.py — _probe_ci (lines 150-175)

# Level 1: ci_status (cached) — provider detection, workflow count
# Already computed above via get_cached

# Level 2: ci_workflows (uncached) — deep audit
wf_result = ci_workflows(project_root)
total_issues = 0
for wf in wf_result.get("workflows", []):
    issues = wf.get("issues", [])
    total_issues += len(issues)

if total_issues == 0:
    score += 0.4                          # full credit
else:
    score += 0.2                          # partial credit
    findings.append(f"{total_issues} workflow issue(s) detected")

# Level 3: trigger completeness
all_triggers: set[str] = set()
for wf in wf_result.get("workflows", []):
    all_triggers.update(wf.get("triggers", []))

if "push" in all_triggers and "pull_request" in all_triggers:
    score += 0.2                          # full credit
elif all_triggers:
    score += 0.1                          # partial credit
```

Three dimensions: (1) CI presence, (2) workflow audit pass/fail,
(3) trigger completeness. A project with CI but no PR trigger scores
lower than one with both push and PR triggers. This encourages full
CI coverage.

---

### Feature Coverage Summary

| Feature | Where | Complexity |
|---------|-------|-----------|
| Penalty vs additive scoring | `_probe_git` vs other probes | Two mental models for two situations |
| Weight-sorted recommendation dedup | `project_health` | `sorted()` + `not in` guard + cap 10 |
| Inline stack detection for quality | `_probe_quality._compute_quality` | Three config imports inside probe |
| Per-probe exception isolation | `project_health` loop | Two-layer safety (inner + outer) |
| Baseline score for optional integrations | `_probe_packages`, `_probe_env` | 0.5 neutral return |
| Bidirectional devops cache | All probes via `get_cached()` | Shared mtime-invalidated cache |
| CI workflow quality audit | `_probe_ci` | Three-dimension analysis |

---

## Design Decisions

### Why 7 probes?

The 7 probes cover all major aspects of project health that
the DevOps Control Plane manages. Each probe maps 1:1 to a
service domain (Git, Docker, CI, Packages, Environment, Quality,
Structure). This provides complete visibility into project
readiness without gaps or overlaps.

### Why DataRegistry for weights?

Scoring weights are inherently subjective and may vary by team
or project type. A library project might deprioritize Docker
(weight 0) while a microservice project might maximize it.
Storing weights in DataRegistry allows operators to tune scoring
without modifying code.

### Why lazy service imports?

Each probe imports its required service inside the function body.
This prevents import-time circular dependencies and ensures that
a missing service (e.g., Docker not installed, packages_svc has
import error) doesn't crash the entire metrics module. Failed
imports are caught by the per-probe exception handler.

### Why devops cache integration?

Probes reuse the same cached status data that the DevOps tab
cards display. This bidirectional sharing means `project_health()`
is fast when the dashboard was recently viewed, and conversely,
a health check warms the cache for subsequent card renders. The
alternative (separate cache or no cache) would double the work.

### Why top-10 recommendation limit?

More than 10 recommendations becomes overwhelming and loses
signal. The list is sorted by probe weight (most impactful
first), ensuring the user sees the highest-value improvements.
If all 7 probes generated 3 recs each (21 total), showing
all would dilute the urgency of the important ones.

### Why baseline score 0.5 for optional integrations?

Packages and environment files are optional — a library might
not use `.env` files, and a documentation site might not have
dependency managers. Scoring them at 0 would unfairly penalize
projects that simply don't need these features. A baseline of
0.5 (neutral) means these probes neither help nor hurt the
score when the integration is absent.

### Why penalty-based scoring for git but additive for others?

Git is the only integration where a clean state is the **default
expectation** — a new repo starts clean. Penalties model
deviations from that ideal. Other integrations (Docker, CI)
start from zero capability and earn points as features are added.
This difference in mental model is reflected in the scoring
approach.
