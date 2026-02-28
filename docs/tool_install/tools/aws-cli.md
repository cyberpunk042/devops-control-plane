# aws-cli — Full Spectrum Analysis

> **Tool ID:** `aws-cli`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | aws-cli v2 — Amazon Web Services command-line interface |
| Language | Python (v2 ships with embedded Python) |
| Author | Amazon Web Services |
| CLI binary | `aws` |
| Category | `cloud` |
| Verify command | `aws --version` |
| Recipe key | `aws-cli` |

### Special notes
- **Binary name mismatch**: recipe key is `aws-cli` but CLI binary is `aws`.
- v2 ships as a self-contained installer with embedded Python runtime.
- Official installer is a bundled `.zip` — **NOT** a pip package (v1 was pip-based).
- `pip install awscli` exists on PyPI but installs v1 — AWS discourages for v2.
- brew formula is `awscli` (not `aws-cli`).
- snap package is `aws-cli` with `--classic` confinement.
- `_default` uses `$(uname -m)` for runtime arch detection — works on x86_64 and aarch64.
- AWS URL pattern: `awscli-exe-linux-{x86_64|aarch64}.zip` — matches `uname -m` exactly.
- NOT in apt (v1 only via python3-awscli), dnf (v1 only), pacman, zypper.
- apk has it in Alpine community repo but may lag versions.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ⚠️ | `awscli` | v1 only — DO NOT USE for v2 |
| `dnf` | ⚠️ | `awscli` | v1 only — DO NOT USE for v2 |
| `apk` | ✅ | `aws-cli` | Alpine community — may lag |
| `pacman` | ❌ | — | AUR only (`aws-cli-v2`) |
| `zypper` | ❌ | — | Not in openSUSE repos |
| `brew` | ✅ | `awscli` | **Preferred** — always v2 |
| `snap` | ✅ | `aws-cli` | `--classic` confinement |
| `_default` | ✅ | — | Official bundled installer |

---

## 3. Installation

| Platform | Command | PM |
|----------|---------|-----|
| macOS/Linux (preferred) | `brew install awscli` | brew |
| Linux with snap | `snap install aws-cli --classic` | snap |
| Linux any arch (fallback) | Official zip installer | _default |

### brew method (preferred)
```bash
brew install awscli
```

### snap method
```bash
sudo snap install aws-cli --classic
```
- Requires systemd (snap uses systemd).

### _default method (official installer)
```bash
ARCH=$(uname -m) && \
  curl "https://awscli.amazonaws.com/awscli-exe-linux-${ARCH}.zip" \
  -o /tmp/awscliv2.zip && cd /tmp && unzip -qo awscliv2.zip \
  && sudo ./aws/install --update && rm -rf /tmp/aws /tmp/awscliv2.zip
```
- **Needs sudo** — installs to `/usr/local`.
- Requires `curl` and `unzip`.
- `install_via: github_release` — triggers GitHub release handlers.
- `$(uname -m)` auto-detects x86_64 or aarch64 — works on Raspbian/ARM.

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Download | `curl` | For _default method |
| Download | `unzip` | For _default method |

No C library dependencies — self-contained binary bundle.

---

## 5. Failure Handlers

### Layer 2a: method-family handlers (10 total)
| Family | Handlers |
|--------|----------|
| `brew` | 1 (no formula) |
| `snap` | 1 (snapd not running) |
| `_default` | 5 (missing curl/git/wget/unzip/npm) |
| `github_release` | 3 (rate limit, asset not found, extract failed) |

### Layer 1: INFRA handlers (9 cross-tool)
All standard — network, disk, permissions, OOM, timeout.

### Layer 3: None needed.

---

## 6. Validation Results

```
Schema:    VALID
Coverage:  361/361 (100%) — 19 scenarios × 19 presets
Handlers:  10 method-specific + 9 INFRA = 19
```

---

## 7. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Moved `cli: "aws"` to top |
| `data/recipes.py` | Updated label to include full description |
| `data/recipes.py` | Added `snap` install method |
| `data/recipes.py` | Added `install_via: github_release` for _default |
| `data/recipes.py` | Added `prefer: ["brew", "snap"]` |
| `data/recipes.py` | Added `update` for snap |
| `data/recipes.py` | Fixed hardcoded x86_64 → `$(uname -m)` for runtime arch |
| `data/recipes.py` | Removed platform dict — single _default list |
| `data/recipes.py` | Added research comments |

---

## 8. Platform Coverage

| Platform | Method | Notes |
|----------|--------|-------|
| **macOS** | brew | **Preferred** — formula `awscli` |
| **Linux with brew** | brew | Linuxbrew supported |
| **Linux with snap** | snap | `aws-cli --classic` |
| **Debian/Ubuntu** | snap or _default | apt has v1 only — skip |
| **Fedora/RHEL** | _default | dnf has v1 only — skip |
| **Alpine** | apk (community) | May lag versions |
| **Arch** | _default | AUR only — skipped |
| **openSUSE** | _default | Not in zypper |
| **Raspbian (aarch64)** | _default | `$(uname -m)` auto-detects aarch64 ✅ |
| **WSL** | snap or _default | Standard Linux methods |

brew preferred. snap for Linux systems with systemd.
Official installer as universal fallback.
