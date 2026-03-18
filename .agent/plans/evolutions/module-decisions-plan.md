# Module Decisions — Clean Implementation Plan
> Status: PLAN — 2026-03-18

---

## Data Model

### New nested models in project.py

```python
class ModuleDeferral(BaseModel):
    """A deferred posture warning — team decision to address later."""
    until: str = ""       # "2026-09-01" or "Q3 2026"
    reason: str = ""      # why it's deferred

class ModuleVersionPlan(BaseModel):
    """A version upgrade plan — team commitment to raise the floor."""
    target: str = ""      # target floor version, e.g. "3.12"
    date: str = ""        # target date, e.g. "Q3 2026"

class ModuleRef(BaseModel):
    # Identity
    name: str
    path: str
    domain: str = "service"
    stack: str = ""
    description: str = ""

    # Decisions (team, version-controlled)
    version_strategy: Literal["latest", "compatibility", ""] = ""
    version_note: str = ""
    deferral: ModuleDeferral | None = None
    version_plan: ModuleVersionPlan | None = None
```

### In project.yml

```yaml
modules:
  - name: core
    path: src/core
    domain: library
    stack: python-lib
    version_strategy: compatibility
    version_note: "We only deploy on 3.12+"
    deferral:
      until: "2026-09-01"
      reason: "Waiting for vendor SDK 3.10 support"
    version_plan:
      target: "3.12"
      date: "Q3 2026"

  - name: web
    path: src/ui/web
    domain: ops
    stack: python-flask
    # no decisions — posture evaluates normally
```

When no deferral/plan exists, the field is absent from YAML (None in Python).
When set, it's a clean nested object. No flat field pollution.

---

## What Each Decision Does

### version_strategy
Already exists. Controls the evaluation lens.
- "latest" → warn about falling behind current
- "compatibility" → warn about EOL/CVEs, breadth is a strength
- "" → platform deduces from gap

### version_note
Already exists. Human explanation visible on posture card.
Does NOT suppress warnings — just marks as acknowledged.

### deferral
Suppresses the posture warning until the date.
- Bridge reads `deferral.until` — if date hasn't passed, suppress warning
- If date HAS passed, re-surface with "deferral expired" indicator
- UI shows deferred modules differently (muted, with deferral info)
- Clearing a deferral = set `deferral: null` in project.yml

### version_plan
Records a team commitment to upgrade.
- Bridge reads `version_plan.target` and `version_plan.date`
- UI shows the plan on the posture card
- If date has passed without the floor being raised, show "plan overdue"
- Clearing a plan = set `version_plan: null` in project.yml

---

## What Changes

### Backend

**project.py** — add ModuleDeferral + ModuleVersionPlan models, add fields to ModuleRef

**posture.py endpoints** — all 3 write endpoints (module-note, module-defer, module-plan)
use the same project.yml write pattern but write nested objects:
```python
# Defer
mod["deferral"] = {"until": until, "reason": reason}

# Plan
mod["version_plan"] = {"target": target_floor, "date": target_date}

# Clear deferral
if clearing:
    mod.pop("deferral", None)
```

**bridges/modules.py** — the bridge reads decisions from project config:
```python
ref = module_refs.get(name)
deferral = getattr(ref, "deferral", None)
plan = getattr(ref, "version_plan", None)

# If deferred and date not passed → suppress warning
if deferral and deferral.until:
    # parse date, compare to today
    # if not expired: mark module as deferred, soften rank
    # if expired: mark as "deferral expired"
```

**posture.py enrichment** — pass deferral + plan data to frontend:
```python
item["deferral"] = {
    "until": deferral.until,
    "reason": deferral.reason,
    "expired": is_expired,
} if deferral else None

item["version_plan"] = {
    "target": plan.target,
    "date": plan.date,
    "overdue": is_overdue,
} if plan else None
```

### Frontend

**Posture table** — deferred modules show muted with a 📅 indicator.
Modules with plans show a 📋 indicator.

**Peek panels** — status peek shows deferral/plan info when present:
- "This module's warning is deferred until Q3 2026 because: [reason]"
- "This module has a plan to upgrade to ≥3.12 by Q3 2026"

**Remediation modal** — decide section shows existing deferral/plan
if already set, with option to modify or clear.

**Below-table sections** — deferred modules listed separately:
- "📅 core: deferred until 2026-09-01 (waiting for vendor SDK)"
- "📋 web: upgrading to ≥3.12 by Q3 2026"

---

## Execution Order

```
1. Add ModuleDeferral + ModuleVersionPlan to project.py
2. Update defer endpoint to write nested object to project.yml
3. Update plan endpoint to write nested object to project.yml
4. Update bridge to read deferral/plan from ModuleRef
5. Update enrichment to pass deferral/plan to frontend
6. Update posture table to show deferral/plan indicators
7. Update peek panels to show deferral/plan info
8. Update remediation modal to show/modify existing decisions
9. Delete .state/module_decisions.json references (dead code)
```
