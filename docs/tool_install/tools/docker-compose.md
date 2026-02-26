# docker-compose — Full Spectrum Analysis

> **Tool ID:** `docker-compose`
> **Last audited:** 2026-02-26 (resweep)
> **Status:** ✅ Complete

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | Docker Compose — multi-container Docker orchestration |
| Language | Go (V2). Python (V1 — deprecated, EOL) |
| CLI binary | `docker` (compose is a CLI plugin, invoked as `docker compose`) |
| Category | `container` |
| Verify command | `docker compose version` |
| Recipe key | `docker-compose` |

### Special notes
- Docker Compose **V2** is a Docker CLI plugin, not a standalone binary.
  It is invoked as `docker compose` (with space), NOT `docker-compose` (with hyphen).
- Docker Compose V1 (python-based, standalone `docker-compose` binary) is
  deprecated and EOL since July 2023.
- The `cli` field is set to `docker` because compose is a subcommand of
  the `docker` CLI.

---

## 2. Package Availability

| PM | Available | Package name | Source |
|----|-----------|--------------|--------|
| `apt` | ✅ | `docker-compose-plugin` | Docker official repo (NOT `docker-compose-v2`) |
| `dnf` | ✅ | `docker-compose-plugin` | Docker official repo |
| `apk` | ✅ | `docker-cli-compose` | Alpine community repo (3.15+) |
| `pacman` | ✅ | `docker-compose` | Arch extra repo |
| `zypper` | ✅ | `docker-compose` | openSUSE Virtualization:containers repo |
| `brew` | ✅ | `docker-compose` | formulae.brew.sh |
| `snap` | ❌ | — | Not available as snap |
| `pip` | ❌ | — | Only V1 (deprecated), not V2 |
| `npm` | ❌ | — | Not available |
| `cargo` | ❌ | — | Not available |
| `go` | ❌ | — | Not available (internal Go binary) |

### Package name corrections applied
- **apt:** Changed from `docker-compose-v2` (wrong) to `docker-compose-plugin` (correct)
- **apk:** Changed from `docker-compose` (legacy/py) to `docker-cli-compose` (Go V2 plugin)
- **update commands:** Fixed to match install package names

---

## 3. Binary Download (_default)

| Field | Value |
|-------|-------|
| Releases | https://github.com/docker/compose/releases |
| URL pattern | `https://github.com/docker/compose/releases/latest/download/docker-compose-linux-{arch}` |
| Archive format | Raw binary (no archive) |
| Arch naming | `x86_64`, `aarch64`, `armv7`, `armv6` (raw `uname -m`, NOT `amd64`/`arm64`) |
| OS naming | `linux`, `darwin` |
| Install location | `/usr/local/lib/docker/cli-plugins/docker-compose` (as CLI plugin) |
| Dependencies | `curl` (download), `docker` (runtime) |
| needs_sudo | Yes (writes to `/usr/local/lib/docker/cli-plugins/`) |

### Architecture mapping (critical)
Docker Compose releases use **raw `uname -m` names** (`x86_64`, `aarch64`) — NOT the
normalized names used by Go/Docker Hub (`amd64`, `arm64`). The system-wide `_IARCH_MAP`
normalizes `x86_64 → amd64` and `aarch64 → arm64`, which produces wrong URLs.

**Fix applied:** `arch_map: {"x86_64": "x86_64", "aarch64": "aarch64", "armv7l": "armv7"}` in
the recipe overrides `_IARCH_MAP` via the `_arch_map` injection in `plan_resolution.py`.

| `platform.machine()` | `_IARCH_MAP` (wrong for compose) | `arch_map` override (correct) | GitHub asset | URL verified |
|-----------------------|----------------------------------|-------------------------------|-------------|------|
| `x86_64` | `amd64` ❌ (404) | `x86_64` ✅ | `docker-compose-linux-x86_64` | 302 ✅ |
| `aarch64` | `arm64` ❌ (404) | `aarch64` ✅ | `docker-compose-linux-aarch64` | 302 ✅ |
| `armv7l` | `armhf` ❌ (404) | `armv7` ✅ | `docker-compose-linux-armv7` | 302 ✅ |

**Live verified:** `amd64` and `arm64` URLs return HTTP 404. Correct URLs return 302→download.

### _default install command
```bash
COMPOSE_ARCH={arch} && \
mkdir -p /usr/local/lib/docker/cli-plugins && \
curl -sSfL https://github.com/docker/compose/releases/latest/download/docker-compose-linux-$COMPOSE_ARCH \
  -o /usr/local/lib/docker/cli-plugins/docker-compose && \
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
```

### mkdir -p safety note
The `mkdir -p` was added during the resweep. On fresh installs where Docker was installed
via the convenience script or manually, `/usr/local/lib/docker/cli-plugins/` may not exist.
Without `mkdir -p`, `curl -o` would fail with "No such file or directory".

---

## 4. Build from Source

| Field | Value |
|-------|-------|
| Build system | Go (`go build`) |
| Git repo | https://github.com/docker/compose.git |
| Branch | `main` (or tag `v2.x.x`) |
| Build deps | `go` (1.21+), `make`, `git` |
| Build command | `make binary` |
| Output binary | `bin/build/docker-compose` |

Not included in recipe — Go build requires specific version match and build toolchain.

---

## 5. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Runtime binary | `docker` | Required — compose is a Docker plugin |
| Download | `curl` | For `_default` install method |

### Reverse deps
No other tools in the stack depend on docker-compose.

---

## 6. Failure Surface

### 6.1 Per-install-method failures
All PM-based install methods have dedicated Layer 2 METHOD_FAMILY_HANDLERS:

| PM | Handlers | IDs |
|----|---------|-----|
| `apt` | Package not found, DB locked | `apt_stale_index`, `apt_locked` |
| `dnf` | Package not found | `dnf_no_match` |
| `apk` | Unsatisfiable constraints, DB locked | `apk_unsatisfiable`, `apk_locked` |
| `pacman` | Target not found, DB locked | `pacman_target_not_found`, `pacman_locked` |
| `zypper` | Package not found, PM locked | `zypper_not_found`, `zypper_locked` |
| `brew` | Formula not found | `brew_no_formula` |
| `_default` | Missing curl/git/wget/unzip/npm | 5 dependency handlers |

All methods also inherit Layer 1 INFRA_HANDLERS (network, disk, permissions,
timeout, OOM — 9 total).

### 6.2 Tool-specific failures (Layer 3 on_failure)

| Failure | Pattern | Category | Handler ID |
|---------|---------|----------|-----------|
| Plugin not registered | `'compose' is not a docker command` | dependency | `compose_plugin_not_found` |
| V1 legacy not found | `docker-compose: command not found` | compatibility | `compose_v1_not_found` |
| YAML / version error | `Version in .* is unsupported`, `yaml: line N:` | environment | `compose_yaml_error` |

---

## 7. Handler Layers

### Layer 1: INFRA_HANDLERS (existing)
9 cross-tool handlers apply. No changes needed.

### Layer 2: METHOD_FAMILY_HANDLERS
- `apt` family: `apt_stale_index`, `apt_locked` — existing
- `dnf` family: `dnf_no_match` — existing
- `apk` family: `apk_unsatisfiable`, `apk_locked` — **ADDED**
- `pacman` family: `pacman_target_not_found`, `pacman_locked` — **ADDED**
- `zypper` family: `zypper_not_found`, `zypper_locked` — **ADDED**
- `brew` family: `brew_no_formula` — existing
- `_default` family: 5 handlers (missing_curl, missing_git, etc.) — existing

### Layer 3: Recipe on_failure (added)
3 handlers added. See §6.2.

---

## 8. Availability Gates

No new capability gates needed. Compose handlers use `install_dep` and
`manual` strategies:
- `install_dep` with `dep: "docker-compose"` → resolves via recipe (Tier 1)
- `manual` (alias creation, YAML editing) → always ready

No systemd or container-specific options in compose handlers.

---

## 9. Resolver Data

### KNOWN_PACKAGES
Added `docker-compose` entry with per-PM package names:
```python
"docker-compose": {
    "apt": "docker-compose-plugin",
    "dnf": "docker-compose-plugin",
    "apk": "docker-cli-compose",
    "pacman": "docker-compose",
    "zypper": "docker-compose",
    "brew": "docker-compose",
},
```

### LIB_TO_PACKAGE_MAP
No C library dependencies. No changes needed.

### Special installers
No standalone installer needed (has _default binary download).

---

## 10. Recipe — After

```python
"docker-compose": {
    "cli": "docker",
    "label": "Docker Compose",
    "category": "container",
    "install": {
        "apt":    ["apt-get", "install", "-y", "docker-compose-plugin"],
        "dnf":    ["dnf", "install", "-y", "docker-compose-plugin"],
        "apk":    ["apk", "add", "docker-cli-compose"],
        "pacman": ["pacman", "-S", "--noconfirm", "docker-compose"],
        "zypper": ["zypper", "install", "-y", "docker-compose"],
        "brew":   ["brew", "install", "docker-compose"],
        "_default": [...],  # GitHub releases binary download
    },
    "needs_sudo": {
        "apt": True, "dnf": True, "apk": True,
        "pacman": True, "zypper": True, "brew": False,
        "_default": True,
    },
    "requires": {"binaries": ["docker", "curl"]},
    "arch_map": {"x86_64": "x86_64", "aarch64": "aarch64", "armv7l": "armv7"},
    "version_constraint": {
        "type": "gte",
        "reference": "2.0.0",
        "description": "Docker Compose V2 required ...",
    },
    "verify": ["docker", "compose", "version"],
    "update": {
        "apt":    [..., "docker-compose-plugin"],
        "dnf":    [..., "docker-compose-plugin"],
        "apk":    [..., "docker-cli-compose"],
        "pacman": [..., "docker-compose"],
        "zypper": [..., "docker-compose"],
        "brew":   [..., "docker-compose"],
        "_default": [...],
    },
    "on_failure": [
        # compose_plugin_not_found — 1 option (install_dep)
        # compose_v1_not_found — 2 options (install_dep + manual alias)
        # compose_yaml_error — 2 options (manual + install_dep)
    ],
},
```

---

## 11. Validation Results

```
Schema:    VALID (recipe + 3 on_failure handlers + 10 PM family handlers)
Coverage:  513/513 (100%) — 27 scenarios × 19 presets
Zero-opts: PASSED — every handler has ≥1 ready option on every system
Regression: PASSED — full suite exit code 0, no new errors
URL test:  docker-compose-linux-{x86_64,aarch64,armv7} → HTTP 302 (valid)
           docker-compose-linux-{amd64,arm64,armhf} → HTTP 404 (wrong)
```

---

## 12. Changes Applied

| File | Change | Line |
|------|--------|------|
| `data/recipes.py` | Fixed apt package: `docker-compose-v2` → `docker-compose-plugin` | 1271 |
| `data/recipes.py` | Fixed apk package: `docker-compose` → `docker-cli-compose` | 1273 |
| `data/recipes.py` | Added `cli: "docker"` field | 1269 |
| `data/recipes.py` | Added `category: "container"` field | 1270 |
| `data/recipes.py` | Added `_default` install method (GitHub releases binary) | 1277-1285 |
| `data/recipes.py` | Added `_default` to `needs_sudo` | 1290 |
| `data/recipes.py` | Added `curl` to `requires.binaries` | 1296 |
| `data/recipes.py` | Fixed apt/apk update commands to match install | 1301-1305 |
| `data/recipes.py` | Added `_default` update method | 1308-1314 |
| `data/recipes.py` | Added 3 `on_failure` handlers (plugin, v1, yaml) | 1316-1447 |
| `resolver/dynamic_dep_resolver.py` | Added `docker-compose` to `KNOWN_PACKAGES` | 235-241 |
| `data/remediation_handlers.py` | Added `apk` METHOD_FAMILY_HANDLERS (2 handlers) | cross-tool |
| `data/remediation_handlers.py` | Added `pacman` METHOD_FAMILY_HANDLERS (2 handlers) | cross-tool |
| `data/remediation_handlers.py` | Added `zypper` METHOD_FAMILY_HANDLERS (2 handlers) | cross-tool |
| `data/recipes.py` | Added `arch_map` for correct arch naming in GitHub releases | 1317 |
| `execution/build_helpers.py` | Fixed missing `_IARCH_MAP` import (NameError bug) | 18 |
| `resolver/plan_resolution.py` | Inject recipe `arch_map` as `_arch_map` in profile before substitution | 297-310 |
| `data/recipes.py` | Added `mkdir -p` to install and update `_default` commands | 1289, 1319 |
| `data/recipes.py` | Added `armv7l` → `armv7` to `arch_map` | 1326 |

---

## 13. Raspbian / ARM Notes

| Aspect | Status |
|--------|--------|
| `_default` (GitHub binary) | ✅ Correct arch mapping via `arch_map` override |
| `apt` (docker-compose-plugin) | ✅ Available in Docker's Raspbian repo |
| aarch64 (Raspberry Pi 4/5 64-bit) | ✅ `docker-compose-linux-aarch64` exists |
| armv7l (Raspberry Pi 3/4 32-bit) | ✅ `docker-compose-linux-armv7` exists |
| Plugin directory | ✅ `mkdir -p` ensures directory exists before download |
| armhf naming | ❌ No asset named `armhf` — Compose uses `armv7` |
