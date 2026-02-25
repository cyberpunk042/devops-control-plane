# Domain: Kernel

> This document catalogs kernel operations relevant to the tool
> install system: kernel config detection, module loading (modprobe),
> kernel recompilation, bootloader updates, WSL kernel customization.
> Covers risk levels, rollback, and safeguards.
>
> SOURCE DOCS: scope-expansion §2.5 (kernel recompilation/modules),
>              arch-system-model §Kernel state (Phase 6 schema),
>              arch-system-model §WSL interop (Phase 6),
>              scope-expansion §2.8 (restart requirements)

---

## Overview

Kernel operations are the HIGHEST RISK actions in the tool install
system. A failed kernel modification can make the system unbootable.

### Why kernel matters for tool installation

| Scenario | Kernel involvement |
|----------|-------------------|
| GPU passthrough (VFIO) | Load/enable vfio-pci module |
| Container runtimes | Enable cgroups v2 |
| Filesystems | Enable btrfs, zfs modules |
| Network tools | Enable wireguard module |
| NVIDIA driver | dkms builds kernel module against current kernel |

### Phase 2 vs Phase 6

| Phase | Kernel capability |
|-------|------------------|
| Phase 2 | No kernel operations. None of the 30 tools require kernel changes. |
| Phase 6 | Module loading, config detection, recompilation with safeguards. |

---

## Kernel Config Detection

### Where the config lives

| Location | When present |
|----------|-------------|
| `/boot/config-$(uname -r)` | Most distros (Debian, RHEL, SUSE) |
| `/proc/config.gz` | If `CONFIG_IKCONFIG_PROC=y` (Alpine, Arch) |
| Not available | Some minimal containers, WSL |

### Reading config values

```bash
# Direct read
grep CONFIG_VFIO_PCI /boot/config-$(uname -r)
# CONFIG_VFIO_PCI=m     ← compiled as module
# CONFIG_VFIO_PCI=y     ← built into kernel
# # CONFIG_VFIO_PCI is not set  ← disabled

# From /proc/config.gz
zcat /proc/config.gz | grep CONFIG_VFIO_PCI
```

### Config states

| State | Meaning | Impact |
|-------|---------|--------|
| `=y` | Built-in (compiled into kernel) | Always active, no modprobe needed |
| `=m` | Module (compiled separately) | Load with `modprobe`, file in `/lib/modules/` |
| `is not set` / `=n` | Disabled | Not available. Needs kernel recompilation to enable. |
| Not found | Config not readable | Cannot determine state |

### System profile schema (Phase 6)

```python
"kernel": {
    "version": str,              # uname -r
    "config_available": bool,    # /boot/config-$(uname -r) exists
    "config_path": str | None,   # path to kernel config file
    "loaded_modules": list[str], # from lsmod (module names only)
    "module_check": {            # specific modules checked on demand
        "vfio_pci": {
            "loaded": bool,      # in loaded_modules
            "compiled": bool,    # .ko file exists in /lib/modules/
            "config_state": str | None,  # "y", "m", "n", None
        },
    },
    "iommu_groups": list[dict] | None,  # from /sys/kernel/iommu_groups/
}
```

### Detection commands

```bash
# Kernel version
uname -r
# 6.5.0-44-generic

# Loaded modules
lsmod
# Module                  Size  Used by
# nvidia               2568192  0
# vfio_pci               16384  0

# Check if specific module is compiled (available to load)
find /lib/modules/$(uname -r) -name "vfio-pci.ko*"
# /lib/modules/6.5.0-44-generic/kernel/drivers/vfio/pci/vfio-pci.ko

# Config state for specific option
grep CONFIG_VFIO_PCI /boot/config-$(uname -r)
# CONFIG_VFIO_PCI=m

# IOMMU groups
ls /sys/kernel/iommu_groups/*/devices/
```

---

## Module Loading (Low Risk)

Loading a pre-compiled kernel module is the SAFEST kernel
operation. The module already exists; we just activate it.

### How it works

```
1. Check: is module compiled? (find /lib/modules/.../*.ko)
2. Load: sudo modprobe MODULE_NAME
3. Verify: lsmod | grep MODULE_NAME
4. Persist: /etc/modules-load.d/MODULE.conf
```

### Commands

```bash
# Load module immediately
sudo modprobe vfio-pci

# Verify it's loaded
lsmod | grep vfio_pci

# Persist across reboots
echo "vfio-pci" | sudo tee /etc/modules-load.d/vfio.conf

# Unload module (if needed)
sudo modprobe -r vfio-pci
```

### Persistence locations

| Platform | Persistence file |
|----------|-----------------|
| Debian/Ubuntu | `/etc/modules-load.d/MODULE.conf` |
| RHEL/Fedora | `/etc/modules-load.d/MODULE.conf` |
| Arch | `/etc/modules-load.d/MODULE.conf` |
| Alpine | `/etc/modules` (single file, one per line) |
| SUSE | `/etc/modules-load.d/MODULE.conf` |

### Recipe format

```python
"vfio_pci_modprobe": {
    "steps": [
        {"label": "Load vfio-pci module",
         "command": ["modprobe", "vfio-pci"],
         "needs_sudo": True,
         "risk": "low"},
        {"label": "Persist module on boot",
         "command": ["bash", "-c",
                     "echo vfio-pci >> /etc/modules-load.d/vfio.conf"],
         "needs_sudo": True,
         "risk": "low"},
    ],
}
```

### Failure modes

| Failure | Cause | Recovery |
|---------|-------|----------|
| `Module not found` | Not compiled for this kernel | Need DKMS or kernel recompilation |
| `Operation not permitted` | No sudo | Run with sudo |
| `Unknown symbol` | Module version mismatch | Rebuild module for current kernel |

---

## DKMS (Dynamic Kernel Module Support)

### What it is

DKMS automatically rebuilds kernel modules when the kernel is
updated. Critical for out-of-tree modules like NVIDIA drivers.

### How it works

```
1. Source code stored in /usr/src/MODULE-VERSION/
2. DKMS config: /usr/src/MODULE-VERSION/dkms.conf
3. On kernel update: dkms auto-rebuilds module for new kernel
4. Module installed to /lib/modules/NEW_KERNEL/updates/
```

### NVIDIA + DKMS

```bash
# NVIDIA driver uses DKMS
sudo apt-get install -y nvidia-driver-535
# dkms.conf registered as part of package install

# When kernel updates:
# apt triggers dkms rebuild → nvidia module for new kernel

# Check DKMS status
dkms status
# nvidia/535.129.03, 6.5.0-44-generic, x86_64: installed
```

### DKMS failure

If DKMS rebuild fails after kernel update:
- GPU driver won't load on new kernel
- System boots but without GPU acceleration
- Fix: `sudo dkms install nvidia/535.129.03`
- Or: rollback to old kernel via GRUB

---

## Kernel Recompilation (High Risk)

### When needed

Only when a kernel CONFIG option is set to `=n` (disabled) and
needs to be `=y` or `=m`:
- Enable VFIO when not compiled
- Enable cgroups v2 on old kernels
- Enable specific filesystem support
- Enable hardware support not in default config

### The pipeline

```
1. Install build dependencies
   └── build-essential, flex, bison, libssl-dev, libelf-dev, libncurses-dev

2. Get kernel source
   └── apt-get install linux-source OR git clone

3. Copy current config
   └── cp /boot/config-$(uname -r) .config

4. Modify config
   └── scripts/config --enable CONFIG_VFIO_PCI

5. Build kernel (LONG: 20-120 min)
   └── make -j$(nproc)

6. Install modules
   └── sudo make modules_install

7. Install kernel
   └── sudo make install

8. Update bootloader
   └── sudo update-grub (Debian)
   └── sudo grub2-mkconfig -o /boot/grub2/grub.cfg (RHEL)

9. REBOOT REQUIRED
   └── The new kernel loads on next boot
```

### Build dependency packages

| Family | Packages |
|--------|----------|
| debian | `build-essential`, `libncurses-dev`, `flex`, `bison`, `libssl-dev`, `libelf-dev`, `bc` |
| rhel | `gcc`, `make`, `ncurses-devel`, `flex`, `bison`, `openssl-devel`, `elfutils-libelf-devel`, `bc` |
| alpine | `build-base`, `ncurses-dev`, `flex`, `bison`, `openssl-dev`, `elfutils-dev`, `bc` |

### Bootloader commands

| Platform | Bootloader | Update command |
|----------|-----------|---------------|
| Debian/Ubuntu | GRUB2 | `sudo update-grub` |
| RHEL/Fedora | GRUB2 | `sudo grub2-mkconfig -o /boot/grub2/grub.cfg` |
| Arch | GRUB2 | `sudo grub-mkconfig -o /boot/grub/grub.cfg` |
| Alpine | Extlinux or GRUB | `sudo update-extlinux` or `sudo grub-mkconfig` |
| SUSE | GRUB2 | `sudo grub2-mkconfig -o /boot/grub2/grub.cfg` |
| systemd-boot | systemd-boot | `sudo bootctl update` |

### Disk space required

| Component | Size |
|-----------|------|
| Kernel source | ~1 GB |
| Build directory | ~3-5 GB |
| Installed kernel + modules | ~200-500 MB |
| Total needed | ~5-7 GB free |

---

## Risk Levels

### Risk classification

| Operation | Risk level | Why |
|-----------|-----------|-----|
| `modprobe` (load module) | **Low** | Can `modprobe -r` to unload. No reboot. Reversible. |
| `/etc/modules-load.d/` edit | **Low** | Delete file to undo. Takes effect on next boot. |
| DKMS module install | **Medium** | Builds against kernel. Failure = no module but system boots. |
| Kernel recompilation | **High** | Wrong config can make system unbootable. |
| `make install` (kernel) | **High** | Replaces boot kernel image. |
| `update-grub` | **Medium** | Updates boot menu. Wrong config = boot issues. |
| System reboot | **Medium** | Service interruption. New kernel might fail. |

### Risk in recipe format

```python
{
    "label": "Enable CONFIG_VFIO_PCI",
    "command": ["scripts/config", "--enable", "CONFIG_VFIO_PCI"],
    "risk": "high",
},
{
    "label": "Install kernel",
    "command": ["make", "install"],
    "needs_sudo": True,
    "risk": "high",
},
```

### UI treatment by risk level

| Risk | UI treatment |
|------|-------------|
| low | Normal step, green indicator |
| medium | Yellow warning icon, expanded explanation |
| high | Red warning, double-confirm dialog, rollback instructions shown |

---

## Rollback

### Boot into old kernel

The PRIMARY rollback for kernel operations:

```
1. GRUB menu appears on boot (hold Shift on Debian, or set GRUB_TIMEOUT)
2. Select "Advanced options"
3. Choose the PREVIOUS kernel version
4. System boots with old, known-good kernel
```

### Config backup

```bash
# Before modifying
cp /boot/config-$(uname -r) /boot/config.backup

# To restore
cp /boot/config.backup /boot/config-$(uname -r)
```

### Recipe rollback instructions

```python
"rollback": {
    "description": "If boot fails: select old kernel in GRUB menu, "
                   "or boot from recovery, then restore /boot/config.backup",
},
```

---

## Safeguards

The recipe system MUST enforce these for kernel operations:

### 1. Never auto-execute

```python
# Kernel steps NEVER run automatically.
# Plan shows every step. User must explicitly confirm EACH step.
"auto_execute": False,  # always False for kernel operations
```

### 2. Backup before modify

```python
# Always save current config before changing it
{"label": "Backup current config",
 "command": ["cp", "/boot/config-$(uname -r)", "/boot/config.backup"],
 "needs_sudo": True,
 "risk": "medium"},
```

### 3. Include rollback instructions

Every kernel recipe MUST include a `rollback` field explaining
how to recover from a failed boot.

### 4. Restart awareness

```python
# Steps that need reboot
{"label": "Reboot required",
 "restart_required": "system",
 "restart_message": "Reboot to load the new kernel. "
                    "If boot fails, select the old kernel in GRUB."},
```

The plan engine persists state before reboot and resumes after.

### 5. Risk tagging

Every step in a kernel recipe MUST have a `risk` field.

---

## WSL Kernel Customization

### The difference

WSL2 uses a Microsoft-provided kernel, not a distro kernel:

```bash
uname -r
# 5.15.153.1-microsoft-standard-WSL2
```

### Detection

```python
# From Phase 1 detection
is_wsl = "microsoft" in uname_r.lower()
```

### How to customize WSL kernel

```
1. Clone WSL kernel source
   └── git clone https://github.com/microsoft/WSL2-Linux-Kernel.git

2. Apply config changes
   └── Same as native: scripts/config --enable CONFIG_XXX

3. Build
   └── make -j$(nproc) KCONFIG_CONFIG=Microsoft/config-wsl

4. Copy vmlinux to Windows filesystem
   └── cp vmlinux /mnt/c/Users/USERNAME/

5. Create/edit .wslconfig on Windows
   └── [wsl2]
       kernel=C:\\Users\\USERNAME\\vmlinux

6. Restart WSL
   └── wsl.exe --shutdown (from Windows)
   └── Then reopen WSL terminal
```

### WSL kernel differences from native

| Aspect | Native Linux | WSL2 |
|--------|-------------|------|
| Kernel source | Distro's linux-source | Microsoft fork |
| Config location | `/boot/config-*` | Not in standard location |
| Bootloader | GRUB | N/A (Hyper-V loads vmlinux) |
| Reboot | `sudo reboot` | `wsl.exe --shutdown` |
| Rollback | GRUB old kernel | Delete .wslconfig kernel line |
| Module location | `/lib/modules/` | `/lib/modules/` (inside WSL) |
| `modprobe` | Works normally | Works (if module compiled) |

### WSL kernel modules that matter

| Module | Purpose | Default in WSL kernel? |
|--------|---------|----------------------|
| vfio-pci | GPU passthrough | ❌ (WSL uses GPU-PV, not VFIO) |
| wireguard | VPN | ✅ Usually compiled in |
| cgroup v2 | Containers | ✅ Usually enabled |
| nfs | Network filesystem | ⚠️ May need enabling |

---

## Common Kernel Modules for DevOps

| Module | Purpose | When needed |
|--------|---------|-------------|
| `vfio-pci` | GPU passthrough to VMs | KVM + GPU |
| `wireguard` | Modern VPN | VPN setup |
| `br_netfilter` | Bridge netfilter | Kubernetes networking |
| `overlay` | Overlay filesystem | Docker/containerd |
| `ip_vs` | IPVS load balancing | Kubernetes services |
| `nf_conntrack` | Connection tracking | Kubernetes/iptables |
| `xt_REDIRECT` | Packet redirect | Service mesh (Istio) |
| `vhost_net` | Virtio networking | KVM networking |

### Checking required modules for Docker/K8s

```bash
# Docker's check script
curl -fsSL https://raw.githubusercontent.com/moby/moby/master/contrib/check-config.sh | bash

# Manual checks
for mod in br_netfilter overlay ip_vs nf_conntrack; do
    lsmod | grep -q $mod && echo "$mod: loaded" || echo "$mod: NOT loaded"
done
```

---

## Containers and Kernel

### No kernel operations in containers

Containers share the HOST kernel. You CANNOT:
- Load kernel modules from inside a container
- Recompile the kernel inside a container
- Change kernel config from inside a container

**Detection:**
```python
if system_profile["container"]["in_container"]:
    # Skip all kernel operations
    # Show message: "Kernel operations not available in containers"
```

### Privileged containers (exception)

`docker run --privileged` CAN run `modprobe`, but this is:
- A security risk
- Affects the HOST kernel (not container)
- Not a normal use case
- Not something the recipe system should support

---

## Phase Roadmap

| Phase | Kernel capability |
|-------|------------------|
| Phase 2 | No kernel awareness. No kernel operations. |
| Phase 6 | Kernel config detection. Module state checking. modprobe with safeguards. DKMS awareness. |
| Phase 6+ | Kernel recompilation pipeline. Bootloader updates. WSL kernel customization. Full rollback support. |

---

## Traceability

| Topic | Source |
|-------|--------|
| Kernel module workflow | scope-expansion §2.5 (full tree) |
| VFIO recipe example | scope-expansion §2.5 (modprobe + recompile) |
| WSL kernel customization | scope-expansion §2.5 (WSL interop) |
| Safeguards (5 rules) | scope-expansion §2.5 (mandatory safeguards) |
| Kernel state schema | arch-system-model §Kernel state (Phase 6) |
| Kernel detection commands | arch-system-model §Detection |
| WSL interop schema | arch-system-model §WSL interop (Phase 6) |
| Restart requirements | scope-expansion §2.8 (restart_required) |
| Risk levels in UI | scope-expansion §2.5 (risk: high) |
| Build deps for kernel | domain-build-from-source §build dependencies |
| NVIDIA + DKMS | domain-gpu §NVIDIA driver installation |
