# Domain: GPU

> This document catalogs GPU detection, driver installation, and
> compute framework support: NVIDIA (CUDA, compute capability),
> AMD (ROCm), Intel (OpenCL, oneAPI). How GPU presence influences
> recipe choices, framework installation, and build flags.
>
> SOURCE DOCS: scope-expansion §2.9 (GPU requirements),
>              scope-expansion §2.10 (PyTorch/TF variants),
>              arch-system-model §GPU hardware (Phase 6 schema),
>              scope-expansion §2.5 (VFIO/GPU passthrough)

---

## Overview

GPUs affect tool installation in three ways:

1. **Framework variant selection** — PyTorch CPU vs CUDA vs ROCm
   installs completely different packages from different pip indexes
2. **Build flags** — OpenCV compiled with `-DWITH_CUDA=ON` enables
   GPU acceleration but requires CUDA toolkit installed
3. **Driver installation** — NVIDIA/AMD drivers are system packages
   that need specific repo setup

### Phase 2 vs Phase 6

| Phase | GPU capability |
|-------|---------------|
| Phase 2 | No GPU awareness. PyTorch not in tool list. The 30 tools don't need GPU. |
| Phase 6 | Full GPU detection. CUDA/ROCm choices in recipes. Hardware constraint evaluation. Driver installation. |

---

## GPU Vendors

### NVIDIA

| Property | Value |
|----------|-------|
| **Market** | Dominant in ML/AI, HPC, gaming |
| **Compute framework** | CUDA (proprietary) |
| **Driver** | Proprietary (nvidia-driver) |
| **Detection** | lspci, nvidia-smi |
| **Version info** | Driver version, CUDA version, compute capability |

**Key NVIDIA components:**

| Component | What it is | How to detect |
|-----------|-----------|--------------|
| GPU hardware | Physical card | `lspci \| grep -i nvidia` |
| Driver | Kernel module + userspace | `nvidia-smi` (success = driver loaded) |
| CUDA version (driver) | Max CUDA the driver supports | `nvidia-smi` header output |
| CUDA toolkit | nvcc compiler + libraries | `nvcc --version` |
| Compute capability | GPU arch generation | `nvidia-smi --query-gpu=compute_cap` |
| cuDNN | Deep learning primitives library | Check file: `/usr/lib/libcudnn.so` |

### AMD

| Property | Value |
|----------|-------|
| **Market** | Growing in ML, strong in HPC and gaming |
| **Compute framework** | ROCm (open source) |
| **Driver** | Open source (amdgpu) or proprietary (amdgpu-pro) |
| **Detection** | lspci, rocm-smi |

**Key AMD components:**

| Component | What it is | How to detect |
|-----------|-----------|--------------|
| GPU hardware | Physical card | `lspci \| grep -i amd` |
| amdgpu driver | Kernel module (open source) | `lsmod \| grep amdgpu` |
| ROCm toolkit | Compute framework | `rocm-smi` or `/opt/rocm/.info/version` |
| HIP | CUDA-compatible API | `hipcc --version` |

### Intel

| Property | Value |
|----------|-------|
| **Market** | Integrated GPUs (iGPU), new discrete (Arc) |
| **Compute framework** | OpenCL, oneAPI |
| **Driver** | Open source (i915) |
| **Detection** | lspci, clinfo |

**Key Intel components:**

| Component | What it is | How to detect |
|-----------|-----------|--------------|
| GPU hardware | Integrated or discrete | `lspci \| grep -i intel.*vga` |
| i915 driver | Kernel module | `lsmod \| grep i915` |
| OpenCL runtime | Compute API | `clinfo` (shows Intel platform) |
| oneAPI toolkit | Intel compute framework | `source /opt/intel/oneapi/setvars.sh` |

---

## Detection

### System profile schema (Phase 6)

```python
"gpu": {
    "nvidia": {
        "present": bool,              # lspci shows NVIDIA device
        "model": str | None,          # "RTX 4090", "Tesla V100"
        "driver_version": str | None, # "535.129.03" from nvidia-smi
        "cuda_version": str | None,   # "12.2" from nvidia-smi
        "nvcc_version": str | None,   # "12.4" from nvcc --version (toolkit)
        "compute_capability": str | None,  # "8.9"
    },
    "amd": {
        "present": bool,              # lspci shows AMD GPU
        "model": str | None,
        "rocm_version": str | None,   # from rocm-smi or /opt/rocm/.info/version
    },
    "intel": {
        "present": bool,              # lspci shows Intel GPU
        "model": str | None,
        "opencl_available": bool,     # clinfo shows Intel platform
    },
}
```

### Detection commands

#### Step 1: Identify GPU hardware (lspci)

```bash
lspci | grep -iE "vga|3d|display"
```

**Output examples:**
```
# NVIDIA
01:00.0 VGA compatible controller: NVIDIA Corporation GA102 [GeForce RTX 3090]

# AMD
06:00.0 VGA compatible controller: Advanced Micro Devices, Inc. [AMD/ATI] Navi 21

# Intel (integrated)
00:02.0 VGA compatible controller: Intel Corporation UHD Graphics 770

# Multiple GPUs
00:02.0 VGA compatible controller: Intel Corporation UHD Graphics 770
01:00.0 VGA compatible controller: NVIDIA Corporation GA102 [GeForce RTX 3090]
```

**Parsing:** Match vendor string: "NVIDIA" → nvidia, "AMD" → amd,
"Intel" → intel. Extract model from brackets.

**lspci not available:** In containers, lspci may not be installed.
Fallback: check `/sys/bus/pci/devices/*/vendor` for vendor IDs:
- `0x10de` = NVIDIA
- `0x1002` = AMD
- `0x8086` = Intel

#### Step 2: NVIDIA details (nvidia-smi)

```bash
nvidia-smi --query-gpu=name,driver_version,compute_cap --format=csv,noheader
```

**Output:**
```
NVIDIA GeForce RTX 4090, 535.129.03, 8.9
```

**CUDA version from nvidia-smi header:**
```bash
nvidia-smi | head -3
# +-------------------------+
# | NVIDIA-SMI 535.129.03   Driver Version: 535.129.03   CUDA Version: 12.2 |
# +-------------------------+
```

**nvidia-smi not available:** Driver not installed. `present=True`
(hardware exists) but `driver_version=None`, `cuda_version=None`.

#### Step 3: CUDA toolkit version (nvcc)

```bash
nvcc --version
# nvcc: NVIDIA (R) Cuda compiler driver
# Cuda compilation tools, release 12.4, V12.4.99
```

**nvcc vs nvidia-smi CUDA:** These report DIFFERENT things:
- `nvidia-smi` → max CUDA the DRIVER supports
- `nvcc` → CUDA TOOLKIT version installed
- They can differ (driver 12.2 supports toolkit <= 12.2)

#### Step 4: AMD ROCm version

```bash
# Option A: rocm-smi
rocm-smi --showdriverversion

# Option B: version file
cat /opt/rocm/.info/version
# 5.7.1
```

#### Step 5: Intel OpenCL

```bash
clinfo | grep "Platform Name"
# Platform Name: Intel(R) OpenCL HD Graphics
```

### Detection in containers

| Environment | lspci? | nvidia-smi? | GPU access? |
|------------|--------|-------------|-------------|
| Bare metal | ✅ | ✅ (if driver installed) | ✅ |
| VM (no passthrough) | ✅ (host GPU) | ❌ | ❌ |
| VM (GPU passthrough) | ✅ (passed GPU) | ✅ | ✅ |
| Docker (no --gpus) | ❌ usually | ❌ | ❌ |
| Docker (--gpus all) | ❌ usually | ✅ | ✅ |
| Docker (--device) | ❌ usually | ✅ | ✅ |
| WSL2 | ❌ | ✅ (if driver on host) | ✅ |

**Docker + NVIDIA:** Requires `nvidia-container-toolkit`.
nvidia-smi works inside the container if configured correctly.

---

## NVIDIA Driver Installation

### Methods per platform

| Platform | Method | Package |
|----------|--------|---------|
| Ubuntu | apt repo (nvidia ppa) | `nvidia-driver-535` |
| Ubuntu | apt repo (CUDA repo) | `cuda-drivers` |
| Debian | apt (non-free) | `nvidia-driver` |
| Fedora | RPM Fusion repo | `akmod-nvidia` |
| Arch | pacman | `nvidia` |
| Alpine | ❌ Not supported | — |
| macOS | ❌ Not supported (since Mojave) | — |

### Ubuntu NVIDIA driver install

```bash
# Option A: ubuntu-drivers (recommended)
ubuntu-drivers devices  # list detected GPUs + recommended driver
sudo ubuntu-drivers autoinstall

# Option B: explicit version
sudo apt-get install -y nvidia-driver-535

# Option C: CUDA repo (installs driver + toolkit)
# Add CUDA repo first, then:
sudo apt-get install -y cuda-drivers
```

**Post-install:** REBOOT REQUIRED. The nvidia kernel module loads
on next boot.

### Recipe format (Phase 6)

```python
"nvidia-driver": {
    "label": "NVIDIA Driver",
    "install": {
        "apt": ["ubuntu-drivers", "autoinstall"],
        "dnf": ["dnf", "install", "-y", "akmod-nvidia"],
        "pacman": ["pacman", "-S", "--noconfirm", "nvidia"],
    },
    "needs_sudo": {"_default": True},
    "requires": {
        "hardware": {"gpu.nvidia.present": True},
    },
    "verify": ["nvidia-smi"],
    "restart_required": "system",
    "restart_message": "Reboot to load the NVIDIA kernel module.",
    "risk": "medium",
},
```

---

## CUDA Toolkit Installation

### Components

| Component | Purpose | Size |
|-----------|---------|------|
| nvcc | CUDA compiler | ~50 MB |
| CUDA libraries | cuBLAS, cuFFT, cuSPARSE | ~500 MB |
| cuDNN | Deep learning primitives | ~500 MB |
| CUDA samples | Example code | ~200 MB |
| Total | | ~1.5-3 GB |

### Install methods

| Method | Command | Notes |
|--------|---------|-------|
| NVIDIA repo + apt | `apt install cuda-toolkit-12-4` | Per-version package |
| NVIDIA runfile | `cuda_12.4.0_550.54.14_linux.run` | Universal but manual |
| pip (PyTorch only) | PyTorch bundles its own CUDA | No separate install needed |
| conda | `conda install cudatoolkit=12.1` | Isolated environment |

### Version compatibility matrix

| CUDA Toolkit | Min Driver | Compute Capability |
|-------------|------------|-------------------|
| 12.4 | 550.54 | 5.0+ |
| 12.1 | 530.30 | 5.0+ |
| 11.8 | 520.61 | 3.5+ |
| 11.7 | 515.43 | 3.5+ |

**Compute capability by GPU generation:**

| Generation | Compute Cap | Example GPUs |
|-----------|------------|-------------|
| Kepler | 3.5 | K40, K80 |
| Maxwell | 5.0-5.2 | GTX 750-980 |
| Pascal | 6.0-6.1 | GTX 1060-1080, Tesla P100 |
| Volta | 7.0 | Tesla V100 |
| Turing | 7.5 | RTX 2060-2080, T4 |
| Ampere | 8.0-8.6 | RTX 3060-3090, A100 |
| Ada Lovelace | 8.9 | RTX 4060-4090, L40 |
| Hopper | 9.0 | H100 |

**Why compute capability matters:** PyTorch CUDA 11.8 requires
compute capability ≥ 3.5. Modern features need higher. The
recipe's hardware constraint checks this:

```python
"requires": {
    "hardware": {
        "gpu.nvidia.present": True,
        "gpu.nvidia.compute_capability": ">=7.0",
    },
},
```

---

## ROCm Installation

### Components

| Component | Purpose |
|-----------|---------|
| ROCm runtime | Core compute runtime |
| HIP | CUDA-compatible API |
| rocBLAS | GPU BLAS library |
| MIOpen | Deep learning primitives |

### Install (Ubuntu)

```bash
# Add ROCm repo
wget -qO - https://repo.radeon.com/rocm/rocm.gpg.key | sudo apt-key add -
echo "deb [arch=amd64] https://repo.radeon.com/rocm/apt/5.7 ubuntu main" \
    | sudo tee /etc/apt/sources.list.d/rocm.list
sudo apt-get update
sudo apt-get install -y rocm-hip-sdk
```

### Supported AMD GPUs

Not all AMD GPUs support ROCm:

| Architecture | ROCm support | Example GPUs |
|-------------|-------------|-------------|
| RDNA 3 | ✅ | RX 7900 XTX |
| RDNA 2 | ✅ | RX 6800-6900 |
| CDNA 3 | ✅ | MI300X |
| CDNA 2 | ✅ | MI250X |
| Vega | ✅ | Vega 64, MI50 |
| Polaris | ❌ | RX 580 |
| Older | ❌ | — |

---

## GPU-Dependent Tool Variants

### PyTorch — the primary example

PyTorch uses DIFFERENT pip index URLs for different backends:

```python
"pytorch": {
    "choices": [
        {
            "id": "compute",
            "label": "Compute Platform",
            "options": [
                {"id": "cpu", "label": "CPU only",
                 "pip_index": "https://download.pytorch.org/whl/cpu"},
                {"id": "cuda118", "label": "CUDA 11.8",
                 "pip_index": "https://download.pytorch.org/whl/cu118",
                 "requires": {"hardware": {"gpu.nvidia.present": True}}},
                {"id": "cuda121", "label": "CUDA 12.1",
                 "pip_index": "https://download.pytorch.org/whl/cu121",
                 "requires": {"hardware": {"gpu.nvidia.present": True}}},
                {"id": "rocm57", "label": "ROCm 5.7",
                 "pip_index": "https://download.pytorch.org/whl/rocm5.7",
                 "requires": {"hardware": {"gpu.amd.present": True}}},
            ],
        },
    ],
    "install_variants": {
        "cpu":      {"command": _PIP + ["install", "torch", "torchvision",
                                         "--index-url", "{pip_index}"]},
        "cuda118":  {"command": _PIP + ["install", "torch", "torchvision",
                                         "--index-url", "{pip_index}"]},
        "cuda121":  {"command": _PIP + ["install", "torch", "torchvision",
                                         "--index-url", "{pip_index}"]},
        "rocm57":   {"command": _PIP + ["install", "torch", "torchvision",
                                         "--index-url", "{pip_index}"]},
    },
},
```

### TensorFlow

```python
# CPU
pip install tensorflow

# GPU (same package, auto-detects CUDA)
pip install tensorflow  # uses CUDA if available

# Older TF versions had separate packages:
pip install tensorflow-gpu  # deprecated since TF 2.x
```

### OpenCV build flags

```python
# cmake flags based on GPU
"-DWITH_CUDA=ON"   # NVIDIA
"-DWITH_OPENCL=ON" # Any GPU with OpenCL
```

---

## GPU in Containers and VMs

### Docker + NVIDIA

```bash
# Run with GPU access
docker run --gpus all nvidia/cuda:12.2-base nvidia-smi

# Requires: nvidia-container-toolkit installed on host
```

**Inside container:** `nvidia-smi` works, CUDA works.
**Detection:** `nvidia-smi` succeeds → GPU available.

### WSL2 + NVIDIA

Windows NVIDIA driver exposes GPU to WSL2 automatically:
- No driver install needed INSIDE WSL
- `nvidia-smi` works in WSL if Windows driver supports it
- CUDA toolkit can be installed in WSL normally

### VMs

| Hypervisor | GPU access | Method |
|-----------|-----------|--------|
| KVM/QEMU | VFIO passthrough | Pass PCI device to VM |
| VMware | vGPU | VMware vGPU profile |
| VirtualBox | ❌ | No GPU passthrough |
| Hyper-V | GPU-PV (paravirtualization) | Windows-specific |

---

## GPU Passthrough (VFIO)

For VMs that need direct GPU access:

```python
"vfio_pci": {
    "label": "VFIO-PCI (GPU Passthrough)",
    "choices": [
        {
            "id": "method",
            "options": [
                {"id": "module_load",
                 "label": "Load vfio-pci module",
                 "available": True},  # checked via /lib/modules/.../vfio-pci.ko
                {"id": "recompile",
                 "label": "Recompile kernel with CONFIG_VFIO_PCI=y",
                 "available": False},  # fallback if module not available
            ],
        },
    ],
},
```

Module loading (non-invasive):
```bash
sudo modprobe vfio-pci
echo vfio-pci >> /etc/modules-load.d/vfio.conf  # persist on boot
```

Kernel recompilation (invasive): See domain-kernel.md.

---

## Edge Cases

| Case | Impact | Detection |
|------|--------|-----------|
| No GPU | CPU-only variants selected | lspci shows no GPU |
| GPU present, no driver | Can't use GPU compute | nvidia-smi fails |
| Driver installed, no toolkit | Can't compile CUDA code | nvcc missing |
| Multiple GPUs | May need to select which | `nvidia-smi -L` lists all |
| GPU in use by display | May limit compute resources | Check X11/Wayland session |
| Container without --gpus | nvidia-smi fails despite host GPU | Container detection |
| WSL2 without GPU support | nvidia-smi fails | WSL + no /dev/dxg |
| Old GPU (low compute cap) | Modern CUDA frameworks fail | compute_capability check |
| AMD GPU without ROCm support | ROCm install fails | GPU model check |

---

## Traceability

| Topic | Source |
|-------|--------|
| GPU detection schema | arch-system-model §GPU hardware (Phase 6) |
| GPU detection commands | arch-system-model §Detection (lspci, nvidia-smi) |
| GPU requirements in recipes | scope-expansion §2.9 |
| PyTorch variant selection | scope-expansion §2.10 |
| VFIO/GPU passthrough | scope-expansion §2.5 |
| Hardware constraints in choices | scope-expansion §2.9 (compute_capability >=7.0) |
| NVIDIA driver recipe | scope-expansion §2.8 (service management) |
| Build flags (CUDA) | domain-build-systems §build flags |
| Phase 6 roadmap | scope-expansion §Phase 6 |
| Deep tier detection | arch-system-model §tiered detection |
