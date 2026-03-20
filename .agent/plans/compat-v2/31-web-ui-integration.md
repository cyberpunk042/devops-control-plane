# 31 — Web UI Integration

> **Document**: 31 of 37
> **Milestone**: M10 — Integration & UX
> **Status**: Draft

---

## 1. Purpose

The web UI is how users interact with the compat system through the admin panel. This document specifies what the UI shows, how it maps to the API, and what UX improvements over v1 are required.

This is NOT a frontend implementation spec — it describes WHAT the UI does, not HOW it's rendered. Implementation details (HTML structure, CSS, JS functions) come during the coding phase.

---

## 2. UI Components

### 2.1 Module Posture Card — Compat Section

On the system posture page, each module card shows compat status:

```
┌─────────────────────────────────────────┐
│ web (src/ui/web)          Python 3.12   │
│                                         │
│ Version Floor: 3.11                     │
│ Version Plan: ↓ 3.8 (in progress)      │
│ Progress: ████████░░ 3/10 steps        │
│                                         │
│ [View Plan]  [Analyze]                  │
└─────────────────────────────────────────┘
```

### 2.2 Plan Modal

When user clicks "View Plan", a modal shows the full plan:

```
┌──────────────────────────────────────────────────────────┐
│ Version Plan: web → Python 3.8 (downgrade)              │
│                                                         │
│ ✅ Scan for incompatible features              passed   │
│ ✅ Add __future__ annotations (3 files)        passed   │
│ ⚠️ Fix incompatible code (15 findings)    attention    │
│    14 auto-fixable, 1 manual                            │
│    [Fix All Auto]  [View Findings]  [Skip]              │
│ ○ Verify fixes                               pending   │
│ ○ Check dependencies                         pending   │
│ ○ Update config                              pending   │
│ ○ Set up test environment                    pending   │
│ ○ Run compatibility tests                    pending   │
│ ○ Re-scan and confirm                        pending   │
│                                                         │
│ ─────────────────────────────────────────────           │
│ Progress: 2/9 passed  │  [Run Remaining]                │
│                                                         │
│ Footer: [Rollback Plan]                    [Close]      │
└──────────────────────────────────────────────────────────┘
```

### 2.3 Step States — Visual

| State | Icon | Background | Text | Actions |
|-------|------|------------|------|---------|
| PENDING | ○ | grey | "pending" | [Execute] [Skip] |
| RUNNING | ◉ (animated) | blue | "running..." | — |
| PASSED | ✅ | green | "passed" | — |
| FAILED | ❌ | red | error message | [Retry] [Skip] [View Error] |
| NEEDS_ATTENTION | ⚠️ | yellow | finding summary | [Fix All] [View] [Skip] [Confirm] |
| BLOCKED | 🔒 | orange | blocker info | [View Blocker] [Skip] |
| SKIPPED | ⏭️ | grey | "skipped" | — |

### 2.4 What is NOT shown

- **No "✅ Mark as done" on FAILED steps.** NEVER. This was a v1 bug.
- **No "✅ Mark as done" on NEEDS_ATTENTION steps** unless it's a read-only step where "Confirm reviewed" makes sense.
- **No confusing diff previews for test steps.** Test steps show clear info: "Will run pytest on Python 3.8 using venv at .venvs/web-3.8/"
- **No auto-executing steps that show a preview first.** If a step has a preview, the preview is informational. Execution is a separate explicit action.

---

## 3. Findings View

When user clicks "View Findings" on a NEEDS_ATTENTION step:

```
┌──────────────────────────────────────────────────────────┐
│ Incompatible Features Found                              │
│ Module: core │ Target: Python 3.8 │ 15 findings         │
│                                                         │
│ ┌─ datetime.UTC (14 files) ─────────── error ─── 🔧 ──┐│
│ │ src/core/models/action.py:11                          ││
│ │   from datetime import UTC, datetime                  ││
│ │ src/core/models/state.py:14                           ││
│ │   from datetime import UTC, datetime                  ││
│ │ ... 12 more files                                     ││
│ │                                                       ││
│ │ Fix: Replace UTC → timezone.utc (auto-fixable)       ││
│ │ [Fix All 14]  [View All Files]                       ││
│ └───────────────────────────────────────────────────────┘│
│                                                         │
│ ┌─ enum.StrEnum (1 file) ──────────── error ─── ⚠️ ──┐│
│ │ src/core/engine/executor.py:45                        ││
│ │   from enum import StrEnum                            ││
│ │                                                       ││
│ │ Fix: Manual — use backports.strenum or define base   ││
│ │ [View Instructions]                                  ││
│ └───────────────────────────────────────────────────────┘│
│                                                         │
│ Transitive findings (from other modules):               │
│ 🔒 None — this IS the root cause module                │
│                                                         │
│ [Fix All Auto (14)]  [Skip Step]              [Close]   │
└──────────────────────────────────────────────────────────┘
```

### 3.1 Fix result feedback

After clicking "Fix All":

```
┌──────────────────────────────────────────────────────────┐
│ Fixing datetime.UTC...                                   │
│                                                         │
│ ✅ src/core/models/action.py — fixed, verified          │
│ ✅ src/core/models/state.py — fixed, verified           │
│ ✅ src/core/persistence/audit.py — fixed, verified      │
│ ✅ src/core/engine/executor.py — fixed, verified        │
│ ... 10 more                                             │
│                                                         │
│ Result: 14/14 files fixed and verified                   │
│                                                         │
│ Remaining: 1 manual fix (StrEnum in executor.py)        │
│                                                         │
│ [Done]                                                  │
└──────────────────────────────────────────────────────────┘
```

### 3.2 Fix failure feedback

```
┌──────────────────────────────────────────────────────────┐
│ Fixing StrEnum...                                        │
│                                                         │
│ ❌ src/core/engine/executor.py                          │
│    Fix applied but verification FAILED                   │
│    → StrEnum still detected at line 45                   │
│    → File rolled back to original                        │
│                                                         │
│ The fix transform could not handle this pattern.         │
│ Manual fix required:                                     │
│                                                         │
│   Option 1: pip install backports.strenum               │
│     from backports.strenum import StrEnum                │
│                                                         │
│   Option 2: Define a base class                          │
│     class StrEnum(str, Enum): pass                       │
│                                                         │
│ [Close]                                                 │
└──────────────────────────────────────────────────────────┘
```

---

## 4. Batch Execution View

When user clicks "Run Remaining":

```
┌──────────────────────────────────────────────────────────┐
│ ▶ Running 7 steps                                        │
│                                                         │
│ ✅ Fix incompatible code           2.3s                  │
│    Fixed 14 files, verified                              │
│ ✅ Verify fixes                    0.8s                  │
│    All re-detections passed                              │
│ ✅ Check dependencies              1.2s                  │
│    All 12 packages compatible                            │
│ ✅ Update config                   0.1s                  │
│    Updated pyproject.toml                                │
│ ◉ Set up test environment          running...            │
│    Creating venv with Python 3.8...                      │
│ ○ Run compatibility tests          pending               │
│ ○ Re-scan and confirm              pending               │
│                                                         │
│ Progress: ████████████░░░░ 4/7 │ 4.4s elapsed           │
│                                                         │
│ [Cancel]                                                │
└──────────────────────────────────────────────────────────┘
```

### 4.1 Batch stops on failure

```
│ ✅ Fix incompatible code           2.3s                  │
│ ✅ Verify fixes                    0.8s                  │
│ ❌ Run compatibility tests         5.1s                  │
│    39 failed, 16 passed                                  │
│    [View Test Output]  [Retry]  [Skip]                  │
│ ○ Re-scan and confirm              pending               │
│                                                         │
│ ⚠️ Batch stopped — step failed                          │
```

---

## 5. Assessment View

Before creating a plan, show the assessment:

```
┌──────────────────────────────────────────────────────────┐
│ Version Change Assessment                                │
│ Module: web │ Direction: ↓ 3.11 → 3.8                   │
│                                                         │
│ Achievable: YES (after fixing dependencies)              │
│                                                         │
│ Code changes needed:                                     │
│   1 file: datetime.UTC → timezone.utc (auto-fix)        │
│                                                         │
│ Dependency changes: none                                 │
│                                                         │
│ ⚠️ Transitive blockers:                                 │
│   Module 'core' needs fixing first (14 files)            │
│   Recommended: run core's plan before web's              │
│                                                         │
│ Estimated effort: ~16 minutes                            │
│ Risk: LOW                                                │
│                                                         │
│ [Create Plan]  [Cancel]                                  │
└──────────────────────────────────────────────────────────┘
```

---

## 6. Import Graph Visualization

Optional — when user wants to understand dependencies:

```
┌──────────────────────────────────────────────────────────┐
│ Import Graph: web                                        │
│                                                         │
│   web/routes/backup/archive.py                           │
│     └─→ core/models/action.py  ⚠️ datetime.UTC         │
│     └─→ core/models/state.py   ⚠️ datetime.UTC         │
│                                                         │
│   web/routes/metrics/health.py                           │
│     └─→ (direct) ⚠️ datetime.UTC                       │
│                                                         │
│   web/routes/chat/messages.py                            │
│     └─→ core/services/chat/models.py ⚠️ datetime.UTC   │
│                                                         │
│ Legend: ⚠️ = incompatible feature in dependency          │
│                                                         │
│ [Close]                                                 │
└──────────────────────────────────────────────────────────┘
```

---

## 7. State Refresh

The UI must stay in sync with the backend state:

### 7.1 After step execution
- Re-fetch plan state from `GET /api/compat/plan/{module}`
- Update all step icons/colors/actions
- Update progress bar

### 7.2 After fix application
- Re-fetch findings from `POST /api/compat/analyze`
- Update findings count on the step
- If all findings resolved → step transitions to PASSED

### 7.3 After batch completion
- Re-fetch full plan state
- Show completion summary
- Update module card on posture page

### 7.4 No polling
- Individual actions: fetch after action completes
- Batch: SSE stream provides real-time updates
- No setInterval polling

---

## 8. Integration Points

### 8.1 With API (Document 30)
- All UI actions call API endpoints
- SSE streaming for batch execution
- UI renders API responses

### 8.2 With Lifecycle (Document 06)
- Step states from the state machine determine UI rendering
- UI never writes to project.yml directly — always through API → state machine

### 8.3 With Current UI
- New compat UI lives alongside existing posture UI during migration
- Eventually replaces the plan modal in `_system_posture.html`
