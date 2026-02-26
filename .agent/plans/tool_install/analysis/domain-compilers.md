# Domain: Compilers

> ⚠️ **PHASE LABELS MAY BE STALE** — As of 2026-02-25, code has evolved far beyond
> what the phase roadmaps suggest. Many features labeled "Phase 4-8 future" are
> ALREADY IMPLEMENTED. See `audit-domain-docs.md` and `audit-missing-pieces.md`
> for the verified truth. Code is the source of truth, not these phase labels.


> This document catalogs compilers and toolchain packages relevant
> to the tool install system: gcc, g++, clang, rustc, go compiler.
> Covers detection, installation, meta-packages (build-essential),
> C library differences (glibc vs musl), and version management.
>
> SOURCE DOCS: scope-expansion §2.4 (build requirements),
>              phase2.2 §Category 4 (rustc via rustup),
>              domain-platforms (per-family toolchain packages),
>              domain-build-systems (build-essential tables)

---

## Overview

Compilers are needed in two scenarios:

1. **Building tools from source** — `cargo install` compiles Rust code.
   Some pip packages need a C compiler for native extensions.
2. **As user-installable tools** — developers need compilers to write
   and build their own code.

### Phase 2 reality

In Phase 2, compilers are relevant ONLY because:
- `cargo install` uses `rustc` (installed automatically via rustup)
- Cargo tools need system C libraries for linking (openssl, curl)
- `gcc` may be needed to compile C extensions during pip installs

No recipe directly requires the user to install gcc/clang.
But the build-essential meta-packages appear in the dependency
chain for cargo tools (linking against C libraries).

---

## C/C++ Compilers

### gcc (GNU Compiler Collection)

| Property | Value |
|----------|-------|
| **What it compiles** | C, C++, Fortran, Go, Ada, and more |
| **Binary (C)** | `gcc` |
| **Binary (C++)** | `g++` |
| **Default on** | All Linux distros (except macOS) |
| **Detection** | `shutil.which("gcc")` |

**Package names:**

| Family | C compiler | C++ compiler | Notes |
|--------|-----------|-------------|-------|
| debian | `gcc` | `g++` | Or via `build-essential` |
| rhel | `gcc` | `gcc-c++` | Or via `@development-tools` group |
| alpine | `gcc` | `g++` | Or via `build-base` |
| arch | `gcc` | (includes g++) | Or via `base-devel` group |
| suse | `gcc` | `gcc-c++` | Or via `devel_basis` pattern |
| macos | N/A (clang aliased as gcc) | N/A | Via Xcode CLI Tools |

### clang (LLVM)

| Property | Value |
|----------|-------|
| **What it compiles** | C, C++, Objective-C, CUDA |
| **Binary (C)** | `clang` |
| **Binary (C++)** | `clang++` |
| **Default on** | macOS (via Xcode CLI Tools) |
| **Detection** | `shutil.which("clang")` |

**Package names:**

| Family | Package | Notes |
|--------|---------|-------|
| debian | `clang` (or `clang-17` for specific version) | Not installed by default |
| rhel | `clang` | Not installed by default |
| alpine | `clang` | Not installed by default |
| arch | `clang` | Not installed by default |
| suse | `clang` | Not installed by default |
| macos | Xcode Command Line Tools | `xcode-select --install` |

### gcc vs clang on macOS

**Critical behavior:** On macOS, Apple aliases `gcc` → `clang`:

```bash
$ gcc --version
Apple clang version 15.0.0 (clang-1500.3.9.4)
```

This means:
- `shutil.which("gcc")` returns `/usr/bin/gcc` on macOS
- But it's actually clang, not GNU gcc
- This usually doesn't matter (clang is compatible for most builds)
- Detection: check `gcc --version` output for "clang" string

---

## Rust Compiler (rustc)

| Property | Value |
|----------|-------|
| **What it compiles** | Rust code |
| **Binary** | `rustc` |
| **Install method** | Via rustup (curl-pipe-bash) |
| **Install location** | `~/.cargo/bin/rustc` |
| **Detection** | `shutil.which("rustc")` |
| **Needs sudo** | No |

### How rustc is installed

rustc and cargo are ALWAYS installed together via rustup:

```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
```

This installs the entire Rust toolchain:

| Tool | Binary | Purpose |
|------|--------|---------|
| rustc | `~/.cargo/bin/rustc` | Compiler |
| cargo | `~/.cargo/bin/cargo` | Package manager + build tool |
| rustfmt | `~/.cargo/bin/rustfmt` | Code formatter |
| clippy | `~/.cargo/bin/cargo-clippy` | Linter |
| rustdoc | `~/.cargo/bin/rustdoc` | Documentation generator |
| rustup | `~/.cargo/bin/rustup` | Toolchain manager |

### Version management (rustup)

```bash
# Show current version
rustc --version    # rustc 1.75.0

# Update to latest stable
rustup update

# Install specific version
rustup install 1.74.0

# Switch versions
rustup default 1.74.0

# Install nightly
rustup install nightly
rustup default nightly
```

**Phase 2:** We install the latest stable. No version pinning.
`rustup update` is the update command in recipes.

### rustc as a dependency

In the recipe system, `rustc` and `cargo` share the same install
recipe. When `cargo` is in `requires.binaries`, installing it
implicitly installs `rustc` too.

---

## Go Compiler

| Property | Value |
|----------|-------|
| **What it compiles** | Go code |
| **Binary** | `go` |
| **Install method** | System package (apt/dnf/apk) or snap |
| **Detection** | `shutil.which("go")` |
| **Needs sudo** | Yes (system package) |

### Package names

| Family | Package | Notes |
|--------|---------|-------|
| debian | `golang-go` | |
| rhel | `golang` | |
| alpine | `go` | |
| arch | `go` | |
| suse | `go` | |
| macos | `go` (brew) | |
| snap | `go --classic` | |

### Go as a compiler for tool installs

`go install` downloads and compiles Go binaries:

```bash
go install golang.org/x/tools/gopls@latest
# Installs to ~/go/bin/
```

**Phase 2:** We don't use `go install` for any tool. Go is a
system package dependency only (some tools need Go to build).

---

## Toolchain Meta-Packages

Most distros bundle the essential build tools into a single
meta-package. Installing it satisfies most build requirements:

### build-essential (Debian family)

```bash
apt-get install -y build-essential
```

**What it installs:**

| Component | Package |
|-----------|---------|
| C compiler | `gcc` |
| C++ compiler | `g++` |
| Make | `make` |
| C library headers | `libc6-dev` |
| Debian build tools | `dpkg-dev` |

### @development-tools (RHEL family)

```bash
dnf groupinstall -y "Development Tools"
# Or: dnf group install -y development-tools
```

**What it installs:**

| Component | Package |
|-----------|---------|
| C compiler | `gcc` |
| C++ compiler | `gcc-c++` |
| Make | `make` |
| Autotools | `autoconf`, `automake` |
| Bison/Flex | `bison`, `flex` |
| And more | `binutils`, `libtool`, `pkgconf`, etc. |

### build-base (Alpine)

```bash
apk add build-base
```

**What it installs:**

| Component | Package |
|-----------|---------|
| C compiler | `gcc` |
| C++ compiler | `g++` |
| Make | `make` |
| musl headers | `musl-dev` |
| Binutils | `binutils` |
| Fortran | `fortran` |

### base-devel (Arch)

```bash
pacman -S --noconfirm base-devel
```

**What it installs:**

| Component | Package |
|-----------|---------|
| C compiler | `gcc` |
| Make | `make` |
| Autotools | `autoconf`, `automake` |
| pkg-config | `pkgconf` |
| And more | `binutils`, `libtool`, `patch`, etc. |

### devel_basis (SUSE)

```bash
zypper install -y -t pattern devel_basis
```

### Xcode Command Line Tools (macOS)

```bash
xcode-select --install
```

**What it provides:**

| Component | Tool |
|-----------|------|
| C/C++/ObjC compiler | `clang` (aliased as `gcc`) |
| Make | `make` (GNU Make) |
| Git | `git` |
| Linker | `ld` |
| Various utils | `ar`, `nm`, `strip`, etc. |

**Detection:**
```bash
xcode-select -p    # returns path if installed
# Or:
xcrun --show-sdk-path  # returns SDK path
```

**macOS note:** Xcode CLI Tools is the ONLY way to get compilers
on macOS (short of installing full Xcode from App Store or
building LLVM from source). `brew install gcc` gives GNU gcc
but most users use Apple's clang.

---

## C Library (libc)

The C library determines binary compatibility. Pre-compiled binaries
must match the target system's libc:

| libc | Used by | Impact on tool install |
|------|---------|----------------------|
| **glibc** | Debian, RHEL, Arch, SUSE | Standard. Most pre-built binaries target glibc. |
| **musl** | Alpine | Pre-built glibc binaries WON'T work. Need musl-specific builds or static linking. |
| **libSystem** | macOS | Apple's own. macOS binaries are separate from Linux anyway. |

### musl vs glibc impact

| Scenario | glibc (Debian/RHEL) | musl (Alpine) |
|----------|-------------------|--------------|
| Pre-built binary download | ✅ Works | ❌ Usually fails |
| pip wheels | ✅ manylinux wheels | ⚠️ Need musllinux wheels |
| cargo install (compile) | ✅ Links against glibc | ✅ Links against musl |
| System packages | ✅ Distro provides | ✅ Distro provides |
| Static binaries | ✅ Works | ✅ Works |

**Detection in system profile:**
```python
"libraries": {
    "libc_type": "glibc",  # or "musl" or "system"
    "libc_version": "2.36",
}
```

**Detection method:**
```bash
# Check for musl
ldd --version 2>&1 | head -1
# glibc: "ldd (Ubuntu GLIBC 2.35-0ubuntu3) 2.35"
# musl:  "musl libc (aarch64)"

# Or check the dynamic linker
file /lib/ld-*
# glibc: /lib/ld-linux-x86-64.so.2
# musl:  /lib/ld-musl-x86_64.so.1
```

### Impact on cargo tools

cargo-audit and cargo-outdated link against OpenSSL. On Alpine:
- Install `openssl-dev` (musl headers, not glibc headers)
- Cargo compiles against musl — produces musl binary
- This works correctly because `cargo install` builds from source

On Debian/RHEL:
- Install `libssl-dev` / `openssl-devel` (glibc headers)
- Cargo compiles against glibc — produces glibc binary
- This works correctly

**Conclusion:** libc type matters for PRE-BUILT binaries.
It does NOT matter for `cargo install` (compiles from source).

---

## Compiler Version Management

### System compiler versions

| Family | How to install specific version | Example |
|--------|-------------------------------|---------|
| debian | Versioned package: `gcc-13`, `clang-17` | `apt install gcc-13` |
| rhel | Via devtoolset/gcc-toolset SCL | `dnf install gcc-toolset-13` |
| alpine | Only current version | `apk add gcc` |
| arch | Only current version (rolling) | `pacman -S gcc` |
| macos | Xcode version determines clang version | Update Xcode |

### update-alternatives (Debian)

When multiple gcc versions are installed:

```bash
# Register versions
update-alternatives --install /usr/bin/gcc gcc /usr/bin/gcc-12 12
update-alternatives --install /usr/bin/gcc gcc /usr/bin/gcc-13 13

# Switch between versions
update-alternatives --config gcc
```

### rustc version management

Handled entirely by rustup (see rustc section above).
Most flexible version management of any compiler.

### Phase 2 stance

We do NOT manage compiler versions. The system's default compiler
is used for all builds. Compiler version pinning is a Phase 5+
concern for advanced build-from-source recipes.

---

## Detection Summary

| Compiler | Detection | Version check |
|----------|-----------|--------------|
| gcc | `shutil.which("gcc")` | `gcc --version` |
| g++ | `shutil.which("g++")` | `g++ --version` |
| clang | `shutil.which("clang")` | `clang --version` |
| rustc | `shutil.which("rustc")` | `rustc --version` |
| go | `shutil.which("go")` | `go version` |
| Xcode CLI | `xcode-select -p` | `clang --version` |

### Detection schema (IMPLEMENTED — differs from this spec)

```python
"compilers": {
    "cc": {"path": "/usr/bin/gcc", "version": "13.2.0", "type": "gcc"},
    "cxx": {"path": "/usr/bin/g++", "version": "13.2.0", "type": "gcc"},
    "rustc": {"path": "~/.cargo/bin/rustc", "version": "1.75.0",
              "manager": "rustup"},
    "go": {"path": "/usr/bin/go", "version": "1.21.5"},
},
"libc": {"type": "glibc", "version": "2.36"},
```

---

## Traceability

| Topic | Source |
|-------|--------|
| Build-from-source requires gcc/clang | scope-expansion §2.4 |
| build-essential per family | domain-platforms (6 families) |
| build-essential in build-systems | domain-build-systems §meta-packages |
| rustc via rustup | phase2.2 §Category 4 |
| rustup installs rustc + cargo | domain-language-pms §cargo |
| macOS clang-as-gcc | domain-platforms §macOS |
| musl vs glibc | domain-platforms §Alpine |
| libc_type in system profile | arch-system-model §libraries |
| Compiler choice as build flag | domain-build-systems §build flags |
| Cross-compile toolchains | domain-build-systems §cross-compilation |
