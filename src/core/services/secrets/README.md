# Secrets Domain

> **4 files · 941 lines · GitHub secrets/variables sync, key generation, and environment management.**
>
> Bridges local `.env` files with GitHub Actions secrets and variables.
> Handles key classification, generation, bulk push/sync, single-key operations,
> and deployment environment lifecycle.

---

## How It Works

The secrets domain has three concerns, each in its own module:

### 1. Core Operations — Helpers, Detection, Generation

`ops.py` provides the shared foundation:

```
   .env file                            gh CLI
      │                                    │
      ├── fresh_env(root)                  ├── gh_status()
      │   Read .env → merge with           │   → {installed, authenticated}
      │   os.environ for subprocess        │
      │                                    ├── gh_auto_detect(root)
      ├── env_path_for(root, name)         │   → {token, repo}
      │   .env | .env.<name>               │
      │                                    └── gh_repo_flag(root)
      ├── read_env_values(path)                → ["-R", "owner/repo"]
      │   → {KEY: "value", ...}
      │
      └── classify_key(name)               (re-exported from data layer)
          → "secret" | "config" | "internal"
```

**Key classification** determines whether a key is pushed as a GitHub
secret (encrypted, never readable) or a GitHub variable (plaintext,
readable by workflows):

| Classification | Pattern | GitHub Target |
|---------------|---------|---------------|
| `secret` | Contains: KEY, SECRET, TOKEN, PASSWORD, PRIVATE, CREDENTIAL | `gh secret set` |
| `config` | Contains: URL, HOST, PORT, NAME, ENV, MODE, LEVEL, REGION | `gh variable set` |
| `internal` | Starts with `_` or `GITHUB_` prefix | Excluded from GitHub push |

**Key generators** create cryptographic values:

| Generator | Method | Output |
|-----------|--------|--------|
| `password` | Random from `[a-zA-Z0-9!@#$%^&*]` | Raw string (8–256 chars) |
| `token` | `secrets.token_urlsafe()` | URL-safe base64 string |
| `ssh-ed25519` | `ssh-keygen -t ed25519` | Base64 private + plaintext public |
| `ssh-rsa` | `ssh-keygen -t rsa -b 4096` | Base64 private + plaintext public |
| `cert-selfsigned` | `openssl req -x509 -newkey ec` | Base64 cert + base64 key |

### 2. GitHub Secrets & Variables — Sync with GitHub

`gh_ops.py` manages the bidirectional bridge between `.env` files and
GitHub Actions secrets/variables:

```
LOCAL (.env file)                      GITHUB (secrets & variables)
  KEY=value                              gh secret set KEY
  CONFIG_VAR=value                       gh variable set CONFIG_VAR
      │                                         │
      │  push_secrets()                         │
      │  ───────────────────────────────────►   │
      │                                         │
      │  list_gh_secrets()                      │
      │  ◄───────────────────────────────────   │
      │                                         │
      │  set_secret(target="both")              │
      │  ─────────── local ─────────────►       │
      │  ─────────── github ────────────►       │
      │                                         │
      │  remove_secret(target="both")           │
      │  ─────────── local ─────────────►       │
      │  ─────────── github ────────────►       │
```

**Dual-target architecture:** Each operation can target `local` (.env),
`github` (Actions), or `both` — giving users fine-grained control over
where secrets are stored.

### 3. Deployment Environments — GitHub Env Lifecycle

`env_ops.py` manages GitHub deployment environments:

```
Multi-Environment Lifecycle

  seed_environments(root, ["staging", "production"])
      │
      ├── Copy .env → .env.staging
      ├── Copy .env → .env.production
      ├── Copy .env.vault → .env.staging.vault
      ├── Copy .env.vault → .env.production.vault
      └── Write .env.active = "staging"

  create_environment(root, "production")
      └── gh api -X PUT repos/{repo}/environments/production

  cleanup_environment(root, "staging")
      ├── Delete .env.staging
      ├── Delete .env.staging.vault
      └── Optionally delete GitHub environment
```

---

## Key Data Shapes

### gh_status response

```python
# gh CLI available and authenticated
{"installed": True, "authenticated": True}

# gh CLI not installed
{"installed": False, "authenticated": False}

# gh CLI installed but not authenticated
{"installed": True, "authenticated": False}
```

### gh_auto_detect response

```python
{
    "token": "gho_xxxxxxxxxxxx",      # from `gh auth token`
    "repo": "owner/repo-name",       # from `git remote get-url origin`
}

# No GitHub setup
{"token": None, "repo": None}
```

### list_gh_secrets response

```python
# Success
{
    "available": True,
    "secrets": ["DATABASE_URL", "JWT_SECRET", "AWS_ACCESS_KEY_ID"],
    "variables": ["NODE_ENV", "API_BASE_URL", "LOG_LEVEL"],
    "scoped_to": "repo",             # "repo" | environment name
}

# gh CLI not installed
{
    "available": False,
    "reason": "gh CLI not installed",
    "secrets": [],
    "variables": [],
}

# Not authenticated
{
    "available": False,
    "reason": "gh CLI not authenticated",
    "secrets": [],
    "variables": [],
}
```

### set_secret response

```python
{
    "name": "DATABASE_URL",
    "local": {"success": True},
    "github": {
        "success": True,
        "error": None,
    },
}
```

### remove_secret response

```python
{
    "name": "OLD_KEY",
    "local": {"success": True},
    "github": {
        "success": True,
        "error": None,
    },
}
```

### push_secrets response

```python
# Full push
{
    "env_saved": True,
    "deletions_applied": ["DEPRECATED_KEY"],
    "results": [
        {"name": "DATABASE_URL", "kind": "secret", "success": True, "error": None},
        {"name": "NODE_ENV", "kind": "variable", "success": True, "error": None},
    ],
    "all_success": True,
    "pushed": ["DATABASE_URL", "NODE_ENV"],
}

# gh CLI not available
{
    "env_saved": True,
    "error": "gh CLI not installed",
    "results": [],
    "all_success": False,
}
```

### generate_key response

```python
# Password
{
    "type": "password",
    "value": "xK9$mP2@rL5...",
    "base64": False,
    "meta_tags": "@type:password @generated:password @length:32",
}

# SSH key
{
    "type": "ssh-ed25519",
    "value": "<base64 private key>",
    "public_value": "ssh-ed25519 AAAA... generated-by-devops-control-plane",
    "base64": True,
    "meta_tags": "@encoding:base64 @generated:ssh-ed25519",
}

# Self-signed certificate
{
    "type": "cert-selfsigned",
    "value": "<base64 certificate>",
    "private_key": "<base64 private key>",
    "base64": True,
    "meta_tags": "@encoding:base64 @generated:cert-selfsigned",
}
```

### list_environments response

```python
# Success
{
    "available": True,
    "environments": ["staging", "production"],
    "reason": None,
}

# No environments configured
{
    "available": True,
    "environments": [],
    "reason": None,
}

# No GitHub repository
{
    "available": False,
    "environments": [],
    "reason": "GITHUB_REPOSITORY not configured",
}
```

### seed_environments response

```python
{
    "seeded": ["staging", "production"],
    "skipped": ["development"],        # already existed
    "active": "staging",               # from default parameter
}
```

---

## Architecture

```
                  CLI (ui/cli/secrets.py)
                  Routes (routes/secrets/)
                         │
                         │ imports
                         │
              ┌──────────▼──────────┐
              │  secrets_ops.py     │  backward-compat shim
              │  (re-exports all)   │  → imports from secrets/
              └──────────┬──────────┘
                         │
              ┌──────────▼──────────────────────────────┐
              │  secrets/__init__.py                      │
              │  Public API — re-exports all symbols      │
              └────┬──────────┬──────────┬───────────────┘
                   │          │          │
          ┌────────┘          │          └──────────┐
          ▼                   ▼                     ▼
       ops.py             gh_ops.py             env_ops.py
     (helpers,          (list, set,          (environments,
      detection,         remove, push          create, seed,
      generators)        secrets/vars)         cleanup)
```

### Dependency Rules

| Rule | Detail |
|------|--------|
| `ops.py` is the base | Helpers used by both other modules |
| `gh_ops.py` imports `ops` | Uses `fresh_env`, `gh_repo_flag`, `env_path_for`, `classify_key` |
| `env_ops.py` imports `ops` | Uses `gh_repo_flag`, `env_path_for` |
| `gh_ops.py` and `env_ops.py` are independent | No cross-imports |

---

## File Map

```
secrets/
├── __init__.py      Public API re-exports (38 lines)
├── ops.py           Helpers, gh CLI status, key generators (256 lines)
├── gh_ops.py        GitHub secrets & variables management (442 lines)
├── env_ops.py       Deployment environment management (205 lines)
└── README.md        This file
```

---

## Per-File Documentation

### `ops.py` — Core Helpers & Generators (256 lines)

| Section | Function | Purpose |
|---------|----------|---------|
| **Helpers** | `fresh_env(root)` | Build subprocess env with .env values merged |
| **Helpers** | `gh_repo_flag(root)` | Get `["-R", "owner/repo"]` for gh commands |
| **Helpers** | `env_path_for(root, env_name)` | Resolve `.env` or `.env.<name>` path |
| **Helpers** | `read_env_values(path)` | Parse .env → `{KEY: "value"}` dict |
| **Detection** | `gh_status()` | Check gh CLI installed + authenticated |
| **Detection** | `gh_auto_detect(root)` | Get token + detect repo from git remote |
| **Generators** | `generate_key(type, length, cn)` | Generate password, token, SSH key, or cert |

**`fresh_env` quirks:** Strips quotes from .env values (single or double),
merges on top of `os.environ`, forces `TERM=dumb` (prevents escape codes
in gh CLI output).

**`read_env_values` rules:**
- Skips blank lines and `#` comments
- Strips `# local-only` suffix before parsing value
- Strips surrounding quotes (single or double)
- Returns `{key: value}` dict

### `gh_ops.py` — GitHub Secrets & Variables (442 lines)

| Function | What It Does | Audited |
|----------|-------------|---------|
| `list_gh_secrets(root, env_name)` | List secrets + variables from GitHub | No |
| `set_secret(root, name, value, target, env_name)` | Set single secret/variable | ✅ |
| `remove_secret(root, name, target, kind, env_name)` | Remove secret/variable | ✅ |
| `push_secrets(root, *, secrets_dict, variables, ...)` | Bulk push to GitHub + .env | ✅ |

**`push_secrets` flow (the most complex function):**

```
push_secrets(root, secrets_dict, variables, env_values,
             deletions, sync_keys, push_to_github, save_to_env,
             exclude_from_github, env_name)
    │
    ├── 1. Merge sync_keys: read from .env, classify, add to maps
    │      (sync_keys reads live .env values for GitHub sync)
    │
    ├── 2. Save to .env (if save_to_env):
    │      ├── Read existing lines
    │      ├── Update existing KEY=value lines in-place
    │      ├── Append new keys
    │      ├── Delete keys in deletions list
    │      └── Write back with trailing newline
    │
    └── 3. Push to GitHub (if push_to_github):
           ├── Verify gh auth status
           ├── Push secrets_map → gh secret set
           ├── Push vars_map → gh variable set
           │   (skip GITHUB_* and excluded keys)
           └── Collect per-key success/failure results
```

**Exclude rules for GitHub push:**
- Keys starting with `GITHUB_` — GitHub's own namespace
- Keys in `exclude_from_github` set — user-specified exclusions
- Empty values — skipped silently

### `env_ops.py` — Deployment Environments (205 lines)

| Function | What It Does | Audited |
|----------|-------------|---------|
| `list_environments(root)` | GitHub API: `/repos/{repo}/environments` | No |
| `create_environment(root, name)` | GitHub API: `PUT /repos/{repo}/environments/{name}` | ✅ |
| `cleanup_environment(root, name, delete_files, delete_github)` | Delete local files + optionally GitHub env | ✅ |
| `seed_environments(root, names, default)` | Copy .env → .env.<name> for each env | ✅ |

**Environment file convention:**

| File | Purpose |
|------|---------|
| `.env` | Active environment (symlink-style swap via vault) |
| `.env.<name>` | Per-environment variables |
| `.env.<name>.vault` | Per-environment encrypted vault |
| `.env.active` | Marker file: which env is active (text content) |

---

## Audit Trail

| Event | Icon | Title | Target |
|-------|------|-------|--------|
| Key generated | 🔑 | Key Generated | generator type |
| Secret set | 🔐 | Secret Set | key name |
| Secret removed | 🗑️ | Secret Removed | key name |
| Secrets pushed | 📤 | Secrets Pushed | github |
| Environment created | 🌱 | Environment Created | env name |
| Environment cleaned | 🧹 | Environment Cleaned | env name |
| Environments seeded | 🌱 | Environments Seeded | environments |

---

## Consumers

| Consumer | What It Uses |
|----------|-------------|
| **Routes** `routes/secrets/` | All functions — list, set, remove, push, generate, environments |
| **CLI** `ui/cli/secrets.py` | `list_gh_secrets`, `set_secret`, `push_secrets`, `generate_key` |
| **Vault** `vault/env_ops.py` | Uses `classify_key` for key classification |
| **Wizard** `wizard/helpers.py` | `gh_status`, `gh_auto_detect`, `list_environments` |
| **CI** `ci/compose.py` | Secret references for CI workflow generation |

---

## API Endpoints

| Route | Method | Purpose | Module |
|-------|--------|---------|--------|
| `/api/secrets/gh/status` | GET | gh CLI + auth status | `ops` |
| `/api/secrets/gh/detect` | GET | Auto-detect token + repo | `ops` |
| `/api/secrets/gh/list` | GET | List secrets + variables | `gh_ops` |
| `/api/secrets/set` | POST | Set single secret | `gh_ops` |
| `/api/secrets/remove` | POST | Remove secret | `gh_ops` |
| `/api/secrets/push` | POST | Bulk push to GitHub | `gh_ops` |
| `/api/secrets/generate` | POST | Generate key/token/cert | `ops` |
| `/api/secrets/environments` | GET | List GitHub environments | `env_ops` |
| `/api/secrets/environments/create` | POST | Create environment | `env_ops` |
| `/api/secrets/environments/cleanup` | POST | Cleanup environment | `env_ops` |
| `/api/secrets/environments/seed` | POST | Seed environment files | `env_ops` |

---

## Error Handling Patterns

```python
# Pattern 1: "available" + "reason" (list/detect)
{"available": False, "reason": "gh CLI not installed", "secrets": [], "variables": []}

# Pattern 2: "error" string (simple failures)
{"error": "Secret name required"}
{"error": "gh CLI not installed"}

# Pattern 3: per-target results (dual-target operations)
{
    "name": "MY_KEY",
    "local": {"success": True},
    "github": {"success": False, "error": "Not authenticated"},
}

# Pattern 4: per-key results (bulk operations)
{
    "results": [
        {"name": "KEY1", "kind": "secret", "success": True, "error": None},
        {"name": "KEY2", "kind": "variable", "success": False, "error": "..."},
    ],
    "all_success": False,
}
```

---

## Advanced Feature Showcase

### 1. Pattern-Based Key Classification

Every key name is automatically classified as `"secret"` or `"config"`
by matching against 15 substrings loaded from the central data registry.

```python
# src/core/data — classify_key() (the single source of truth)
SECRET_PATTERNS = [
    "key", "secret", "token", "password", "passwd", "pass",
    "credential", "auth", "api_key", "apikey", "private",
    "jwt", "cert", "certificate", "signing",
]

def classify_key(key_name: str) -> str:
    lower = key_name.lower()
    for pattern in get_registry().secret_patterns:
        if pattern in lower:
            return "secret"
    return "config"
```

`DATABASE_PASSWORD` → secret. `LOG_LEVEL` → config.
Push\_secrets uses this to route each key to `gh secret set`
or `gh variable set` without user intervention.

---

### 2. Multi-Type Key Generation

`generate_key()` produces 5 types of secrets, each with appropriate
tooling and metadata tags for downstream consumers.

```python
# ops.py — generate_key() branches by gen_type
"password"       → secrets.choice(alphabet) × length
                   meta: @type:password @generated:password @length:32

"token"          → secrets.token_urlsafe(length)
                   meta: @generated:token @length:32

"ssh-ed25519"    → ssh-keygen -t ed25519 (in temp dir)
                   returns: {value: b64(private), public_value: pub, base64: True}

"ssh-rsa"        → ssh-keygen -t rsa -b 4096 (in temp dir)
                   returns: {value: b64(private), public_value: pub, base64: True}

"cert-selfsigned"→ openssl req -x509 -newkey ec (prime256v1)
                   returns: {value: b64(cert), private_key: b64(key), base64: True}
```

SSH and cert types use temporary directories cleaned up automatically.
Binary values are base64-encoded and tagged `@encoding:base64`.

---

### 3. Dual-Target Operations

`set_secret` and `remove_secret` accept a `target` parameter that
controls where the operation applies: local `.env`, GitHub, or both.

```python
# gh_ops.py — set_secret() target routing
target in ("local", "both"):
    → write to .env file (upsert key=value line)
target in ("github", "both"):
    → classify_key(name) → "secret" → gh secret set
                          → "config" → gh variable set
```

GitHub push calls `gh_repo_flag()` which reads `GITHUB_REPOSITORY`
from the fresh `.env` — bootstrapping itself from the local config.

---

### 4. Bulk Push with sync\_keys

`push_secrets` supports a `sync_keys` parameter: a list of key names
to read from the live `.env` and push to GitHub without the caller
having to supply values.

```python
# gh_ops.py — push_secrets(), sync_keys flow
if sync_list and push_to_github:
    raw = fresh_env(project_root)       # read live .env values
    for key_name in sync_list:
        if key_name in excludes:
            continue
        val = raw.get(key_name, "")
        if not val:
            continue
        kind = classify_key(key_name)   # auto-classify
        if kind == "secret":
            secrets_map.setdefault(key_name, val)
        else:
            vars_map.setdefault(key_name, val)
```

One API call syncs N keys from `.env` to GitHub — the UI
bulk-selects keys and fires a single push.

---

### 5. GITHUB\_\* Exclusion Rules

Keys starting with `GITHUB_` are never pushed to GitHub because
GitHub Actions auto-injects its own `GITHUB_*` variables.
Pushing them would overwrite runtime values.

```python
# gh_ops.py — push_secrets() per-key guard
for name, value in secrets_map.items():
    if not value:
        continue
    if name.startswith("GITHUB_") or name in excludes:
        continue                       # ← skip GITHUB_TOKEN, etc.
    subprocess.run(["gh", "secret", "set", name, "--body", value] + ...)
```

Also applies to explicit `exclude_from_github` set, which callers
use for keys like `VAULT_PASSPHRASE` that should never leave the machine.

---

## Design Decisions

### Why classify keys by name pattern instead of letting users decide?

Most `.env` keys follow naming conventions (e.g., `JWT_SECRET` is
always a secret, `LOG_LEVEL` is always a config variable). Auto-classifying
reduces friction: users push all keys at once and the system
automatically routes sensitive values to GitHub secrets (encrypted)
and non-sensitive values to GitHub variables (readable by workflows).
The classification is overridable via the `exclude_from_github` parameter.

### Why dual-target (local + github) instead of GitHub-first?

Some users work offline or don't have GitHub configured. The `.env` file
is always the source of truth; GitHub is a replication target. Allowing
`target="local"` means the secrets UI works even without GitHub
connectivity. Allowing `target="github"` means users can push to
GitHub without modifying their local `.env`.

### Why `push_secrets` combines save + push in one call?

The common user workflow is: "I updated my secrets in the UI, now
deploy them." Making this two separate calls (save, then push) risks
partial state if one fails. Combining them into one atomic operation
with per-key results gives users a clear picture of what succeeded
and what didn't.

### Why does `fresh_env` merge with os.environ?

Some secrets reference environment variables (e.g., `$HOME` in paths).
Merging `.env` on top of the system environment ensures subprocess
commands have access to both local project secrets and system-level
variables. The `TERM=dumb` override prevents color codes from
corrupting `gh` CLI output parsing.

### Why separate env_ops.py from gh_ops.py?

`gh_ops.py` manages individual secrets/variables (set, remove, push).
`env_ops.py` manages deployment environments (create, cleanup, seed)
which operate at a higher abstraction level — they manage groups of
files and GitHub API resources. Different lifecycle, different
concerns, no code sharing.

### Why does seed_environments copy instead of symlink?

File systemlinks create confusion: editing `.env.staging` might
silently modify `.env` if they're linked. Copying creates independent
files that can diverge per environment. The vault system also
needs independent `.vault` files per environment for independent
lock/unlock cycles.

### Why are GITHUB_* keys excluded from push?

GitHub Actions automatically injects `GITHUB_*` environment variables
into workflow runs. Pushing them as secrets/variables would shadow
the built-in values and cause subtle bugs (e.g., wrong repository
name in workflow steps). The exclusion is unconditional — it
cannot be overridden.
