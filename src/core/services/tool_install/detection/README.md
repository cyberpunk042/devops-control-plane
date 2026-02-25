# L3 Detection — System State Readers

> Reads the real system. Subprocess calls and file reads.
> Strictly **read-only** — never mutates.
> Returns dicts that feed the resolver and dashboard.

---

## Two-Tier Detection Model

| Tier | Budget | Caller | Cached |
|------|--------|--------|--------|
| **Fast** | ~120ms | Every audit scan (`_detect_os`) | Per-scan |
| **Deep** | ~2s | On-demand (provisioning flows) | Per-session (TTL) |

Fast tier feeds the system profile for method selection.
Deep tier feeds rich hardware/network info for GPU tools, builds, etc.

---

## Files

### `tool_version.py` — Tool Version Detection

Detects installed tool versions by running `tool --version` and parsing output.

```python
from src.core.services.tool_install.detection.tool_version import get_tool_version, check_updates

version = get_tool_version("cargo-audit")   # → "0.17.6" or None
updates = check_updates("cargo-audit", "0.17.6")  # → {"available": True, "latest": "0.18.0"}
```

**Functions:**
| Function | What it does |
|----------|-------------|
| `get_tool_version(tool)` | Run version command, parse output → version string |
| `check_updates(tool, installed)` | Compare installed vs latest available |
| `_is_linux_binary(path)` | Check if path is a real binary (not a shell alias) |

### `system_deps.py` — System Package Detection

Checks whether system packages are installed via the system PM.

```python
from src.core.services.tool_install.detection.system_deps import check_system_deps

result = check_system_deps("cargo-audit", system_profile)
# → {"all_installed": False, "missing": ["libssl-dev"], "installed": ["pkg-config"]}
```

**Functions:**
| Function | What it does |
|----------|-------------|
| `check_system_deps(tool, profile)` | Check all required packages for a tool |
| `_is_pkg_installed(pkg, pm)` | Check one package (dpkg-query, rpm, etc.) |

### `hardware.py` — Hardware Detection (Deep Tier)

GPU, kernel, CPU, RAM, disk — comprehensive hardware state.

```python
from src.core.services.tool_install.detection.hardware import detect_gpu, detect_hardware

gpu = detect_gpu()
# → {"vendor": "nvidia", "model": "RTX 3080", "driver": "535.183",
#    "cuda": "12.2", "modules": ["nvidia", "nvidia_uvm"]}

hw = detect_hardware()
# → {"cpu": "AMD Ryzen 9", "ram_mb": 32768, "disk_free_mb": 120000}
```

**Functions:**
| Function | What it does |
|----------|-------------|
| `detect_gpu()` | NVIDIA/AMD/Intel GPU detection via lspci + nvidia-smi/rocminfo |
| `detect_kernel()` | Kernel version, config, secure boot state |
| `detect_hardware()` | CPU, RAM, disk |
| `detect_build_toolchain()` | GCC/Clang/Make/CMake availability + versions |
| `check_cuda_driver_compat(cuda, driver)` | CUDA/driver version compatibility check |

### `install_failure.py` — Failure Analysis

When a step fails, analyzes the output to suggest remediation.

```python
from src.core.services.tool_install.detection.install_failure import _analyse_install_failure

analysis = _analyse_install_failure("cargo-audit", stderr, exit_code)
# → {"pattern": "compiler_bug", "remediation": {...}}
```

### `network.py` — Network Connectivity

Checks if registries (pypi, npm, crates.io) are reachable.

```python
from src.core.services.tool_install.detection.network import check_all_registries

reachable = check_all_registries()
# → {"pypi.org": True, "registry.npmjs.org": True, "crates.io": False}
```

### `service_status.py` — Service Status Detection

Checks systemd/init service state.

```python
from src.core.services.tool_install.detection.service_status import get_service_status

status = get_service_status("docker")
# → {"active": True, "enabled": True, "type": "systemd"}
```

### `condition.py` — Recipe Condition Evaluator

Evaluates `when:` conditions in recipe steps.

```python
from src.core.services.tool_install.detection.condition import _evaluate_condition

result = _evaluate_condition({"os": "linux", "distro": "ubuntu"}, context)
# → True/False
```

### `environment.py` — Environment Detection

Detects NVM, sandbox environments, CPU features.

### `recipe_deps.py` — Recipe Dependency Extraction

Extracts system dependency lists from recipe declarations.
