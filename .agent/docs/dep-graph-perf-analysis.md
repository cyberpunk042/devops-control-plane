# Dependency Graph Performance Analysis

## Problem

Graph view shows "Building dependency graph..." for 6+ seconds, even when nothing changed.

## Measured timings

| Endpoint | .venv target | .venv-ft target | No venv |
|---|---|---|---|
| `/dep-graph` | **6.2s** | 0.8s | 0.9s |
| `/graph` | 0.4s | ~0.04s | 0.04s |
| **Combined** | **~6.5s** | ~0.8s | ~0.9s |

## Root causes

### 1. Sequential per-package subprocess calls (CRITICAL)

`get_package_deps_batch()` in `subdeps.py` runs `_pip_show()` for EACH declared package sequentially.
Each `_pip_show()` spawns a subprocess: `python -m pip show <package>` (10s timeout).

With 15 packages × ~0.4s each = **6 seconds**.

**`pip show` accepts multiple packages in ONE call** — already verified:
- 15 separate calls: **5.4s**
- 1 batch call: **0.5s** (11x faster)

### 2. No caching on sub-dep results

`get_package_deps_batch()` has zero caching. Every graph render re-queries all sub-deps even if nothing changed.
The tree data is mediator-cached (300s TTL), but sub-deps are computed fresh every time.

### 3. `get_installed_packages()` called redundantly

When `venv` param is specified:
- `dep_full_graph()` calls `get_installed_packages()` at line ~220 for status patching
- `get_package_deps_batch()` calls it AGAIN internally at line 199
- `dep_graph()` calls it AGAIN for its own status patching

That's 3 subprocess calls for the same data within one page load.

### 4. Fallback chain adds latency for .venv

`.venv` has pip installed → uses `python -m pip show` (~0.4s per call).
`.venv-ft` has NO pip → pip fails, falls back to `uv pip show` (~0.05s per call).
The fallback itself doesn't add much time, but pip is inherently slower than uv.

## Fix plan

### Fix 1: Batch `pip show` into ONE subprocess call

Replace the per-package loop in `get_package_deps_batch()` with a single call:
`pip show pkg1 pkg2 pkg3 ...` → parse `---`-separated output.

Expected improvement: 6.2s → ~1s for .venv target.

### Fix 2: Cache sub-dep results with TTL

Sub-dependencies don't change unless packages are installed/removed.
Cache `get_package_deps_batch()` results keyed by (venv_path, frozenset(packages)).
TTL: 300s (same as tree). Invalidate on `dependency.installed` change.

### Fix 3: Pass installed dict to avoid redundant subprocess calls

`dep_full_graph()` already calls `get_installed_packages()` — pass that dict
into `get_package_deps_batch()` instead of letting it call again internally.

### Fix 4: Also pass `venv` to `/graph` endpoint (done)

Already implemented in this session.

## Expected result after fixes

| Endpoint | .venv target (before) | .venv target (after) |
|---|---|---|
| `/dep-graph` | 6.2s | ~0.8s (batch pip show) |
| `/graph` | 0.4s | 0.4s (unchanged) |
| Cached hit | N/A | ~0.04s |
