# zoxide — Full Spectrum Analysis

> **Tool ID:** `zoxide`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | zoxide — smarter cd command |
| Language | Rust |
| CLI binary | `zoxide` |
| Category | `devtools` |
| Verify command | `zoxide --version` |
| Recipe key | `zoxide` |

### Special notes
- By ajeetdsouza. Learns your most-used directories, provides smart jump.
- Inspired by `z`, `autojump`, and `fasd`. Written in Rust.
- Works with bash, zsh, fish, nushell, PowerShell, xonsh.
- Available in ALL 6 native PMs.
- `_default` uses official installer script — installs to `~/.local/bin` (no sudo).
- NOT available as snap.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ✅ | `zoxide` | Debian/Ubuntu |
| `dnf` | ✅ | `zoxide` | Fedora/RHEL |
| `apk` | ✅ | `zoxide` | Alpine 3.13+ |
| `pacman` | ✅ | `zoxide` | Arch |
| `zypper` | ✅ | `zoxide` | openSUSE |
| `brew` | ✅ | `zoxide` | macOS |
| `snap` | ❌ | — | Not available |

---

## 3. Installation

| Platform | Command | PM |
|----------|---------|-----|
| Debian/Ubuntu | `apt-get install -y zoxide` | apt |
| Fedora/RHEL | `dnf install -y zoxide` | dnf |
| Alpine | `apk add zoxide` | apk |
| Arch | `pacman -S --noconfirm zoxide` | pacman |
| openSUSE | `zypper install -y zoxide` | zypper |
| macOS | `brew install zoxide` | brew |
| Fallback | `curl -sS .../install.sh \| bash` | _default |

### _default method
```bash
curl -sS https://raw.githubusercontent.com/ajeetdsouza/zoxide/main/install.sh | bash
```
- **No sudo needed** — installs to `~/.local/bin`.
- Requires `curl`.
- `install_via: curl_pipe_bash` — triggers TLS, arch, and script 404 handlers.
- Update: re-run same command (idempotent).

### Post-install
Shell init required. Add to shell config:
- bash: `eval "$(zoxide init bash)"`
- zsh: `eval "$(zoxide init zsh)"`
- fish: `zoxide init fish | source`

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Download | `curl` | For _default method |

No runtime dependencies — standalone Rust binary.

---

## 5. Failure Handlers

### Layer 2a: method-family handlers (18 total)
| Family | Handlers |
|--------|----------|
| `apt` | 2 (stale index, locked) |
| `dnf` | 1 (no match) |
| `apk` | 2 (unsatisfiable, locked) |
| `pacman` | 2 (not found, locked) |
| `zypper` | 2 (not found, locked) |
| `brew` | 1 (no formula) |
| `_default` | 5 (missing curl/git/wget/unzip/npm) |
| `curl_pipe_bash` | 3 (TLS, unsupported arch, script 404) |

### Layer 1: INFRA handlers (9 cross-tool)
All standard — network, disk, permissions, OOM, timeout.

### Layer 3: None needed.
No unique zoxide-specific failure modes.

---

## 6. Validation Results

```
Schema:    VALID
Coverage:  513/513 (100%) — 27 scenarios × 19 presets
Handlers:  18 method-specific + 9 INFRA = 27
```

---

## 7. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Added `cli: "zoxide"` |
| `data/recipes.py` | Updated label to "zoxide (smarter cd command)" |
| `data/recipes.py` | Added `apk` and `zypper` install methods (2 new) |
| `data/recipes.py` | Added `prefer` list for all 6 native PMs |
| `data/recipes.py` | Added `update` commands for all 7 methods |
| `data/recipes.py` | Added research comments |

---

## 8. Platform Coverage

| Platform | Method | Notes |
|----------|--------|-------|
| **macOS** | brew | Standard formula |
| **Raspbian (aarch64)** | apt | Standard repos |
| **Debian/Ubuntu** | apt | Standard repos |
| **Fedora/RHEL** | dnf | Standard repos |
| **Alpine** | apk | Alpine 3.13+ |
| **Arch** | pacman | Standard repos |
| **openSUSE** | zypper | Standard repos |
| **Any (fallback)** | _default | Installer script (~/.local/bin) |

All presets have native PM coverage. _default provides user-local fallback
(no root required).
