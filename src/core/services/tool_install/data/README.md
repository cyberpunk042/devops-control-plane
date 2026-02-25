# L0 Data — Pure Data Dictionaries

> No logic. No imports beyond stdlib. Just dicts and constants.

---

## Files

### `recipes.py` — Tool Recipe Registry
**61 tools.** The central knowledge base for every installable tool.

Each recipe is a dict keyed by tool ID (e.g. `"cargo-audit"`) that declares:
- How to install (per package manager / platform)
- What it depends on (binaries, system packages, hardware)
- How to verify success
- How to update/rollback
- What repos to add first
- What env vars to propagate

See [root README](../README.md#recipe-fields-reference) for the full field spec.

#### Categories in recipes.py:
| Category | Tools | Example |
|----------|-------|---------|
| pip tools | 7 | ruff, mypy, pytest, black, pip-audit, safety, bandit |
| npm tools | 5 | eslint, prettier, npm-audit, snyk, license-checker |
| cargo tools | 3 | cargo-audit, cargo-outdated, cargo-deny |
| system packages | 15 | git, curl, jq, htop, tmux, tree, shellcheck, etc. |
| container tools | 6 | docker, docker-compose, podman, kubectl, helm, k9s |
| infra tools | 6 | terraform, ansible, packer, vault, consul, nomad |
| CI/CD tools | 5 | gh, act, dagger, earthly, buildpacks |
| cloud CLIs | 6 | aws-cli, gcloud, az-cli, doctl, flyctl, railway |
| GPU drivers | 4 | nvidia-driver, cuda-toolkit, rocm, vulkan |
| Language runtimes | 4 | rustup, nvm, pyenv, golang |

### `constants.py` — Shared Constants
- `_IARCH_MAP` — Architecture name normalization (amd64→x86_64, etc.)
- `BUILD_TIMEOUT_TIERS` — Timeout presets for build steps
- `_VERSION_FETCH_CACHE` — Cache duration for version lookups

### `profile_maps.py` — Shell Profile Paths
- `_PROFILE_MAP` — Maps shell names to their rc/profile files
  (`bash` → `~/.bashrc`, `zsh` → `~/.zshrc`, etc.)

### `cuda_matrix.py` — CUDA/Driver Compatibility
- `_CUDA_DRIVER_COMPAT` — Maps CUDA versions to minimum driver versions

### `undo_catalog.py` — Rollback Commands
- `UNDO_COMMANDS` — Maps tool IDs to their uninstall commands
  (`"ruff"` → `["pip", "uninstall", "-y", "ruff"]`)

### `restart_triggers.py` — Restart Triggers
- `RESTART_TRIGGERS` — Maps tool IDs to restart requirements
  (`"nvidia-driver"` → `"system"`, `"rustup"` → `"shell"`)

---

## Usage

```python
from src.core.services.tool_install.data import TOOL_RECIPES, UNDO_COMMANDS

recipe = TOOL_RECIPES["cargo-audit"]
print(recipe["install"]["_default"])  # ["cargo", "install", "cargo-audit"]
print(recipe["requires"]["binaries"])  # ["cargo"]
```
