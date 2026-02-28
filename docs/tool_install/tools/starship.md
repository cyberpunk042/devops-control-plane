# starship — Full Spectrum Analysis

> **Tool ID:** `starship`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | starship — cross-shell customizable prompt |
| Language | Rust |
| CLI binary | `starship` |
| Category | `devtools` |
| Verify command | `starship --version` |
| Recipe key | `starship` |

### Special notes
- Minimal, blazing-fast, and infinitely customizable prompt for any shell.
- Works with bash, zsh, fish, PowerShell, Ion, Elvish, Tcsh, Nushell, Xonsh.
- Written in Rust — pre-compiled binary or installable via native PMs.
- Recommends a Nerd Font for proper icon/glyph display.
- **dnf requires COPR repo** (`atim/starship`) — non-standard, so skipped.
- Official installer script at `starship.rs/install.sh`.
- Previously had only brew + _default — expanded to 7 methods.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ✅ | `starship` | Debian 13+, Ubuntu |
| `dnf` | ⚠️ | `starship` | Requires COPR repo — **skipped** |
| `apk` | ✅ | `starship` | Alpine 3.13+ |
| `pacman` | ✅ | `starship` | Arch |
| `zypper` | ✅ | `starship` | openSUSE |
| `brew` | ✅ | `starship` | macOS |
| `snap` | ✅ | `starship` | Snapcraft |

---

## 3. Installation

| Platform | Command | PM |
|----------|---------|-----|
| Debian/Ubuntu | `apt-get install -y starship` | apt |
| Alpine | `apk add starship` | apk |
| Arch | `pacman -S --noconfirm starship` | pacman |
| openSUSE | `zypper install -y starship` | zypper |
| macOS | `brew install starship` | brew |
| Snap-enabled | `snap install starship` | snap |
| Fallback | `curl -sS https://starship.rs/install.sh \| sh -s -- -y` | _default |

### _default method
```bash
curl -sS https://starship.rs/install.sh | sh -s -- -y
```
- **Needs sudo** — installs to `/usr/local/bin`.
- `-y` flag: non-interactive confirmation.
- Official installer from starship.rs — handles OS/arch detection.
- `install_via: curl_pipe_bash` — triggers TLS, arch, and script 404 handlers.

### Post-install
Shell init required. Add to shell config:
- bash: `eval "$(starship init bash)"`
- zsh: `eval "$(starship init zsh)"`
- fish: `starship init fish | source`

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Download | `curl` | For _default method |
| Recommended | Nerd Font | For proper glyph rendering |

No runtime binary dependencies — standalone binary.

---

## 5. Failure Handlers

### Layer 2a: method-family handlers (18 total)
| Family | Handlers |
|--------|----------|
| `apt` | 2 (stale index, locked) |
| `apk` | 2 (unsatisfiable, locked) |
| `pacman` | 2 (not found, locked) |
| `zypper` | 2 (not found, locked) |
| `brew` | 1 (no formula) |
| `snap` | 1 (snapd unavailable) |
| `_default` | 5 (missing curl/git/wget/unzip/npm) |
| `curl_pipe_bash` | 3 (TLS, unsupported arch, script 404) |

### Layer 1: INFRA handlers (9 cross-tool)
All standard — network, disk, permissions, OOM, timeout.

### Layer 3: None needed.
No unique starship-specific failure modes.

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
| `data/recipes.py` | Added `cli: "starship"` |
| `data/recipes.py` | Updated label to "cross-shell customizable prompt" |
| `data/recipes.py` | Added `apt`, `apk`, `pacman`, `zypper`, `snap` methods (5 new) |
| `data/recipes.py` | Added `prefer` list for all 6 native PMs + snap |
| `data/recipes.py` | Added `update` commands for all 7 methods |
| `data/recipes.py` | Added research comments (COPR note, Nerd Font) |

---

## 8. Platform Coverage

| Platform | Method | Notes |
|----------|--------|-------|
| **macOS** | brew | Standard formula |
| **Raspbian (aarch64)** | apt | Debian repos |
| **Debian/Ubuntu** | apt | Debian 13+ |
| **Fedora/RHEL** | _default | dnf needs COPR — uses installer |
| **Alpine** | apk | Alpine 3.13+ |
| **Arch** | pacman | Standard repos |
| **openSUSE** | zypper | Standard repos |
| **Any with snap** | snap | Universal fallback |
| **Any (fallback)** | _default | Official installer script |

Fedora/RHEL uses _default fallback because dnf requires non-standard COPR repo.
All other presets have native PM coverage.
