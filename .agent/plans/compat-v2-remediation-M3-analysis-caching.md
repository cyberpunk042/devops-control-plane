# M3 — Analysis Caching: Results as Mediator Nodes

> Currently, every call to the compat engine runs a fresh full analysis. Results are
> computed, used once, thrown away. The mediator caches everything else in this program
> — posture, index, detect, devops. Compat analysis results must be cached the same way.

---

## What Exists Now (broken)

Every handler and endpoint that needs compat data runs `compat.detection.analyze_module()`
from scratch. That's a full scan of all files × all entries. Even after M2's performance
fix (down from 57s to ~3s), running 3s of work on every request is unacceptable when the
answer hasn't changed since the last scan.

The mediator already solves this for every other data source:
- `posture.modules` is cached with TTL=60s
- `index.scan` is cached with TTL=None (event-driven)
- `detect.docker` is cached with TTL=120s

Compat analysis results should work the same way.

---

## What M3 Delivers

### 1. `compat.analysis.{module}` mediator nodes

For each module in project.yml, register a dynamic mediator node:

```
Path:        compat.analysis.{module_name}  (e.g. compat.analysis.web, compat.analysis.core)
TTL:         None (event-driven — only recompute when files change)
Persist:     True (JSON shard — analysis results survive restart)
Depends on:  index.scan (cascade: when files change, analysis is invalidated)
```

Resolver:
- Gets orchestrator from `mediator.get("compat.orchestrator")`
- Gets module config (target version, direction) from project.yml
- Runs `compat.detection.analyze_module()` (the M2-optimized version)
- Returns AnalysisResult
- Cached until index.scan changes (i.e., until a file is modified)

### 2. Handlers read from mediator cache

Every handler that needs compat data reads from the mediator:

```python
# In any handler:
m = get_mediator()
result = m.peek("compat.analysis.web")
if result is not None:
    analysis = result["data"]
    # Use cached analysis — 0ms
else:
    # Compat not loaded yet — use legacy path
```

No handler ever calls `analyze_module()` directly. The mediator owns the computation.

### 3. Fix engine invalidates via mediator

When the fix engine modifies files:

```python
# After applying fixes to module "web":
m = get_mediator()
m.bust_path("compat.analysis.web", cascade=True)
# This cascades to posture.modules → posture.full → posture.summary
# Next get() recomputes from the fixed files
```

No manual rescan needed. The mediator cascade handles everything.

### 4. `/api/compat/analyze` reads from mediator

```python
@compat_bp.route("/compat/analyze", methods=["POST"])
def compat_analyze():
    module_name = body.get("module")
    m = get_mediator()

    # get() returns cached if fresh, recomputes if stale
    result = m.get(f"compat.analysis.{module_name}")
    analysis = result["data"]
    return jsonify({"ok": True, "findings": [...], ...})
```

First call: computes and caches. Subsequent calls: <1ms cache hit.
When files change: index.scan cascade invalidates, next call recomputes.

### 5. Background pre-computation

On server startup, after the registry loads (M1), dispatch analysis for all modules:

```python
# In register_compat():
for module in module_configs:
    mediator.dispatch(f"compat.analysis.{module['name']}")
    # BACKGROUND(5) priority — runs when nothing else needs capacity
```

By the time the user opens the posture modal, analysis is already cached.

---

## Files Changed

| File | Action |
|------|--------|
| `src/core/services/mediator/registrations/compat.py` | Add compat.analysis.* node registration |
| `src/core/services/compat/analysis/finding.py` | Add to_dict()/from_dict() for persistence |
| `src/core/services/compat/fix/engine.py` | Add mediator bust_path() after fixes |
| `src/ui/web/routes/compat.py` | Read from mediator instead of fresh analysis |

---

## Verification

1. `mediator.diag("compat.analysis.web")` shows cached with source="computed"
2. Second call to `/api/compat/analyze` for same module returns in <5ms
3. After editing a .py file, `index.scan` cascade invalidates `compat.analysis.*`
4. After fix, `compat.analysis.*` is invalidated and next read recomputes
5. Background dispatch populates cache before user interaction
