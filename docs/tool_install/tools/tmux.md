# tmux — Full Spectrum Analysis

> **Tool ID:** `tmux`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | tmux — terminal multiplexer |
| Language | C |
| CLI binary | `tmux` |
| Category | `devtools` |
| Verify command | `tmux -V` (capital V, no `--`) |
| Recipe key | `tmux` |

### Special notes
- Classic Unix tool for managing multiple terminal sessions within a single window.
- Allows detaching/reattaching sessions — essential for remote server work.
- Written in C — one of the oldest and most widely packaged tools in the system.
- Available in ALL 6 native PMs — no `_default` binary download needed.
- No runtime dependencies — pre-compiled in all distro repos.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ✅ | `tmux` | Debian/Ubuntu |
| `dnf` | ✅ | `tmux` | Fedora/RHEL |
| `apk` | ✅ | `tmux` | Alpine |
| `pacman` | ✅ | `tmux` | Arch |
| `zypper` | ✅ | `tmux` | openSUSE |
| `brew` | ✅ | `tmux` | macOS |

---

## 3. Installation

| Platform | Command | PM |
|----------|---------|-----|
| Debian/Ubuntu | `apt-get install -y tmux` | apt |
| Fedora/RHEL | `dnf install -y tmux` | dnf |
| Alpine | `apk add tmux` | apk |
| Arch | `pacman -S --noconfirm tmux` | pacman |
| openSUSE | `zypper install -y tmux` | zypper |
| macOS | `brew install tmux` | brew |

---

## 4. Dependencies

No build or runtime dependencies — standalone C binary.
Dynamically links against standard system libraries (libc, libevent, ncurses)
which are always present in every distro.

---

## 5. Failure Handlers

### Layer 2a: method-family handlers (10 total)
| Family | Handlers |
|--------|----------|
| `apt` | 2 (stale index, locked) |
| `dnf` | 1 (no match) |
| `apk` | 2 (unsatisfiable, locked) |
| `pacman` | 2 (not found, locked) |
| `zypper` | 2 (not found, locked) |
| `brew` | 1 (no formula) |

### Layer 1: INFRA handlers (9 cross-tool)
All standard — network, disk, permissions, OOM, timeout.

### Layer 3: None needed.
No unique tmux-specific failure modes.

---

## 6. Validation Results

```
Schema:    VALID
Coverage:  361/361 (100%) — 19 scenarios × 19 presets
Handlers:  10 PM-specific + 9 INFRA = 19
```

---

## 7. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Added `cli: "tmux"` |
| `data/recipes.py` | Updated label to "tmux (terminal multiplexer)" |
| `data/recipes.py` | Added `prefer` list for all 6 PMs |
| `data/recipes.py` | Added `update` commands for all 6 PMs |

---

## 8. Platform Coverage

| Platform | Method | Notes |
|----------|--------|-------|
| **macOS** | brew | Standard formula |
| **Raspbian (aarch64)** | apt | Standard repos |
| **Debian/Ubuntu** | apt | Standard repos |
| **Fedora/RHEL** | dnf | Standard repos |
| **Alpine** | apk | Standard repos |
| **Arch** | pacman | Standard repos |
| **openSUSE** | zypper | Standard repos |

All presets have native PM coverage. No fallback needed.
