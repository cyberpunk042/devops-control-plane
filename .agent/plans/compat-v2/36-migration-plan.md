# 36 — Migration Plan (v1 → v2)

> **Document**: 36 of 37
> **Milestone**: Validation & migration
> **Status**: Draft

---

## 1. Purpose

This document specifies how to transition from the v1 system (`src/core/services/module_upgrade/automation/`) to the v2 system (`src/core/services/compat/`) without breaking the existing UI or disrupting in-progress plans.

---

## 2. Migration Phases

### Phase 1: Build v2 alongside v1

**Duration**: Milestones M1–M9

v2 is built in a NEW directory. v1 is untouched.

```
src/core/services/
├── module_upgrade/         ← v1 (unchanged)
│   ├── automation/
│   │   ├── code_scanner.py
│   │   ├── dep_checker.py
│   │   ├── executor.py
│   │   ├── test_env.py
│   │   └── wizard.py
│   ├── generator.py
│   └── context.py
│
└── compat/                 ← v2 (new)
    ├── database/
    ├── analysis/
    ├── fix/
    ├── backends/
    ├── lifecycle/
    └── edge_cases/
```

**Rules during Phase 1:**
- v1 code is NOT modified (except critical bug fixes)
- v2 code does NOT import from v1
- v1 routes (`/api/posture/module-*`) stay active
- v2 routes (`/api/compat/*`) are added alongside
- project.yml format is backward compatible (new fields are additive)

### Phase 2: Feature parity

**Duration**: Milestone M10

v2 handles everything v1 handles, plus more. Verification checklist:

| Capability | v1 | v2 | Verified |
|-----------|----|----|----------|
| Scan for incompatible features | ✅ | ✅ | |
| Add __future__ annotations | ✅ | ✅ | |
| Guide incompatible syntax | ✅ | ✅ | |
| Check dependency compatibility | ✅ | ✅ | |
| Generate pyproject.toml | ✅ | ✅ | |
| Update CI matrix | ✅ | ✅ | |
| Scaffold module tests | ✅ | ✅ | |
| Generate compatibility tests | ✅ | ✅ | |
| Set up test environment | ✅ | ✅ | |
| Run isolated tests | ✅ | ✅ | |
| Re-scan module | ✅ | ✅ | |
| Batch execution | ✅ | ✅ | |
| SSE streaming progress | ✅ | ✅ | |
| Plan modal UI | ✅ | ✅ | |

PLUS v2 additions:
- AST-based detection (not regex)
- Detection-fix coupling
- Transitive import analysis
- Step state machine (not boolean done)
- Verification loop
- Rollback
- 1000+ feature entries
- 100+ edge cases
- 10 languages

### Phase 3: Switchover

**Duration**: 1 milestone

1. **UI switchover**: Plan modal calls v2 API routes instead of v1
2. **CLI switchover**: CLI commands use v2 engine
3. **Route deprecation**: v1 routes return 301 redirects to v2 routes
4. **project.yml migration**: Script converts v1 plan format to v2

### Phase 4: Cleanup

**Duration**: 1 milestone

1. **Remove v1 code**: Delete `src/core/services/module_upgrade/automation/`
2. **Remove v1 routes**: Delete deprecated posture routes
3. **Remove v1 UI code**: Remove old modal functions
4. **Update documentation**: READMEs, references

---

## 3. project.yml Migration

### 3.1 v1 format

```yaml
version_plan:
  target: "3.8"
  date: Now
  checklist:
    - label: Scan for incompatible features
      id: scan_incompatible_features:abc123
      done: true
    - label: Run isolated tests
      id: run_isolated_tests:def456
```

### 3.2 v2 format

```yaml
version_plan:
  target: "3.8"
  direction: downgrade
  created_at: "2026-03-19T12:00:00Z"
  checklist:
    - label: Scan for incompatible features
      id: scan_incompatible_features:abc123
      state: passed
      done: true                    # Kept for backward compat
      completed_at: "2026-03-19T12:00:00Z"
    - label: Run isolated tests
      id: run_isolated_tests:def456
      state: pending
      done: false
```

### 3.3 Migration script

```python
def migrate_plan(plan: dict) -> dict:
    """Convert v1 plan format to v2.

    - Add 'direction' field (default: downgrade)
    - Add 'state' field derived from 'done'
    - Add timestamps where known
    - Keep 'done' field for backward compat
    """
    if "direction" not in plan:
        plan["direction"] = "downgrade"

    for step in plan.get("checklist", []):
        if "state" not in step:
            if step.get("done"):
                step["state"] = "passed"
            else:
                step["state"] = "pending"

    return plan
```

### 3.4 Automatic migration

When v2 reads a project.yml with v1-format plans, it auto-migrates in memory (does NOT write back). The first time a v2 operation modifies the plan, it writes back in v2 format.

---

## 4. Data Migration

### 4.1 Feature patterns → Feature database

v1 patterns in code → v2 YAML entries:

| v1 source | v2 destination |
|-----------|---------------|
| `_RUNTIME_FEATURES` in module_intel.py | `database/entries/python/stdlib.yml` + `syntax.yml` |
| `_ANNOTATION_FEATURES` in module_intel.py | `database/entries/python/typing.yml` |
| `_COMPAT_PATTERNS` in test_env.py | Merged into feature entries (fix section) |
| `_REWRITE_GUIDES` in code_scanner.py | Merged into feature entries (fix section) |

This is a ONE-TIME manual process during M1. The hardcoded patterns are the starting point for the feature database entries.

### 4.2 Existing plans

In-progress plans created by v1 continue to work:
- v2 reads v1 format (auto-migrates in memory)
- Completed steps stay completed
- Uncompleted steps are re-analyzed by v2 engine
- New steps may be added based on v2's more thorough analysis

---

## 5. Risk Mitigation

### 5.1 Parallel operation period

During Phase 2, BOTH v1 and v2 are available:
- v1 at `/api/posture/module-*`
- v2 at `/api/compat/*`

Users can switch between them. If v2 has issues, v1 is still available.

### 5.2 Feature flag

```yaml
# project.yml
compat:
  engine: v2        # "v1" | "v2" | "auto"
                    # auto = v2 if available, fallback to v1
```

### 5.3 Rollback to v1

If v2 has critical issues post-switchover:
1. Set `compat.engine: v1` in project.yml
2. v1 routes and engine are restored
3. v2 plans are compatible with v1 (v1 ignores extra fields)

---

## 6. Timeline

| Phase | Milestones | Description |
|-------|-----------|-------------|
| Phase 1 | M1–M9 | Build v2 alongside v1 |
| Phase 2 | M10 | Feature parity + UI integration |
| Phase 3 | Post-M10 | Switchover |
| Phase 4 | Post-switchover | Cleanup |

---

## 7. Integration Points

### 7.1 With all documents
- Migration plan is the thread connecting all 37 documents
- Each document's component replaces a v1 component
- Document 01 (architecture) maps v1 → v2 component by component
