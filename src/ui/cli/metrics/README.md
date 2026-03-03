# CLI: Metrics — Project Health Score, Summary & Reports

> **1 file · 197 lines · 3 commands · Group: `controlplane metrics`**
>
> Three levels of project health insight:
>
> 1. **health** — full probe-based scoring with recommendations
> 2. **summary** — quick project overview (no probes, fast)
> 3. **report** — Markdown health report for documentation
>
> Core service: `core/services/metrics/ops.py`

---

## Commands

### `controlplane metrics health`

Run all health probes and show project score.

```
controlplane metrics health
controlplane metrics health --json
```

**Output:**

```
🔍 Running health probes...

════════════════════════════════════════════════════════════
  PROJECT HEALTH: 72/100 — Grade C
════════════════════════════════════════════════════════════

  [████████████████████████████████░░░░░░░░] 72%

  🔀 Git            ✅  95%
  🐳 Docker         ✅  85%
  ⚙️ CI/CD          ⚠️  60%
  📦 Packages       ✅  80%
  🔐 Environment    ❌  40%
     Missing .env.example
     No vault passphrase registered
  🔍 Quality        ⚠️  65%
     No type-checking configured
  📁 Structure      ✅  80%

  💡 Recommendations:
     1. Add a .env.example for documentation
     2. Configure mypy or pyright for type checking
     3. Add concurrency groups to CI workflows
```

**Probes:** git, docker, ci, packages, env, quality, structure

Each probe returns a 0.0–1.0 score, findings list, and recommendations.

---

### `controlplane metrics summary`

Quick project summary — no probes, fast.

```
controlplane metrics summary
controlplane metrics summary --json
```

**Output:**

```
📋 DevOps Control Plane
   Root: /home/user/my-project
   Modules: 5
   Stacks: python, node

   Integrations:
      ✅ git
      ✅ docker
      ✅ ci
      ❌ terraform
      ❌ k8s
```

---

### `controlplane metrics report`

Generate a full health report in Markdown format.

```
controlplane metrics report > HEALTH.md
```

**Output (Markdown to stdout):**

```markdown
# Project Health Report: My Project

**Score:** 72/100 — Grade **C**
**Generated:** 2026-03-02T17:30:00
**Modules:** 5
**Stacks:** python, node

## Probe Results

| Probe | Score | Status |
|-------|-------|--------|
| git | 95% | ✅ |
| docker | 85% | ✅ |
| ci | 60% | ⚠️ |
...

## Findings

### env
- Missing .env.example
- No vault passphrase registered

## Recommendations

1. Add a .env.example for documentation
2. Configure mypy or pyright for type checking
```

---

## File Map

```
cli/metrics/
├── __init__.py    197 lines — group + 3 commands + _resolve_project_root
└── README.md               — this file
```

---

## Dependency Graph

```
__init__.py
├── click                ← click.group, click.command
├── config.loader        ← find_project_file (lazy)
└── metrics.ops          ← project_health, project_summary (lazy)
```

---

## Registration

Registered in `src/main.py`:

```python
from src.ui.cli.metrics import metrics
```

---

## Design Decisions

### Why summary and health are separate

`summary` is fast — it reads project metadata without running
any probes. `health` runs 7+ probes that may invoke external
tools (git, docker, npm). Keeping them separate lets users
get a quick overview without waiting for the full analysis.

### Why report outputs raw Markdown

The report command prints Markdown to stdout instead of writing
a file. This follows Unix conventions: pipe to a file if you
want persistence (`> HEALTH.md`), or pipe to other tools for
further processing.

### Why the score bar uses block characters

The `████░░░░` visualization gives an immediate visual signal
without requiring terminal color support. It works in any
terminal, piped output, and CI logs.
