# cargo — Full Spectrum Analysis

> **Tool ID:** `cargo`
> **Last audited:** 2026-02-26
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | Cargo — Rust package manager and build system |
| Language | Rust (self-hosted) |
| CLI binary | `cargo` |
| Category | `language` |
| Verify command | `cargo --version` |
| Recipe key | `cargo` |

### Special notes
- Cargo is distributed alongside `rustc` and `rustup`. Installing cargo
  means installing the Rust toolchain.
- Two fundamentally different installation paths exist:
  1. **rustup (recommended)** — `_default`, `brew`, `pacman`, `snap` all
     install rustup first, which then manages cargo + rustc + rust-std.
     Always provides latest stable. Installs user-locally to `$HOME/.cargo/bin`.
  2. **System packages** — `apt`, `dnf`, `apk`, `zypper` install cargo
     directly from distro repos. These versions can lag significantly
     (e.g. Ubuntu 22.04 ships Rust 1.66 vs current 1.83+).
- The `prefer` field routes to `_default` first because rustup always
  gives the latest stable.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ✅ | `cargo` | Distro repo, often outdated |
| `dnf` | ✅ | `cargo` | Distro repo, often outdated |
| `apk` | ✅ | `cargo` | Alpine community repo |
| `pacman` | ✅ | `rustup` | Arch's recommendation — provides cargo via `rustup default stable` |
| `zypper` | ✅ | `cargo` | openSUSE repo |
| `brew` | ✅ | `rustup` | Installs `rustup-init`, then `rustup-init -y` provides cargo |
| `snap` | ✅ | `rustup --classic` | Provides rustup, then `rustup default stable` provides cargo |
| `pip` | ❌ | — | Not available |
| `npm` | ❌ | — | Not available |
| `go` | ❌ | — | Not available |

### Multi-step installs (critical)
`pacman`, `brew`, and `snap` install **rustup** (the manager), NOT cargo.
After the package install, a second command is required to actually produce
a usable cargo binary:

| PM | Step 1 (package install) | Step 2 (toolchain install) |
|----|--------------------------|---------------------------|
| `pacman` | `pacman -S rustup` | `rustup default stable` |
| `brew` | `brew install rustup` | `rustup-init -y` |
| `snap` | `snap install rustup --classic` | `rustup default stable` |

Without step 2, `cargo --version` would fail.

---

## 3. Binary Download (_default)

| Field | Value |
|-------|-------|
| Method | `rustup.rs` convenience script |
| URL | `https://sh.rustup.rs` |
| Command | `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \| sh -s -- -y` |
| Install location | `$HOME/.cargo/bin/cargo` (user-local) |
| Dependencies | `curl` |
| needs_sudo | No |
| Post-install | `export PATH="$HOME/.cargo/bin:$PATH"` |

### Architecture handling
The rustup.rs script auto-detects the host architecture — no `{arch}`
substitution needed. No `arch_map` override required.

### Raspbian note
On Raspberry Pi with 64-bit kernel + 32-bit userland, rustup auto-detects
`aarch64` and installs 64-bit binaries that can't execute in the 32-bit
userland. See §6.2 for the remediation handler.

---

## 4. Build from Source

| Field | Value |
|-------|-------|
| Build system | Rust (bootstrapping) |
| Git repo | https://github.com/rust-lang/cargo.git |
| Build deps | Existing Rust toolchain, `git`, C compiler |
| Complexity | Very high (requires bootstrap chain) |

Not included in recipe — bootstrapping Rust from source requires an existing
Rust compiler. The `_default` (rustup) path is always available and much
simpler.

---

## 5. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Download | `curl` | For `_default` install method (rustup.rs) |
| Runtime | None | Self-contained once installed |

### Reverse deps
Cargo is a dependency for tools installed via `cargo install`:
- `ripgrep`, `fd`, `bat`, `exa`/`eza`, `delta`, `tokei`, `hyperfine`,
  `cargo-audit`, `cargo-outdated`, `cargo-edit`, `cargo-nextest`,
  `cargo-watch`, etc.

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
|---------|---------|----------|-----------:|
| Raspbian arch mismatch | `exec format error`, `cannot execute binary file`, `command failed.*cargo.*No such file or directory` | environment | `rustup_arch_mismatch` |
| Low memory during rustup | `Killed`, `SIGKILL`, `signal: 9`, `out of memory` (exit code 137) | resources | `rustup_low_memory` |

#### rustup_arch_mismatch
**Scenario:** Raspberry Pi with 64-bit kernel + 32-bit userland. `uname -m`
reports `aarch64`, rustup installs 64-bit binaries, but the 32-bit userland
can't execute them. Error appears during verify (`cargo --version`).

**Options:**
1. Reinstall with `--default-toolchain stable-armv7-unknown-linux-gnueabihf` (recommended)
2. Upgrade to 64-bit OS (manual)

#### rustup_low_memory
**Scenario:** Raspberry Pi or other low-RAM device. rustup is killed by OOM
during toolchain unpacking, especially when extracting `rust-docs` component.

**Options:**
1. Install with `--profile minimal` — skips rust-docs, only installs rustc+cargo+rust-std (recommended)
2. Set `RUSTUP_UNPACK_RAM=100000000` to limit unpack memory

### 6.3 Cargo-as-method failures (Layer 2 cargo family)
These apply when cargo is used to install OTHER tools (`cargo install <tool>`):

| Failure | Pattern | Category | Handler ID |
|---------|---------|----------|-----------:|
| Rust compiler too old | `requires rustc X.Y.Z or newer` | dependency | `rustc_version_mismatch` |
| GCC compiler bug | `COMPILER BUG DETECTED`, `memcmp` | compiler | `gcc_memcmp_bug` |
| Missing C library | `cannot find -l<lib>` | dependency | `missing_c_library` |
| Missing compiler | `linker cc not found` | dependency | `missing_compiler` |
| Missing pkg-config | `could not find pkg-config` | dependency | `missing_pkg_config` |
| Missing dev headers | `Package X was not found in pkg-config search path` | dependency | `missing_pkg_config_library` |

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
- `cargo` family: 6 handlers — 4 existing + **2 ADDED** (pkg-config)

### Layer 3: Recipe on_failure (added)
2 handlers added. See §6.2.

### Handler fixes applied
- `gcc_memcmp_bug`: Added `suse` and `macos` families to `install_packages`
- `missing_compiler`: Added `macos` family to `install_packages`

---

## 8. Availability Gates

No new capability gates needed. All existing gates correctly handle cargo's methods:

| Gate | Result |
|------|--------|
| Native PM (apt/dnf/apk/pacman/zypper) | Existing — impossible if not on system |
| Installable PM (brew/snap) | Existing — locked if not present |
| snap + systemd | Existing — impossible without systemd |
| Language PM (cargo as method) | Existing — locked if cargo not on PATH |
| Read-only rootfs | Existing — impossible for install_packages |
| Architecture | No exclusions needed (rustup supports all) |

---

## 9. Resolver Data

### KNOWN_PACKAGES
Added `cargo` entry with per-PM package names:
```python
"cargo": {
    "apt": "cargo", "dnf": "cargo",
    "apk": "cargo", "pacman": "rustup",
    "zypper": "cargo", "brew": "rustup",
},
```

Note: `pacman` and `brew` use `rustup` because those PMs install rustup
which then provides cargo. `apt`/`dnf`/`apk`/`zypper` install `cargo` directly.

### LIB_TO_PACKAGE_MAP
No C library dependencies for cargo itself. No changes needed.

### Special installers
rustup.rs is the `_default` install method — already handled by the recipe.

---

## 10. Recipe — After

```python
"cargo": {
    "cli": "cargo",
    "label": "Cargo (Rust)",
    "category": "language",
    "install": {
        "apt":    ["apt-get", "install", "-y", "cargo"],
        "dnf":    ["dnf", "install", "-y", "cargo"],
        "apk":    ["apk", "add", "cargo"],
        "pacman": ["bash", "-c",
                   "pacman -S --noconfirm rustup && "
                   "rustup default stable"],
        "zypper": ["zypper", "install", "-y", "cargo"],
        "brew":   ["bash", "-c",
                   "brew install rustup && "
                   "rustup-init -y"],
        "snap":   ["bash", "-c",
                   "snap install rustup --classic && "
                   "rustup default stable"],
        "_default": [
            "bash", "-c",
            "curl --proto '=https' --tlsv1.2 -sSf "
            "https://sh.rustup.rs | sh -s -- -y",
        ],
    },
    "needs_sudo": {
        "apt": True, "dnf": True, "apk": True,
        "pacman": True, "zypper": True,
        "brew": False, "snap": True, "_default": False,
    },
    "prefer": ["_default", "brew", "snap"],
    "requires": {"binaries": ["curl"]},
    "post_env": 'export PATH="$HOME/.cargo/bin:$PATH"',
    "verify": ["bash", "-c",
               'export PATH="$HOME/.cargo/bin:$PATH" && cargo --version'],
    "update": {
        "apt":    [..., "cargo"],
        "dnf":    [..., "cargo"],
        "apk":    [..., "cargo"],
        "pacman": ["bash", "-c", 'export PATH=... && rustup update'],
        "zypper": [..., "cargo"],
        "brew":   ["bash", "-c", 'export PATH=... && rustup update'],
        "snap":   ["bash", "-c", 'export PATH=... && rustup update'],
        "_default": ["bash", "-c", 'export PATH=... && rustup update'],
    },
    "on_failure": [
        # rustup_arch_mismatch — 2 options (env_fix, manual)
        # rustup_low_memory — 2 options (env_fix, retry_with_modifier)
    ],
},
```

---

## 11. Validation Results

```
Schema:    VALID (recipe + 2 on_failure handlers + 6 cargo method handlers)
Coverage:  627/627 (100%) — 33 scenarios × 19 presets
Handlers:  22 PM-family + 2 on_failure + 9 INFRA = 33 total scenarios
```

---

## 12. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Expanded cargo from _default-only stub to full 8-method recipe |
| `data/recipes.py` | Added `cli: "cargo"`, `category: "language"` |
| `data/recipes.py` | Fixed pacman/brew/snap to chain rustup toolchain install |
| `data/recipes.py` | Fixed update commands for pacman/brew/snap to use `rustup update` |
| `data/recipes.py` | Added 2 `on_failure` handlers (arch mismatch + low memory) |
| `resolver/dynamic_dep_resolver.py` | Added `cargo` to `KNOWN_PACKAGES` |
| `data/remediation_handlers.py` | Added `missing_pkg_config` handler (cargo method family) |
| `data/remediation_handlers.py` | Added `missing_pkg_config_library` handler (cargo method family) |
| `data/remediation_handlers.py` | Added `suse` + `macos` to `gcc_memcmp_bug` packages |
| `data/remediation_handlers.py` | Added `macos` to `missing_compiler` packages |

---

## 13. Raspbian / ARM Notes

| Aspect | Status |
|--------|--------|
| `_default` (rustup.rs) | ✅ Auto-detects architecture |
| `apt` (cargo package) | ✅ Available in Raspbian repos (often outdated) |
| aarch64 (64-bit Pi 4/5) | ✅ rustup installs aarch64 toolchain |
| armv7l (32-bit Pi 3/4) | ✅ rustup installs armv7 toolchain |
| 64-bit kernel + 32-bit userland | ⚠️ Handled by `rustup_arch_mismatch` on_failure handler |
| Low RAM (Pi Zero/1/2) | ⚠️ Handled by `rustup_low_memory` on_failure handler |
| `RUSTUP_UNPACK_RAM` | ✅ Available as remediation option |
| `--profile minimal` | ✅ Available as remediation option |
