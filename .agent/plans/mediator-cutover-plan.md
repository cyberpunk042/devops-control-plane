# Mediator Full Cutover — Legacy Removal Plan

> **Status:** ✅ ALL PHASES COMPLETE — 363 tests pass
> **Executed:** 2026-03-12
> **Precondition:** Phases W1–W3 complete (trilateral cascade wired).
> **Result:** Disk cache fully removed from initial_state. Legacy index removed.

---

## Toggle Architecture (Preserved)

The peek/symbols heavy scan is behind `is_peek_index_enabled()`:

```
server.py:
  if is_peek_index_enabled(PROJECT_ROOT):
      start_index_watcher(...)    # mediator FS watcher (sole source)
  else:
      # nothing — peek feature disabled, no index at all
```

- Toggle OFF → no symbols, no peek, no heavy scan, no watcher
- Toggle ON → full symbols + peek via mediator, no legacy fallback

---

## Track A: Index/Peek Deadlock Resolution (C1-C3) ✅

### C1: Decouple peek.py from get_index() ✅

**Files changed:** `src/core/services/peek.py` (3 sites), `src/ui/web/routes/content/peek.py` (1 site)

Added `_get_index_data()` and `_get_index_symbols()` helpers that fetch
directly from the mediator (`m.get("index.files")` etc.), bypassing the
`get_index()` bridge entirely. This breaks the deadlock cycle:

```
BEFORE: peek resolver → get_index() → bridge → mediator → peek resolver → DEADLOCK
AFTER:  peek resolver → mediator.get("index.files") → done (no bridge)
```

### C2: Enable symbols/peek in the bridge ✅

**File changed:** `src/core/services/project_index.py`

Removed the "intentionally do NOT fetch" skip block. The bridge now reads
`index.symbols` and `index.peek` from the mediator. Safe because C1
eliminated the circular dependency.

### C3: Remove legacy start_project_index fallback ✅

**File changed:** `src/ui/web/server.py`

Removed the `start_project_index(root)` call. The mediator is the sole
index source. The peek toggle still gates the watcher.

---

## Track B: initial_state from Mediator (C4-C5) ✅

### C4+C5: Full cutover to mediator-powered initial_state ✅

**File changed:** `src/ui/web/server.py`

Removed `_get_devops_cache()` (mtime-based disk cache reader) entirely.
All 23 `_INJECT_KEYS` now map to mediator nodes via `_KEY_TO_MEDIATOR`:

| Key domain | Mediator path | Count |
|-----------|---------------|-------|
| detect cards | `detect.{key}` | 13 |
| GitHub API | `extra.gh_pulls/runs/workflows` | 3 |
| Project status | `extra.project_status` | 1 |
| Wizard detect | `extra.wiz_detect` | 1 |
| Audit L0/L1 | `extra.audit_*` | 5 |

**New registration file:** `src/core/services/mediator/registrations/extra.py`
Registers 10 `extra.*` nodes with the same resolvers the routes used.

`stale_ok=True` ensures the context processor never blocks page load.

---

## Mediator Node Summary (52 total)

| Domain | Nodes | Description |
|--------|-------|-------------|
| `index.*` | 9 | File/dir index, symbols, peek, stats |
| `detect.*` | 13 | Docker, K8s, Git, security, etc. |
| `devops.*` | 14 | 13 card mergers + devops.status |
| `posture.*` | 6 | 4 pillars + full + summary |
| `extra.*` | 10 | GitHub API, audit, wizard, project status |
| **Total** | **52** | |

---

## Tests

- 363 mediator tests pass
- Bridge tests updated (symbols/peek now provided)
- Startup tests updated (52 nodes, 5 domains)

---

## What "Done" Looks Like

1. ✅ Delete `.state/devops_cache.json` — no impact on initial_state
2. ✅ Legacy `_index` singleton no longer drives peek/symbols
3. ✅ `start_project_index()` no longer called
4. ✅ Dashboard loads via mediator cache (stale_ok=True)
5. ✅ Peek reads mediator directly (no bridge deadlock)
6. ✅ Toggle OFF disables heavy scan — no watcher, no symbols/peek
7. ✅ Toggle ON gives full scan via mediator — no legacy code involved
