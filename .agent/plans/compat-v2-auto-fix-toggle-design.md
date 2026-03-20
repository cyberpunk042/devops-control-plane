# Auto-Fix Toggle — Full Design

> The plan modal needs a checkbox that controls whether fix steps modify
> source files automatically or just show a preview. OFF by default.

---

## Current Flow (broken — always auto-applies)

```
Plan Modal
  ├── "▶ Run N automatable steps" button
  │     → _openStepModal(batch) → streamSSE(/api/posture/module-wizard)
  │       → wizard_batch() → execute_step(step_id, mode="execute")
  │         → handler runs in execute mode → MODIFIES FILES
  │
  ├── Individual "🔧 Automate" button
  │     → modulePlanAutomate() → fetch(preview) → modal → "Apply" button
  │       → _modalApplyStep() → fetch(mode="execute")
  │         → handler runs in execute mode → MODIFIES FILES
```

Both paths end at `mode="execute"` which modifies files. There's no gate.

---

## Target Flow (with checkbox)

```
Plan Modal
  ├── [checkbox] 🔧 Auto-fix mode (OFF by default)
  │
  ├── "▶ Run N automatable steps" button
  │     → sends auto_fix flag with the batch request
  │     → wizard_batch() passes flag to execute_step()
  │     → handler checks flag:
  │       ├── Flag ON  → execute mode, modify files
  │       └── Flag OFF → execute mode BUT fix handlers return preview
  │                       batch pauses, shows what would change
  │
  ├── Individual "🔧 Automate" button
  │     → preview fetch (always) → modal shows what would change
  │     → "Apply" button:
  │       ├── Auto-fix ON  → execute, modify files
  │       └── Auto-fix OFF → show confirmation: "Enable auto-fix to apply"
```

---

## What Changes

### 1. Frontend: Checkbox in plan modal

In `_renderPlanModal()`, add a checkbox between the progress bar and the batch button:

```
[x] 🔧 Auto-fix mode — When enabled, fix steps modify source files.
                         When disabled, fix steps only show what would change.
```

State stored in `window._compatAutoFixEnabled` (default: `false`).

### 2. Frontend: Batch button passes the flag

`modulePlanRunBatch()` reads the checkbox state and includes it in the SSE payload:

```javascript
const payload = {
    module: moduleName,
    wizard_type: 'batch',
    step_ids: stepIds,
    step_labels: stepLabels,
    auto_fix: window._compatAutoFixEnabled || false,  // NEW
};
```

### 3. Frontend: Individual apply passes the flag

`_modalApplyStep()` includes the flag in the execute request:

```javascript
body: JSON.stringify({
    module: moduleName,
    step_id: stepId,
    mode: 'execute',
    auto_fix: window._compatAutoFixEnabled || false,  // NEW
})
```

### 4. Backend: wizard route passes flag to batch

`posture_module_wizard()` reads `auto_fix` from the request body and passes it
to `wizard_batch()`:

```python
auto_fix = body.get("auto_fix", False)
for event in wizard_batch(ctx, step_ids, step_labels, project_root, auto_fix=auto_fix):
    yield _sse(event)
```

### 5. Backend: wizard_batch passes flag to execute_step

`wizard_batch()` accepts `auto_fix` parameter and passes it to `execute_step()`:

```python
def wizard_batch(ctx, step_ids, step_labels, project_root, auto_fix=False):
    ...
    result = execute_step(module_name, step_id, mode, project_root, auto_fix=auto_fix)
```

### 6. Backend: execute_step passes flag to handler

`execute_step()` accepts `auto_fix` and passes it via the context or as a parameter:

```python
def execute_step(module_name, step_id, mode, project_root, auto_fix=False):
    ...
    ctx = build_context(module_name, target, project_root)
    ctx.auto_fix = auto_fix  # Add to UpgradeContext
    result = handler(ctx, mode)
```

### 7. Backend: fix handlers check the flag

`handle_fix_compat_auto()` and `handle_add_future_annotations()` check `ctx.auto_fix`
before modifying files:

```python
def handle_fix_compat_auto(ctx, mode):
    if mode == "execute" and not ctx.auto_fix:
        # Return preview instead of executing
        return {
            "ok": True,
            "can_apply": True,
            "preview_type": "compat_fix_preview",
            "summary": "...",
            "auto_fix_required": True,  # tells UI to show toggle prompt
            ...
        }

    if mode == "execute" and ctx.auto_fix:
        # Actually apply fixes
        ...
```

### 8. Backend: step-execute route passes flag

`posture_module_step_execute()` reads `auto_fix` from request and passes it:

```python
auto_fix = body.get("auto_fix", False)
result = execute_step(module_name, step_id, mode, project_root, auto_fix=auto_fix)
```

---

## What Stays the Same

- Non-fix steps (scan, dep check, CI, test, scaffold) — unaffected. They don't
  modify source code. The flag only gates fix-type handlers.
- Preview mode — always works regardless of flag. Shows what would change.
- The Automate button — always present. Always opens preview first.

---

## Step Types and the Flag

| Step type | auto_fix OFF | auto_fix ON |
|-----------|-------------|-------------|
| scan_incompatible_features | Normal — shows findings | Same |
| fix_compat_auto | Returns preview (what would change) | Applies fixes |
| add_future_annotations | Returns preview | Applies fixes |
| guide_incompatible_syntax | Normal — shows guide | Same |
| rescan_module | Normal — invalidates cache | Same |
| check_dep_compat_pypi | Normal — checks deps | Same |
| run_pip_install | Normal — runs subprocess | Same |
| scaffold_module_tests | Normal — creates test files | Same |
| run_isolated_tests | Normal — runs tests | Same |

Only `fix_compat_auto` and `add_future_annotations` are affected by the flag.

---

## Files Changed

| File | Change |
|------|--------|
| `_system_posture.html` | Checkbox in plan modal, pass flag in batch/apply payloads |
| `src/ui/web/routes/posture.py` | step-execute and wizard routes read `auto_fix` from body |
| `src/core/services/module_upgrade/context.py` | Add `auto_fix: bool = False` to UpgradeContext |
| `src/core/services/module_upgrade/automation/executor.py` | Pass `auto_fix` to handler via context |
| `src/core/services/module_upgrade/automation/wizard.py` | Accept and pass `auto_fix` parameter |
| `src/core/services/module_upgrade/automation/code_scanner.py` | Fix handlers check `ctx.auto_fix` |
