# semgrep — Full Spectrum Analysis

> **Tool ID:** `semgrep`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | Semgrep — SAST (static analysis security testing) |
| Language | Python + OCaml (core engine) |
| CLI binary | `semgrep` |
| Category | `security` |
| Verify command | `semgrep --version` |
| Recipe key | `semgrep` |

### Special notes
- By Semgrep Inc. (formerly r2c / Return to Corp).
- Supports 30+ languages for pattern-based code scanning.
- Python package wrapping a native OCaml binary engine.
- Requires Python 3.10+.
- Available via pip, brew, and snap.
- NOT in apt, dnf, apk, pacman, zypper.
- **snap has ARM64 support** — valuable for Raspbian.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `pip` | ✅ | `semgrep` | **Official/canonical** |
| `brew` | ✅ | `semgrep` | Standard formula |
| `snap` | ✅ | `semgrep` | ARM64 support, good alternative |
| `apt` | ❌ | — | Not available |
| `dnf` | ❌ | — | Not available |
| `apk` | ❌ | — | Not available |
| `pacman` | ❌ | — | Not available |
| `zypper` | ❌ | — | Not available |

---

## 3. Installation

### Via pip (_default)

| Field | Value |
|-------|-------|
| Method | `pip install semgrep` |
| Install location | Python site-packages + `~/.local/bin/semgrep` |
| Dependencies | Python 3.10+, pip |
| needs_sudo | No |
| install_via | `pip` |

### Via brew

| Field | Value |
|-------|-------|
| Method | `brew install semgrep` |
| needs_sudo | No |
| Notes | Handles Python deps automatically |

### Via snap

| Field | Value |
|-------|-------|
| Method | `snap install semgrep` |
| needs_sudo | Yes |
| Notes | ARM64 support, requires systemd |

### Platform considerations

- **macOS (arm64/Intel)**: brew preferred. pip also works.
- **Raspbian ARM (aarch64)**: snap preferred (ARM64 native).
  pip may work but OCaml binary wheels could fail on ARM.
- **Alpine**: pip only (no snap — no systemd). May need
  build deps for native wheels.
- **Debian/Ubuntu**: snap or pip. Modern Debian/Ubuntu may
  hit PEP 668 with pip → handler exists.
- **Arch**: pip. No pacman package. PEP 668 enforced.

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Runtime | Python 3.10+ | Required for pip install |
| Runtime | pip | For _default install method |

---

## 5. Post-install

When installed via pip with `--user`, binary goes to `~/.local/bin/`.
May need PATH addition: `export PATH=$HOME/.local/bin:$PATH`.

---

## 6. Failure Handlers

### Layer 2b: install_via family (pip — 11 handlers)
| Handler | Category | Trigger |
|---------|----------|---------|
| `pep668` | environment | Externally managed Python |
| `pip_venv_not_available` | dependency | python3-venv missing |
| `pip_system_install_warning` | environment | pip into system Python |
| `missing_pip` | dependency | pip not installed |
| `pip_permission_denied` | permissions | Permission denied |
| `pip_version_conflict` | dependency | Dep version conflict |
| `pip_hash_mismatch` | network | Hash mismatch |
| `pip_build_wheel_failed` | compiler | Wheel build failed |
| `pip_no_matching_dist` | dependency | Package not found |
| `pip_ssl_error` | network | SSL cert error |
| `pip_python_version` | compatibility | Python version too old |

### Layer 2a: method-family handlers (shared)
| Family | Handler | Trigger |
|--------|---------|---------|
| `brew` | `brew_no_formula` | Formula not found |
| `snap` | `snapd_unavailable` | snapd not running |
| `_default` | `missing_curl` | curl not installed |
| `_default` | `missing_git` | git not installed |
| `_default` | `missing_wget` | wget not installed |
| `_default` | `missing_unzip` | unzip not installed |
| `_default` | `missing_npm_default` | npm not installed |

### Layer 1: INFRA handlers (9 cross-tool)
Network, disk, permissions, OOM, timeout — all standard.

### Layer 3: per-tool on_failure handlers
None needed. Standard pip + brew + snap install.

---

## 7. Recipe Structure

```python
"semgrep": {
    "cli": "semgrep",
    "label": "Semgrep (SAST — static analysis security testing)",
    "category": "security",
    "install": {
        "brew":    ["brew", "install", "semgrep"],
        "snap":    ["snap", "install", "semgrep"],
        "_default": _PIP + ["install", "semgrep"],
    },
    "needs_sudo": {"brew": False, "snap": True, "_default": False},
    "install_via": {"_default": "pip"},
    "prefer": ["brew", "snap"],
    "verify": ["semgrep", "--version"],
    "update": {
        "brew":    ["brew", "upgrade", "semgrep"],
        "snap":    ["snap", "refresh", "semgrep"],
        "_default": _PIP + ["install", "--upgrade", "semgrep"],
    },
}
```

---

## 8. Validation Results

```
Schema:    VALID (recipe + all method-family handlers)
Coverage:  513/513 (100%) — 27 scenarios × 19 presets
Handlers:  1 brew + 1 snap + 5 _default + 11 pip + 9 INFRA = 27 total
```

---

## 9. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Added `cli: "semgrep"` |
| `data/recipes.py` | Updated label to include SAST expansion |
| `data/recipes.py` | Added `snap` install method (ARM64 support) |
| `data/recipes.py` | Added `prefer: ["brew", "snap"]` |
| `data/recipes.py` | Added `snap` update command |

---

## 10. Platform Coverage

| Platform | Method | Notes |
|----------|--------|-------|
| **macOS (arm64/Intel)** | brew preferred | Handles deps |
| **Raspbian (aarch64)** | snap preferred | ARM64 native, no pip wheel issues |
| **Debian/Ubuntu** | snap or pip | PEP 668 handler for pip |
| **Alpine** | pip only | No snap (no systemd) |
| **Arch** | pip | PEP 668 enforced |
| **Fedora/SUSE** | pip or snap | Standard install |

---

## 11. Future Enhancements

- **Config file support**: Could check for `.semgrep.yml` or
  `.semgrepignore` and suggest creating one.
- **CI integration**: Could offer CI pipeline config generation
  for GitHub Actions / GitLab CI.
