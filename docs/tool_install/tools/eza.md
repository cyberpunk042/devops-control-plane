# eza — Full Spectrum Analysis

> **Tool ID:** `eza`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | eza — modern ls replacement |
| Language | Rust |
| CLI binary | `eza` |
| Category | `devtools` |
| Verify command | `eza --version` |
| Recipe key | `eza` |

### Special notes
- Community fork of `exa` (unmaintained since 2023).
- Colorized output, Git integration, tree view, icons.
- Written in Rust — **not available in all native PMs**.
- NOT in `apk` (Alpine) or `zypper` (openSUSE).
- `apt` availability starts from Ubuntu 24.04+.
- `_default` uses `cargo install` — needs Rust toolchain.
- Unique among devtools: **only tool using cargo as fallback**.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ✅ | `eza` | Ubuntu 24.04+ only |
| `dnf` | ✅ | `eza` | Fedora 39+ |
| `apk` | ❌ | — | Not in Alpine repos |
| `pacman` | ✅ | `eza` | Arch community |
| `zypper` | ❌ | — | Not in openSUSE repos |
| `brew` | ✅ | `eza` | macOS |

---

## 3. Installation

| Platform | Command | PM |
|----------|---------|-----|
| Debian/Ubuntu (24.04+) | `apt-get install -y eza` | apt |
| Fedora/RHEL | `dnf install -y eza` | dnf |
| Arch | `pacman -S --noconfirm eza` | pacman |
| macOS | `brew install eza` | brew |
| Fallback | `cargo install eza` | _default |

### _default method (cargo)
```bash
cargo install eza
```
- **No sudo needed** — installs to `~/.cargo/bin`.
- Requires full Rust toolchain (`rustc`, `cargo`).
- May also need C compiler (`gcc`/`cc`) and system libraries for linking.
- `install_via: cargo` — triggers cargo-specific failure handlers.

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Build | `cargo` | For _default method |
| Build | `rustc` | Rust compiler (cargo handler checks version) |
| Build | `gcc`/`cc` | C compiler for native deps |

No runtime dependencies — standalone binary after compilation.

---

## 5. Failure Handlers

### Layer 2a: method-family handlers (17 total)
| Family | Handlers |
|--------|----------|
| `apt` | 2 (stale index, locked) |
| `dnf` | 1 (no match) |
| `pacman` | 2 (not found, locked) |
| `brew` | 1 (no formula) |
| `_default` | 5 (missing curl/git/wget/unzip/npm) |
| `cargo` | 6 (rustc version, gcc bug, missing C lib, missing compiler, pkg-config, pkg-config lib) |

### Layer 1: INFRA handlers (9 cross-tool)
All standard — network, disk, permissions, OOM, timeout.

### Layer 3: None needed.
No unique eza-specific failure modes. Cargo handlers cover all
build-from-source failures generically.

---

## 6. Validation Results

```
Schema:    VALID
Coverage:  494/494 (100%) — 26 scenarios × 19 presets
Handlers:  17 method-specific + 9 INFRA = 26
```

---

## 7. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Added `cli: "eza"` |
| `data/recipes.py` | Updated label to "eza (modern ls replacement)" |
| `data/recipes.py` | Added `prefer` list for native PMs |
| `data/recipes.py` | Added `update` commands for all 5 methods |
| `data/recipes.py` | Added research comments (availability gaps) |

---

## 8. Platform Coverage

| Platform | Method | Notes |
|----------|--------|-------|
| **macOS** | brew | Standard formula |
| **Debian/Ubuntu** | apt | Ubuntu 24.04+ only |
| **Fedora/RHEL** | dnf | Fedora 39+ |
| **Arch** | pacman | Community repos |
| **Alpine** | _default (cargo) | Not in apk — needs Rust toolchain |
| **openSUSE** | _default (cargo) | Not in zypper — needs Rust toolchain |
| **Raspbian (aarch64)** | _default (cargo) | Not in apt on older versions |

Alpine and openSUSE presets fall back to cargo. This is the narrowest
native PM coverage in the devtools stack.
