# go — Full Spectrum Analysis

> **Tool ID:** `go`
> **Last audited:** 2026-02-26 (re-audited — fixed missing cli + handler schema)
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | Go — programming language and toolchain |
| Language | Go (self-hosted) |
| CLI binary | `go` |
| Category | `language` |
| Verify command | `go version` |
| Recipe key | `go` |

### Special notes
- Go has no separate toolchain manager like rustup. The `go` binary
  IS the toolchain.
- Two installation paths:
  1. **_default (recommended)** — binary tarball from go.dev, always
     latest stable. Installs to `/usr/local/go/`. Needs sudo.
  2. **System packages** — apt/dnf/apk/pacman/zypper install from
     distro repos. Can lag significantly (e.g. Ubuntu 22.04 ships
     Go 1.18 vs current 1.26+).
  3. **snap** — provides near-latest builds via Canonical packaging.
- `/usr/local/go/bin` is NOT in PATH by default on most systems.
  The recipe includes `post_env` to handle this.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ✅ | `golang-go` | Debian/Ubuntu. `golang` is a meta-package |
| `dnf` | ✅ | `golang` | Fedora/RHEL |
| `apk` | ✅ | `go` | Alpine community repo |
| `pacman` | ✅ | `go` | Arch extra repo |
| `zypper` | ✅ | `go` | openSUSE devel:languages:go repo |
| `brew` | ✅ | `go` | formulae.brew.sh |
| `snap` | ✅ | `go --classic` | Canonical packaging, near-latest |
| `pip` | ❌ | — | Not available |
| `npm` | ❌ | — | Not available |
| `cargo` | ❌ | — | Not available |

### Package name notes
- **apt:** `golang-go` is the tools package (compiler, linker, etc.).
  `golang` is a transitional meta-package that pulls in `golang-go`
  and `golang-src`. The recipe uses `golang-go` directly.
- **dnf:** `golang` provides everything on Fedora/RHEL.

---

## 3. Binary Download (_default)

| Field | Value |
|-------|-------|
| Releases | https://go.dev/dl/ |
| Version API | `https://go.dev/VERSION?m=text` (returns e.g. `go1.26.0`) |
| URL pattern | `https://go.dev/dl/${GO_VERSION}.linux-{arch}.tar.gz` |
| Archive format | `.tar.gz` containing `/go/` directory |
| Arch naming | `amd64`, `arm64`, `armv6l`, `386` |
| OS naming | `linux`, `darwin`, `windows` |
| Install location | `/usr/local/go/` |
| Dependencies | `curl` (download), `tar` (extraction) |
| needs_sudo | Yes (writes to `/usr/local/`) |

### Architecture mapping
go.dev uses Go's native arch names which mostly match `_IARCH_MAP`:

| `platform.machine()` | `_IARCH_MAP` | go.dev | Match? |
|-----------------------|-------------|--------|--------|
| `x86_64` | `amd64` | `amd64` | ✅ |
| `aarch64` | `arm64` | `arm64` | ✅ |
| `armv7l` | `armhf` | `armv6l` | ❌ — needs `arch_map` override |

**Fix applied:** `arch_map: {"armv7l": "armv6l"}` overrides `_IARCH_MAP`
for 32-bit ARM only. Other arches fall through to `_IARCH_MAP` correctly.

### _default install command
```bash
GO_VERSION=$(curl -sSf https://go.dev/VERSION?m=text | head -1) && \
curl -sSfL "https://go.dev/dl/${GO_VERSION}.linux-{arch}.tar.gz" \
  -o /tmp/go.tar.gz && \
rm -rf /usr/local/go && \
tar -C /usr/local -xzf /tmp/go.tar.gz && \
rm /tmp/go.tar.gz
```

### Why `rm -rf /usr/local/go` before extraction?
The Go project explicitly recommends removing the old installation
before extracting the new one. Go does NOT support in-place upgrades
because leftover files from old versions can cause subtle build issues.

---

## 4. Build from Source

| Field | Value |
|-------|-------|
| Build system | Go (bootstrapping) |
| Git repo | https://go.googlesource.com/go |
| Build deps | Existing Go toolchain (Go 1.22+ to bootstrap), `git`, C compiler |
| Complexity | Very high (requires bootstrap chain) |

Not included in recipe — bootstrapping Go from source requires an
existing Go compiler. The `_default` (go.dev binary) path is always
available and much simpler.

---

## 5. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Download | `curl` | For `_default` install method |
| Extraction | `tar` | For extracting `.tar.gz` (usually pre-installed) |
| Runtime | None | Self-contained once installed |

### Reverse deps
Go is a dependency for tools installed via `go install`:
- `gh`, `lazygit`, `lazydocker`, `act`, `golangci-lint`, `gopls`,
  `gofumpt`, `air`, `delve`, `ko`, `hugo`, `terraform` (build dep),
  `kind`, `k9s`, etc.

---

## 6. Failure Surface

### 6.1 Per-install-method failures
All PM-based install methods have dedicated Layer 2 METHOD_FAMILY_HANDLERS:

| PM | Handlers | IDs |
|----|---------|-----|
| `apt` | Package not found, DB locked | `apt_stale_index`, `apt_locked` |
| `dnf` | Package not found | `dnf_no_match` |
| `apk` | Unsatisfiable constraints, DB locked | `apk_unsatisfiable`, `apk_locked` |
| `pacman` | Target not found, DB locked | `pacman_target_not_found`, `pacman_locked` |
| `zypper` | Package not found, PM locked | `zypper_not_found`, `zypper_locked` |
| `brew` | Formula not found | `brew_no_formula` |
| `snap` | snapd not available | `snapd_unavailable` |
| `_default` | Missing curl/git/wget/unzip/npm | 5 dependency handlers |

All methods also inherit Layer 1 INFRA_HANDLERS (network, disk, permissions,
timeout, OOM — 9 total).

### 6.2 Tool-specific failures (Layer 3 on_failure)

| Failure | Pattern | Category | Handler ID |
|---------|---------|----------|-----------|
| GOPATH permission denied | `permission denied.*gopath`, `GOPATH.*permission denied` | permissions | `go_gopath_permission` |
| Go not in PATH | `go: command not found` | environment | `go_path_not_set` |
| noexec /tmp blocks build | `permission denied.*/tmp/go-build`, `fork/exec /tmp/go-build.*` | environment | `go_noexec_tmp` |

#### go_gopath_permission
**Scenario:** Directories under `~/go` (GOPATH) were created by root
(e.g. via `sudo go install`). Subsequent non-root `go install` calls
fail with permission denied on the module cache.

**Options:**
1. Fix GOPATH ownership: `chown -R $USER:$USER ${GOPATH:-$HOME/go}` (recommended)

#### go_path_not_set
**Scenario:** After `_default` install, `/usr/local/go/bin` is not in
PATH. User's shell can't find `go`.

**Options:**
1. Add Go to PATH in `~/.profile` (recommended)

#### go_noexec_tmp
**Scenario:** On hardened systems where `/tmp` is mounted with `noexec`,
Go cannot compile because it builds to `/tmp/go-build*` and tries to
execute the compiled binary from there.

**Options:**
1. Set `GOTMPDIR=$HOME/go_tmp` — redirects Go's temp dir (recommended)

### 6.3 Go-as-method failures (Layer 2 go family)
These apply when Go is used to install OTHER tools (`go install <module>@latest`):

| Failure | Pattern | Category | Handler ID |
|---------|---------|----------|-----------|
| Go version too old | `requires go >= X.Y`, `module requires Go X.Y` | dependency | `go_version_mismatch` |
| CGO needs C compiler | `cgo: C compiler "gcc" not found` | dependency | `go_cgo_missing_compiler` |
| Module not found | `go: module ... not found`, `404 Not Found` | dependency | `go_module_not_found` |

---

## 7. Handler Layers

### Layer 1: INFRA_HANDLERS (existing)
9 cross-tool handlers apply. No changes needed.

### Layer 2: METHOD_FAMILY_HANDLERS
- `apt` family: `apt_stale_index`, `apt_locked` — existing
- `dnf` family: `dnf_no_match` — existing
- `apk` family: `apk_unsatisfiable`, `apk_locked` — existing
- `pacman` family: `pacman_target_not_found`, `pacman_locked` — existing
- `zypper` family: `zypper_not_found`, `zypper_locked` — existing
- `brew` family: `brew_no_formula` — existing
- `snap` family: `snapd_unavailable` — existing
- `_default` family: 5 handlers (missing_curl, etc.) — existing
- `go` family: 3 handlers — **ALL NEW**

### Layer 3: Recipe on_failure (added)
3 handlers added. See §6.2.

---

## 8. Availability Gates

No new capability gates needed. All existing gates correctly handle
Go's methods:

| Gate | Result |
|------|--------|
| Native PM (apt/dnf/apk/pacman/zypper) | Existing — impossible if not on system |
| Installable PM (brew/snap) | Existing — locked if not present |
| snap + systemd | Existing — impossible without systemd |
| Language PM (go as method) | Existing — locked if go not on PATH |
| Read-only rootfs | Existing — impossible for install_packages |
| Architecture | `arch_map` override for armv7l → armv6l |

---

## 9. Resolver Data

### KNOWN_PACKAGES
Updated `go` entry with correct per-PM package names:
```python
"go": {
    "apt": "golang-go", "dnf": "golang",
    "apk": "go", "pacman": "go",
    "zypper": "go", "brew": "go",
    "snap": "go",
},
```

**Fix applied:** `apt` was `golang` (meta-package), changed to
`golang-go` (actual tools package) to match recipe.

### LIB_TO_PACKAGE_MAP
No C library dependencies for Go itself. No changes needed.

---

## 10. Recipe — After

```python
"go": {
    "cli": "go",
    "label": "Go",
    "category": "language",
    "install": {
        "apt":    ["apt-get", "install", "-y", "golang-go"],
        "dnf":    ["dnf", "install", "-y", "golang"],
        "apk":    ["apk", "add", "go"],
        "pacman": ["pacman", "-S", "--noconfirm", "go"],
        "zypper": ["zypper", "install", "-y", "go"],
        "brew":   ["brew", "install", "go"],
        "snap":   ["snap", "install", "go", "--classic"],
        "_default": [...],  # go.dev binary tarball
    },
    "needs_sudo": {
        "apt": True, "dnf": True, "apk": True,
        "pacman": True, "zypper": True, "brew": False,
        "snap": True, "_default": True,
    },
    "prefer": ["_default", "snap", "brew"],
    "requires": {"binaries": ["curl"]},
    "arch_map": {"armv7l": "armv6l"},
    "post_env": "export PATH=$PATH:/usr/local/go/bin",
    "verify": ["bash", "-c", "export PATH=... && go version"],
    "update": {
        "apt":    [..., "golang-go"],
        "dnf":    [..., "golang"],
        ...
        "_default": [...],  # same as install (idempotent)
    },
    "on_failure": [
        # go_gopath_permission — 1 option (env_fix)
        # go_path_not_set — 1 option (env_fix)
        # go_noexec_tmp — 1 option (env_fix)
    ],
},
```

---

## 11. Validation Results

```
Schema:    VALID (recipe + 3 on_failure handlers + 3 go method handlers)
Coverage:  589/589 (100%) — 31 scenarios × 19 presets
Handlers:  19 PM-family + 3 go-method + 3 on_failure + 9 INFRA = 31 total
```

---

## 12. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Added `cli: "go"` (was missing from recipe despite docs claiming it) |
| `data/recipes.py` | Added `_default` install method (go.dev binary tarball) |
| `data/recipes.py` | Added `zypper` install/update method |
| `data/recipes.py` | Added `requires: {"binaries": ["curl"]}` |
| `data/recipes.py` | Added `arch_map: {"armv7l": "armv6l"}` |
| `data/recipes.py` | Added `post_env` for `/usr/local/go/bin` |
| `data/recipes.py` | Fixed `verify` to include PATH for _default |
| `data/recipes.py` | Fixed `prefer` — `_default` first for latest stable |
| `data/recipes.py` | Added `_default` update method (idempotent redownload) |
| `data/recipes.py` | Added 3 `on_failure` handlers (GOPATH perms, PATH, noexec /tmp) |
| `resolver/dynamic_dep_resolver.py` | Fixed `apt: "golang-go"`, added `snap: "go"` |
| `data/remediation_handlers.py` | Added `go` METHOD_FAMILY_HANDLERS (3 handlers) |
| `data/remediation_handlers.py` | Fixed `go_cgo_missing_compiler` handler: `packages` was a bare string `"build_tools"`, must be a per-family dict |

---

## 13. Raspbian / ARM Notes

| Aspect | Status |
|--------|--------|
| `_default` (go.dev binary) | ✅ `armv6l` tarball available on go.dev |
| `apt` (golang-go package) | ✅ Available in Raspbian repos (often outdated) |
| aarch64 (64-bit Pi 4/5) | ✅ `arm64` tarball correct via `_IARCH_MAP` |
| armv7l (32-bit Pi 3/4) | ✅ `armv6l` via `arch_map` override |
| armv6l (Pi Zero/1) | ✅ Go supports ARMv6 natively |
| `/usr/local/go/bin` PATH | ⚠️ Handled by `post_env` and `go_path_not_set` handler |
