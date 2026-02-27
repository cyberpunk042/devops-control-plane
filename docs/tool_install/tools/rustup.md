# rustup — Full Spectrum Analysis

> **Tool ID:** `rustup`
> **Last audited:** 2026-02-26
> **Status:** ✅ Complete (coverage + remediation)

---

## 1. Identity

| Field | Value |
|-------|-------|
| Tool | rustup — official Rust toolchain installer and version manager |
| Language | Rust |
| CLI binary | `rustup` (also provides `rustup-init` on some PMs) |
| Category | `rust` |
| Verify command | `rustup --version` |
| Recipe key | `rustup` |

### What rustup does

rustup manages Rust toolchains (stable, beta, nightly) and
cross-compilation targets. After installation, it provides:
- `rustup` — the toolchain manager itself
- `rustc` — the Rust compiler
- `cargo` — the Rust package manager / build system

```bash
rustup default stable       # install/select stable
rustup update               # update all installed toolchains
rustup target add wasm32    # add cross-compilation target
```

### Relationship to cargo

rustup is to Rust what nvm is to Node. The existing `cargo`
recipe already uses rustup to install cargo on several PMs
(pacman, brew, snap all chain `rustup default stable`).
The rustup recipe makes rustup itself installable as a
standalone tool.

---

## 2. Package Availability

| PM | Available | Package name | Notes |
|----|-----------|--------------|-------|
| `apt` | ✅ | `rustup` | Debian 13+ / Ubuntu 24.04+ only |
| `dnf` | ✅ | `rustup` | Fedora; needs `rustup-init` after |
| `apk` | ✅ | `rustup` | Alpine; needs `rustup-init` after |
| `pacman` | ✅ | `rustup` | Arch official repos |
| `zypper` | ✅ | `rustup` | openSUSE |
| `brew` | ✅ | `rustup` | Homebrew; needs `rustup-init` after |
| `snap` | ✅ | `rustup` | snap --classic |
| `_default` | ✅ | — | `sh.rustup.rs` official installer |

### Package name consistency

Unusually, the package name is `rustup` everywhere. No name
divergence across package managers.

### PM install ≠ ready to use

**Critical:** On most PMs, `apt install rustup` / `dnf install rustup`
only provides the `rustup` or `rustup-init` binary. It does NOT
automatically install a Rust toolchain. Users must still run:
```bash
rustup default stable    # or: rustup-init -y
```
The recipe chains this automatically.

---

## 3. Install Methods

### _default (official installer) — PREFERRED

```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
```

The installer:
1. Downloads the correct `rustup-init` binary for the host arch
2. Installs rustup to `~/.cargo/bin`
3. Installs stable toolchain (rustc + cargo + rust-std)
4. Adds `~/.cargo/bin` to PATH in shell config
5. Does NOT require root/sudo

### PM methods (apt/dnf/apk/pacman/zypper/brew/snap)

All chain `rustup default stable` (or `rustup-init -y`, or
`rustup toolchain install stable`) after the package install
to ensure a toolchain is immediately available.

### Why prefer _default over PMs

1. Always latest version (PMs may lag)
2. Self-updating (`rustup self update`)
3. User-local install (no sudo)
4. Consistent behavior across all platforms

---

## 4. Dependencies

| Type | Dependency | Notes |
|------|-----------|-------|
| Required | `curl` | Downloads installer / initial binary |
| Optional | C compiler (gcc/clang) | Required to compile native crates later |

### Runtime: no C library deps

rustup itself is a static binary. However, many Rust
crates that users will later compile need a C linker,
which is handled by the cargo method-family handlers
(missing_compiler, missing_c_library, etc.).

---

## 5. Post-install

```bash
export PATH="$HOME/.cargo/bin:$PATH"
```

The official installer adds this to `~/.bashrc` / `~/.zshrc`
automatically. PM installs may or may not do this.

### Unlike nvm, rustup IS a binary

`shutil.which("rustup")` works after PATH is set.
No special file-existence check needed.

---

## 6. Update

Two update paths:
- **Self-update:** `rustup self update` — updates rustup itself
- **Toolchain update:** `rustup update` — updates installed toolchains

The recipe's `update._default` uses `rustup self update`.
PM-based updates use each PM's upgrade command.

---

## 7. Failure Handlers

### Layer 1: PM-family handlers (13 total)
apt (2), dnf (1), apk (2), pacman (2), zypper (2), brew (1),
snap (1), _default (5) — standard package manager handlers.

### Layer 2: category-mapped handlers (cargo — 6)
rustup's category is `rust`, mapped to the `cargo` method-family:

| Handler | Category | What it catches |
|---------|----------|----------------|
| `rustc_version_mismatch` | dependency | Rust compiler too old |
| `gcc_memcmp_bug` | compiler | GCC bug with aws-lc-sys |
| `missing_c_library` | dependency | Missing C library |
| `missing_compiler` | dependency | C/C++ compiler not found |
| `missing_pkg_config` | dependency | pkg-config not found |
| `missing_pkg_config_library` | dependency | System library not found |

### Layer 3: INFRA handlers (9 cross-tool)
Network, disk, permissions, OOM, timeout — all standard.

### Layer 4: per-tool on_failure handlers (2)

Mirrored from cargo's on_failure handlers — same root cause (sh.rustup.rs installer):

| Handler | Category | Trigger | Options |
|---------|----------|---------|---------|
| `rustup_arch_mismatch` | environment | Exec format error — 64-bit kernel + 32-bit userland (Raspberry Pi) | Reinstall for armv7 (recommended), upgrade to 64-bit OS |
| `rustup_low_memory` | resources | Killed/OOM during toolchain extraction | Minimal profile (recommended), limit unpack RAM |

### Shared concern with cargo

The `cargo` tool has identical handlers (`rustup_arch_mismatch`,
`rustup_low_memory`) because both tools use the same `sh.rustup.rs`
installer. Having them on both tools ensures proper remediation
regardless of whether the user asks to install "rustup" or "cargo".

---

## 8. Recipe Structure

```python
"rustup": {
    "cli": "rustup",
    "label": "rustup (Rust toolchain manager)",
    "category": "rust",
    "install": {
        "apt": [..., "rustup default stable"],
        "dnf": [..., "rustup-init -y"],
        "apk": [..., "rustup-init -y"],
        "pacman": [..., "rustup default stable"],
        "zypper": [..., "rustup toolchain install stable"],
        "brew": [..., "rustup-init -y"],
        "snap": [..., "rustup default stable"],
        "_default": ["bash", "-c", "curl ... | sh -s -- -y"],
    },
    "needs_sudo": {
        "apt": True, "dnf": True, "apk": True,
        "pacman": True, "zypper": True,
        "brew": False, "snap": True, "_default": False,
    },
    "prefer": ["_default", "brew", "pacman", "snap"],
    "requires": {"binaries": ["curl"]},
    "post_env": 'export PATH="$HOME/.cargo/bin:$PATH"',
    "verify": [..., "rustup --version"],
    "update": {
        "_default": [..., "rustup self update"],
        "apt": [...], "dnf": [...], ...
    },
}
```

---

## 9. Validation Results

```
Schema:    VALID (recipe + all method-family handlers + on_failure)
Coverage:  627/627 (100%) — 33 scenarios × 19 presets
Handlers:  13 PM-family + 6 cargo (via category) + 5 _default + 2 on_failure + 9 INFRA - 2 overlap = 33 total
```

---

## 10. Changes Applied

| File | Change |
|------|--------|
| `data/recipes.py` | Created rustup recipe (8 install methods, prefer, requires, post_env, update) |
| `data/tool_failure_handlers.py` | Added 2 on_failure handlers (arch mismatch, low memory) |

### Pre-existing
| File | Already existed |
|------|----------------|
| `resolver/dynamic_dep_resolver.py` | rustup already in KNOWN_PACKAGES with `_install_cmd` |
| `data/remediation_handlers.py` | cargo method-family handlers apply via category |
| `data/tool_failure_handlers.py` | cargo on_failure handlers reference rustup |

---

## 11. Design Notes

### rustup vs cargo: why separate recipes?

cargo is the build tool / package manager. rustup is the
version manager that installs cargo (and rustc). They serve
different purposes:

- "Install cargo" = I need to build/run Rust projects
- "Install rustup" = I need to manage Rust versions

Both use the same installer (`sh.rustup.rs`) and produce
the same result, but the user's intent differs.

### PM install chaining

The recipe chains `rustup default stable` after PM installs.
This is critical — without it, `rustup --version` works but
`rustc` and `cargo` don't exist yet. Different PMs use
different commands:
- `rustup default stable` — pacman, apt, snap
- `rustup-init -y` — dnf, apk, brew
- `rustup toolchain install stable` — zypper

### No KNOWN_PACKAGES change needed

The package name is `rustup` everywhere, and the
`_install_cmd` entry already exists. No divergence.
