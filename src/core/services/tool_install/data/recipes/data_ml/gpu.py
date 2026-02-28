"""
L0 Data — GPU driver & toolkit recipes.

Categories: gpu
Pure data, no logic.
"""

from __future__ import annotations


_GPU_RECIPES: dict[str, dict] = {
    #
    # Spec: Phase 6 §Driver option matrix, domain-gpu.
    # Risk: HIGH — kernel modules, DKMS, possible reboot.

    "nvidia-driver": {
        "label": "NVIDIA Driver",
        "cli": "nvidia-smi",
        "category": "gpu",
        "risk": "high",
        "install": {
            "apt": ["apt-get", "install", "-y", "nvidia-driver-535"],
            "dnf": ["dnf", "install", "-y", "nvidia-gpu-firmware",
                    "akmod-nvidia"],
        },
        "needs_sudo": {"apt": True, "dnf": True},
        "repo_setup": {
            "apt": [
                {
                    "label": "Add NVIDIA PPA",
                    "command": ["add-apt-repository", "-y",
                                "ppa:graphics-drivers/ppa"],
                    "needs_sudo": True,
                },
                {
                    "label": "Update package lists",
                    "command": ["apt-get", "update"],
                    "needs_sudo": True,
                },
            ],
        },
        "requires": {
            "hardware": {"gpu_vendor": "nvidia"},
            "packages": {
                "debian": ["linux-headers-generic", "dkms"],
                "rhel":   ["kernel-devel", "kernel-headers"],
            },
        },
        "post_install": [
            {
                "label": "Load NVIDIA kernel module",
                "command": ["modprobe", "nvidia"],
                "needs_sudo": True,
            },
        ],
        "verify": ["nvidia-smi"],
        "rollback": {
            "apt": ["apt-get", "purge", "-y", "nvidia-driver-535"],
            "post": ["modprobe", "nouveau"],
        },
        "restart_required": "system",
    },
    "cuda-toolkit": {
        "label": "CUDA Toolkit",
        "cli": "nvcc",
        "category": "gpu",
        "risk": "high",
        "install": {
            "apt": ["apt-get", "install", "-y", "nvidia-cuda-toolkit"],
            "dnf": ["dnf", "install", "-y", "cuda-toolkit"],
        },
        "needs_sudo": {"apt": True, "dnf": True},
        "requires": {
            "hardware": {"gpu_vendor": "nvidia"},
            "binaries": ["nvidia-smi"],
        },
        "post_install": [
            {
                "label": "Set CUDA environment paths",
                "command": [
                    "bash", "-c",
                    'echo "export PATH=/usr/local/cuda/bin:$PATH" '
                    '>> /etc/profile.d/cuda.sh && '
                    'echo "/usr/local/cuda/lib64" > '
                    "/etc/ld.so.conf.d/cuda.conf && ldconfig",
                ],
                "needs_sudo": True,
            },
        ],
        "verify": ["nvcc", "--version"],
    },
    "vfio-passthrough": {
        "type": "data_pack",
        "label": "VFIO GPU Passthrough",
        "category": "gpu",
        "risk": "high",
        "install": {
            # No package install — kernel modules are built-in or via DKMS
        },
        "needs_sudo": {"_default": True},
        "requires": {
            "hardware": {"gpu.has_gpu": True},
        },
        "steps": [
            {
                "id": "vfio-modules",
                "type": "config",
                "label": "Enable VFIO kernel modules",
                "action": "ensure_line",
                "file": "/etc/modules-load.d/vfio.conf",
                "lines": [
                    "vfio",
                    "vfio_iommu_type1",
                    "vfio_pci",
                    "vfio_virqfd",
                ],
                "needs_sudo": True,
                "risk": "high",
                "backup_before": ["/etc/modules-load.d/vfio.conf"],
            },
            {
                "id": "iommu-grub",
                "type": "config",
                "label": "Enable IOMMU in boot parameters",
                "action": "ensure_line",
                "file": "/etc/default/grub",
                "content": 'GRUB_CMDLINE_LINUX_DEFAULT="quiet splash intel_iommu=on iommu=pt"',
                "needs_sudo": True,
                "risk": "high",
                "backup_before": ["/etc/default/grub"],
                "depends_on": ["vfio-modules"],
            },
            {
                "id": "update-grub",
                "type": "post_install",
                "label": "Update GRUB configuration",
                "command": ["update-grub"],
                "needs_sudo": True,
                "depends_on": ["iommu-grub"],
            },
            {
                "id": "load-vfio",
                "type": "post_install",
                "label": "Load VFIO modules",
                "command": ["modprobe", "vfio-pci"],
                "needs_sudo": True,
                "depends_on": ["vfio-modules"],
            },
        ],
        "verify": ["lsmod | grep vfio"],
        "rollback": {
            "remove_files": ["/etc/modules-load.d/vfio.conf"],
            "post": ["update-grub"],
        },
        "restart_required": "system",
    },
    "rocm": {
        "label": "AMD ROCm",
        "cli": "rocminfo",
        "category": "gpu",
        "risk": "high",
        "install": {
            "apt": [
                "bash", "-c",
                "wget https://repo.radeon.com/amdgpu-install/latest/"
                "ubuntu/jammy/amdgpu-install_6.0_all.deb && "
                "dpkg -i amdgpu-install_6.0_all.deb && "
                "amdgpu-install --usecase=rocm --no-dkms -y",
            ],
            "dnf": ["dnf", "install", "-y", "rocm-dev"],
        },
        "needs_sudo": {"apt": True, "dnf": True},
        "requires": {
            "hardware": {"gpu_vendor": "amd"},
            "platforms": ["debian", "rhel"],
        },
        "post_install": [
            {
                "label": "Add user to render and video groups",
                "command": [
                    "bash", "-c",
                    "usermod -aG render,video $USER",
                ],
                "needs_sudo": True,
            },
        ],
        "verify": ["rocminfo"],
        "remove": {
            "apt": ["amdgpu-install", "--uninstall"],
            "dnf": ["dnf", "remove", "-y", "rocm-dev"],
        },
        "rollback": {
            "apt": ["amdgpu-install", "--uninstall"],
            "post": ["modprobe", "amdgpu"],
        },
        "restart_required": "session",
    },
}
