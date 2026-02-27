# pipx — Full Spectrum Analysis

> **Tool ID:** `pipx`
> **Last audited:** 2026-02-26
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | pipx — install & run Python CLI apps in isolated environments |
| Language | Python |
| CLI binary | `pipx` |
| Category | `python` |
| Verify command | `pipx --version` |
| Recipe key | `pipx` |

### Special notes
- pipx is the **officially recommended** way to install Python CLI tools
  like poetry, black, ruff, pre-commit, etc.
- Unlike pip, pipx creates isolated virtual environments for each tool,
  preventing dependency conflicts.
- pipx is itself installable via most system PMs, making it a foundational
  tool in the Python ecosystem.
- We added `pipx` as a valid install method key in `recipe_schema.py`
  during the poetry audit — this recipe completes the circle by making
  pipx itself installable by the system.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ✅ | `pipx` | Debian 12+/Ubuntu 23.04+ |
| `dnf` | ✅ | `pipx` | Fedora 38+ |
| `apk` | ✅ | `pipx` | Alpine edge |
| `pacman` | ✅ | `python-pipx` | Arch extra |
| `zypper` | ✅ | `python3-pipx` | openSUSE Tumbleweed |
| `brew` | ✅ | `pipx` | macOS/Linux |
| `pip` | ✅ | `pipx` | `pip install --user pipx` (PEP 668 blocks on modern distros) |
| `snap` | ❌ | — | Not available |
| `npm` | ❌ | — | Not a JS tool |
| `cargo` | ❌ | — | Not a Rust tool |

### Package name notes
- **pacman:** `python-pipx` (Arch convention: no "3" suffix)
- **zypper:** `python3-pipx` (openSUSE uses python3- prefix)
- **Everywhere else:** `pipx`
- Recorded in `KNOWN_PACKAGES`.

---

## 3. Install Methods

### System PMs (apt, dnf, apk, pacman, zypper, brew)
Standard package install. Preferred — they handle dependencies.

### _default (pip install --user + ensurepath)
```bash
pip install --user pipx && python3 -m pipx ensurepath
```
- Falls back to pip for distros without a native pipx package.
- `ensurepath` adds `~/.local/bin` to PATH.
- May be blocked by PEP 668 on modern distros.

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Runtime | `python3` | Required — pipx is a Python tool |
| Runtime | `python3-venv` | Needed by pipx to create isolated venvs (apt systems) |

### Reverse deps
pipx is a dependency for:
- poetry (via `pipx` install method)
- uv (via `pipx` install method)
- black, ruff, pre-commit, and many other Python CLI tools

---

## 5. Post-install

pipx installs tools to `$HOME/.local/bin`. This path must be on PATH.

The `post_env` handles this:
```bash
export PATH="$HOME/.local/bin:$PATH"
```

For the `_default` method, `pipx ensurepath` also adds this to
shell config files.

---

## 6. Failure Handlers

### Layer 1: method-family handlers
pipx inherits handlers from its install methods:

**pip (11 handlers):** PEP 668, version conflicts, SSL, etc.
(applies to `_default` method which uses pip internally)

**System PM handlers:**
- apt (2): stale index, locked
- dnf (1): no match
- apk (2): unsatisfiable, locked
- pacman (2): target not found, locked
- zypper (2): not found, locked
- brew (1): no formula

**_default (5):** curl/git/wget/unzip/npm missing

### Layer 2: INFRA handlers (9 cross-tool)
Network, disk, permissions, OOM, timeout — all standard.

### Layer 3: per-tool on_failure handlers
None needed — pipx's unique failures are handled at Layer 2 (method-family)
because they affect ALL tools installed via pipx.

### Layer 2 additions: pipx method-family handlers

| Handler | Category | Trigger | Options |
|---------|----------|---------|---------|
| `pipx_venv_missing` | dependency | `venv module not found` — pipx can't create isolated environments | Install python3-venv (per-family packages) |
| `missing_pipx` | dependency | `pipx: command not found` — pipx itself isn't installed | Install pipx (recommended), switch to pip (fallback) |

---

## 7. Recipe Structure

```python
"pipx": {
    "cli": "pipx",
    "label": "pipx (install & run Python CLI apps in isolated environments)",
    "category": "python",
    "install": {
        "apt":    ["apt-get", "install", "-y", "pipx"],
        "dnf":    ["dnf", "install", "-y", "pipx"],
        "apk":    ["apk", "add", "pipx"],
        "pacman": ["pacman", "-S", "--noconfirm", "python-pipx"],
        "zypper": ["zypper", "install", "-y", "python3-pipx"],
        "brew":   ["brew", "install", "pipx"],
        "_default": [
            "bash", "-c",
            "pip install --user pipx && python3 -m pipx ensurepath",
        ],
    },
    "needs_sudo": {
        "apt": True, "dnf": True, "apk": True,
        "pacman": True, "zypper": True,
        "brew": False, "_default": False,
    },
    "prefer": ["apt", "dnf", "brew"],
    "requires": {"binaries": ["python3"]},
    "post_env": 'export PATH="$HOME/.local/bin:$PATH"',
    "verify": ["pipx", "--version"],
    "update": {
        "pip":  ["pip", "install", "--upgrade", "pipx"],
        "brew": ["brew", "upgrade", "pipx"],
    },
}
```

---

## 8. Validation Results

```
Schema:    VALID (recipe + all method-family handlers)
Coverage:  703/703 (100%) — 37 scenarios × 19 presets
Handlers:  11 pip + 10 PM-family + 5 _default + 2 pipx-family + 9 INFRA = 37 total
```

---

## 9. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Created pipx recipe (7 install methods, prefer, update) |
| `resolver/dynamic_dep_resolver.py` | Added pipx to `KNOWN_PACKAGES` (pacman=python-pipx, zypper=python3-pipx) |
| `data/remediation_handlers.py` | Added `pipx` method-family handlers (2: venv missing, pipx not found) |

---

## 10. Design Notes

### Why prefer system PMs over pip for pipx
The `_default` method uses pip, but `pip install --user pipx` is
blocked by PEP 668 on modern distros (Debian 12+, Ubuntu 23.04+,
Fedora 38+). System PM packages don't have this issue.

The `prefer` order is `["apt", "dnf", "brew"]`:
- System PMs handle python3-venv dependency automatically
- No PEP 668 conflict
- pip as fallback for older distros only

### pipx as an install method vs as a tool
pipx serves dual roles:
1. **As a tool (this recipe):** pipx itself needs to be installed
2. **As an install method:** once installed, pipx can install other
   tools (poetry, uv, black, ruff, etc.)

The `pipx` method key was added to `VALID_METHOD_KEYS` during the
poetry audit. This recipe ensures the pipx tool itself is installable.

### Circular dependency concern
If `pipx` method is preferred for poetry/uv, and pipx needs to be
installed first, there's a soft dependency chain:
`poetry (via pipx)` → `pipx` → `apt/dnf` (or `pip`)

This is handled correctly because:
1. The method selection logic checks if `pipx` is on PATH
2. If not, it falls back to the next preferred method
3. The system can auto-install pipx first if needed
