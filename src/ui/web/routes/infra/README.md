# Infra Routes — Environment (.env) Management & IaC Detection API

> **3 files · 134 lines · 9 endpoints · Blueprint: `infra_bp` · Prefix: `/api`**
>
> Two sub-domains under a single blueprint:
>
> 1. **Environment (.env)** — detect .env files, list variables (with
>    optional redaction), diff two .env files (missing/extra keys),
>    validate for common issues (placeholders, duplicates, unquoted
>    spaces), and generate .env.example ↔ .env bidirectionally.
>
> 2. **Infrastructure as Code (IaC)** — detect IaC providers (Terraform,
>    Kubernetes, Pulumi, Ansible, etc.) via DataRegistry patterns,
>    inventory IaC resources (Terraform resource blocks, Kubernetes
>    manifests), and aggregate dashboard card data (vault state, GitHub
>    secret sync, per-environment status).
>
> Routes delegate to `core/services/env/ops.py` (393 lines) and
> `core/services/env/infra_ops.py` (288 lines).

---

## How It Works

### Request Flow

```
Frontend
│
├── devops/_env.html ──────────── Environment dashboard card
│   ├── GET  /api/env/card-status   (cached aggregation)
│   ├── GET  /api/infra/status      (combined env + IaC)
│   ├── GET  /api/infra/env/status  (env file inventory)
│   ├── GET  /api/infra/env/vars    (list vars)
│   ├── GET  /api/infra/env/diff    (compare .env files)
│   ├── GET  /api/infra/env/validate (lint .env)
│   ├── POST /api/infra/env/generate-example  (→ .env.example)
│   ├── POST /api/infra/env/generate-env      (→ .env)
│   ├── GET  /api/infra/iac/status  (IaC detection)
│   └── GET  /api/infra/iac/resources (IaC inventory)
│
     ▼
routes/infra/                         ← HTTP layer (this package)
├── __init__.py  — blueprint definition
├── env.py       — environment endpoints (7 routes)
└── iac.py       — IaC + card endpoints (3 routes)
     │
     ▼
core/services/env/                    ← Business logic
├── ops.py (393 lines)
│   ├── _env_files()             — file variants from DataRegistry
│   ├── _parse_env_file()        — KEY=value parser
│   ├── _redact_value()          — sensitive value masking
│   ├── env_status()             — detect .env files
│   ├── env_vars()               — list variables (redactable)
│   ├── env_diff()               — compare two files
│   ├── env_validate()           — lint for issues
│   ├── generate_env_example()   — .env → .env.example
│   └── generate_env_from_example() — .env.example → .env
│
└── infra_ops.py (288 lines)
    ├── _iac_providers()         — IaC catalog from DataRegistry
    ├── iac_status()             — detect IaC providers
    ├── iac_resources()          — inventory resources
    ├── infra_status()           — combined env + IaC
    └── env_card_status()        — full dashboard aggregation
```

### Environment Detection Pipeline

```
GET /api/infra/env/status
     │
     ▼
env_ops.env_status(root)
     │
     ├── For each env file variant (from DataRegistry):
     │   .env, .env.example, .env.sample, .env.template,
     │   .env.local, .env.production, .env.staging, etc.
     │   │
     │   ├── File exists?
     │   │   └── YES → parse with _parse_env_file()
     │   │       ├── Handle: KEY=value
     │   │       ├── Handle: KEY="value" (quoted)
     │   │       ├── Handle: KEY='value' (single-quoted)
     │   │       ├── Handle: export KEY=value
     │   │       ├── Skip: comments (#) and empty lines
     │   │       └── Count variables
     │   │
     │   └── NO → skip
     │
     └── Return:
         {
             files: [{name, exists: true, var_count}, ...],
             has_env: bool,       ← .env exists
             has_example: bool,   ← .env.example|sample|template exists
             total_vars: int,     ← sum of all file var counts
         }
```

### Variable Listing Pipeline (with Redaction)

```
GET /api/infra/env/vars?file=.env&redact=true
     │
     ▼
env_ops.env_vars(root, file=".env", redact=True)
     │
     ├── Parse .env file → {KEY: value, ...}
     │
     ├── If redact=true:
     │   _redact_value(value) for each value
     │   Short values (≤4 chars): "****"
     │   Longer values: first 2 chars + "****" + last 2 chars
     │   Example: "sk_live_abc123xyz" → "sk****yz"
     │
     └── Return:
         { ok: true, file: ".env", variables: {...}, count: N }
```

### Env Diff Pipeline

```
GET /api/infra/env/diff?source=.env.example&target=.env
     │
     ▼
env_ops.env_diff(root, source=".env.example", target=".env")
     │
     ├── Parse source (.env.example) → set of keys
     ├── Parse target (.env)         → set of keys
     │
     ├── missing = source_keys - target_keys
     │   (keys in example but not in .env → need to add)
     │
     ├── extra = target_keys - source_keys
     │   (keys in .env but not in example → undocumented)
     │
     ├── common = source_keys ∩ target_keys
     │   (keys in both → in sync)
     │
     └── in_sync = (missing empty AND extra empty)
```

### Env Validation Pipeline

```
GET /api/infra/env/validate?file=.env
     │
     ▼
env_ops.env_validate(root, file=".env")
     │
     ├── Read file lines
     │
     ├── For each non-comment, non-empty line:
     │   ├── No '=' found → warning
     │   │
     │   ├── Duplicate key check:
     │   │   Track seen_keys → "Duplicate key 'X' (first at line N)"
     │   │
     │   ├── Empty value check:
     │   │   KEY= → info: "Empty value for 'KEY'"
     │   │
     │   ├── Placeholder detection:
     │   │   Patterns: your_, changeme, xxx, todo, fixme,
     │   │   replace, example, placeholder, <, >
     │   │   → warning: "Possible placeholder value for 'KEY'"
     │   │
     │   └── Unquoted spaces:
     │       KEY=hello world (no quotes) → warning
     │
     └── valid = no warnings (info-only issues are OK)
```

### IaC Detection Pipeline

```
GET /api/infra/iac/status
     │
     ▼
infra_ops.iac_status(root)
     │
     ├── Load IaC provider catalog from DataRegistry:
     │   _iac_providers() → {terraform, kubernetes, pulumi, ansible, ...}
     │
     ├── For each provider spec:
     │   ├── Check files (glob patterns):
     │   │   terraform: *.tf, terraform.tfvars, terraform.tfstate
     │   │   kubernetes: *.yaml in k8s/, manifests/, etc.
     │   │
     │   ├── Check marker files:
     │   │   terraform: .terraform.lock.hcl
     │   │   pulumi: Pulumi.yaml
     │   │
     │   ├── Check directories:
     │   │   kubernetes: k8s/, kubernetes/, manifests/, deploy/
     │   │   Also scan for *.yml, *.yaml, *.tf, *.json inside
     │   │
     │   ├── Check CLI availability:
     │   │   shutil.which("terraform"), shutil.which("kubectl"), etc.
     │   │
     │   └── Only include if files_found or dirs_found
     │
     └── Return:
         { providers: [{id, name, cli, cli_available,
                        files_found, dirs_found}, ...],
           has_iac: bool }
```

### IaC Resource Inventory Pipeline

```
GET /api/infra/iac/resources
     │
     ▼
infra_ops.iac_resources(root)
     │
     ├── Terraform (.tf files):
     │   ├── Glob: **/*.tf (skip .terraform/)
     │   ├── Regex: resource "type" "name"
     │   │   resource "aws_s3_bucket" "my_bucket"
     │   │   → { provider: "terraform", type: "aws_s3_bucket",
     │   │       name: "my_bucket", file: "main.tf" }
     │   └── Cap: no limit (bounded by file count)
     │
     ├── Kubernetes (YAML manifests):
     │   ├── Directories: k8s/, kubernetes/, manifests/, deploy/
     │   ├── Glob: **/*.y*ml
     │   ├── Parse: yaml.safe_load_all (multi-document)
     │   │   kind: Deployment, name: my-app
     │   │   → { provider: "kubernetes", type: "Deployment",
     │   │       name: "my-app", file: "k8s/deployment.yaml" }
     │   └── Handle: malformed docs gracefully (continue)
     │
     └── Return:
         { resources: [...], count: N }
```

### Dashboard Card Aggregation Pipeline

```
GET /api/env/card-status?bust=1
     │
     ▼
devops_cache.get_cached(root, "env", lambda: env_card_status(root), force=force)
     │
     ├── Cache HIT → return cached card data
     └── Cache MISS → env_card_status(root)
         │
         ├── 1. Load project environments:
         │   project.yml → [{name: "dev", default: true}, {name: "prod"}, ...]
         │
         ├── 2. Detect active environment:
         │   vault_env_ops.read_active_env(root)
         │
         ├── 3. Fetch GitHub environments:
         │   secrets_ops.list_environments(root) → ["dev", "staging", "prod"]
         │
         ├── 4. Per-env GitHub secrets (if GitHub available):
         │   For each env: secrets_ops.list_gh_secrets(root, env_name)
         │   → { secrets: [...], variables: [...] }
         │
         ├── 5. Per-env local state:
         │   For each env:
         │   ├── Vault state:
         │   │   .env exists        → "unlocked"
         │   │   .env.vault exists  → "locked"
         │   │   neither            → "empty"
         │   │
         │   ├── Local key count:
         │   │   vault_io.list_env_keys(.env) → count
         │   │
         │   └── Sync analysis (if GitHub):
         │       local_only = local_keys - gh_keys
         │       gh_only    = gh_keys - local_keys
         │       in_sync    = (both empty)
         │
         └── 6. .env file inventory:
             env_status(root) → files, has_env, total_vars
```

---

## File Map

```
routes/infra/
├── __init__.py     18 lines — blueprint definition + sub-module imports
├── env.py          80 lines — 7 environment endpoints
├── iac.py          36 lines — 3 IaC + card endpoints
└── README.md                — this file
```

Core business logic resides in:
- `core/services/env/ops.py` (393 lines) — env file operations
- `core/services/env/infra_ops.py` (288 lines) — IaC detection + card aggregation

---

## Per-File Documentation

### `__init__.py` — Blueprint Definition (18 lines)

```python
infra_bp = Blueprint("infra", __name__)

from . import env, iac  # register routes
```

### `env.py` — Environment Endpoints (80 lines)

| Function | Method | Route | Tracked | What It Does |
|----------|--------|-------|---------|-------------|
| `infra_status()` | GET | `/infra/status` | No | Combined env + IaC status |
| `env_status()` | GET | `/infra/env/status` | No | .env file inventory |
| `env_vars()` | GET | `/infra/env/vars` | No | List variables (redactable) |
| `env_diff()` | GET | `/infra/env/diff` | No | Compare two .env files |
| `env_validate()` | GET | `/infra/env/validate` | No | Lint .env for issues |
| `env_generate_example()` | POST | `/infra/env/generate-example` | ✅ generate | .env → .env.example |
| `env_generate_env()` | POST | `/infra/env/generate-env` | ✅ generate | .env.example → .env |

**Query parameter handling:**

```python
# env_vars — file selection + redaction toggle
file = request.args.get("file", ".env")
redact = request.args.get("redact", "true").lower() != "false"

# env_diff — source/target selection
source = request.args.get("source", ".env.example")
target = request.args.get("target", ".env")

# env_validate — file selection
file = request.args.get("file", ".env")
```

**Error handling pattern:**

All observation endpoints check for `"error"` in the result and
return 404 when the requested file doesn't exist:

```python
result = env_ops.env_vars(_project_root(), file=file, redact=redact)
if "error" in result:
    return jsonify(result), 404
return jsonify(result)
```

Generation endpoints return 400 on error instead:

```python
result = env_ops.generate_env_example(_project_root())
if "error" in result:
    return jsonify(result), 400
return jsonify(result)
```

### `iac.py` — IaC + Card Endpoints (36 lines)

| Function | Method | Route | Cached | What It Does |
|----------|--------|-------|--------|-------------|
| `iac_status()` | GET | `/infra/iac/status` | No | IaC provider detection |
| `iac_resources()` | GET | `/infra/iac/resources` | No | Resource inventory |
| `env_card_status()` | GET | `/env/card-status` | ✅ "env" | Dashboard aggregation |

**Note the route prefix difference:** `env_card_status` uses
`/env/card-status` (not `/infra/env/...`). This is because the
dashboard card endpoint predates the `/infra/` reorganization
and the route is kept for backward compatibility.

**Card status with caching:**

```python
@infra_bp.route("/env/card-status")
def env_card_status():
    from src.core.services.devops.cache import get_cached

    root = _project_root()
    force = request.args.get("bust", "") == "1"
    return jsonify(get_cached(
        root, "env",
        lambda: env_ops.env_card_status(root),
        force=force,
    ))
```

---

## Dependency Graph

```
__init__.py
└── Imports: env, iac

env.py
├── env.ops           ← env_status, env_vars, env_diff, env_validate,
│                       generate_env_example, generate_env_from_example,
│                       infra_status (eager)
├── run_tracker       ← @run_tracked decorator
└── helpers           ← project_root

iac.py
├── env.ops           ← iac_status, iac_resources (eager, via re-export)
├── devops.cache      ← get_cached (lazy, inside handler)
└── helpers           ← project_root
```

**Core service internals:**

```
env/ops.py (393 lines)
├── _env_files()              — DataRegistry file list
├── _parse_env_file()         — KEY=value parser (handles quoting, export)
├── _redact_value()           — first2 + **** + last2
├── env_status()              — detect files (line 98-135)
├── env_vars()                — list variables (line 141-163)
├── env_diff()                — compare files (line 166-207)
├── env_validate()            — lint checks (line 210-296)
├── generate_env_example()    — .env → .env.example (line 302-345)
├── generate_env_from_example() — .env.example → .env (line 348-379)
└── Re-exports from infra_ops: iac_status, iac_resources,
    infra_status, env_card_status

env/infra_ops.py (288 lines)
├── _iac_providers()          — DataRegistry IaC catalog
├── iac_status()              — provider detection (line 34-89)
├── iac_resources()           — TF + K8s parsing (line 92-143)
├── infra_status()            — combined status (line 149-159)
└── env_card_status()         — dashboard aggregation (line 165-287)
    ├── config.loader         ← load_project, find_project_file
    ├── secrets_ops           ← list_environments, list_gh_secrets
    ├── vault_env_ops         ← read_active_env
    └── vault_io              ← list_env_keys
```

---

## Consumers

| Layer | Module | What It Uses |
|-------|--------|-------------|
| Server | `ui/web/server.py` | Imports `infra_bp`, registers at `/api` prefix |
| Dashboard | `scripts/devops/_env.html` | `/env/card-status` (environment card) |
| Dashboard | `scripts/devops/_env.html` | `/infra/env/*` (detail views) |
| Cache | `devops/cache` compute registry | `"env"` key → `env_card_status(root)` |

---

## Data Shapes

### `GET /api/infra/env/status` response

```json
{
    "files": [
        { "name": ".env", "exists": true, "var_count": 12 },
        { "name": ".env.example", "exists": true, "var_count": 12 },
        { "name": ".env.production", "exists": true, "var_count": 8 }
    ],
    "has_env": true,
    "has_example": true,
    "total_vars": 32
}
```

### `GET /api/infra/env/vars?file=.env&redact=true` response

```json
{
    "ok": true,
    "file": ".env",
    "variables": {
        "DATABASE_URL": "po****ql",
        "SECRET_KEY": "ab****yz",
        "DEBUG": "true",
        "PORT": "****"
    },
    "count": 4
}
```

### `GET /api/infra/env/vars?file=.env&redact=false` response

```json
{
    "ok": true,
    "file": ".env",
    "variables": {
        "DATABASE_URL": "postgresql://user:pass@localhost:5432/db",
        "SECRET_KEY": "abc123def456xyz",
        "DEBUG": "true",
        "PORT": "8080"
    },
    "count": 4
}
```

### `GET /api/infra/env/vars?file=missing.env` error response

```json
{ "error": "File not found: missing.env" }
```

Status code: **404**

### `GET /api/infra/env/diff` response (in sync)

```json
{
    "ok": true,
    "source": ".env.example",
    "target": ".env",
    "missing": [],
    "extra": [],
    "common": ["DATABASE_URL", "DEBUG", "PORT", "SECRET_KEY"],
    "in_sync": true
}
```

### `GET /api/infra/env/diff` response (out of sync)

```json
{
    "ok": true,
    "source": ".env.example",
    "target": ".env",
    "missing": ["NEW_FEATURE_FLAG", "SMTP_HOST"],
    "extra": ["OLD_DEPRECATED_VAR"],
    "common": ["DATABASE_URL", "SECRET_KEY"],
    "in_sync": false
}
```

### `GET /api/infra/env/validate` response (clean)

```json
{
    "ok": true,
    "file": ".env",
    "issues": [],
    "issue_count": 0,
    "valid": true
}
```

### `GET /api/infra/env/validate` response (with issues)

```json
{
    "ok": true,
    "file": ".env",
    "issues": [
        {
            "line": 3,
            "severity": "info",
            "message": "Empty value for 'NEW_VAR'"
        },
        {
            "line": 7,
            "severity": "warning",
            "message": "Duplicate key 'SECRET_KEY' (first at line 2)"
        },
        {
            "line": 12,
            "severity": "warning",
            "message": "Possible placeholder value for 'API_KEY'"
        },
        {
            "line": 15,
            "severity": "warning",
            "message": "Unquoted value with spaces for 'APP_NAME'"
        }
    ],
    "issue_count": 4,
    "valid": false
}
```

### `POST /api/infra/env/generate-example` response

```json
{
    "ok": true,
    "file": {
        "path": ".env.example",
        "content": "# Environment variables\n# Copy to .env and fill in values\n#\n# Generated from .env (4 variables)\n\n# ── DATABASE ──\nDATABASE_URL=\n\n# ── SECRET ──\nSECRET_KEY=\n\nDEBUG=\nPORT=\n",
        "overwrite": false,
        "reason": "Generated .env.example from .env (4 variables)"
    }
}
```

### `POST /api/infra/env/generate-env` response

```json
{
    "ok": true,
    "file": {
        "path": ".env",
        "content": "# Copy of .env.example — fill in your values\nDATABASE_URL=\nSECRET_KEY=\nDEBUG=\nPORT=\n",
        "overwrite": false,
        "reason": "Generated .env from .env.example"
    }
}
```

### `GET /api/infra/status` response

```json
{
    "env": {
        "files": [
            { "name": ".env", "exists": true, "var_count": 12 }
        ],
        "has_env": true,
        "has_example": false,
        "total_vars": 12
    },
    "iac": {
        "providers": [
            {
                "id": "terraform",
                "name": "Terraform",
                "cli": "terraform",
                "cli_available": true,
                "files_found": ["main.tf", "variables.tf"],
                "dirs_found": []
            }
        ],
        "has_iac": true
    }
}
```

### `GET /api/infra/iac/status` response

```json
{
    "providers": [
        {
            "id": "terraform",
            "name": "Terraform",
            "cli": "terraform",
            "cli_available": true,
            "files_found": ["main.tf", "variables.tf", "outputs.tf"],
            "dirs_found": []
        },
        {
            "id": "kubernetes",
            "name": "Kubernetes",
            "cli": "kubectl",
            "cli_available": true,
            "files_found": ["k8s/deployment.yaml", "k8s/service.yaml"],
            "dirs_found": ["k8s"]
        }
    ],
    "has_iac": true
}
```

### `GET /api/infra/iac/resources` response

```json
{
    "resources": [
        {
            "provider": "terraform",
            "type": "aws_s3_bucket",
            "name": "static_assets",
            "file": "storage.tf"
        },
        {
            "provider": "terraform",
            "type": "aws_iam_role",
            "name": "lambda_exec",
            "file": "iam.tf"
        },
        {
            "provider": "kubernetes",
            "type": "Deployment",
            "name": "web-app",
            "file": "k8s/deployment.yaml"
        },
        {
            "provider": "kubernetes",
            "type": "Service",
            "name": "web-app",
            "file": "k8s/service.yaml"
        }
    ],
    "count": 4
}
```

### `GET /api/env/card-status` response

```json
{
    "environments": [
        {
            "name": "dev",
            "default": true,
            "active": true,
            "vault_state": "unlocked",
            "local_keys": 12,
            "gh_secrets": 8,
            "gh_variables": 3,
            "local_only": ["NEW_LOCAL_VAR"],
            "gh_only": ["GH_ONLY_SECRET"],
            "in_sync": false,
            "on_github": true
        },
        {
            "name": "prod",
            "default": false,
            "active": false,
            "vault_state": "locked",
            "local_keys": 15,
            "gh_secrets": 15,
            "gh_variables": 5,
            "local_only": [],
            "gh_only": [],
            "in_sync": true,
            "on_github": true
        }
    ],
    "active": "dev",
    "github": {
        "available": true,
        "reason": null
    },
    "env_files": [
        { "name": ".env", "exists": true, "var_count": 12 }
    ],
    "has_env": true,
    "total_vars": 12
}
```

---

## Advanced Feature Showcase

### 1. Value Redaction

Sensitive values are redacted by default when listing variables:

```python
def _redact_value(value: str) -> str:
    if len(value) <= 4:
        return "****"
    return value[:2] + "****" + value[-2:]

# "sk_live_abc123xyz" → "sk****yz"
# "true"              → "****"
```

The frontend can toggle redaction off with `?redact=false` for
trusted environments or debugging.

### 2. .env File Format Parser

The parser handles multiple .env conventions:

```python
def _parse_env_file(path: Path) -> dict:
    # KEY=value
    # KEY="value"    (double-quoted, strips quotes)
    # KEY='value'    (single-quoted, strips quotes)
    # export KEY=value  (handles export prefix)
    # # comment line    (skipped)
    # empty line        (skipped)
```

### 3. Env Diff for Sync Detection

The diff endpoint reveals configuration drift between `.env.example`
(version-controlled) and `.env` (local):

```python
missing = sorted(source_vars - target_vars)  # need to add
extra = sorted(target_vars - source_vars)    # undocumented
common = sorted(source_vars & target_vars)   # in sync
in_sync = len(missing) == 0 and len(extra) == 0
```

### 4. Validation with Severity Levels

Issues are classified as `info` or `warning`:

```python
# info: non-critical, won't affect valid flag
{"severity": "info", "message": "Empty value for 'NEW_VAR'"}

# warning: indicates a real problem, makes valid=false
{"severity": "warning", "message": "Duplicate key 'X' (first at line 3)"}

# valid is only false when warnings exist
valid = len([i for i in issues if i["severity"] == "warning"]) == 0
```

### 5. Prefix-Grouped Example Generation

When generating `.env.example`, variables are grouped by their
prefix for readability:

```python
current_prefix = ""
for key in sorted(parsed.keys()):
    prefix = key.split("_")[0] if "_" in key else ""
    if prefix != current_prefix and prefix:
        lines.append(f"\n# ── {prefix} ──")
        current_prefix = prefix
    lines.append(f"{key}=")
```

This produces:

```
# ── DATABASE ──
DATABASE_HOST=
DATABASE_NAME=
DATABASE_PORT=

# ── REDIS ──
REDIS_HOST=
REDIS_PORT=
```

### 6. Multi-Source Example Detection

The generate-env endpoint checks multiple example file names:

```python
for name in (".env.example", ".env.sample", ".env.template"):
    p = project_root / name
    if p.is_file():
        example_path = p
        break
```

This accommodates different project conventions (Rails uses
`.env.sample`, Django tutorials use `.env.template`, most
Node.js projects use `.env.example`).

### 7. Dashboard Card Aggregation

The card endpoint combines data from 5 different services in a
single cached call:

```python
# 5 data sources in one call:
config.loader       → project environments
vault_env_ops       → active environment
secrets_ops         → GitHub environments + secrets
vault_io            → local key counts
env_ops.env_status  → .env file inventory
```

---

## Design Decisions

### Why env and IaC share a blueprint

Both deal with infrastructure configuration. The environment
variables (.env) and IaC configs (Terraform, Kubernetes) are
often managed together — a Terraform deployment needs env vars,
a Kubernetes deployment needs secrets. Grouping them under
`infra_bp` reflects this domain relationship.

### Why card-status is cached but individual endpoints are not

- **`/env/card-status`** combines 5 data sources (project config,
  vault state, GitHub secrets, local keys, .env files). This is
  expensive and changes infrequently. Cache key: `"env"`.
- **Individual endpoints** (`/infra/env/vars`, `/infra/env/diff`)
  are used for user-initiated inspection. Stale data would be
  confusing when the user just edited their `.env` file.

### Why redaction is on by default

Environment variables frequently contain secrets (API keys,
database passwords, tokens). Defaulting to redacted display
prevents accidental exposure. The `?redact=false` escape
hatch exists for debugging but requires explicit opt-in.

### Why generate uses overwrite=false

Both `.env.example` and `.env` generators set `overwrite=false`:

```python
GeneratedFile(path=".env.example", overwrite=False, ...)
```

The frontend must check if the file exists and confirm with the
user before writing. This prevents silent overwrite of customized
files.

### Why IaC resource parsing is regex-based

Terraform HCL files are parsed with a simple regex:

```python
re.finditer(r'resource "([^"]+)" "([^"]+)"', content)
```

A full HCL parser (python-hcl2) would be more accurate but adds
a heavy dependency for a detection feature. The regex handles
99% of real-world Terraform files correctly.

### Why the /env/card-status route prefix differs

The card endpoint uses `/env/card-status` (not `/infra/env/card-status`)
because it was created before the `/infra/` reorganization. Changing
it would break the dashboard polling logic. The blueprint routing
handles both `/infra/*` and `/env/*` paths via the same `infra_bp`.

---

## Coverage Summary

| Capability | Endpoint | Method | Tracked | Cached |
|-----------|----------|--------|---------|--------|
| Combined status | `/infra/status` | GET | No | No |
| Env file inventory | `/infra/env/status` | GET | No | No |
| Variable listing | `/infra/env/vars` | GET | No | No |
| File diff | `/infra/env/diff` | GET | No | No |
| File validation | `/infra/env/validate` | GET | No | No |
| Generate example | `/infra/env/generate-example` | POST | ✅ generate | No |
| Generate env | `/infra/env/generate-env` | POST | ✅ generate | No |
| IaC detection | `/infra/iac/status` | GET | No | No |
| IaC resources | `/infra/iac/resources` | GET | No | No |
| Dashboard card | `/env/card-status` | GET | No | ✅ "env" |
