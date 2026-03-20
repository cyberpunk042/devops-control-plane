# M5 — Frontend: Fix Every JavaScript Problem

> The frontend JavaScript was modified with blocking API calls, hardcoded values,
> duplicate calls, and missing loading states. Every change in _system_posture.html
> needs to be fixed.

---

## What Exists Now (broken)

### `moduleCompatAnalyze()` — Deep Analyze button
- Hardcodes `target_version: '3.8'` — wrong for any module with a different plan target
- Passes `include_transitive: true` by default — maximum analysis scope every time
- No loading state management — user clicks, waits 57s with no feedback

### `moduleCreatePlan()` — Plan creation
- Calls `/api/compat/assess` (57s) BEFORE creating the plan
- Then calls `/api/posture/module-plan` which internally calls assess AGAIN
- Total: two 57-second assess calls for one plan creation
- Shows a toast for 5s between the two calls

### Plan detail modal — setTimeout assess
- `setTimeout(100ms)` fires `/api/compat/assess` every time modal opens
- This blocks the server for 57+ seconds from a background call
- The assess data is informational only — not critical for the modal

### `moduleCompatFixAll()` — Fix all button
- After fixing, calls `postureRescan()` which does a full posture rescan (10+ seconds)
- Should use mediator cascade invalidation instead

### `_autoFixCompat()` — Individual fix button
- Calls `/api/posture/module-compat-fix` which creates an orchestrator + full analysis
  just to do a string replace

### `_modalApplyStep()` — Step execution results
- Shows compat_hints with auto-fix buttons that go through the broken compat-fix endpoint

---

## What M5 Delivers

### 1. Deep Analyze reads target from plan

```javascript
window.moduleCompatAnalyze = async function(moduleName) {
    // Read target from the module's plan, not hardcoded
    const planResp = await fetch('/api/posture/module-plan-detail?module=' + encodeURIComponent(moduleName));
    const planData = await planResp.json();
    const target = planData.target_floor || '3.8';

    const resp = await fetch('/api/compat/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            module: moduleName,
            target_version: target,
            include_transitive: false,  // direct only by default, transitive on request
        }),
    });
    ...
};
```

### 2. Plan creation — no pre-assess

Remove the `/api/compat/assess` call from `moduleCreatePlan()`. The plan endpoint
handles assessment internally. One call instead of two.

```javascript
window.moduleCreatePlan = async function(moduleName) {
    const target = ...;
    const date = ...;

    // Go straight to plan creation — no separate assess call
    const resp = await fetch('/api/posture/module-plan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ module: moduleName, target_floor: target, target_date: date }),
    });
    ...
};
```

### 3. Remove setTimeout assess from plan detail

Remove the entire `setTimeout(async () => { ... /api/compat/assess ... }, 100)` block.
The plan detail modal shows plan data from project.yml — it doesn't need a 57-second
assessment call.

If assessment info is desired, read it from the mediator cache via a non-blocking endpoint
that returns cached data or nothing — never triggers fresh computation.

### 4. Fix-all uses mediator cascade

After fixing, don't call `postureRescan()`. The fix endpoint (M4) already calls
`mediator.bust_path()` which cascades to posture. The frontend just needs to
re-fetch the updated posture:

```javascript
window.moduleCompatFixAll = async function(moduleName, targetVersion) {
    const resp = await fetch('/api/compat/fix/apply-all', { ... });
    const data = await resp.json();
    if (data.ok) {
        // Posture was already invalidated by the fix endpoint via mediator cascade
        // Just re-fetch the summary for badge update
        fetchSummary();
    }
};
```

### 5. Auto-fix uses legacy path

Until the compat engine is fully integrated (M3+M4), the auto-fix buttons should use
the legacy string-replace path which works in milliseconds:

```javascript
window._autoFixCompat = async function(moduleName, search, replace) {
    // The compat-fix endpoint (fixed in M4) tries compat cache first,
    // falls back to string replace. Either way it's fast now.
    const resp = await fetch('/api/posture/module-compat-fix', { ... });
    ...
};
```

### 6. Loading states for all compat operations

Every compat API call that might take >500ms should show a loading state:

```javascript
// Before call:
toast('🔍 Analyzing...', 'info');
// Or disable the button and show spinner

// After call:
// Show results or error
```

---

## Files Changed

| File | Action |
|------|--------|
| `src/ui/web/templates/scripts/globals/_system_posture.html` | Fix all 7 issues |

---

## Verification

1. "Deep Analyze" button reads target from module plan, not hardcoded '3.8'
2. Plan creation makes ONE API call, not two
3. Plan detail modal does NOT fire a background assess call
4. Fix-all does NOT call postureRescan() — relies on mediator cascade
5. No 57-second blocking from any frontend interaction
