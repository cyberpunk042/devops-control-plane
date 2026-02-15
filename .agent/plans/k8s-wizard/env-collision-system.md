# Env Collision System — Status

## ✅ Completed

### Validator Core (`_wizValidation`)
- Shared validator `envCollision` registered on scope `*` (fires for both `dk` and `k8s`)
- `recheck(prefix)` triggers all shared + prefix-specific validators

### Input Collection
- Queries from `{prefix}-svc-env-list-{svcId}` containers (not global DOM scan)
- Docker: skips unchecked infra checkboxes (`mf-dk-infra-*`)
- K8s: skips hidden service cards (`k8s-mod-card-*` with `display:none`)
- K8s: also collects from `k8s-comp-env-list-*` (companion env vars)

### Temporal Ordering (data-env-ts)
- Each key input gets `data-env-ts = Date.now()` on first interaction
- Set in: oninput (first keystroke), auto-fill (_onVarSelect), and pre-Phase-1 stamping for pre-populated keys
- Cross-service collision warning only shows on the NEWER input (later timestamp)
- Same-service duplicates (RED) always show on BOTH sides
- Tiebreaker for equal timestamps: DOM order (first in keyInputs = owner)

### Smart Key Sync (data-last-var)
- When user changes variable dropdown from X to Y, key updates from X to Y if key still matches X
- If key was manually edited, it's not overridden
- Tracked via `data-last-var` on the key input

### Vault Creation Dedup (_setElsewhere)
- When cross-service collision detected on newer input: entire notice div hidden (data-hidden-by-collision)
- Dupe warning div ("Also defined on: MySQL") is the only message shown
- When collision clears: notice restored, creation form visible again

### Delete Button Fix
- K8s delete button: `_updateEnvSummary('infra-mysql')` now properly quoted (was `_updateEnvSummary(infra-mysql)` → ReferenceError)

## ⏳ Remaining Work

### K8s Backend Integration
- K8s wizard step 2 backend routes need to handle the env collision state
- Saving/loading wizard state with env vars and collision resolution
- K8s infra add handler: ensure timestamps are set when infra card is dynamically added

### Docker Backend
- Docker wizard backend needs similar env collision state handling

### Edge Cases to Test
- Two app services both adding same key (app-vs-app collision)
- Companion env vars colliding with main pod env vars
- Infra-vs-infra collisions (e.g., PostgreSQL + TimescaleDB both with POSTGRES_DB)
- Toggle infra off → collision should clear on app service
- Toggle infra back on → collision should reappear on correct side

### Cleanup
- The `elsewhere` logic in `_onVarSelect` / `_dkOnVarSelect` (lines ~3497-3505 / ~1720-1728) has dead code: both if/else branches do the same thing. Can be simplified since the validator now controls elsewhere visibility.
