# L0 Data — Pure Data Dictionaries

> No logic. No imports beyond stdlib. Just dicts and constants.

---

## Structure

### `recipes/` — Tool Recipe Registry
**300 tools across 7 domain packages.**

The central knowledge base for every installable tool, organized by domain:

| Package | What | Tools |
|---------|------|-------|
| `recipes/core/` | System utilities, shells, terminals | 40 |
| `recipes/languages/` | 14 language ecosystems (Python → R) | 109 |
| `recipes/devops/` | K8s, cloud, containers, CI/CD, monitoring | 53 |
| `recipes/security/` | Scanners, crypto & TLS tools | 16 |
| `recipes/network/` | Networking, DNS, proxies, service mesh | 17 |
| `recipes/data_ml/` | ML, databases, data packs, GPU drivers | 20 |
| `recipes/specialized/` | Dev tools, media, docs, build tools, config | 67 |

Each recipe declares how to install (per package manager / platform),
what it depends on, how to verify, how to update/rollback.
See **[recipes/README.md](recipes/README.md)** for the full package structure.

### `constants.py` — Shared Constants
- `_PIP` — Resolve pip via the current interpreter (`[sys.executable, "-m", "pip"]`)
- `_IARCH_MAP` — Architecture name normalization (x86_64→amd64, aarch64→arm64, etc.)
- `BUILD_TIMEOUT_TIERS` — Timeout presets for build steps (small/medium/large/huge)
- `_VERSION_FETCH_CACHE` — Runtime cache for version API fetches

### `recipe_schema.py` — Recipe Validation
Schema definitions and validators for recipe dicts. Ensures every recipe
conforms to the expected field types, required keys, and category values.

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

### `remediation_handlers/` — Failure Remediation Registry
**77 handlers across 4 layers. 19 method families. Pure data, no logic.**

Layer-based failure handler definitions mapping error patterns to remediation options:

| Layer | File(s) | Handlers |
|-------|---------|----------|
| Layer 2 — Method family | `method_families/` (19 files) | 66 handlers, 131 options |
| Layer 1 — Infrastructure | `infra.py` | 9 handlers, 17 options |
| Layer 0 — Bootstrap | `bootstrap.py` | 2 handlers, 3 options |
| Utility | `lib_package_map.py` | 16 C-lib → distro-package entries |

See **[remediation_handlers/README.md](remediation_handlers/README.md)** for the full package structure.

### `tool_failure_handlers/` — Per-Tool Failure Handler Registry
**52 handlers across 18 tools. 3 domains. Pure data, no logic.**

Tool-specific failure patterns and remediation options, organized by domain:

| Domain | File(s) | Tools | Handlers |
|--------|---------|-------|----------|
| Languages | `languages/` (5 files) | 11 (cargo, rustup, go, python, poetry, uv, node, nvm, yarn, pnpm, composer) | 30 handlers, 69 options |
| DevOps | `devops/` (3 files) | 6 (docker, docker-compose, helm, kubectl, gh, terraform) | 21 handlers, 42 options |
| Security | `security/` (1 file) | 1 (trivy) | 2 handlers, 4 options |

See **[tool_failure_handlers/README.md](tool_failure_handlers/README.md)** for the full package structure.

---

## Usage

```python
from src.core.services.tool_install.data import TOOL_RECIPES, UNDO_COMMANDS

recipe = TOOL_RECIPES["cargo-audit"]
print(recipe["install"]["_default"])  # ["cargo", "install", "cargo-audit"]
print(recipe["requires"]["binaries"])  # ["cargo"]
```

---

## Re-exports

`data/__init__.py` re-exports all public symbols:

| Symbol | Source |
|--------|--------|
| `TOOL_RECIPES` | `recipes/__init__.py` |
| `_PIP` | `constants.py` |
| `_IARCH_MAP` | `constants.py` |
| `_VERSION_FETCH_CACHE` | `constants.py` |
| `BUILD_TIMEOUT_TIERS` | `constants.py` |
| `_CUDA_DRIVER_COMPAT` | `cuda_matrix.py` |
| `_PROFILE_MAP` | `profile_maps.py` |
| `RESTART_TRIGGERS` | `restart_triggers.py` |
| `UNDO_COMMANDS` | `undo_catalog.py` |
