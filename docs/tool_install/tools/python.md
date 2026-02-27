# python — Full Spectrum Analysis

> **Tool ID:** `python`
> **Last audited:** 2026-02-26
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | Python — interpreted programming language |
| Language | C (CPython reference implementation) |
| CLI binary | `python3` |
| Category | `language` |
| Verify command | `python3 --version` |
| Recipe key | `python` |

### Special notes
- `cli` is `python3` — differs from tool_id `python`. This is intentional
  because many systems still have `python` pointing to Python 2 or nothing.
- Python 3 is **pre-installed** on virtually all Linux distributions.
  This recipe primarily serves two cases:
  1. Minimal container images (Alpine Docker, scratch images) where it's missing
  2. Building a **newer version from source** when the distro version is too old
- Python is a dependency for hundreds of downstream tools (pip, ruff, mypy,
  pytest, black, poetry, etc.) — any Python failure affects the entire ecosystem
- `snap` is intentionally excluded: the `python3-alt` snap has confusing
  version naming and conflicts with the system `python3` symlink

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ✅ | `python3` | Debian/Ubuntu — usually pre-installed |
| `dnf` | ✅ | `python3` | Fedora/RHEL/Rocky — usually pre-installed |
| `apk` | ✅ | `python3` | Alpine — pre-installed in most images |
| `pacman` | ✅ | `python` | Arch — `python` provides Python 3 |
| `zypper` | ✅ | `python3` | openSUSE |
| `brew` | ✅ | `python@3` | macOS — versioned formula |
| `snap` | ⚠️ | `python3-alt` | Excluded — naming conflicts, no canonical snap |
| `pip` | ❌ | — | Cannot install Python via pip |
| `npm` | ❌ | — | Not available |
| `cargo` | ❌ | — | Not available |

### Package name notes
- **pacman:** Arch uses `python` for Python 3 and `python2` for legacy
- **brew:** Uses versioned formula `python@3` (not `python`)
- **snap:** `python3-alt` exists but creates separate `/snap/python3-alt/`
  paths that don't integrate with the system — intentionally excluded

---

## 3. Binary Download / Source Build (_default)

| Field | Value |
|-------|-------|
| Source | https://www.python.org/ftp/python/ |
| Archive format | `.tgz` containing `Python-X.Y.Z/` |
| Build system | autotools (`./configure && make && make altinstall`) |
| Install location | `/usr/local/` (via `--prefix=/usr/local`) |
| Dependencies | `curl`, build toolchain, libssl-dev, libffi-dev, ... |
| needs_sudo | Yes (writes to `/usr/local/`) |

### Why source build as _default?
Python does NOT publish pre-compiled binaries like Go or Rust. The official
distribution channel is source tarballs. While this makes installation slower,
it provides:
- Always-latest stable version
- Full module support (SSL, sqlite, readline, etc.)
- Profile Guided Optimization (`--enable-optimizations`)

### Why `make altinstall` not `make install`?
`make install` creates a `python3` symlink that would **overwrite the system
Python**, potentially breaking system tools that depend on the distro-supplied
version. `make altinstall` installs as `python3.X` (e.g. `python3.13`) without
touching the `python3` symlink, which is the safe approach.

### Build dependencies (per family)
These are specified in `requires.packages`:

| Family | Packages |
|--------|----------|
| debian | `build-essential`, `libssl-dev`, `zlib1g-dev`, `libncurses5-dev`, `libreadline-dev`, `libsqlite3-dev`, `libffi-dev`, `libbz2-dev`, `liblzma-dev` |
| rhel | `gcc`, `make`, `openssl-devel`, `zlib-devel`, `ncurses-devel`, `readline-devel`, `sqlite-devel`, `libffi-devel`, `bzip2-devel`, `xz-devel` |
| alpine | `build-base`, `openssl-dev`, `zlib-dev`, `ncurses-dev`, `readline-dev`, `sqlite-dev`, `libffi-dev`, `bzip2-dev`, `xz-dev` |
| arch | `base-devel`, `openssl`, `zlib`, `ncurses`, `readline`, `sqlite`, `libffi`, `bzip2`, `xz` |
| suse | `gcc`, `make`, `libopenssl-devel`, `zlib-devel`, `ncurses-devel`, `readline-devel`, `sqlite3-devel`, `libffi-devel`, `libbz2-devel`, `xz-devel` |

### What happens without each dependency?
| Missing package | Consequence |
|----------------|-------------|
| `libssl-dev` | No SSL module → pip cannot download anything |
| `libffi-dev` | No ctypes module → many Python packages fail |
| `zlib1g-dev` | No zlib module → pip cannot decompress wheels |
| `libsqlite3-dev` | No sqlite3 module |
| `libreadline-dev` | No readline in REPL (arrows don't work) |
| `libncurses-dev` | No curses module |
| `libbz2-dev` | No bz2 module |
| `liblzma-dev` | No lzma module (xz compression) |

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Download | `curl` | For `_default` install method |
| Build | `build-essential` | Compiler for source build |
| Build | `libssl-dev` + 8 more | See §3 table |
| Runtime | None | Self-contained once installed |

### Reverse deps
Python is a dependency for tools installed via pip:
- `ruff`, `mypy`, `pytest`, `black`, `bandit`, `pip-audit`, `safety`,
  `poetry`, `pdm`, `uv`, `pyright`, `isort`, `flake8`, `tox`, `nox`,
  `mkdocs`, `sphinx`, `ansible`, `jupyter`, and many more

---

## 5. Failure Surface

### 5.1 Per-install-method failures (Layer 2)
All PM-based install methods have dedicated METHOD_FAMILY_HANDLERS:

| PM | Handlers | IDs |
|----|---------|-----|
| `apt` | Stale index, DB locked | `apt_stale_index`, `apt_locked` |
| `dnf` | Package not found | `dnf_no_match` |
| `apk` | Unsatisfiable, DB locked | `apk_unsatisfiable`, `apk_locked` |
| `pacman` | Target not found, DB locked | `pacman_target_not_found`, `pacman_locked` |
| `zypper` | Not found, PM locked | `zypper_not_found`, `zypper_locked` |
| `brew` | Formula not found | `brew_no_formula` |
| `_default` | Missing curl/git/wget/unzip/npm | 5 dependency handlers |

### 5.2 Tool-specific failures (Layer 3 on_failure)

| Failure | Pattern | Category | Handler ID |
|---------|---------|----------|------------|
| Python 3 not found | `python3: command not found` | dependency | `python_not_found` |
| SSL module missing | `ssl module in Python is not available` | dependency | `python_ssl_module_missing` |
| tkinter not available | `No module named '_tkinter'` | dependency | `python_tkinter_missing` |
| libpython shared lib missing | `error while loading shared libraries: libpython` | environment | `python_libpython_missing` |
| zlib module missing | `can't decompress data; zlib not available` | dependency | `python_zlib_missing` |
| Python version too old | `requires a different Python` | environment | `python_version_too_old` |
| macOS Xcode CLT missing | `xcode-select: install` | environment | `python_macos_xcode_clt_missing` |

#### python_not_found
**Scenario:** Minimal container images or cloud VMs don't have python3.
Also catches cases where `python` exists but `python3` doesn't (Python 2
vs 3 confusion).

**Options:**
1. Install python3 via package manager (recommended)
2. Install `python-is-python3` package on Ubuntu (symlink fix)

#### python_ssl_module_missing
**Scenario:** After building Python from source without `libssl-dev`,
`import ssl` fails. This breaks pip, requests, urllib3, and any
HTTPS-dependent code.

**Options:**
1. Install SSL development headers + rebuild Python (recommended)
2. Use system Python (which includes SSL support)

#### python_tkinter_missing
**Scenario:** tkinter is not bundled with python3 on Debian/Ubuntu
(packaged separately as `python3-tk`). GUIs, matplotlib backends,
and some test frameworks need it.

**Options:**
1. Install tkinter package from system PM (recommended)

#### python_libpython_missing
**Scenario:** After building Python from source without `--enable-shared`,
or when the base Python of a virtual environment is removed/upgraded.
Programs that embed Python (GDB, C extensions via PyO3) need the shared
library.

**Options:**
1. Install python3-dev/python3-devel package (recommended)
2. Run `sudo ldconfig` to refresh library cache

#### python_zlib_missing
**Scenario:** zlib development headers were not installed when Python was
built from source. Without zlib, pip cannot decompress downloaded packages
and `make altinstall` itself may fail.

**Options:**
1. Install zlib development headers + rebuild Python (recommended)

#### python_version_too_old
**Scenario:** System Python works but is too old for modern tools.
openSUSE 15 ships 3.6, RHEL 9 ships 3.9, older Ubuntu ships 3.8.
Many tools now require >= 3.10. Catches both explicit version-requirement
errors from pip AND syntax errors from walrus operator (`:=`) or
match/case statements used in newer code.

**Options:**
1. Install newer Python from repos — deadsnakes PPA on Ubuntu, AppStream
   on RHEL/Rocky, dnf on Fedora (recommended, manual instructions)
2. Build newer Python from source using `make altinstall`

#### python_macos_xcode_clt_missing
**Scenario:** On macOS, python3 is provided by Xcode Command Line Tools.
If CLT is not installed, running `python3` triggers a GUI popup or errors
out with `xcode-select`. This is macOS-specific.

**Options:**
1. Install Xcode CLT via `xcode-select --install` (recommended)
2. Install Python via Homebrew (independent of CLT)

---

## 6. Handler Layers

### Layer 1: INFRA_HANDLERS (existing)
9 cross-tool handlers apply. No changes needed.

### Layer 2: METHOD_FAMILY_HANDLERS
- `apt` family: 2 handlers — existing
- `dnf` family: 1 handler — existing
- `apk` family: 2 handlers — existing
- `pacman` family: 2 handlers — existing
- `zypper` family: 2 handlers — existing
- `brew` family: 1 handler — existing
- `_default` family: 5 handlers — existing

### Layer 3: Recipe on_failure (added)
7 handlers added. See §5.2.

---

## 7. Per-system behavior across 19 presets

| Preset | Family | PM | Python3 pre-installed? | Notes |
|--------|--------|-----|----------------------|-------|
| `debian_11` | debian | apt | ✅ Yes | Python 3.9 |
| `debian_12` | debian | apt | ✅ Yes | Python 3.11 |
| `docker_debian_12` | debian | apt | ✅ Yes | Python 3.11 |
| `ubuntu_2004` | debian | apt | ✅ Yes | Python 3.8 |
| `ubuntu_2204` | debian | apt | ✅ Yes | Python 3.10 |
| `ubuntu_2404` | debian | apt | ✅ Yes | Python 3.12 |
| `raspbian_bookworm` | debian | apt | ✅ Yes | Python 3.11, ARM64 |
| `wsl2_ubuntu_2204` | debian | apt | ✅ Yes | Python 3.10 |
| `fedora_39` | rhel | dnf | ✅ Yes | Python 3.12 |
| `fedora_41` | rhel | dnf | ✅ Yes | Python 3.13 |
| `centos_stream9` | rhel | dnf | ✅ Yes | Python 3.9 |
| `rocky_9` | rhel | dnf | ✅ Yes | Python 3.9 |
| `alpine_318` | alpine | apk | ✅ Yes | Python 3.11 |
| `alpine_320` | alpine | apk | ✅ Yes | Python 3.12 |
| `arch_latest` | arch | pacman | ✅ Yes | Python 3.12+ |
| `opensuse_15` | suse | zypper | ✅ Yes | Python 3.6 (old!) |
| `macos_14_arm` | macos | brew | ⚠️ Xcode | Apple ships Python via Xcode CLT |
| `macos_13_x86` | macos | brew | ⚠️ Xcode | Apple ships Python via Xcode CLT |
| `k8s_alpine_318` | alpine | apk | ⚠️ ro | Read-only rootfs, may be missing |

---

## 8. Resolver Data

### KNOWN_PACKAGES
Existing entry is correct:
```python
"python3": {
    "apt": "python3", "dnf": "python3",
    "apk": "python3", "pacman": "python",
    "zypper": "python3", "brew": "python@3",
},
```

### LIB_TO_PACKAGE_MAP
Build dependencies (libssl-dev, libffi-dev, etc.) are already covered
in the existing `LIB_TO_PACKAGE_MAP`. No changes needed.

---

## 9. Recipe — After

```python
"python": {
    "label": "Python",
    "cli": "python3",
    "category": "language",
    "install": {
        "apt":    ["apt-get", "install", "-y", "python3"],
        "dnf":    ["dnf", "install", "-y", "python3"],
        "apk":    ["apk", "add", "python3"],
        "pacman": ["pacman", "-S", "--noconfirm", "python"],
        "zypper": ["zypper", "install", "-y", "python3"],
        "brew":   ["brew", "install", "python@3"],
        "_default": [
            "bash", "-c",
            "PY_VERSION=$(curl -sSf https://www.python.org/ftp/python/"
            " | grep -oP '(?<=href=\")3\\.\\d+\\.\\d+(?=/\")'"
            " | sort -V | tail -1) && "
            "curl -sSfL \"https://www.python.org/ftp/python/"
            "${PY_VERSION}/Python-${PY_VERSION}.tgz\""
            " -o /tmp/python.tgz && ..."
        ],
    },
    "needs_sudo": {
        "apt": True, "dnf": True, "apk": True,
        "pacman": True, "zypper": True, "brew": False,
        "_default": True,
    },
    "requires": {
        "binaries": ["curl"],
        "packages": {
            "debian": ["build-essential", "libssl-dev", ...],
            "rhel": ["gcc", "make", "openssl-devel", ...],
            ...
        },
    },
    "verify": ["python3", "--version"],
    # update: derived by get_update_map() for PM methods
    # on_failure: in TOOL_FAILURE_HANDLERS["python"]
}
```

---

## 10. Validation Results

```
Schema:    VALID (recipe + 7 on_failure handlers)
Coverage:  589/589 (100%) — 31 scenarios × 19 presets
Handlers:  15 PM-family + 5 _default + 7 on_failure + 9 INFRA = 31 total
```

---

## 11. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Added `category: "language"` |
| `data/recipes.py` | Added `_default` install (source build from python.org) |
| `data/recipes.py` | Added `_default` to `needs_sudo` |
| `data/recipes.py` | Added `requires` with build deps for 5 families |
| `data/recipes.py` | Removed explicit `update` (now derived by Evolution D) |
| `data/tool_failure_handlers.py` | Added 7 handlers: `python_not_found`, `python_ssl_module_missing`, `python_tkinter_missing`, `python_libpython_missing`, `python_zlib_missing`, `python_version_too_old`, `python_macos_xcode_clt_missing` |

---

## 12. Update Derivation

Python has no explicit `update` map. Evolution D's `get_update_map()` derives
PM update commands automatically:

| PM | Derived update command |
|----|----------------------|
| apt | `apt-get install --only-upgrade -y python3` |
| dnf | `dnf upgrade -y python3` |
| apk | `apk upgrade python3` |
| pacman | `pacman -S --noconfirm python` |
| zypper | `zypper update -y python3` |
| brew | `brew upgrade python@3` |
| _default | Not derivable (source build) |
