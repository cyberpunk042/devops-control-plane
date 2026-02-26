# Phase 2 — Scope Expansion Analysis: Decision Trees, Choices & Constraints

## What the User is Pointing At

The current design assumes: one tool → one recipe → one path per platform.
Reality is: one tool → MANY possible paths → user chooses (or system forces).

This document analyses every dimension the user raised and how it
changes the architecture.

---

## 1. The Fundamental Shift: From Flat Recipes to Decision Trees

### Current model (flat)

```
tool → method → command → done
```

### Real model (tree)

```
tool
├── choice: version? → [4.9, 4.10, 5.0]
├── choice: backend? → [cpu, cuda, rocm, opencl]
│   ├── cuda → requires: nvidia-gpu, cuda-toolkit
│   │   ├── choice: cuda version? → [11.8, 12.1, 12.4]
│   │   │   └── each leads to different packages
│   │   └── constraint: GPU compute capability ≥ X
│   ├── rocm → requires: amd-gpu, rocm-toolkit
│   └── cpu → no GPU requirement
├── choice: install method? → [package, pip, build-from-source]
│   ├── build-from-source → requires: cmake, gcc/clang, make
│   │   ├── cmake not installed → ANOTHER decision tree
│   │   └── choice: compiler? → [gcc, clang]
│   └── package → requires: repo setup
└── post-install: configure, download data, restart?
```

Every layer has choices. Choices lead to branches. Branches lead to
different solution leaves. The USER decides unless the system FORCES
a specific branch due to constraints.

### The key principle

**Always present, sometimes disabled.**

Every option at every choice point is ALWAYS returned to the frontend.
Unavailable options are marked `disabled: true` with a `reason`.
The assistant panel uses this to explain WHY something isn't available
and WHAT would need to change to enable it.

```python
{
    "id": "cuda",
    "label": "NVIDIA CUDA",
    "available": False,
    "disabled_reason": "No NVIDIA GPU detected",
    "enable_hint": "Install an NVIDIA GPU and CUDA drivers to enable this option",
}
```

---

## 2. Every Dimension Analyzed

### 2.1 Complex Software (OpenCV, FFMPEG with codecs, etc.)

**What makes it complex:**
- Multiple build backends (cmake, meson, autotools)
- Optional features toggled by build flags (-DWITH_CUDA=ON)
- System library dependencies vary by feature set
- Build from source can take 30+ minutes
- Pre-built packages exist but may lack features
- Version matters (4.x vs 5.x have different APIs)

**What the recipe needs:**
```python
"opencv": {
    "label": "OpenCV",
    "choices": [
        {
            "id": "install_method",
            "label": "Installation Method",
            "type": "single",  # single choice
            "options": [
                {
                    "id": "pip",
                    "label": "pip (pre-built, CPU only)",
                    "description": "Fast install, limited features",
                },
                {
                    "id": "pip-headless",
                    "label": "pip headless (no GUI, smaller)",
                    "description": "For servers without display",
                },
                {
                    "id": "system",
                    "label": "System package",
                    "description": "Distribution version, may be outdated",
                },
                {
                    "id": "source",
                    "label": "Build from source",
                    "description": "Full control, all features, slow",
                    "requires": {"binaries": ["cmake", "make", "gcc"]},
                },
            ],
        },
        {
            "id": "gpu_backend",
            "label": "GPU Backend",
            "type": "single",
            "depends_on": {"install_method": "source"},  # only for source builds
            "options": [
                {"id": "none", "label": "CPU only"},
                {
                    "id": "cuda",
                    "label": "NVIDIA CUDA",
                    "requires": {"hardware": ["nvidia-gpu"]},
                    "requires_packages": {...},
                },
                {
                    "id": "rocm",
                    "label": "AMD ROCm",
                    "requires": {"hardware": ["amd-gpu"]},
                },
                {
                    "id": "opencl",
                    "label": "OpenCL (generic)",
                    "requires_packages": {...},
                },
            ],
        },
        {
            "id": "version",
            "label": "Version",
            "type": "single",
            "options": [
                {"id": "4.9.0", "label": "4.9.0 (LTS)"},
                {"id": "4.10.0", "label": "4.10.0 (Latest stable)"},
            ],
        },
    ],
    # The install commands are resolved AFTER choices are made.
    # Each combination of choices produces a different plan.
    "install_variants": {
        "pip": {
            "command": _PIP + ["install", "opencv-python=={version}"],
            "needs_sudo": False,
        },
        "pip-headless": {
            "command": _PIP + ["install", "opencv-python-headless=={version}"],
            "needs_sudo": False,
        },
        "source": {
            # This is a MULTI-STEP build process
            "steps": [
                {"label": "Clone OpenCV source",
                 "command": ["git", "clone", "--branch", "{version}",
                             "https://github.com/opencv/opencv.git"]},
                {"label": "Configure build",
                 "command": ["cmake", "-B", "build",
                             "-DCMAKE_BUILD_TYPE=Release",
                             "{gpu_flags}"]},
                {"label": "Build",
                 "command": ["make", "-j{nproc}", "-C", "build"]},
                {"label": "Install",
                 "command": ["make", "-C", "build", "install"],
                 "needs_sudo": True},
            ],
        },
    },
}
```

**Impact on architecture:**
- Recipes need a `choices` field — list of choice points
- Choices can depend on other choices (`depends_on`)
- Install commands use template variables from choices
- The resolver becomes a TWO-PHASE process:
  1. Return choices to frontend (with availability/constraints)
  2. Receive selected choices, THEN resolve the plan

### 2.2 Configuration Inputs

**What this means:**
- Some tools need user-provided values during install
- Docker: which storage driver? (overlay2, btrfs, devicemapper)
- Kubernetes: which CRI? (containerd, CRI-O)
- Database: admin password, port, data directory
- Web server: document root, listen port

**What the recipe needs:**
```python
"inputs": [
    {
        "id": "docker_storage_driver",
        "label": "Storage Driver",
        "type": "select",
        "options": ["overlay2", "btrfs", "devicemapper"],
        "default": "overlay2",
        "description": "overlay2 is recommended for most systems",
        "condition": "has_systemd",  # only relevant on systemd systems
    },
    {
        "id": "port",
        "label": "Listen Port",
        "type": "number",
        "default": 8080,
        "validation": {"min": 1, "max": 65535},
    },
    {
        "id": "data_dir",
        "label": "Data Directory",
        "type": "path",
        "default": "/var/lib/myapp",
    },
]
```

These inputs are used in post_install configuration steps:
```python
"post_install": [
    {
        "label": "Configure Docker daemon",
        "command": ["bash", "-c",
                    'echo \'{"storage-driver": "{docker_storage_driver}"}\' '
                    '> /etc/docker/daemon.json'],
        "needs_sudo": True,
    },
]
```

**Impact on architecture:**
- Recipe format gets an `inputs` field
- Frontend renders input fields before execution
- Input values are substituted into commands via template variables
- Validation runs client-side AND server-side

### 2.3 Repository Types

**Not just apt repos.** The system needs to handle:

| Repo type | Example | Setup steps |
|-----------|---------|------------|
| apt (deb) | Docker CE, GitHub CLI, HashiCorp | GPG key + sources.list entry + apt-get update |
| dnf/yum (rpm) | Docker CE, EPEL, RPMFusion | rpm --import key + .repo file + dnf makecache |
| PPA (Ubuntu) | deadsnakes (Python versions) | add-apt-repository ppa:X |
| COPR (Fedora) | community packages | dnf copr enable X |
| AUR (Arch) | community packages | yay/paru install X |
| Flatpak | GUI apps | flatpak remote-add + flatpak install |
| pip index | private PyPI mirrors | pip config set index-url |
| npm registry | private npm mirrors | npm config set registry |
| Docker registry | private container images | docker login |
| Cargo registry | alternative crate sources | .cargo/config.toml |
| Snap store | Canonical snap store | default, but can add custom stores |
| Homebrew tap | third-party formulas | brew tap X |

**What the recipe needs:**
```python
"repo_setup": {
    "apt": {
        "type": "gpg_key_and_source",
        "steps": [...],
    },
    "dnf": {
        "type": "repo_file",
        "steps": [...],
    },
    "ppa": {
        "type": "ppa",
        "name": "ppa:deadsnakes/ppa",
    },
    "brew_tap": {
        "type": "tap",
        "name": "hashicorp/tap",
    },
}
```

### 2.4 Build from Source

**When this happens:**
- Package not in repos (too new, too niche)
- Need custom compile flags (GPU support, specific features)
- Need latest version (repos have old version)
- Cross-compiling

**The chain of requirements:**
```
Build from source
├── Requires build tools
│   ├── cmake (might not be installed)
│   │   └── cmake requires: apt install cmake OR pip install cmake OR build cmake from source
│   ├── gcc/g++ (might not be installed)
│   │   └── apt install build-essential / dnf groupinstall "Development Tools"
│   ├── make (might not be installed)
│   └── ninja (optional, faster)
├── Requires source code
│   ├── git clone (requires git)
│   └── OR wget/curl tarball download
├── Requires dev libraries
│   ├── libssl-dev, libcurl-dev, etc.
│   └── These have different names per distro (already handled)
├── Configure step
│   ├── ./configure --with-X --without-Y
│   ├── cmake -DFLAG=VALUE
│   └── meson setup build
├── Build step
│   ├── make -j$(nproc)
│   ├── cmake --build build
│   └── ninja -C build
├── Install step
│   ├── make install (needs sudo for /usr/local)
│   ├── cmake --install build
│   └── Or install to user directory (no sudo)
└── Post-build cleanup (optional)
    └── Remove source dir to save space
```

**Impact on architecture:**
- A new step type: `"type": "build"` with sub-steps (configure, make, install)
- Build tools become recursive dependencies
- The resolver needs to detect build tool availability
- Build timeout needs to be much longer (30+ minutes for large projects)
- Progress reporting becomes important (make outputs progress)

### 2.5 Kernel Recompilation / Module Management

**When this happens:**
- Enable kernel modules (vfio for GPU passthrough, wireguard, etc.)
- Enable cgroups v2 (required for modern container runtimes)
- Enable specific filesystems (btrfs, zfs)
- Enable hardware support (specific network drivers)

**This IS automatable.** The steps are well-defined:

```
Kernel module workflow:
├── Detect current kernel config: /boot/config-$(uname -r)
├── Detect loaded modules: lsmod
├── CHOICE: module loading vs kernel recompilation
│   ├── Module loading (non-invasive, immediate)
│   │   ├── modprobe MODULE_NAME
│   │   ├── Persist: echo MODULE_NAME >> /etc/modules-load.d/X.conf
│   │   └── Verify: lsmod | grep MODULE_NAME
│   └── Kernel recompilation (invasive, requires reboot)
│       ├── Install kernel source/headers
│       ├── Copy current config: cp /boot/config-$(uname -r) .config
│       ├── Set config option: scripts/config --enable CONFIG_X
│       ├── Build: make -j$(nproc)
│       ├── Install: make modules_install && make install
│       ├── Update bootloader: update-grub / grub2-mkconfig
│       ├── RESTART REQUIRED: reboot
│       └── Verify: grep CONFIG_X /boot/config-$(uname -r)
```

**WSL interop angle:**
On WSL2, the kernel is a Microsoft-provided kernel. To customize it:
- Build a custom WSL kernel from source (github.com/microsoft/WSL2-Linux-Kernel)
- Place it at `C:\Users\USER\.wslconfig` pointing to the custom vmlinux
- `wsl --shutdown` and restart
- WSL interop allows running Windows commands from Linux:
  `wsl.exe --shutdown` from within WSL itself

This is MORE steps but still automatable. The recipe needs:
- Detection: `uname -r` contains "microsoft" → WSL kernel
- Different workflow for WSL vs native Linux
- Cross-OS commands (powershell.exe from Linux for .wslconfig)

**Safeguards the recipe system MUST enforce:**
1. **Confirmation gate:** Kernel operations are NEVER auto-executed.
   The plan shows every step and requires explicit user confirmation.
2. **Backup:** Save current kernel config before modification.
3. **Rollback instructions:** Include "how to boot old kernel" in plan output.
4. **Restart awareness:** Mark steps with `restart_required: "system"`.
   Plan pauses and persists state. Resumes after reboot.
5. **Risk level:** Steps tagged with `risk: "high"` get extra UI treatment
   (warning colors, expanded explanation, double-confirm).

**Recipe format for kernel operations:**
```python
"vfio_pci": {
    "label": "VFIO-PCI (GPU Passthrough)",
    "choices": [
        {
            "id": "method",
            "label": "How to enable",
            "options": [
                {
                    "id": "modprobe",
                    "label": "Load module (if compiled)",
                    "available": True,  # checked via /lib/modules/.../vfio-pci.ko
                    "risk": "low",
                },
                {
                    "id": "recompile",
                    "label": "Recompile kernel with CONFIG_VFIO_PCI=y",
                    "available": True,
                    "risk": "high",
                    "warning": "Requires kernel rebuild and system reboot",
                    "estimated_time": "20-60 minutes",
                },
            ],
        },
    ],
    "install_variants": {
        "modprobe": {
            "steps": [
                {"label": "Load vfio-pci module",
                 "command": ["modprobe", "vfio-pci"],
                 "needs_sudo": True, "risk": "low"},
                {"label": "Persist module on boot",
                 "command": ["bash", "-c",
                             "echo vfio-pci >> /etc/modules-load.d/vfio.conf"],
                 "needs_sudo": True},
            ],
        },
        "recompile": {
            "steps": [
                {"label": "Install kernel build deps",
                 "command": ["apt-get", "install", "-y",
                             "build-essential", "libncurses-dev", "flex",
                             "bison", "libssl-dev", "libelf-dev"],
                 "needs_sudo": True},
                {"label": "Download kernel source",
                 "command": [...], "needs_sudo": True},
                {"label": "Backup current config",
                 "command": ["cp", "/boot/config-$(uname -r)", "/boot/config.backup"],
                 "needs_sudo": True, "risk": "medium"},
                {"label": "Enable CONFIG_VFIO_PCI",
                 "command": ["scripts/config", "--enable", "CONFIG_VFIO_PCI"],
                 "risk": "high"},
                {"label": "Build kernel",
                 "command": ["make", "-j$(nproc)"],
                 "estimated_time": "20-60 min"},
                {"label": "Install modules",
                 "command": ["make", "modules_install"],
                 "needs_sudo": True, "risk": "high"},
                {"label": "Install kernel",
                 "command": ["make", "install"],
                 "needs_sudo": True, "risk": "high"},
                {"label": "Update bootloader",
                 "command": ["update-grub"],
                 "needs_sudo": True},
                {"label": "Reboot required",
                 "restart_required": "system",
                 "restart_message": "Reboot to load the new kernel. "
                                    "If boot fails, select the old kernel in GRUB."},
            ],
            "rollback": {
                "description": "If boot fails: select old kernel in GRUB menu, "
                               "or boot from recovery, then restore /boot/config.backup",
            },
        },
    },
}
```

### 2.6 Broken Shell Profile

**What can go wrong:**
- PATH is corrupted in .bashrc/.profile
- Syntax error in .bashrc prevents shell from loading
- Environment variables point to wrong locations
- Multiple conflicting profile files (.bash_profile vs .bashrc vs .profile)

**What the resolver can do:**
- Detect: `subprocess.run(["bash", "-l", "-c", "echo $PATH"])` and compare
  to `subprocess.run(["bash", "-c", "echo $PATH"])` (login vs non-login)
- If a tool is installed but not on PATH → profile issue
- Report: "cargo is installed at ~/.cargo/bin/cargo but not on PATH"
- Suggest: "Add to ~/.bashrc: export PATH=$HOME/.cargo/bin:$PATH"

**Impact on architecture:**
- New step type: `"type": "shell_config"` — add lines to profile
- Verify step should check both `shutil.which()` AND direct path
- The resolver can offer a "Fix PATH" remediation option
- Shell type detection: bash vs zsh vs fish (different profile files)

```python
"shell_config": {
    "bash": {"file": "~/.bashrc", "line": 'export PATH="$HOME/.cargo/bin:$PATH"'},
    "zsh":  {"file": "~/.zshrc",  "line": 'export PATH="$HOME/.cargo/bin:$PATH"'},
    "fish": {"file": "~/.config/fish/config.fish",
             "line": 'set -gx PATH $HOME/.cargo/bin $PATH'},
}
```

### 2.7 Sandboxed/Restricted Shells

**Scenarios:**
- chroot environment (limited filesystem)
- snap confinement (can't access /usr/local)
- Docker container (no systemd, possibly read-only layers)
- restricted shell (rbash — can't change PATH, can't use /)
- Flatpak sandbox
- SELinux/AppArmor restrictions

**What the resolver can do:**
- Phase 1 detects container/chroot/snap
- Constraints disable options that can't work:
  ```python
  {"id": "install_to_usr_local",
   "available": False,
   "disabled_reason": "Read-only filesystem at /usr/local (snap confinement)"}
  ```
- Alternative paths offered: install to user directory instead

### 2.8 System Restart Requirements

**When a restart is needed:**
- Kernel module loaded (GPU drivers)
- Group membership change (docker group → needs logout/login)
- Kernel update
- systemd unit file changes (daemon-reload + restart)
- Profile changes (need new login shell)

**What the recipe needs:**
```python
"post_install": [
    {
        "label": "Add user to docker group",
        "command": [...],
        "needs_sudo": True,
        "restart_required": "session",  # "session" | "service" | "system"
        "restart_message": "Log out and back in for group changes to take effect",
    },
    {
        "label": "Install NVIDIA driver",
        "command": [...],
        "restart_required": "system",
        "restart_message": "Reboot required to load the new kernel module",
    },
]
```

**Impact on architecture:**
- Steps can declare `restart_required` level
- The plan execution can PAUSE: "Restart needed before continuing"
- The plan needs to be RESUMABLE after restart
- Plan state needs to persist across sessions (save to disk)

### 2.9 GPU Requirements

**Detection (Phase 1 expansion):**
```python
"gpu": {
    "nvidia": {
        "present": True,
        "model": "RTX 4090",
        "driver_version": "535.129.03",
        "cuda_version": "12.2",
        "compute_capability": "8.9",
    },
    "amd": {
        "present": False,
    },
    "intel": {
        "present": True,
        "model": "Intel UHD 770",
        "opencl_available": True,
    },
}
```

**Constraint in choices:**
```python
{
    "id": "cuda",
    "label": "NVIDIA CUDA",
    "requires": {
        "hardware": {
            "gpu.nvidia.present": True,
            "gpu.nvidia.compute_capability": ">=7.0",
        },
    },
    "available": True,  # resolved by comparing requirements to detected hardware
    "disabled_reason": None,  # only set if available=False
}
```

### 2.10 NLP / Machine Learning Frameworks

**Why this is complex:**
- PyTorch: CPU vs CUDA 11.8 vs CUDA 12.1 vs ROCm (different pip index URLs!)
- TensorFlow: CPU vs GPU (different pip packages)
- spaCy: needs language model downloads after install
- Hugging Face: needs model downloads (can be gigabytes)
- NLTK: needs data downloads (corpora, tokenizers)

**PyTorch example:**
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
                {"id": "rocm", "label": "ROCm 5.7",
                 "pip_index": "https://download.pytorch.org/whl/rocm5.7",
                 "requires": {"hardware": {"gpu.amd.present": True}}},
            ],
        },
    ],
    "install_variants": {
        "cpu": {"command": _PIP + ["install", "torch", "torchvision",
                                    "--index-url", "{pip_index}"]},
        "cuda118": {"command": _PIP + ["install", "torch", "torchvision",
                                        "--index-url", "{pip_index}"]},
        # ... same pattern, different index URL
    },
}
```

### 2.11 Language Packs and Data Packs

**What this means:**
- spaCy: `python -m spacy download en_core_web_sm` (English small model)
- NLTK: `python -c "import nltk; nltk.download('punkt')"`
- Hugging Face: `huggingface-cli download bert-base-uncased`
- Tesseract OCR: language data files
- Locale packs: `locale-gen en_US.UTF-8`

**What the recipe needs:**
```python
"data_packs": [
    {
        "id": "en_core_web_sm",
        "label": "English (small)",
        "size": "13 MB",
        "command": [sys.executable, "-m", "spacy", "download", "en_core_web_sm"],
    },
    {
        "id": "en_core_web_lg",
        "label": "English (large, more accurate)",
        "size": "741 MB",
        "command": [sys.executable, "-m", "spacy", "download", "en_core_web_lg"],
    },
],
"data_pack_choice": {
    "type": "multi",  # can select multiple
    "label": "Language Models",
    "description": "Select the models to download after installation",
}
```

### 2.12 System Configuration (Logging, Journal, Logrotate)

**What this means:**
- journald: configure max disk usage, compression, rate limiting
- logrotate: add rotation config for new tool's logs
- rsyslog/syslog-ng: forward logs to remote server
- Application config: nginx.conf, docker daemon.json, etc.

**What the recipe needs:**
```python
"config_templates": {
    "journald": {
        "file": "/etc/systemd/journald.conf.d/tool.conf",
        "template": "[Journal]\nSystemMaxUse={journal_max_size}\nCompress=yes\n",
        "inputs": [
            {"id": "journal_max_size", "label": "Max journal size",
             "type": "select", "options": ["100M", "500M", "1G", "2G"],
             "default": "500M"},
        ],
        "needs_sudo": True,
        "post_command": ["systemctl", "restart", "systemd-journald"],
        "condition": "has_systemd",
    },
    "logrotate": {
        "file": "/etc/logrotate.d/tool",
        "template": "{log_path} {\n    daily\n    rotate {rotate_count}\n    ...\n}\n",
        "inputs": [...],
        "needs_sudo": True,
    },
}
```

### 2.13 Version Selection

**This is universal.** Almost every tool has versions:
- Python: 3.10, 3.11, 3.12, 3.13
- Node: 18 LTS, 20 LTS, 22 current
- Go: 1.21, 1.22, 1.23
- Rust: stable, beta, nightly
- Docker: latest, specific version
- kubectl: must match cluster version (±1 minor)

**What the recipe needs:**
```python
"version_choice": {
    "type": "single",
    "label": "Version",
    "source": "static",  # or "dynamic" (fetch from API)
    "options": [
        {"id": "3.12", "label": "Python 3.12 (Recommended)", "default": True},
        {"id": "3.11", "label": "Python 3.11 (Previous LTS)"},
        {"id": "3.13", "label": "Python 3.13 (Newest, experimental)",
         "warning": "Some packages may not support 3.13 yet"},
    ],
    # Version affects the install command:
    # apt: python3.12 vs python3.11 (needs deadsnakes PPA)
    # brew: python@3.12 vs python@3.11
    # source: different tarball URL
}
```

**Dynamic version sources:**
```python
"version_choice": {
    "source": "dynamic",
    "fetch_url": "https://api.github.com/repos/kubernetes/kubernetes/releases",
    "parse": "json[].tag_name",
    "cache_ttl": 3600,  # cache for 1 hour
}
```

### 2.14 Branching Decision Trees — The Core Architecture

**Every layer can have choices. Choices create branches.**

```
Install OpenCV
├─ CHOICE: method? → [pip, system, source]
│  ├─ pip
│  │  ├─ CHOICE: variant? → [full, headless]
│  │  ├─ CHOICE: version? → [4.9, 4.10]
│  │  └─ LEAF: pip install opencv-python==4.10.0
│  ├─ system
│  │  ├─ CONSTRAINT: package available? → debian:yes, alpine:no
│  │  └─ LEAF: apt-get install python3-opencv
│  └─ source
│     ├─ CHOICE: gpu? → [none, cuda, rocm]
│     │  ├─ cuda
│     │  │  ├─ CONSTRAINT: nvidia GPU? → detected/not
│     │  │  ├─ CHOICE: cuda version? → [11.8, 12.1, 12.4]
│     │  │  │  └─ CONSTRAINT: driver compat? → 535+ for 12.x
│     │  │  └─ ... more deps
│     │  └─ none
│     ├─ CHOICE: extra modules? → [contrib, no-contrib]
│     ├─ REQUIRES: cmake, gcc, python3-dev, numpy
│     │  ├─ cmake not installed → sub-tree
│     │  └─ ...
│     └─ LEAF: cmake -B build ... && make && make install
```

**The resolver needs TWO passes:**

**Pass 1: Discovery** (returns to frontend)
```python
resolve_choices(tool, system_profile) -> {
    "tool": "opencv",
    "choices": [
        {
            "id": "method",
            "options": [
                {"id": "pip", "available": True},
                {"id": "system", "available": True,
                 "note": "Version 4.6 from Ubuntu repos (may be outdated)"},
                {"id": "source", "available": True,
                 "warning": "Build takes 20-60 minutes"},
            ],
        },
        # ... (choices revealed based on previous selections)
    ],
}
```

**Pass 2: Plan** (after user selects)
```python
resolve_install_plan(tool, system_profile, selections={
    "method": "source",
    "gpu": "cuda",
    "cuda_version": "12.1",
    "version": "4.10.0",
    "extra_modules": "contrib",
}) -> {
    "steps": [...],  # concrete plan based on selections
}
```

### 2.15 Disabled Options — Always Present for the Assistant

**Critical principle:** Options that can't be used on this system are
NOT removed. They are returned with `available: False` and a reason.

Why? The assistant panel needs to tell the user:
- "CUDA acceleration is not available because no NVIDIA GPU was detected"
- "To enable this option, install an NVIDIA GPU and CUDA toolkit"
- "The ROCm option requires an AMD GPU with ROCm 5.x support"

If we remove unavailable options, the assistant can't explain them.
The user doesn't know what they're missing.

```python
{
    "id": "cuda",
    "label": "NVIDIA CUDA acceleration",
    "available": False,
    "disabled_reason": "No NVIDIA GPU detected (lspci shows no NVIDIA device)",
    "enable_hint": "Install a compatible NVIDIA GPU and install the "
                   "proprietary NVIDIA driver to enable CUDA support",
    "learn_more": "https://developer.nvidia.com/cuda-gpus",
}
```

### 2.16 Network & Offline Scenarios

**What can happen:**
- Full internet access (normal case)
- Behind corporate proxy (HTTP_PROXY, HTTPS_PROXY)
- Air-gapped environment (no internet at all)
- Partial access (internal mirror reachable, public internet not)
- Intermittent connectivity (timeout during large downloads)

**What the system needs:**
- Phase 1 detection: probe key endpoints (PyPI, GitHub, npm registry)
- Each endpoint probe returns: reachable/unreachable/slow/proxy-required
- Recipes that need network have a `requires.network` field
- If network is unavailable, disable online-only options (curl scripts, pip)
- Offer alternatives: local binary, pre-downloaded package, internal mirror

```python
"network": {
    "online": True,
    "proxy_detected": True,
    "proxy_url": "http://proxy.corp.com:8080",
    "endpoints": {
        "pypi.org": {"reachable": True, "latency_ms": 45},
        "github.com": {"reachable": True, "latency_ms": 120},
        "registry.npmjs.org": {"reachable": False, "error": "timeout"},
    },
}
```

**Impact on architecture:**
- Install methods gain a `requires.network` field (most need it)
- Options missing network are disabled with clear reason
- Future: local cache / mirror support for air-gapped environments
- Proxy settings can be injected into commands (pip --proxy, curl --proxy)

### 2.17 Parallel Step Execution

**Current model:** Plans are LINEAR — step 1, step 2, step 3, done.

**Reality:** Some steps are INDEPENDENT and could run in parallel:
- While building OpenCV from source (30 min), download data packs
- While `apt-get install` runs for one tool, `pip install` runs for another
- System package batch + cargo build can overlap

**What the plan format needs:**
```python
"steps": [
    {"id": "step1", "type": "packages", ...},
    {"id": "step2", "type": "tool", ..., "depends_on": ["step1"]},
    {"id": "step3", "type": "tool", ..., "depends_on": ["step1"]},
    # step2 and step3 can run in parallel — both only depend on step1
    {"id": "step4", "type": "verify", ..., "depends_on": ["step2", "step3"]},
]
```

**Impact on architecture:**
- Plan steps get an optional `depends_on` field (list of step IDs)
- Steps with no unmet dependencies can be dispatched simultaneously
- Frontend needs to show parallel progress (multiple log streams)
- Phase 2 keeps it simple: all linear. Phase 8+ adds parallelism.
- Plan format must NOT prevent this — `depends_on` is additive

### 2.18 Pages Install Unification

**Current state:** `pages_install.py` is a SEPARATE install system
for page builders (Hugo, MkDocs, Docusaurus). It has:
- Its own SSE streaming
- Its own arch/OS detection (duplicates Phase 1)
- Its own binary download logic (Hugo binary installer)
- Its own error handling

**What should happen:**
- Hugo, MkDocs, Docusaurus become TOOL_RECIPES entries
- Hugo binary download uses the same binary installer pattern
- MkDocs uses pip install (already a supported method)
- Docusaurus uses npm install (already a supported method)
- SSE streaming uses the unified streamSSE() pattern
- Frontend uses executeInstallPlan() like all other tools

**Impact on architecture:**
- Add Hugo/MkDocs/Docusaurus to TOOL_RECIPES
- Hugo needs a `binary` install method with URL template
- The existing `pages_install.py` can be gradually replaced
- Frontend pages-install.js uses the same modal pattern
- This is a Phase 3 task (frontend unification)

---

## 3. How This Changes the Recipe Format

### Old format (Phase 2.2)

```python
TOOL_RECIPES = {
    "ruff": {
        "label": "Ruff",
        "install": {"_default": _PIP + ["install", "ruff"]},
        "needs_sudo": {"_default": False},
        "verify": ["ruff", "--version"],
        "update": {"_default": _PIP + ["install", "--upgrade", "ruff"]},
    },
}
```

### New format (evolved)

```python
TOOL_RECIPES = {
    # SIMPLE tools (most devops tools) — same as before, no choices
    "ruff": {
        "label": "Ruff",
        "install": {"_default": _PIP + ["install", "ruff"]},
        "needs_sudo": {"_default": False},
        "verify": ["ruff", "--version"],
        "update": {"_default": _PIP + ["install", "--upgrade", "ruff"]},
        # No choices field → simple recipe, resolved directly
    },

    # COMPLEX tools — have choices that create branches
    "pytorch": {
        "label": "PyTorch",
        "choices": [...],          # decision points
        "inputs": [...],           # user-provided values
        "install_variants": {...}, # per-branch install commands
        "data_packs": [...],       # optional downloads after install
        "config_templates": {...}, # configuration files to write
        # Resolved via two-pass: discover choices → user selects → plan
    },
}
```

**Backward compatible:** Simple tools (no `choices` field) use the
existing single-pass resolver. Complex tools (with `choices`) use
the two-pass resolver. The code checks:

```python
if "choices" in recipe:
    # Two-pass: return choices first, then resolve with selections
else:
    # Single-pass: resolve directly (current behavior)
```

---

## 4. What This Means for the Phase Structure

The current Phase 2 sub-phases handle SIMPLE tools. The complex
scenarios described above are a DIFFERENT level of capability.

### What Phase 2 covers (unchanged)

Phase 2.1-2.5: Install devops CLI tools with multi-platform support,
dependency resolution, service management, updates. This covers ALL
35+ tools in the current _TOOLS registry.

**These tools are ALL simple recipes.** None of them need decision
trees, GPU detection, build-from-source, or configuration inputs.
They have at most: platform variants + dependency chains + post-install.

### What Phase 4+ covers (new)

The complex scenarios require:

**Phase 4: Decision Tree Architecture**
- Choice/input/constraint data model
- Two-pass resolver (discover → select → plan)
- Frontend choice UI (radio buttons, selects, disabled options)
- Assistant integration (explain disabled options)
- Template variable substitution in commands

**Phase 5: Build-from-Source Support**
- Build step type (configure, compile, install)
- Build tool dependency chains
- Long-running build progress reporting
- Build flag management

**Phase 6: Hardware Detection**
- GPU detection (NVIDIA, AMD, Intel)
- CUDA/ROCm version detection
- Kernel config inspection
- Hardware constraint evaluation

**Phase 7: Data Packs & Downloads**
- Language model downloads
- Dataset downloads
- Size estimation and progress
- Multi-select UI

**Phase 8: System Configuration**
- Config file templates
- Service configuration
- Log configuration
- Restart management (session, service, system)
- Resumable plans (persist state across restarts)

### Why the split matters

Phase 2 is ACHIEVABLE NOW. It improves the existing system
significantly. 35+ tools get multi-platform support.

Phases 4-8 are a DIFFERENT PRODUCT. They turn the tool installer
into a full software provisioning system. Each phase is independently
valuable but builds on the previous.

---

## 5. The Architecture Must Be Designed for Growth

Even though Phase 2 only implements simple recipes, the DATA FORMAT
and RESOLVER INTERFACE must be designed so that:

1. Adding `choices` to a recipe later doesn't break existing recipes
2. The endpoint can evolve from single-pass to two-pass
3. The frontend can render choice UI when it encounters it
4. Disabled options flow through the system to the assistant

**Concrete design rules for Phase 2:**

1. `TOOL_RECIPES` is a dict. Adding new keys to a recipe entry is safe.
2. `resolve_install_plan()` returns a dict. Adding new keys is safe.
3. The endpoint response format is extensible (JSON dict, not array).
4. The frontend checks for `choices` field — if absent, direct install.
   If present, show choice UI first.

These rules mean Phase 2 code doesn't need to IMPLEMENT choices,
but it doesn't PREVENT them either.

---

## 6. Scenarios Beyond Phase 2 (Named and Mapped)

| Scenario | Why beyond Phase 2 | Which future phase |
|----------|-------------------|-------------------|
| OpenCV with CUDA | Needs GPU detection, build-from-source, choice tree | Phase 4+5+6 |
| PyTorch GPU variant | Needs GPU detection, choice UI, pip index switching | Phase 4+6 |
| Kernel module loading | Needs kernel config detection, risk gates, confirmation | Phase 6 |
| Kernel recompilation | Needs build-from-source, restart+resume, rollback | Phase 5+6+8 |
| WSL kernel customization | Needs WSL interop detection, cross-OS commands | Phase 6 |
| GPU passthrough (vfio) | Needs kernel module loading + IOMMU group detection | Phase 6 |
| Broken .bashrc / .zshrc | Needs shell type detection, profile file editing | Phase 4 |
| Restricted shell (rbash) | Needs sandbox detection in Phase 1 expansion | Phase 1+ |
| System restart + resume | Needs persistent plan state, resumable execution | Phase 8 |
| spaCy language models | Needs data pack UI (multi-select, size estimates) | Phase 7 |
| HuggingFace model download | Needs data pack UI + large download progress | Phase 7 |
| journald configuration | Needs config template system + inputs | Phase 8 |
| logrotate configuration | Needs config template system | Phase 8 |
| Version selection (Python, Node, Go) | Needs choice UI + version-aware commands | Phase 4 |
| npm global permission fix | Needs shell config editing | Phase 4 |
| Docker storage driver config | Needs config input UI | Phase 4+8 |
| Build cmake from source to build opencv | Recursive build chains | Phase 5 |
| Private PyPI/npm registry | Needs registry config | Phase 4 |
| Air-gapped / offline install | Needs network detection, local mirror support | Phase 4+ |
| Parallel step execution | Needs plan format extension for DAG-based steps | Phase 8+ |
| pages_install.py unification | Separate install system for page builders | Phase 3+ |

---

## 7. Updated Phase Roadmap

```
Phase 1  (DONE)     System detection (fast tier)
  1+     (FUTURE)   Expansion: GPU, kernel, shell, network, disk (deep tier)
Phase 2  (CURRENT)  Simple tool recipes + resolver + execution
  2.1  Package checking (multi-pm)
  2.2  Recipe format + dependency declarations (lifecycle)
  2.3  Resolver engine (single-pass, no choices)
  2.4  Execution replacement
  2.5  Update & maintenance
Phase 3             Frontend + pages unification (step modal, plan display, pages_install)
Phase 4             Decision trees (choices, inputs, constraints, version selection)
Phase 5             Build-from-source (cmake, make, meson, progress, disk)
Phase 6             Hardware + kernel (GPU detect, module loading, kernel recompile, WSL kernel)
Phase 7             Data packs & downloads (spaCy, NLTK, HuggingFace, locale)
Phase 8             System config & orchestration (services, config files, restart, parallel)
```

Each phase is independently shippable. Phase 2 alone is a major
improvement over the current flat Debian-only system.

---

## 8. Key Architectural Principles (Applies to ALL Phases)

1. **Always present, sometimes disabled.**
   Every option exists in the response. Unavailable = disabled + reason.

2. **User decides, system suggests.**
   The resolver recommends defaults. The user can override.
   Forced choices (only one option available) are auto-selected.

3. **Branches are explicit.**
   No hidden conditional logic. Every decision point is a named choice
   with visible options.

4. **The assistant panel is the explainer.**
   Disabled reasons, enable hints, trade-off descriptions — all flow
   through the data to the assistant panel.

5. **Plans are deterministic.**
   Given the same tool + system profile + selections → same plan.
   No randomness, no external fetches during resolution (only during
   dynamic version listing).

6. **Extensibility by addition.**
   Adding a new field to a recipe doesn't break existing recipes.
   Adding a new choice type doesn't break existing choices.
   The system is designed for evolution, not revolution.

7. **Nothing is off-limits with safeguards.**
   Kernel recompilation, GPU driver installation, bootloader updates —
   all are automatable. High-risk steps get confirmation gates, backups,
   rollback instructions, and risk-level UI treatment. The system
   presents the risk honestly and lets the user decide.

8. **Interactive from the Admin panel.**
   Everything the system can do is accessible from the web admin UI.
   The user browses, selects, configures, and executes — all from the
   browser. The CLI and TUI are alternative interfaces to the same
   resolver and execution engine.

---

## 9. Infrastructure Requirement: Download Backend Cascade

> Discovered during curl per-tool audit (2026-02-26).
> This is a cross-cutting infrastructure concern that applies to ALL
> install methods that download anything: `_default`, `source`, `binary`.

### 9.1 The problem: circular dependencies in download tools

Many tools use `curl | bash` or `git clone https://` to install.
But what if `curl` is missing? What if `git` is missing?
What if both are missing?

The download backends available on a system are:

| Backend | CLI binary | HTTPS? | Depends on libcurl? | Default availability |
|---------|-----------|--------|---------------------|---------------------|
| `curl` | `curl` | ✅ | IS libcurl | Most systems, not guaranteed |
| `wget` | `wget` | ✅ | ❌ (gnutls/openssl) | Many systems, NOT macOS, NOT Alpine minimal, NOT Arch minimal |
| `python3 urllib` | `python3` | ✅ | ❌ (Python ssl module) | Most systems, NOT bare Alpine |
| `busybox wget` | `busybox wget` or `wget` | ❌ (no TLS by default) | ❌ | Alpine only (BusyBox applet, no HTTPS) |
| `git` (HTTPS) | `git` | ✅ | ✅ (git uses libcurl for HTTP) | Many systems, NOT all |
| `perl LWP` | `perl` | ✅ (if LWP installed) | ❌ | Not common |

**Key fact:** `git clone https://` uses libcurl under the hood on most
Linux systems. If curl/libcurl is completely absent, git HTTPS also
breaks. So "use git clone as fallback for missing curl" is circular.

**Key fact:** `wget` uses its own HTTP stack (gnutls or openssl
directly), NOT libcurl. wget is the true independent fallback.

**Key fact:** `python3 urllib` uses Python's ssl module (linked to
system openssl), NOT libcurl. python3 is another true independent
fallback.

### 9.2 The base case: native PM never needs a download backend

The native PM (`apt`, `dnf`, `apk`, `pacman`, `zypper`, `brew`)
uses its OWN download mechanism. It does NOT need curl, wget, or git.

- `apt` uses its own HTTP transport (`/usr/lib/apt/methods/http`)
- `dnf` uses `librepo` (its own download library)
- `apk` uses its own fetch code
- `pacman` uses its own download code
- `zypper` uses `libzypp` (its own download library)
- `brew` uses `curl` (exception! brew DOES need curl)

So on every Linux system, the native PM is the **base case** that
breaks all circular dependencies. brew on macOS is the exception —
macOS always has curl pre-installed (Apple ships it with the OS).

### 9.3 The unlock cascade

```
Level 0: Native PM (always available — the base case)
  │
  ├── apt/dnf/apk/pacman/zypper install curl    → curl is now READY
  ├── apt/dnf/apk/pacman/zypper install wget    → wget is now READY
  ├── apt/dnf/apk/pacman/zypper install git     → git is now READY
  └── apt/dnf/apk/pacman/zypper install python3 → python3 urllib READY
        │
Level 1: With curl available
  │
  ├── curl | bash install scripts    → _default methods READY
  ├── git clone https://             → source (git) methods READY
  ├── curl -LO binary.tar.gz        → binary download methods READY
  └── pip/npm/cargo install          → language PM methods READY
        │
Level 2: With curl + git available
  │
  ├── git clone + make              → source build methods READY
  ├── pip install from git repos     → pip+git methods READY
  └── cargo install from git repos   → cargo+git methods READY
```

**Nothing is `impossible` due to missing download tools.**
Everything is `locked` with an unlock chain that bottoms out at
the native PM. The only `impossible` states are:
- PM not available on this system (e.g., `dnf` on Debian)
- Hardware not present (e.g., NVIDIA GPU)
- Architecture not supported (e.g., ARM-only tool on x86)

### 9.4 Handler option ordering for download failures

When a download fails because the download backend is missing,
the handler should offer options in TWO groups:

**Primary options (shown prominently, ordered by likelihood):**

1. 🟢 **Recommended:** Install the missing tool via native PM
   (e.g., `apt install curl`) — always `ready` on the right system
2. 🟢 **Alternative:** Use wget to download instead
   — `ready` if wget is installed, `locked` if not
3. 🟢 **Alternative:** Use python3 urllib to download instead
   — `ready` if python3 is installed, `locked` if not

**Extended options (collapsed / expandable, for edge cases):**

4. 🔒 Install wget first, then use wget to download
   — `locked`, unlock dep: wget (install via PM)
5. 🔒 Install python3 first, then use urllib
   — `locked`, unlock dep: python3 (install via PM)
6. 🔒 Install git first, then git clone
   — `locked`, unlock dep: git (install via PM)
   — note: git HTTPS also needs libcurl on most systems

### 9.5 Infrastructure changes needed

The current handler/remediation architecture supports `ready`/`locked`/
`impossible` states and the `_compute_availability` function gates
options correctly. What's MISSING:

1. **Option grouping:** No way to mark options as "primary" vs
   "extended/other". The frontend shows all options in a flat list.
   Need a `group` or `priority` field on options.

2. **Download backend abstraction:** When a recipe says `git_repo:`
   or `tarball_url:`, the execution engine needs to try available
   backends in order:
   - For tarballs: curl → wget → python3 urllib
   - For git repos: git (if libcurl works) → wget tarball fallback
   This is NOT per-tool logic. It's infrastructure.

3. **The `missing_curl` handler "Use wget instead" option** does NOT
   check if wget is actually installed. It's a modifier with no
   availability gate. This needs to go through `_compute_availability`.

4. **Locked option unlock deps** should cascade: if "Use wget" is
   locked because wget isn't installed, the unlock dep "wget" resolves
   to `apt install wget` which is always `ready` — so the user sees
   `locked (install wget first)` not `impossible`.

### 9.6 When to implement

This is infrastructure that should be built AFTER the per-tool audit
is complete. The per-tool audit documents the download dependencies
factually. The infrastructure evolution then addresses all of them
at once rather than per-tool hacks.

Phase mapping: This falls under **Phase 2 evolution** for the option
grouping and availability gating, and **Phase 5** for the download
backend abstraction in the build-from-source execution engine.

