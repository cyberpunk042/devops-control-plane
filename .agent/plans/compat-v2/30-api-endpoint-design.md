# 30 — API & Endpoint Design

> **Document**: 30 of 37
> **Milestone**: M10 — Integration & UX
> **Status**: Draft

---

## 1. Purpose

The API layer exposes the compat engine to consumers: the web UI, the CLI, and any future integrations. All three call the same backend — the API is the single entry point. No consumer talks directly to the engine internals.

All routes live under `/api/compat/`. The old `/api/posture/module-*` routes remain for backward compat during migration but are deprecated.

---

## 2. Route Map

### 2.1 Analysis

| Method | Route | Purpose |
|--------|-------|---------|
| `POST` | `/api/compat/analyze` | Analyze a module for version compatibility |
| `POST` | `/api/compat/analyze-project` | Analyze entire project (all modules) |
| `GET` | `/api/compat/import-graph/{module}` | Get import dependency graph for a module |
| `GET` | `/api/compat/module-graph` | Get module-to-module dependency graph |
| `POST` | `/api/compat/assess` | Pre-plan assessment (is target achievable?) |

### 2.2 Plans

| Method | Route | Purpose |
|--------|-------|---------|
| `POST` | `/api/compat/plan/create` | Create a version plan for a module |
| `GET` | `/api/compat/plan/{module}` | Get current plan and step states |
| `DELETE` | `/api/compat/plan/{module}` | Delete a version plan |
| `POST` | `/api/compat/plan/{module}/rollback` | Rollback all plan changes |

### 2.3 Step execution

| Method | Route | Purpose |
|--------|-------|---------|
| `POST` | `/api/compat/step/execute` | Execute a single step |
| `POST` | `/api/compat/step/skip` | Skip a step |
| `POST` | `/api/compat/step/retry` | Retry a failed step |
| `POST` | `/api/compat/step/confirm` | Confirm a NEEDS_ATTENTION step as reviewed |
| `POST` | `/api/compat/batch/execute` | Execute multiple steps (SSE stream) |

### 2.4 Fixes

| Method | Route | Purpose |
|--------|-------|---------|
| `POST` | `/api/compat/fix/apply` | Apply fixes for specific findings |
| `POST` | `/api/compat/fix/apply-all` | Apply all auto-fixable findings in a module |
| `POST` | `/api/compat/fix/verify` | Verify a fix worked |
| `POST` | `/api/compat/fix/rollback` | Rollback a specific fix |

### 2.5 Feature database

| Method | Route | Purpose |
|--------|-------|---------|
| `GET` | `/api/compat/features` | Browse feature database (paginated) |
| `GET` | `/api/compat/features/{id}` | Get a single feature entry |
| `GET` | `/api/compat/features/search` | Search features by name/language/version |
| `GET` | `/api/compat/features/stats` | Feature database statistics |

### 2.6 Dependencies

| Method | Route | Purpose |
|--------|-------|---------|
| `POST` | `/api/compat/deps/check` | Check dependency compatibility |
| `GET` | `/api/compat/deps/alternatives/{package}` | Find compatible versions of a package |

---

## 3. Request/Response Formats

### 3.1 POST /api/compat/analyze

**Request:**
```json
{
  "module": "web",
  "target_version": "3.8",
  "direction": "downgrade",
  "include_transitive": true
}
```

**Response (200):**
```json
{
  "ok": true,
  "module": "web",
  "target_version": "3.8",
  "direction": "downgrade",
  "scan_duration_ms": 450,
  "files_scanned": 127,
  "summary": {
    "total_findings": 15,
    "direct": 1,
    "transitive": 14,
    "by_severity": {"error": 15, "warning": 0, "info": 0},
    "by_fix": {"auto_fixable": 14, "manual": 1, "no_fix": 0}
  },
  "findings": [
    {
      "feature_id": "python.stdlib.datetime_utc",
      "feature_name": "datetime.UTC",
      "file": "src/ui/web/routes/metrics/health.py",
      "line": 6,
      "col": 0,
      "source_line": "from datetime import UTC, datetime",
      "severity": "error",
      "error_type": "import_error",
      "is_transitive": false,
      "fix_available": true,
      "fix_strategy": "replace_import_and_usages"
    },
    {
      "feature_id": "python.stdlib.datetime_utc",
      "file": "src/core/models/action.py",
      "line": 11,
      "source_line": "from datetime import UTC, datetime",
      "severity": "error",
      "is_transitive": true,
      "imported_by": "src/ui/web/routes/backup/archive.py",
      "import_chain": [
        "src/ui/web/routes/backup/archive.py",
        "src/core/models/action.py"
      ],
      "source_module": "core",
      "fix_available": true
    }
  ],
  "blocking_modules": [
    {
      "module": "core",
      "findings_count": 14,
      "recommendation": "Fix module 'core' first"
    }
  ],
  "code_floor": "3.11",
  "dependency_floor": "3.8",
  "effective_floor": "3.11",
  "target_achievable": true,
  "target_achievable_after": "fixing 15 findings (14 auto, 1 manual)"
}
```

### 3.2 POST /api/compat/step/execute

**Request:**
```json
{
  "module": "core",
  "step_id": "fix_datetime_utc:abc123"
}
```

**Response (200):**
```json
{
  "ok": true,
  "step_id": "fix_datetime_utc:abc123",
  "state": "passed",
  "summary": "Fixed datetime.UTC in 14 files",
  "duration_ms": 2300,
  "fixes_applied": 14,
  "fixes_verified": 14,
  "fixes_failed": 0,
  "details": [
    {
      "file": "src/core/models/action.py",
      "fix_applied": true,
      "verified": true,
      "diff": "--- a/src/core/models/action.py\n+++ b/src/core/models/action.py\n@@ -11 +11 @@\n-from datetime import UTC, datetime\n+from datetime import timezone, datetime"
    }
  ]
}
```

**Response on failure (200 with state=failed):**
```json
{
  "ok": false,
  "step_id": "fix_strenum:def456",
  "state": "failed",
  "error": "Fix verification failed",
  "summary": "1 fix applied but verification failed — rolled back",
  "fixes_applied": 1,
  "fixes_verified": 0,
  "fixes_failed": 1,
  "fixes_rolled_back": 1,
  "details": [
    {
      "file": "src/core/engine/executor.py",
      "fix_applied": true,
      "verified": false,
      "verification_error": "StrEnum still detected at line 45 after fix",
      "rolled_back": true
    }
  ]
}
```

### 3.3 POST /api/compat/batch/execute (SSE)

**Request:**
```json
{
  "module": "core",
  "step_ids": ["scan:abc", "fix_utc:def", "verify:ghi"],
  "step_labels": ["Scan", "Fix UTC", "Verify"]
}
```

**Response: SSE stream**
```
data: {"type": "batch_start", "total_steps": 3}

data: {"type": "step_start", "step_index": 0, "label": "Scan", "step_id": "scan:abc"}
data: {"type": "step_log", "step_index": 0, "line": "Scanning 127 files..."}
data: {"type": "step_log", "step_index": 0, "line": "Found 15 incompatible features"}
data: {"type": "step_complete", "step_index": 0, "state": "needs_attention", "findings_count": 15}

data: {"type": "batch_stopped", "stopped_at": 0, "reason": "Step needs attention — 15 findings require action"}

data: {"type": "batch_complete", "steps_passed": 0, "steps_needs_attention": 1, "stopped": true}
```

### 3.4 POST /api/compat/fix/apply

**Request:**
```json
{
  "module": "core",
  "findings": [
    {"feature_id": "python.stdlib.datetime_utc", "file": "src/core/models/action.py", "line": 11},
    {"feature_id": "python.stdlib.datetime_utc", "file": "src/core/models/state.py", "line": 14}
  ]
}
```

**Response (200):**
```json
{
  "ok": true,
  "fixes_applied": 2,
  "fixes_verified": 2,
  "fixes_failed": 0,
  "files_modified": ["src/core/models/action.py", "src/core/models/state.py"],
  "results": [
    {"file": "src/core/models/action.py", "success": true, "verified": true},
    {"file": "src/core/models/state.py", "success": true, "verified": true}
  ]
}
```

### 3.5 POST /api/compat/assess

**Request:**
```json
{
  "module": "web",
  "target_version": "3.8",
  "direction": "downgrade"
}
```

**Response (200):**
```json
{
  "ok": true,
  "achievable": true,
  "current_floor": "3.11",
  "target": "3.8",
  "gap": "3.11 → 3.8",
  "code_fixes_needed": 15,
  "code_fixes_auto": 14,
  "code_fixes_manual": 1,
  "dep_changes_needed": 0,
  "blocking_modules": ["core"],
  "fix_order": [["core"], ["web"]],
  "estimated_effort": "~15 minutes",
  "recommendation": "Fix module 'core' first (14 auto-fixes + 1 manual), then fix 'web' (1 auto-fix)"
}
```

### 3.6 GET /api/compat/plan/{module}

**Response (200):**
```json
{
  "ok": true,
  "module": "core",
  "target_version": "3.8",
  "direction": "downgrade",
  "steps": [
    {
      "id": "scan:abc123",
      "label": "Scan for incompatible features",
      "type": "analysis",
      "state": "passed",
      "done": true,
      "completed_at": "2026-03-19T12:00:00Z",
      "findings_count": 0
    },
    {
      "id": "fix_utc:def456",
      "label": "Fix datetime.UTC (14 files)",
      "type": "transform",
      "state": "needs_attention",
      "done": false,
      "findings_count": 14,
      "findings_fixable": 14,
      "actions": ["fix_all", "skip"]
    },
    {
      "id": "verify:ghi789",
      "label": "Verify fixes",
      "type": "verification",
      "state": "pending",
      "done": false
    }
  ],
  "progress": {
    "total": 3,
    "passed": 1,
    "failed": 0,
    "needs_attention": 1,
    "pending": 1,
    "blocked": 0,
    "skipped": 0,
    "percent": 33.3
  }
}
```

### 3.7 GET /api/compat/import-graph/{module}

**Response (200):**
```json
{
  "ok": true,
  "module": "web",
  "nodes": [
    {"file": "src/ui/web/routes/backup/archive.py", "module": "web"},
    {"file": "src/core/models/action.py", "module": "core"}
  ],
  "edges": [
    {
      "source": "src/ui/web/routes/backup/archive.py",
      "target": "src/core/models/action.py",
      "import_type": "from_import",
      "names": ["Action"],
      "line": 5,
      "is_cross_module": true
    }
  ],
  "cross_module_deps": ["core"]
}
```

---

## 4. Error Responses

All error responses follow the same format:

```json
{
  "ok": false,
  "error": "Human-readable error message",
  "error_type": "validation_error",
  "details": {}
}
```

| HTTP Status | When |
|------------|------|
| 200 | Success (even if step FAILED — that's a successful execution with a failed result) |
| 400 | Invalid request (missing fields, invalid module name) |
| 404 | Module not found, plan not found |
| 500 | Internal server error |

**Important**: A step that FAILS is still a 200 response. The step executed successfully — it just found that things are broken. HTTP status reflects the API call success, not the step outcome. The `state` field in the response tells you the step outcome.

---

## 5. SSE Event Types

For streaming endpoints (`/batch/execute`):

| Event type | Fields | When |
|-----------|--------|------|
| `batch_start` | `total_steps` | Batch begins |
| `step_start` | `step_index`, `label`, `step_id` | Step begins |
| `step_log` | `step_index`, `line` | Log line during step |
| `step_progress` | `step_index`, `current`, `total` | Progress within step |
| `step_complete` | `step_index`, `state`, `summary`, `duration_ms` | Step finished |
| `batch_stopped` | `stopped_at`, `reason` | Batch stopped early |
| `batch_complete` | `steps_passed`, `steps_failed`, ... | Batch finished |

---

## 6. Authentication & Authorization

For this project, the API runs on localhost (port 8000) and does not require authentication. If deployed externally:
- All `/api/compat/fix/*` and `/api/compat/step/*` routes require write access
- All `/api/compat/analyze/*` and `/api/compat/features/*` routes are read-only
- Plan creation/deletion requires write access

---

## 7. Rate Limiting

No rate limiting for local use. For deployed instances:
- Analysis endpoints: 10 req/min per module (expensive)
- Fix endpoints: 5 req/min per module (modifies files)
- Feature database endpoints: 100 req/min (cheap reads)

---

## 8. Versioning

API is versioned via the URL path. Current version is implicit (v1). If breaking changes are needed:
- `/api/compat/v2/analyze` for v2
- Old routes remain for backward compat

---

## 9. Integration Points

### 9.1 With Web UI (Document 31)
- UI calls all endpoints via fetch()
- SSE streaming for batch execution
- Real-time state updates

### 9.2 With CLI (Document 32)
- CLI calls the same endpoints
- Can also call engine directly (bypass HTTP for local use)

### 9.3 With Engine Internals
- Each route instantiates the appropriate engine component
- Routes are thin wrappers — validation + engine call + response formatting
- No business logic in routes
