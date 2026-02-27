# poetry — Full Spectrum Analysis

> **Tool ID:** `poetry`
> **Last audited:** 2026-02-26
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | Poetry — Python dependency management and packaging |
| Language | Python |
| CLI binary | `poetry` |
| Category | `python` |
| Verify command | `poetry --version` |
| Recipe key | `poetry` |

### Special notes
- Poetry manages Python project deps, virtual envs, and packaging
  via `pyproject.toml` and `poetry.lock`.
- The **officially recommended** install method is `pipx` or the
  official installer script (`install.python-poetry.org`).
- `pip install poetry` works but is **discouraged** — it can cause
  dependency conflicts with the system Python (PEP 668 on modern
  distros).
- System PM packages (`apt`, `dnf`, `pacman`) are available but
  **often outdated** compared to PyPI.
- Poetry installs to `$HOME/.local/bin` — needs PATH setup.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `pipx` | ✅ | `poetry` | Officially recommended (isolated install) |
| `pip` | ✅ | `poetry` | Works but discouraged (PEP 668 conflicts) |
| `apt` | ✅ | `python3-poetry` | Debian testing/unstable, often outdated |
| `dnf` | ✅ | `python3-poetry` | Fedora, often outdated |
| `pacman` | ✅ | `python-poetry` | Arch extra/community |
| `brew` | ✅ | `poetry` | macOS/Linux Homebrew |
| `apk` | ❌ | — | Not in Alpine repos |
| `zypper` | ❌ | — | Not in openSUSE repos |
| `snap` | ❌ | — | Not available |
| `npm` | ❌ | — | Not a JS tool |
| `cargo` | ❌ | — | Not a Rust tool |

### Package name notes
- **apt/dnf:** Package is `python3-poetry` (follows Python3 naming
  convention). Recorded in `KNOWN_PACKAGES`.
- **pacman:** Package is `python-poetry` (Arch convention: no "3"
  suffix). Recorded in `KNOWN_PACKAGES`.
- **pip/pipx/brew:** Package name matches CLI (`poetry`).

---

## 3. Install Method — _default (official installer)

| Field | Value |
|-------|-------|
| Command | `curl -sSL https://install.python-poetry.org \| python3 -` |
| Script | Official Poetry installer |
| Install location | `$HOME/.local/bin/poetry` (Linux), `$HOME/Library/Application Support/pypoetry` (macOS) |
| Dependencies | `curl` (download), `python3` (runtime) |
| needs_sudo | No |

### Platform coverage
The official installer handles OS detection internally:
- Linux x86_64 ✅ (pure Python, no native code)
- Linux aarch64 ✅
- Linux armv7l (Raspbian) ✅
- macOS Intel ✅
- macOS Apple Silicon ✅

Poetry is a **pure Python package** — no architecture-specific
binary downloads. All platforms where Python 3 runs are supported.

### Post-install
PATH needs updating (handled by `post_env`):
```bash
export PATH="$HOME/.local/bin:$PATH"
```

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Download | `curl` | For `_default` installer script |
| Runtime | `python3` | Required — Poetry is a Python tool |
| Optional | `pipx` | For `pipx` install method (recommended) |

### Reverse deps
Poetry is used by:
- Python projects using `pyproject.toml`
- Projects needing reproducible dependency locking
- Libraries publishing to PyPI

---

## 5. Post-install

**_default / pip / pipx:** Installs to `$HOME/.local/bin/`.
Needs PATH setup (configured via `post_env`).

**apt / dnf / pacman:** Installs to system paths, no PATH changes.

**brew:** Installs to Homebrew prefix, no PATH changes.

The `verify` command includes PATH export:
```python
["bash", "-c", 'export PATH="$HOME/.local/bin:$PATH" && poetry --version']
```

---

## 6. Failure Handlers

### Layer 1: method-family handlers
Poetry inherits handlers from its install methods:

**pip (11 handlers):**
| Handler | Category |
|---------|----------|
| `pep668` | environment |
| `pip_venv_not_available` | dependency |
| `pip_system_install_warning` | environment |
| `missing_pip` | dependency |
| `pip_permission_denied` | permissions |
| `pip_version_conflict` | dependency |
| `pip_hash_mismatch` | network |
| `pip_build_wheel_failed` | compiler |
| `pip_no_matching_dist` | dependency |
| `pip_ssl_error` | network |
| `pip_python_version` | compatibility |

Plus: apt (2), dnf (1), pacman (2), brew (1), _default (5).

### Layer 2: INFRA handlers (9 cross-tool)
Network, disk, permissions, OOM, timeout — all standard.

### Layer 3: per-tool on_failure handlers

| Handler | Category | Trigger | Options |
|---------|----------|---------|---------|
| `poetry_python3_not_found` | dependency | `python3: command not found` | Install python3 via system PM (recommended), switch to brew |

---

## 7. Recipe Structure

```python
"poetry": {
    "cli": "poetry",
    "label": "Poetry (Python dependency management and packaging)",
    "category": "python",
    "install": {
        "pipx":   ["pipx", "install", "poetry"],
        "pip":    ["pip", "install", "--user", "poetry"],
        "apt":    ["apt-get", "install", "-y", "python3-poetry"],
        "dnf":    ["dnf", "install", "-y", "python3-poetry"],
        "pacman": ["pacman", "-S", "--noconfirm", "python-poetry"],
        "brew":   ["brew", "install", "poetry"],
        "_default": [
            "bash", "-c",
            "curl -sSL https://install.python-poetry.org | python3 -",
        ],
    },
    "needs_sudo": {
        "pipx": False, "pip": False,
        "apt": True, "dnf": True, "pacman": True,
        "brew": False, "_default": False,
    },
    "prefer": ["pipx", "_default", "brew"],
    "requires": {"binaries": ["curl"]},
    "post_env": 'export PATH="$HOME/.local/bin:$PATH"',
    "verify": ["bash", "-c", '... && poetry --version'],
    "update": {
        "pipx": ["pipx", "upgrade", "poetry"],
        "pip":  ["pip", "install", "--upgrade", "poetry"],
        "brew": ["brew", "upgrade", "poetry"],
    },
}
```

---

## 8. Validation Results

```
Schema:    VALID (recipe + all method-family handlers + on_failure)
Coverage:  608/608 (100%) — 32 scenarios × 19 presets
Handlers:  11 pip + 5 PM-family + 5 _default + 1 on_failure + 9 INFRA = 32 total
```

Note: `pipx` has no method-family-specific handlers yet. Failures in
`pipx install` would be caught by INFRA handlers (network, permissions,
disk). Tool-specific failures should be added in remediation audit.

---

## 9. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Added `cli: "poetry"` |
| `data/recipes.py` | Updated `label` to include full description |
| `data/recipes.py` | Added `pipx`, `pip`, `apt`, `dnf`, `pacman` install methods |
| `data/recipes.py` | Added `prefer: ["pipx", "_default", "brew"]` |
| `data/recipes.py` | Added `needs_sudo` for all 7 methods |
| `data/recipes.py` | Added `update` for pipx, pip, brew |
| `data/recipe_schema.py` | Added `pipx` to `VALID_METHOD_KEYS` |
| `resolver/dynamic_dep_resolver.py` | Added poetry to `KNOWN_PACKAGES` (apt=python3-poetry, dnf=python3-poetry, pacman=python-poetry) |
| `data/tool_failure_handlers.py` | Added `poetry_python3_not_found` handler (2 options) |

---

## 10. Update Derivation

Explicit `update` map provided for pipx, pip, brew. Other PM
updates derived by `get_update_map()`:

| PM | Update command | Source |
|----|---------------|--------|
| pipx | `pipx upgrade poetry` | Explicit |
| pip | `pip install --upgrade poetry` | Explicit |
| brew | `brew upgrade poetry` | Explicit |
| apt | `apt-get install --only-upgrade -y python3-poetry` | Derived |
| dnf | `dnf upgrade -y python3-poetry` | Derived |
| pacman | `pacman -S --noconfirm python-poetry` | Derived |
| _default | N/A (official installer) | — |

---

## 11. Design Notes

### Why prefer pipx over pip
`pip install poetry` into the system Python is officially
discouraged because:
1. PEP 668 on modern distros blocks system-wide pip installs
2. Poetry has many dependencies that can conflict with system
   packages
3. pipx creates an isolated environment for Poetry's dependencies

The `prefer` order is `["pipx", "_default", "brew"]` — pip is
available as a method but not preferred.

### Why `pipx` was added to VALID_METHOD_KEYS
pipx is a distinct package manager from pip:
- pip installs into the current Python environment
- pipx installs each tool into its own isolated venv
- Many Python CLI tools (poetry, black, ruff, pre-commit)
  recommend pipx as the primary install method

### Pure Python — no platform concerns
Poetry is pure Python. No native code, no `arch_map`, no
`{os}/{arch}` placeholders needed. Works on any platform where
Python 3 runs.
