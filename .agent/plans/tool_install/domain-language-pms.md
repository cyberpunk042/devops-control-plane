# Domain: Language Package Managers

> This document catalogs every language-level package manager the
> tool install system handles: pip, npm, cargo, and their runtimes.
> It covers install mechanics, permission models, isolation strategies,
> dependency chains, and how they integrate with recipes.
>
> SOURCE CODE: tool_install.py `_PIP`, `TOOL_RECIPES` (implemented)
> SOURCE DOCS: phase2.2 §Category 1-4 (pip/npm/cargo/rustup analysis),
>              arch-recipe-format §Category 1-4,
>              scope-expansion §2.6 (PATH), §2.15 (private registries)

---

## Overview

Language PMs install tools WITHIN a language ecosystem. They differ
from system PMs (apt, dnf, etc.) in several fundamental ways:

| Aspect | System PM (apt) | Language PM (pip) |
|--------|----------------|-------------------|
| Scope | Entire OS | One language ecosystem |
| Permissions | Usually needs sudo | Usually user-space |
| Isolation | Shared system dirs | Can be isolated (venv, nvm) |
| Dependencies | OS packages | Language packages |
| Registry | Distro repos | Language registry (pypi.org) |
| Needs internet | Depends (local cache) | Almost always |
| Cross-platform | Per-distro | Works on any OS |

**In the recipe system:** Language PM tools use the `"_default"` install
method key. They work on ANY platform because they don't depend on
system-specific commands. The `_default` fallback is the last resort
in the resolver's method selection order.

---

## pip (Python)

### Identity

| Property | Value |
|----------|-------|
| **Language** | Python |
| **Registry** | pypi.org |
| **Install dir (venv)** | `$VIRTUAL_ENV/lib/pythonX.Y/site-packages/` |
| **Install dir (user)** | `~/.local/lib/pythonX.Y/site-packages/` |
| **Binary dir (venv)** | `$VIRTUAL_ENV/bin/` |
| **Binary dir (user)** | `~/.local/bin/` |
| **Needs sudo** | No (venv or user install) |

### How we use it

The application runs inside a Python venv. pip installs go INTO that venv:

```python
_PIP = [sys.executable, "-m", "pip"]
```

**Why `sys.executable -m pip`?** Because:
1. `pip` may not be on `$PATH` in some venvs
2. `python -m pip` guarantees we use the SAME Python as the running app
3. `sys.executable` is the exact Python binary running the server

### Current tools (7)

| Tool | Install | Update |
|------|---------|--------|
| ruff | `_PIP + ["install", "ruff"]` | `_PIP + ["install", "--upgrade", "ruff"]` |
| mypy | `_PIP + ["install", "mypy"]` | `_PIP + ["install", "--upgrade", "mypy"]` |
| pytest | `_PIP + ["install", "pytest"]` | `_PIP + ["install", "--upgrade", "pytest"]` |
| black | `_PIP + ["install", "black"]` | `_PIP + ["install", "--upgrade", "black"]` |
| pip-audit | `_PIP + ["install", "pip-audit"]` | `_PIP + ["install", "--upgrade", "pip-audit"]` |
| safety | `_PIP + ["install", "safety"]` | `_PIP + ["install", "--upgrade", "safety"]` |
| bandit | `_PIP + ["install", "bandit"]` | `_PIP + ["install", "--upgrade", "bandit"]` |

### Recipe pattern

```python
"ruff": {
    "label": "Ruff",
    "install": {"_default": _PIP + ["install", "ruff"]},
    "needs_sudo": {"_default": False},
    "verify": ["ruff", "--version"],
    "update": {"_default": _PIP + ["install", "--upgrade", "ruff"]},
},
```

**Characteristics:**
- No `requires` — pip is available because the app is running in Python
- No platform variance — `_default` only
- No sudo — venv installs don't need elevated privileges
- No post_install — tools are immediately available in venv's `bin/`
- Simplest category in the entire recipe system

### Permission model

| Context | Needs sudo? | Install location |
|---------|------------|-----------------|
| In a venv (our case) | No | `$VIRTUAL_ENV/bin/` |
| User install (`--user`) | No | `~/.local/bin/` |
| System-wide | Yes | `/usr/local/bin/` |
| Docker (root) | No | `/usr/local/bin/` (root owns it) |

**Our system always uses venv.** sudo is never needed for pip.

### Verify strategy

Two options for verifying pip-installed tools:

```python
# Option A: run the tool (current approach)
["ruff", "--version"]

# Option B: check pip package
_PIP + ["show", "ruff"]
```

Both work. Option A confirms the binary is functional.
Option B confirms the package is in the venv but doesn't test the binary.
We use Option A in recipes.

### Private registries (NOT IMPLEMENTED — Phase 4)

```python
# Standard PyPI
_PIP + ["install", "ruff"]

# Private index
_PIP + ["install", "--index-url", "https://pypi.internal.com/simple/", "ruff"]

# Extra index (fall back to PyPI)
_PIP + ["install", "--extra-index-url", "https://pypi.internal.com/simple/", "ruff"]
```

Detection: `pip config get global.index-url` reveals custom index.
Recipe field: `pip_index` in install_variants (Phase 4).

### Edge cases

| Case | Impact | Handling |
|------|--------|---------|
| pip itself is outdated | Install may warn but usually succeeds | Not our concern, venv has pip |
| Network down | Install fails (pypi.org unreachable) | Error analysis suggests checking network |
| Package not on PyPI | `ERROR: No matching distribution` | Error analysis shows package name |
| Version conflict | pip resolves automatically | May take longer |
| Wheel not available for arch | Falls back to source build → may need gcc | Known limitation; rare for our 7 tools |
| musl (Alpine) | Some wheels unavailable | Our 7 tools all have musl wheels |

---

## npm (Node.js)

### Identity

| Property | Value |
|----------|-------|
| **Language** | JavaScript / Node.js |
| **Registry** | registry.npmjs.org |
| **Global install dir (system)** | `/usr/local/lib/node_modules/` |
| **Global install dir (nvm)** | `~/.nvm/versions/node/vX/lib/node_modules/` |
| **Global binary dir (system)** | `/usr/local/bin/` |
| **Global binary dir (nvm)** | `~/.nvm/versions/node/vX/bin/` |
| **Needs sudo** | Depends on install method |

### How we use it

npm installs tools GLOBALLY with `-g`:

```python
["npm", "install", "-g", "eslint"]
```

### Current tools (2)

| Tool | Install | Update | Requires |
|------|---------|--------|----------|
| eslint | `["npm", "install", "-g", "eslint"]` | `["npm", "update", "-g", "eslint"]` | npm binary |
| prettier | `["npm", "install", "-g", "prettier"]` | `["npm", "update", "-g", "prettier"]` | npm binary |

### Recipe pattern

```python
"eslint": {
    "label": "ESLint",
    "install": {"_default": ["npm", "install", "-g", "eslint"]},
    "needs_sudo": {"_default": False},
    "requires": {"binaries": ["npm"]},
    "verify": ["eslint", "--version"],
    "update": {"_default": ["npm", "update", "-g", "eslint"]},
},
```

### Permission model

| npm source | Global prefix | Needs sudo? |
|-----------|--------------|-------------|
| System package (apt install npm) | `/usr/local/` | **Yes** (or EACCES) |
| nvm | `~/.nvm/versions/node/vX/` | No |
| snap install node | `/snap/node/…` snap-managed | Via snap (sudo) |
| brew install node | `/opt/homebrew/` or `/usr/local/` | No (brew user-space) |
| Manually downloaded | Wherever extracted | Depends |

**Current decision:** Mark `needs_sudo: False` for npm tools.
If the global prefix is system-owned and the user doesn't have
write permission, `npm install -g` fails with EACCES. The error
analysis handles this case post-failure. This preserves current
behavior.

**NOT IMPLEMENTED (Phase 4):** Detect npm global prefix and set
`needs_sudo` dynamically:
```python
prefix = subprocess.run(["npm", "config", "get", "prefix"],
                        capture_output=True, text=True).stdout.strip()
needs_sudo = not os.access(prefix, os.W_OK)
```

### npm as a dependency

npm itself is a system package that the resolver may need to install:

| Family | Package | Command |
|--------|---------|---------|
| debian | `npm` (comes with nodejs) | `apt-get install -y npm` |
| rhel | `npm` (comes with nodejs) | `dnf install -y npm` |
| alpine | `npm` (separate from nodejs) | `apk add npm` |
| arch | `npm` (comes with nodejs) | `pacman -S --noconfirm npm` |
| suse | `npm` | `zypper install -y npm` |
| macos | `node` (npm bundled) | `brew install node` |
| snap | `node` (npm bundled) | `snap install node --classic` |

**macOS + brew gotcha:** Install `node` not `npm` — npm is bundled
with the Node.js formula.

### Node version management (nvm)

nvm is NOT directly supported in Phase 2. If nvm is installed:
- `shutil.which("npm")` finds the nvm-managed npm
- Install works normally (writes to nvm's prefix)
- No sudo needed

NOT IMPLEMENTED: nvm detection could enable version-specific installs.

### Edge cases

| Case | Impact | Handling |
|------|--------|---------|
| EACCES on `npm install -g` | Permission denied on system npm | Error analysis suggests `--prefix` or nvm |
| npm not on PATH | `requires: ["npm"]` triggers npm install | Resolver installs npm first |
| Old npm version | Some packages need newer npm | Not our concern for eslint/prettier |
| Network down | registry.npmjs.org unreachable | Error analysis |
| Conflicting global versions | npm warns but installs | Acceptable |

---

## cargo (Rust)

### Identity

| Property | Value |
|----------|-------|
| **Language** | Rust |
| **Registry** | crates.io |
| **Install dir** | `~/.cargo/bin/` |
| **Source cache** | `~/.cargo/registry/` |
| **Build dir** | Target crate's temp build dir |
| **Needs sudo** | No (installs to `~/.cargo/`) |

### How we use it

cargo installs Rust-based tools from crates.io:

```python
["cargo", "install", "cargo-audit"]
```

### Current tools (2)

| Tool | Install | Update | Requires binaries | Requires packages |
|------|---------|--------|-------------------|-------------------|
| cargo-audit | `["cargo", "install", "cargo-audit"]` | Same as install | cargo | openssl dev headers |
| cargo-outdated | `["cargo", "install", "cargo-outdated"]` | Same as install | cargo | openssl + curl dev headers |

### Recipe pattern

```python
"cargo-audit": {
    "label": "cargo-audit",
    "install": {"_default": ["cargo", "install", "cargo-audit"]},
    "needs_sudo": {"_default": False},
    "requires": {
        "binaries": ["cargo"],
        "packages": {
            "debian": ["pkg-config", "libssl-dev"],
            "rhel":   ["pkgconf-pkg-config", "openssl-devel"],
            "alpine": ["pkgconf", "openssl-dev"],
            "arch":   ["pkgconf", "openssl"],
            "suse":   ["pkg-config", "libopenssl-devel"],
            "macos":  ["pkg-config", "openssl@3"],
        },
    },
    "verify": ["cargo", "audit", "--version"],
    "update": {"_default": ["cargo", "install", "cargo-audit"]},
},
```

### Dependency chain

cargo tools have the DEEPEST dependency chains in the system:

```
cargo-audit
  → cargo (binary dependency)
    → curl (binary dependency of cargo, needed for rustup)
  → pkg-config + libssl-dev (system packages, needed for compilation)
```

The resolver walks this recursively:
1. `cargo-audit` requires `cargo`
2. `cargo` requires `curl`
3. `curl` is a batchable system package
4. `cargo-audit` requires system packages (keyed by family)

### cargo as a dependency (runtime install)

cargo is NOT a system package. It's installed via rustup:

```python
"cargo": {
    "label": "Cargo (Rust)",
    "install": {
        "_default": [
            "bash", "-c",
            "curl --proto '=https' --tlsv1.2 -sSf "
            "https://sh.rustup.rs | sh -s -- -y",
        ],
    },
    "needs_sudo": {"_default": False},
    "requires": {"binaries": ["curl"]},
    "post_env": 'export PATH="$HOME/.cargo/bin:$PATH"',
    "verify": ["bash", "-c",
              'export PATH="$HOME/.cargo/bin:$PATH" && cargo --version'],
    "update": {"_default": ["bash", "-c",
              'export PATH="$HOME/.cargo/bin:$PATH" && rustup update']},
},
```

**Key details:**
- Installs to `~/.cargo/bin/` (user-space, no sudo)
- `post_env` adds cargo to PATH for subsequent steps
- rustup installs both `cargo` and `rustc`
- **Resolved:** cargo `needs_sudo` is `{"_default": False}` in
  `TOOL_RECIPES`. No sudo bug exists in the current recipe format.

### System packages for compilation

cargo tools compile from source. They need C libraries and headers:

| Library | Why needed | Package varies by family |
|---------|-----------|------------------------|
| OpenSSL | TLS/crypto (cargo-audit uses it) | Yes (6 different names) |
| libcurl | HTTP client (cargo-outdated uses it) | Yes (6 different names) |
| pkg-config | Build-time lib discovery | Yes (2 different names) |

These are installed as SYSTEM packages (via apt/dnf/apk) BEFORE
the `cargo install` step runs.

### Build performance

| Factor | Impact |
|--------|--------|
| CPU cores | More cores = faster (cargo uses parallel compilation) |
| RAM | cargo-audit needs ~1GB, cargo-outdated needs ~1.5GB |
| Disk | Source + build artifacts: 200-500MB per tool |
| Time | cargo-audit: 2-5 min, cargo-outdated: 3-8 min |
| Alpine (musl) | May be slower due to musl vs glibc optimizations |

### post_env and wrapping

When cargo is installed for the first time, `~/.cargo/bin` is NOT
on PATH until the user starts a new shell. The `post_env` mechanism
solves this:

```python
# Resolver wraps subsequent steps:
["bash", "-c", 'export PATH="$HOME/.cargo/bin:$PATH" && cargo install cargo-audit']
["bash", "-c", 'export PATH="$HOME/.cargo/bin:$PATH" && cargo audit --version']
```

If cargo was ALREADY on PATH (pre-existing install), wrapping is
skipped — the `post_env` is only accumulated when cargo is freshly
installed during the current plan.

### Edge cases

| Case | Impact | Handling |
|------|--------|---------|
| Compilation fails (missing headers) | cargo install errors out | Error analysis checks system packages |
| Disk space insufficient | Build fills disk | NOT IMPLEMENTED: check disk_free_gb |
| OOM during compilation | Process killed | NOT IMPLEMENTED: check available RAM |
| Cargo already installed but outdated | `cargo install` re-compiles | Acceptable |
| rustup already installed | `rustup` script detects, updates | Safe to re-run |
| Network down | Can't download crates | Error analysis |

---

## Runtimes as Dependencies

Language PMs themselves must be installed before their tools can be
installed. This creates the following dependency hierarchy:

```
pip tools (ruff, mypy, ...)
  └── pip ← always available (app runs in Python venv)

npm tools (eslint, prettier)
  └── npm ← may need installing (system package)
      └── nodejs ← npm is bundled with node on some distros

cargo tools (cargo-audit, cargo-outdated)
  └── cargo ← may need installing (rustup script)
      └── curl ← may need installing (system package)
```

### Runtime recipe lookup

The resolver looks up dependencies in the recipe dict. If `npm` is
in `requires.binaries`, the resolver does:

1. `shutil.which("npm")` → on PATH? Skip.
2. Not found → look up `TOOL_RECIPES["npm"]` for install recipe
3. Recursively resolve npm's own dependencies
4. Insert npm install steps BEFORE the npm tool's steps

### Runtime install patterns

| Runtime | Install type | Needs sudo? | post_env? |
|---------|-------------|------------|-----------|
| pip | Pre-installed (venv) | — | No |
| npm | System package (apt/dnf/apk) | Yes | No (goes to /usr/bin/) |
| cargo | curl script (rustup) | No | Yes (`~/.cargo/bin`) |
| go | System package or binary download | Depends | May need (`~/go/bin`) |

---

## NOT IMPLEMENTED Language PMs (Phase 4+)

### go (Go modules)

```python
# Binary install via go
["go", "install", "golang.org/x/tools/gopls@latest"]

# Installs to: $GOPATH/bin/ or ~/go/bin/
# Needs GOPATH/GOBIN on PATH
```

Not currently in the system. Would follow the cargo pattern
(binary dependency + post_env for PATH).

### gem (Ruby)

```python
# Global gem install
["gem", "install", "rubocop"]

# Installs to: /usr/local/lib/ruby/gems/ (system) or ~/.gem/ (user)
# Needs sudo for system install
```

Not currently in the system. Not planned for Phase 2.

### composer (PHP)

```python
# Global composer install
["composer", "global", "require", "phpstan/phpstan"]

# Installs to: ~/.config/composer/vendor/bin/
# Needs PATH update
```

Not currently in the system. Not planned for Phase 2.

---

## Registry and Network

All language PMs require network access to their registries:

| PM | Registry | URL | Fallback |
|----|----------|-----|----------|
| pip | PyPI | https://pypi.org/simple/ | Private index URL |
| npm | npmjs | https://registry.npmjs.org/ | Private registry |
| cargo | crates.io | https://index.crates.io/ | Alternative registry |

### Network detection integration (NOT IMPLEMENTED — Phase 4)

```python
"network": {
    "endpoints": {
        "pypi.org": {"reachable": True, "latency_ms": 45},
        "registry.npmjs.org": {"reachable": True, "latency_ms": 120},
    },
}
```

If a registry is unreachable:
- Disable install methods that depend on it
- Provide clear error: "pypi.org is unreachable — pip installs will fail"
- Suggest: proxy config, VPN, or offline alternative

### Proxy support

| PM | Proxy config | Env var |
|----|-------------|---------|
| pip | `pip install --proxy http://proxy:8080` | `HTTP_PROXY`, `HTTPS_PROXY` |
| npm | `npm config set proxy http://proxy:8080` | `HTTP_PROXY`, `HTTPS_PROXY` |
| cargo | `.cargo/config.toml: [http] proxy = ...` | `CARGO_HTTP_PROXY` |

---

## Comparison: Language PM vs System PM for the Same Tool

Some tools can be installed either way:

| Tool | System PM | Language PM | Which we prefer |
|------|-----------|-------------|----------------|
| git | apt install git | — | System PM (only option) |
| ruff | — | pip install ruff | Language PM (only option) |
| node | apt install nodejs | nvm install node | System PM (Phase 2) |
| python | apt install python3 | pyenv install | System PM (Phase 2) |
| cmake | apt install cmake | pip install cmake | System PM |

In Phase 2, the resolver uses the recipe's `install` keys.
There's no dynamic "should I use pip or apt?" decision.
The recipe author makes that choice when writing the recipe.

---

## Traceability

| Topic | Source |
|-------|--------|
| `_PIP` constant | tool_install.py line 31 (implemented) |
| pip tool recipes | phase2.2 §Category 1 (7 tools) |
| npm tool recipes | phase2.2 §Category 2 (2 tools) |
| cargo tool recipes | phase2.2 §Category 3 (2 tools) |
| cargo/rustup runtime | phase2.2 §Category 4 |
| post_env mechanics | arch-recipe-format §post_env |
| npm permission issue | phase2.2 §Category 2 (EACCES note) |
| System package names for cargo | phase2.2 §Category 3 (per-family tables) |
| Private registries | scope-expansion §2.15 |
| Network detection | scope-expansion §2.16, arch-system-model §network |
| PyTorch pip index | scope-expansion §2.9 (GPU variant) |
