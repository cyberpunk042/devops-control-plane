# Vault Routes — Secrets Encryption, .env Key Management & Transfer API

> **7 files · 421 lines · 19 endpoints · Blueprint: `vault_bp` · Prefix: `/api`**
>
> Five sub-domains under a single blueprint:
>
> 1. **Status (read-only)** — vault status, secret file detection
>    (2 endpoints)
> 2. **Security** — lock (encrypt), unlock (decrypt), register passphrase,
>    auto-lock timer (4 endpoints)
> 3. **Keys** — CRUD on .env entries: list, add, update, delete, move,
>    raw-value, toggle local-only, set metadata, rename section
>    (9 endpoints)
> 4. **Environment management** — active env, activate, templates, create
>    .env file (4 endpoints)
> 5. **Transfer** — export/import encrypted vault files (2 endpoints)
>
> Backed by `core/services/vault/` (2,074 lines across 4 modules):
> - `core.py` (617 lines) — lock/unlock/export/import/passphrase
> - `io.py` (519 lines) — low-level .env I/O and vault file parsing
> - `env_ops.py` (444 lines) — env management, key listing, templates
> - `env_crud.py` (427 lines) — key CRUD, sections, metadata tags

---

## How It Works

### Vault Status Pipeline

```
GET /api/vault/status?env=production
     │
     ▼
vault.vault_status(env_path)
     │
     ├── env_path resolved from ?env= query param:
     │   ├── ?env=""         → .env
     │   └── ?env=production → .env.production
     │
     ├── Check file existence:
     │   ├── .env (or .env.{name}) exists? → plaintext available
     │   └── .env.vault (or .env.{name}.vault) exists? → encrypted backup
     │
     ├── Determine state:
     │   ├── "unlocked" — .env exists, no .vault
     │   ├── "locked" — .vault exists, no .env
     │   ├── "both" — both files exist (needs resolution)
     │   └── "missing" — neither exists
     │
     └── Return:
         { state: "unlocked", env_exists: true, vault_exists: false,
           auto_lock_minutes: 30, has_passphrase: true }

GET /api/vault/secrets
     │
     ▼
vault.detect_secret_files(root)
     │
     ├── Walk project for:
     │   ├── .env, .env.*, .env.vault
     │   ├── *.key, *.pem, *.p12, id_rsa, id_ed25519
     │   ├── credentials, secrets.yml
     │   └── ...
     │
     └── Return:
         { files: [{path, type, locked, gitignored}] }
```

### Lock / Unlock Lifecycle

```
POST /api/vault/lock  { passphrase: "my-secret" }
     │
     ├── @run_tracked("setup", "setup:vault_lock")
     │
     ▼
vault.lock_vault(env_path, passphrase)
     │
     ├── Read .env contents
     ├── Encrypt with passphrase (AES-256-GCM via Fernet)
     ├── Write .env.vault
     ├── Delete .env (plaintext removed)
     ├── Store passphrase hash in memory (for auto-lock)
     │
     └── Return: { ok: true, state: "locked" }

POST /api/vault/unlock  { passphrase: "my-secret" }
     │
     ├── @run_tracked("setup", "setup:vault_unlock")
     │
     ▼
vault.unlock_vault(env_path, passphrase)
     │
     ├── Read .env.vault
     ├── Decrypt with passphrase
     ├── Write .env (plaintext restored)
     ├── Keep .env.vault (backup)
     ├── Store passphrase in memory (for auto-lock)
     │
     └── Return: { ok: true, state: "unlocked" }

POST /api/vault/register  { passphrase: "my-secret" }
     │
     ├── @run_tracked("setup", "setup:vault_register")
     │
     ▼
vault.register_passphrase(passphrase, env_path)
     │
     ├── Validate passphrase against existing .env.vault
     ├── Store in memory (no file changes)
     │
     └── Return: { ok: true, registered: true }

POST /api/vault/auto-lock  { minutes: 30 }
     │
     ▼
vault.set_auto_lock_minutes(30)
     │
     └── Return: { ok: true, minutes: 30 }
```

### Key Management Pipeline

```
GET /api/vault/keys?env=production
     │
     ▼
vault_env_ops.list_keys_enriched(env_path)
     │
     ├── Parse .env file:
     │   ├── Extract KEY=VALUE pairs
     │   ├── Preserve section comments (# ── Section ──)
     │   ├── Detect # local-only annotations
     │   ├── Extract @ metadata tags
     │   └── Mask values (show "••••••" not raw secrets)
     │
     └── Return:
         { keys: [{key, masked_value, section, local_only, meta_tags}] }

POST /api/vault/add-keys
     Body: { entries: [{key: "API_KEY", value: "abc"}], section: "API" }
     │
     ▼
vault_env_ops.add_keys(env_path, entries, section="API")
     │
     ├── Add/update entries in .env
     ├── Place under section comment if specified
     │
     └── Return: { ok: true, added: 1 }

POST /api/vault/update-key  { key: "API_KEY", value: "new-value" }
     │
     ▼
vault_env_ops.update_key(env_path, "API_KEY", "new-value")
     │
     └── Return: { ok: true }

POST /api/vault/delete-key  { key: "API_KEY" }
     │
     ▼
vault_env_ops.delete_key(env_path, "API_KEY")
     │
     └── Return: { ok: true }

POST /api/vault/move-key  { key: "API_KEY", section: "Infrastructure" }
     │
     ▼
vault_env_ops.move_key(env_path, "API_KEY", "Infrastructure")
     │
     └── Return: { ok: true }

POST /api/vault/rename-section  { old_name: "API", new_name: "External APIs" }
     │
     ▼
vault_env_ops.rename_section(env_path, "API", "External APIs")
     │
     └── Return: { ok: true }

POST /api/vault/raw-value  { key: "API_KEY" }
     │
     ▼
vault_env_ops.get_raw_value(env_path, "API_KEY")
     │
     └── Return: { ok: true, key: "API_KEY", value: "sk-abc123..." }
     (This is the ONLY endpoint that returns unmasked values)

POST /api/vault/toggle-local-only  { key: "API_KEY", local_only: true }
     │
     ▼
vault_env_ops.toggle_local_only(env_path, "API_KEY", local_only=True)
     │
     ├── Adds or removes "# local-only" annotation
     │   (used by /secrets/push to skip GitHub sync)
     │
     └── Return: { ok: true }

POST /api/vault/set-meta  { key: "API_KEY", meta_tags: "@rotate=90d @owner=backend" }
     │
     ▼
vault_env_ops.set_meta(env_path, "API_KEY", "@rotate=90d @owner=backend")
     │
     └── Return: { ok: true }
```

### Environment Management Pipeline

```
GET /api/vault/active-env
     │
     ▼
vault_env_ops.read_active_env(root)
     │
     └── Return: { active: "production" }
         (reads .state/active_env or defaults to "")

POST /api/vault/activate-env  { name: "staging" }
     │
     ▼
vault_env_ops.activate_env(root, "staging", vault_module=vault)
     │
     ├── If current env is unlocked:
     │   └── Auto-lock current .env → .env.vault
     ├── Swap .env ↔ .env.{name}
     ├── Save active env pointer
     │
     └── Return: { ok: true, active: "staging" }

GET /api/vault/templates
     │
     ▼
vault_env_ops.get_templates()
     │
     └── Return: { sections: ["Database", "Auth", "AWS", "Docker", ...] }

POST /api/vault/create  { entries: [...], template_sections: ["Database", "Auth"] }
     │
     ├── @run_tracked("setup", "setup:vault")
     │
     ▼
vault_env_ops.create_env(env_path, entries=[...], template_sections=["Database", "Auth"])
     │
     ├── Expand template sections into key stubs
     ├── Merge with provided entries
     ├── Write .env file
     │
     └── Return: { ok: true, path: ".env" }
```

### Transfer Pipeline

```
POST /api/vault/export  { password: "transfer-key", filename: ".env" }
     │
     ├── @run_tracked("backup", "backup:vault")
     │
     ▼
vault.export_vault_file(file_path, password)
     │
     ├── Read file contents
     ├── Encrypt with transfer password (separate from vault passphrase)
     ├── Base64 encode
     │
     └── Return: { success: true, envelope: "base64-encoded-encrypted-data" }

POST /api/vault/import
     Body: { password: "transfer-key", vault_data: "base64...", target: ".env", dry_run: true }
     │
     ├── @run_tracked("restore", "restore:vault")
     │
     ▼
vault.import_vault_file(vault_data, target_path, password, dry_run=True)
     │
     ├── Decode Base64
     ├── Decrypt with transfer password
     ├── dry_run=true? → preview without writing
     ├── dry_run=false? → write to target file
     │
     └── Return: { ok: true, preview: "KEY1=***\nKEY2=***\n..." }
```

---

## File Map

```
routes/vault/
├── __init__.py     22 lines — blueprint + 5 sub-module imports
├── helpers.py      18 lines — shared _env_path() helper
├── status.py       25 lines — 2 detection endpoints
├── security.py     83 lines — 4 lock/unlock endpoints
├── keys.py        153 lines — 9 key management endpoints
├── env_mgmt.py     61 lines — 4 environment management endpoints
├── transfer.py     59 lines — 2 export/import endpoints
└── README.md               — this file
```

Core business logic: `core/services/vault/` (2,074 lines across 4 modules).
Backward-compat shims: `vault.py` (9 lines), `vault_env_ops.py` (32 lines).

---

## Per-File Documentation

### `__init__.py` — Blueprint Definition (22 lines)

```python
vault_bp = Blueprint("vault", __name__)

from . import status, security, keys, env_mgmt, transfer
```

### `helpers.py` — Shared Utilities (18 lines)

```python
def _env_path() -> Path:
    env_name = request.args.get("env", "").strip().lower()
    root = _project_root()
    if not env_name:
        return root / ".env"
    return root / f".env.{env_name}"
```

Used by every sub-module to support multi-environment mode via `?env=` query param.

### `status.py` — Detection (25 lines)

| Function | Method | Route | What It Does |
|----------|--------|-------|-------------|
| `vault_status()` | GET | `/vault/status` | Vault state + config |
| `vault_secrets()` | GET | `/vault/secrets` | Detect secret files |

### `security.py` — Lock/Unlock (83 lines)

| Function | Method | Route | Tracked | What It Does |
|----------|--------|-------|---------|-------------|
| `vault_lock()` | POST | `/vault/lock` | ✅ `setup:vault_lock` | Encrypt .env → .env.vault |
| `vault_unlock()` | POST | `/vault/unlock` | ✅ `setup:vault_unlock` | Decrypt .env.vault → .env |
| `vault_register()` | POST | `/vault/register` | ✅ `setup:vault_register` | Register passphrase only |
| `vault_auto_lock()` | POST | `/vault/auto-lock` | No | Set auto-lock timeout |

### `keys.py` — .env Key CRUD (153 lines)

| Function | Method | Route | What It Does |
|----------|--------|-------|-------------|
| `vault_keys()` | GET | `/vault/keys` | List keys (masked values) |
| `vault_add_keys()` | POST | `/vault/add-keys` | Add key-value pairs |
| `vault_update_key()` | POST | `/vault/update-key` | Update single key |
| `vault_delete_key()` | POST | `/vault/delete-key` | Remove key |
| `vault_move_key()` | POST | `/vault/move-key` | Move key between sections |
| `vault_rename_section()` | POST | `/vault/rename-section` | Rename section comment |
| `vault_raw_value()` | POST | `/vault/raw-value` | Get unmasked value |
| `vault_toggle_local_only()` | POST | `/vault/toggle-local-only` | Toggle local-only flag |
| `vault_set_meta()` | POST | `/vault/set-meta` | Set metadata tags |

### `env_mgmt.py` — Environment Management (61 lines)

| Function | Method | Route | Tracked | What It Does |
|----------|--------|-------|---------|-------------|
| `vault_active_env()` | GET | `/vault/active-env` | No | Current active env |
| `vault_activate_env()` | POST | `/vault/activate-env` | No | Swap .env to named env |
| `vault_templates()` | GET | `/vault/templates` | No | List template sections |
| `vault_create()` | POST | `/vault/create` | ✅ `setup:vault` | Create .env from template |

### `transfer.py` — Export/Import (59 lines)

| Function | Method | Route | Tracked | What It Does |
|----------|--------|-------|---------|-------------|
| `vault_export()` | POST | `/vault/export` | ✅ `backup:vault` | Encrypted export |
| `vault_import()` | POST | `/vault/import` | ✅ `restore:vault` | Decrypt and import |

---

## Dependency Graph

```
__init__.py
└── Imports: status, security, keys, env_mgmt, transfer

helpers.py
└── helpers ← project_root (eager)

status.py
├── vault        ← vault_status, detect_secret_files (eager)
├── helpers      ← project_root (eager)
└── .helpers     ← _env_path (local)

security.py
├── vault        ← lock_vault, unlock_vault, register_passphrase,
│                  set_auto_lock_minutes (eager)
├── run_tracker  ← @run_tracked (eager)
└── .helpers     ← _env_path (local)

keys.py
├── vault_env_ops ← list_keys_enriched, add_keys, update_key, delete_key,
│                   move_key, rename_section, get_raw_value,
│                   toggle_local_only, set_meta (eager)
└── .helpers      ← _env_path (local)

env_mgmt.py
├── vault         ← (passed to activate_env as vault_module) (eager)
├── vault_env_ops ← read_active_env, activate_env, get_templates, create_env (eager)
├── run_tracker   ← @run_tracked (eager)
├── helpers       ← project_root (eager)
└── .helpers      ← _env_path (local)

transfer.py
├── vault         ← export_vault_file, import_vault_file (eager)
├── run_tracker   ← @run_tracked (eager)
└── helpers       ← project_root (eager)
```

---

## Consumers

| Layer | Module | What It Uses |
|-------|--------|-------------|
| Server | `ui/web/server.py` | Imports `vault_bp`, registers at `/api` |
| Vault panel | `scripts/secrets/_vault.html` | `/vault/status`, `/vault/lock`, `/vault/unlock` |
| Secrets init | `scripts/secrets/_init.html` | `/vault/status` |
| Key editor | `scripts/secrets/_keys.html` | `/vault/keys`, `/vault/add-keys`, `/vault/raw-value` |
| Secret form | `scripts/secrets/_form.html` | `/vault/keys` |
| Secrets sync | `scripts/secrets/_sync.html` | `/vault/keys`, `/vault/status` |
| DevOps env | `scripts/devops/_env.html` | `/vault/status`, `/vault/active-env` |
| Docker wizard | `scripts/docker_wizard/_raw_step1_detect.html` | `/vault/status` |
| K8s wizard | `scripts/k8s_wizard/_raw_step1_detect.html` | `/vault/status` |
| K8s containers | `scripts/k8s_wizard/_raw_step2_containers.html` | `/vault/keys` |
| CI/CD setup | `scripts/integrations/setup/_cicd.html` | `/vault/keys` |
| GitHub setup | `scripts/integrations/setup/_github.html` | `/vault/keys` |
| Wizard init | `scripts/wizard/_init.html` | `/vault/status` |
| Wizard steps | `scripts/wizard/_steps.html` | `/vault/status`, `/vault/keys` |
| Debugging | `scripts/_debugging.html` | `/vault/status` |

---

## Data Shapes

### `GET /api/vault/status?env=production` response

```json
{
    "state": "unlocked",
    "env_exists": true,
    "vault_exists": false,
    "auto_lock_minutes": 30,
    "has_passphrase": true
}
```

### `GET /api/vault/keys` response

```json
{
    "keys": [
        {
            "key": "DATABASE_URL",
            "masked_value": "postgres://••••••",
            "section": "Database",
            "local_only": false,
            "meta_tags": "@rotate=90d"
        },
        {
            "key": "DEBUG_FLAG",
            "masked_value": "true",
            "section": "Local",
            "local_only": true,
            "meta_tags": ""
        }
    ]
}
```

### `POST /api/vault/raw-value` response

```json
{
    "ok": true,
    "key": "DATABASE_URL",
    "value": "postgres://user:password@host:5432/db"
}
```

### `POST /api/vault/lock` response

```json
{ "ok": true, "state": "locked" }
```

### `POST /api/vault/export` response

```json
{
    "success": true,
    "envelope": "gAAAAA...base64-encoded-encrypted-data..."
}
```

### `POST /api/vault/import` response (dry run)

```json
{
    "ok": true,
    "preview": "DATABASE_URL=***\nAPI_KEY=***\n..."
}
```

### `GET /api/vault/active-env` response

```json
{ "active": "production" }
```

### `GET /api/vault/templates` response

```json
{
    "sections": ["Database", "Auth", "AWS", "Docker",
                 "Monitoring", "Email", "Redis", "S3"]
}
```

---

## Advanced Feature Showcase

### 1. Multi-Environment Support via `?env=` param

Every vault endpoint respects the `?env=` query parameter:

```
/vault/status?env=production    → checks .env.production
/vault/keys?env=staging         → lists .env.staging keys
/vault/lock?env=dev             → encrypts .env.dev
```

The shared `_env_path()` helper resolves this uniformly.

### 2. Section-Aware .env Structure

The vault respects and preserves section comments in .env files:

```env
# ── Database ──
DATABASE_URL=postgres://...
REDIS_URL=redis://...

# ── Auth ──
JWT_SECRET=...
API_KEY=... # local-only
```

Keys can be moved between sections, sections can be renamed,
and new keys can be added to specific sections.

### 3. Metadata Tags

Keys support `@` metadata annotations:

```env
API_KEY=sk-abc123  # @rotate=90d @owner=backend
```

The `/vault/set-meta` endpoint manages these inline.

### 4. Transfer with Dry Run

The import endpoint supports `dry_run: true` to preview what
would be imported without modifying any files. This lets the
UI show a confirmation dialog before executing.

### 5. Auto-Lock on Environment Switch

When activating a different environment via `/vault/activate-env`,
the current .env is automatically locked if the passphrase is
registered. This prevents leaving plaintext secrets exposed.

### 6. Value Masking by Default

`/vault/keys` returns masked values (`••••••`) by default.
Only `/vault/raw-value` (POST, requiring intentional action)
returns the actual secret value. This prevents accidental
exposure in API responses.

---

## Design Decisions

### Why keys.py uses vault_env_ops, not vault

The `vault` module handles encryption/decryption (security concerns).
The `vault_env_ops` module handles .env file parsing and manipulation
(data management). This separation means key CRUD operations work
on plaintext .env files without needing the encryption subsystem.

### Why raw-value is POST, not GET

GET requests with secret values could be logged in browser history,
server access logs, or proxy logs. Using POST ensures the request
body (containing the key name) isn't leaked through URL logging.

### Why vault_status is not cached

Vault state can change at any moment (auto-lock timer expiring,
manual lock/unlock). Caching would show stale state, which is
dangerous for a security-critical feature.

### Why export uses a separate password

The export password is different from the vault passphrase.
This allows sharing encrypted exports with other team members
using a one-time transfer password, without revealing the
vault passphrase.

---

## Coverage Summary

| Capability | Endpoint | Method | Tracked | Cached |
|-----------|----------|--------|---------|--------|
| Vault status | `/vault/status` | GET | No | No |
| Secret files | `/vault/secrets` | GET | No | No |
| Lock | `/vault/lock` | POST | ✅ `setup:vault_lock` | No |
| Unlock | `/vault/unlock` | POST | ✅ `setup:vault_unlock` | No |
| Register | `/vault/register` | POST | ✅ `setup:vault_register` | No |
| Auto-lock | `/vault/auto-lock` | POST | No | No |
| List keys | `/vault/keys` | GET | No | No |
| Add keys | `/vault/add-keys` | POST | No | No |
| Update key | `/vault/update-key` | POST | No | No |
| Delete key | `/vault/delete-key` | POST | No | No |
| Move key | `/vault/move-key` | POST | No | No |
| Rename section | `/vault/rename-section` | POST | No | No |
| Raw value | `/vault/raw-value` | POST | No | No |
| Toggle local-only | `/vault/toggle-local-only` | POST | No | No |
| Set meta | `/vault/set-meta` | POST | No | No |
| Active env | `/vault/active-env` | GET | No | No |
| Activate env | `/vault/activate-env` | POST | No | No |
| Templates | `/vault/templates` | GET | No | No |
| Create .env | `/vault/create` | POST | ✅ `setup:vault` | No |
| Export | `/vault/export` | POST | ✅ `backup:vault` | No |
| Import | `/vault/import` | POST | ✅ `restore:vault` | No |
