# E9 Chunk 2 — Automation Engine (Python)

> Automation handlers for Python module upgrade/downgrade steps.
> Depends on: Chunk 1 (checklist generation) complete.
> Architecture: `.agent/docs/E9-checklist-automation-architecture.md`
> Status: SCAFFOLD — not ready for execution until Chunk 1 ships

---

## What This Chunk Delivers

Plan steps that have an `automation_id` become actionable. The user sees
an "automate" or "preview" button next to each automatable step in the plan modal.
Clicking it runs the handler — either directly (auto) or showing a preview first (semi-auto).

Python-specific handlers only. The architecture supports all languages but this chunk
implements Python automation exclusively.

---

## Scope

### Automation Handlers to Implement

| automation_id | What it does | Mode | Risk |
|---------------|-------------|------|------|
| `edit_pyproject_requires_python` | Edit `requires-python` in pyproject.toml | auto | low |
| `edit_setup_py_python_requires` | Edit `python_requires` in setup.py | auto | low |
| `check_dep_compat_pypi` | Query PyPI Requires-Python per dep | auto | low |
| `update_deps_interactive` | Show alternatives, user picks versions | semi-auto | medium |
| `scan_breaking_changes` | Scan code for version-breaking patterns | auto | low |
| `scan_incompatible_features` | Scan for features above target (downgrade) | auto | low |
| `remove_future_annotations` | Remove `__future__` imports (when safe) | auto | low |
| `add_future_annotations` | Add `__future__` imports where needed | auto | low |
| `modernize_type_hints` | Replace `typing.X` with builtins, show diff | semi-auto | medium |
| `update_ci_matrix` | Detect CI config + show proposed edit | semi-auto | medium |
| `rescan_module` | Invalidate + recompute posture | auto | low |

### API Endpoint

```
POST /api/posture/module-step-execute
  { module: "...", step_id: "edit_pyproject_requires_python:a1b2", mode: "preview"|"execute" }
```

### Frontend Changes

- Plan modal: add automation button per step (icon based on auto/semi-auto)
- Preview display: inline diff in same modal (no stacking)
- Execute feedback: step marked done, success/error toast
- Re-link step IDs to recipe at modal load time (split id on `:`, match automation_id)

---

## Files to Create

| File | Purpose | Est. Lines |
|------|---------|-----------|
| `module_upgrade/automation/__init__.py` | Handler registry dict | ~30 |
| `module_upgrade/automation/executor.py` | Dispatch, preview/execute routing, mark done | ~80 |
| `module_upgrade/automation/config_editor.py` | Edit pyproject.toml, setup.py | ~120 |
| `module_upgrade/automation/dep_checker.py` | PyPI queries, compatibility check | ~100 |
| `module_upgrade/automation/code_scanner.py` | Breaking changes, feature scan, __future__ | ~120 |

## Files to Edit

| File | Change |
|------|--------|
| `src/ui/web/routes/posture.py` | Add POST /posture/module-step-execute endpoint |
| `src/ui/web/templates/scripts/globals/_system_posture.html` | Plan modal: automation buttons, inline diff |
| `src/ui/web/static/css/admin.css` | Styles for automation buttons, diff display |

---

## Key Reuse

- `module_intel._scan_module_imports()` → dep checker uses existing import scanning
- `module_intel.compute_code_floor()` → code scanner extends existing feature detection
- `subprocess_runner._run_subprocess()` → for any shell commands needed
- `m.put("posture.modules", cascade=True)` → rescan handler
- `_adm()` → inline guidance in preview display
- Existing dep-alternatives endpoint pattern → dep checker follows same PyPI query approach

---

## Design Constraints

- **Preview before execute** for semi-auto steps (inline, same modal)
- **Atomic writes** for config file edits (read → modify → write, no partial state)
- **No execution without user consent** — auto steps still require the user to click
- **Mark done in project.yml** after successful execution
- **Cache PyPI results** in `.state/` for repeated queries
