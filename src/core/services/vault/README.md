# Vault Domain

> The secrets safe for the devops control plane.
> Encrypts sensitive files at rest using AES-256-GCM, manages
> passphrase sessions with auto-lock timers, rate-limits unlock
> attempts, and provides a full .env file management stack —
> from key CRUD to template-based creation to multi-environment
> activation.

---

## How It Works

The vault has two distinct halves — **crypto** (encrypt/decrypt files)
and **env management** (read/write/organize `.env` files). They're
related because the primary thing being encrypted IS the `.env` file,
but they serve different UX flows.

### Crypto Flow — Lock & Unlock

When a user locks a secret file, the vault encrypts the plaintext,
overwrites the original with random data (3-pass), and deletes it.
Only the `.vault` file remains. To get the plaintext back, the user
provides the passphrase, and the vault decrypts + deletes the
`.vault` file.

```
User clicks "Lock"
      │
      ▼
  lock_vault(secret_path, passphrase)
      │
      ├── 1. Read plaintext bytes
      ├── 2. Generate random salt (16B) + IV (12B)
      ├── 3. Derive AES-256 key via PBKDF2-SHA256 (100K iterations)
      ├── 4. Encrypt with AES-256-GCM → ciphertext + auth tag
      ├── 5. Write JSON envelope to .env.vault
      ├── 6. Secure-delete plaintext (3-pass random overwrite)
      ├── 7. Store passphrase in memory (for auto-lock later)
      └── 8. Start/reset inactivity timer
```

The passphrase is held in an in-memory dict (`_session_passphrases`)
keyed by resolved file path. This means:

- **Each vault can have its own passphrase** — the `.env` file and
  a `secrets.yml` file can use different passwords
- **Auto-lock re-encrypts everything** — when the timer fires after
  30 minutes of inactivity, it iterates every stored passphrase and
  locks each file
- **Server restart clears all passphrases** — no persistence. The
  user must unlock again.

### Rate Limiting — Progressive Lockout

Failed unlock attempts trigger escalating lockouts:

| Attempts | Lockout |
|----------|---------|
| 3 | 30 seconds |
| 6 | 5 minutes |
| 10 | 15 minutes |

The rate limiter resets on a successful unlock. This prevents brute
forcing the passphrase via the web UI.

### Export/Import — Portable Backups

Export creates a JSON envelope with **higher** KDF iterations
(600K vs 100K) because exported files may be stored on disk
indefinitely and attacked offline. The export leaves the original
file untouched — it's a copy operation, not a lock.

### .env Management — The Other Half

The vault also manages `.env` files as structured documents:

1. **Detection** — scan the project for known secret file patterns
   (`.env`, `.env.production`, `secrets.yml`, etc.)
2. **Parsing** — read `.env` into keys with masked values, metadata
   tags (`@type:toggle`, `@generated:password`), and section grouping
3. **CRUD** — add/update/delete keys, move between sections, rename
   sections, toggle `# local-only` markers
4. **Classification** — each key is classified as `secret` or `config`
   using the `classify_key()` function from the data layer
5. **Templates** — create new `.env` files from predefined template
   sections (Content Vault, OAuth, Email, etc.)
6. **Multi-environment** — activate different `.env.{name}` files by
   swapping them into `.env` (with vault file handling)

---

## File Map

```
vault/
├── __init__.py     Public API re-exports
├── core.py         Crypto engine — lock/unlock, session, auto-lock, rate limiting (530 lines)
├── io.py           Export/import envelopes, secret detection, .env parsing (520 lines)
├── env_ops.py      .env file operations — activation, enriched listing, templates (445 lines)
├── env_crud.py     .env key CRUD — add/update/delete, sections, metadata (425 lines)
└── README.md       This file
```

### `core.py` — The Crypto Engine (530 lines)

Everything that touches `cryptography` or manages passphrase state
lives here. This is the security-critical module.

| Function | What It Does |
|----------|-------------|
| `lock_vault()` | Encrypt file → JSON envelope, secure-delete plaintext |
| `unlock_vault()` | Decrypt envelope → restore plaintext, delete envelope |
| `auto_lock()` | Lock ALL unlocked vaults using stored passphrases |
| `register_passphrase()` | Store passphrase without locking (for auto-lock) |
| `vault_status()` | Check locked/unlocked state + rate limit info |
| `set_auto_lock_minutes()` | Configure inactivity timeout (0 = disabled) |
| `touch_activity()` | Reset timer on user-initiated requests |
| `get_passphrase()` | Return stored passphrase for a file (or None) |
| `has_any_passphrase()` | Quick check: is anything unlocked? |

### `io.py` — Export/Import + Parsing (520 lines)

Two concerns in one file because they share the crypto constants
and the `_vault_path_for()` helper. The parsing functions are consumed
by `env_ops.py` for enriched key listing.

| Function | What It Does |
|----------|-------------|
| `export_vault_file()` | Create downloadable encrypted envelope (600K KDF) |
| `import_vault_file()` | Decrypt envelope, optionally write to disk (with diff) |
| `detect_secret_files()` | Scan project root for secret file patterns |
| `list_env_keys()` | Parse `.env` → keys with masked values + metadata |
| `list_env_sections()` | Parse `.env` → grouped sections with keys |
| `_parse_meta_tags()` | Parse `@type:toggle @encoding:base64` comment tags |

### `env_ops.py` — File Operations (445 lines)

Higher-level operations that compose parsing + classification.
Manages environment activation (file swapping) and template-based
file creation.

| Function | What It Does |
|----------|-------------|
| `list_keys_enriched()` | Keys + classification (`secret`/`config`) + raw values |
| `activate_env()` | Swap `.env` ↔ `.env.{name}` with vault handling |
| `read_active_env()` | Which environment is currently active? |
| `create_env()` | Generate `.env` from templates and/or custom entries |
| `get_templates()` | Available template sections for the UI |
| `read_env_values()` | Raw key→value dict from `.env` |

### `env_crud.py` — Key CRUD (425 lines)

The lowest-level .env file mutations. Each function reads the file,
modifies the relevant lines, writes back, and records an audit event.

| Function | What It Does |
|----------|-------------|
| `add_keys()` | Add/update key-value pairs (with section targeting) |
| `update_key()` | Update a single key's value |
| `delete_key()` | Remove a key |
| `get_raw_value()` | Read unmasked value of a single key |
| `move_key()` | Move a key from one section to another |
| `rename_section()` | Rename a section comment header |
| `toggle_local_only()` | Toggle `# local-only` marker |
| `set_meta()` | Set/update `@` metadata comment tags |

---

## Dependency Graph

```
core.py        standalone — only depends on cryptography + audit_helpers
   ↑
io.py          imports crypto constants + _vault_path_for from core.py
   ↑
env_ops.py     imports _vault_path_for from core.py (lazy)
   │           imports list_env_keys, list_env_sections from io.py (lazy)
   │           imports classify_key from data layer
   │           re-exports env_crud at module bottom
   ↑
env_crud.py    imports _find_section_end, _write_env, read_env_values from env_ops.py
```

`core.py` is the foundation. `io.py` depends on core for crypto
constants. `env_ops.py` and `env_crud.py` have a mutual dependency
managed via lazy imports and bottom-of-file re-exports — the same
pattern as the original files.

---

## Security Invariants

| Invariant | Implementation |
|-----------|---------------|
| Passphrase never on disk | Held only in `_session_passphrases` dict, cleared on server stop |
| Secure delete before unlink | 3-pass random overwrite via `_secure_delete()` |
| Rate limiting on unlock | Progressive lockout: 30s → 5min → 15min |
| Higher KDF for exports | 600K iterations (vs 100K for in-place lock) |
| Thread-safe state access | `threading.Lock` guards `_session_passphrases` |
| Lazy crypto imports | `cryptography` only imported inside functions that use it |
| Auto-lock on inactivity | Timer fires after configurable minutes (default: 30) |

---

## Backward Compatibility

The original files are now thin shims that re-export from this package:

| Old path | Re-exports from |
|----------|----------------|
| `services/vault.py` | Package resolution → `vault/__init__.py` (Python prefers directory) |
| `services/vault_io.py` | `vault/io.py` |
| `services/vault_env_ops.py` | `vault/env_ops.py` (including env_crud re-exports) |
| `services/vault_env_crud.py` | `vault/env_crud.py` |

For new code, import from the package:

```python
# ✅ Package-level — most convenient
from src.core.services.vault import vault_status, lock_vault, detect_secret_files

# ✅ Specific submodule — when you want to be explicit
from src.core.services.vault.core import vault_status
from src.core.services.vault.env_ops import list_keys_enriched

# ⚠️ Legacy shim — still works, avoid in new code
from src.core.services.vault_io import detect_secret_files
```

---

## Consumers

| Consumer | What It Uses | Import Pattern |
|----------|-------------|----------------|
| `routes_vault.py` | All vault + env_ops functions | `from src.core.services import vault, vault_env_ops` |
| `ui/cli/vault.py` | lock, unlock, status, export, create, add, update, delete | Individual function imports |
| `security_posture.py` | `vault_status` | Lazy import inside function |
| `env_infra_ops.py` | `list_env_keys` | Lazy import inside function |

---

## API Endpoints

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/vault/status` | GET | Vault status (locked/unlocked + rate limit info) |
| `/api/vault/lock` | POST | Encrypt + secure-delete plaintext |
| `/api/vault/unlock` | POST | Decrypt + restore plaintext |
| `/api/vault/register` | POST | Store passphrase for auto-lock |
| `/api/vault/auto-lock` | POST | Configure auto-lock timeout |
| `/api/vault/secrets` | GET | List detected secret files |
| `/api/vault/keys` | GET | Enriched key listing with classification |
| `/api/vault/templates` | GET | Available .env template sections |
| `/api/vault/create` | POST | Create new .env from templates |
| `/api/vault/add-keys` | POST | Add/update keys |
| `/api/vault/update-key` | POST | Update single key value |
| `/api/vault/delete-key` | POST | Delete a key |
| `/api/vault/active-env` | GET | Which environment is active |
| `/api/vault/activate-env` | POST | Switch active environment |
| `/api/vault/export` | POST | Download encrypted envelope |
| `/api/vault/import` | POST | Upload + decrypt envelope |
