# Security Scan Routes — Secret Scanning, Sensitive Files, Posture & Gitignore API

> **3 files · 143 lines · 7 endpoints · Blueprint: `security_bp2` · Prefix: `/api`**
>
> Two sub-domains under a single blueprint:
>
> 1. **Detection (read-only)** — combined status, posture summary,
>    secret scanning, sensitive file detection, gitignore analysis,
>    posture scoring (6 endpoints, 1 cached)
> 2. **Actions (mutation)** — generate .gitignore (1 endpoint)
>
> Backed by `core/services/security/` (1,127 lines across 4 modules):
> - `common.py` (381 lines) — patterns, skip lists, dismiss/undismiss
> - `scan.py` (360 lines) — secret scanning, sensitive files, gitignore
> - `posture.py` (304 lines) — multi-factor security scoring
> - `ops.py` (41 lines) — re-export hub

---

## How It Works

### Combined Security Status Pipeline (Cached)

```
GET /api/security/status?bust=1
     │
     ▼
devops_cache.get_cached(root, "security", _compute)
     │
     ├── Cache HIT → return cached status
     └── Cache MISS → _compute()
         │
         ├── security_ops.scan_secrets(root)
         │   ├── Walk source files (skip _SKIP_DIRS, _SKIP_EXTENSIONS)
         │   ├── Match _SECRET_PATTERNS (regex for API keys, tokens, passwords)
         │   ├── Filter out _has_nosec() lines (# nosec comments)
         │   ├── Filter out dismissed findings
         │   └── Return: { findings: [...], count: 5 }
         │
         ├── security_ops.security_posture(root)
         │   ├── Factor 1: Secret scan findings (0 = good)
         │   ├── Factor 2: Sensitive files exposure
         │   ├── Factor 3: .gitignore coverage
         │   ├── Factor 4: Environment file protection
         │   ├── Factor 5: Dependency audit results
         │   ├── Weighted score calculation → 0-100 scale
         │   └── Return: { score: 85, grade: "B+", factors: [...] }
         │
         └── Return:
             {
                 findings: [...],
                 finding_count: 5,
                 posture: { score: 85, grade: "B+", factors: [...] }
             }
```

### Posture Summary Pipeline (Cache-Only, Never Scans)

```
GET /api/security/posture-summary
     │
     ▼
_load_cache(root)  ← direct cache read, NO computation
     │
     ├── 1. Try "security" cache entry → return if exists
     │
     ├── 2. Fallback: try "audit:l2:risks" cache entry
     │   ├── Extract findings where category in ("secrets", "security")
     │   └── Return subset with posture:{} and _source: "audit:l2:risks"
     │
     └── 3. Nothing cached → { empty: true }

WHY: The DevOps Security card calls this on every tab switch.
     Running a full scan would be too slow. This endpoint only
     reads whatever was cached from a previous /security/status
     or audit scan.
```

### Individual Scan Endpoints

```
GET /api/security/scan
     │
     ▼
security_ops.scan_secrets(root)
     └── Walk files → match secret patterns → return findings

GET /api/security/files
     │
     ▼
security_ops.detect_sensitive_files(root)
     │
     ├── Scan for sensitive file patterns:
     │   ├── .env, .env.*, *.key, *.pem, *.p12
     │   ├── id_rsa, id_ed25519, *.cert
     │   ├── credentials, secrets.yml, vault.*
     │   └── ...
     │
     └── Return:
         { files: [{path, type, gitignored}], count: 3 }

GET /api/security/gitignore
     │
     ▼
security_ops.gitignore_analysis(root, stack_names=["python", "node"])
     │
     ├── Parse existing .gitignore
     ├── Compare against recommended patterns for stacks:
     │   ├── Python → __pycache__/, *.pyc, .venv/, dist/
     │   ├── Node → node_modules/, dist/, .env
     │   └── ...
     │
     └── Return:
         { existing: [...], missing: [...], coverage_percent: 75 }

GET /api/security/posture
     │
     ▼
security_ops.security_posture(root)
     └── Multi-factor score → { score, grade, factors }
```

### Gitignore Generation Pipeline

```
POST /api/security/generate/gitignore
     Body: { stacks: ["python", "node"] }
     │
     ├── @run_tracked("generate", "generate:gitignore")
     │
     ▼
security_ops.generate_gitignore(root, ["python", "node"])
     │
     ├── stacks provided? Use them
     │   stacks omitted? → _get_stack_names() from helpers
     │
     ├── Merge recommended patterns for each stack
     ├── Merge with existing .gitignore (don't duplicate)
     ├── Write updated .gitignore
     │
     └── Return:
         { ok: true, added: ["__pycache__/", "node_modules/"] }
```

---

## File Map

```
routes/security_scan/
├── __init__.py     18 lines — blueprint + 2 sub-module imports
├── detect.py      100 lines — 6 detection endpoints
├── actions.py      25 lines — 1 action endpoint
└── README.md               — this file
```

Core business logic: `core/services/security/` (1,127 lines across 4 modules).

---

## Per-File Documentation

### `__init__.py` — Blueprint Definition (18 lines)

```python
security_bp2 = Blueprint("security2", __name__)

from . import detect, actions  # register routes
```

**Note the `2` suffix** — `security_bp2` / `security2` — to avoid
naming conflicts with other security-related blueprints.

### `detect.py` — Detection Endpoints (100 lines)

| Function | Method | Route | Cached | What It Does |
|----------|--------|-------|--------|-------------|
| `security_status()` | GET | `/security/status` | ✅ `"security"` | Combined scan + posture |
| `security_posture_summary()` | GET | `/security/posture-summary` | Reads cache only | Lightweight summary |
| `security_scan()` | GET | `/security/scan` | No | Scan for hardcoded secrets |
| `security_files()` | GET | `/security/files` | No | Detect sensitive files |
| `security_gitignore()` | GET | `/security/gitignore` | No | Analyze .gitignore coverage |
| `security_posture()` | GET | `/security/posture` | No | Full posture score |

**The posture-summary endpoint is unique in the entire codebase:**

```python
from src.core.services.devops.cache import _load_cache

cache = _load_cache(root)

# 1. Try direct security cache
sec_entry = cache.get("security")
if sec_entry and "data" in sec_entry:
    return jsonify(sec_entry["data"])

# 2. Fallback: extract from audit risks cache
risks_entry = cache.get("audit:l2:risks")
# ...filter to security-category findings...

return jsonify({"empty": True})
```

It's the only endpoint that:
1. **Directly reads** the raw cache via `_load_cache()` (private API)
2. **Falls back** to a different cache key (`audit:l2:risks`)
3. **Never triggers** computation — pure cache read

### `actions.py` — Generation Endpoint (25 lines)

| Function | Method | Route | Tracked | What It Does |
|----------|--------|-------|---------|-------------|
| `security_generate_gitignore()` | POST | `/security/generate/gitignore` | ✅ `generate:gitignore` | Generate .gitignore |

**Stack source fallback:**

```python
stack_names = data.get("stacks") or _get_stack_names()
# Request body overrides auto-detected stacks
```

---

## Dependency Graph

```
__init__.py
└── Imports: detect, actions

detect.py
├── security.ops  ← scan_secrets, detect_sensitive_files,
│                   gitignore_analysis, security_posture (eager)
├── helpers       ← project_root, get_stack_names (eager)
├── devops.cache  ← get_cached (lazy), _load_cache (lazy) (inside handlers)
└── devops.cache  ← _load_cache (private API, posture-summary only)

actions.py
├── security.ops  ← generate_gitignore (eager)
├── run_tracker   ← @run_tracked (eager)
└── helpers       ← project_root, get_stack_names (eager)
```

---

## Consumers

| Layer | Module | What It Uses |
|-------|--------|-------------|
| Server | `ui/web/server.py` | Imports `security_bp2`, registers at `/api` |
| DevOps card | `scripts/devops/_security.html` | `/security/posture-summary` (lightweight) |
| Git setup | `scripts/integrations/_git.html` | `/security/gitignore`, `/security/generate/gitignore` |
| Git int setup | `scripts/integrations/setup/_git.html` | `/security/gitignore` |

---

## Data Shapes

### `GET /api/security/status` response

```json
{
    "findings": [
        {
            "file": "src/config.py",
            "line": 42,
            "pattern": "API key",
            "match": "AKIAIOSFODNN7EXAMPLE",
            "severity": "high"
        }
    ],
    "finding_count": 1,
    "posture": {
        "score": 85,
        "grade": "B+",
        "factors": [
            { "name": "secret_scan", "score": 90, "weight": 0.3, "detail": "1 finding" },
            { "name": "sensitive_files", "score": 100, "weight": 0.2, "detail": "None exposed" },
            { "name": "gitignore", "score": 75, "weight": 0.2, "detail": "Missing 3 patterns" },
            { "name": "env_protection", "score": 80, "weight": 0.15, "detail": ".env gitignored" },
            { "name": "dep_audit", "score": 90, "weight": 0.15, "detail": "1 vuln" }
        ]
    }
}
```

### `GET /api/security/posture-summary` response

```json
// From security cache:
{ "findings": [...], "finding_count": 1, "posture": {...} }

// From audit cache fallback:
{ "findings": [...], "finding_count": 2, "posture": {}, "_source": "audit:l2:risks" }

// Nothing cached:
{ "empty": true }
```

### `GET /api/security/files` response

```json
{
    "files": [
        { "path": ".env", "type": "environment", "gitignored": true },
        { "path": "certs/server.key", "type": "private_key", "gitignored": false }
    ],
    "count": 2
}
```

### `GET /api/security/gitignore` response

```json
{
    "existing": ["node_modules/", "*.pyc", "__pycache__/"],
    "missing": [".venv/", "dist/", ".env.local"],
    "coverage_percent": 75
}
```

### `GET /api/security/posture` response

```json
{
    "score": 85,
    "grade": "B+",
    "factors": [
        { "name": "secret_scan", "score": 90, "weight": 0.3, "detail": "1 finding" },
        { "name": "sensitive_files", "score": 100, "weight": 0.2 },
        { "name": "gitignore", "score": 75, "weight": 0.2 },
        { "name": "env_protection", "score": 80, "weight": 0.15 },
        { "name": "dep_audit", "score": 90, "weight": 0.15 }
    ]
}
```

### `POST /api/security/generate/gitignore` response

```json
{
    "ok": true,
    "added": ["__pycache__/", ".venv/", "dist/", "*.egg-info/"]
}
```

---

## Advanced Feature Showcase

### 1. Multi-Source Posture Summary

The posture-summary endpoint is the only endpoint that reads from
two different cache keys (`security` and `audit:l2:risks`). This
lets the DevOps Security card show meaningful data even if the
user hasn't run a dedicated security scan — audit data can fill in.

### 2. # nosec Comment Support

Secret scan findings can be suppressed inline:

```python
API_KEY = "AKIAIOSFODNN7EXAMPLE"  # nosec
```

The scanner checks `_has_nosec()` and excludes suppressed lines.

### 3. Multi-Factor Posture Scoring

Security posture is calculated from 5 weighted factors:
- Secret scan (30%) — are there hardcoded secrets?
- Sensitive files (20%) — are private keys exposed?
- Gitignore coverage (20%) — does .gitignore cover recommended patterns?
- Env protection (15%) — are .env files gitignored?
- Dependency audit (15%) — are there known vulnerabilities?

### 4. Stack-Aware Gitignore Generation

The `.gitignore` generator knows the right patterns for each stack:

```python
# Python → __pycache__/, *.pyc, .venv/, dist/, *.egg-info/
# Node → node_modules/, dist/, .env, .env.local
# Go → vendor/, *.exe
# Rust → target/, *.rs.bk
```

---

## Design Decisions

### Why the blueprint is named security_bp2

The `2` suffix avoids naming conflict with the earlier `security`
blueprint name. The package is `security_scan` but the blueprint
registers under the `security2` namespace in Flask.

### Why posture-summary uses private cache API

The `_load_cache()` function is a private API, but this endpoint
needs to read the cache without triggering computation. Using
`get_cached()` would require a compute function, which would
trigger a scan — defeating the purpose.

### Why /security/status combines scan + posture

The cached status endpoint runs both scan and posture together so
the DevOps card gets everything in one call. The individual
endpoints (`/scan`, `/posture`) exist for targeted access outside
the cache.

---

## Coverage Summary

| Capability | Endpoint | Method | Tracked | Cached |
|-----------|----------|--------|---------|--------|
| Combined status | `/security/status` | GET | No | ✅ `"security"` |
| Posture summary | `/security/posture-summary` | GET | No | Reads cache only |
| Secret scan | `/security/scan` | GET | No | No |
| Sensitive files | `/security/files` | GET | No | No |
| Gitignore analysis | `/security/gitignore` | GET | No | No |
| Posture score | `/security/posture` | GET | No | No |
| Generate gitignore | `/security/generate/gitignore` | POST | ✅ `generate:gitignore` | No |
