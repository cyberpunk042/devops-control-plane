# Tool Install v2 — Phase 5: Build-from-Source Support

## Context

Phases 2-4 handle tools that install via package managers, binary
downloads, or language-specific installers. Phase 5 adds support
for building software from source — `./configure && make && make install`,
`cargo install` from git, `cmake` builds, Rust crate compilation, etc.

### Dependencies

```
Phase 2.2 (recipes)      ── provides: TOOL_RECIPES format
Phase 2.4 (execution)    ── provides: execute_plan(), _run_subprocess()
Phase 4 (choices)        ── provides: choice UI (e.g. "install from package or build?")
Phase 5 (THIS)           ── provides: build-from-source step types + toolchain detection
```

### Domains consumed

| Domain | What Phase 5 uses |
|--------|------------------|
| domain-build-systems | make, cmake, meson, ninja, autotools |
| domain-compilers | gcc, clang, rustc version requirements |
| domain-build-from-source | Full build lifecycle, configure/build/install |

---

## When Build-from-Source is Needed

| Scenario | Why not use a package? |
|----------|----------------------|
| Tool not packaged for distro | No apt/dnf package exists (e.g. new Rust tools) |
| Package too old | Distro ships ancient version |
| Need custom compile flags | GPU support, specific features |
| Platform not supported | No binary for this arch (ARM, RISC-V) |
| Air-gapped with source tarball | No network for package download |
| Cargo tool compilation | `cargo install` IS building from source |

### Already handled by Phase 2

`cargo install` is technically build-from-source but is handled
as a language PM in Phase 2. Phase 5 handles the MORE complex
cases: autotools, cmake, manual builds.

---

## Build Lifecycle

### The 7 stages

```
1. Prerequisites    — compilers, build tools, dev libraries
2. Obtain source    — git clone, tarball download, local path
3. Configure        — ./configure, cmake, meson setup
4. Build            — make, cmake --build, ninja
5. Test (optional)  — make test, ctest
6. Install          — make install, cmake --install
7. Verify           — binary --version, functional check
```

### Mapped to plan steps

```python
{
    "tool": "neovim",
    "steps": [
        {"type": "packages", "label": "Install build prerequisites",
         "packages": ["ninja-build", "gettext", "cmake", "unzip", "curl",
                      "build-essential"],
         "needs_sudo": True},
        {"type": "source", "label": "Clone neovim source",
         "source": {
             "type": "git",
             "repo": "https://github.com/neovim/neovim.git",
             "branch": "stable",
         },
         "dest": "/tmp/neovim-build"},
        {"type": "build", "label": "Build neovim",
         "command": ["make", "CMAKE_BUILD_TYPE=Release"],
         "cwd": "/tmp/neovim-build",
         "timeout": 600},
        {"type": "install", "label": "Install neovim",
         "command": ["make", "install"],
         "cwd": "/tmp/neovim-build",
         "needs_sudo": True},
        {"type": "verify", "label": "Verify neovim",
         "command": ["nvim", "--version"]},
        {"type": "cleanup", "label": "Clean build directory",
         "command": ["rm", "-rf", "/tmp/neovim-build"]},
    ],
}
```

---

## New Step Types

### type: source

```python
def _execute_source_step(step):
    """Obtain source code."""
    source = step["source"]
    dest = step["dest"]

    if source["type"] == "git":
        cmd = ["git", "clone"]
        if source.get("branch"):
            cmd += ["--branch", source["branch"]]
        if source.get("depth"):
            cmd += ["--depth", str(source["depth"])]
        cmd += [source["repo"], dest]
        return _run_subprocess(cmd, timeout=step.get("timeout", 120))

    elif source["type"] == "tarball":
        # Download + extract
        url = source["url"]
        return _download_and_extract(url, dest,
                                     extract_type=source.get("format", "tar.gz"))

    elif source["type"] == "local":
        # Source already on disk (air-gapped)
        if not Path(dest).exists():
            return {"ok": False, "error": f"Source not found: {dest}"}
        return {"ok": True, "message": "Source already present"}
```

### type: build

```python
def _execute_build_step(step, *, env_overrides=None):
    """Run a build command (make, cmake, ninja)."""
    cmd = step["command"]
    cwd = step.get("cwd")

    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)

    # Build-specific env
    if step.get("parallel"):
        # Auto-detect CPU count for parallel builds
        import multiprocessing
        jobs = step.get("jobs", multiprocessing.cpu_count())
        if cmd[0] == "make" and "-j" not in cmd:
            cmd = cmd + [f"-j{jobs}"]
        elif cmd[0] == "ninja" and "-j" not in cmd:
            cmd = cmd + [f"-j{jobs}"]

    return _run_subprocess(
        cmd,
        timeout=step.get("timeout", 600),  # builds can be slow
        env_overrides=env_overrides,
        cwd=cwd,
    )
```

### type: install

Same as command step but in a build directory with sudo.

### type: cleanup

```python
def _execute_cleanup_step(step):
    """Clean up build artifacts."""
    import shutil as sh
    target = step.get("target", step.get("command", [None])[-1])
    if target and Path(target).exists():
        sh.rmtree(target, ignore_errors=True)
    return {"ok": True, "message": "Cleaned up"}
```

---

## Toolchain Detection

### Required for build-from-source

Before attempting a build, verify the toolchain:

```python
def detect_build_toolchain() -> dict:
    """Detect available build tools."""
    tools = {
        "gcc": _tool_version("gcc", r"(\d+\.\d+\.\d+)"),
        "g++": _tool_version("g++", r"(\d+\.\d+\.\d+)"),
        "clang": _tool_version("clang", r"(\d+\.\d+\.\d+)"),
        "make": _tool_version("make", r"(\d+\.\d+)"),
        "cmake": _tool_version("cmake", r"(\d+\.\d+\.\d+)"),
        "ninja": _tool_version("ninja", r"(\d+\.\d+\.\d+)"),
        "meson": _tool_version("meson", r"(\d+\.\d+\.\d+)"),
        "autoconf": _tool_version("autoconf", r"(\d+\.\d+)"),
        "automake": _tool_version("automake", r"(\d+\.\d+)"),
        "pkg-config": _tool_version("pkg-config", r"(\d+\.\d+)"),
        "rustc": _tool_version("rustc", r"(\d+\.\d+\.\d+)"),
        "cargo": _tool_version("cargo", r"(\d+\.\d+\.\d+)"),
        "go": _tool_version("go", r"go(\d+\.\d+\.\d+)"),
    }
    return {k: v for k, v in tools.items() if v is not None}


def _tool_version(binary: str, pattern: str) -> str | None:
    if not shutil.which(binary):
        return None
    try:
        r = subprocess.run(
            [binary, "--version"],
            capture_output=True, text=True, timeout=5,
        )
        m = re.search(pattern, r.stdout + r.stderr)
        return m.group(1) if m else "unknown"
    except Exception:
        return None
```

### Toolchain requirements in recipes

```python
"neovim": {
    ...,
    "build_from_source": {
        "requires_toolchain": {
            "cmake": ">=3.16",
            "make": True,
            "gcc": True,  # or clang
        },
        "requires_packages": {
            "debian": ["ninja-build", "gettext", "cmake", "unzip",
                       "curl", "build-essential"],
            "fedora": ["ninja-build", "gettext", "cmake", "unzip",
                       "curl", "gcc-c++"],
        },
    },
}
```

---

## Build System Adapters

### Autotools (./configure && make)

```python
def _autotools_plan(recipe, profile, build_dir):
    """Generate plan steps for autotools build."""
    steps = []
    configure_args = recipe.get("configure_args", [])

    steps.append({
        "type": "build", "label": "Configure",
        "command": ["./configure"] + configure_args,
        "cwd": build_dir,
        "timeout": 120,
    })
    steps.append({
        "type": "build", "label": "Build",
        "command": ["make"],
        "cwd": build_dir,
        "parallel": True,
        "timeout": 600,
    })
    steps.append({
        "type": "install", "label": "Install",
        "command": ["make", "install"],
        "cwd": build_dir,
        "needs_sudo": True,
        "timeout": 60,
    })
    return steps
```

### CMake

```python
def _cmake_plan(recipe, profile, build_dir):
    """Generate plan steps for CMake build."""
    steps = []
    cmake_args = recipe.get("cmake_args", [])
    build_type = recipe.get("build_type", "Release")

    steps.append({
        "type": "build", "label": "CMake configure",
        "command": ["cmake", "-B", "build",
                    f"-DCMAKE_BUILD_TYPE={build_type}"] + cmake_args,
        "cwd": build_dir,
        "timeout": 60,
    })
    steps.append({
        "type": "build", "label": "CMake build",
        "command": ["cmake", "--build", "build"],
        "cwd": build_dir,
        "parallel": True,
        "timeout": 600,
    })
    steps.append({
        "type": "install", "label": "CMake install",
        "command": ["cmake", "--install", "build"],
        "cwd": build_dir,
        "needs_sudo": True,
        "timeout": 60,
    })
    return steps
```

### Cargo from git

```python
def _cargo_git_plan(recipe, profile):
    """Generate plan for cargo install from git."""
    return [{
        "type": "tool", "label": f"Build from git",
        "command": ["cargo", "install", "--git", recipe["git_repo"]],
        "timeout": 600,
        "needs_sudo": False,
    }]
```

---

## Build Timeouts

### Extended timeouts for compilation

| Operation | Default timeout | Why |
|-----------|----------------|-----|
| git clone | 120s | Large repos |
| configure | 120s | Autoconf checks |
| make (small) | 300s | Small C projects |
| make (large) | 600s | Neovim, LLVM |
| cargo install | 300s | Rust compilation |
| cmake --build | 600s | C/C++ projects |

### Timeout per estimated size

```python
BUILD_TIMEOUT_TIERS = {
    "small": 300,    # < 10k LOC
    "medium": 600,   # 10k-100k LOC
    "large": 1200,   # 100k-1M LOC
    "huge": 3600,    # 1M+ LOC (LLVM, Linux kernel)
}
```

---

## Resource Awareness

### Before starting a build

```python
def _check_build_resources(recipe) -> dict:
    """Check if system has resources for this build."""
    import shutil as sh

    disk_needed_mb = recipe.get("disk_estimate_mb", 500)
    ram_needed_mb = recipe.get("ram_estimate_mb", 512)

    # Disk check (build directory)
    build_dir = recipe.get("build_dir", "/tmp")
    disk = sh.disk_usage(build_dir)
    disk_free_mb = disk.free // (1024 * 1024)

    # RAM check
    with open("/proc/meminfo") as f:
        for line in f:
            if line.startswith("MemAvailable:"):
                ram_free_mb = int(line.split()[1]) // 1024
                break

    issues = []
    if disk_free_mb < disk_needed_mb:
        issues.append(f"Need {disk_needed_mb}MB disk, have {disk_free_mb}MB")
    if ram_free_mb < ram_needed_mb:
        issues.append(f"Need {ram_needed_mb}MB RAM, have {ram_free_mb}MB")

    return {
        "ok": len(issues) == 0,
        "issues": issues,
        "disk_free_mb": disk_free_mb,
        "ram_free_mb": ram_free_mb,
    }
```

---

## Choice Integration

### "Package or build from source?"

```python
"neovim": {
    "choices": [
        {
            "id": "install_method",
            "type": "select_one",
            "label": "Install Method",
            "options": [
                {"value": "package", "label": "System package (apt/snap)",
                 "default": True},
                {"value": "source", "label": "Build from source",
                 "description": "Latest version, requires build tools (~5 min)"},
            ],
        },
    ],
    "install": {
        "package": {"debian": ["apt-get", "install", "-y", "neovim"]},
        "source": {
            "build_system": "cmake",
            "git_repo": "https://github.com/neovim/neovim.git",
            "branch": "stable",
            ...
        },
    },
}
```

---

## Files Touched

| File | Changes |
|------|---------|
| `tool_install.py` | Add detect_build_toolchain(), _execute_source_step(), _execute_build_step(), _execute_cleanup_step(). Add build system adapters. Extended _run_subprocess() with cwd support. |
| `routes_audit.py` | Build toolchain in system profile response. |

---

## Edge Cases

| Case | Impact | Handling |
|------|--------|---------|
| No compiler installed | Can't build | Prerequisites step installs build-essential |
| Disk full during build | Build fails | Pre-check disk space, warn user |
| Build takes 30+ minutes | User thinks it hung | Progress via make output streaming |
| make -j exhausts RAM | OOM killer | Limit parallel jobs to CPU/2 |
| Source repo unreachable | Can't clone | Network check, offer tarball alternative |
| Configure fails (missing lib) | Build blocked | Parse configure output, suggest dev packages |
| Build succeeds, binary not in PATH | Tool "not found" | post_env PATH addition |
| Cleanup fails (permissions) | Stale build dir | Non-fatal, warn user |
| Cross-compilation | Wrong binary | Out of scope (Phase 5 = native only) |

---

## Traceability

| Topic | Source |
|-------|--------|
| Build system catalog | domain-build-systems |
| Compiler requirements | domain-compilers |
| Full build lifecycle | domain-build-from-source |
| Timeout tiers | domain-build-from-source §timeouts |
| Resource awareness | domain-hardware-detect §RAM, disk |
| Choice integration | Phase 4 choice UI |
| Execute plan | Phase 2.4 execution engine |
