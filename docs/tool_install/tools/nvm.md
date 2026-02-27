# nvm — Full Spectrum Analysis

> **Tool ID:** `nvm`
> **Last audited:** 2026-02-26
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | nvm — Node Version Manager |
| Language | Shell script (bash) |
| CLI binary | `nvm` — **shell function, NOT a binary** |
| Category | `node` |
| Verify command | `bash -c '[ -s "$HOME/.nvm/nvm.sh" ]'` |
| Recipe key | `nvm` |

### Critical: nvm is a shell function

Unlike every other tool in the system, nvm is NOT a binary on PATH.
It's a shell function sourced from `~/.nvm/nvm.sh` into the current
shell session. This has major implications:

- `shutil.which("nvm")` will **NEVER** return a result
- `which nvm` returns nothing
- `type nvm` outputs "nvm is a function" (only in sourced shells)
- Verify checks for the **file** `~/.nvm/nvm.sh` instead of running `nvm --version`
- The `_install_cmd` in KNOWN_PACKAGES already handles this correctly

### What nvm does

nvm manages multiple Node.js versions on a single system. After
installation, users run:
```bash
nvm install 20        # install Node 20
nvm use 20            # switch to Node 20
nvm alias default 20  # set default
```

Node.js versions are installed to `~/.nvm/versions/node/`.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ❌ | — | Not in Debian/Ubuntu repos |
| `dnf` | ❌ | — | Not in Fedora/RHEL repos |
| `apk` | ❌ | — | Not in Alpine repos |
| `pacman` | ❌ | — | AUR only, not official |
| `zypper` | ❌ | — | Not in openSUSE repos |
| `brew` | ✅ | `nvm` | formulae.brew.sh |
| `snap` | ❌ | — | Not available |
| `pip` | ❌ | — | Not Python |
| `npm` | ❌ | — | Circular dependency (nvm installs node which provides npm) |
| `cargo` | ❌ | — | Not Rust |

### Why so few PM packages?

nvm is fundamentally a user-space tool. It installs Node.js
versions into `~/.nvm/`, not system-wide. System PMs would
conflict with this model — if you `apt install nodejs`, that's
a system-wide Node.js, not managed by nvm.

The nvm team explicitly recommends the installer script over any
PM package for this reason.

---

## 3. Install Methods

### _default (official installer script) — PREFERRED

```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.4/install.sh | bash
```

The installer:
1. Clones the nvm repo to `~/.nvm`
2. Adds sourcing lines to shell config (`~/.bashrc`, `~/.zshrc`, etc.)
3. Does NOT require root/sudo

### brew

```bash
brew install nvm
```

Homebrew formula. Requires additional manual setup:
- Create `~/.nvm` directory
- Add sourcing lines to shell config

### Why prefer _default over brew

The official installer is more reliable and self-contained:
- brew's nvm formula has caveats about manual setup
- The official installer auto-configures shell profiles
- brew is macOS-centric; _default works everywhere

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Required | `curl` | Downloads the installer script |
| Required | `bash` | Installer is a bash script; Alpine needs bash explicitly |
| Optional | `git` | Used by nvm internally for updates (already present on most systems) |

### Alpine Linux special case

Alpine ships with BusyBox's `sh`, not bash. nvm requires bash
explicitly. The recipe's `requires.binaries` includes `bash` which
will trigger the `missing_curl`/`missing_bash` handlers if absent.

---

## 5. Post-install

nvm requires shell sourcing to work. The `post_env` handles this:

```bash
export NVM_DIR="$HOME/.nvm" && \
  [ -s "$NVM_DIR/nvm.sh" ] && \
  source "$NVM_DIR/nvm.sh"
```

This must be in the user's shell config for nvm to be available
in new shells. The official installer adds this automatically.

### Verify strategy

Since nvm is a shell function, not a binary, the verify command
checks for file existence instead:

```bash
bash -c '[ -s "$HOME/.nvm/nvm.sh" ]'
```

This returns exit code 0 if `~/.nvm/nvm.sh` exists and is non-empty.

---

## 6. Update

The official update method (from nvm's docs) is:
```bash
cd "$NVM_DIR" && git fetch --tags origin && \
  git checkout $(git describe --abbrev=0 --tags \
    --match 'v[0-9]*' $(git rev-list --tags --max-count=1)) && \
  source "$NVM_DIR/nvm.sh"
```

This fetches the latest release tag and switches to it.

For brew: `brew upgrade nvm`

---

## 7. Failure Handlers

### Layer 1: method-family handlers
nvm inherits handlers from its install methods:

**brew (1):** formula not found
**_default (5):** curl/git/wget/unzip/npm missing

### Layer 2: category-mapped handlers (npm)
nvm's category is `node`, which maps to the `npm` method-family.
This pulls in 12 npm handlers — while nvm itself doesn't use npm
for installation, these handlers would apply to any npm-based
operations triggered through the nvm-managed Node.js.

### Layer 3: INFRA handlers (9 cross-tool)
Network, disk, permissions, OOM, timeout — all standard.

### Layer 4: per-tool on_failure handlers (2)

| Handler | Category | Trigger | Options |
|---------|----------|---------|---------|
| `nvm_dir_exists` | environment | `~/.nvm already exists and is not an empty directory` — git clone fails over existing dir | Remove ~/.nvm and retry (recommended), switch to brew |
| `nvm_profile_not_found` | configuration | `Profile not found` — installer can't add nvm sourcing to shell config | Create ~/.bashrc with config (recommended), manual instructions |

---

## 8. Recipe Structure

```python
"nvm": {
    "cli": "nvm",
    "label": "nvm (Node Version Manager)",
    "category": "node",
    "install": {
        "brew": ["brew", "install", "nvm"],
        "_default": [
            "bash", "-c",
            "curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/"
            "v0.40.4/install.sh | bash",
        ],
    },
    "needs_sudo": {
        "brew": False,
        "_default": False,
    },
    "prefer": ["_default", "brew"],
    "requires": {"binaries": ["curl", "bash"]},
    "post_env": (
        'export NVM_DIR="$HOME/.nvm" && '
        '[ -s "$NVM_DIR/nvm.sh" ] && '
        'source "$NVM_DIR/nvm.sh"'
    ),
    "verify": ["bash", "-c", '[ -s "$HOME/.nvm/nvm.sh" ]'],
    "update": {
        "_default": [...git checkout latest tag...],
        "brew": ["brew", "upgrade", "nvm"],
    },
}
```

---

## 9. Validation Results

```
Schema:    VALID (recipe + all method-family handlers + on_failure)
Coverage:  551/551 (100%) — 29 scenarios × 19 presets
Handlers:  1 brew + 5 _default + 12 npm (via category) + 2 on_failure + 9 INFRA = 29 total
```

---

## 10. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Created nvm recipe (2 install methods, prefer, requires, post_env, update) |
| `data/tool_failure_handlers.py` | Added 2 on_failure handlers (dir exists, profile not found) |

### Pre-existing
| File | Already existed |
|------|----------------|
| `resolver/dynamic_dep_resolver.py` | nvm already in KNOWN_PACKAGES with `_install_cmd` |

---

## 11. Design Notes

### nvm vs fnm vs n

There are several Node version managers:
- **nvm** — the original, most widely used, shell function
- **fnm** — Rust binary, faster, works like nvm
- **n** — npm package (`npm install -g n`), simpler

We support nvm because it's the de facto standard. fnm and n
could be added later if needed.

### Shell function challenge

nvm being a shell function creates a fundamental challenge for
any tool installation system that relies on `shutil.which()` or
`which` to detect presence. Our solution: verify by checking for
the `~/.nvm/nvm.sh` file existence instead.

This is documented in the recipe comments and in the verify
command design.

### No sudo needed

nvm is entirely user-space. Both install methods have
`needs_sudo: False`. This is correct — nvm installs to `~/.nvm`
and writes to user shell configs.

### Version pinning in installer URL

The `_default` installer URL pins to `v0.40.4` (latest as of
Jan 2026). This is intentional:
- Using `/HEAD/install.sh` would always get latest (unstable)
- The pinned URL ensures reproducibility
- The `update` command handles upgrading to latest

When nvm releases a new major version, the recipe URL should be
updated.
