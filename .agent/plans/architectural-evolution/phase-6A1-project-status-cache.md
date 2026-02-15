# Phase 6A-1: Double Cache for `/api/project/status`

**Status:** Ready to implement  
**Parent:** Phase 6 — Caching Architecture  
**Priority:** 🔴 Critical — this is the single biggest blocker in the app

---

## Problem

`GET /api/project/status` calls `run_all_probes(root)` which runs 8 integration probes
(git, github, docker, cicd, k8s, terraform, pages, dns). Each probe may invoke
subprocess calls (`git`, `docker`, `gh`, `kubectl`, `terraform`). On a single-threaded
Flask dev server, this blocks ALL other requests for 3–10 seconds.

This endpoint is called:
1. From `_dashboard.html` → `loadSetupProgress()` (line 279)
2. From `_integrations_init.html` → `_fetchIntProjectStatus()` (line 17)
3. Both calls happen on the **same page load** if user was on the integrations tab

Neither call uses any cache — server or client.

---

## Changes Required

### 1. `devops_cache.py` — Add watch paths

**What:** Add a `"project-status"` key to `_WATCH_PATHS`.

**Watch paths:**
```python
"project-status": [
    ".git/HEAD", ".git/index",           # git state
    ".github/workflows/",               # CI/CD
    "Dockerfile", "docker-compose.yml", "docker-compose.yaml",  # Docker
    "k8s/", "kubernetes/",              # K8s
    "terraform/", "main.tf",            # Terraform
    "project.yml",                      # Pages/project config
    ".pages/",                          # Pages output
    "CNAME", "netlify.toml",            # DNS
],
```

**Note on `.git/`:** Using `.git/HEAD` and `.git/index` instead of `.git/` — the
directory mtime changes constantly (reflogs, etc.) which would defeat caching.
HEAD changes on checkout/commit, index changes on stage.

### 2. `routes_project.py` — Wrap in `get_cached()`

**Current code (line 33–42):**
```python
@project_bp.route("/project/status")
def project_status():
    statuses = run_all_probes(_root())
    return jsonify({
        "integrations": statuses,
        "suggested_next": suggest_next(statuses),
        "progress": compute_progress(statuses),
    })
```

**New code:**
```python
from src.core.services.devops_cache import get_cached

@project_bp.route("/project/status")
def project_status():
    root = _root()
    force = request.args.get("force") == "1"
    def _compute():
        statuses = run_all_probes(root)
        return {
            "integrations": statuses,
            "suggested_next": suggest_next(statuses),
            "progress": compute_progress(statuses),
        }
    return jsonify(get_cached(root, "project-status", _compute, force=force))
```

Also need to add `request` to the Flask import line.

### 3. `_dashboard.html` — Add client cache to `loadSetupProgress()`

**Current code (line 279):**
```js
const data = await api('/project/status');
```

**New code:**
```js
const cached = cardCached('project-status');
const data = cached || await api('/project/status');
if (!cached) cardStore('project-status', data);
```

### 4. `_integrations_init.html` — Add client cache to `_fetchIntProjectStatus()`

**Current code (line 14–22):**
```js
async function _fetchIntProjectStatus() {
    if (_intProjectStatus) return _intProjectStatus;
    try {
        _intProjectStatus = await api('/project/status');
    } catch {
        _intProjectStatus = { integrations: {}, progress: { complete: 0, total: 8, percent: 0 } };
    }
    return _intProjectStatus;
}
```

**New code:**
```js
async function _fetchIntProjectStatus() {
    if (_intProjectStatus) return _intProjectStatus;
    try {
        const cached = cardCached('project-status');
        _intProjectStatus = cached || await api('/project/status');
        if (!cached) cardStore('project-status', _intProjectStatus);
    } catch {
        _intProjectStatus = { integrations: {}, progress: { complete: 0, total: 8, percent: 0 } };
    }
    return _intProjectStatus;
}
```

This means:
- First call from dashboard caches it
- Second call from integrations tab gets it from sessionStorage
- Page refresh within 10 min gets it from sessionStorage
- Server only recomputes if watched files changed

---

## Files Modified

| File | Change |
|---|---|
| `src/core/services/devops_cache.py` | Add `"project-status"` watch paths |
| `src/ui/web/routes_project.py` | Wrap `project_status()` in `get_cached()` |
| `src/ui/web/templates/scripts/_dashboard.html` | Client cache in `loadSetupProgress()` |
| `src/ui/web/templates/scripts/_integrations_init.html` | Client cache in `_fetchIntProjectStatus()` |

## Verification

After implementation:
1. Load the app, switch to integrations tab
2. Check server logs: `/api/project/status` should appear **once** (not twice)
3. Refresh the page (F5) while still on integrations
4. Check server logs: `/api/project/status` should **NOT appear** (served from client cache)
5. Wait 10+ minutes and refresh — should re-fetch
6. Modify a Dockerfile and refresh — server should recompute (mtime changed)
