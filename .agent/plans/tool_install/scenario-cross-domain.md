# Scenarios: Cross-Domain Installations

> Complex installation scenarios that span multiple domains.
> Each scenario traces through the full system: detection →
> choices → resolution → plan → execution → verification.
>
> These scenarios validate the architecture handles real-world
> complexity where multiple domains interact.

---

## Scenario 1: Docker CE on Debian (no snap)

**Domains:** packages, repos, services, config, sudo, restart

### Context
- Debian 12, systemd, no snap
- User wants Docker CE (official), not docker.io
- No existing Docker installation

### Detection
```
distro_family: debian
package_manager: apt
has_snap: false
has_systemd: true
is_root: false
has_sudo: true
```

### Choices presented
```
Choice: docker_variant
  ○ docker.io (Debian community)     — available
  ● Docker CE (Official)             — available, user picks
  ○ Podman (alternative)             — available
```

### Resolved plan (7 steps)
```
Step 1: [repo]         Import Docker GPG key                    sudo
Step 2: [repo]         Add Docker apt repository                sudo
Step 3: [packages]     apt-get update                           sudo
Step 4: [packages]     Install docker-ce, docker-ce-cli,        sudo
                       containerd.io
Step 5: [service]      Start docker                             sudo
Step 6: [service]      Enable docker on boot                    sudo
Step 7: [verify]       docker --version
```

### Restart needs
```
service_restart: [docker]           — already handled by step 5
shell_restart: false
reboot_required: false
post_install_note: "Run 'sudo usermod -aG docker $USER' then re-login
                    to use Docker without sudo"
```

---

## Scenario 2: PyTorch + CUDA on Ubuntu

**Domains:** gpu, kernel, packages, language-pms, data-packs, choices, network

### Context
- Ubuntu 22.04, systemd, NVIDIA RTX 3080
- No NVIDIA driver installed (nouveau active)
- User wants PyTorch with GPU support

### Detection
```
distro_family: debian
gpu.has_gpu: true
gpu.vendor: nvidia
gpu.model: NVIDIA GeForce RTX 3080
gpu.driver_loaded: false
kernel.modules_loaded: [nouveau]
kernel.secure_boot: false
kernel.version: 6.5.0-44-generic
kernel.headers_installed: true
```

### Choices presented
```
Choice 1: nvidia_driver_version
  ● Recommended (535)    — auto-detected for RTX 3080
  ○ Latest (545)
  ○ 470 (legacy)         — disabled: "Not compatible with RTX 3080"

Choice 2: cuda_version
  ● 12.3                 — compatible with driver 535
  ○ 12.2
  ○ 11.8
  ○ 12.4                 — disabled: "Requires driver 545+"

Choice 3: pytorch_variant
  ● pip (recommended)
  ○ conda
  ○ build from source    — "Requires 30+ min, 8 GB RAM"
```

### Resolved plan (12 steps)
```
Step 1:  [repo]        Add NVIDIA PPA                          sudo    risk:medium
Step 2:  [packages]    apt-get update                          sudo
Step 3:  [packages]    Install linux-headers-6.5.0-44-generic  sudo
Step 4:  [packages]    Install nvidia-driver-535               sudo    risk:high
Step 5:  [packages]    Blacklist nouveau                       sudo    risk:medium
Step 6:  [verify]      nvidia-smi
Step 7:  [packages]    Install CUDA toolkit 12.3               sudo
Step 8:  [config]      Add CUDA to PATH (.bashrc)
Step 9:  [tool]        pip install torch torchvision --index-url
                       https://download.pytorch.org/whl/cu123
Step 10: [download]    Download PyTorch CUDA libraries         ~2 GB
Step 11: [verify]      python -c "import torch; print(torch.cuda.is_available())"
Step 12: [notification] Reboot required for NVIDIA driver
```

### Risk assessment
```
Overall risk: HIGH
  Step 4: nvidia-driver install (risk: high)
    - Modifies kernel modules
    - Can break display
    - Backup: nouveau fallback
  Step 5: blacklist nouveau (risk: medium)
    - Modifies modprobe config
    - Backup: /etc/modprobe.d/blacklist-nouveau.conf
```

### Restart needs
```
reboot_required: true    — NVIDIA driver needs reboot
shell_restart: true      — CUDA PATH added
reasons:
  - "NVIDIA driver installed — reboot required"
  - "CUDA added to PATH — restart shell or: source ~/.bashrc"
```

---

## Scenario 3: cargo-audit on Alpine (no glibc)

**Domains:** containers, compilers, build-from-source, packages, language-pms

### Context
- Alpine 3.19 (in container)
- musl libc (not glibc)
- Rust 1.72 installed via rustup
- cargo-audit requires Rust 1.74+

### Detection
```
distro_family: alpine
package_manager: apk
in_container: true
is_root: true
has_systemd: false
libc: musl
rust_version: 1.72.0
cargo_version: 1.72.0
```

### Resolution
```
1. cargo-audit latest requires rustc 1.74+
2. Current rustc: 1.72
3. Remediation options generated:
```

### Choices presented
```
Choice: install_strategy
  ○ Compatible version (cargo-audit@0.18.3, works with rustc 1.72)
  ● Upgrade Rust first, then install latest
  ○ Build from source (locked to compatible commit)
```

### Resolved plan (5 steps)
```
Step 1: [packages]    apk add pkgconf openssl-dev curl-dev     (root, no sudo)
Step 2: [tool]        rustup update                            (upgrades to 1.80+)
Step 3: [verify]      rustc --version                          (confirm 1.74+)
Step 4: [tool]        cargo install cargo-audit                (builds from crates.io)
                      timeout: 300s
Step 5: [verify]      cargo-audit --version
```

### Special handling
```
- Alpine/musl: some crates need musl-specific patches
- In container: root already, no sudo
- Build from source: cargo compiles, needs build deps
- Timeout extended: 300s for Rust compilation
```

---

## Scenario 4: Full DevOps Stack on Fedora

**Domains:** packages, repos, language-pms, services, config, choices

### Context
- Fedora 39, systemd, no tools pre-installed
- User wants: docker, kubectl, helm, terraform, gh, trivy

### Detection
```
distro_family: fedora
package_manager: dnf
has_snap: false
has_systemd: true
```

### Resolution: Batch install
```
6 tools → resolver produces MERGED plan:

Shared steps (deduplicated):
  - Package groups batched (one dnf call)
  - Repos added in sequence (different GPG keys)

Tool-specific steps in parallel where possible:
  - helm (bash-curl) || gh (dnf) || trivy (bash-curl)
  - kubectl (repo+dnf) sequential (repo setup first)
```

### Resolved plan (15 steps, DAG)
```
Step 1:  [repo]      Add Docker repo (GPG + yum source)       sudo
Step 2:  [repo]      Add Kubernetes repo                      sudo
Step 3:  [repo]      Add HashiCorp repo                       sudo
Step 4:  [repo]      Add GitHub CLI repo                      sudo
Step 5:  [packages]  dnf install docker-ce kubectl terraform   sudo
                     gh                                        (batched!)
Step 6:  [tool]      Install helm (bash-curl)                  sudo
                     depends_on: []
Step 7:  [tool]      Install trivy (bash-curl)                 sudo
                     depends_on: []
Step 8:  [service]   Start docker                              sudo
                     depends_on: [5]
Step 9:  [service]   Enable docker                             sudo
                     depends_on: [5]
Step 10: [config]    Docker daemon.json (BuildKit)             sudo
                     depends_on: [5]
Step 11: [service]   Restart docker (config changed)           sudo
                     depends_on: [10]
Step 12: [data]      trivy --download-db-only                  
                     depends_on: [7]
Step 13: [verify]    docker --version                          depends_on: [11]
Step 14: [verify]    kubectl version --client                  depends_on: [5]
Step 15: [verify]    All tools verified                        depends_on: [6,7,13,14]
```

### DAG parallelism
```
Steps 1-4: sequential (repo additions)
Step 5: waits on 1-4
Steps 6,7: parallel with 5 (independent downloads)
Steps 8,9,10: parallel after 5 (all depend on docker installed)
Step 11: after 10 (config must be written before restart)
Step 12: after 7 (trivy must be installed)
Steps 13,14: after respective installs
Step 15: final verification gate
```

---

## Scenario 5: Hugo Site Builder on WSL2

**Domains:** wsl, binary-installers, network, shells, containers

### Context
- WSL2 (Ubuntu 22.04 under Windows 11)
- No Hugo installed
- User wants Hugo extended (for SCSS support)
- Docker Desktop available on Windows side

### Detection
```
distro_family: debian
in_wsl: true
wsl_version: 2
has_systemd: true (WSL2 systemd enabled)
has_snap: true
docker_desktop: true (via WSL integration)
cpu_arch: x86_64
```

### Choices presented
```
Choice 1: hugo_variant
  ● Hugo Extended (SCSS/SASS support)
  ○ Hugo Standard

Choice 2: install_method
  ○ snap install hugo                 — available
  ● Binary download (latest version)  — available
  ○ Build from source (Go required)   — disabled: "Go not installed"
  ○ apt install hugo                  — disabled: "apt version too old (0.92)"
```

### Resolved plan (4 steps)
```
Step 1: [source]     Fetch latest Hugo release from GitHub API
Step 2: [download]   Download hugo_extended_0.128.0_linux-amd64.tar.gz    ~20 MB
Step 3: [tool]       Extract to ~/.local/bin/hugo, chmod 755
Step 4: [verify]     hugo version
```

### WSL-specific handling
```
- PATH: ~/.local/bin should already be in PATH on WSL Ubuntu
- No sudo needed (user-space install)
- Docker: already available via Docker Desktop integration
- No snap needed (binary download preferred for latest)
```

---

## Scenario 6: OpenCV with CUDA on Ubuntu

**Domains:** gpu, build-from-source, compilers, packages, choices, data-packs

### Context
- Ubuntu 22.04, NVIDIA RTX 4090
- NVIDIA driver 535 + CUDA 12.3 already installed
- User wants OpenCV with CUDA support (not available as apt package)

### Detection
```
gpu.vendor: nvidia
gpu.driver_version: 535.183.01
gpu.cuda_version: 12.3
python_version: 3.11
cmake_version: 3.22
gcc_version: 12.3.0
```

### Choices presented
```
Choice 1: opencv_variant
  ○ OpenCV (CPU only, pip install)       — easy, 5 seconds
  ● OpenCV + CUDA (build from source)    — complex, ~30 min
  ○ OpenCV + CUDA + cuDNN               — most features, needs cuDNN

Choice 2: python_bindings
  ● Yes (build with Python bindings)
  ○ No (C++ only)
```

### Resolved plan (10 steps)
```
Step 1:  [packages]   Install build deps (cmake, g++, python3-dev,   sudo
                      libgtk-3-dev, libavcodec-dev, ...)
Step 2:  [source]     git clone opencv + opencv_contrib
Step 3:  [build]      cmake -B build                                timeout: 60s
                      -DWITH_CUDA=ON
                      -DCUDA_ARCH_BIN=8.9 (RTX 4090)
                      -DOPENCV_EXTRA_MODULES_PATH=contrib/modules
                      -DPYTHON3_EXECUTABLE=/usr/bin/python3
Step 4:  [build]      cmake --build build -j8                       timeout: 1800s
Step 5:  [install]    cmake --install build                         sudo
Step 6:  [verify]     python3 -c "import cv2; print(cv2.getBuildInformation())"
Step 7:  [verify]     Check CUDA support in build info
Step 8:  [cleanup]    rm -rf /tmp/opencv-build
```

### Resource pre-check
```
disk_needed: ~5 GB (source + build)
ram_needed: ~4 GB (parallel compilation)
estimated_time: 20-40 min
cpu_cores_used: 8 (of 16)
```

---

## Scenario 7: Air-Gapped Kubernetes Node

**Domains:** network, containers, packages, services, config, data-packs

### Context
- RHEL 9, air-gapped (no internet)
- Offline package mirror available at 192.168.1.100
- User needs: containerd, kubectl, kubelet, kubeadm

### Detection
```
distro_family: rhel
package_manager: dnf
network.state: air_gapped
network.probes: {pypi: false, github: false, gcr: false,
                 internal_mirror: true}
has_systemd: true
```

### Choices presented
```
Choice 1: container_runtime
  ○ Docker CE              — disabled: "Cannot reach download.docker.com"
  ● containerd             — available via offline mirror
  ○ CRI-O                  — available via offline mirror

Choice 2: k8s_version
  Select: 1.29.3           — available in offline mirror
  (versions loaded from mirror manifest, not GitHub)
```

### Resolved plan (10 steps)
```
Step 1:  [repo]       Add offline mirror as dnf repo             sudo
Step 2:  [packages]   dnf install containerd kubectl             sudo
                      kubelet kubeadm
Step 3:  [config]     Write /etc/containerd/config.toml          sudo
Step 4:  [config]     Write /etc/sysctl.d/k8s.conf               sudo
                      (net.bridge, ip_forward)
Step 5:  [config]     Write /etc/modules-load.d/k8s.conf         sudo
                      (br_netfilter, overlay)
Step 6:  [tool]       modprobe br_netfilter overlay              sudo
Step 7:  [tool]       sysctl --system                            sudo
Step 8:  [service]    Start + enable containerd                  sudo
Step 9:  [service]    Start + enable kubelet                     sudo
Step 10: [verify]     kubectl version --client
                      kubelet --version
                      containerd --version
```

### Air-gapped handling
```
- All online options disabled (Docker CE, GitHub-based installs)
- Package source: offline mirror only
- No version API calls — versions from mirror manifest
- Container images: must be pre-loaded from offline registry
```

---

## Scenario 8: ML Development Environment

**Domains:** language-pms, gpu, data-packs, choices, network

### Context
- Ubuntu 22.04, NVIDIA A100 (data center GPU)
- CUDA 12.3 + driver already installed
- User wants: PyTorch + Jupyter + common ML libraries

### Resolved plan (8 steps)
```
Step 1:  [tool]       pip install torch torchvision torchaudio
                      --index-url https://download.pytorch.org/whl/cu123
Step 2:  [tool]       pip install jupyterlab numpy pandas
                      scikit-learn matplotlib seaborn
Step 3:  [tool]       pip install transformers datasets
                      accelerate evaluate
Step 4:  [download]   Download spaCy en_core_web_lg            560 MB
Step 5:  [download]   Download NLTK punkt tokenizer             35 MB
Step 6:  [verify]     python -c "import torch; assert torch.cuda.is_available()"
Step 7:  [verify]     jupyter lab --version
Step 8:  [config]     jupyter server --generate-config
```

### Download awareness
```
Total download: ~4.5 GB
  PyTorch CUDA wheels: ~2.5 GB
  ML libraries: ~1.2 GB
  spaCy model: ~560 MB
  NLTK data: ~35 MB

Estimated time at 100 Mbps: ~6 min
Disk space needed: ~8 GB (wheels + installed)
```

---

## Cross-Scenario Patterns

### What these scenarios validate

| Pattern | Scenarios |
|---------|-----------|
| Multi-step plans (5+ steps) | All |
| Choices affect plan | 1, 2, 4, 5, 6, 7 |
| Sudo across multiple steps | 1, 2, 4, 7 |
| Package batching | 4, 7 |
| DAG parallelism | 4 |
| Build-from-source | 3, 6 |
| GPU-gated options | 2, 6, 8 |
| Air-gapped fallbacks | 7 |
| Binary download | 5 |
| Data pack downloads | 2, 8 |
| Restart/reboot needs | 1, 2 |
| Container-specific paths | 3 |
| WSL-specific paths | 5 |
| Risk escalation | 2, 6 |
| Version constraints | 2, 3, 7 |

---

## Traceability

| Scenario | Phases exercised |
|----------|-----------------|
| 1 (Docker CE) | 2, 3, 4, 8 |
| 2 (PyTorch+CUDA) | 2, 3, 4, 6, 7 |
| 3 (cargo-audit Alpine) | 2, 5 |
| 4 (Full DevOps stack) | 2, 3, 4, 8 |
| 5 (Hugo WSL2) | 2, 3, 4 |
| 6 (OpenCV CUDA) | 2, 4, 5, 6 |
| 7 (Air-gapped K8s) | 2, 4, 7, 8 |
| 8 (ML Environment) | 2, 6, 7 |
