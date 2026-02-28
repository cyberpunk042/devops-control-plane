# Tool Recipe Registry

> **300 tools. 7 domain packages. Pure data, no logic.**
>
> Every installable tool, runtime, driver, data pack, and config template —
> organized by domain, not by install method. The folder structure IS the documentation.

---

## How It Works

Each leaf file exports a partial `dict[str, dict]` of tool recipes.
Domain `__init__.py` files merge their children.
The top-level `__init__.py` merges all domains into the single
canonical `TOOL_RECIPES` dict.

```python
from src.core.services.tool_install.data.recipes import TOOL_RECIPES
recipe = TOOL_RECIPES["cargo-audit"]   # flat key lookup, always
```

Every consumer does flat key lookup (`TOOL_RECIPES.get(tool_id)`).
The internal package structure is invisible to them.

---

## Package Structure

```
recipes/
├── __init__.py                  ← Composite merge → TOOL_RECIPES (300 tools)
│
├── core/                        ← Core system tools (40 tools)
│   ├── __init__.py              ← Merges: system + shell
│   ├── system.py                ← system, compression, process, backup, utility
│   └── shell.py                 ← shell, terminal
│
├── languages/                   ← Programming language ecosystems (109 tools)
│   ├── __init__.py              ← Merges all 14 language files
│   ├── python.py                ← python (pip, poetry, ruff, mypy, etc.)
│   ├── node.py                  ← node, pages (npm, eslint, prettier, hugo)
│   ├── rust.py                  ← rust, language (cargo, rustup, ripgrep, etc.)
│   ├── go.py                    ← go (golang, golangci-lint, etc.)
│   ├── jvm.py                   ← java, scala, kotlin
│   ├── ruby.py                  ← ruby (ruby, bundler, rails)
│   ├── php.py                   ← php (php, composer, laravel, phpstan)
│   ├── dotnet.py                ← dotnet (dotnet-sdk, nuget, omnisharp, ef)
│   ├── elixir.py                ← elixir (erlang, elixir, mix)
│   ├── lua.py                   ← lua (lua, luarocks, stylua)
│   ├── zig.py                   ← zig (zig, zls)
│   ├── wasm.py                  ← wasm (wasmtime, wasmer, wasm-pack)
│   ├── haskell.py               ← haskell (ghc, cabal, stack)
│   ├── ocaml.py                 ← ocaml (ocaml, opam, dune)
│   └── rlang.py                 ← rlang (r-base, rscript)
│
├── devops/                      ← DevOps & infrastructure (53 tools)
│   ├── __init__.py              ← Merges: k8s + cloud + containers + cicd + monitoring
│   ├── k8s.py                   ← k8s (kubectl, helm, k9s, kustomize, etc.)
│   ├── cloud.py                 ← cloud, iac, hashicorp (aws, gcloud, terraform, etc.)
│   ├── containers.py            ← container, virtualization (docker, podman, etc.)
│   ├── cicd.py                  ← cicd, git, scm (gh, act, dagger, git, etc.)
│   └── monitoring.py            ← monitoring (prometheus, grafana, etc.)
│
├── security/                    ← Security & crypto (16 tools)
│   ├── __init__.py              ← Merges: scanners + crypto
│   ├── scanners.py              ← security (trivy, snyk, grype, semgrep, etc.)
│   └── crypto.py                ← crypto (openssl, certbot, age, sops, step-cli)
│
├── network/                     ← Networking (17 tools)
│   ├── __init__.py              ← Merges: network + dns + proxy + service_discovery
│   ├── network.py               ← network (nmap, httpie, wget, socat, etc.)
│   ├── dns.py                   ← dns (bind-utils, dog, dnsx)
│   ├── proxy.py                 ← proxy (nginx, haproxy, traefik, envoy)
│   └── service_discovery.py     ← service_discovery (etcd, linkerd)
│
├── data_ml/                     ← Data, ML & databases (20 tools)
│   ├── __init__.py              ← Merges: ml + databases + data_packs + gpu
│   ├── ml.py                    ← ml (pytorch, tensorflow, jupyter, etc.)
│   ├── databases.py             ← database (psql, mysql, mongosh, redis, sqlite)
│   ├── data_packs.py            ← data_pack (trivy-db, geoip, wordlists, etc.)
│   └── gpu.py                   ← gpu (nvidia-driver, cuda-toolkit, rocm, vfio)
│
└── specialized/                 ← Dev tools & niche (67 tools)
    ├── __init__.py              ← Merges: devtools + media_docs + config + build_tools
    ├── devtools.py              ← devtools, editors, testing, taskrunner, profiling, formatting
    ├── media_docs.py            ← media, docs, messaging, logging, api, protobuf
    ├── config.py                ← config (config template recipes)
    └── build_tools.py           ← cpp, embedded (gcc, cmake, OpenOCD, etc.)
```

---

## Recipe Model Reference

Recipes are not scripts. They are **declarative specifications**.
The resolver reads a recipe + the system profile and produces an executable plan.
One recipe works on every supported platform — the intelligence is in the resolver.

### Field Reference

| Field | Type | Required | Purpose |
|-------|------|----------|---------|
| `label` | `str` | ✅ | Human-readable name |
| `category` | `str` | ✅ | Domain identity (determines file location) |
| `install` | `dict[method → cmd]` | ✅ | Per-method install commands |
| `needs_sudo` | `dict[method → bool]` | ✅ | Per-method sudo requirements |
| `verify` | `list[str]` | ✅ | Command to verify successful install |
| `cli` | `str` | | Binary name for detection (`which {cli}`) |
| `cli_verify_args` | `list[str]` | | Custom args for version check (instead of `--version`) |
| `requires` | `dict` | | Dependencies (see below) |
| `prefer` | `list[str]` | | Ordered PM preference (resolver tries these first) |
| `install_via` | `dict[method → str]` | | Install mechanism label (`pip`, `cargo`, `curl_pipe_bash`, etc.) |
| `arch_map` | `dict[str → str]` | | Architecture normalization for `{arch}` placeholders |
| `post_env` | `str` | | Shell export injected into subsequent steps |
| `repo_setup` | `dict[pm → list[step]]` | | Pre-install repository configuration |
| `post_install` | `list[step]` | | Post-install commands |
| `update` | `dict[method → cmd]` | | Per-method update commands |
| `rollback` | `dict` | | Undo/removal commands |
| `risk` | `str` | | `low` / `medium` / `high` — safety classification |
| `restart_required` | `str` | | `shell` / `session` / `system` |
| `version_constraint` | `dict` | | Compatibility rules (e.g., kubectl ±1 minor version) |
| `type` | `str` | | Recipe type override: `data_pack` or `config` |
| `choices` | `list[choice]` | | Interactive variant selection |
| `install_variants` | `dict[id → variant]` | | Per-choice install commands |
| `inputs` | `list[input]` | | User inputs (credentials, paths, model IDs) |
| `steps` | `list[step]` | | Multi-step recipes (data packs, kernel config) |
| `config_templates` | `list[template]` | | Config file templates with inputs |

---

## Advanced Feature Showcase

### 1. Multi-Platform Method Selection (77 tools)

The resolver picks the right method for the target system.
`prefer` tells it which PM to try first.

```python
# kubectl — 8 install methods, cross-platform
"kubectl": {
    "install": {
        "snap":   ["snap", "install", "kubectl", "--classic"],
        "apt":    ["apt-get", "install", "-y", "kubectl"],
        "dnf":    ["dnf", "install", "-y", "kubernetes-client"],
        "apk":    ["apk", "add", "kubectl"],
        "pacman": ["pacman", "-S", "--noconfirm", "kubectl"],
        "zypper": ["zypper", "install", "-y", "kubernetes-client"],
        "brew":   ["brew", "install", "kubectl"],
        "_default": ["bash", "-c", "curl -sSfL -o /tmp/kubectl ..."],  # binary download
    },
    "prefer": ["_default", "snap", "brew"],   # resolver tries these first
    ...
}
```

Same user action → different plans per distro. The recipe is ONE dict.

---

### 2. Architecture-Portable Binary Downloads (26 tools)

`{os}` and `{arch}` placeholders in URLs, resolved at install time.
`arch_map` normalizes the host's `uname -m` to what the download URL expects.

```python
"kubectl": {
    "install": {
        "_default": [
            "bash", "-c",
            'curl -sSfL -o /tmp/kubectl '
            '"https://dl.k8s.io/release/'
            '$(curl -sSfL https://dl.k8s.io/release/stable.txt)'
            '/bin/{os}/{arch}/kubectl" && '
            'chmod +x /tmp/kubectl && mv /tmp/kubectl /usr/local/bin/kubectl',
        ],
    },
    "arch_map": {"x86_64": "amd64", "aarch64": "arm64", "armv7l": "arm"},
}
```

On `x86_64` → downloads `.../amd64/kubectl`. On Raspberry Pi → `.../arm64/kubectl`.

---

### 3. Transitive Dependency Resolution

`requires.binaries` triggers recursive resolution. `requires.packages` injects
distro-specific system packages.

```python
"cargo-audit": {
    "requires": {
        "binaries": ["cargo"],               # → resolver recurses into "cargo" recipe
        "packages": {                         # → resolver reads distro family
            "debian": ["pkg-config", "libssl-dev"],
            "rhel":   ["pkgconf-pkg-config", "openssl-devel"],
            "alpine": ["pkgconf", "openssl-dev"],
            "macos":  ["pkg-config", "openssl@3"],
        },
    },
}
```

Install `cargo-audit` on Ubuntu → plan includes: `apt-get install libssl-dev`,
then `curl | sh` (rustup), then `cargo install cargo-audit`. Automatic.

---

### 4. GPU-Aware Choice-Based Variants (3 tools)

User picks a variant. Each variant has its own install command, risk level,
estimated time, and hardware requirements.

```python
"pytorch": {
    "choices": [{
        "id": "variant",
        "label": "PyTorch variant",
        "type": "single",
        "options": [
            {
                "id": "cpu",
                "label": "CPU only",
                "description": "Suitable for development, testing, ...",
                "risk": "low",
                "estimated_time": "2-5 minutes",
                "default": True,
            },
            {
                "id": "cuda",
                "label": "NVIDIA CUDA (GPU accelerated)",
                "warning": "Requires NVIDIA drivers and CUDA toolkit. ~2 GB.",
                "requires": {"hardware": ["nvidia"]},  # grayed out if no NVIDIA GPU
            },
            {
                "id": "rocm",
                "label": "AMD ROCm (GPU accelerated)",
                "requires": {"hardware": ["amd"]},
            },
        ],
    }],
    "install_variants": {
        "cpu":  {"command": ["pip3", "install", "torch", "--index-url", ".../cpu"]},
        "cuda": {"command": ["pip3", "install", "torch"]},
        "rocm": {"command": ["pip3", "install", "torch", "--index-url", ".../rocm6.2"]},
    },
}
```

The resolver presents all three — available AND unavailable (with disabled reasons).
User picks. Resolver applies the selected variant's command.

---

### 5. Kernel-Level Step-Based Provisioning (6 tools)

Multi-step recipes with ordered steps, `depends_on` DAG edges,
file backup before mutation, risk tagging per step.

```python
"vfio-passthrough": {
    "type": "data_pack",
    "risk": "high",
    "steps": [
        {
            "id": "vfio-modules",
            "type": "config",
            "label": "Enable VFIO kernel modules",
            "action": "ensure_line",
            "file": "/etc/modules-load.d/vfio.conf",
            "lines": ["vfio", "vfio_iommu_type1", "vfio_pci", "vfio_virqfd"],
            "needs_sudo": True,
            "risk": "high",
            "backup_before": ["/etc/modules-load.d/vfio.conf"],
        },
        {
            "id": "iommu-grub",
            "type": "config",
            "label": "Enable IOMMU in boot parameters",
            "file": "/etc/default/grub",
            "content": 'GRUB_CMDLINE_LINUX_DEFAULT="quiet splash intel_iommu=on iommu=pt"',
            "backup_before": ["/etc/default/grub"],
            "depends_on": ["vfio-modules"],           # ← DAG edge
        },
        {
            "id": "update-grub",
            "type": "post_install",
            "command": ["update-grub"],
            "depends_on": ["iommu-grub"],
        },
        {
            "id": "load-vfio",
            "type": "post_install",
            "command": ["modprobe", "vfio-pci"],
            "depends_on": ["vfio-modules"],
        },
    ],
    "rollback": {
        "remove_files": ["/etc/modules-load.d/vfio.conf"],
        "post": ["update-grub"],
    },
    "restart_required": "system",
}
```

---

### 6. GPU Driver Stack with Repo Setup (2 tools)

Full lifecycle: add repo → install packages → load kernel module → verify → rollback.

```python
"nvidia-driver": {
    "risk": "high",
    "repo_setup": {
        "apt": [
            {"label": "Add NVIDIA PPA",
             "command": ["add-apt-repository", "-y", "ppa:graphics-drivers/ppa"],
             "needs_sudo": True},
            {"label": "Update package lists",
             "command": ["apt-get", "update"],
             "needs_sudo": True},
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
        {"label": "Load NVIDIA kernel module",
         "command": ["modprobe", "nvidia"],
         "needs_sudo": True},
    ],
    "rollback": {
        "apt": ["apt-get", "purge", "-y", "nvidia-driver-535"],
        "post": ["modprobe", "nouveau"],    # fall back to open-source driver
    },
    "restart_required": "system",
}
```

---

### 7. Config Templates with User Inputs (4 tools)

Parametrized config file generation with typed inputs, validation,
post-apply commands, and system condition checks.

```python
"docker-daemon-config": {
    "type": "config",
    "config_templates": [{
        "id": "docker_config",
        "file": "/etc/docker/daemon.json",
        "format": "json",
        "template": '{\n  "storage-driver": "{docker_storage_driver}",\n  ...}',
        "inputs": [
            {"id": "docker_storage_driver", "label": "Storage Driver",
             "type": "select", "options": ["overlay2", "btrfs", "devicemapper"],
             "default": "overlay2"},
            {"id": "log_max_size", "label": "Max log size per container",
             "type": "select", "options": ["10m", "50m", "100m", "500m"],
             "default": "50m"},
        ],
        "needs_sudo": True,
        "post_command": ["systemctl", "restart", "docker"],
        "condition": "has_systemd",
        "backup": True,                    # back up existing file before write
    }],
}
```

```python
"nginx-vhost": {
    "type": "config",
    "config_templates": [{
        "file": "/etc/nginx/sites-available/{site_name}",   # path includes input
        "format": "raw",
        "template": "server {\n    listen {port};\n    server_name {server_name};\n    ...}",
        "inputs": [
            {"id": "site_name", "type": "text", "default": "default"},
            {"id": "port", "type": "number", "default": 80,
             "validation": {"min": 1, "max": 65535}},
            {"id": "server_name", "type": "text", "default": "_"},
            {"id": "document_root", "type": "path", "default": "/var/www/html"},
        ],
        "post_command": ["bash", "-c",
                         "ln -sf ... && nginx -t && systemctl reload nginx"],
    }],
}
```

---

### 8. Data Pack Downloads with Credentials (5 tools)

`type: "data_pack"` recipes download data files — vulnerability databases,
ML models, wordlists. Some require user-provided credentials.

```python
"hf-model": {
    "type": "data_pack",
    "label": "HuggingFace Model (gated)",
    "inputs": [
        {"id": "model_id", "label": "Model ID", "type": "text",
         "default": "meta-llama/Llama-2-7b-hf", "required": True},
        {"id": "hf_token", "label": "HuggingFace Token", "type": "password",
         "required": True,
         "help_text": "Get a token from https://huggingface.co/settings/tokens"},
    ],
    "steps": [{
        "id": "download-hf-model",
        "type": "post_install",
        "command": ["python3", "-c",
                    "from huggingface_hub import snapshot_download; "
                    "snapshot_download('{model_id}', token='{hf_token}')"],
    }],
    "requires": {
        "binaries": ["python3"],
        "network": ["https://huggingface.co"],    # network reachability check
    },
}
```

```python
"trivy-db": {
    "type": "data_pack",
    "steps": [{
        "type": "download",
        "url": "https://github.com/.../db.tar.gz",
        "dest": "~/.cache/trivy/db/trivy.db",
        "size_bytes": 150_000_000,         # disk space check before download
        "freshness_days": 7,               # re-download if older than 7 days
    }],
    "requires": {"binaries": ["trivy"]},
}
```

---

### 9. Environment Propagation (30 tools)

`post_env` injects shell exports into all subsequent steps.
Critical for tools that install to non-standard paths
(rustup → `~/.cargo/bin`, nvm → `~/.nvm`, etc.).

```python
"rustup": {
    "post_env": 'export PATH="$HOME/.cargo/bin:$PATH"',
    # → resolver injects this into every step AFTER rustup install
    # → cargo, rustc, cargo-audit all find the newly installed binaries
}
```

---

### 10. Version Constraints (1 tool)

Declarative version compatibility rules. The resolver can warn or
auto-select the right version.

```python
"kubectl": {
    "version_constraint": {
        "type": "minor_range",
        "reference_hint": "cluster_version",     # look at the K8s cluster
        "range": 1,                               # ±1 minor version
        "description": "kubectl should be within ±1 minor version of the K8s cluster.",
    },
}
```

---

## Feature Coverage Summary

| Feature | Tools Using It | Example |
|---------|---------------|---------|
| Multi-method install | 300 | Every recipe |
| `prefer` (PM priority) | 77 | kubectl, helm, docker |
| `post_env` propagation | 30 | rustup, nvm, go, wasmtime |
| `arch_map` portability | 26 | kubectl, k9s, grype, gh |
| `risk` classification | 13 | nvidia-driver, pytorch, vfio |
| `update` commands | ~60 | kubectl, helm, all PMs |
| `type: data_pack` | 6 | trivy-db, hf-model, vfio |
| `type: config` | 4 | docker-daemon, nginx-vhost |
| `choices` + `variants` | 3 | pytorch, opencv, mkdocs |
| `inputs` (credentials) | 2 | geoip-db, hf-model |
| `repo_setup` | 1 | nvidia-driver |
| `version_constraint` | 1 | kubectl |
| `rollback` | 3 | nvidia, vfio, rocm |
| `restart_required` | 3 | nvidia, vfio, rocm |
| `config_templates` | 4 | docker-daemon, journald, nginx |
| `steps` (multi-step DAG) | 6 | vfio, trivy-db, spacy-en |

---

## Shared Constant: `_PIP`

```python
from src.core.services.tool_install.data.constants import _PIP
# _PIP = [sys.executable, "-m", "pip"]
```

Used by ~50 tool recipes across `python.py`, `security/scanners.py`, `data_ml/ml.py`,
and several other files. Defined once in `constants.py` — never duplicated.

---

## Adding a New Tool

1. **Identify the domain** — Where does this tool belong?
   A Kubernetes tool goes in `devops/k8s.py`. A Python linter goes in `languages/python.py`.

2. **Add the recipe dict** to the appropriate leaf file:
   ```python
   "my-tool": {
       "label": "My Tool",
       "category": "python",
       "install": {
           "_default": _PIP + ["install", "my-tool"],
           "apt": ["apt-get", "install", "-y", "my-tool"],
       },
       "needs_sudo": {"_default": False, "apt": True},
       "verify": ["my-tool", "--version"],
   }
   ```

3. **Done.** No imports to update, no `__init__.py` changes,
   no consumer changes. The merge chain picks it up automatically.

### If adding a new domain:

1. Create `recipes/new_domain/` with `__init__.py` + leaf file(s)
2. Add the import + merge in `recipes/__init__.py`
3. That's it — consumers still just use `TOOL_RECIPES`

---

## Design Decisions

### Why domain folders, not flat files?

The folder structure is navigational documentation. A developer adding
a Kubernetes tool opens `recipes/devops/k8s.py` — they don't scroll
through a 7,000-line file or search 15 flat files for the right one.

### Why Composite Registry, not a dynamic loader?

Explicit imports over magic. Every merge is visible in the `__init__.py`
chain. No `importlib.import_module()`, no `pkgutil.walk_packages()`,
no runtime discovery. You can `grep` for any recipe variable name
and trace exactly where it enters `TOOL_RECIPES`.

### Why `category` field on every recipe?

It's the tool's domain identity. It determines which file the tool
lives in, and it's used by consumers for grouping in the UI.
Every tool has exactly one category. No exceptions.
