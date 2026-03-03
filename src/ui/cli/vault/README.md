# CLI Domain: Vault — Encrypt, Decrypt, .env Management & Environment Switching

> **4 files · 404 lines · 11 commands · Group: `controlplane vault`**
>
> Secrets vault lifecycle: detect secret files, encrypt/decrypt files with
> passphrase-based encryption (lock/unlock), check vault status, export
> vault files as portable JSON, manage .env keys (list, add, update,
> delete), create .env files from template sections, and switch active
> environments by swapping .env files.
>
> Core services: `core/services/vault.py` + `core/services/vault_io.py` +
> `core/services/vault_env_ops.py`

---

## How It Works

```
┌──────────────────────────────────────────────────────────────────────┐
│                         controlplane vault                          │
│                                                                      │
│  ┌── Detect ──┐  ┌── Crypto ──────────┐  ┌── Env Mgmt ───────────┐│
│  │ detect     │  │ lock FILE -p       │  │ keys [--env]           ││
│  └────────────┘  │ unlock FILE -p     │  │ templates              ││
│                   │ status FILE        │  │ create [--env] [-t]    ││
│                   │ export FILE -p     │  │ add-key KEY [VAL]      ││
│                   └────────────────────┘  │ update-key KEY VAL     ││
│                                            │ delete-key KEY         ││
│                                            │ activate NAME          ││
│                                            └────────────────────────┘│
└──────────┬──────────────────────┬──────────────────┬───────────────┘
           │                      │                  │
           ▼                      ▼                  ▼
┌───────────────────┐  ┌──────────────────┐  ┌────────────────────────┐
│ vault_io.py       │  │ vault.py         │  │ vault_env_ops.py       │
│                   │  │                  │  │                        │
│ detect_secret_    │  │ lock_vault()     │  │ list_keys_enriched()   │
│   files(root)     │  │ unlock_vault()   │  │ get_templates()        │
│ export_vault_     │  │ vault_status()   │  │ create_env()           │
│   file(path, pp)  │  │                  │  │ add_keys()             │
└───────────────────┘  └──────────────────┘  │ update_key()           │
                                              │ delete_key()           │
                                              │ activate_env()         │
                                              └────────────────────────┘
```

### Encryption Model

The vault uses passphrase-based symmetric encryption. Files live in
two states:

```
plaintext (.env)  ←→  encrypted (.env.vault)
                lock ─────→
                ←───── unlock
```

- **lock**: read plaintext file → encrypt with passphrase → write `.vault` file
- **unlock**: read `.vault` file → decrypt with passphrase → restore plaintext
- **status**: check whether the vault file exists and its state

### Detect vs Security Scan

`vault detect` and `security files` both find secret files, but with
different purposes:
- `vault detect` uses `vault_io.detect_secret_files()` — looks for
  files that can be managed by the vault (encrypted/decrypted)
- `security files` uses `security_ops.detect_sensitive_files()` — checks
  whether sensitive files are protected by `.gitignore`

### Environment Management

The vault manages `.env` files with section-aware structure:

```
# ── Database ──
DATABASE_URL=postgres://localhost/mydb
DATABASE_POOL=5

# ── API Keys ──
API_KEY=sk-1234
WEBHOOK_SECRET=whsec_...
```

The `keys` command understands this structure and shows:
- Key name, masked value, kind (secret vs variable), local-only flag
- Section boundaries

### Template System

Templates are pre-defined .env section blueprints:

```
templates list:
├── content_vault   → VAULT_PASSPHRASE, VAULT_KEY
├── database        → DATABASE_URL, DATABASE_POOL, DATABASE_SSL
├── api_keys        → API_KEY, WEBHOOK_SECRET
├── cloud_aws       → AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION
└── (etc.)

create --template database --template api_keys:
→ Generates .env with both sections pre-populated
```

### Environment Activation

The `activate` command implements environment switching:

```
activate production:
1. Save current .env → .env.<old>
2. Copy .env.production → .env
3. Write .env.active marker with current env name
4. Reload vault module state
```

This allows zero-downtime environment switching for local development.

---

## Commands

### `controlplane vault detect`

Scan project for secret files (.env, credentials, keys).

```bash
controlplane vault detect
controlplane vault detect --json
```

**Output example:**

```
🔍 Found 3 secret file(s):
   • .env [unlocked]
   • .env.production [locked]
   • credentials.json
```

---

### `controlplane vault lock FILE`

Encrypt a secret file (lock it into the vault).

```bash
controlplane vault lock .env -p mypassphrase
controlplane vault lock .env
# (prompts for passphrase with hidden input)
```

**Output:** `"✅ Locked: .env"` + vault file path

---

### `controlplane vault unlock FILE`

Decrypt a vault file (unlock it back to plaintext).

```bash
controlplane vault unlock .env.vault -p mypassphrase
controlplane vault unlock .env.vault
# (prompts for passphrase)
```

**Output:** `"✅ Unlocked: .env.vault"` + plaintext path

**Error on wrong passphrase:** `"❌ <ValueError message>"`

---

### `controlplane vault status FILE`

Check vault status for a secret file.

```bash
controlplane vault status .env
```

**Output examples:**

```
🔒 .env: locked
   Vault file: .env.vault
```

```
🔓 .env: unlocked
   Vault file: .env.vault
```

```
❓ .env: missing
```

---

### `controlplane vault export FILE`

Export a vault file as a portable JSON envelope.

```bash
controlplane vault export .env.vault -p mypassphrase
controlplane vault export .env.vault --json
```

**Output:**

```
✅ Exported: .env.vault
   Format: json
   Entries: 12
```

---

### `controlplane vault keys`

List .env keys with masked values.

```bash
controlplane vault keys
controlplane vault keys --env production
controlplane vault keys --json
```

**Output example:**

```
🔑 Keys (6):
   🔒 DATABASE_URL                    = post**** 📌
   🔒 API_KEY                         = sk-1****
   📋 DEBUG                           = true
   📋 LOG_LEVEL                       = info
   🔒 WEBHOOK_SECRET                  = whse****
   📋 PORT                            = 8080

📂 Sections:
   • Database (2 keys)
   • API Keys (2 keys)
   • Config (2 keys)
```

**Icons:**
- `🔒` — secret value (masked)
- `📋` — variable (non-secret)
- `📌` — local-only key (not in templates)

**Vault locked:** `"🔒 Vault is locked — unlock first."`

---

### `controlplane vault templates`

Show available .env template sections.

```bash
controlplane vault templates
controlplane vault templates --json
```

**Output example:**

```
📋 Available templates:
   • content_vault        Content Vault
     VAULT_PASSPHRASE, VAULT_KEY
   • database             Database
     DATABASE_URL, DATABASE_POOL, DATABASE_SSL
   • api_keys             API Keys
     API_KEY, WEBHOOK_SECRET, API_BASE_URL +1 more
```

---

### `controlplane vault create`

Create a new .env file from template sections.

```bash
controlplane vault create --template database --template api_keys
controlplane vault create --env production -t database -t cloud_aws
controlplane vault create --json
```

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--env` | string | (empty) | Environment name (creates `.env.<name>`) |
| `-t/--template` | string | (repeatable) | Template section IDs to include |
| `--json` | flag | off | JSON output |

---

### `controlplane vault add-key KEY [VALUE]`

Add a key-value pair to the .env file.

```bash
controlplane vault add-key DATABASE_URL postgres://localhost/mydb
controlplane vault add-key API_KEY sk-1234 --section "API Keys"
controlplane vault add-key NEW_KEY --env production
```

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `KEY` | argument | (required) | Key name |
| `VALUE` | argument | (optional) | Key value (empty default) |
| `--env` | string | (empty) | Environment name |
| `-s/--section` | string | (empty) | Section to add under |

---

### `controlplane vault update-key KEY VALUE`

Update a key's value in the .env file.

```bash
controlplane vault update-key DATABASE_URL postgres://prod/mydb
controlplane vault update-key API_KEY sk-5678 --env staging
```

---

### `controlplane vault delete-key KEY`

Remove a key from the .env file.

```bash
controlplane vault delete-key OLD_KEY
controlplane vault delete-key OLD_KEY --env production
```

---

### `controlplane vault activate NAME`

Switch the active environment by swapping .env files.

```bash
controlplane vault activate production
controlplane vault activate staging --json
```

---

## File Map

```
cli/vault/
├── __init__.py     43 lines — group definition, _resolve_project_root,
│                              _env_path helper, sub-module imports
├── detect.py       39 lines — detect command (secret file scanning)
├── crypto.py      102 lines — lock, unlock, status, export commands
├── env_mgmt.py    220 lines — keys, templates, create, add/update/delete,
│                              activate commands
└── README.md               — this file
```

**Total: 404 lines of Python across 4 files.**

---

## Per-File Documentation

### `__init__.py` — Group + helpers (43 lines)

| Symbol | Kind | What It Does |
|--------|------|-------------|
| `_resolve_project_root(ctx)` | helper | Reads `config_path` from context, falls back to `find_project_file()` |
| `_env_path(project_root, env_name)` | helper | Returns `.env` or `.env.<name>` path |
| `vault()` | Click group | Top-level `vault` group |
| `from . import crypto, detect, env_mgmt` | import | Registers sub-modules |

**`_env_path` helper:** Unique to the vault domain. Centralizes the
pattern of resolving `.env.production` vs `.env` from an optional
environment name parameter.

---

### `detect.py` — Secret file detection (39 lines)

| Symbol | Kind | What It Does |
|--------|------|-------------|
| `detect_secrets(ctx, as_json)` | command (`detect`) | Scan project for manageable secret files |

**Core service import (lazy):**

| Import | From | Used For |
|--------|------|----------|
| `detect_secret_files` | `vault_io` | Secret file discovery |

**Polymorphic result handling:** The result can be either a list
(old API) or a dict with `files` key (new API). The command handles
both formats.

---

### `crypto.py` — Encryption operations (102 lines)

| Symbol | Kind | What It Does |
|--------|------|-------------|
| `lock(ctx, file, passphrase)` | command | Encrypt file → `.vault` |
| `unlock(ctx, file, passphrase)` | command | Decrypt `.vault` → plaintext |
| `status(ctx, file)` | command | Check lock/unlock state |
| `export(ctx, file, passphrase, as_json)` | command | Export as portable JSON |

**Core service imports (all lazy):**

| Import | From | Used For |
|--------|------|----------|
| `lock_vault` | `vault` | File encryption |
| `unlock_vault` | `vault` | File decryption |
| `vault_status` | `vault` | State checking |
| `export_vault_file` | `vault_io` | Portable JSON export |

**Passphrase handling:** Both `lock` and `unlock` use Click's
`prompt=True, hide_input=True` for interactive passphrase entry.
The `-p` option allows non-interactive usage (scripts/CI).

**Multi-exception handling in `unlock`:**
- `FileNotFoundError` → vault file doesn't exist
- `ValueError` → wrong passphrase (decryption failed)
- `Exception` → catch-all for unexpected errors

---

### `env_mgmt.py` — .env key management (220 lines)

| Symbol | Kind | What It Does |
|--------|------|-------------|
| `list_keys(ctx, env_name, as_json)` | command (`keys`) | List .env keys with masked values |
| `list_templates(as_json)` | command (`templates`) | Show available template sections |
| `create_env(ctx, env_name, templates, as_json)` | command (`create`) | Create .env from template sections |
| `add_key(ctx, key, value, env_name, section)` | command (`add-key`) | Add key to .env |
| `update_key_cmd(ctx, key, value, env_name)` | command (`update-key`) | Update existing key value |
| `delete_key_cmd(ctx, key, env_name)` | command (`delete-key`) | Remove key from .env |
| `activate_env(ctx, name, as_json)` | command (`activate`) | Switch active environment |

**Core service imports (all lazy):**

| Import | From | Used For |
|--------|------|----------|
| `vault_env_ops.list_keys_enriched` | `vault_env_ops` | Key listing with masking |
| `vault_env_ops.get_templates` | `vault_env_ops` | Template section listing |
| `vault_env_ops.create_env` | `vault_env_ops` | .env file creation |
| `vault_env_ops.add_keys` | `vault_env_ops` | Key addition |
| `vault_env_ops.update_key` | `vault_env_ops` | Key value update |
| `vault_env_ops.delete_key` | `vault_env_ops` | Key removal |
| `vault_env_ops.activate_env` | `vault_env_ops` | Environment switching |
| `vault` (web module) | `src.ui.web.vault` | Vault module state reload |

**`activate` web module import:** This is the only CLI command that
imports from `src.ui.web`. The `activate_env` core function accepts
`vault_module` to reload vault state after environment switching.

**Template preview truncation:** The `templates` command shows at most
3 keys per section. If more, shows `+N more`.

---

## Dependency Graph

```
__init__.py
├── click                     ← click.group
├── core.config.loader        ← find_project_file (lazy)
└── Imports: crypto, detect, env_mgmt

detect.py
├── click                     ← click.command
└── core.services.vault_io    ← detect_secret_files (lazy)

crypto.py
├── click                     ← click.command
├── core.services.vault       ← lock_vault, unlock_vault,
│                                vault_status (all lazy)
└── core.services.vault_io    ← export_vault_file (lazy)

env_mgmt.py
├── click                     ← click.command
├── core.services.vault_env_ops ← list_keys_enriched, get_templates,
│                                  create_env, add_keys, update_key,
│                                  delete_key, activate_env (all lazy)
└── ui.web.vault              ← vault module (for activate)
```

**Three core services:** Vault is the only CLI domain that imports from
three separate core service modules (`vault`, `vault_io`, `vault_env_ops`).

---

## Consumers

### Who registers this CLI group

| Layer | Module | What It Does |
|-------|--------|-------------|
| CLI entry | `src/main.py:447` | `from src.ui.cli.vault import vault` |

### Who also uses the same core services

| Layer | Module | Core Service Used |
|-------|--------|------------------|
| Core | `security/posture.py:181` | `vault.vault_status` (security scoring) |
| Core | `env/infra_ops.py:194` | `vault_io.list_env_keys` (env detection) |

---

## Design Decisions

### Why vault uses three core service modules

Each module has a distinct responsibility:
- `vault.py` — pure cryptographic operations (lock, unlock, status)
- `vault_io.py` — file I/O operations (detect files, export)
- `vault_env_ops.py` — .env structure management (keys, templates, sections)

### Why `lock`/`unlock` use prompt-based passphrase

Passphrases should never appear in shell history. Click's `prompt=True,
hide_input=True` reads from stdin without echoing. The `-p` flag is
available for scripted/CI usage where security is handled differently.

### Why `keys` shows masked values

Displaying full secret values in the terminal is a security risk
(shoulder surfing, screen recording, terminal logs). Masking shows
enough to confirm the correct secret is set.

### Why `activate` imports from `ui.web`

Environment switching needs to reload the web module's in-memory
vault state. Without this, the web admin panel would show stale
secrets until server restart. This is a necessary layering violation.

### Why `add-key` value argument is optional

Sometimes you want to add a placeholder key with an empty value
(e.g., `add-key NEW_API_KEY`) and fill in the value later. Making
the value optional supports this workflow.
