# Domain: Containers

> This document catalogs every container environment the tool install
> system may encounter, how each is detected, what limitations it
> imposes, and what the recipes and resolver must account for.
>
> SOURCE CODE: l0_detection.py `_detect_container()` (implemented)
> SOURCE DOCS: phase1 §3.4, phase2.2 §docker analysis,
>              phase2.3 §6 (condition eval), scenarios S29-S33,
>              scope-expansion §2.7 (sandboxed/restricted)

---

## Detection

Container detection is a FAST TIER operation (< 2ms).
Implemented in `_detect_container()`:

```python
"container": {
    "in_container": bool,    # any container signal detected
    "runtime": str | None,   # "docker" | "containerd" | "podman" | None
    "in_k8s": bool,          # running inside a Kubernetes pod
    "read_only_rootfs": bool, # /tmp write probe failed (read-only root)
    "ephemeral_warning": str | None,  # warning text for K8s pods
}
```

### Detection methods (in order)

| Method | Signal | Sets |
|--------|--------|------|
| 1. `/.dockerenv` file exists | Docker created this file | `in_container=True`, `runtime="docker"` |
| 2. `/proc/1/cgroup` contains "docker" | Docker's cgroup namespace | `in_container=True`, `runtime="docker"` |
| 3. `/proc/1/cgroup` contains "kubepods" | Kubernetes pod cgroup | `in_container=True`, `runtime="containerd"`, `in_k8s=True` |
| 4. `/proc/1/cgroup` contains "containerd" | containerd runtime | `in_container=True`, `runtime="containerd"` |
| 5. `/proc/1/environ` contains "container=" | systemd-nspawn, LXC | `in_container=True` |
| 6. `KUBERNETES_SERVICE_HOST` env var | K8s injects this | `in_k8s=True`, `in_container=True` |

**Detection flow:**
```
Check /.dockerenv → yes? docker
  ↓ no
Read /proc/1/cgroup → "docker"? docker
                     → "kubepods"? containerd + k8s
                     → "containerd"? containerd
  ↓ no match
Read /proc/1/environ → "container="? something
  ↓ no
Check $KUBERNETES_SERVICE_HOST → set? k8s
  ↓ no
Not a container.
```

### Runtime identification

| Runtime | How detected | Common base images |
|---------|-------------|-------------------|
| Docker | `/.dockerenv` or "docker" in cgroup | ubuntu, debian, alpine, fedora, node, python |
| containerd | "containerd" in cgroup | K8s pods, managed K8s, AWS ECS with containerd |
| Podman | "container=" in environ, no /.dockerenv | Same images as Docker, rootless containers |
| LXC/LXD | "container=lxc" in environ | ubuntu, debian (full system containers) |
| systemd-nspawn | "container=systemd-nspawn" in environ | Full distro images |

**Podman detection gap:** Podman doesn't create `/.dockerenv` and
may not show up in cgroups the same way. It DOES set the `container=`
environment variable. Detection works but `runtime` may be `None`
instead of `"podman"`.

**Future enhancement:** Check for `$container` env var value to
identify podman vs LXC vs nspawn. Not implemented in Phase 1.

---

## Container Limitations

### What changes inside containers

| Capability | Host | Docker | K8s Pod | Podman (rootless) |
|-----------|------|--------|---------|-------------------|
| systemd | ✅ | ❌ (usually) | ❌ | ❌ |
| sudo | ✅ | ⚠️ (often root) | ⚠️ (often root) | ❌ (rootless) |
| Package install | ✅ | ✅ (as root) | ✅ (as root) | ⚠️ |
| Service start/enable | ✅ | ❌ | ❌ | ❌ |
| Kernel modules | ✅ | ❌ | ❌ | ❌ |
| /proc, /sys writes | ✅ | ❌ (read-only) | ❌ (read-only) | ❌ |
| User management | ✅ | ⚠️ | ⚠️ | ❌ |
| Network (outbound) | ✅ | ✅ | ✅ | ✅ |
| Filesystem (writable) | ✅ | ✅ | ⚠️ (read-only layers) | ✅ |
| pip/npm/cargo install | ✅ | ✅ | ✅ | ✅ |

### No systemd

The most impactful limitation. Containers typically use PID 1 as the
application process, not systemd.

**Detection:** `capabilities.has_systemd == False`

**Impact on recipes:**
- All `condition: "has_systemd"` post-install steps are EXCLUDED
- Docker daemon can't be started/enabled via systemctl
- No journal logging (journald)
- No timer units (systemd timers)
- No socket activation

**Resolver behavior (existing, Phase 2.3 §6):**
```python
_evaluate_condition("has_systemd", profile)  # → False in containers
# → post-install step excluded from plan
```

**Exceptions:**
- WSL2 with `[boot] systemd=true` in `/etc/wsl.conf` → HAS systemd
- Docker with `--privileged` + systemd as PID 1 → HAS systemd
- LXC/LXD full system containers → often HAS systemd

### Running as root

Most Docker images default to root. This is actually HELPFUL for
package installation (no sudo needed) but BAD for security.

**Detection:** `capabilities.is_root == True`

**Impact on recipes:**
- `needs_sudo: True` steps don't need `sudo` prefix — execution
  layer strips it when running as root
- `condition: "not_root"` steps are EXCLUDED (e.g., usermod group-add)
- Plan still sets `needs_sudo: True` for the step (resolver doesn't
  know about root stripping); the executor handles it

### No sudo available

Containers without sudo installed, and not running as root (e.g.,
non-root user in a Dockerfile with `USER appuser`).

**Detection:** `capabilities.has_sudo == False` AND `is_root == False`

**Impact on recipes:**
- System package installs (apt/dnf/apk) will FAIL
- pip/npm/cargo installs to user space still work
- Plan adds warning: "This plan requires sudo but sudo is not available"

### Read-only filesystem layers

Some K8s pods and Docker containers have read-only root filesystems.
`/usr/local/bin`, `/etc/`, `/usr/lib/` may be read-only.

**Detection:** `container.read_only_rootfs == True` — detected via
a write probe to `/tmp/.dcp_ro_probe`. If the probe fails, the root
filesystem is considered read-only.

**Impact on recipes:**
- Binary downloads to `/usr/local/bin` fail
- Config file writes fail
- Package installs may fail if package manager dirs are read-only

**Workaround:** Install to writable paths (`~/.local/bin`, `/tmp`).
This requires recipe variants that support user-space installation.

### No kernel access

Containers share the host kernel. Kernel modules, kernel config,
IOMMU groups, and GPU hardware are host-level concerns.

**Impact on recipes:**
- `requires.kernel_config` can't be checked or modified
- `requires.hardware` (GPU) detection may partially work
  (nvidia-smi inside NVIDIA Docker containers)
- Kernel recompilation is impossible
- Module loading (modprobe) is impossible

**Detection:** `container.in_container == True` → disable all
kernel-related recipe options with:
```python
{"available": False,
 "disabled_reason": "Running inside a container — kernel access not available",
 "enable_hint": "Run this on the host system instead"}
```

---

## Container Scenarios (Traces from Phase 2.3)

### Docker container, Debian-based, root (S30)

```
Profile: family=debian, pm=apt, root=yes, systemd=no, container=yes

Installing git:
  Method: apt (batchable)
  Plan: pkg(git) → verify(git --version)
  Sudo: plan says True, executor strips sudo (root)
  Post-install: none (git has none)
  Steps: 2
```

### Alpine container, root (S31)

```
Profile: family=alpine, pm=apk, root=yes, systemd=no, container=yes

Installing curl:
  Method: apk (batchable)
  Plan: pkg(curl) → verify(curl --version)
  Sudo: plan says True, executor strips sudo (root)
  Steps: 2

Alpine specifics: musl libc, ash shell, minimal base
```

### Fedora container, deep dependency chain (S32)

```
Profile: family=rhel, pm=dnf, root=yes, systemd=no, container=yes

Installing cargo-audit:
  Dep chain: cargo-audit → cargo → curl (already installed in Fedora base)
  System packages (RHEL names): pkgconf-pkg-config, openssl-devel
  
  Plan: pkg(pkgconf-pkg-config, openssl-devel)
      → tool(rustup)
      → tool(cargo install cargo-audit) [env-wrapped]
      → verify
  Steps: 4
  
  Key: RHEL package names used, not Debian names.
  family="rhel" → requires.packages["rhel"] selected.
```

### Docker-in-Docker (S33)

```
Profile: family=debian, pm=apt, root=yes, systemd=no, container=yes

Installing docker:
  Method: apt (batchable, docker.io)
  Post-install:
    "has_systemd" → False → EXCLUDE systemctl start
    "has_systemd" → False → EXCLUDE systemctl enable
    "not_root" → False → EXCLUDE usermod group-add
  
  Plan: pkg(docker.io) → verify(docker --version)
  Steps: 2

  WARNING: Install succeeds but docker daemon won't run.
  Docker-in-Docker requires either:
  - Mount host's /var/run/docker.sock → use host's Docker daemon
  - Run with --privileged + start dockerd manually
  - Use dind (docker-in-docker) sidecar container

  verify(docker --version) passes (binary exists).
  verify(docker info) would fail (no daemon).
  Our verify uses --version (Phase 2).
```

### Docker in container, root (S29)

```
Profile: pm=apt, root=yes, systemd=no, in_container=yes

Same outcome as S33. All post-install excluded.
Plan has 2 steps. Functionally limited.
```

---

## Kubernetes Pod Specifics

### Detection

Two signals that indicate K8s:
1. `/proc/1/cgroup` contains "kubepods"
2. `KUBERNETES_SERVICE_HOST` env var is set

Both set `in_k8s = True`. Either alone is sufficient.

### K8s-specific limitations

| Concern | Impact |
|---------|--------|
| Pod lifecycle | Pods are ephemeral — installed tools lost on restart |
| Resource limits | CPU/memory limits may cause builds to OOM-kill |
| Network policies | Outbound to pypi.org, registry.npmjs.org may be blocked |
| Service accounts | K8s RBAC may limit what the pod can do |
| Init containers | Install could run as init container instead |
| Sidecar pattern | Some tools (docker) need sidecar containers |

### What the resolver should do for K8s

**Phase 2:** No special handling. Container detection + condition
evaluation already excludes systemd/group-add steps.

**Future phases:**
- Warn that installs are ephemeral (lost on pod restart)
- Suggest baking tools into the container image instead
- Detect network policies that block package downloads
- Offer Dockerfile snippet as alternative to runtime install

---

## Condition Reference

These are the conditions defined in Phase 2.3 that interact with
container environments:

| Condition | Evaluates to | In typical container |
|-----------|-------------|---------------------|
| `"has_systemd"` | `capabilities.has_systemd` | `False` |
| `"not_root"` | `not capabilities.is_root` | `False` (root) |
| `"not_container"` | `not container.in_container` | `False` |
| `None` | `True` (always) | `True` |

### Condition combos by environment

| Environment | has_systemd | not_root | not_container |
|------------|-------------|----------|---------------|
| Ubuntu desktop | True | True | True |
| Ubuntu server | True | depends | True |
| WSL2 (no systemd) | False | True | True |
| WSL2 (systemd=true) | True | True | True |
| Docker (root) | False | False | False |
| Docker (non-root) | False | True | False |
| K8s pod (root) | False | False | False |
| Alpine container | False | False* | False |

*Alpine containers almost always run as root.

---

## Common Container Base Images

These are the environments the system will encounter most often:

| Image | Family | PM | Root | musl | systemd |
|-------|--------|-----|------|------|---------|
| `ubuntu:22.04` | debian | apt | yes | no | no |
| `debian:bookworm` | debian | apt | yes | no | no |
| `alpine:3.19` | alpine | apk | yes | yes | no |
| `fedora:39` | rhel | dnf | yes | no | no |
| `python:3.12` | debian | apt | yes | no | no |
| `node:20` | debian | apt | yes | no | no |
| `golang:1.22` | debian | apt | yes | no | no |
| `rust:1.75` | debian | apt | yes | no | no |
| `amazonlinux:2023` | rhel | dnf | yes | no | no |

**Note:** Most popular base images are Debian-based. The `python:`,
`node:`, `golang:`, and `rust:` images all use Debian as their base.
Alpine variants exist (`python:3.12-alpine`) but are less common
due to musl compatibility issues.

---

## What Works Everywhere (Container-safe Operations)

These operations work reliably inside any container:

| Operation | Why it works |
|-----------|-------------|
| `pip install` (in venv) | Python venv is user-space |
| `npm install -g` | npm global dir is writable |
| `cargo install` | Installs to `~/.cargo/bin` |
| `apt-get install` (as root) | Package manager works normally |
| `apk add` (as root) | Package manager works normally |
| `shutil.which()` | PATH lookup works normally |
| Binary download to user dir | Writable user space |
| `--version` verify | Non-destructive, no daemon needed |

These do NOT work in typical containers:

| Operation | Why it fails |
|-----------|-------------|
| `systemctl start X` | No systemd |
| `systemctl enable X` | No systemd |
| `modprobe X` | No kernel access |
| `usermod -aG` | May work but pointless (ephemeral) |
| `update-grub` | No bootloader |
| Write to `/boot/` | Usually read-only |
| GPU driver install | Needs host kernel |

---

## Traceability

| Topic | Source |
|-------|--------|
| Detection code | l0_detection.py `_detect_container()` (lines 135-179) |
| Container detection spec | phase1 §3.4 (done) |
| Condition evaluation | phase2.3 §6 (designed) |
| Container scenarios | phase2.3-scenarios S29-S33, S34-S38 |
| Docker post-install analysis | phase2.2 §docker analysis |
| Sandboxed environments | scope-expansion §2.7 |
| Docker-in-Docker warnings | phase2.3-scenarios S33 |
