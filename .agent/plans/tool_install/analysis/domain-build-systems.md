# Domain: Build Systems

> ⚠️ **PHASE LABELS MAY BE STALE** — As of 2026-02-25, code has evolved far beyond
> what the phase roadmaps suggest. Many features labeled "Phase 4-8 future" are
> ALREADY IMPLEMENTED. See `audit-domain-docs.md` and `audit-missing-pieces.md`
> for the verified truth. Code is the source of truth, not these phase labels.


> This document catalogs the build tools and build systems the tool
> install system encounters: cmake, make, meson, autotools, ninja,
> and cargo build. How they're detected, installed as recursive
> dependencies, invoked, and how build flags are managed.
>
> SOURCE DOCS: scope-expansion §2.4 (build from source),
>              scope-expansion §Phase 5 roadmap,
>              phase2.2 §Category 7 (make as system package),
>              arch-recipe-format §install_variants (build steps)

---

## Overview

Build systems are tools that COMPILE software from source code into
runnable binaries. They matter for the tool install system in two ways:

1. **As installable tools themselves** — make is a Category 7 system
   package that some users need for general development
2. **As recursive dependencies** — building cargo tools from source
   requires a compiler, make, and potentially cmake

### Phase 2 vs Phase 5

| Phase | Build system role |
|-------|-------------------|
| Phase 2 | `make` is a simple system package. `cargo build` happens transparently inside `cargo install`. No direct build system invocation. |
| Phase 5 | Full build-from-source support: configure → build → install. Build tools become first-class dependencies. |

---

## Build Systems Reference

### make (GNU Make)

| Property | Value |
|----------|-------|
| **What it does** | Reads `Makefile`, runs commands to build targets |
| **Install** | System package (same name everywhere) |
| **Package name** | `make` on all distros |
| **Binary** | `make` |
| **Detection** | `shutil.which("make")` |
| **Needs sudo** | Yes (system package install) |

**How it's used in tool installation:**

```bash
# Autotools-style project
./configure --prefix=/usr/local
make -j$(nproc)        # parallel build
sudo make install       # install to /usr/local

# cmake-generated Makefiles
cmake -B build
make -C build -j$(nproc)
sudo make -C build install
```

**`-j$(nproc)` flag:** Enables parallel compilation using all
available CPU cores. Critical for build performance.

**Current status:** `make` is a Category 7 system package in Phase 2.
It's installable via any system PM but is NOT used as a build tool
by any Phase 2 recipe.

### cmake

| Property | Value |
|----------|-------|
| **What it does** | Meta-build system: generates Makefiles or ninja files |
| **Install** | System package OR pip install OR binary download |
| **Package names** | `cmake` on all distros |
| **Binary** | `cmake` |
| **Detection** | `shutil.which("cmake")` |

**Three install methods for cmake itself:**

| Method | Command | Pro | Con |
|--------|---------|-----|-----|
| System PM | `apt-get install -y cmake` | Easy, managed | May be old version |
| pip | `pip install cmake` | Latest version | In Python venv only |
| Binary download | From cmake.org | Any version | Manual management |

**This is a recursive dependency problem:** If a tool needs cmake to
build, and cmake isn't installed, the resolver must install cmake
first — but cmake itself has multiple install methods.

**How cmake is invoked:**

```bash
# Configure (generate build files)
cmake -B build \
    -DCMAKE_BUILD_TYPE=Release \
    -DWITH_CUDA=ON \
    -DCMAKE_INSTALL_PREFIX=/usr/local

# Build
cmake --build build -j $(nproc)
# OR: make -C build -j$(nproc)
# OR: ninja -C build

# Install
sudo cmake --install build
# OR: sudo make -C build install
```

**Build flags (`-D` options):**
- `-DCMAKE_BUILD_TYPE=Release` — optimization level
- `-DWITH_CUDA=ON` — enable CUDA support
- `-DCMAKE_INSTALL_PREFIX=/usr/local` — where to install
- `-DBUILD_SHARED_LIBS=ON` — shared vs static libraries

**Recipe format for cmake builds (Phase 5):**
```python
"install_variants": {
    "build-from-source": {
        "steps": [
            {"label": "Configure build",
             "command": ["cmake", "-B", "build",
                         "-DCMAKE_BUILD_TYPE=Release",
                         "-DWITH_CUDA={cuda_flag}"],
             "needs_sudo": False},
            {"label": "Compile",
             "command": ["make", "-j{nproc}", "-C", "build"],
             "needs_sudo": False},
            {"label": "Install",
             "command": ["make", "-C", "build", "install"],
             "needs_sudo": True},
        ],
    },
},
```

### meson

| Property | Value |
|----------|-------|
| **What it does** | Modern build system (Python-based), generates ninja files |
| **Install** | System package or pip |
| **Package names** | `meson` on most distros |
| **Binary** | `meson` |
| **Detection** | `shutil.which("meson")` |

**How meson is invoked:**

```bash
# Configure
meson setup build --buildtype=release

# Build
ninja -C build

# Install
sudo ninja -C build install
```

**Meson always uses ninja** as the backend (not make). If a
recipe needs meson, it also needs ninja.

**Phase 2:** Not used by any recipe.
**Phase 5:** Would be added as a build backend option.

### autotools (configure/make)

| Property | Value |
|----------|-------|
| **What it does** | Classic Unix build system: `./configure && make && make install` |
| **Install** | `autoconf`, `automake`, `libtool` packages |
| **Detection** | `shutil.which("autoconf")` |

**The autotools trio:**

| Tool | Package (debian) | Package (rhel) | What it does |
|------|-----------------|---------------|-------------|
| autoconf | `autoconf` | `autoconf` | Generates `configure` script |
| automake | `automake` | `automake` | Generates `Makefile.in` |
| libtool | `libtool` | `libtool` | Handles shared libraries |

**How autotools projects are built:**

```bash
# If from git (no configure script yet)
autoreconf -i

# Standard build
./configure --prefix=/usr/local --with-ssl --without-gui
make -j$(nproc)
sudo make install
```

**Phase 2:** Not used by any recipe.
**Phase 5:** Would be added as a build backend alongside cmake.

### ninja

| Property | Value |
|----------|-------|
| **What it does** | Fast, low-level build executor (faster than make) |
| **Install** | System package |
| **Package names** | `ninja-build` (debian/rhel), `ninja` (alpine/arch/brew) |
| **Binary** | `ninja` |
| **Detection** | `shutil.which("ninja")` |

**How ninja is invoked:**

```bash
# Build (after cmake or meson configure)
ninja -C build

# Install
sudo ninja -C build install

# Parallel by default (uses all cores)
```

**ninja vs make:** ninja is 2-10x faster for incremental builds
because it tracks file timestamps more efficiently. cmake and
meson can generate ninja files instead of Makefiles.

### cargo build (implicit)

| Property | Value |
|----------|-------|
| **What it does** | Rust's build system, compiles Rust code |
| **Install** | Comes with cargo (via rustup) |
| **Binary** | `cargo` |

**How it's used in tool installation:**

```bash
# cargo install = download + compile + install
cargo install cargo-audit
```

**`cargo install` is a BUILD SYSTEM invocation.** It:
1. Downloads source from crates.io
2. Compiles with `rustc` (using all available cores)
3. Installs binary to `~/.cargo/bin/`

The user doesn't invoke `cargo build` directly — `cargo install`
handles the entire pipeline. This is why cargo tools take 2-8
minutes instead of seconds.

**Phase 2:** cargo build is used IMPLICITLY via `cargo install`.
No direct build system configuration needed.

---

## Build Tool Detection

### Phase 2 (current)

Build tools are detected like any other binary — `shutil.which()`:

```python
# Simple presence check
has_make = shutil.which("make") is not None
has_cmake = shutil.which("cmake") is not None
has_gcc = shutil.which("gcc") is not None
```

This is sufficient for Phase 2 because:
- `make` is a simple system package (install like any other)
- `cargo install` doesn't need make/cmake (cargo handles builds)

### Phase 5 (IMPLEMENTED — deep tier `_detect_compilers_and_build_tools()`)

```python
"build_tools": {
    "make": {"available": True, "version": "4.3"},
    "cmake": {"available": True, "version": "3.27.4"},
    "meson": {"available": False},
    "ninja": {"available": True, "version": "1.11.1"},
    "autoconf": {"available": False},
    "gcc": {"available": True, "version": "13.2.0"},
    "g++": {"available": True, "version": "13.2.0"},
    "clang": {"available": False},
    "nproc": 8,
}
```

---

## Build Tool as Recursive Dependency

When a tool needs building from source, the build tools themselves
become dependencies that may need installing:

```
opencv (build from source)
├── cmake         ← build tool (may need installing)
├── make          ← build tool (may need installing)
├── gcc/g++       ← compiler (may need installing)
├── python3-dev   ← dev headers
├── numpy         ← pip package
└── libopencv-dev ← system package
```

### Dependency resolution chain

```
1. Resolver sees: opencv requires cmake, make, gcc
2. shutil.which("cmake") → None (not installed)
3. Look up TOOL_RECIPES["cmake"]
4. cmake requires nothing (simple system package)
5. Insert: apt-get install -y cmake
6. Repeat for make, gcc
7. Then: configure → build → install opencv
```

### Build-essential packages

Most build chains need a C/C++ compiler + make. Distros bundle these:

| Family | Meta-package | Includes |
|--------|-------------|----------|
| debian | `build-essential` | gcc, g++, make, libc-dev, dpkg-dev |
| rhel | `@development-tools` (dnf group) | gcc, g++, make, binutils, etc. |
| alpine | `build-base` | gcc, g++, make, musl-dev, binutils |
| arch | `base-devel` (pacman group) | gcc, make, binutils, etc. |
| suse | `devel_basis` (zypper pattern) | gcc, g++, make, etc. |
| macos | Xcode Command Line Tools | clang, make, etc. |

**Installing the meta-package once** satisfies many build deps:

```python
# Instead of: apt-get install gcc g++ make
# Use:        apt-get install build-essential
```

---

## Build Flags and Configuration

### Flag categories

| Category | Example | When relevant |
|----------|---------|-------------|
| Build type | `-DCMAKE_BUILD_TYPE=Release` | Always (debug vs release) |
| Feature toggle | `-DWITH_CUDA=ON` | GPU support |
| Install prefix | `-DCMAKE_INSTALL_PREFIX=/usr/local` | Where to install |
| Library type | `-DBUILD_SHARED_LIBS=ON` | Shared vs static |
| Compiler choice | `-DCMAKE_C_COMPILER=clang` | gcc vs clang |
| CPU optimization | `-march=native` | Performance tuning |
| Cross-compile | `-DCMAKE_TOOLCHAIN_FILE=...` | Different target arch |

### Recipe integration (Phase 5)

```python
"inputs": [
    {"id": "build_type", "type": "select", "default": "Release",
     "options": ["Release", "Debug", "RelWithDebInfo"],
     "label": "Build type"},
    {"id": "cuda_support", "type": "select", "default": "OFF",
     "options": ["ON", "OFF"],
     "label": "Enable CUDA support",
     "condition": "has_nvidia_gpu"},
],

"install_variants": {
    "build-from-source": {
        "steps": [
            {"label": "Configure",
             "command": ["cmake", "-B", "build",
                         "-DCMAKE_BUILD_TYPE={build_type}",
                         "-DWITH_CUDA={cuda_support}"]},
            {"label": "Build",
             "command": ["cmake", "--build", "build",
                         "-j", "{nproc}"]},
            {"label": "Install",
             "command": ["cmake", "--install", "build"],
             "needs_sudo": True},
        ],
    },
},
```

---

## Build Performance

### Factors

| Factor | Impact | How to optimize |
|--------|--------|----------------|
| CPU cores | Linear scaling with `-j$(nproc)` | Always use parallel builds |
| RAM | 1-4 GB per concurrent compilation | Limit `-j` if low RAM |
| Disk I/O | Source + build artifacts | SSD preferred |
| ccache | 5-10x faster rebuilds | Install ccache |
| Build type | Debug is slower than Release | Use Release for install |

### Typical build times

| Tool | Build time (4 cores) | Build time (16 cores) | Disk usage |
|------|---------------------|----------------------|-----------|
| cargo-audit | 2-5 min | 1-2 min | ~200 MB |
| cargo-outdated | 3-8 min | 1-3 min | ~300 MB |
| OpenCV (from source) | 15-45 min | 5-15 min | ~2 GB |
| Python (from source) | 5-15 min | 2-5 min | ~500 MB |
| Linux kernel | 30-120 min | 10-30 min | ~5 GB |

### Build timeout

Phase 2: `cargo install` uses the default subprocess timeout
(currently no explicit timeout — it runs until completion).

Phase 5: Build steps need longer timeouts:
- System package install: 60s timeout
- pip/npm install: 120s timeout
- cargo install: **600s** (10 min) timeout
- Full source build: **3600s** (1 hr) timeout

---

## Cross-Compilation

### What it is

Building a binary on one architecture for a DIFFERENT architecture:
e.g., compiling arm64 binaries on an amd64 machine.

### When it matters

| Scenario | Source arch | Target arch |
|----------|-----------|-------------|
| Build for Raspberry Pi on x86 | amd64 | armv7 |
| Build for Apple Silicon on Intel | amd64 | arm64 |
| Build Docker image for multi-arch | any | amd64 + arm64 |

### Phase 2 stance

Cross-compilation is NOT supported in Phase 2. Tool installation
always targets the CURRENT architecture. Binary downloads are for
the current arch (or hardcoded to amd64).

### Phase 5+ requirements

```python
"requires": {
    "cross_compile": {
        "toolchain": "aarch64-linux-gnu-gcc",
        "sysroot": "/usr/aarch64-linux-gnu/",
        "cmake_toolchain_file": "...",
    },
}
```

Cross-compile toolchain packages:
- debian: `gcc-aarch64-linux-gnu`, `g++-aarch64-linux-gnu`
- rhel: `gcc-aarch64-linux-gnu` (from cross-toolchain repos)
- Alpine: Not well supported (musl + cross = complex)

---

## Phase Roadmap

| Phase | Build system capability |
|-------|------------------------|
| Phase 2 | `make` as installable system package. `cargo install` runs builds transparently. No direct build invocation. |
| Phase 4 | Build-from-source as a choice option (recipe `install_variants`). Build flag inputs via `inputs` field. |
| Phase 5 | Full build pipeline: configure→build→install as step type. Build tool dependency chains. Progress reporting. Timeout management. ccache integration. |
| Phase 6 | Build with GPU flags (CUDA, ROCm). Build with hardware-specific optimizations. |

---

## Traceability

| Topic | Source |
|-------|--------|
| Build from source overview | scope-expansion §2.4 |
| Build chain requirements | scope-expansion §2.4 (dependency tree) |
| Build step type | scope-expansion §2.4 (`"type": "build"`) |
| cmake recipe example | scope-expansion §2.4 (OpenCV build steps) |
| Phase 5 roadmap | scope-expansion §Phase 5 |
| make as system package | phase2.2 §Category 7 |
| install_variants (build steps) | arch-recipe-format §install_variants |
| Build flags via inputs | arch-recipe-format §inputs |
| cargo build (implicit) | domain-language-pms §cargo |
| Build-essential packages | domain-platforms (per-family meta-packages) |
