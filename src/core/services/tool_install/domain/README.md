# L1 Domain — Pure Logic

> Input → Output. No subprocess. No filesystem. No network.
> Fully testable with no mocks.

These functions operate on plan data, step dicts, and version strings.
They are called by the resolver (L2) and orchestrator (L5) to compute
risk levels, validate DAGs, generate rollback plans, etc.

---

## Files

### `risk.py` — Risk Assessment

Computes risk levels for steps and plans based on step type, sudo
requirements, and recipe-declared risk.

```python
from src.core.services.tool_install.domain.risk import _infer_risk, _plan_risk

risk = _infer_risk(step)       # → "low" | "medium" | "high"
plan_risk = _plan_risk(steps)  # → {"level": "high", "reasons": ["GPU driver install"]}
```

Used by the UI to show risk indicators:
| Risk | UI Treatment |
|------|-------------|
| `low` | Normal step, auto-proceed |
| `medium` | Yellow highlight, confirm prompt |
| `high` | Red highlight, expanded warning, backup shown |

### `dag.py` — Dependency Graph Logic

Manages step ordering for parallel execution. Adds implicit dependencies
(e.g. two apt-get steps can't run simultaneously), validates for cycles,
and determines which steps are ready to execute.

```python
from src.core.services.tool_install.domain.dag import _validate_dag, _get_ready_steps

errors = _validate_dag(steps)                      # → [] if valid
ready = _get_ready_steps(steps, done_set, running_set)  # → runnable steps
```

### `rollback.py` — Rollback Plan Generation

Given completed steps, generates undo steps using `UNDO_COMMANDS` (L0).

```python
from src.core.services.tool_install.domain.rollback import _generate_rollback

undo_steps = _generate_rollback(completed_steps)
# → [{"label": "Uninstall cargo-audit", "command": ["cargo", "uninstall", "cargo-audit"]}]
```

### `restart.py` — Restart Detection

Checks completed steps against `RESTART_TRIGGERS` to determine if the
user needs to restart their shell or system.

```python
from src.core.services.tool_install.domain.restart import detect_restart_needs

needs = detect_restart_needs(plan, completed_steps)
# → {"needs_restart": True, "type": "shell", "tools": ["rustup"]}
```

### `version_constraint.py` — Version Validation

Validates installed version against recipe constraints (semver comparison).

```python
from src.core.services.tool_install.domain.version_constraint import check_version_constraint

result = check_version_constraint("docker", "24.0.7", context)
# → {"ok": True} or {"ok": False, "reason": "Requires >= 25.0.0"}
```

### `input_validation.py` — User Input Validation

Validates user-provided inputs for choice answers and template values.
Uses recipe-declared validation rules (regex, enum, range).

### `error_analysis.py` — Build Error Pattern Matching

Parses build output to identify common failure patterns and suggest fixes.
Works on compiler errors, linker failures, missing headers, etc.

### `download_helpers.py` — Download UX Helpers

Format file sizes and estimate download times for UI display.

```python
from src.core.services.tool_install.domain.download_helpers import _fmt_size
_fmt_size(1048576)  # → "1.0 MB"
```
