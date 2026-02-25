# Tier 2 — Plan Generation Analysis

> **Created: 2026-02-24 (evening)**
> 
> This is the pre-implementation analysis for Tier 2 of the tool
> install v2 system. NO CODE is written until we agree on the
> approach. Follows the "think before acting" rule.

---

## What Tier 2 Covers (From Implementation Status)

| # | Item | Spec Source |
|---|------|------------|
| 3 | Build system adapters | Phase 5 spec §Build System Adapters |
| 4 | Config template system | domain-config-files §Template Schema |
| 5 | Risk system | domain-risk-levels §Risk Classification |

---

## Inventory: What Exists vs What's Missing

### Build System Adapters (Item #3)

**WHAT EXISTS in `tool_install.py`:**

| Function | Line | Status |
|----------|------|--------|
| `detect_build_toolchain()` | 2873 | ✅ Detects gcc, g++, clang, cmake, ninja, etc |
| `_execute_source_step()` | 2974 | ✅ git clone + tarball download |
| `_execute_build_step()` | 3036 | ✅ Generic build command with parallel flag |
| `_execute_install_step()` | 3076 | ✅ Install command with sudo |
| `_execute_cleanup_step()` | 3093 | ✅ Remove build directory |
| `execute_plan_step()` | 3705 | ✅ Dispatcher handles all 5 build step types |

**WHAT'S MISSING:**

| Function | Purpose | Complexity |
|----------|---------|-----------|
| `_autotools_plan()` | Generate configure→make→install steps | Medium |
| `_cmake_plan()` | Generate cmake configure→build→install steps | Medium |
| `_cargo_git_plan()` | Generate cargo install --git step | Low |
| `_check_build_resources()` | Pre-build disk/RAM check | Low |
| `_analyse_build_failure()` | Parse stderr for common errors | Medium |
| Build flag substitution | `{nproc}`, `{cuda_flag}` in commands | Low |

**Assessment:** The step executors exist. The adapters are plan
_generators_ — they take a recipe + system profile and produce a
list of steps. They're basically factory functions. This is the
simplest Tier 2 item.

**Dependencies:** None — these are pure functions that return step
lists. The step executors already handle all the step types.

### Config Template System (Item #4)

**WHAT EXISTS in `tool_install.py`:**

| Function | Line | Status |
|----------|------|--------|
| `_execute_config_step()` | 3457 | ✅ write/append/ensure_line |
| `_evaluate_condition()` | 1047 | ✅ has_systemd, not_root, not_container |
| Config backup (timestamped) | Inside config step | ✅ cp -p with timestamp |

**WHAT'S MISSING:**

| Function | Purpose | Complexity |
|----------|---------|-----------|
| `_render_template()` | `{var}` substitution in template strings | Low |
| `_validate_input()` | Validate input values against type schema | Medium |
| `_validate_output()` | Post-render format validation (JSON/YAML/INI) | Medium |
| `action: "template"` in config step | Full template pipeline | Medium |
| Additional conditions | `has_openrc`, `file_exists:PATH`, `is_root`, `has_docker` | Low |
| `config_templates` in recipe format | Schema integration with TOOL_RECIPES | Low |

**Assessment:** The config step executor already handles write, append,
ensure_line. What's missing is the `template` action, which is the
full pipeline: collect inputs → validate → render → validate output
→ backup → write → post-command. This is a coordinated pipeline, not
complex algorithmically but has many moving parts.

**Dependencies:**
- Input validation needs the input type definitions (which are just
  schema checks — no external deps)
- Output validation for JSON is trivial (`json.loads()`), YAML needs
  `yaml` (already in requirements), INI uses `configparser` (stdlib)
- Additional conditions depend on deep tier data (now available from
  Tier 1!)

### Risk System (Item #5)

**WHAT EXISTS in `tool_install.py`:**

| Function | Line | Status |
|----------|------|--------|
| `needs_sudo` field on steps | Throughout | ✅ Already used |
| `risk` field | — | ❌ Not used anywhere |
| Risk-based UI | — | ❌ Not implemented |

**WHAT'S MISSING:**

| Function | Purpose | Complexity |
|----------|---------|-----------|
| `_infer_risk()` | Infer risk from step context (sudo, kernel, driver) | Low |
| `_plan_risk()` | Aggregate step risks to plan-level risk | Low |
| `_backup_before_step()` | Backup paths listed in `backup_before` | Low |
| Risk field addition to plan output | Add `risk` to plan steps + plan-level | Low |
| Confirmation gate data | Return risk metadata in plan for frontend use | Low |
| Risk escalation | Runtime risk change — COMPLEX, deferred | High |

**Assessment:** This is mostly about **enriching the plan output** with
risk metadata. The actual enforcement (confirmation gates, double-confirm)
is a **frontend concern**. The backend just needs to:
1. Tag each step with a risk level
2. Compute plan-level risk
3. Include backup paths for high-risk steps
4. Return all of this in the plan response

**Dependencies:**
- `_backup_before_step()` depends on step execution (called during
  execute_plan_step, not during planning)
- The rest is plan enrichment — pure computation

---

## Dependency Graph

```
                    ┌─────────────────┐
                    │   Deep Tier     │
                    │   (Tier 1) ✅   │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
             ┌─────│  Condition Eval  │─────┐
             │     │  (extend)        │     │
             │     └────────┬────────┘     │
             │              │              │
    ┌────────▼──────┐ ┌────▼──────────┐ ┌──▼──────────────┐
    │ Risk System   │ │ Config Tmpl   │ │ Build Adapters  │
    │ (Item #5)     │ │ (Item #4)     │ │ (Item #3)       │
    │               │ │               │ │                 │
    │ _infer_risk() │ │ _render()     │ │ _autotools()    │
    │ _plan_risk()  │ │ _validate()   │ │ _cmake()        │
    │ _backup()     │ │ template act  │ │ _cargo_git()    │
    └───────────────┘ └───────────────┘ └─────────────────┘
         │                   │                   │
         └───────────────────┼───────────────────┘
                             │
                    ┌────────▼────────┐
                    │ Tier 3: Recipes │
                    │ (uses all above)│
                    └─────────────────┘
```

Key insight: **All 3 items are independent of each other.** They
all feed into Tier 3 (recipe data). We can implement them in any
order.

---

## Recommended Implementation Order

### Phase A: Risk System (simplest, highest leverage)

**Why first:** Every plan already emits step dicts. Adding `risk`
is just enrichment — small code surface, zero breaking changes,
and it enables the frontend to show risk indicators immediately.

**Scope:**
1. `_infer_risk(step)` — 20 lines, pure function
2. `_plan_risk(steps)` — 10 lines, pure function
3. `_backup_before_step(step)` — 15 lines, file copy
4. Wire into `resolve_install_plan()` — add `risk` to each step
5. Wire into `execute_plan_step()` — call `_backup_before_step()` for high-risk
6. Return plan-level `risk` + `risk_summary` in plan response

**Estimate:** ~80 lines of code. No new dependencies.

**Testable:** Call `/api/audit/install-plan` with `{"tool": "docker"}`,
verify the response includes `risk` on each step and plan-level risk.

### Phase B: Build System Adapters (medium, fills a real gap)

**Why second:** These are factory functions that generate step lists.
The step executors already work. The adapters just need to produce
the right step dicts.

**Scope:**
1. `_autotools_plan(recipe, profile, build_dir)` — 30 lines
2. `_cmake_plan(recipe, profile, build_dir)` — 40 lines
3. `_cargo_git_plan(recipe, profile)` — 15 lines
4. `_check_build_resources(recipe)` — 25 lines
5. Variable substitution: `{nproc}`, `{cuda_flag}` in command arrays — 20 lines
6. Wire adapter selection into `resolve_install_plan()` — 20 lines

**Estimate:** ~150 lines. No new dependencies.

**Testable:** Can't fully test without build-from-source recipes in
TOOL_RECIPES (Tier 3). But the functions can be unit-tested with
synthetic recipe dicts.

### Phase C: Config Template System (most complex, most moving parts)

**Why last:** It has the most moving parts (input validation, template
rendering, output validation, the full pipeline). It also needs Tier 3
recipes (Docker daemon.json, journald config) to be truly useful.

**Scope:**
1. `_render_template(template, inputs)` — 10 lines
2. `_validate_input(input_def, value)` — 30 lines (6 input types)
3. `_validate_output(content, format)` — 25 lines (JSON/YAML/INI/raw)
4. `action: "template"` in `_execute_config_step()` — 40 lines
5. Additional conditions in `_evaluate_condition()` — 20 lines
6. Wire `config_templates` from recipe into plan generation — 30 lines

**Estimate:** ~155 lines. Needs `yaml` import for YAML validation
(already available in the project).

**Testable:** Can test `_render_template()` and `_validate_input()`
with unit data. Full pipeline needs config template recipes (Tier 3).

---

## What We Are NOT Doing in Tier 2

These are explicitly deferred to Tier 4+ per the status doc:

| Item | Why Deferred | Tier |
|------|-------------|------|
| `execute_plan_dag()` (async parallel) | Complex, needs depends_on field everywhere | 4 |
| `_validate_dag()` (Kahn's algorithm) | Only needed once DAG engine exists | 4 |
| Risk escalation mid-plan | Runtime complexity, dynamic re-confirmation | 4 |
| State persistence (pause/resume) | JSON file persistence, resume detection | 4 |
| Plan engine state machine | CREATED→RUNNING→PAUSED→DONE transitions | 4 |
| `_analyse_build_failure()` | Nice-to-have, not blocking | 5 |
| Progress parsing (cmake/ninja %) | Frontend display concern | 5 |
| Build failure analysis | Post-mortem, not core path | 5 |

---

## Pre-Flight Checklist

Before implementing, verify:

- [x] All domain docs read (build-from-source, build-systems,
      config-files, risk-levels)
- [x] Phase specs read (Phase 5, Phase 8)
- [x] Existing code inventoried (execute steps, dispatcher, conditions)
- [x] Dependency graph mapped (all 3 are independent)
- [x] What's NOT in scope is explicit
- [ ] **User approval of implementation order and scope**

---

## Summary

| Phase | Item | Lines | Dependencies | Blocking? |
|-------|------|-------|-------------|-----------|
| A | Risk system | ~80 | None | No |
| B | Build adapters | ~150 | None | No |
| C | Config templates | ~155 | yaml (available) | No |
| **Total** | **All Tier 2** | **~385** | **None** | **No** |

All 3 are pure-function/enrichment work. No new routes needed.
No breaking changes. Each phase is independently testable.

The real value unlock happens when Tier 3 adds the recipe data
that uses these systems (GPU driver recipes, data pack recipes,
config template recipes — the 36 missing recipe definitions).

---

## Traceability

| This analysis | References |
|---------------|-----------|
| Risk functions | domain-risk-levels §_infer_risk, §_plan_risk, §_backup_before_step |
| Build adapters | Phase 5 spec §Build System Adapters |
| Config templates | domain-config-files §Config Template Schema |
| Existing executors | tool_install.py lines 2974-3568 |
| Existing conditions | tool_install.py line 1047 |
| Implementation priority | tool-install-v2-implementation-status.md §Tier 2 |
