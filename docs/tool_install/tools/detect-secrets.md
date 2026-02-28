# detect-secrets — Full Spectrum Analysis

> **Tool ID:** `detect-secrets`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | detect-secrets — secret detection in codebases |
| Language | Python |
| CLI binary | `detect-secrets` |
| Category | `security` |
| Verify command | `detect-secrets --version` |
| Recipe key | `detect-secrets` |

### Special notes
- By Yelp. Enterprise-grade secret detection.
- Designed for pre-commit hooks and CI/CD pipelines.
- Uses entropy-based detection + regex patterns.
- Maintains a `.secrets.baseline` file for tracking.
- Pure Python — no native extensions, lightweight deps.
- pip is canonical install method.
- brew formula available.
- NOT in apt, dnf, apk, pacman (standard), zypper, snap.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `pip` | ✅ | `detect-secrets` | **Official/canonical** |
| `brew` | ✅ | `detect-secrets` | Standard formula |
| `apt` | ❌ | — | Not available |
| `dnf` | ❌ | — | Not available |
| `apk` | ❌ | — | Not available |
| `pacman` | ❌ | — | Not in standard repos |
| `zypper` | ❌ | — | Not available |
| `snap` | ❌ | — | Not available |

---

## 3. Installation (_default via pip)

| Field | Value |
|-------|-------|
| Method | `pip install detect-secrets` |
| Install location | Python site-packages + `~/.local/bin/detect-secrets` |
| Dependencies | Python, pip |
| needs_sudo | No |
| install_via | `pip` |

### Platform considerations

- **macOS (arm64/Intel)**: brew preferred — handles Python deps.
- **Raspbian ARM (aarch64)**: pip works — pure Python, no wheels to build.
- **Alpine**: pip works — no native extensions.
- **Debian/Ubuntu**: pip works. PEP 668 on modern versions → handler exists.
- **All platforms**: Pure Python = no architecture-specific build issues.

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Runtime | Python | Required |
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
| `_default` | `missing_curl` | curl not installed |
| `_default` | `missing_git` | git not installed |
| `_default` | `missing_wget` | wget not installed |
| `_default` | `missing_unzip` | unzip not installed |
| `_default` | `missing_npm_default` | npm not installed |

### Layer 1: INFRA handlers (9 cross-tool)
Network, disk, permissions, OOM, timeout — all standard.

### Layer 3: per-tool on_failure handlers
None needed. Pure Python pip + brew install — very straightforward.

---

## 7. Recipe Structure

```python
"detect-secrets": {
    "cli": "detect-secrets",
    "label": "detect-secrets (Yelp secret detection tool)",
    "category": "security",
    "install": {
        "brew":    ["brew", "install", "detect-secrets"],
        "_default": _PIP + ["install", "detect-secrets"],
    },
    "needs_sudo": {"brew": False, "_default": False},
    "install_via": {"_default": "pip"},
    "prefer": ["brew"],
    "verify": ["detect-secrets", "--version"],
    "update": {
        "brew":    ["brew", "upgrade", "detect-secrets"],
        "_default": _PIP + ["install", "--upgrade", "detect-secrets"],
    },
}
```

---

## 8. Validation Results

```
Schema:    VALID (recipe + all method-family handlers)
Coverage:  494/494 (100%) — 26 scenarios × 19 presets
Handlers:  1 brew + 5 _default + 11 pip + 9 INFRA = 26 total
```

---

## 9. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Added `cli: "detect-secrets"` |
| `data/recipes.py` | Updated label to `"detect-secrets (Yelp secret detection tool)"` |
| `data/recipes.py` | Added `brew` install method |
| `data/recipes.py` | Added `prefer: ["brew"]` |
| `data/recipes.py` | Added `brew` update command |

---

## 10. Platform Coverage

| Platform | Method | Notes |
|----------|--------|-------|
| **macOS (arm64/Intel)** | brew preferred | Handles Python deps |
| **Raspbian (aarch64)** | pip | Pure Python — no wheel build issues |
| **Debian/Ubuntu** | pip | PEP 668 handler for modern distros |
| **Alpine** | pip | No native extensions needed |
| **Arch** | pip | PEP 668 enforced |
| **Fedora/SUSE** | pip | Standard install |

---

## 11. Future Enhancements

- **Baseline management**: Could offer to initialize
  `.secrets.baseline` after install.
- **Pre-commit integration**: Could auto-configure
  `.pre-commit-config.yaml` with detect-secrets hook.
