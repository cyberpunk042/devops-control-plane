# Scenarios: Interop & Special Environments

> Installation scenarios in non-standard environments where the
> system must adapt its behavior. Each scenario describes the
> environment constraints, what changes in detection, resolution,
> and execution, and what the user should expect.

---

## Scenario 1: WSL2 — Ubuntu Under Windows

### I1.1 — Basic tool install in WSL2

**Context:**
- WSL2, Ubuntu 22.04 under Windows 11
- systemd enabled (modern WSL2)
- Docker Desktop installed on Windows side
- User wants to install kubectl

**Detection differences:**
```
in_wsl: true
wsl_version: 2
has_systemd: true          # modern WSL2 with systemd
docker: available           # via Docker Desktop WSL integration
snap: available             # works in WSL2 with systemd
```

**What changes in resolution:**
```
kubectl recipe:
  snap install kubectl --classic    ← works normally
  apt install kubectl               ← works normally
  binary download                   ← works normally
  
  NO CHANGES NEEDED — WSL2 with systemd is effectively a full Linux
```

**What the user sees:** Normal install flow. WSL2 is transparent.

---

### I1.2 — Docker in WSL2 (Docker Desktop integration)

**Context:**
- Docker Desktop running on Windows
- WSL2 integration enabled
- User clicks "Install Docker" in audit panel

**Detection:**
```
docker --version: Docker version 27.0.1 (from Docker Desktop)
dockerd: NOT running locally (it's on Windows side)
/var/run/docker.sock: exists (WSL integration socket)
```

**What changes:**
```
Tool: docker
Status: ✅ Already installed (via Docker Desktop)
Version: 27.0.1

Note: Docker is provided by Docker Desktop on Windows.
      No installation needed in WSL2.
      
If you want a native Docker in WSL2:
  ○ Install docker.io (apt)           [Install]
  ○ Keep Docker Desktop integration    [Keep — recommended]
```

**System behavior:**
- Detect Docker Desktop integration (socket exists, no local dockerd)
- Mark as installed
- Offer choice only if user explicitly wants native Docker
- No service management (Docker Desktop manages the daemon)

---

### I1.3 — WSL1 limitations

**Context:**
- WSL1 (not WSL2) — no real Linux kernel
- No systemd, no snap, no Docker

**Detection:**
```
in_wsl: true
wsl_version: 1
has_systemd: false
has_snap: false
docker: not available
```

**What changes:**
```
Disabled options:
  ○ Docker         — disabled: "Requires WSL2 or real Linux kernel"
  ○ snap packages  — disabled: "snap requires systemd (WSL2)"
  ○ systemd services — disabled: "WSL1 does not have systemd"
  
Available options:
  ○ apt packages   — works
  ○ pip packages   — works
  ○ cargo install  — works
  ○ npm -g         — works
  ○ binary download — works
```

**Impact:** Service management steps are filtered out. No systemctl calls.

---

## Scenario 2: Docker-in-Docker (DinD)

### I2.1 — Running inside a Docker container

**Context:**
- Ubuntu 22.04 container (not privileged)
- No systemd, no snap, root user
- Limited filesystem
- User wants to install trivy

**Detection:**
```
in_container: true
container_type: docker
is_root: true
has_systemd: false
has_sudo: false              # root already, sudo not installed
has_snap: false
writable_paths: ["/tmp", "/root", "/usr/local"]
```

**What changes in resolution:**
```
trivy recipe:
  ○ snap install trivy       — disabled: "No snap in container"
  ○ apt install trivy        — disabled: "No trivy apt package"
  ● bash-curl installer      — available (downloads binary)
  
  sudo handling: SKIPPED (already root)
  service management: SKIPPED (no systemd)
```

**Resolved plan:**
```
Step 1: [packages] apt-get update && apt-get install -y wget     (root, no sudo)
Step 2: [tool]     wget + install trivy binary to /usr/local/bin
Step 3: [verify]   trivy version
```

---

### I2.2 — Docker-in-Docker (privileged)

**Context:**
- Docker container with `--privileged` flag
- Docker socket mounted (`-v /var/run/docker.sock`)
- User wants Docker CLI inside container

**Detection:**
```
in_container: true
docker_socket: /var/run/docker.sock exists
docker_cli: not installed
privileged: true
```

**What changes:**
```
Docker install:
  ● Install docker-cli only (no daemon needed)
    → apt-get install -y docker.io    OR
    → download docker CLI binary
  
  Skip: dockerd, systemctl start/enable, daemon.json config
  Reason: Using host's Docker daemon via mounted socket
```

---

### I2.3 — Rootless container (non-root user)

**Context:**
- Container running as non-root user (UID 1000)
- No sudo available
- /usr/local/bin not writable

**Detection:**
```
in_container: true
is_root: false
has_sudo: false
writable_paths: ["/home/user", "/tmp"]
```

**What changes:**
```
All tools MUST install to user paths:
  pip: pip install --user PKG
  npm: npm install -g PKG (with prefix ~/.npm-global)
  binary: install to ~/.local/bin
  cargo: install to ~/.cargo/bin (default)
  
  System packages (apt): ❌ NOT AVAILABLE
    → "Cannot install system packages without root access"
    → Suggest: rebuild container image with required packages
```

---

## Scenario 3: Remote SSH Install

### I3.1 — devops-cp running locally, managing remote host

**Context:**
- devops-cp admin panel on local machine
- User wants to install tools on remote server via SSH
- Remote: Debian 12, SSH accessible

**Architecture:**
```
┌─ Local (browser) ──────┐     SSH     ┌─ Remote Server ────────┐
│                         │  ────────>  │                         │
│ Admin Panel             │             │ target host             │
│ POST /audit/install     │             │ apt install docker-ce   │
│                         │             │                         │
└─────────────────────────┘             └─────────────────────────┘
```

**How it works:**
```python
# Remote execution wraps commands in SSH
def _run_subprocess_remote(cmd, *, host, ssh_key, **kwargs):
    ssh_cmd = [
        "ssh", "-i", ssh_key,
        "-o", "StrictHostKeyChecking=accept-new",
        host,
        "--",
    ] + cmd
    return _run_subprocess(ssh_cmd, **kwargs)
```

**Challenges:**
```
- sudo password: must be piped through SSH stdin
- Environment: remote PATH may differ
- Detection: must run detect on REMOTE host
- Timeout: SSH connection adds latency
- File transfer: config files must be scp'd, not written via tee
```

**Plan modification:**
```
All steps get wrapped:
  Local:  ["apt-get", "install", "-y", "docker-ce"]
  Remote: ["ssh", "user@host", "--", "apt-get", "install", "-y", "docker-ce"]
  
Config writes:
  Local:  tee /etc/docker/daemon.json
  Remote: scp local_file user@host:/etc/docker/daemon.json
```

**Current scope:** Phase 2-8 handles LOCAL only. Remote SSH
is a FUTURE extension. The architecture supports it because
_run_subprocess() is the single execution point — wrapping
it with SSH is a non-breaking change.

---

### I3.2 — devops-cp running ON the remote host

**Context:**
- devops-cp deployed on a server
- User accesses admin panel via browser over network
- All installs happen on the server itself

**How it works:** Identical to local install — no SSH needed.
The admin panel IS running on the target host. This is the
default deployment model.

---

## Scenario 4: CI/CD Pipeline Install

### I4.1 — GitHub Actions

**Context:**
- Ubuntu runner (ubuntu-latest)
- Root access, no password needed
- Pre-installed: docker, git, node, python, go
- User wants CI to install trivy + run audit

```yaml
# .github/workflows/audit.yml
- name: Install trivy
  run: |
    curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sudo sh -s -- -b /usr/local/bin
    trivy --version
```

**What changes for CI:**
```
- sudo: passwordless (NOPASSWD in CI runner)
- Interactive: NONE (no choice modal, no password prompt)
- Detection: pre-detect what's already installed
- Recipe selection: auto (no choices, use defaults)
- Timeout: extended (CI runners are slow)
- Verification: always run (can't assume)
```

**CI mode in devops-cp:**
```python
def install_tool_ci(tool: str) -> dict:
    """Non-interactive install for CI environments.
    
    - No choices (use defaults)
    - No sudo password (assumes passwordless)
    - No UI (return JSON result)
    """
    profile = get_system_profile()
    plan = resolve_install_plan(tool, profile)
    return execute_plan(plan, sudo_password="")
```

---

### I4.2 — GitLab CI with Docker executor

**Context:**
- GitLab CI, Docker executor
- Running in container as root
- No persistent filesystem between jobs

```yaml
# .gitlab-ci.yml
audit:
  image: ubuntu:22.04
  before_script:
    - apt-get update && apt-get install -y python3 python3-pip
    - pip install devops-cp
  script:
    - devops-cp install trivy --non-interactive
    - devops-cp audit run trivy
```

**What changes:**
```
- in_container: true
- is_root: true
- No persistence: tool installed every run
- Optimization: use Docker image with tools pre-installed
  → devops-cp can generate a Dockerfile with all tools baked in
```

---

### I4.3 — Jenkins on bare metal

**Context:**
- Jenkins agent on Debian 11
- Jenkins user has sudo (passwordless for specific commands)
- Persistent filesystem

**What changes:**
```
- Non-interactive: same as CI mode
- Sudo: passwordless (NOPASSWD configured for jenkins user)
- Persistent: tools persist between builds (only install if missing)
- Lock contention: multiple Jenkins jobs may try to install simultaneously
  → Use file lock (/tmp/devops-cp-install.lock) to serialize
```

---

## Scenario 5: Kubernetes Pod

### I5.1 — Init container for tool setup

**Context:**
- K8s pod with init container
- Init container runs devops-cp to install tools
- Main container uses the tools via shared volume

```yaml
initContainers:
  - name: tool-setup
    image: ubuntu:22.04
    command: ["sh", "-c", "pip install devops-cp && devops-cp install trivy --prefix /tools"]
    volumeMounts:
      - name: tools
        mountPath: /tools

containers:
  - name: app
    volumeMounts:
      - name: tools
        mountPath: /usr/local/bin
```

**What changes:**
```
- Install prefix: /tools (shared volume, not system paths)
- No services: no systemd in container
- No persistence: pod restart = reinstall
- Optimization: bake tools into container image
```

---

### I5.2 — Sidecar pattern

**Context:**
- devops-cp runs as sidecar container
- Manages tool lifecycle for the main container
- Shared process namespace

```
Not recommended for tool install — sidecar is for monitoring/proxy.
Tool install is a build-time concern, not runtime.
Recommendation: Use proper container image with tools baked in.
```

---

## Scenario 6: Vagrant / VM Provisioning

### I6.1 — Vagrantfile provisioner

**Context:**
- Vagrant VM, Ubuntu 22.04
- Shell provisioner runs on `vagrant up`

```ruby
Vagrant.configure("2") do |config|
  config.vm.provision "shell", inline: <<-SHELL
    pip install devops-cp
    devops-cp install docker kubectl helm --non-interactive
  SHELL
end
```

**What changes:**
```
- Full Linux environment (no container limitations)
- Root access (vagrant provisioner runs as root)
- Non-interactive: no UI
- Idempotent: vagrant provision may run multiple times
  → All install steps must be idempotent (skip if installed)
```

---

## Scenario 7: Multi-Architecture

### I7.1 — ARM64 (Raspberry Pi / Apple Silicon VM)

**Context:**
- Ubuntu 24.04 on ARM64 (Raspberry Pi 5 or UTM on Mac)
- Some tools don't have ARM64 binaries

**Detection:**
```
cpu_arch: aarch64
```

**What changes:**
```
Binary downloads must use correct arch:
  x86_64: hugo_0.128.0_linux-amd64.tar.gz
  aarch64: hugo_0.128.0_linux-arm64.tar.gz
  
Disabled options:
  Some tools have NO ARM64 binary:
  ○ terraform (older versions)  — disabled: "No ARM64 binary for 1.5.x"
    → Use 1.6+ which has ARM64 support
  
Architecture in recipe:
  "hugo": {
      "binary_download": {
          "x86_64": "https://...linux-amd64.tar.gz",
          "aarch64": "https://...linux-arm64.tar.gz",
      },
  }
```

---

### I7.2 — Mixed architecture cluster

**Context:**
- K8s cluster with x86_64 and ARM64 nodes
- devops-cp manages tools per-node

**What changes:**
```
- Detection runs on EACH node
- Plans resolve per-architecture
- Same tool may have different install methods per arch
- Binary URLs are architecture-dependent
```

---

## Scenario 8: Nested Virtualization

### I8.1 — Container inside WSL2 inside Windows

```
Windows 11 → WSL2 (Ubuntu) → Docker → Ubuntu container
```

**Detection chain:**
```
in_container: true
in_wsl: false         # Container doesn't see WSL
container_type: docker
is_root: true/false   # depends on container
has_systemd: false    # container typically doesn't
```

**Behavior:** Identical to I2.1 (Docker container). The WSL2
layer is invisible from inside the container. The system only
sees the innermost environment.

---

### I8.2 — VM inside VM (nested)

```
Host → VMware → Ubuntu VM → KVM → Ubuntu VM
```

**Detection:** Each layer looks like a normal Linux host.
The system doesn't need to detect nesting depth. It only
cares about the current environment's capabilities.

---

## Interop Pattern Summary

| Environment | sudo | systemd | snap | docker | services | notes |
|-------------|------|---------|------|--------|----------|-------|
| Bare metal | ✅ | ✅ | ✅ | ✅ | ✅ | Full capabilities |
| WSL2 (systemd) | ✅ | ✅ | ✅ | via Desktop | ✅ | Near-native |
| WSL1 | ✅ | ❌ | ❌ | ❌ | ❌ | Limited |
| Docker (root) | N/A | ❌ | ❌ | via socket | ❌ | No services |
| Docker (non-root) | ❌ | ❌ | ❌ | ❌ | ❌ | User paths only |
| CI (GitHub) | ✅ (no pw) | ✅ | ✅ | ✅ | ✅ | Non-interactive |
| CI (Docker exec) | N/A | ❌ | ❌ | ❌ | ❌ | Ephemeral |
| K8s pod | N/A | ❌ | ❌ | ❌ | ❌ | Build-time concern |
| Vagrant VM | ✅ (root) | ✅ | ✅ | ✅ | ✅ | Full capabilities |
| ARM64 | ✅ | ✅ | ✅ | ✅ | ✅ | Arch-gated binaries |

### Adaptation rules

```
1. in_container=true  → skip service management, skip snap
2. is_root=true       → skip sudo wrapping
3. has_systemd=false  → skip systemctl, use alternatives
4. has_snap=false     → disable snap options
5. cpu_arch!=x86_64   → use arch-specific binary URLs
6. in_wsl=true        → check Docker Desktop integration
7. CI mode            → non-interactive, use defaults, no password
```

---

## Traceability

| Topic | Source |
|-------|--------|
| WSL detection | domain-containers §WSL |
| Container detection | domain-containers §container type |
| Docker socket detection | domain-containers §Docker-in-Docker |
| Service management skip | Phase 8 §init system detection |
| Architecture detection | Phase 6 §cpu_arch |
| sudo skip for root | Phase 2.4 §sudo handling |
| Non-interactive mode | Phase 4 §auto_resolve |
| Binary arch URLs | Phase 2.2 §binary download recipes |
| Snap availability | domain-package-managers §snap |
| Air-gapped alternatives | domain-network §air-gapped |
