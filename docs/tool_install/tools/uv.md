# uv — Full Spectrum Analysis

> **Tool ID:** `uv`
> **Last audited:** 2026-02-26
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | uv — extremely fast Python package and project manager |
| Language | Rust (compiled native binary) |
| CLI binary | `uv` |
| Category | `python` |
| Verify command | `uv --version` |
| Recipe key | `uv` |

### Special notes
- uv is written in **Rust**, NOT Python. It's a compiled native
  binary, unlike poetry (pure Python).
- Created by Astral (the team behind Ruff).
- Aims to replace pip, pip-tools, pipx, poetry, pyenv, virtualenv.
- The standalone installer downloads a **pre-built platform-specific
  binary** — not a Python package.
- Since v0.5.0, the installer installs to `~/.local/bin` (previously
  `~/.cargo/bin`). Our recipe was updated to reflect this.
- uv is available in more system PMs than poetry because of its
  rapid adoption.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `pip` | ✅ | `uv` | Python wrapper around native binary |
| `pipx` | ✅ | `uv` | Isolated install |
| `brew` | ✅ | `uv` | macOS/Linux Homebrew |
| `dnf` | ✅ | `uv` | Fedora 41+ |
| `apk` | ✅ | `uv` | Alpine edge/testing |
| `pacman` | ✅ | `uv` | Arch extra |
| `cargo` | ✅ | `uv` | Builds from source (slow) |
| `apt` | ❌ | — | Not in Debian repos yet |
| `zypper` | ❌ | — | Not in openSUSE repos yet |
| `snap` | ✅ | `astral-uv` | Available but not in recipe (snap name differs) |
| `npm` | ❌ | — | Not a JS tool |

### Package name notes
- uv is `uv` everywhere it's available — no name divergence.
- No KNOWN_PACKAGES entry needed.
- snap uses `astral-uv` but snap method not added (niche).

---

## 3. Install Method — _default (Astral standalone installer)

| Field | Value |
|-------|-------|
| Command | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Script | Official Astral installer |
| Install location | `$HOME/.local/bin/uv` (since v0.5.0) |
| Dependencies | `curl` (download) |
| needs_sudo | No |

### Platform coverage
The installer downloads a pre-built native binary:
- Linux x86_64 ✅ (native Rust binary)
- Linux aarch64 ✅
- Linux armv7l (Raspbian) ✅ (if available)
- macOS Intel ✅
- macOS Apple Silicon ✅

### Critical fix: install path change
The installer path changed in uv v0.5.0:
- **Before v0.5.0:** `~/.cargo/bin/uv`
- **After v0.5.0:** `~/.local/bin/uv`

Our recipe was updated to use the correct modern path.

### Post-install
```bash
export PATH="$HOME/.local/bin:$PATH"
```

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Download | `curl` | For `_default` installer |
| Build (cargo only) | Rust toolchain | Only if building from source |
| None (runtime) | — | uv is self-contained |

### Reverse deps
uv is used by:
- Modern Python projects wanting fast dependency resolution
- CI/CD pipelines (replaces pip for speed)
- Projects using `pyproject.toml` and `uv.lock`

---

## 5. Failure Handlers

### Layer 1: method-family handlers
uv inherits handlers from its install methods:

**pip (11 handlers):** PEP 668, version conflicts, SSL, etc.
**cargo (6 handlers):** Rust version, GCC bug, missing libs, pkg-config.
**Plus:** dnf (1), apk (2), pacman (2), brew (1), _default (5).

### Layer 2: INFRA handlers (9 cross-tool)
Network, disk, permissions, OOM, timeout — all standard.

### Layer 3: per-tool on_failure handlers

| Handler | Category | Trigger | Options |
|---------|----------|---------|---------|
| `uv_glibc_too_old` | compatibility | `GLIBC_2.28 not found` — compiled binary needs newer glibc | pip (recommended — bundles binary), pipx (isolated), cargo (build from source) |

---

## 6. Recipe Structure

```python
"uv": {
    "cli": "uv",
    "label": "uv (extremely fast Python package and project manager)",
    "category": "python",
    "install": {
        "pip":    ["pip", "install", "uv"],
        "pipx":   ["pipx", "install", "uv"],
        "dnf":    ["dnf", "install", "-y", "uv"],
        "apk":    ["apk", "add", "uv"],
        "pacman": ["pacman", "-S", "--noconfirm", "uv"],
        "cargo":  ["cargo", "install", "--locked", "uv"],
        "brew":   ["brew", "install", "uv"],
        "_default": [
            "bash", "-c",
            "curl -LsSf https://astral.sh/uv/install.sh | sh",
        ],
    },
    "needs_sudo": {
        "pip": False, "pipx": False,
        "dnf": True, "apk": True, "pacman": True,
        "cargo": False, "brew": False, "_default": False,
    },
    "prefer": ["_default", "brew", "pipx"],
    "requires": {"binaries": ["curl"]},
    "post_env": 'export PATH="$HOME/.local/bin:$PATH"',
    "verify": ["bash", "-c", '... && uv --version'],
    "update": {
        "pip":    ["pip", "install", "--upgrade", "uv"],
        "pipx":   ["pipx", "upgrade", "uv"],
        "brew":   ["brew", "upgrade", "uv"],
        "_default": [
            "bash", "-c",
            "curl -LsSf https://astral.sh/uv/install.sh | sh",
        ],
    },
}
```

---

## 7. Validation Results

```
Schema:    VALID (recipe + all method-family handlers + on_failure)
Coverage:  760/760 (100%) — 40 scenarios × 19 presets
Handlers:  11 pip + 6 cargo + 5 PM-family + 5 _default + 1 on_failure + 9 INFRA = 40 total
```

---

## 8. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Added `cli: "uv"` |
| `data/recipes.py` | Updated `label` to full description |
| `data/recipes.py` | Added `pip`, `pipx`, `dnf`, `apk`, `pacman`, `cargo` install methods |
| `data/recipes.py` | Added `prefer: ["_default", "brew", "pipx"]` |
| `data/recipes.py` | Added `needs_sudo` for all 8 methods |
| `data/recipes.py` | **Fixed `post_env`**: `~/.cargo/bin` → `~/.local/bin` (installer path changed in v0.5.0) |
| `data/recipes.py` | **Fixed `verify`**: Same path correction |
| `data/recipes.py` | Added `update` for pip, pipx, brew, _default |
| `data/remediation_handlers.py` | Fixed pre-existing cargo handler `packages` schema error (bare string → dict) |
| `data/tool_failure_handlers.py` | Added `uv_glibc_too_old` handler (3 options: pip, pipx, cargo) |

---

## 9. Design Notes

### Why _default is preferred over pip/pipx
uv is a **compiled Rust binary**. The standalone installer downloads
the pre-built binary directly — fast, no Python needed, no virtual
environment complexity. pip/pipx install a Python wrapper that
contains the binary, which is slower and adds unnecessary layers.

### Why cargo is included but not preferred
`cargo install --locked uv` builds from source. This is extremely
slow (10+ minutes) compared to the standalone installer (seconds).
It's available as a fallback for environments where only cargo is
available (e.g., Rust development containers).

### Why the install path changed
Before v0.5.0, the installer used `~/.cargo/bin` which confused
users into thinking uv was a cargo-installed tool. Since v0.5.0,
it uses `~/.local/bin` following the XDG convention.

### uv vs poetry design difference
Poetry is pure Python, installs via pip/pipx. uv is a compiled
Rust binary, downloads as a standalone executable. This fundamental
difference means:
- uv's `_default` is a binary download (like kubectl)
- poetry's `_default` is a Python script pipe to python3
