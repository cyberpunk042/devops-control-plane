# checkov — Full Spectrum Analysis

> **Tool ID:** `checkov`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | Checkov — IaC security scanner |
| Language | Python |
| CLI binary | `checkov` |
| Category | `security` |
| Verify command | `checkov --version` |
| Recipe key | `checkov` |

### Special notes
- By Bridgecrew (Palo Alto Networks).
- Scans Terraform, CloudFormation, Kubernetes, Helm, ARM templates,
  Serverless, Dockerfiles, and more.
- Pure Python — canonical install via pip.
- Requires Python 3.9–3.12.
- Heavy dependency tree (many Python packages).
- brew formula available — handles Python deps automatically.
- NOT in apt, dnf, apk, pacman, zypper, snap.
- No pre-compiled binaries — it's a Python package.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `pip` | ✅ | `checkov` | **Official/canonical** |
| `brew` | ✅ | `checkov` | Standard formula |
| `apt` | ❌ | — | Not available |
| `dnf` | ❌ | — | Not available |
| `apk` | ❌ | — | Not available |
| `pacman` | ❌ | — | Not available |
| `zypper` | ❌ | — | Not available |
| `snap` | ❌ | — | Not available |

---

## 3. Installation (_default via pip)

| Field | Value |
|-------|-------|
| Method | `pip install checkov` |
| Install location | Python site-packages + `~/.local/bin/checkov` |
| Dependencies | Python 3.9–3.12, pip |
| needs_sudo | No (user-level pip install) |
| install_via | `pip` |

### Platform considerations

- **macOS**: brew preferred — handles Python version management.
  pip also works if Python 3.9+ available.
- **Raspbian ARM (aarch64)**: pip works. Some wheels may need to be
  built from source (slower). No brew typically.
- **Alpine (musl)**: pip works but some C extension wheels may not
  have musl builds — may require build deps.
- **Debian/Ubuntu**: Modern versions may hit PEP 668 (externally managed
  Python). Use `--break-system-packages` or venv.
- **All platforms**: pip handlers cover PEP 668, SSL, build wheel,
  version conflicts comprehensively.

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Runtime | Python 3.9–3.12 | Required |
| Runtime | pip | For _default install method |
| Runtime | Many Python packages | checkov has ~50+ transitive deps |

---

## 5. Post-install

When installed via pip with `--user`, binary goes to `~/.local/bin/`.
May need PATH addition: `export PATH=$HOME/.local/bin:$PATH`.

---

## 6. Failure Handlers

### Layer 2b: install_via family (pip)
| Handler | Category | Trigger |
|---------|----------|---------|
| `pep668` | environment | Externally managed Python (PEP 668) |
| `pip_venv_not_available` | dependency | python3-venv not installed |
| `pip_system_install_warning` | environment | pip into system Python |
| `missing_pip` | dependency | pip not installed |
| `pip_permission_denied` | permissions | Permission denied |
| `pip_version_conflict` | dependency | Dependency version conflict |
| `pip_hash_mismatch` | network | Hash mismatch (corrupted download) |
| `pip_build_wheel_failed` | compiler | Failed to build wheel |
| `pip_no_matching_dist` | dependency | Package not found |
| `pip_ssl_error` | network | SSL certificate error |
| `pip_python_version` | compatibility | Python version incompatible |

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
None needed. Standard pip + brew install.

---

## 7. Recipe Structure

```python
"checkov": {
    "cli": "checkov",
    "label": "Checkov (IaC security scanner)",
    "category": "security",
    "install": {
        "brew":    ["brew", "install", "checkov"],
        "_default": _PIP + ["install", "checkov"],
    },
    "needs_sudo": {"brew": False, "_default": False},
    "install_via": {"_default": "pip"},
    "prefer": ["brew"],
    "verify": ["checkov", "--version"],
    "update": {
        "brew":    ["brew", "upgrade", "checkov"],
        "_default": _PIP + ["install", "--upgrade", "checkov"],
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
| `data/recipes.py` | Added `cli: "checkov"` |
| `data/recipes.py` | Updated label to `"Checkov (IaC security scanner)"` |
| `data/recipes.py` | Added `brew` install method |
| `data/recipes.py` | Added `prefer: ["brew"]` |
| `data/recipes.py` | Added `brew` update command |

---

## 10. Platform Coverage

| Platform | Method | Notes |
|----------|--------|-------|
| **macOS (arm64/Intel)** | brew preferred | Handles Python deps |
| **Raspbian (aarch64)** | pip | Some wheels may need building |
| **Debian/Ubuntu** | pip | May hit PEP 668 (handler exists) |
| **Alpine** | pip | C extensions may need build deps |
| **Arch** | pip | No pacman package |
| **Fedora/SUSE** | pip | Standard pip install |

---

## 11. Future Enhancements

- **Python version check**: Could verify Python 3.9–3.12 before
  attempting pip install.
- **venv isolation**: Could recommend virtual environment install
  for cleaner dependency management.
