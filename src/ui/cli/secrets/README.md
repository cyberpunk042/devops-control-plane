# CLI Domain: Secrets — GitHub Secrets, Key Generation & Environments

> **4 files · 389 lines · 9 commands + 1 subgroup · Group: `controlplane secrets`**
>
> GitHub-integrated secrets management: check gh CLI status, auto-detect
> tokens and repository, generate secrets/keys/certificates, CRUD
> operations on GitHub secrets and variables (with optional local .env
> sync), and manage GitHub deployment environments.
>
> Core service: `core/services/secrets/ops.py` (re-exported via `secrets_ops.py`)

---

## How It Works

```
┌──────────────────────────────────────────────────────────────────────┐
│                       controlplane secrets                          │
│                                                                      │
│  ┌── Status ──────────┐  ┌── CRUD ───────────┐  ┌── Envs ───────┐ │
│  │ status             │  │ set NAME VALUE    │  │ envs list     │ │
│  │ auto-detect        │  │ remove NAME       │  │ envs create   │ │
│  │ generate [--type]  │  │ list [-e ENV]     │  │ envs cleanup  │ │
│  └────────────────────┘  └───────────────────┘  └───────────────┘ │
└──────────┬──────────────────────┬──────────────────┬──────────────┘
           │                      │                  │
           ▼                      ▼                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│                core/services/secrets/ops.py (via secrets_ops.py)    │
│                                                                      │
│  Status:                                                             │
│    gh_status()                 → installed, authenticated, version  │
│    gh_auto_detect(root)        → token, repo, saved[]              │
│    generate_key(type, len, cn) → value, public_value, private_key  │
│                                                                      │
│  CRUD:                                                               │
│    set_secret(root, name, value, target, env) → env_saved, gh_set  │
│    remove_secret(root, name, target, kind, env) → removed          │
│    list_gh_secrets(root, env)  → secrets[], variables[]            │
│                                                                      │
│  Environments:                                                       │
│    list_environments(root)     → environments[]                    │
│    create_environment(root, name) → created                        │
│    cleanup_environment(root, name, del_files, del_gh) → actions[]  │
└──────────────────────────────────────────────────────────────────────┘
```

### Dual-Target Architecture

The `set` and `remove` commands can target three locations:

```
--target local   → .env file only
--target github  → GitHub repository secrets only
--target both    → both local .env AND GitHub (default)
```

This lets users keep local development secrets in sync with GitHub
CI/CD secrets from a single command.

### Key Generation Types

The `generate` command supports multiple secret types:

| Type | What It Generates |
|------|-------------------|
| `password` | Random alphanumeric string (default 32 chars) |
| `token` | Random hex token |
| `ssh-ed25519` | Ed25519 SSH key pair (private + public) |
| `ssh-rsa` | RSA SSH key pair |
| `cert-selfsigned` | Self-signed TLS certificate + private key |

### Deployment Environments

GitHub deployment environments provide scoped secrets. The `envs`
subgroup manages these environments:

```
envs list                     → List all environments
envs create staging           → Create "staging" environment
envs cleanup staging          → Delete local .env.staging files

secrets set API_KEY xxx -e staging → Set secret scoped to "staging"
secrets list -e staging           → List secrets in "staging"
```

### Error Handling Pattern

All secrets commands use `✓`/`✗` icons (not ✅/❌ emoji) for a more
compact, terminal-friendly display. JSON output always includes
`error` key checks before sys.exit(1).

---

## Commands

### `controlplane secrets status`

Check gh CLI installation and authentication status.

```bash
controlplane secrets status
controlplane secrets status --json
```

**Output examples:**

```
  gh CLI: 2.40.0
  ✓ Authenticated
```

```
✗ gh CLI not installed
  Install: https://cli.github.com/
```

---

### `controlplane secrets auto-detect`

Auto-detect GitHub token and repository from environment.

```bash
controlplane secrets auto-detect
controlplane secrets auto-detect --json
```

**Output example:**

```
  ✓ GitHub token detected
  Repository: user/repo
  → Saved GITHUB_TOKEN to .env
  → Saved GITHUB_REPO to .env
```

---

### `controlplane secrets generate`

Generate a secret value (password, token, SSH key, certificate).

```bash
controlplane secrets generate
controlplane secrets generate --type token --length 64
controlplane secrets generate --type ssh-ed25519
controlplane secrets generate --type cert-selfsigned --cn example.com
controlplane secrets generate --json
```

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--type` | choice | password | password, token, ssh-ed25519, ssh-rsa, cert-selfsigned |
| `-l/--length` | int | 32 | Length (for password/token) |
| `--cn` | string | localhost | Common Name (for certificates) |
| `--json` | flag | off | JSON output |

**Output examples:**

```
  Generated (password):
  a8Kj2mP9xQ4nR7vL3wB6yH1eT5sD0fG
```

```
  Generated (ssh-ed25519):

  Private key (base64):
  LS0tLS1CRUdJTiBPUEVOU1NIIFBSSVZBVEUgS0VZLS0tLS0KYjNCbGJu...

  Public key:
  ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIKxyz...
```

---

### `controlplane secrets set NAME VALUE`

Set a secret in .env and/or GitHub.

```bash
# Set in both local and GitHub (default)
controlplane secrets set DATABASE_URL postgres://localhost/mydb

# GitHub only
controlplane secrets set API_KEY sk-1234 --target github

# Scoped to a deployment environment
controlplane secrets set API_KEY sk-prod --target github -e production

# JSON output
controlplane secrets set KEY value --json
```

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `NAME` | argument | (required) | Secret name |
| `VALUE` | argument | (required) | Secret value |
| `-t/--target` | choice | both | local, github, or both |
| `-e/--env-name` | string | (empty) | GitHub environment scope |
| `--json` | flag | off | JSON output |

---

### `controlplane secrets remove NAME`

Remove a secret from .env and/or GitHub.

```bash
controlplane secrets remove OLD_KEY
controlplane secrets remove OLD_KEY --target github
controlplane secrets remove OLD_VAR --kind variable
controlplane secrets remove OLD_KEY --target github -e production
```

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `NAME` | argument | (required) | Secret name |
| `-t/--target` | choice | both | local, github, or both |
| `-k/--kind` | choice | secret | secret or variable |
| `-e/--env-name` | string | (empty) | GitHub environment scope |

---

### `controlplane secrets list`

List secrets and variables set on GitHub.

```bash
controlplane secrets list
controlplane secrets list -e production
controlplane secrets list --json
```

**Output example:**

```
  🔒 Secrets (3):
     • DATABASE_URL
     • API_KEY
     • SECRET_KEY

  📋 Variables (2):
     • ENV = production
     • DEBUG = false
```

---

### `controlplane secrets envs list`

List GitHub deployment environments.

```bash
controlplane secrets envs list
controlplane secrets envs list --json
```

**Output example:**

```
  🌍 Environments (3):
     • production
     • staging
     • preview
```

---

### `controlplane secrets envs create NAME`

Create a GitHub deployment environment.

```bash
controlplane secrets envs create staging
```

---

### `controlplane secrets envs cleanup NAME`

Clean up an environment — delete local .env files and optionally remove
the GitHub environment.

```bash
controlplane secrets envs cleanup staging
controlplane secrets envs cleanup staging --delete-github
controlplane secrets envs cleanup staging --keep-files --delete-github
```

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `NAME` | argument | (required) | Environment name |
| `--delete-files/--keep-files` | flag | delete | Delete local `.env.<name>` files |
| `--delete-github/--keep-github` | flag | keep | Delete the GitHub environment too |

---

## File Map

```
cli/secrets/
├── __init__.py     35 lines — group definition, _resolve_project_root,
│                              sub-module imports (status, crud, envs)
├── status.py      111 lines — status, auto-detect, generate commands
├── crud.py        136 lines — set, remove, list commands
├── envs.py        107 lines — envs subgroup (list, create, cleanup)
└── README.md               — this file
```

**Total: 389 lines of Python across 4 files.**

---

## Per-File Documentation

### `__init__.py` — Group definition (35 lines)

| Symbol | Kind | What It Does |
|--------|------|-------------|
| `_resolve_project_root(ctx)` | helper | Reads `config_path` from context, falls back to `find_project_file()` |
| `secrets()` | Click group | Top-level `secrets` group |
| `from . import status, crud, envs` | import | Registers sub-modules |

---

### `status.py` — gh CLI + detection + key generation (111 lines)

| Symbol | Kind | What It Does |
|--------|------|-------------|
| `status(ctx, as_json)` | command | Check gh CLI installed + authenticated |
| `auto_detect(ctx, as_json)` | command (`auto-detect`) | Detect GitHub token/repo, save to .env |
| `generate(gen_type, length, cn, as_json)` | command | Generate password/token/SSH key/certificate |

**Core service imports (all lazy):**

| Import | From | Used For |
|--------|------|----------|
| `gh_status` | `secrets_ops` | CLI + auth status check |
| `gh_auto_detect` | `secrets_ops` | Token/repo auto-detection |
| `generate_key` | `secrets_ops` | Key/secret generation |

**Note on `generate`:** This command does NOT take `ctx` or use
`_resolve_project_root`. Key generation is a pure computation — no
project context needed.

**SSH/certificate output truncation:** Key material is truncated to
first 80 characters with `...` suffix. Full output is available via
`--json`.

---

### `crud.py` — Secret CRUD operations (136 lines)

| Symbol | Kind | What It Does |
|--------|------|-------------|
| `set_secret_cmd(ctx, name, value, target, env_name, as_json)` | command (`set`) | Set secret in .env and/or GitHub |
| `remove_secret_cmd(ctx, name, target, kind, env_name, as_json)` | command (`remove`) | Remove from .env and/or GitHub |
| `list_secrets_cmd(ctx, env_name, as_json)` | command (`list`) | List GitHub secrets + variables |

**Core service imports (all lazy):**

| Import | From | Used For |
|--------|------|----------|
| `set_secret` | `secrets_ops` | Dual-target secret setting |
| `remove_secret` | `secrets_ops` | Dual-target secret removal |
| `list_gh_secrets` | `secrets_ops` | GitHub secrets/variables listing |

**List polymorphic handling:** The `list` command handles secrets and
variables that come as either plain strings or dicts with `name`/`value`
keys. This accounts for different GitHub API response formats.

---

### `envs.py` — Deployment environments (107 lines)

| Symbol | Kind | What It Does |
|--------|------|-------------|
| `envs()` | Click group | `secrets envs` subgroup |
| `envs_list(ctx, as_json)` | command (`envs list`) | List deployment environments |
| `envs_create(ctx, name, as_json)` | command (`envs create`) | Create a deployment environment |
| `envs_cleanup(ctx, name, delete_files, delete_github, as_json)` | command (`envs cleanup`) | Clean up environment (local + GitHub) |

**Core service imports (all lazy):**

| Import | From | Used For |
|--------|------|----------|
| `list_environments` | `secrets_ops` | Environment listing |
| `create_environment` | `secrets_ops` | Environment creation |
| `cleanup_environment` | `secrets_ops` | Environment deletion + file cleanup |

**Cleanup safety defaults:** `--delete-files` defaults to True (local
.env files are cheap to recreate), `--delete-github` defaults to False
(GitHub environments contain secrets that can't be recovered).

---

## Dependency Graph

```
__init__.py
├── click                     ← click.group
├── core.config.loader        ← find_project_file (lazy)
└── Imports: status, crud, envs

status.py
├── click                     ← click.command
└── core.services.secrets_ops ← gh_status, gh_auto_detect,
                                 generate_key (all lazy)

crud.py
├── click                     ← click.command
└── core.services.secrets_ops ← set_secret, remove_secret,
                                 list_gh_secrets (all lazy)

envs.py
├── click                     ← click.group, click.command
└── core.services.secrets_ops ← list_environments, create_environment,
                                 cleanup_environment (all lazy)
```

---

## Consumers

### Who registers this CLI group

| Layer | Module | What It Does |
|-------|--------|-------------|
| CLI entry | `src/main.py:452` | `from src.ui.cli.secrets import secrets` |

### Who also uses the same core service

| Layer | Module | Core Service Used |
|-------|--------|------------------|
| Web | `web/helpers.py:48` | `secrets_ops.fresh_env` (environment refresh) |

---

## Design Decisions

### Why set/remove default to `--target both`

Most users want their secrets in both places: `.env` for local
development, GitHub for CI/CD. Making `both` the default reduces
friction. Users who only want one target can override with `-t local`
or `-t github`.

### Why `remove` distinguishes `--kind secret` vs `--kind variable`

GitHub treats secrets and variables differently at the API level.
Secrets are encrypted and write-only; variables are plaintext and
readable. The `--kind` flag maps to different GitHub API endpoints.

### Why `generate` doesn't use project context

Key generation is a pure computation: random bytes → formatted output.
No project files are needed. This makes `generate` usable outside
a project directory.

### Why cleanup defaults differ for files vs GitHub

Local `.env.staging` files can be regenerated from `.env.example` or
the `infra env` commands. GitHub environments contain secrets that may
be impossible to recover if deleted. The asymmetric defaults protect
against accidental secret loss.

### Why `list` explicitly handles string vs dict format

The GitHub API returns secrets as strings (just names, since values
are encrypted) but variables as objects with `name` and `value`. The
list command handles both formats gracefully for a uniform display.
