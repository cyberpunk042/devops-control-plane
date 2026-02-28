# Secrets Domain

> Secrets management for the devops control plane.
> Bridges local `.env` files with GitHub Secrets/Variables via `gh` CLI,
> generates cryptographic keys (passwords, tokens, SSH, TLS certs),
> and manages multi-environment deployment configurations.

---

## How It Works

The secrets domain serves two audiences:

1. **Local development** — `.env` files hold secrets and config
   variables. The domain reads/writes these files, generates strong
   values, and manages multi-environment setups (dev/staging/prod).

2. **GitHub CI/CD** — the domain pushes secrets and variables to
   GitHub using the `gh` CLI, with automatic classification: keys
   classified as `secret` go to `gh secret set`, keys classified as
   `config` go to `gh variable set`.

### Push Flow — Local to GitHub

```
User triggers "Push to GitHub"
      │
      ▼
  push_secrets(project_root, secrets_dict, variables, ...)
      │
      ├── 1. Merge secrets + variables dicts
      ├── 2. If sync_keys: read .env, classify each key
      │       └── secret keys → secrets_map, config keys → vars_map
      ├── 3. Save merged values to local .env file
      ├── 4. Check gh CLI is installed + authenticated
      ├── 5. For each secret: gh secret set NAME --body VALUE
      ├── 6. For each variable: gh variable set NAME --body VALUE
      └── 7. Return per-key success/failure report
```

### Key Classification

The `classify_key()` function (from the data layer) determines
whether a key is a `secret` or `config` based on naming patterns:

- **Secret**: contains `KEY`, `SECRET`, `TOKEN`, `PASSWORD`, `CERT`
- **Config**: everything else (`APP_NAME`, `NODE_ENV`, `PORT`)

This classification drives:
- Which GitHub endpoint to use (secrets vs variables)
- Whether to show `@type:password` UI hints
- Whether to mask values in the admin panel

### Multi-Environment Support

Projects can define multiple environments (dev, staging, production).
Each environment has its own `.env.{name}` file. The secrets domain
handles:

- **Seeding** — copy `.env` → `.env.{name}` for each new environment
- **Environment-scoped secrets** — `gh secret set --env staging`
- **Cleanup** — delete local files and/or GitHub environments
- **Listing** — query the GitHub API for all deployment environments

---

## File Map

```
secrets/
├── __init__.py     Public API re-exports
├── ops.py          Core helpers, gh CLI status, key generators (255 lines)
├── env_ops.py      GitHub environment management (205 lines)
├── gh_ops.py       GitHub secrets/variables CRUD (442 lines)
└── README.md       This file
```

### `ops.py` — Core Helpers + Key Generators (255 lines)

Shared utilities consumed by the other submodules, plus the gh CLI
status check and cryptographic key generation.

| Function | What It Does |
|----------|-------------|
| `fresh_env()` | Build subprocess env dict merged with `.env` values |
| `gh_repo_flag()` | Return `["-R", "owner/repo"]` flag for gh CLI |
| `env_path_for()` | Resolve `.env` or `.env.{name}` path |
| `read_env_values()` | Parse `.env` → raw key→value dict |
| `classify_key()` | Re-export from data layer (secret vs config) |
| `gh_status()` | Check if gh CLI is installed + authenticated |
| `gh_auto_detect()` | Get GitHub token + detect repo from git remote |
| `generate_key()` | Generate password, token, SSH key, or TLS cert |

### `env_ops.py` — Environment Management (205 lines)

GitHub deployment environment lifecycle.

| Function | What It Does |
|----------|-------------|
| `list_environments()` | List all GitHub deployment environments |
| `create_environment()` | Create a new environment via GitHub API |
| `cleanup_environment()` | Delete local files and/or GitHub environment |
| `seed_environments()` | Copy `.env` → `.env.{name}` for multi-env transition |

### `gh_ops.py` — GitHub Secrets & Variables (442 lines)

CRUD operations for GitHub repository secrets and variables.

| Function | What It Does |
|----------|-------------|
| `list_gh_secrets()` | List secrets AND variables from GitHub |
| `set_secret()` | Set a single secret to `.env` and/or GitHub |
| `remove_secret()` | Remove a secret/variable from `.env` and/or GitHub |
| `push_secrets()` | Batch push — secrets to `gh secret`, variables to `gh variable`, save to `.env` |

---

## Dependency Graph

```
ops.py         standalone — stdlib + audit_helpers + data layer
   ↑
env_ops.py     imports gh_repo_flag, env_path_for from ops.py
   
ops.py
   ↑
gh_ops.py      imports fresh_env, gh_repo_flag, env_path_for, classify_key from ops.py
```

`ops.py` is the foundation. Both `env_ops.py` and `gh_ops.py` depend
on it but not on each other.

---

## Backward Compatibility

| Old path | Re-exports from |
|----------|----------------|
| `services/secrets_ops.py` | `secrets/ops.py` + `secrets/env_ops.py` + `secrets/gh_ops.py` |
| `services/secrets_env_ops.py` | `secrets/env_ops.py` |
| `services/secrets_gh_ops.py` | `secrets/gh_ops.py` |

The original `secrets_ops.py` re-exported everything from the other
two files at the bottom — the shim preserves this behavior.

For new code:
```python
# ✅ Package-level
from src.core.services.secrets import push_secrets, generate_key

# ✅ Specific submodule
from src.core.services.secrets.gh_ops import push_secrets

# ⚠️ Legacy shim — still works, avoid in new code
from src.core.services.secrets_ops import push_secrets
```

---

## Consumers

| Consumer | What It Uses | Import Pattern |
|----------|-------------|----------------|
| `routes_secrets.py` | All ops + gh_ops + env_ops | `from src.core.services import secrets_ops` |
| `routes_content.py` | `fresh_env` | Lazy `from secrets_ops import fresh_env` |
| `env_infra_ops.py` | Module-level import | Lazy `from src.core.services import secrets_ops` |
| `ui/cli/secrets.py` | Individual functions | Lazy imports inside each CLI command |

---

## API Endpoints

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/secrets/status` | GET | gh CLI + auth status |
| `/api/secrets/list` | GET | List GitHub secrets + variables |
| `/api/secrets/set` | POST | Set a single secret |
| `/api/secrets/remove` | POST | Remove a secret/variable |
| `/api/secrets/push` | POST | Batch push to GitHub + save to .env |
| `/api/secrets/generate` | POST | Generate password/token/SSH/cert |
| `/api/secrets/environments` | GET | List deployment environments |
| `/api/secrets/environments/create` | POST | Create a new environment |
| `/api/secrets/environments/cleanup` | POST | Clean up an environment |
| `/api/secrets/environments/seed` | POST | Seed multi-env files |
