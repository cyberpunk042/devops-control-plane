# Secrets Routes — GitHub Secrets/Variables, Key Generation & Environment Management API

> **3 files · 210 lines · 10 endpoints · Blueprint: `secrets_bp` · Prefix: `/api`**
>
> Two sub-domains under a single blueprint:
>
> 1. **Status (read-only)** — GitHub CLI status, auto-detect repo/token,
>    list deployment environments, list secrets and variables (4 endpoints)
> 2. **Actions (mutations)** — generate keys, set/remove secrets, bulk
>    push, create environments, cleanup, seed multi-env (6 endpoints)
>
> Backed by `core/services/secrets/` (937 lines across 3 modules):
> - `ops.py` (255 lines) — classification, gh CLI, key generation
> - `gh_ops.py` (441 lines) — GitHub secrets/variables CRUD
> - `env_ops.py` (204 lines) — environment lifecycle management

---

## How It Works

### GitHub Status Pipeline

```
GET /api/gh/status
     │
     ▼
secrets_ops.gh_status()
     │
     ├── shutil.which("gh") → installed?
     ├── gh auth status → authenticated?
     ├── gh api user → logged in user
     │
     └── Return:
         { installed: true, authenticated: true, user: "octocat" }

GET /api/gh/auto
     │
     ▼
secrets_ops.gh_auto_detect(root)
     │
     ├── gh auth token → extract token
     ├── git remote get-url origin → extract owner/repo
     │
     └── Return:
         { token: "ghp_...", repo: "owner/repo", ok: true }
```

### Environments & Secrets Listing

```
GET /api/gh/environments
     │
     ▼
secrets_ops.list_environments(root)
     │
     └── gh api /repos/{owner}/{repo}/environments
         → { ok: true, environments: ["production", "staging", "dev"] }

GET /api/gh/secrets?env=production
     │
     ▼
secrets_ops.list_gh_secrets(root, env_name="production")
     │
     ├── Scope depends on env_name:
     │   ├── env=""     → repo-level secrets + variables
     │   └── env="prod" → environment-scoped secrets + variables
     │
     ├── gh secret list → secret names (values are never returned)
     ├── gh variable list → variable names + values
     │
     └── Return:
         { ok: true,
           secrets: ["DATABASE_URL", "API_KEY"],
           variables: [{ name: "NODE_ENV", value: "production" }] }
```

### Key Generation Pipeline

```
POST /api/keys/generate  { type: "password", length: 32 }
     │
     ▼
secrets_ops.generate_key(gen_type="password", length=32)
     │
     ├── type="password" → secrets.token_urlsafe(length)
     ├── type="token"    → secrets.token_hex(length)
     ├── type="uuid"     → uuid.uuid4()
     ├── type="ssh"      → ssh-keygen -t ed25519
     ├── type="cert"     → openssl req -x509 (self-signed)
     │
     └── Return:
         { ok: true, type: "password", value: "aB3x..." }
         or (SSH): { ok: true, type: "ssh", private_key: "...", public_key: "..." }
         or (cert): { ok: true, type: "cert", cert: "...", key: "..." }
```

### Secret Set/Remove Pipeline

```
POST /api/secret/set  { name: "API_KEY", value: "abc123", target: "both" }
     │
     ▼
secrets_ops.set_secret(root, "API_KEY", "abc123", target="both", env_name="")
     │
     ├── target = "both" | "github" | "local"
     │
     ├── target includes "local" or "both"?
     │   └── Write to .env file (or .env.{env_name})
     │
     ├── target includes "github" or "both"?
     │   └── gh secret set API_KEY -b "abc123"
     │       (or --env production if env_name set)
     │
     └── Return: { ok: true, targets: ["local", "github"] }

POST /api/secret/remove  { name: "API_KEY", target: "both", kind: "secret" }
     │
     ▼
secrets_ops.remove_secret(root, "API_KEY", target="both", kind="secret", env_name="")
     │
     ├── kind = "secret" | "variable"
     │
     ├── Local? → Remove from .env file
     ├── GitHub secret? → gh secret delete API_KEY
     ├── GitHub variable? → gh variable delete API_KEY
     │
     └── Return: { ok: true }
```

### Bulk Push Pipeline

```
POST /api/secrets/push
     Body: {
         secrets: { "API_KEY": "abc", "DB_URL": "..." },
         variables: { "NODE_ENV": "production" },
         env_values: { "PORT": "3000" },
         deletions: ["OLD_KEY"],
         sync_keys: ["API_KEY", "DB_URL"],
         push_to_github: true,
         save_to_env: true,
         exclude_from_github: ["LOCAL_ONLY_KEY"]
     }
     │
     ▼
secrets_ops.push_secrets(root, ...)
     │
     ├── 1. Process deletions:
     │   └── For each key in deletions → gh secret delete / gh variable delete
     │
     ├── 2. Push secrets to GitHub:
     │   └── For each in secrets_dict → gh secret set (unless excluded)
     │
     ├── 3. Push variables to GitHub:
     │   └── For each in variables → gh variable set
     │
     ├── 4. Save to .env file:
     │   └── Merge secrets + env_values → write .env
     │
     ├── 5. Sync enforcement:
     │   └── Verify sync_keys exist in both GitHub and .env
     │
     └── Return:
         { ok: true, pushed: 5, deleted: 1, saved_to_env: true }
```

### Environment Lifecycle

```
POST /api/gh/environment/create  { name: "staging" }
     │
     ▼
secrets_ops.create_environment(root, "staging")
     │
     └── gh api -X PUT /repos/{owner}/{repo}/environments/staging
         → { ok: true, name: "staging" }

POST /api/env/cleanup  { name: "staging", delete_files: true, delete_github: false }
     │
     ▼
secrets_ops.cleanup_environment(root, "staging", delete_files=True, delete_github=False)
     │
     ├── delete_files=True? → rm .env.staging
     ├── delete_github=True? → gh api -X DELETE /repos/.../environments/staging
     │
     └── Return: { ok: true, files_deleted: [".env.staging"] }

POST /api/env/seed  { environments: ["dev", "staging", "production"], default: "dev" }
     │
     ▼
secrets_ops.seed_environments(root, ["dev", "staging", "production"], default="dev")
     │
     ├── Copy .env → .env.dev, .env.staging, .env.production
     ├── Set default env pointer
     │
     └── Return: { ok: true, seeded: ["dev", "staging", "production"] }
```

---

## File Map

```
routes/secrets/
├── __init__.py     18 lines — blueprint + 2 sub-module imports
├── status.py       40 lines — 4 read-only endpoints
├── actions.py     152 lines — 6 mutation endpoints
└── README.md               — this file
```

Core business logic: `core/services/secrets/` (937 lines across 3 modules).
Backward-compat shim: `core/services/secrets_ops.py` (31 lines, re-exports all).

---

## Per-File Documentation

### `__init__.py` — Blueprint Definition (18 lines)

```python
secrets_bp = Blueprint("secrets", __name__)

from . import status, actions  # register routes
```

### `status.py` — Read-Only Endpoints (40 lines)

| Function | Method | Route | What It Does |
|----------|--------|-------|-------------|
| `api_gh_status()` | GET | `/gh/status` | GitHub CLI installed + authenticated |
| `api_gh_auto()` | GET | `/gh/auto` | Auto-detect token + repo from git remote |
| `api_gh_environments()` | GET | `/gh/environments` | List deployment environments |
| `api_gh_secrets()` | GET | `/gh/secrets` | List secrets + variables |

**Shared `_env_name()` helper:**

```python
def _env_name() -> str:
    return request.args.get("env", "").strip().lower()
```

Used by `/gh/secrets` to scope queries to a specific environment.

### `actions.py` — Mutation Endpoints (152 lines)

| Function | Method | Route | What It Does |
|----------|--------|-------|-------------|
| `api_keys_generate()` | POST | `/keys/generate` | Generate secret values |
| `api_gh_environment_create()` | POST | `/gh/environment/create` | Create deployment env |
| `api_env_cleanup()` | POST | `/env/cleanup` | Delete env files + optionally GitHub env |
| `api_env_seed()` | POST | `/env/seed` | Seed multi-env from single .env |
| `api_secret_set()` | POST | `/secret/set` | Set secret to local + GitHub |
| `api_secret_remove()` | POST | `/secret/remove` | Remove secret from local + GitHub |
| `api_push_secrets()` | POST | `/secrets/push` | Bulk push with sync enforcement |

**The bulk push endpoint is the most complex — it accepts 8 parameters:**

```python
result = secrets_ops.push_secrets(
    root,
    secrets_dict=data.get("secrets", {}),          # encrypted values → GitHub secrets
    variables=data.get("variables", {}),            # plain values → GitHub variables
    env_values=data.get("env_values", {}),          # local-only values → .env
    deletions=data.get("deletions", []),             # keys to delete
    sync_keys=data.get("sync_keys", []),             # keys that must be in both
    push_to_github=data.get("push_to_github", True), # write to GitHub
    save_to_env=data.get("save_to_env", True),       # write to .env
    exclude_from_github=set(data.get("exclude_from_github", [])),  # skip GitHub
    env_name=_env_name(),                            # environment scope
)
```

---

## Dependency Graph

```
__init__.py
└── Imports: status, actions

status.py
├── secrets_ops ← gh_status, gh_auto_detect, list_environments, list_gh_secrets (eager)
└── helpers     ← project_root (eager)

actions.py
├── secrets_ops ← generate_key, create_environment, cleanup_environment,
│                 seed_environments, set_secret, remove_secret, push_secrets (eager)
└── helpers     ← project_root (eager)
```

**Core service chain:**

```
secrets_ops.py (shim, 31 lines)
├── secrets/ops.py (255 lines)
│   ├── classify_key → categorize as secret vs variable
│   ├── gh_status → check gh CLI status
│   ├── gh_auto_detect → extract token + repo
│   └── generate_key → generate passwords, tokens, SSH keys, certs
│
├── secrets/gh_ops.py (441 lines)
│   ├── list_gh_secrets → list secrets + variables
│   ├── set_secret → set to GitHub + .env
│   ├── remove_secret → remove from GitHub + .env
│   └── push_secrets → bulk push with sync
│
└── secrets/env_ops.py (204 lines)
    ├── list_environments → list GitHub deployment envs
    ├── create_environment → create deployment env
    ├── cleanup_environment → delete files + env
    └── seed_environments → split .env → multi-env
```

---

## Consumers

| Layer | Module | What It Uses |
|-------|--------|-------------|
| Server | `ui/web/server.py` | Imports `secrets_bp`, registers at `/api` |
| Secrets panel | `scripts/secrets/_init.html` | `/gh/status`, `/gh/auto` |
| Secrets list | `scripts/secrets/_secrets.html` | `/gh/secrets`, `/secret/set`, `/secret/remove` |
| Secrets sync | `scripts/secrets/_sync.html` | `/secrets/push` |
| Key gen | `scripts/secrets/_keys.html` | `/keys/generate` |
| Secrets render | `scripts/secrets/_render.html` | `/gh/secrets` |
| Env card | `scripts/devops/_env.html` | `/gh/status` |
| CI/CD | `scripts/integrations/_cicd.html` | `/gh/secrets` |
| GitHub | `scripts/integrations/_github.html` | `/gh/status` |
| GitHub setup | `scripts/integrations/setup/_github.html` | `/gh/auto` |
| Auth modal | `scripts/globals/_auth_modal.html` | `/gh/status` |
| Ops modal | `scripts/globals/_ops_modal.html` | `/gh/secrets` |
| Wizard | `scripts/wizard/_integrations.html` + `_steps.html` | `/gh/auto`, `/gh/status` |

---

## Data Shapes

### `GET /api/gh/status` response

```json
{
    "installed": true,
    "authenticated": true,
    "user": "octocat"
}
```

### `GET /api/gh/auto` response

```json
{
    "ok": true,
    "token": "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    "repo": "octocat/my-project"
}
```

### `GET /api/gh/environments` response

```json
{
    "ok": true,
    "environments": ["production", "staging", "development"]
}
```

### `GET /api/gh/secrets?env=production` response

```json
{
    "ok": true,
    "secrets": ["DATABASE_URL", "API_KEY", "JWT_SECRET"],
    "variables": [
        { "name": "NODE_ENV", "value": "production" },
        { "name": "LOG_LEVEL", "value": "warn" }
    ]
}
```

### `POST /api/keys/generate` request + response

```json
// Request (password):
{ "type": "password", "length": 32 }
// Response:
{ "ok": true, "type": "password", "value": "aB3xKm9p..." }

// Request (SSH key):
{ "type": "ssh" }
// Response:
{ "ok": true, "type": "ssh",
  "private_key": "-----BEGIN OPENSSH PRIVATE KEY-----\n...",
  "public_key": "ssh-ed25519 AAAA..." }

// Request (self-signed cert):
{ "type": "cert", "cn": "api.example.com" }
// Response:
{ "ok": true, "type": "cert",
  "cert": "-----BEGIN CERTIFICATE-----\n...",
  "key": "-----BEGIN PRIVATE KEY-----\n..." }
```

### `POST /api/secret/set` request + response

```json
// Request:
{ "name": "API_KEY", "value": "sk-abc123", "target": "both" }

// Response:
{ "ok": true, "targets": ["local", "github"] }
```

### `POST /api/secrets/push` response

```json
{
    "ok": true,
    "pushed": 5,
    "deleted": 1,
    "saved_to_env": true
}
```

### `POST /api/env/seed` request + response

```json
// Request:
{ "environments": ["dev", "staging", "production"], "default": "dev" }

// Response:
{ "ok": true, "seeded": ["dev", "staging", "production"] }
```

---

## Advanced Feature Showcase

### 1. Dual-Target Secret Management

Every secret operation supports a `target` parameter:
- `"local"` — .env file only
- `"github"` — GitHub secrets API only
- `"both"` — write to both simultaneously

This allows developers to keep local-only secrets (like debug
flags) while syncing production secrets with GitHub.

### 2. Multi-Type Key Generation

The `/keys/generate` endpoint produces 5 different secret types:
- **password** — `secrets.token_urlsafe()`
- **token** — `secrets.token_hex()`
- **uuid** — `uuid.uuid4()`
- **ssh** — `ssh-keygen -t ed25519` (returns key pair)
- **cert** — `openssl req -x509` (returns cert + private key)

### 3. Bulk Push with Sync Enforcement

The `/secrets/push` endpoint has a `sync_keys` parameter that
ensures specified keys exist in both GitHub and .env:

```json
{ "sync_keys": ["API_KEY", "DB_URL"] }
```

If a sync key is missing from either target after push, the
response flags it.

### 4. Environment Seeding

`/env/seed` transitions a project from single-env to multi-env
by duplicating `.env` into environment-specific files:

```
.env → .env.dev, .env.staging, .env.production
```

### 5. Environment Cleanup with Selective Deletion

`/env/cleanup` supports granular cleanup with two independent flags:

```json
{ "delete_files": true, "delete_github": false }
```

Delete local .env files without touching GitHub, or vice versa.

---

## Design Decisions

### Why secrets routes use non-standard URL patterns

The routes use `/gh/`, `/secret/`, `/secrets/`, `/keys/`, `/env/`
prefixes because these endpoints were originally split across
different areas (GitHub management, key generation, environment
management). The grouping under a single blueprint unifies them
without breaking existing frontend references.

### Why actions are not tracked

Secret operations are sensitive — tracking them in the activity
log with their parameters could expose secret values. Instead,
these operations are fire-and-forget from the tracker perspective.

### Why secret values are never returned in lists

`/gh/secrets` returns only secret **names**, never values. GitHub
doesn't expose secret values after creation, and the local .env
values are not returned through the listing endpoint for security.

---

## Coverage Summary

| Capability | Endpoint | Method | Tracked | Cached |
|-----------|----------|--------|---------|--------|
| GH CLI status | `/gh/status` | GET | No | No |
| Auto-detect | `/gh/auto` | GET | No | No |
| Environments | `/gh/environments` | GET | No | No |
| List secrets | `/gh/secrets` | GET | No | No |
| Generate key | `/keys/generate` | POST | No | No |
| Create env | `/gh/environment/create` | POST | No | No |
| Cleanup env | `/env/cleanup` | POST | No | No |
| Seed envs | `/env/seed` | POST | No | No |
| Set secret | `/secret/set` | POST | No | No |
| Remove secret | `/secret/remove` | POST | No | No |
| Bulk push | `/secrets/push` | POST | No | No |
