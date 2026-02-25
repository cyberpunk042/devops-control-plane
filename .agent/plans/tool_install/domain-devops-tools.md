# Domain: DevOps Tools

> This document catalogs the current tool scope: the 42 CLI tools
> that the install system manages. Categories, install methods,
> dependencies, lifecycle, and what Phase 2 actually implements.
> This is the concrete inventory — not future tools.
>
> SOURCE DOCS: tool_install.py (current source code, exact recipes),
>              phase2.2 §1.1-1.3 (tool-by-tool inventory + gaps),
>              phase2.3 scenarios (install flows),
>              domain-package-managers (PM commands)

---

## Overview

The tool install system manages **42 tools** across 5 install
methods. These are all CLI tools used for DevOps workflows:
development, containerization, infrastructure, security, and
quality.

### The code today

```python
# tool_install.py — two dicts
_NO_SUDO_RECIPES  # 11 tools (pip, npm, cargo — user-space)
_SUDO_RECIPES     # 31 tools (apt, snap, bash-curl — system-level)
```

Phase 2 replaces these with a unified `TOOL_RECIPES` dict.

---

## Full Tool Inventory

### Category: Python Quality (7 tools)

| Tool | Install method | Package | Needs sudo | Category |
|------|---------------|---------|-----------|----------|
| ruff | pip | ruff | ❌ | Linter |
| mypy | pip | mypy | ❌ | Type checker |
| pytest | pip | pytest | ❌ | Test runner |
| black | pip | black | ❌ | Formatter |
| pip-audit | pip | pip-audit | ❌ | Security |
| safety | pip | safety | ❌ | Security |
| bandit | pip | bandit | ❌ | Security |

**Common traits:**
- All use `_PIP + ["install", PACKAGE]`
- All run in venv or user-space (`--user`)
- No sudo required
- No system dependencies
- Runtime dependency: `python3` + `pip`

### Category: JavaScript Quality (2 tools)

| Tool | Install method | Package | Needs sudo | Category |
|------|---------------|---------|-----------|----------|
| eslint | npm -g | eslint | ❌ | Linter |
| prettier | npm -g | prettier | ❌ | Formatter |

**Common traits:**
- Use `["npm", "install", "-g", PACKAGE]`
- Runtime dependency: `npm` (which requires `node`)
- Global install (`-g`) may need sudo without nvm
- EACCES error handling documented in domain-language-pms

### Category: Rust Security (2 tools)

| Tool | Install method | Package | Needs sudo | Category |
|------|---------------|---------|-----------|----------|
| cargo-audit | cargo install | cargo-audit | ❌ | Security |
| cargo-outdated | cargo install | cargo-outdated | ❌ | Outdated deps |

**Common traits:**
- Use `["cargo", "install", PACKAGE]`
- Runtime dependency: `cargo` (which requires `rustc`, via rustup)
- System build dependencies: `pkg-config`, `libssl-dev`, `libcurl4-openssl-dev`
  (Debian names — see domain-compilers for cross-platform names)
- Long compile time (~2-5 min)

### Category: Container & Orchestration (7 tools)

| Tool | Install method | Package | Needs sudo | Category |
|------|---------------|---------|-----------|----------|
| docker | apt | docker.io | ✅ | Container runtime |
| docker-compose | apt | docker-compose-v2 | ✅ | Multi-container |
| kubectl | snap | kubectl --classic | ✅ | K8s CLI |
| helm | bash-curl | get-helm-3 script | ✅ | K8s package manager |
| skaffold | binary download | skaffold-linux-amd64 | ✅ | K8s dev workflow |
| trivy | bash-curl | install.sh | ✅ | Container scanner |
| terraform | snap | terraform --classic | ✅ | Infrastructure-as-Code |

**Common traits:**
- All need sudo (system-level install)
- Docker needs post-install: usermod -aG docker $USER + newgrp
- kubectl/helm/skaffold work together for K8s workflows
- Binary downloads are hardcoded to amd64 (Phase 4 fixes this)

### Category: Version Control (2 tools)

| Tool | Install method | Package | Needs sudo | Category |
|------|---------------|---------|-----------|----------|
| git | apt | git | ✅ | VCS |
| gh | snap | gh | ✅ | GitHub CLI |

### Category: Language Runtimes (6 tools)

| Tool | Install method | Package | Needs sudo | Category |
|------|---------------|---------|-----------|----------|
| python | apt | python3 | ✅ | Python runtime |
| pip | apt | python3-pip | ✅ | Python package mgr |
| node | snap | node --classic | ✅ | Node.js runtime |
| npm | apt | npm | ✅ | Node package mgr |
| npx | apt | npm | ✅ | Node runner (bundled with npm) |
| go | snap | go --classic | ✅ | Go runtime |
| cargo | bash-curl | rustup.rs | ❌* | Rust toolchain |
| rustc | bash-curl | rustup.rs | ❌* | Rust compiler |

*cargo/rustc: marked as `install_type: "sudo"` in `_SUDO_RECIPES`
but the actual script installs to `~/.cargo` (no sudo needed).
This is a **known bug** documented in phase2.2 §1.2.

### Category: System Utilities (10 tools)

| Tool | Install method | Package | Needs sudo | Category |
|------|---------------|---------|-----------|----------|
| curl | apt | curl | ✅ | HTTP client |
| jq | apt | jq | ✅ | JSON processor |
| make | apt | make | ✅ | Build tool |
| gzip | apt | gzip | ✅ | Compression |
| dig | apt | dnsutils | ✅ | DNS query |
| openssl | apt | openssl | ✅ | TLS/crypto |
| rsync | apt | rsync | ✅ | File sync |
| ffmpeg | apt | ffmpeg | ✅ | Media processing |
| expect | apt | expect | ✅ | Automation |

**Note:** `dig` installs `dnsutils` on Debian. Package name
differs across families (see domain-package-managers).

### Category: Terminal Emulators (5 tools)

| Tool | Install method | Package | Needs sudo | Category |
|------|---------------|---------|-----------|----------|
| xterm | apt | xterm | ✅ | Terminal |
| gnome-terminal | apt | gnome-terminal | ✅ | Terminal |
| xfce4-terminal | apt | xfce4-terminal | ✅ | Terminal |
| konsole | apt | konsole | ✅ | Terminal |
| kitty | apt | kitty | ✅ | Terminal |

**Purpose:** Used for interactive spawn (opening tool in
separate terminal window).

---

## Install Methods Summary

| Method | Count | Needs sudo | Example |
|--------|-------|-----------|---------|
| apt-get | 23 | ✅ | `apt-get install -y git` |
| snap | 5 | ✅ | `snap install kubectl --classic` |
| pip | 7 | ❌ | `python -m pip install ruff` |
| npm -g | 2 | ❌* | `npm install -g eslint` |
| cargo install | 2 | ❌ | `cargo install cargo-audit` |
| bash-curl | 4 | Mixed | `curl ... \| bash` |
| binary download | 1 | ✅ | `curl -Lo /usr/local/bin/skaffold ...` |

*npm -g may need sudo depending on npm installation method.

---

## Dependency Chains

### Runtime dependencies

```python
# From _TOOL_REQUIRES
_TOOL_REQUIRES = {
    "cargo-audit":    "cargo",
    "cargo-outdated": "cargo",
}

# From _RUNTIME_DEPS
_RUNTIME_DEPS = {
    "cargo": {"label": "Rust toolchain", "install": "cargo"},
}
```

### Implicit dependencies (not declared, caught at runtime)

| Tool | Implicit dep | How detected |
|------|-------------|-------------|
| eslint | npm | `cmd[0] == "npm"` check in `install_tool()` |
| prettier | npm | `cmd[0] == "npm"` check |
| cargo-audit | cargo | `_TOOL_REQUIRES` lookup |
| cargo-outdated | cargo | `_TOOL_REQUIRES` lookup |
| cargo-audit | pkg-config, libssl-dev, libcurl4-openssl-dev | `_analyse_install_failure` (post-failure) |
| helm | curl | Implicit in bash script |
| trivy | curl | Implicit in bash script |
| skaffold | curl | Implicit in bash script |
| pip tools | python3 | _PIP uses `sys.executable` |

### Phase 2 fixes

All dependencies will be EXPLICIT in `TOOL_RECIPES`:
```python
"cargo-audit": {
    "requires": {
        "binaries": ["cargo"],
        "system_deps": {
            "debian": ["pkg-config", "libssl-dev", "libcurl4-openssl-dev"],
            "rhel": ["pkgconf-pkg-config", "openssl-devel", "libcurl-devel"],
            # ...
        },
    },
}
```

---

## Tool Lifecycle

### Install flow (current)

```
1. Check if tool exists: shutil.which(tool)
2. If exists: return "already installed"
3. Check runtime dep: _TOOL_REQUIRES[tool] → dep binary
4. If dep missing: install dep first (recursive)
5. Execute install command from _NO_SUDO/_SUDO_RECIPES
6. Verify: shutil.which(tool) after install
```

### Update flow (Phase 2)

```python
"update": {
    "pip": _PIP + ["install", "--upgrade", PACKAGE],
    "apt": ["apt-get", "install", "--only-upgrade", "-y", PACKAGE],
    "snap": ["snap", "refresh", PACKAGE],
    "npm": ["npm", "update", "-g", PACKAGE],
    "cargo": ["cargo", "install", PACKAGE],  # reinstalls latest
}
```

### Remove flow (Phase 2+)

```python
"remove": {
    "pip": _PIP + ["uninstall", "-y", PACKAGE],
    "apt": ["apt-get", "remove", "-y", PACKAGE],
    "snap": ["snap", "remove", PACKAGE],
    "npm": ["npm", "uninstall", "-g", PACKAGE],
    "cargo": ["cargo", "uninstall", PACKAGE],
}
```

---

## Known Issues (Phase 2 Resolves)

| Issue | Impact | Fix in Phase 2 |
|-------|--------|---------------|
| All apt recipes hardcoded Debian names | Fails on RHEL, Alpine, Arch | Per-family package names in TOOL_RECIPES |
| cargo/rustc marked as sudo but isn't | Unnecessary password prompt | `needs_sudo: False` in recipe |
| npm/npx both install `npm` package | Redundant | Single recipe, npx as alias |
| System deps only declared for cargo | pip builds with native extensions fail silently | `system_deps` for all tools needing native libs |
| No update commands | Can't upgrade tools | `update` field in recipe |
| No verify commands | Can't confirm tool works after install | `verify` field in recipe |
| No post-install steps | Docker user group not added automatically | `post_install` field in recipe |
| Binary downloads hardcoded amd64 | Fails on ARM | Architecture interpolation (Phase 4) |
| snap assumed available | Fails on RHEL, Alpine | Fallback install methods per platform |

---

## Tool Categories for UI

| Category | Tools | Icon |
|----------|-------|------|
| Container & K8s | docker, docker-compose, kubectl, helm, skaffold, terraform | 🐳 |
| Security | trivy, pip-audit, safety, bandit, cargo-audit, cargo-outdated | 🔒 |
| Quality | ruff, mypy, black, eslint, prettier | ✅ |
| Testing | pytest | 🧪 |
| VCS | git, gh | 📦 |
| Runtimes | python, pip, node, npm, npx, go, cargo, rustc | ⚙️ |
| Utilities | curl, jq, make, gzip, dig, openssl, rsync, ffmpeg, expect | 🔧 |
| Terminals | xterm, gnome-terminal, xfce4-terminal, konsole, kitty | 💻 |

---

## What Phase 2 Does NOT Cover

Tools that exist in the scope expansion but are NOT in the
current 42-tool list:

| Future tool | Why not in Phase 2 | Phase |
|------------|-------------------|-------|
| PyTorch, TensorFlow | ML frameworks need GPU variants | Phase 6-7 |
| spaCy, NLTK, HuggingFace | Need data pack UI | Phase 7 |
| nginx, Apache | Service management complexity | Phase 3+ |
| Prometheus, Grafana | Service management + config | Phase 3+ |
| OpenCV | Build-from-source pipeline | Phase 5 |
| Tesseract | Data packs (OCR language data) | Phase 7 |

---

## Traceability

| Topic | Source |
|-------|--------|
| _NO_SUDO_RECIPES (11 tools) | tool_install.py lines 34-46 |
| _SUDO_RECIPES (31 tools) | tool_install.py lines 49-83 |
| CARGO_BUILD_DEPS | tool_install.py line 88 |
| _TOOL_REQUIRES | tool_install.py lines 360-363 |
| _RUNTIME_DEPS | tool_install.py lines 354-358 |
| Tool-by-tool gap analysis | phase2.2 §1.1 (_NO_SUDO), §1.2 (_SUDO), §1.3 (CARGO) |
| Per-family package names | phase2.2 §1.2 (per-tool tables) |
| cargo sudo bug | phase2.2 §1.2 (important note) |
| Install flow scenarios | phase2.3 (10 scenarios) |
| PM commands | domain-package-managers (apt, dnf, etc.) |
| Package naming | domain-package-managers §package naming |
| pip venv model | domain-language-pms §pip |
| npm global install | domain-language-pms §npm |
| cargo build deps | domain-language-pms §cargo |
