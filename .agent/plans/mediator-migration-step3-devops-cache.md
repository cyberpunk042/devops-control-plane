# Step 3: Migrate devops_cache Consumers — Analysis & Plan

**Date:** 2026-03-13
**Status:** Phase A ✅, Phase B ✅, Phase C (partial) ✅

---

## The Landscape

`src.core.services.devops.cache` is a 766-line module that provides:

| Method | Purpose | Call Sites |
|--------|---------|------------|
| `get_cached(root, key, fn)` | mtime-based compute-or-return | 14 |
| `invalidate(root, key)` | remove single key from cache | 9 |
| `invalidate_scope(root, scope)` | remove keys by category | 3 |
| `invalidate_all(root)` | nuke entire cache | 1 |
| `invalidate_with_cascade(root, key)` | invalidate + dependents | 1 |
| `recompute_all(root)` | background sequential recompute | 2 |
| `register_compute(key, fn)` | register recompute function | 1 |
| `load_prefs(root)` | read devops_prefs.json | 5 |
| `save_prefs(root, prefs)` | write devops_prefs.json | 2 |
| `load_activity(root)` | read audit_activity.json | 1 |
| `DEVOPS_KEYS` / `INTEGRATION_KEYS` / `AUDIT_KEYS` | scope constants | 3 |

**Total: ~42 call sites across 10 files.**

---

## Categorization by Migrability

### Tier 1: NOT MIGRATABLE (different domain)

These methods operate on **preferences and activity logs**, not cached data.
They read/write flat JSON files. The mediator doesn't manage prefs.

| Method | Files | Decision |
|--------|-------|----------|
| `load_prefs()` | `batch.py`, `devops/__init__.py` | **Keep as-is** |
| `save_prefs()` | `devops/__init__.py` | **Keep as-is** |
| `load_activity()` | `api/audit.py` | **Keep as-is** |

**Rationale:** Preferences and activity logs are NOT cacheable data — they're
user configuration and audit trails. Moving them to the mediator would be
scope creep and architectural confusion.

### Tier 2: ALREADY DUAL-STACKED (invalidation)

These call `invalidate()` to bust the devops cache after mutation events.
The mediator ALSO gets busted via `_mediator_bust()` in the same flow.

| File | What it invalidates | Current state |
|------|-------------------|---------------|
| `helpers.py` `bust_tool_caches()` | integrations, devops, wiz:detect, tools, builders | Legacy-only bust |
| `gh_auth.py` (4 locations) | github, wiz:detect | Legacy-only bust |
| `devops/__init__.py` `devops_cache_bust()` | scope/card/all + `_mediator_bust()` | **Already dual-stacked** |

**Migration:**
- `devops/__init__.py` already calls `_mediator_bust()` alongside legacy bust — done
- `helpers.py` and `gh_auth.py` should ALSO bust the mediator
- BUT: since devops.* resolvers still call `get_cached()`, busting the
  legacy cache IS effectively busting the mediator (the resolver re-reads
  the file). So this is **already correct** — the mediator re-validates
  on next `get()` because the underlying file has changed.

**Decision:** Low priority. The dual bust is already working.

### Tier 3: MIGRATABLE (get_cached → mediator.get)

These call `get_cached()` directly in route handlers. The mediator already
has equivalent nodes for SOME of these keys.

| File | Key(s) | Mediator equivalent | Status |
|------|--------|-------------------|--------|
| `devops/detect.py` | `wiz:detect` | `detect.*` (individual nodes) | **No 1:1 node** |
| `scripts/registry.py` | `scripts` | None | **No mediator node** |
| `batch.py` `_resolve_tools` | `tools` | None | **No mediator node** |
| `batch.py` `_resolve_gh_status` | `github` | `devops.github` | ✅ Has node |
| `audit/analysis.py` | `audit:system`, `audit:deps`, etc. | None registered | **No mediator node** |
| `audit/analysis.py` | `audit:scores`, `audit:scores:enriched` | None registered | **No mediator node** |
| `audit/analysis.py` (L2) | `audit:l2:*` | None registered | **No mediator node** |
| `audit/async_scan.py` | `audit:l2:*`, `audit:scores*` | None registered | **No mediator node** |

**The problem:** Most of these keys (`wiz:detect`, `tools`, `builders`,
`scripts`, all `audit:*` keys) are NOT registered as mediator nodes.
The mediator only has:
- `devops.docker`, `devops.k8s`, `devops.git`, `devops.github`, etc. (13 card nodes)
- `devops.status` (aggregate)

It does NOT have nodes for: `wiz:detect`, `tools`, `builders`, `scripts`,
`audit:scores`, `audit:system`, `audit:deps`, `audit:structure`,
`audit:clients`, `audit:l2:*`, `audit:scores:enriched`.

### Tier 4: THE CORE BINDING (mediator resolvers → get_cached)

The devops.* resolvers in `registrations/devops.py` **call get_cached()**:

```python
def _make_resolver(ck, fn):
    return lambda: get_cached(root, ck, fn)
```

This means the mediator WRAPS the devops cache — it doesn't replace it.
The devops cache module is still the compute+persistence engine.
The mediator adds:
- Cascade invalidation graph
- `peek()` for instant non-blocking reads
- Unified tree for observability

**Removing devops_cache entirely would require:**
1. Moving mtime-based staleness detection INTO the mediator
2. Moving file persistence INTO the mediator (already has shard persistence)
3. Moving EventBus publishing INTO the mediator (already has subscribe)
4. Moving activity logging somewhere else
5. Moving per-key locking INTO the mediator (already has it)

This is a MAJOR refactor, not a migration step.

---

## Recommended Plan

### Phase A: Dead import cleanup (5 min, safe)

Remove unused `devops_cache` imports from:
- `tool_install.py` — imports but never calls
- `tool_execution.py` — imports but never calls

### Phase B: Add mediator bust to helpers/gh_auth (15 min, safe)

Add `_mediator_bust()` calls alongside legacy invalidation in:
- `helpers.py` `bust_tool_caches()`
- `gh_auth.py` (4 invalidation sites)

This ensures the mediator tree stays fresh after mutations,
even if the context processor uses mediator peek first.

### Phase C: Migrate route consumers to mediator ✅ (COMPLETE)

Registered **20 extra.* mediator nodes** (was 10). Tree now has **62 nodes** (was 52).

New nodes added in two batches:
- Batch 1 (4 nodes): `extra.tools`, `extra.builders`, `extra.scripts`, `extra.pages`
- Batch 2 (6 nodes): `extra.audit_system_deep`, `extra.audit_l2_structure`,
  `extra.audit_l2_quality`, `extra.audit_l2_repo`, `extra.audit_l2_risks`,
  `extra.audit_scores_enriched`

Migrated ALL routes that read `get_cached()` to prefer mediator first,
falling back to legacy cache when the mediator isn't available or when
`force=True` (bust).

**Migrated (32+ endpoints across 16 route files):**

*Extra.* domain routes:*
- `audit/analysis.py` — L0: `audit:system` → `extra.audit_system`
- `audit/analysis.py` — L0 deep: `audit:system:deep` → `extra.audit_system_deep`
- `audit/analysis.py` — L1: `audit:deps` → `extra.audit_deps`
- `audit/analysis.py` — L1: `audit:structure` → `extra.audit_structure`
- `audit/analysis.py` — L1: `audit:clients` → `extra.audit_clients`
- `audit/analysis.py` — `audit:scores` → `extra.audit_scores`
- `audit/analysis.py` — `audit:scores:enriched` → `extra.audit_scores_enriched`
- `audit/analysis.py` — L2 structure/quality/repo/risks via `_cache_or_needs_scan`
- `audit/async_scan.py` — all 6 phases → mediator-first with legacy fallback
- `audit/tool_install.py` — `tools` → `extra.tools`
- `devops/detect.py` — `wiz:detect` → `extra.wiz_detect`
- `pages/api.py` — `pages` → `extra.pages`; `builders` → `extra.builders`
- `scripts/registry.py` — `scripts` → `extra.scripts`

*Devops.* card routes:*
- `docker/detect.py` — `docker` → `devops.docker`
- `k8s/detect.py` — `k8s` → `devops.k8s`
- `integrations/git.py` — `git` → `devops.git`
- `integrations/github.py` — `github` → `devops.github`; `gh-pulls/runs/workflows`
- `ci/status.py` — `ci` → `devops.ci`
- `terraform/status.py` — `terraform` → `devops.terraform`
- `dns/__init__.py` — `dns` → `devops.dns`
- `infra/iac.py` — `env` → `devops.env`
- `testing/status.py` — `testing` → `devops.testing`
- `security_scan/detect.py` — `security` → `devops.security`; posture-summary → peek
- `docs/status.py` — `docs` → `devops.docs`
- `quality/status.py` — `quality` → `devops.quality`
- `packages/status.py` — `packages` → `devops.packages`
- `project/__init__.py` — `project-status` → `devops.status` (×2)

*Batch API:*
- `api/batch.py` — `github` → `devops.github`; `tools` → `extra.tools`

**Additional improvements:**
- `core.py` — `persist_node()` now gated on `node.persist` (saves disk I/O)
- `helpers.py` — `bust_tool_caches()` now also busts `extra.tools`, `extra.builders`, `extra.wiz_detect`

### Phase D: Unwrap resolvers from get_cached (MUCH LARGER, future)

Replace the devops.* resolver pattern from:
```python
lambda: get_cached(root, ck, fn)
```
to:
```python
lambda: fn()  # compute directly, mediator handles caching
```

This would make the mediator the SOLE caching layer, eliminating
the devops_cache.json file entirely. BUT this requires:
- Mediator mtime-based staleness (currently in devops cache)
- Mediator activity logging (currently in devops cache)
- Migrating all EventBus events (currently from devops cache)

**Verdict: Phase D is a separate milestone, not part of this migration.**

---

## Summary

| Phase | Status | Files Changed | Impact |
|-------|--------|--------------|--------|
| **A** | ✅ | 2 files | Removed dead imports |
| **B** | ✅ | 2 files | Added mediator bust to 5 invalidation sites |
| **C** | ✅ | 16 route files + registrations + tests | 20 extra nodes, 32+ endpoints migrated |
| **D** | Future | — | Full devops_cache elimination |

