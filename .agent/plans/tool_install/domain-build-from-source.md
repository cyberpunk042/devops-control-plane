# Domain: Build from Source

> ⚠️ **PHASE LABELS MAY BE STALE** — As of 2026-02-25, code has evolved far beyond
> what the phase roadmaps suggest. Many features labeled "Phase 4-8 future" are
> ALREADY IMPLEMENTED. See `audit-domain-docs.md` and `audit-missing-pieces.md`
> for the verified truth. Code is the source of truth, not these phase labels.


> This document catalogs the complete build-from-source pipeline:
> obtaining source code, configuring, compiling, installing, and
> cleaning up. Covers progress reporting, timeout management,
> ccache, parallel builds, disk space, and error handling.
>
> SOURCE DOCS: scope-expansion §2.4 (build from source),
>              scope-expansion §2.5 (kernel recompilation),
>              scope-expansion §Phase 5 roadmap,
>              domain-build-systems (build tools reference),
>              domain-compilers (toolchains reference),
>              arch-system-model §resources (disk_free_gb, cpu_count)

---

## Overview

Building from source is the MOST COMPLEX installation method.
It compiles a tool from its source code instead of downloading
a pre-built binary or package.

### When build-from-source happens

| Scenario | Example | Why not a package? |
|----------|---------|-------------------|
| Tool not in repos | Niche tool, very new release | Not packaged yet |
| Custom build flags needed | GPU support, specific features | Package doesn't have them |
| Need latest version | Repos carry v3, need v5 | Distro lags upstream |
| Cross-compilation | Build arm64 binary on amd64 | Pre-built doesn't exist |
| Static linking needed | Deploy to minimal container | Package has dynamic libs |

### Phase 2 vs Phase 5

| Phase | Build-from-source capability |
|-------|------------------------------|
| Phase 2 | `cargo install` is the ONLY build-from-source. It's implicit — cargo handles everything. No direct build steps. |
| Phase 5 | Full pipeline: clone → configure → build → install. New `"type": "build"` step type. Progress reporting. |

---

## The Pipeline

Every build-from-source follows the same 6-stage pattern:

```
1. OBTAIN source code
   ├── git clone <repo>
   └── OR: curl -L <tarball> | tar xz

2. DEPENDENCIES
   ├── Build tools: cmake, make, gcc (recursive deps)
   └── Dev libraries: libssl-dev, libcurl-dev (system packages)

3. CONFIGURE
   ├── cmake -B build -DFLAGS...
   ├── ./configure --with-X --without-Y
   └── meson setup build --buildtype=release

4. COMPILE
   ├── make -j$(nproc)
   ├── cmake --build build -j $(nproc)
   └── ninja -C build

5. INSTALL
   ├── sudo make install           (→ /usr/local/)
   ├── sudo cmake --install build  (→ /usr/local/)
   └── make install prefix=$HOME/.local  (→ ~/.local/, no sudo)

6. CLEANUP (optional)
   └── rm -rf source-dir build-dir
```

---

## Stage 1: Obtaining Source Code

### git clone

```bash
git clone --depth 1 https://github.com/project/repo.git
cd repo
git checkout v1.5.0   # specific tag
```

**`--depth 1` (shallow clone):** Downloads only latest commit,
not full history. Saves bandwidth and disk. Sufficient for building.

**Requires:** `git` binary on PATH.

### Tarball download

```bash
curl -L https://github.com/project/repo/archive/v1.5.0.tar.gz | tar xz
cd repo-1.5.0
```

**Requires:** `curl` binary on PATH, `tar` (always available).

### Which to use?

| Method | Disk usage | Time | Requires | Notes |
|--------|-----------|------|----------|-------|
| git clone --depth 1 | Small | Medium | git | Has `.git/` dir for metadata |
| Tarball | Smallest | Fast | curl + tar | No git history, no submodules |
| git clone (full) | Large | Slow | git | Only if submodules needed |

**Recipe format:**
```python
"source": {
    "type": "git",  # or "tarball"
    "url": "https://github.com/project/repo.git",
    "ref": "v1.5.0",  # tag or branch
    "shallow": True,
},
```

---

## Stage 2: Dependencies

Before configuring and building, all dependencies must be satisfied:

### Build tool dependencies

| Tool needed | Detection | Install if missing |
|------------|-----------|-------------------|
| cmake | `shutil.which("cmake")` | System PM or pip |
| make | `shutil.which("make")` | System PM |
| gcc/g++ | `shutil.which("gcc")` | build-essential meta-package |
| ninja | `shutil.which("ninja")` | System PM |
| pkg-config | `shutil.which("pkg-config")` | System PM |

### Dev library dependencies

These are system packages with headers needed for compilation:

```python
"requires": {
    "packages": {
        "debian": ["libssl-dev", "libcurl4-openssl-dev", "pkg-config"],
        "rhel":   ["openssl-devel", "libcurl-devel", "pkgconf-pkg-config"],
        "alpine": ["openssl-dev", "curl-dev", "pkgconf"],
        "arch":   ["openssl", "curl", "pkgconf"],
        "suse":   ["libopenssl-devel", "libcurl-devel", "pkg-config"],
        "macos":  ["openssl@3", "curl", "pkg-config"],
    },
},
```

### Dependency resolution order

```
1. Install build tools (cmake, make, gcc) via system PM
2. Install dev libraries (libssl-dev, etc.) via system PM
3. Both are system packages → can be batched in one apt-get call
4. Then proceed to configure step
```

---

## Stage 3: Configure

Configuration tells the build system WHAT to build and WHERE.

### cmake

```bash
cmake -B build \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX=/usr/local \
    -DWITH_CUDA=ON \
    -DBUILD_SHARED_LIBS=ON
```

**Output:** Generates Makefile or ninja.build in `build/`.
**Success indicator:** Exit code 0, last line shows "Build files written".
**Failure modes:**
- Missing dependency → "Could not find package X"
- Wrong cmake version → "CMake 3.20 or higher is required"

### autotools (./configure)

```bash
./configure \
    --prefix=/usr/local \
    --with-ssl \
    --without-gui \
    --enable-shared
```

**Output:** Generates `Makefile`.
**Success indicator:** Exit code 0, "configure: creating Makefile".
**Failure modes:**
- Missing lib → "checking for libssl... no"
- Missing tool → "configure: error: cannot find install-sh"

### meson

```bash
meson setup build \
    --buildtype=release \
    --prefix=/usr/local \
    -Dcuda=enabled
```

**Output:** Generates `build/build.ninja`.
**Success indicator:** Exit code 0.

### Recipe format for configure step

```python
{
    "label": "Configure build",
    "command": ["cmake", "-B", "build",
                "-DCMAKE_BUILD_TYPE=Release",
                "-DWITH_CUDA={cuda_flag}"],
    "needs_sudo": False,
    "timeout": 120,   # 2 minutes is generous for configure
    "expected_exit": 0,
},
```

---

## Stage 4: Compile

Compilation is the LONGEST stage. It transforms source code into
object files and links them into executables.

### Commands

| Build system | Compile command | Parallel flag |
|-------------|----------------|---------------|
| make | `make -j$(nproc)` | `-j N` |
| cmake+make | `cmake --build build -j $(nproc)` | `-j N` |
| cmake+ninja | `cmake --build build` | Auto-parallel |
| ninja | `ninja -C build` | Auto-parallel |
| meson+ninja | `ninja -C build` | Auto-parallel |
| cargo | `cargo build --release` | Auto-parallel |

### Parallel compilation

`-j$(nproc)` uses ALL available CPU cores:

```python
import os
nproc = os.cpu_count() or 1
# Template substitution in recipe:
# ["make", "-j{nproc}"] → ["make", "-j8"]
```

**Limiting parallelism for low-RAM systems:**

| RAM available | Recommended `-j` | Reason |
|---------------|------------------|--------|
| 1 GB | `-j1` | Each gcc process uses ~200-400 MB |
| 2 GB | `-j2` | Prevent OOM |
| 4 GB | `-j4` | Comfortable |
| 8+ GB | `-j$(nproc)` | Full speed |

**Detection:**
```python
import psutil  # or os.sysconf
available_ram_gb = psutil.virtual_memory().available / (1024**3)
safe_j = min(os.cpu_count(), max(1, int(available_ram_gb / 0.5)))
```

### Compile output and progress

Make and ninja output progress differently:

```
# make output (verbose, per-file)
[  4%] Building CXX object src/CMakeFiles/foo.dir/main.cpp.o
[ 12%] Building CXX object src/CMakeFiles/foo.dir/util.cpp.o
[ 20%] Linking CXX executable foo
[100%] Built target foo

# ninja output (compact, single line overwrite)
[42/100] Building CXX object src/main.cpp.o
```

**Parsing progress:** cmake provides percentage in `[XX%]` markers.
ninja provides `[N/total]` markers.

### Recipe format for compile step

```python
{
    "label": "Compile ({nproc} cores)",
    "command": ["make", "-j{nproc}", "-C", "build"],
    "needs_sudo": False,
    "timeout": 3600,  # 1 hour max
    "progress_regex": r"\[\s*(\d+)%\]",  # parse cmake/make percentage
},
```

---

## Stage 5: Install

Copying built binaries to the final location.

### System-wide install (needs sudo)

```bash
sudo make install
# OR:
sudo cmake --install build
# OR:
sudo ninja -C build install
```

Default prefix: `/usr/local/` (binaries → `/usr/local/bin/`,
libraries → `/usr/local/lib/`, headers → `/usr/local/include/`).

### User-space install (no sudo)

```bash
make install prefix=$HOME/.local
# OR:
cmake --install build --prefix $HOME/.local
```

Binaries go to `~/.local/bin/`. Requires PATH update (post_env
or shell_config).

### Install prefix decision

| Factor | Use /usr/local/ | Use ~/.local/ |
|--------|----------------|--------------|
| Sudo available | ✅ Standard | Not needed |
| Multi-user system | ✅ All users see it | ❌ Current user only |
| Container (root) | ✅ Owns /usr/local/ | Not needed |
| Container (non-root) | ❌ Can't write | ✅ Only option |
| Development use | Either | ✅ Won't pollute system |

---

## Stage 6: Cleanup

After installation, source and build directories can be removed:

```bash
rm -rf source-dir/
```

### Disk space reclaimed

| Project | Source dir | Build dir | Install size | Reclaimable |
|---------|-----------|-----------|-------------|-------------|
| cargo-audit | ~5 MB | ~200 MB | ~5 MB | ~200 MB |
| OpenCV | ~100 MB | ~2 GB | ~50 MB | ~2 GB |
| Python | ~80 MB | ~500 MB | ~100 MB | ~500 MB |
| Linux kernel | ~1 GB | ~5 GB | ~200 MB | ~5 GB |

**Phase 5 recipe:** Optional cleanup step:
```python
{
    "label": "Clean up build files",
    "command": ["rm", "-rf", "{source_dir}"],
    "needs_sudo": False,
    "optional": True,  # user can skip if they want to rebuild later
},
```

---

## Disk Space Requirements

### Pre-build check

Before starting a build, verify sufficient disk space:

```python
import shutil
usage = shutil.disk_usage("/")
free_gb = usage.free / (1024**3)
```

**In system profile:**
```python
"resources": {
    "disk_free_gb": 42.5,   # shutil.disk_usage("/").free / 1e9
    "cpu_count": 8,         # os.cpu_count()
    "ram_total_gb": 16.0,
    "ram_available_gb": 12.3,
}
```

### Space requirements by build type

| Build type | Minimum free space | Recommended |
|-----------|-------------------|-------------|
| cargo install (single crate) | 500 MB | 1 GB |
| Small C project | 200 MB | 500 MB |
| Medium project (OpenCV) | 3 GB | 5 GB |
| Large project (LLVM, kernel) | 10 GB | 20 GB |
| pip wheel build (native ext) | 500 MB | 1 GB |

### Recipe format

```python
"disk_requirement_gb": 2.0,  # minimum free space needed
```

The resolver checks `system_profile.resources.disk_free_gb`
against `recipe.disk_requirement_gb` before starting the build.

---

## Timeout Management

### The problem

Builds can take anywhere from 30 seconds to 2+ hours. The timeout
must be generous enough to not kill legitimate builds but short
enough to catch stuck processes.

### Timeout values per step type

| Step type | Current (Phase 2) | Proposed (Phase 5) |
|-----------|-------------------|-------------------|
| System package install | 60s | 120s |
| pip install | No timeout | 120s |
| npm install -g | No timeout | 60s |
| cargo install | No timeout | 600s (10 min) |
| Configure step | — | 120s |
| Compile step | — | 3600s (1 hr) |
| Install step | — | 60s |
| Cleanup step | — | 30s |

### Phase 2 timeout reality

Currently, `cargo install` has NO explicit timeout in tool_install.py.
It runs until completion or failure. This is acceptable because:
1. cargo-audit and cargo-outdated take 2-8 minutes max
2. The user watches progress via the frontend
3. The user can cancel manually

### Phase 5 timeout design

```python
{
    "label": "Compile",
    "command": ["make", "-j{nproc}"],
    "timeout": 3600,
    "timeout_action": "kill",     # or "warn" for interactive
    "timeout_message": "Build exceeded 1 hour time limit",
},
```

---

## Progress Reporting

### The problem

Builds are LONG. The user needs to know it's still working.

### Phase 2 (current)

`cargo install` outputs compilation progress to stderr:
```
   Compiling openssl-sys v0.9.102
   Compiling cargo-audit v0.20.0
```

This output is captured and streamed to the frontend via the
step execution API.

### Phase 5 (future)

Structured progress from build commands:

```python
# Parse make/cmake percentage output
progress_regex = r"\[\s*(\d+)%\]"
match = re.search(progress_regex, line)
if match:
    percent = int(match.group(1))
    emit_progress(step_id, percent)
```

**Frontend display:**
```
Compiling cargo-audit...  [████████░░░░░░░░] 48%
```

### Progress sources

| Build tool | Progress format | Parseable? |
|-----------|-----------------|-----------|
| cmake+make | `[XX%] Building ...` | ✅ Regex: `\[\s*(\d+)%\]` |
| ninja | `[N/total] Building ...` | ✅ Parse N/total |
| cargo | `Compiling crate (N of M)` | ⚠️ Semi-structured |
| make (raw) | File-by-file output | ❌ No percentage |
| autotools | Verbose line-by-line | ❌ No percentage |

---

## ccache (Compiler Cache)

### What it is

ccache caches compilation results. If the same source file is
compiled again with the same flags, ccache returns the cached
object file instantly.

### Impact

| Scenario | Without ccache | With ccache |
|----------|---------------|-------------|
| First build | 10 min | 10 min (no cache yet) |
| Rebuild (no changes) | 10 min | ~10 sec |
| Rebuild (minor changes) | 10 min | ~2 min (cache partial hits) |

### Installation

```python
"ccache": {
    "install": {"_default": ["apt-get", "install", "-y", "ccache"]},
    # Same name on all distros
}
```

### How it integrates

```bash
# Option 1: Set CC/CXX environment variables
export CC="ccache gcc"
export CXX="ccache g++"
cmake -B build ...

# Option 2: cmake flag
cmake -B build -DCMAKE_C_COMPILER_LAUNCHER=ccache \
               -DCMAKE_CXX_COMPILER_LAUNCHER=ccache

# Option 3: symlink (ccache creates these)
# /usr/lib/ccache/gcc → ccache
export PATH="/usr/lib/ccache:$PATH"
```

### Phase 5 recipe support

```python
"build_options": {
    "ccache": {
        "enabled": True,  # use if available
        "required": False,  # don't fail if not installed
    },
},
```

---

## Error Handling

### Common build failures

| Error | Cause | Detection | Recovery |
|-------|-------|-----------|---------|
| `No such file or directory: gcc` | Compiler not installed | Exit code + stderr | Install build-essential |
| `fatal error: openssl/ssl.h` | Missing dev headers | Stderr pattern | Install libssl-dev |
| `Could not find package X` | cmake can't find lib | cmake output | Install dev package |
| `make: *** No rule to make target` | Wrong directory | Exit code | cd to source dir |
| `Permission denied` | Can't write to install dir | Exit code | Use sudo or --prefix |
| `No space left on device` | Disk full during build | Exit code + errno | Free space, clean |
| Killed (signal 9) | OOM killer | Exit code 137 | Reduce `-j`, add RAM |
| Timeout | Build too slow | Timeout handler | Increase timeout |

### Error analysis for builds (Phase 5)

```python
def _analyse_build_failure(stderr: str, step_type: str) -> dict:
    """Analyse why a build step failed."""
    
    if "fatal error:" in stderr and ".h:" in stderr:
        # Missing header file
        header = extract_header_name(stderr)
        return {
            "cause": "missing_header",
            "header": header,
            "suggestion": f"Install dev package for {header}",
        }
    
    if "No space left on device" in stderr:
        return {
            "cause": "disk_full",
            "suggestion": "Free disk space and retry",
        }
    
    if exit_code == 137:
        return {
            "cause": "oom_killed",
            "suggestion": "Reduce parallel jobs (-j) or add RAM",
        }
```

---

## cargo install: Phase 2's Build-from-Source

In Phase 2, the ONLY build-from-source happens via `cargo install`:

```python
["cargo", "install", "cargo-audit"]
```

This single command performs the ENTIRE build pipeline:

| Pipeline stage | What `cargo install` does |
|---------------|--------------------------|
| 1. Obtain source | Downloads from crates.io registry |
| 2. Dependencies | Resolves Rust crate dependencies (Cargo.lock) |
| 3. Configure | Reads Cargo.toml, resolves features |
| 4. Compile | Invokes rustc for each crate, parallel by default |
| 5. Install | Copies binary to `~/.cargo/bin/` |
| 6. Cleanup | Crate source cached in `~/.cargo/registry/` |

**What cargo DOESN'T handle:** System C libraries. The recipe's
`requires.packages` must install `libssl-dev` etc. BEFORE
`cargo install` runs, otherwise the linker fails.

**Build output:**
```
  Downloading crates ...
  Downloaded cargo-audit v0.20.0
   Compiling libc v0.2.152
   Compiling openssl-sys v0.9.102
   Compiling cargo-audit v0.20.0
    Finished release [optimized] target(s) in 3m 47s
   Installing ~/.cargo/bin/cargo-audit
    Installed package `cargo-audit v0.20.0`
```

---

## Full Example: OpenCV Build Recipe (Phase 5)

```python
"opencv": {
    "label": "OpenCV",
    "install_variants": {
        "package": {
            "install": {
                "apt": ["apt-get", "install", "-y", "libopencv-dev"],
                "brew": ["brew", "install", "opencv"],
            },
        },
        "build-from-source": {
            "label": "Build from source",
            "source": {
                "type": "git",
                "url": "https://github.com/opencv/opencv.git",
                "ref": "4.9.0",
                "shallow": True,
            },
            "requires": {
                "binaries": ["cmake", "make", "gcc"],
                "packages": {
                    "debian": ["libgtk-3-dev", "libavcodec-dev",
                               "libavformat-dev", "libswscale-dev",
                               "python3-dev", "python3-numpy"],
                },
            },
            "disk_requirement_gb": 5.0,
            "steps": [
                {"label": "Configure build",
                 "command": ["cmake", "-B", "build",
                             "-DCMAKE_BUILD_TYPE=Release",
                             "-DWITH_CUDA={cuda_flag}",
                             "-DCMAKE_INSTALL_PREFIX=/usr/local"],
                 "needs_sudo": False,
                 "timeout": 120},
                {"label": "Compile ({nproc} cores)",
                 "command": ["make", "-j{nproc}", "-C", "build"],
                 "needs_sudo": False,
                 "timeout": 3600,
                 "progress_regex": r"\[\s*(\d+)%\]"},
                {"label": "Install",
                 "command": ["make", "-C", "build", "install"],
                 "needs_sudo": True,
                 "timeout": 60},
            ],
            "cleanup": {
                "command": ["rm", "-rf", "opencv/", "build/"],
                "optional": True,
            },
        },
    },
    "inputs": [
        {"id": "cuda_flag", "type": "select",
         "options": ["ON", "OFF"], "default": "OFF",
         "label": "CUDA support",
         "condition": "has_nvidia_gpu"},
    ],
    "verify": ["python3", "-c", "import cv2; print(cv2.__version__)"],
},
```

---

## Phase Roadmap

| Phase | Build-from-source capability |
|-------|------------------------------|
| Phase 2 | `cargo install` only (implicit build). No direct configure/make. |
| Phase 4 | Build-from-source as a `choice` option in `install_variants`. |
| Phase 5 | `"type": "build"` step with sub-steps. Progress parsing. Timeout. Disk check. ccache. Cleanup. Error analysis. |
| Phase 6 | GPU build flags (CUDA/ROCm). Hardware-dependent build configuration. |
| Phase 8 | Parallel step execution for independent builds. |

---

## Traceability

| Topic | Source |
|-------|--------|
| Build chain requirements | scope-expansion §2.4 (full tree) |
| Build step type | scope-expansion §2.4 (`"type": "build"`) |
| Kernel build example | scope-expansion §2.5 (recompile steps) |
| Progress reporting roadmap | scope-expansion §Phase 5 |
| Parallel execution roadmap | scope-expansion §2.17, §Phase 8 |
| Build flag management | scope-expansion §Phase 5 |
| Build tools reference | domain-build-systems (cmake, make, ninja) |
| Compiler reference | domain-compilers (gcc, clang, rustc) |
| disk_free_gb in system model | arch-system-model §resources |
| cpu_count in system model | arch-system-model §resources |
| cargo install pipeline | domain-language-pms §cargo |
| Dev library naming | domain-platforms (per-family tables) |
