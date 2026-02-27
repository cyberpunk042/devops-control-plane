# ansible — Full Spectrum Analysis

> **Tool ID:** `ansible`
> **Last audited:** 2026-02-27
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | Ansible — configuration management & automation |
| Language | Python |
| CLI binary | `ansible` (also provides `ansible-playbook`, `ansible-galaxy`, `ansible-vault`) |
| Category | `iac` |
| Verify command | `ansible --version` |
| Recipe key | `ansible` |

### Special notes
- Ansible is **pure Python** — no compiled binaries, no architecture concerns.
- The canonical install method is **pip** (`pip install ansible`).
  System package managers often ship older versions.
- `ansible` is the full package (includes community collections).
  `ansible-core` is the minimal package (core engine only).
- The recipe installs the full `ansible` package.
- Ansible requires **Python 3.9+** on the control node.
- For managed nodes, Ansible connects via SSH — `sshpass` is an
  optional dependency for password-based SSH authentication.
- No snap package available (only an experimental third-party snap).

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `pip` | ✅ | `ansible` | **Official/canonical** install method |
| `apt` | ✅ | `ansible` | Debian/Ubuntu repos (may lag behind PyPI) |
| `dnf` | ✅ | `ansible` | Fedora/RHEL repos |
| `apk` | ✅ | `ansible` | Alpine community repo |
| `pacman` | ✅ | `ansible` | Arch `extra` repo |
| `zypper` | ✅ | `ansible` | openSUSE repos |
| `brew` | ✅ | `ansible` | macOS/Linux Homebrew |
| `snap` | ❌ | — | Only unofficial third-party snap |
| `npm` | ❌ | — | Not available |
| `cargo` | ❌ | — | Not available |
| `go` | ❌ | — | Not available |

### Package name notes
- Package name is `ansible` across ALL package managers — no mapping needed.
- System packages may be significantly behind the latest PyPI version.
  For production use, pip is strongly recommended.
- The `prefer` list routes to system PMs first (apt/dnf/etc.) since they
  handle Python dependency isolation automatically. pip is the `_default`
  fallback.

---

## 3. Installation (_default via pip)

| Field | Value |
|-------|-------|
| Method | `pip install ansible` |
| Install location | `~/.local/bin/` or venv bin dir |
| Dependencies | `python3`, `pip` |
| needs_sudo | No (user-level pip install) |

### Architecture
Not applicable — Ansible is pure Python. No compiled binaries,
no architecture-specific downloads.

### Version resolution
pip resolves the latest stable version from PyPI automatically.

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Runtime | `python3` | Python 3.9+ required on control node |
| Runtime | `pip` | For `_default` install method |
| Runtime (opt) | `sshpass` | Only for password-based SSH auth |
| Runtime (opt) | `paramiko` | Alternative SSH transport |
| Managed node | `python3` | Required on target hosts |

### Reverse deps
Ansible is referenced by:
- `ansible-lint` — Ansible linter
- Various CI/CD pipelines for infrastructure automation
- Molecule — Ansible testing framework

---

## 5. Post-install

When installed via pip, Ansible binaries go to `~/.local/bin/` or
the venv's `bin/` directory. The `_PIP` convention in recipes.py
uses `sys.executable -m pip` which installs into the current Python
environment.

For system packages (apt/dnf/etc.), binaries go to `/usr/bin/`
(standard PATH).

---

## 6. Failure Handlers

### Layer 2b: install_via family (pip)
| Handler | Category | Trigger |
|---------|----------|---------|
| `pep668` | environment | PEP 668 externally-managed Python |
| `pip_venv_not_available` | dependency | python3-venv not installed |
| `pip_system_install_warning` | environment | pip installing into system Python |
| `missing_pip` | dependency | pip not installed |
| `pip_permission_denied` | permissions | pip permission denied |
| `pip_version_conflict` | dependency | pip dependency version conflict |
| `pip_hash_mismatch` | network | pip hash mismatch (cache/proxy issue) |
| `pip_build_wheel_failed` | compiler | pip failed to build wheel |
| `pip_no_matching_dist` | dependency | pip package not found |
| `pip_ssl_error` | network | pip SSL certificate error |
| `pip_python_version` | compatibility | Python version incompatible |

### Layer 2a: method-family handlers (shared)
| Family | Handler | Trigger |
|--------|---------|---------|
| `apt` | `apt_stale_index` | Stale package index |
| `apt` | `apt_locked` | dpkg lock held |
| `dnf` | `dnf_no_match` | Package not in repos |
| `apk` | `apk_unsatisfiable` | Dependency conflict |
| `apk` | `apk_locked` | Database locked |
| `pacman` | `pacman_target_not_found` | Package not found |
| `pacman` | `pacman_locked` | Database locked |
| `zypper` | `zypper_not_found` | Package not found |
| `zypper` | `zypper_locked` | zypper locked |
| `brew` | `brew_no_formula` | Formula not found |
| `_default` | `missing_curl` | curl not installed |
| `_default` | `missing_git` | git not installed |
| `_default` | `missing_wget` | wget not installed |
| `_default` | `missing_unzip` | unzip not installed |
| `_default` | `missing_npm_default` | npm not installed |

### Layer 1: INFRA handlers (9 cross-tool)
Network, disk, permissions, OOM, timeout — all standard.

### Layer 3: per-tool on_failure handlers
None currently. Potential future additions:
- Ansible Galaxy collection install failures
- SSH key authentication failures during playbook execution

---

## 7. Recipe Structure

```python
"ansible": {
    "cli": "ansible",
    "label": "Ansible (configuration management & automation)",
    "category": "iac",
    "install": {
        "_default": _PIP + ["install", "ansible"],
        "apt":    ["apt-get", "install", "-y", "ansible"],
        "dnf":    ["dnf", "install", "-y", "ansible"],
        "apk":    ["apk", "add", "ansible"],
        "pacman": ["pacman", "-S", "--noconfirm", "ansible"],
        "zypper": ["zypper", "install", "-y", "ansible"],
        "brew":   ["brew", "install", "ansible"],
    },
    "needs_sudo": {
        "_default": False, "apt": True, "dnf": True,
        "apk": True, "pacman": True, "zypper": True,
        "brew": False,
    },
    "install_via": {"_default": "pip"},
    "requires": {"binaries": ["python3"]},
    "prefer": ["apt", "dnf", "apk", "pacman", "zypper", "brew"],
    "verify": ["ansible", "--version"],
    "update": {
        "_default": _PIP + ["install", "--upgrade", "ansible"],
        "apt":    ["bash", "-c", "apt-get update && apt-get install ..."],
        "dnf":    ["dnf", "upgrade", "-y", "ansible"],
        "apk":    ["apk", "upgrade", "ansible"],
        "pacman": ["pacman", "-Syu", "--noconfirm", "ansible"],
        "zypper": ["zypper", "update", "-y", "ansible"],
        "brew":   ["brew", "upgrade", "ansible"],
    },
}
```

---

## 8. Validation Results

```
Schema:    VALID (recipe + all method-family handlers)
Coverage:  665/665 (100%) — 35 scenarios × 19 presets
Handlers:  2 apt + 1 dnf + 2 apk + 2 pacman + 2 zypper + 1 brew
           + 5 _default + 11 pip + 9 INFRA = 35 total
```

---

## 9. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Added `cli: "ansible"` |
| `data/recipes.py` | Updated label to `"Ansible (configuration management & automation)"` |
| `data/recipes.py` | Added `apk`, `pacman`, `zypper` install methods |
| `data/recipes.py` | Added `requires: {"binaries": ["python3"]}` |
| `data/recipes.py` | Added `prefer` list routing to system PMs first |
| `data/recipes.py` | Added per-method `update` commands for all PMs |
| `data/recipes.py` | Expanded `needs_sudo` for all methods |

---

## 10. Future Enhancements

- **Per-tool handlers**: Galaxy collection install failures, SSH auth issues
  during playbook execution.
- **`ansible-core` recipe**: Separate recipe for the minimal ansible-core
  package (no community collections).
- **`ansible-lint` recipe**: Companion linting tool.
- **Version constraint**: Could warn when system package is significantly
  behind PyPI version.
