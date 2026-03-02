# Vault Domain

> **5 files · 2,079 lines · Encrypt/decrypt secret files at rest with AES-256-GCM.**
>
> Protects `.env` files and other secrets using passphrase-based
> encryption, with session management, auto-lock timers, rate
> limiting, portable export/import, and structured .env parsing.

---

## How It Works

The vault operates on a simple model: **every secret file has a
companion `.vault` file** that stores the encrypted version.

```
.env                    ←→     .env.vault
.env.production         ←→     .env.production.vault
secrets/api-keys.yml    ←→     secrets/api-keys.yml.vault
```

### Lock / Unlock Cycle

```
                 UNLOCKED
         .env exists (plaintext)
         .env.vault might be stale
                    │
                    │  lock_vault(path, passphrase)
                    ▼
     ┌──────────────────────────────┐
     │  1. Derive key (PBKDF2)      │
     │  2. Generate salt (16 bytes)  │
     │  3. Generate IV (12 bytes)    │
     │  4. Encrypt (AES-256-GCM)    │
     │  5. Write .env.vault          │
     │     (JSON envelope with       │
     │      base64 salt/iv/tag/ct)   │
     │  6. Secure-delete .env        │
     │     (3-pass random overwrite  │
     │      + fsync, then unlink)    │
     │  7. Clear session passphrase  │
     │  8. Cancel auto-lock if no    │
     │     passphrases remain        │
     └──────────────────────────────┘
                    │
                    ▼
                 LOCKED
         .env is gone
         .env.vault contains encrypted bytes
                    │
                    │  unlock_vault(path, passphrase)
                    ▼
     ┌──────────────────────────────┐
     │  1. Check rate limit          │
     │  2. Read .env.vault           │
     │  3. Extract salt, IV, tag     │
     │  4. Derive key (PBKDF2)      │
     │  5. Decrypt (AES-256-GCM)    │
     │     → InvalidTag = wrong pass │
     │  6. Write .env (plaintext)    │
     │  7. Store passphrase in       │
     │     _session_passphrases      │
     │  8. Start auto-lock timer     │
     │  9. Reset rate limit          │
     └──────────────────────────────┘
                    │
                    ▼
                 UNLOCKED
```

### Crypto Parameters

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| **Algorithm** | AES-256-GCM | Authenticated encryption — tamper detection |
| **KDF** | PBKDF2-HMAC-SHA256 | Slow key derivation — resists brute force |
| **KDF iterations** | 100,000 | Balance: ~100ms on modern hardware |
| **Salt** | 16 bytes (random) | Unique per encryption — prevents rainbow tables |
| **IV/Nonce** | 12 bytes (random) | GCM standard nonce length |
| **Key** | 32 bytes (256 bits) | AES-256 key derived from passphrase + salt |
| **Export KDF iterations** | 600,000 | Higher for offline attack resistance |
| **Auth tag** | 16 bytes | GCM authentication tag for tamper detection |

### Vault File Format

Vault files are **JSON envelopes** (not raw binary):

```json
{
  "vault": true,
  "version": 1,
  "algorithm": "aes-256-gcm",
  "kdf": "pbkdf2-sha256",
  "kdf_iterations": 100000,
  "salt": "<base64>",
  "iv": "<base64>",
  "tag": "<base64>",
  "ciphertext": "<base64>",
  "original_name": ".env"
}
```

All binary fields are base64-encoded for portability.

### Session Security

**Passphrase memory:** After lock or unlock, the passphrase is stored
in `_session_passphrases` (module-level dict, keyed by resolved path).
This enables auto-lock: the timer can re-encrypt the file without
asking the user again.

**Auto-lock timer:** After 30 minutes of inactivity, all unlocked
vaults are automatically locked using their stored passphrases.

```
User Activity Detection:

  POST /api/vault/...         → touch_activity()
  POST /api/secrets/...       → touch_activity()
  GET /api/status            → NOT touched (background poll)
  GET /api/vault/status      → NOT touched (status check)

  Only user-initiated mutating requests reset the timer.
  Background polling does NOT extend the session.
```

**Rate limiting:** Failed unlock attempts trigger escalating delays:

```python
_RATE_LIMIT_TIERS = [
    (3, 30),       # After 3 fails: 30s lockout
    (6, 300),      # After 6 fails: 5min lockout
    (10, 900),     # After 10 fails: 15min lockout
]
```

**Secure deletion:** When locking, the plaintext file is overwritten
with random data **3 times** (with `os.fsync` after each pass) before
being deleted. This prevents recovery of plaintext from filesystem
residuals.

---

## Key Data Shapes

### vault_status response

```python
# Locked — vault file exists, plaintext does not
{
    "locked": True,
    "vault_exists": True,
    "plaintext_exists": False,
    "has_passphrase": False,     # no session passphrase stored
    "vault_size": 1284,
    "vault_modified": "2026-02-28T14:30:00",
}

# Unlocked — plaintext exists and vault may be stale
{
    "locked": False,
    "vault_exists": True,
    "plaintext_exists": True,
    "has_passphrase": True,      # passphrase in session memory
    "plaintext_size": 1240,
    "plaintext_modified": "2026-02-28T14:35:00",
}

# No vault — file exists but has never been locked
{
    "locked": False,
    "vault_exists": False,
    "plaintext_exists": True,
    "has_passphrase": False,
    "plaintext_size": 1240,
}
```

### lock_vault response

```python
# Success
{"success": True, "message": "Vault locked (.env)"}

# Errors (raised as ValueError)
# "Passphrase must be at least 4 characters"
# ".env not found — nothing to lock"
```

### unlock_vault response

```python
# Success
{"success": True, "message": "Vault unlocked"}

# Wrong passphrase (raised as ValueError)
# "Wrong passphrase — decryption failed"

# Rate limited (raised as ValueError)
# "Too many failed attempts. Try again in 25s."
# (rate limit checked via _check_rate_limit → returns dict with
#  {"error": ..., "retry_after": int, "attempts": int})
```

### register_passphrase response

```python
# Success — passphrase verified against existing vault
{"success": True, "message": "Passphrase registered — auto-lock enabled"}

# Wrong passphrase (raised as ValueError)
# "Wrong passphrase"
```

### export_vault_file response (JSON envelope)

```python
{
    "format": "dcp-vault-export-v1",
    "original_name": ".env",
    "created_at": "2026-02-28T14:30:00+00:00",
    "kdf": "pbkdf2-sha256",
    "kdf_iterations": 600000,
    "salt": "<base64>",
    "iv": "<base64>",
    "tag": "<base64>",
    "ciphertext": "<base64>",
}
```

### import_vault_file response

```python
# Success (write or dry_run)
{
    "success": True,
    "changes": [
        {"key": "DATABASE_URL", "action": "added"},
        {"key": "JWT_SECRET", "action": "changed"},
        {"key": "APP_NAME", "action": "unchanged"},
    ],
    "size": 1240,
}

# Wrong passphrase (raised as ValueError)
# "Wrong password or corrupted vault file"
```

### detect_secret_files response

```python
[
    # Unlocked file (plaintext exists)
    {
        "name": ".env",
        "path": "/project/.env",
        "exists": True,
        "locked": False,
        "size": 1240,
        "modified": 1709145000.0,
        "vault_exists": True,
    },
    # Locked file (only vault exists)
    {
        "name": ".env.production",
        "path": "/project/.env.production",
        "exists": False,
        "locked": True,
        "vault_size": 980,
        "vault_modified": 1709145000.0,
        "vault_exists": True,
    },
]
```

### list_env_keys response

```python
[
    {
        "key": "DATABASE_URL",
        "has_value": True,
        "masked": "postgres://****:****@localhost:5432/app",
        "local_only": False,
        "meta": {"type": "url"},
    },
    {
        "key": "JWT_SECRET",
        "has_value": True,
        "masked": "****",
        "local_only": True,
        "meta": {"generated": "password", "length": 64},
    },
]
```

### list_env_sections response

```python
[
    {
        "name": "Database",
        "keys": [
            {"key": "DATABASE_URL", "has_value": True, "masked": "****", ...},
            {"key": "DB_POOL_SIZE", "has_value": True, "masked": "10", ...},
        ],
    },
    {
        "name": "Authentication",
        "keys": [
            {"key": "JWT_SECRET", "has_value": True, "masked": "****", ...},
        ],
    },
]
```

### list_keys_enriched response

```python
{
    "state": "unlocked",           # "locked" | "unlocked" | "empty"
    "keys": [
        {
            "key": "DATABASE_URL",
            "has_value": True,
            "masked": "****",
            "kind": "secret",       # "secret" | "config" | "internal"
            "raw": None,            # raw value only for "config" kind
            "local_only": False,
            "meta": {},
        },
    ],
    "sections": [...],             # same as list_env_sections
}
```

### Environment activation — activate_env response

```python
# Success
{
    "success": True,
    "previous": "staging",
    "active": "production",
    "state": "unlocked",      # "unlocked" | "locked" | "empty"
}
```

---

## Architecture

```
                  CLI (ui/cli/vault.py)
                  Routes (routes/vault/)
                         │
                         │ imports
                         │
              ┌──────────▼──────────┐
              │  vault_ops.py       │  backward-compat shim
              │  (re-exports all)   │  → imports from vault/
              └──────────┬──────────┘
                         │
              ┌──────────▼──────────────────────────┐
              │  vault/__init__.py                    │
              │  Public API — re-exports all symbols  │
              └────┬──────┬──────┬──────┬────────────┘
                   │      │      │      │
          ┌────────┘      │      │      └────────────┐
          ▼               ▼      ▼                   ▼
       core.py          io.py  env_ops.py        env_crud.py
     (encrypt/        (export/ (env listing,     (key CRUD,
      decrypt,         import,  activation,       section mgmt,
      auto-lock,       detect,  templates,        metadata)
      rate limit)      parse)   create .env)
```

### Dependency Rules

| Rule | Detail |
|------|--------|
| `core.py` is standalone | Crypto operations + session state |
| `io.py` imports `core` | Uses `_vault_path_for`, `get_passphrase`, `VAULT_SUFFIX` |
| `env_ops.py` imports `io` | Uses `list_env_keys`, `list_env_sections` |
| `env_crud.py` is standalone | Pure file manipulation (read/write/parse) |
| `env_ops.py` re-exports `env_crud` | Backward compat — all CRUD via `env_ops` |

---

## File Map

```
vault/
├── __init__.py      Public API re-exports (68 lines)
├── core.py          Encrypt, decrypt, auto-lock, rate limit, session state (618 lines)
├── io.py            Export/import + secret file detection + .env parsing (520 lines)
├── env_ops.py       Environment activation, key listing, templates, .env creation (445 lines)
├── env_crud.py      Key CRUD, section management, metadata operations (428 lines)
└── README.md        This file
```

---

## Per-File Documentation

### `core.py` — Crypto Core (618 lines)

| Section | Functions | Purpose |
|---------|-----------|---------|
| **Crypto** | `_derive_key(passphrase, salt)` | PBKDF2-HMAC-SHA256 key derivation |
| **Crypto** | `_vault_path_for(secret_path)` | `.env` → `.env.vault` path mapping |
| **Crypto** | `_secure_delete(path)` | Overwrite + unlink |
| **Session** | `get_passphrase(path)` | Get stored passphrase |
| **Session** | `has_any_passphrase()` | Any vault in session? |
| **Rate limit** | `_check_rate_limit()` | Escalating delay check |
| **Rate limit** | `_record_failed_attempt()` | Increment failure counter |
| **Rate limit** | `_reset_rate_limit()` | Clear on success |
| **Timer** | `_start_auto_lock_timer()` | 30-minute inactivity timer |
| **Timer** | `_cancel_auto_lock_timer()` | Cancel pending timer |
| **Timer** | `touch_activity(path, method)` | Reset timer for user activity |
| **Core** | `vault_status(path)` | Check lock state |
| **Core** | `lock_vault(path, passphrase)` | Encrypt + secure delete plaintext |
| **Core** | `unlock_vault(path, passphrase)` | Decrypt + write plaintext |
| **Core** | `auto_lock()` | Lock ALL unlocked vaults |
| **Core** | `register_passphrase(passphrase, path)` | Verify + store without locking |
| **Config** | `set_auto_lock_minutes(minutes)` | Set inactivity timeout (0 to disable) |
| **Delegate** | `set_project_root(root)` | Register project root (delegates to core.context) |
| **Delegate** | `get_project_root()` | Return registered project root |

**Module-level state:**

| Object | Type | Purpose |
|--------|------|---------|
| `_session_passphrases` | `dict[str, str]` | Path → passphrase mapping |
| `_auto_lock_timer` | `Timer | None` | Pending auto-lock timer |
| `_auto_lock_minutes` | `int` | Inactivity timeout (default: 30) |
| `_lock` | `threading.Lock` | Thread safety for crypto operations |
| `_failed_attempts` | `int` | Consecutive failed unlock attempts |
| `_last_failed_time` | `float` | Timestamp of last failure |

### `io.py` — Export/Import + Detection + Parsing (520 lines)

| Function | What It Does |
|----------|-------------|
| `export_vault_file(path, passphrase)` | Encrypt → JSON envelope (portable backup) |
| `import_vault_file(data, target, passphrase, dry_run)` | Decrypt JSON → write file |
| `detect_secret_files(root)` | Scan for known secret files with vault status |
| `list_env_keys(path)` | Parse .env → keys with masked values + metadata |
| `list_env_sections(path)` | Parse .env → grouped by section headers |
| `_parse_meta_tags(line)` | Parse `@type:toggle @generated:password` tags |
| `_parse_env_lines(content)` | Raw .env parsing → `{key: value}` dict |

**Meta tag system (`@` tags in .env comments):**

```bash
# @type:toggle @encoding:base64
# @generated:password @length:64
# @local-only
JWT_SECRET=abc123
```

| Tag | Effect |
|-----|--------|
| `@local-only` | Key excluded from GitHub sync |
| `@type:<type>` | UI hint: toggle, url, number, etc. |
| `@encoding:<enc>` | Value encoding: base64, hex |
| `@generated:<gen>` | How value was generated: password, ssh-ed25519, etc. |
| `@length:<n>` | Generator length parameter |
| `@options:<a,b,c>` | Allowed values for toggle type |

**Section header detection:** Recognizes multiple formats:

```bash
# ── Database ──         # box-drawing headers
# === AUTHENTICATION === # triple-equals headers
# --- section ---        # dashed headers
# MY SECTION             # uppercase-only comments
```

### `env_ops.py` — Environment Operations (445 lines)

| Function | What It Does |
|----------|-------------|
| `read_env_values(path)` | Raw key=value parsing |
| `read_active_env(root)` | Which environment is active (from `.env.active`) |
| `activate_env(root, name, vault_module)` | Swap `.env` + `.env.vault` between environments |
| `list_keys_enriched(env_path, vault_path)` | Keys with kind classification (secret/config/internal) |
| `get_templates()` | Available .env template sections for UI |
| `create_env(path, entries, template_sections)` | Create .env from template + key-value pairs |

**Environment activation flow:**

```
activate_env(root, "production")
    │
    ├── 1. Read .env.active → "staging" (old)
    ├── 2. Copy .env → .env.staging (save current)
    ├── 3. Copy .env.staging.vault → .env.vault (if exists)
    ├── 4. Copy .env.production → .env (activate new)
    ├── 5. Copy .env.production.vault → .env.vault
    └── 6. Write "production" to .env.active
```

### `env_crud.py` — Key CRUD Operations (428 lines)

| Function | What It Does | Idempotent |
|----------|-------------|-----------|
| `add_keys(path, entries, section)` | Add/update multiple keys | Yes (update if exists) |
| `update_key(path, key, value)` | Update single key value | Yes |
| `delete_key(path, key)` | Remove key (+ associated comments) | ✅ |
| `get_raw_value(path, key)` | Read unmasked value | N/A |
| `move_key(path, key, target_section)` | Move key to different section | No |
| `rename_section(path, old, new)` | Rename section header | No |
| `toggle_local_only(path, key, local_only)` | Toggle `# local-only` marker | Yes |
| `set_meta(path, key, meta_tags)` | Set/update `@` metadata tags | Yes |

---

## Audit Trail

| Event | Icon | Title | Target |
|-------|------|-------|--------|
| Vault locked | 🔒 | Vault Locked | file path |
| Vault unlocked | 🔓 | Vault Unlocked | file path |
| Auto-lock fired | ⏰ | Auto-Lock | all files |
| Vault exported | 📤 | Vault Exported | file path |
| Vault imported | 📥 | Vault Imported | file path |
| Passphrase registered | 🔑 | Passphrase Registered | file path |

---

## Consumers

| Consumer | What It Uses |
|----------|-------------|
| **Routes** `routes/vault/` | All functions — status, lock, unlock, export, import, env CRUD |
| **CLI** `ui/cli/vault.py` | `vault_status`, `lock_vault`, `unlock_vault` |
| **Secrets** `secrets/gh_ops.py` | Uses env file parsing for GitHub secret sync |
| **Wizard** `wizard/helpers.py` | `detect_secret_files` for environment detection |
| **Metrics** `metrics/ops.py` | `vault_status` for health probes |

---

## API Endpoints

| Route | Method | Purpose | Module |
|-------|--------|---------|--------|
| `/api/vault/status` | GET | Vault lock state | `core` |
| `/api/vault/lock` | POST | Encrypt + secure delete | `core` |
| `/api/vault/unlock` | POST | Decrypt | `core` |
| `/api/vault/register` | POST | Verify + store passphrase | `core` |
| `/api/vault/export` | POST | Create portable backup | `io` |
| `/api/vault/import` | POST | Restore from backup | `io` |
| `/api/vault/files` | GET | List detected secret files | `io` |
| `/api/vault/env/keys` | GET | List .env keys (masked) | `io` |
| `/api/vault/env/sections` | GET | List .env sections | `io` |
| `/api/vault/env/enriched` | GET | Keys with classification | `env_ops` |
| `/api/vault/env/templates` | GET | Available .env templates | `env_ops` |
| `/api/vault/env/create` | POST | Create new .env file | `env_ops` |
| `/api/vault/env/activate` | POST | Switch active environment | `env_ops` |
| `/api/vault/env/add` | POST | Add/update keys | `env_crud` |
| `/api/vault/env/update` | POST | Update single key | `env_crud` |
| `/api/vault/env/delete` | POST | Delete key | `env_crud` |
| `/api/vault/env/get` | GET | Get raw value | `env_crud` |
| `/api/vault/env/move` | POST | Move key to section | `env_crud` |
| `/api/vault/env/rename-section` | POST | Rename section | `env_crud` |
| `/api/vault/env/toggle-local` | POST | Toggle local-only | `env_crud` |
| `/api/vault/env/set-meta` | POST | Set metadata tags | `env_crud` |

---

## Advanced Feature Showcase

### 1. JSON Envelope with Full Crypto Stack

`lock_vault` encrypts with AES-256-GCM and stores everything needed
to decrypt in a single self-describing JSON envelope.

```python
# core.py — lock_vault() builds this envelope
envelope = {
    "vault": True,
    "version": 1,
    "algorithm": "aes-256-gcm",
    "kdf": "pbkdf2-sha256",
    "kdf_iterations": KDF_ITERATIONS,     # 100_000
    "salt": base64.b64encode(salt).decode("ascii"),
    "iv": base64.b64encode(iv).decode("ascii"),
    "tag": base64.b64encode(tag).decode("ascii"),
    "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
    "original_name": secret_path.name,
}
```

One file, one JSON, all metadata inline. No separate key files,
no binary blob — human-inspectable, version-tagged, portable.

---

### 2. 3-Pass Secure Deletion with fsync

After encrypting, the plaintext is overwritten 3 times with random
data before deletion. Each pass is flushed to disk via `os.fsync`.

```python
# core.py — _secure_delete()
def _secure_delete(path: Path) -> None:
    try:
        size = path.stat().st_size
        for _ in range(3):
            with open(path, "wb") as f:
                f.write(os.urandom(max(size, 1)))
                f.flush()
                os.fsync(f.fileno())
        path.unlink()
    except Exception:
        try:
            path.unlink()       # Fallback: at least delete it
        except Exception:
            pass
```

Prevents casual recovery (`strings`, `grep` on disk). Falls back
to simple delete if overwrite fails (read-only filesystem, etc.).

---

### 3. Escalating Rate Limit Tiers

Failed unlock attempts trigger increasingly harsh lockouts —
not a flat limit but a 3-tier escalation.

```python
# core.py — rate limiting state
_RATE_LIMIT_TIERS = [
    # (max_attempts, lockout_seconds)
    (3, 30),       # After 3 fails: 30s lockout
    (6, 300),      # After 6 fails: 5min lockout
    (10, 900),     # After 10 fails: 15min lockout
]
```

The `_check_rate_limit()` function scans all tiers and returns
the longest applicable lockout. Resets to zero on any successful unlock.

---

### 4. Auto-Lock with Smart Activity Tracking

A daemon thread auto-locks all vaults after N minutes of inactivity.
The twist: `touch_activity()` filters out background polling so the
timer actually expires.

```python
# core.py — touch_activity()
_POLLING_ENDPOINTS = {
    "/api/status",
    "/api/health",
    "/api/vault/status",
}

def touch_activity(request_path="", request_method="GET"):
    if not _session_passphrases:
        return
    if request_path in _POLLING_ENDPOINTS and request_method in ("GET", "POST"):
        return
    if request_path.startswith("/static/"):
        return
    _start_auto_lock_timer()     # daemon thread, auto_lock_minutes * 60
```

Without this filter, the dashboard's 30-second status poll would
never let the timer expire.

---

### 5. Hardened Export with Separate KDF Iterations

Export envelopes face offline brute-force (no rate limiting), so
they use 6× more KDF iterations than local vault files.

```python
# core.py constants side-by-side
KDF_ITERATIONS = 100_000           # Local vault — protected by rate limiter
EXPORT_KDF_ITERATIONS = 600_000    # Export — portable, offline-attackable
```

Same algorithm (PBKDF2-SHA256), same envelope structure, but the
export `_derive_key()` call substitutes `EXPORT_KDF_ITERATIONS`.

---

### 6. Dry-Run Import with Key-Level Change Diff

`import_vault_file()` can preview changes before writing. It decrypts
the envelope, parses the .env content, and diffs against the current file.

```python
# io.py — import_vault_file(), dry_run mode
changes: list[dict] = []
if target_path.name == ".env":
    new_env = _parse_env_lines(new_content)
    current_env = _parse_env_lines(target_path.read_text("utf-8")) if target_path.exists() else {}

    for k in sorted(set(list(new_env.keys()) + list(current_env.keys()))):
        if k in new_env and k not in current_env:
            changes.append({"key": k, "action": "added"})
        elif k in new_env and k in current_env:
            action = "unchanged" if new_env[k] == current_env[k] else "changed"
            changes.append({"key": k, "action": action})
        else:
            changes.append({"key": k, "action": "kept"})
```

Returns `{"success": True, "changes": [...], "size": N}` — the UI shows
a preview table (added / changed / unchanged / kept) before committing.

---

### 7. Section-Aware .env Parsing with Metadata Tags

The parser recognizes section headers (multiple formats) and per-key
`@` metadata tags, producing structured output from a flat file.

```python
# io.py — section header regex accepts:
#   # ── Section Name ──      (box-drawing chars)
#   # === SECTION ===          (equals signs)
#   # --- section ---          (dashes)
#   # MY SECTION               (all-caps comment)
section_re = re.compile(
    r"^#\s*(?:[─━═\-=]{2,}\s*)?([A-Za-z][\w\s/()]+?)\s*(?:[─━═\-=]{2,})?\s*$"
)

# io.py — metadata tags parsed from comments above keys
# @type:password @generated:password @length:32
# DB_PASSWORD=...
```

Keys carry structured metadata (`local_only`, `type`, `encoding`,
`generated`) without changing the .env format — all stored in comments.

---

## Design Decisions

### Why PBKDF2 instead of Argon2?

PBKDF2 is available in Python's `hashlib` and `cryptography` without
additional system dependencies. Argon2 requires a C extension
(`argon2-cffi`) and complicates installation on minimal Docker images.
At 100k iterations, PBKDF2-SHA256 provides adequate brute-force
resistance for a local development tool.

### Why session-based passphrase storage instead of a keyring?

The vault passphrase must survive multiple HTTP requests (for
auto-lock). Using the OS keyring would require a keyring backend
that may not exist in Docker containers or CI environments.
A module-level dict is the simplest solution that works everywhere.
The trade-off: passphrase is lost on server restart (user must
re-enter it).

### Why is secure deletion a best-effort overwrite?

True secure deletion requires knowledge of the underlying filesystem
(SSD TRIM, journaling, etc.). The 3-pass random overwrite with
`os.fsync` prevents casual recovery (e.g., `strings` on the disk)
but doesn't guarantee forensic-grade elimination. This is appropriate
for a development tool — if the user needs stronger guarantees, they
should use full-disk encryption.

### Why separate core.py from io.py?

`core.py` handles the crypto lifecycle (lock, unlock, auto-lock,
rate limiting). `io.py` handles I/O concerns (export/import,
secret file detection, .env parsing). Export uses different crypto
parameters (JSON envelope instead of raw binary) and serves a
different purpose (portable backup vs in-place encryption).

### Why does env_ops.py re-export from env_crud.py?

Historical: all env operations were in `env_ops.py`. When CRUD
operations grew large enough to split, the re-exports preserved
backward compatibility for all existing consumers. New code should
import from `env_crud` directly for clarity.

### Why escalating rate limits instead of a simple lockout?

A simple lockout after N attempts would lock out legitimate users
who mistype their passphrase. Escalating delays (5s → 30s → 2min →
10min) slow down attackers while giving legitimate users a path
to retry. The counter resets on any successful unlock.

### Why does touch_activity() filter background polls?

Without filtering, the auto-lock timer would never expire — the
dashboard polls `/api/vault/status` every 30 seconds, which would
continuously reset the inactivity timer. Only user-initiated
mutating requests (POST, not GET status checks) should count as
"activity" for auto-lock purposes.
