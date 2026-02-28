# gcloud — Full Spectrum Analysis

> **Tool ID:** `gcloud`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | gcloud — Google Cloud SDK command-line interface |
| Language | Python |
| Author | Google Cloud |
| CLI binary | `gcloud` |
| Category | `cloud` |
| Verify command | `gcloud --version` (needs PATH to SDK bin) |
| Recipe key | `gcloud` |

### Special notes
- Part of Google Cloud SDK — includes `gcloud`, `gsutil`, `bq`, and other tools.
- Written in Python. Bundles its own Python runtime.
- Google provides official apt/dnf repos but they require adding Google's
  signing key and configuring the repo — complex multi-step setup.
- snap method is simpler: `google-cloud-cli --classic`.
- brew formula: `google-cloud-sdk`.
- _default installer pipes to bash — installs to `$HOME/google-cloud-sdk`.
- Update via `gcloud components update` when installed from script.
- NOT in apk, pacman, zypper, pip.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ✅ | `google-cloud-cli` | Needs Google repo + key |
| `dnf` | ✅ | `google-cloud-cli` | Needs Google repo + key |
| `apk` | ❌ | — | Not in Alpine repos |
| `pacman` | ❌ | — | AUR only |
| `zypper` | ❌ | — | Not in openSUSE repos |
| `brew` | ✅ | `google-cloud-sdk` | macOS/Linux |
| `snap` | ✅ | `google-cloud-cli` | `--classic` — **preferred** |
| `_default` | ✅ | — | Official `curl \| bash` installer |

apt/dnf omitted from recipe because they need complex repo setup.

---

## 3. Installation

| Platform | Command | PM |
|----------|---------|-----|
| Linux (preferred) | `snap install google-cloud-cli --classic` | snap |
| macOS/Linux | `brew install google-cloud-sdk` | brew |
| Any (fallback) | Official installer script | _default |

### snap method (preferred for Linux)
```bash
sudo snap install google-cloud-cli --classic
```
- Requires systemd.

### brew method
```bash
brew install google-cloud-sdk
```

### _default method (installer script)
```bash
curl -sSL https://sdk.cloud.google.com | bash -s -- --disable-prompts --install-dir=$HOME
```
- **No sudo needed** — installs to `$HOME/google-cloud-sdk`.
- Requires `curl`.
- `install_via: curl_pipe_bash`.

### Post-install
```bash
export PATH="$HOME/google-cloud-sdk/bin:$PATH"
```

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Download | `curl` | For _default method |

No C library dependencies — self-contained SDK.

---

## 5. Failure Handlers

### Layer 2a: method-family handlers (10 total)
| Family | Handlers |
|--------|----------|
| `snap` | 1 (snapd not running) |
| `brew` | 1 (no formula) |
| `_default` | 5 (missing curl/git/wget/unzip/npm) |
| `curl_pipe_bash` | 3 (TLS, unsupported arch, script 404) |

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
| `data/recipes.py` | Added `cli: "gcloud"` (was missing) |
| `data/recipes.py` | Updated label to "Google Cloud SDK (gcloud CLI)" |
| `data/recipes.py` | Added `update` commands for all 3 methods |
| `data/recipes.py` | Reordered methods (snap first as preferred) |
| `data/recipes.py` | Added research comments |

---

## 8. Platform Coverage

| Platform | Method | Notes |
|----------|--------|-------|
| **macOS** | brew | Formula: `google-cloud-sdk` |
| **Linux with snap** | snap | **Preferred** — `google-cloud-cli` |
| **Debian/Ubuntu** | snap or _default | apt needs repo setup — skipped |
| **Fedora/RHEL** | _default | dnf needs repo setup — skipped |
| **Alpine** | _default | Not in apk |
| **Arch** | _default | AUR only — skipped |
| **openSUSE** | _default | Not in zypper |
| **Raspbian** | _default | No snap on Raspbian |
| **WSL** | snap or _default | snap depends on WSL2 systemd |
| **Any (fallback)** | _default | Official installer script |

snap preferred for Linux (simple, auto-updates).
brew for macOS. Script installer as universal fallback.
