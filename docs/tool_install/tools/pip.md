# pip — Full-spectrum tool install spec

> Python package installer. Used directly and as an install method for
> hundreds of downstream tools (ruff, mypy, pytest, black, poetry, etc.)

---

## 1. Identity

| Field | Value |
|-------|-------|
| `tool_id` | `pip` |
| `cli` | `pip` |
| `label` | `pip` |
| `category` | `python` |
| `verify` | `pip --version` |

---

## 2. Install methods

| Method | Command | `needs_sudo` |
|--------|---------|:------------:|
| `apt` | `apt-get install -y python3-pip` | ✅ |
| `dnf` | `dnf install -y python3-pip` | ✅ |
| `apk` | `apk add py3-pip` | ✅ |
| `pacman` | `pacman -S --noconfirm python-pip` | ✅ |
| `zypper` | `zypper install -y python3-pip` | ✅ |

### Update method

| Method | Command |
|--------|---------|
| `_default` | `pip install --upgrade pip` |

---

## 3. Downstream impact

pip is the install method for a large portion of the recipe catalog:

| Category | Count | Examples |
|----------|-------|---------|
| `uncategorized` (via `_default` + pip) | 42 | ruff, mypy, pytest, black, pip-audit, bandit |
| `python` | 9 | poetry, uv, pyright, isort, flake8, tox, nox, pdm |
| `ml` | 6 | pytorch, opencv, jupyter, numpy, pandas, tensorflow |
| `docs` | 1 | sphinx |
| `pages` | 1 | mkdocs |

Any pip failure handler benefits **all tools installed via pip**.

---

## 4. Failure scenarios and handlers

### 4.1 pip-specific handlers (11 handlers)

| # | Handler | ID | Category | Trigger |
|---|---------|-----|----------|---------|
| 1 | PEP 668 (externally-managed) | `pep668` | environment | `externally.managed.environment` |
| 2 | **venv not available** | `pip_venv_not_available` | dependency | `ensurepip is not available`, `No module named venv` |
| 3 | **System-level install** | `pip_system_install_warning` | environment | `WARNING: Running pip as the 'root' user` |
| 4 | pip not installed | `missing_pip` | dependency | `No module named pip`, `pip: command not found` |
| 5 | Permission denied | `pip_permission_denied` | permissions | `Permission denied:.*site-packages` |
| 6 | Dependency version conflict | `pip_version_conflict` | dependency | `requires.*but you.*have`, `ResolutionImpossible` |
| 7 | Hash mismatch | `pip_hash_mismatch` | network | `THESE PACKAGES DO NOT MATCH THE HASHES` |
| 8 | Failed to build wheel | `pip_build_wheel_failed` | compiler | `Failed building wheel for`, `command 'gcc' failed` |
| 9 | Package not found | `pip_no_matching_dist` | dependency | `No matching distribution found for` |
| 10 | SSL certificate error | `pip_ssl_error` | network | `CERTIFICATE_VERIFY_FAILED`, `SSLCertVerificationError` |
| 11 | Python version incompatible | `pip_python_version` | compatibility | `requires a different Python`, `requires Python >=` |

### 4.2 Package manager handlers (via install methods)

| Handler | ID | Applies to |
|---------|-----|-----------|
| apt stale index | `apt_stale_index` | Debian/Ubuntu systems |
| apt locked | `apt_locked` | Debian/Ubuntu systems |
| dnf no match | `dnf_no_match` | Fedora/RHEL/CentOS/Rocky |

### 4.3 INFRA handlers (9 cross-tool handlers)

| Handler | ID |
|---------|-----|
| Network unreachable | `network_offline` |
| Download blocked | `network_blocked` |
| Disk full | `disk_full` |
| Read-only filesystem | `read_only_rootfs` |
| No sudo access | `no_sudo` |
| Wrong sudo password | `sudo_wrong_password` |
| Permission denied | `permission_denied_generic` |
| Out of memory | `oom_killed` |
| Command timed out | `command_timeout` |

---

## 5. Per-system behavior across 19 presets

| Preset | Family | PM | pip available via | PEP 668? | Edge cases |
|--------|--------|-----|-------------------|----------|------------|
| `debian_11` | debian | apt | apt | No | |
| `debian_12` | debian | apt | apt | Yes | PEP 668 blocks `pip install` |
| `docker_debian_12` | debian | apt | apt | Yes | No sudo, root user |
| `ubuntu_2004` | debian | apt | apt | No | |
| `ubuntu_2204` | debian | apt | apt | Yes | PEP 668 blocks `pip install` |
| `ubuntu_2404` | debian | apt | apt | Yes | PEP 668 blocks `pip install` |
| `raspbian_bookworm` | debian | apt | apt | Yes | ARM64, PEP 668 |
| `wsl2_ubuntu_2204` | debian | apt | apt | No (22.04 default) | WSL-specific paths |
| `fedora_39` | rhel | dnf | dnf | Yes | PEP 668 |
| `fedora_41` | rhel | dnf | dnf | Yes | PEP 668 |
| `centos_stream9` | rhel | dnf | dnf | No | |
| `rocky_9` | rhel | dnf | dnf | No | |
| `alpine_318` | alpine | apk | apk | No | musl libc — some wheels fail |
| `alpine_320` | alpine | apk | apk | No | musl libc — some wheels fail |
| `arch_latest` | arch | pacman | pacman | Yes | PEP 668 |
| `opensuse_15` | suse | zypper | zypper | No | |
| `macos_14_arm` | macos | brew | brew (Python includes pip) | Yes | ARM64, framework Python |
| `macos_13_x86` | macos | brew | brew (Python includes pip) | Yes | x86_64 Rosetta possible |
| `k8s_alpine_318` | alpine | apk | apk (⚠️ ro rootfs) | No | Read-only rootfs |

---

## 6. Python environment philosophy

**System Python is the OS's dependency. You should never install into it.**

The handler system now follows this hierarchy for all pip-related remediation:

| Priority | Option | Why |
|----------|--------|-----|
| 🥇 1st | **venv** (built-in) | Zero dependencies, safest, most portable |
| 🥈 2nd | **uv** | Modern, fast, auto-creates isolated envs |
| 🥉 3rd | **conda/mamba** | If user's existing ecosystem; manages Python itself |
| 4th | **pipx** | CLI tools only (not libraries) |
| 5th | **OS package** | May be outdated, but safe |
| ☠️ Last | `--break-system-packages` | Risk: **critical** — only in throwaway containers |

### PEP 668 impact

PEP 668 is the most frequently hit pip failure. Systems affected:

| System | PEP 668? | Why |
|--------|----------|-----|
| debian_12, ubuntu_2204, ubuntu_2404 | ✅ | Python >= 3.11 default package |
| fedora_39, fedora_41, arch_latest | ✅ | Distro policy |
| macos 14/13 | ✅ | Homebrew Python |
| debian_11, ubuntu_2004, centos_stream9, rocky_9 | ❌ | Older Python default |
| alpine_318, alpine_320, opensuse_15 | ❌ | No PEP 668 enforcement |

### `pre_packages` — single-shot venv chain

On Debian/Ubuntu, `python3-venv` is **not installed by default**. This means
the recommended venv option would fail silently without extra handling.

The `pre_packages` field solves this at the infrastructure level:

```python
"pre_packages": {
    "debian": ["python3-venv"],    # apt install before venv creation
    "rhel": ["python3-virtualenv"],
    "suse": ["python3-virtualenv"],
}
```

This makes every venv option a **single-shot chain**:

```
Step 1: apt install python3-venv     (pre_packages)
Step 2: python3 -m venv ~/.local/... (fix_commands[0])
Step 3: pip install <tool>            (fix_commands[1])
```

Applied to all venv `env_fix` options across: `pep668`, `pip_system_install_warning`,
`pip_permission_denied`, and `pip_version_conflict`.

The `pip_venv_not_available` handler serves as a **safety net** — if venv
creation is attempted outside the remediation flow and fails, it catches
the error and offers the same resolution.

---

## 7. Python environment detection (`_detect_python()`)

The system profile now detects the active Python environment context at runtime.
This data lives in `system_profile.python` and is available to handlers and UI:

```json
{
  "version": "3.12.8",
  "version_tuple": [3, 12, 8],
  "implementation": "CPython",
  "executable": "/home/user/.venv/bin/python3",
  "prefix": "/home/user/.venv",
  "base_prefix": "/usr",
  "env_type": "venv",
  "in_managed_env": true,
  "pep668": false,
  "env_managers": {
    "uv": false,
    "conda": false,
    "pyenv": true,
    "virtualenv": true,
    "pipx": false
  },
  "system_python_warning": false
}
```

### Detection logic

| Field | How detected |
|-------|--------------|
| `env_type` | Priority: conda (`CONDA_PREFIX`) > uv (`UV_VIRTUAL_ENV`) > pyenv (`PYENV_ROOT` in prefix) > venv (`prefix != base_prefix` + `pyvenv.cfg`) > virtualenv > system |
| `in_managed_env` | True if any environment type other than `system` |
| `pep668` | Checks `EXTERNALLY-MANAGED` file in stdlib path (only when not in managed env) |
| `env_managers` | Binary existence check for uv, conda, pyenv, virtualenv, pipx |
| `system_python_warning` | True when on bare system Python — handlers should offer environment creation |

---

## 8. musl/Alpine wheel failures

Alpine uses musl libc instead of glibc. Many PyPI wheels are glibc-only
(`manylinux` wheels). On Alpine:

- Pure Python packages: ✅ work fine
- C extension packages (numpy, lxml, etc.): ❌ may require source build
- Source build requires: `build-base`, `python3-dev`, and package-specific headers

The `pip_build_wheel_failed` handler addresses this with per-family build packages.

---

## 9. Recipe reference

```python
"pip": {
    "cli": "pip",
    "label": "pip",
    "category": "python",
    "install": {
        "apt":    ["apt-get", "install", "-y", "python3-pip"],
        "dnf":    ["dnf", "install", "-y", "python3-pip"],
        "apk":    ["apk", "add", "py3-pip"],
        "pacman": ["pacman", "-S", "--noconfirm", "python-pip"],
        "zypper": ["zypper", "install", "-y", "python3-pip"],
    },
    "needs_sudo": {
        "apt": True, "dnf": True, "apk": True,
        "pacman": True, "zypper": True,
    },
    "verify": ["pip", "--version"],
    "update": {"_default": ["pip", "install", "--upgrade", "pip"]},
}
```

---

## 10. Validation results

### 10.1 Recipe and handler validation

```
✅ pip recipe: VALID
✅ apt handlers: VALID (2 handlers)
✅ dnf handlers: VALID (1 handlers)
✅ pip handlers: VALID (11 handlers)
```

### 10.2 Remediation handler coverage (23 scenarios × 19 presets = 437 tests)

| Scenario | Handler | 19/19? |
|----------|---------|--------|
| PEP 668 externally managed | `pep668` | ✅ |
| **venv not available** | `pip_venv_not_available` | ✅ |
| **System-level install warning** | `pip_system_install_warning` | ✅ |
| pip not found | `missing_pip` | ✅ |
| Permission denied (site-packages) | `pip_permission_denied` | ✅ |
| Dependency version conflict | `pip_version_conflict` | ✅ |
| Hash mismatch | `pip_hash_mismatch` | ✅ |
| Build wheel failed | `pip_build_wheel_failed` | ✅ |
| Package not found | `pip_no_matching_dist` | ✅ |
| SSL certificate error | `pip_ssl_error` | ✅ |
| Python version incompatible | `pip_python_version` | ✅ |
| apt stale index | `apt_stale_index` | ✅ |
| apt locked | `apt_locked` | ✅ |
| dnf no match | `dnf_no_match` | ✅ |
| + 9 INFRA handlers | (cross-tool) | ✅ |

**TOTAL: 437/437 (100%) — FULL COVERAGE, NO GAPS**

### 10.3 All gaps resolved

| Gap | Status |
|-----|--------|
| G1: Missing `cli` field | ✅ Added |
| G2: Missing `category` field | ✅ Added (`python`) |
| G3: Only 2 pip handlers | ✅ Expanded to 11 handlers |
| G4: No environment-first remediation | ✅ venv is recommended in all pip handlers |
| G5: No system-level install warning | ✅ Added `pip_system_install_warning` |
| G6: No uv/conda options | ✅ All env handlers offer venv, uv, conda |
| G7: No Python env detection | ✅ `_detect_python()` enhanced with env awareness |
| G8: `--break-system-packages` too easy | ✅ Moved to last option, risk: `critical` |
| G9: venv fails without python3-venv | ✅ `pre_packages` installs OS deps before venv creation |
| G10: No handler for venv module missing | ✅ `pip_venv_not_available` catches ensurepip errors |
