# Metrics Routes — Project Health Score & Summary API

> **3 files · 130 lines · 2 endpoints · Blueprint: `metrics_bp` · Prefix: `/api`**
>
> Two endpoints that aggregate health signals from every integration
> into a unified project score:
>
> 1. **Health** — 7 parallel probes (git, docker, CI, packages, env,
>    quality, structure) with weighted scoring, letter grade, and
>    prioritized recommendations
> 2. **Summary** — lightweight project metadata (name, stacks, module
>    count, integration availability) without running expensive probes
>
> Backed by `core/services/metrics/ops.py` (505 lines) — the
> "Total Solution Intelligence" layer.

---

## How It Works

### Health Score Pipeline (Parallel Probes)

```
GET /api/metrics/health?bust=1
     │
     ▼
ThreadPoolExecutor(max_workers=7)
     │
     ├── Thread 1: _probe_git(root)
     │   ├── Reuses cache key: "git"
     │   ├── Checks: is repo clean? on main? has remote?
     │   ├── Score penalties:
     │   │   ├── dirty working tree  → −0.3
     │   │   ├── no remote           → −0.3
     │   │   └── not on main/master  → −0.1
     │   └── Returns: { score: 0.0-1.0, findings, recommendations }
     │
     ├── Thread 2: _probe_docker(root)
     │   ├── Reuses cache key: "docker"
     │   ├── Checks: Docker available? Dockerfile exists? Compose?
     │   │   Daemon running?
     │   └── Returns: { score, findings, recommendations }
     │
     ├── Thread 3: _probe_ci(root)
     │   ├── Reuses cache key: "ci"
     │   ├── Checks: CI config exists? Workflows valid? Coverage?
     │   └── Returns: { score, findings, recommendations }
     │
     ├── Thread 4: _probe_packages(root)
     │   ├── Reuses cache key: "packages"
     │   ├── Checks: lock file exists? outdated count?
     │   └── Returns: { score, findings, recommendations }
     │
     ├── Thread 5: _probe_env(root)
     │   ├── Reuses cache key: "env"
     │   ├── Checks: .env exists? .env.example? in sync?
     │   └── Returns: { score, findings, recommendations }
     │
     ├── Thread 6: _probe_quality(root)
     │   ├── Reuses cache key: "quality"
     │   ├── Checks: lint tools? type checker? test framework?
     │   └── Returns: { score, findings, recommendations }
     │
     └── Thread 7: _probe_structure(root)
         ├── Reuses cache key: "docs"
         ├── Checks: project.yml? README? .gitignore?
         └── Returns: { score, findings, recommendations }
     │
     ▼  All 7 probes complete (bounded by slowest, not sum)
     │
     ├── Load weights from DataRegistry:
     │   weights = { git: 20, docker: 15, ci: 20, packages: 10,
     │               env: 10, quality: 15, structure: 10 }
     │
     ├── Compute weighted total:
     │   total_score = Σ (probe.score × weight)
     │   e.g. git=0.7×20 + docker=1.0×15 + ... = 82.5
     │
     ├── Assign grade:
     │   ├── ≥90 → A
     │   ├── ≥75 → B
     │   ├── ≥60 → C
     │   ├── ≥40 → D
     │   └── <40 → F
     │
     └── Gather recommendations:
         Sorted by weight (highest-weight probes first)
         Deduplicated, capped at 10
```

### Project Summary Pipeline (Lightweight)

```
GET /api/metrics/summary
     │
     ▼
metrics_ops.project_summary(root)
     │
     ├── Detect project name (project.yml, package.json, etc.)
     ├── Identify tech stacks (Python, Node, Go, etc.)
     ├── Count modules / packages
     ├── Check integration availability:
     │   ├── git → shutil.which("git")
     │   ├── docker → shutil.which("docker")
     │   ├── gh → shutil.which("gh")
     │   ├── kubectl → shutil.which("kubectl")
     │   └── helm → shutil.which("helm")
     │
     └── Return:
         { name, root, stacks, modules, integrations: {name: bool} }
```

---

## File Map

```
routes/metrics/
├── __init__.py     18 lines — blueprint + 2 sub-module imports
├── health.py       96 lines — 1 endpoint (full health probe)
├── summary.py      16 lines — 1 endpoint (quick summary)
└── README.md                — this file
```

Core business logic: `core/services/metrics/ops.py` (505 lines).

---

## Per-File Documentation

### `__init__.py` — Blueprint Definition (18 lines)

```python
metrics_bp = Blueprint("metrics", __name__)

from . import health, summary  # register routes
```

### `health.py` — Full Health Probe (96 lines)

| Function | Method | Route | What It Does |
|----------|--------|-------|-------------|
| `project_health()` | GET | `/metrics/health` | 7-probe weighted health score |

**The health endpoint does most of the work route-side** — the
`health.py` module is 96 lines because it orchestrates the parallel
probe execution, weight computation, grade assignment, and
recommendation aggregation directly instead of delegating
everything to the core service.

**Probe registry (route-level constant):**

```python
_HEALTH_PROBES: dict[str, tuple[str, str]] = {
    "git":       ("git",      "_probe_git"),
    "docker":    ("docker",   "_probe_docker"),
    "ci":        ("ci",       "_probe_ci"),
    "packages":  ("packages", "_probe_packages"),
    "env":       ("env",      "_probe_env"),
    "quality":   ("quality",  "_probe_quality"),
    "structure": ("docs",     "_probe_structure"),
}
```

**Parallel execution pattern:**

```python
with ThreadPoolExecutor(max_workers=len(probe_fns)) as pool:
    futures = {
        pool.submit(fn, root): probe_id
        for probe_id, fn in probe_fns.items()
    }
    for future in as_completed(futures):
        probe_id = futures[future]
        try:
            probes[probe_id] = future.result()
        except Exception as exc:
            probes[probe_id] = {
                "score": 0,
                "findings": [f"Probe error: {exc}"],
                "recommendations": [],
            }
```

**Error resilience:** if any probe throws, its score is set to 0
and the error is captured as a finding. Other probes still run.

**Grade banding:**

```python
if total_score >= 90:   grade = "A"
elif total_score >= 75: grade = "B"
elif total_score >= 60: grade = "C"
elif total_score >= 40: grade = "D"
else:                   grade = "F"
```

### `summary.py` — Quick Summary (16 lines)

| Function | Method | Route | What It Does |
|----------|--------|-------|-------------|
| `project_summary()` | GET | `/metrics/summary` | Project metadata |

**Minimal route — pure delegation:**

```python
@metrics_bp.route("/metrics/summary")
def project_summary():
    return jsonify(metrics_ops.project_summary(_project_root()))
```

---

## Dependency Graph

```
__init__.py
└── Imports: health, summary

health.py
├── metrics.ops      ← _probe_git, _probe_docker, ..., _weights, _max_score (eager)
├── helpers          ← project_root (eager)
├── concurrent.futures ← ThreadPoolExecutor (lazy, inside handler)
└── datetime         ← UTC timestamp (eager)

summary.py
├── metrics.ops      ← project_summary (eager)
└── helpers          ← project_root (eager)
```

**The probes themselves pull from other services (lazy):**

```
_probe_git       → devops.cache → git_ops.git_status
_probe_docker    → devops.cache → docker_ops.docker_status
_probe_ci        → devops.cache → ci_ops via card cache
_probe_packages  → devops.cache → package_ops via card cache
_probe_env       → devops.cache → env_ops via card cache
_probe_quality   → devops.cache → quality/audit card cache
_probe_structure → devops.cache → docs_svc card cache
```

---

## Consumers

| Layer | Module | What It Uses |
|-------|--------|-------------|
| Server | `ui/web/server.py` | Imports `metrics_bp`, registers at `/api` |
| Dashboard | `scripts/_dashboard.html` | `/metrics/health` (main dashboard score) |

---

## Data Shapes

### `GET /api/metrics/health` response

```json
{
    "score": 82.5,
    "max_score": 100,
    "grade": "B",
    "timestamp": "2026-03-02T21:06:48+00:00",
    "probes": {
        "git": {
            "score": 0.7,
            "findings": [
                "Working tree has uncommitted changes",
                "No remote configured"
            ],
            "recommendations": [
                "Commit or stash changes",
                "Add GitHub remote: git remote add origin <url>"
            ]
        },
        "docker": {
            "score": 1.0,
            "findings": [
                "Docker 24.0.7 available",
                "Dockerfile found",
                "docker-compose.yml found"
            ],
            "recommendations": []
        },
        "ci": {
            "score": 0.8,
            "findings": ["GitHub Actions configured"],
            "recommendations": ["Add code coverage reporting"]
        },
        "packages": {
            "score": 0.6,
            "findings": ["4 outdated packages"],
            "recommendations": ["Run pip install --upgrade"]
        },
        "env": {
            "score": 0.5,
            "findings": [".env exists", "No .env.example"],
            "recommendations": ["Create .env.example template"]
        },
        "quality": {
            "score": 0.9,
            "findings": ["Ruff configured", "Mypy configured"],
            "recommendations": []
        },
        "structure": {
            "score": 1.0,
            "findings": ["README.md found", ".gitignore found"],
            "recommendations": []
        }
    },
    "recommendations": [
        "Commit or stash changes",
        "Add GitHub remote: git remote add origin <url>",
        "Add code coverage reporting",
        "Run pip install --upgrade",
        "Create .env.example template"
    ]
}
```

### `GET /api/metrics/summary` response

```json
{
    "name": "devops-control-plane",
    "root": "/home/user/devops-control-plane",
    "stacks": ["python", "node"],
    "modules": 42,
    "integrations": {
        "git": true,
        "docker": true,
        "gh": true,
        "kubectl": false,
        "helm": false
    }
}
```

---

## Advanced Feature Showcase

### 1. Parallel Probe Execution

All 7 probes run simultaneously via `ThreadPoolExecutor`. Total
time is bounded by the slowest single probe, not the sum:

```
Sequential: 200ms + 300ms + 150ms + ... = ~1.4s
Parallel:   max(200ms, 300ms, 150ms, ...) = ~300ms
```

### 2. Cache Reuse Across Cards

Each probe reads from the same devops card cache (`"git"`,
`"docker"`, etc.) that the individual DevOps panel cards use.
This means:
- If the user already viewed the DevOps panel → probes are instant
- If cache is cold → probes populate the cache for future card views

### 3. DataRegistry-Driven Weights

Scoring weights are not hardcoded — they come from the
DataRegistry, which loads them from the project's configuration.
This allows per-project weight customization.

### 4. Resilient Error Handling

Each probe is wrapped in a try/except at two levels:
1. Inside the probe function itself (core service)
2. In the `ThreadPoolExecutor` future handler (route)

If a probe fails, it scores 0 and reports the error. The overall
score is still computed from the remaining probes.

### 5. Prioritized Recommendations

Recommendations are sorted by weight (git=20 recommendations appear
before env=10 recommendations), deduplicated, and capped at 10
to prevent information overload.

---

## Design Decisions

### Why health logic lives in the route, not the core service

The core service has `project_health()` with the same logic, but
the route reimplements it to run probes in parallel via
`ThreadPoolExecutor`. The core service runs probes sequentially.
The route overrides the orchestration for better performance in
the web context.

### Why summary doesn't use health probes

Summary is meant to be fast — it checks tool availability with
`shutil.which()` (microseconds) instead of running full probes
that may invoke subprocess calls (seconds). It's used for
lightweight UI elements that just need to know what's available.

### Why grades use fixed thresholds

Using fixed A/B/C/D/F bands instead of percentile-based scoring
makes grades stable and predictable. A score of 90 always means A,
regardless of how other projects score.

---

## Coverage Summary

| Capability | Endpoint | Method | Tracked | Cached |
|-----------|----------|--------|---------|--------|
| Health score | `/metrics/health` | GET | No | No (probes reuse card caches) |
| Project summary | `/metrics/summary` | GET | No | No |
