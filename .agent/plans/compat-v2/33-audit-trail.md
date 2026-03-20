# 33 — Audit Trail & History Spec

> **Document**: 33 of 37
> **Milestone**: M10 — Integration & UX
> **Status**: Draft

---

## 1. Purpose

The audit trail records every action taken by the compat system — every analysis, every fix, every state transition, every rollback. It answers: "what happened, when, and why?"

---

## 2. What Gets Recorded

### 2.1 State transitions

Every step state change is an audit event:

```python
@dataclass
class AuditEvent:
    timestamp: str              # ISO 8601
    event_type: str             # See types below
    module: str                 # Module name
    step_id: str | None         # Step ID if applicable
    actor: str                  # "system" | "user" | "batch"
    data: dict                  # Event-specific payload
```

Event types:

| Type | When | Key data |
|------|------|----------|
| `plan.created` | Plan created | target, direction, steps count |
| `plan.deleted` | Plan deleted | reason |
| `plan.completed` | All steps done | duration, results summary |
| `plan.rolled_back` | Full rollback | files restored, files deleted |
| `step.started` | Step began | step_id, label |
| `step.passed` | Step succeeded | duration, summary |
| `step.failed` | Step failed | error, duration |
| `step.needs_attention` | Findings exist | findings count, severity breakdown |
| `step.blocked` | Blocked by dep | blocked_by, reason |
| `step.skipped` | User skipped | — |
| `step.retried` | User retried | previous_state, run_count |
| `step.confirmed` | User confirmed reviewed | — |
| `analysis.completed` | Analysis ran | findings count, duration |
| `fix.applied` | Fix applied to file | file, feature_id, strategy |
| `fix.verified` | Fix verified | file, all checks passed |
| `fix.failed` | Fix verification failed | file, check that failed |
| `fix.rolled_back` | Fix rolled back | file, reason |
| `dep.checked` | Dependency checked | package, compatible |

### 2.2 Storage

Audit events are stored in a JSON lines file per module:

```
.compat-audit/
├── core.jsonl
├── web.jsonl
└── cli.jsonl
```

Each line is one JSON event:
```json
{"timestamp": "2026-03-19T12:00:00Z", "event_type": "step.passed", "module": "core", "step_id": "scan:abc", "actor": "batch", "data": {"duration_ms": 450, "findings": 15}}
{"timestamp": "2026-03-19T12:00:01Z", "event_type": "fix.applied", "module": "core", "step_id": "fix_utc:def", "actor": "user", "data": {"file": "src/core/models/action.py", "feature_id": "python.stdlib.datetime_utc"}}
```

### 2.3 Retention

- Keep last 1000 events per module
- Rotate when exceeding limit (oldest events dropped)
- No automatic cleanup — user can delete the audit directory

---

## 3. Querying the Audit Trail

```python
class AuditLog:
    def events(self, module: str, limit: int = 100) -> list[AuditEvent]:
        """Get recent events for a module."""

    def events_for_step(self, module: str, step_id: str) -> list[AuditEvent]:
        """Get all events for a specific step."""

    def events_by_type(self, module: str, event_type: str) -> list[AuditEvent]:
        """Filter events by type."""

    def step_history(self, module: str, step_id: str) -> StepHistory:
        """Get complete history of a step: all runs, states, errors."""

    def fix_history(self, module: str, file: str) -> list[AuditEvent]:
        """Get all fix events for a specific file."""

    def plan_summary(self, module: str) -> PlanAuditSummary:
        """Summarize the plan's audit history."""
```

### 3.1 StepHistory

```python
@dataclass
class StepHistory:
    step_id: str
    label: str
    current_state: str
    run_count: int
    first_run: str          # timestamp
    last_run: str           # timestamp
    total_duration_ms: int
    state_transitions: list[tuple[str, str, str]]  # (timestamp, from, to)
    errors: list[str]       # All error messages from failures
```

### 3.2 PlanAuditSummary

```python
@dataclass
class PlanAuditSummary:
    module: str
    created_at: str
    completed_at: str | None
    total_events: int
    total_fixes_applied: int
    total_fixes_verified: int
    total_fixes_rolled_back: int
    total_retries: int
    files_modified: list[str]
    duration_total_ms: int
```

---

## 4. CLI Access

```
$ controlplane compat audit core

Audit trail for module 'core':

  2026-03-19 12:00:00  plan.created        Target 3.8, 9 steps
  2026-03-19 12:00:01  step.passed         Scan — 15 findings, 0.45s
  2026-03-19 12:00:02  step.passed         Add __future__ — 3 files, 0.2s
  2026-03-19 12:00:03  fix.applied         action.py — datetime.UTC
  2026-03-19 12:00:03  fix.verified        action.py — all checks passed
  ... 25 more events

$ controlplane compat audit core --step fix_utc:def456

Step history: fix_utc:def456 (Fix datetime.UTC)
  Run 1: 2026-03-19 12:00:03 — PASSED (2.3s)
    Fixed 14 files, all verified

  State: passed
  Total runs: 1
  Total duration: 2.3s
```

---

## 5. Web UI Access

The audit trail is viewable in the plan modal under an "Audit" tab:

```
┌──────────────────────────────────────────────────────────┐
│ Plan │ Steps │ Findings │ Audit                          │
│                                                         │
│ Recent events:                                           │
│                                                         │
│ 12:00:03  ✅ fix.verified    action.py — datetime.UTC   │
│ 12:00:03  🔧 fix.applied    action.py — datetime.UTC   │
│ 12:00:02  ✅ step.passed    Add __future__ (0.2s)       │
│ 12:00:01  ⚠️ step.attention Scan (15 findings)          │
│ 12:00:00  📋 plan.created   Target 3.8, 9 steps         │
│                                                         │
│ [Load More]                                  [Close]    │
└──────────────────────────────────────────────────────────┘
```

---

## 6. Integration Points

### 6.1 With Lifecycle (Document 06)
- Every state transition writes an audit event
- Audit log is the source of truth for step history

### 6.2 With Fix Engine (Document 05)
- Every fix application/verification/rollback writes an audit event

### 6.3 With API (Document 30)
- `GET /api/compat/audit/{module}` returns audit events
- Filterable by event_type, step_id, date range
