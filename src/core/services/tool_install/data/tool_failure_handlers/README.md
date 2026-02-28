# Tool-Specific Failure Handler Registry

> **52 handlers. 18 tools. 3 domains. Pure data, no logic.**
>
> Every tool-specific failure pattern, its detection regex, and its remediation
> options — organized by tool domain. The folder structure IS the documentation.

---

## How It Works

When a tool install or post-install verification fails, the engine captures stderr
and walks the handler hierarchy. **Tool-specific handlers are checked before
method-family handlers** — they're the most specific layer because the recipe
author knows their tool's failure modes better than any generic method handler.

```
           STDERR + EXIT CODE
                  │
                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│              TOOL-SPECIFIC HANDLERS (this package)                    │
│                                                                      │
│    Keyed by tool ID — only the handlers for the tool being           │
│    installed are searched. Docker failures only check docker          │
│    handlers. Python failures only check python handlers.             │
│                                                                      │
│    52 handlers across 18 tools. Each handler offers remediation      │
│    options: start a daemon, add a user group, switch install         │
│    method, install a dependency, or present manual instructions.     │
└─────────────────────────────┬────────────────────────────────────────┘
                              │ no match
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│              METHOD-FAMILY HANDLERS (remediation_handlers/)           │
│    Layer 2 → Layer 1 → Layer 0                                       │
│    (pip, npm, cargo, apt, ... → infra → bootstrap)                   │
└──────────────────────────────────────────────────────────────────────┘
```

Every consumer does flat symbol import:

```python
from src.core.services.tool_install.data.tool_failure_handlers import (
    TOOL_FAILURE_HANDLERS,
)
```

The internal package structure is invisible to consumers.

---

## Package Structure

```
tool_failure_handlers/
├── __init__.py                  ← Re-exports TOOL_FAILURE_HANDLERS (merges all 3 domains)
│
├── languages/                   ← Language ecosystem tools (11 tools, 30 handlers)
│   ├── __init__.py              ← Merges all 5 files → LANGUAGE_TOOL_HANDLERS
│   ├── rust.py                  ← cargo (2 handlers, 4 options), rustup (2 handlers, 4 options)
│   ├── go.py                    ← go (3 handlers, 3 options)
│   ├── python.py                ← python (7 handlers, 12 options), poetry (1, 2), uv (1, 3)
│   ├── node.py                  ← node (5 handlers, 12 options), nvm (2, 4), yarn (3, 6), pnpm (1, 3)
│   └── php.py                   ← composer (2 handlers, 6 options)
│
├── devops/                      ← DevOps / infrastructure tools (6 tools, 21 handlers)
│   ├── __init__.py              ← Merges all 3 files → DEVOPS_TOOL_HANDLERS
│   ├── containers.py            ← docker (8 handlers, 17 options), docker-compose (3, 5)
│   ├── k8s.py                   ← helm (2 handlers, 4 options), kubectl (3, 5)
│   └── cloud.py                 ← gh (2 handlers, 4 options), terraform (3, 7)
│
└── security/                    ← Security tools (1 tool, 2 handlers)
    ├── __init__.py              ← Merges all 1 file → SECURITY_TOOL_HANDLERS
    └── scanners.py              ← trivy (2 handlers, 4 options)
```

---

## Handler Model Reference

Handlers are **declarative tool-id-to-failure-pattern maps**. When a tool
fails, the matching engine (`handler_matching.py`) selects the handler list
for that specific tool and matches stderr against each handler's regex.
Only handlers for the failing tool are searched — no cross-tool scanning.

### Handler Fields

| Field | Type | Required | Purpose |
|-------|------|----------|---------|
| `pattern` | `str` (regex) | ✅ | Regex matched against stderr + stdout |
| `failure_id` | `str` | ✅ | Unique identifier for this failure mode |
| `category` | `str` | ✅ | Failure domain (`environment`, `dependency`, `permissions`, `configuration`, `compatibility`, `network`) |
| `label` | `str` | ✅ | Human-readable failure name |
| `description` | `str` | ✅ | Explanation of what went wrong and why |
| `example_stderr` | `str` | | Real-world stderr that triggers this handler |
| `options` | `list[dict]` | ✅ | Remediation options (see below) |

### Option Fields

| Field | Type | Required | Purpose |
|-------|------|----------|---------|
| `id` | `str` | ✅ | Unique option identifier within this handler |
| `label` | `str` | ✅ | Human-readable option name |
| `description` | `str` | ✅ | What this option does |
| `icon` | `str` | ✅ | Emoji icon for UI display |
| `recommended` | `bool` | ✅ | Whether this is the suggested default |
| `strategy` | `str` | ✅ | Remediation strategy (see below) |
| `risk` | `str` | | `low`, `medium`, `high` — risk classification |
| `requires` | `dict` | | System prerequisites for this option to be viable |
| `method` | `str` | | Method to switch to (for `switch_method` strategy) |
| `dep` | `str` | | Tool/binary to install as a dependency |
| `fix_commands` | `list[list]` | | Commands to fix the environment before retry |
| `cleanup_commands` | `list[list]` | | Commands to run before retry (cache clearing, etc.) |
| `modifier` | `dict` | | Modifiers applied when retrying |
| `packages` | `dict[str, list]` | | Per-distro packages to install |
| `instructions` | `str` | | Manual instructions for the user |

### Strategies Used

| Strategy | What It Does | Example |
|----------|-------------|---------|
| `env_fix` | Run fix commands to repair the environment | Start Docker daemon |
| `install_dep` | Install a missing dependency | Install Docker |
| `switch_method` | Switch to a different install method | Helm apt → get-helm-3 script |
| `manual` | Present instructions — no automated fix | Docker Desktop startup |
| `install_packages` | Install system packages | containerd.io |
| `cleanup_retry` | Run cleanup commands, then retry | Reset Docker storage |
| `retry_with_modifier` | Retry with extra flags | Docker commands with sudo |

---

## Domain Coverage

### Languages (11 tools, 30 handlers, 69 options)

| File | Tools | Failure Modes Covered |
|------|-------|-----------------------|
| `rust.py` | cargo, rustup | Missing rustup, curl/network failures, rustup not in PATH, target not installed |
| `go.py` | go | GOPATH not set, `go install` requires Go modules, CGO linker failures |
| `python.py` | python, poetry, uv | Python not found, pip not found, pip version mismatch, venv not available, build deps missing, SSL module missing, tkinter missing, poetry/uv not in PATH |
| `node.py` | node, nvm, yarn, pnpm | NVM not loaded, node version conflicts, npm permission errors, global install failures, architecture mismatch, yarn/pnpm not found |
| `php.py` | composer | Composer not found, PHP version mismatch |

### DevOps (6 tools, 21 handlers, 42 options)

| File | Tools | Failure Modes Covered |
|------|-------|-----------------------|
| `containers.py` | docker, docker-compose | Daemon not running, socket permission denied, not installed, containerd down, storage driver errors, API version mismatch, port conflicts, cgroup v2 incompatibility, compose plugin missing, legacy v1 not found, compose YAML syntax errors |
| `k8s.py` | helm, kubectl | GPG key / repo setup failures, package not found (repo not configured), version skew, architecture mismatch |
| `cloud.py` | gh, terraform | GPG key / repo setup failures, package not found (repo not configured), HashiCorp checkpoint API unreachable |

### Security (1 tool, 2 handlers, 4 options)

| File | Tools | Failure Modes Covered |
|------|-------|-----------------------|
| `scanners.py` | trivy | Aqua Security GPG key / repo setup failure, package not found (repo not configured) |

---

## Advanced Feature Showcase

### 1. Multi-Option, Multi-Platform Remediation (Docker — 8 handlers, 17 options)

Docker has the most complex handler set. A single failure
(`docker_daemon_not_running`) offers **4 different remediation paths**
depending on the system type:

```python
# devops/containers.py — handler: docker_daemon_not_running
{
    "pattern": r"Cannot connect to the Docker daemon|...",
    "failure_id": "docker_daemon_not_running",
    "options": [
        {
            "id": "start-docker-systemd",              # systemd systems
            "strategy": "env_fix",
            "requires": {"has_systemd": True},
            "fix_commands": [
                ["sudo", "systemctl", "start", "docker"],
                ["sudo", "systemctl", "enable", "docker"],
            ],
        },
        {
            "id": "start-docker-openrc",               # Alpine / OpenRC
            "requires": {"is_linux": True},
            "strategy": "env_fix",
            "fix_commands": [
                ["sudo", "rc-update", "add", "docker", "default"],
                ["sudo", "service", "docker", "start"],
            ],
        },
        {
            "id": "start-dockerd-manual",              # WSL / containers
            "requires": {"is_linux": True},
            "strategy": "manual",
            "instructions": "Run: sudo dockerd &...",
        },
        {
            "id": "start-docker-desktop",              # macOS
            "strategy": "manual",
            "instructions": "1. Open Docker Desktop...",
        },
    ],
}
```

One failure → four paths. The planner selects which options are viable
based on the system profile (systemd available? Linux? macOS?).

---

### 2. Repository / GPG Key Failures (7 tools)

Seven tools (gh, helm, kubectl, terraform, trivy, composer, docker) require
adding third-party repositories with GPG keys. This is the most common
tool-specific failure mode. Each handler provides the same escape pattern:

```python
# devops/cloud.py — handler: terraform_gpg_repo_setup_failed
{
    "pattern": r"gpg:.*keyserver receive failed|Could not resolve host.*hashicorp|...",
    "failure_id": "terraform_gpg_repo_setup_failed",
    "options": [
        {
            "id": "use-binary-download",               # bypass the repo entirely
            "strategy": "switch_method",
            "method": "_default",                      # ← direct binary download
        },
        {
            "id": "use-snap",                          # alternative package manager
            "strategy": "switch_method",
            "method": "snap",
        },
    ],
}
```

When the repo setup fails → switch to a method that doesn't need it.

---

### 3. System Pre-Requirement Gates (Docker, Python)

Options declare their **system prerequisites** via `requires`. The planner
only presents options whose requirements are met:

```python
# devops/containers.py — docker socket permission denied
{
    "id": "add-docker-group",
    "requires": {"is_linux": True, "not_root": True},  # ← only on Linux, non-root
    "strategy": "env_fix",
    "fix_commands": [
        ["sudo", "groupadd", "-f", "docker"],
        ["sudo", "usermod", "-aG", "docker", "${USER}"],
    ],
}
```

On macOS → this option is hidden. Running as root → this option is hidden.
The UI only shows viable paths.

---

### 4. Risk Classification (Docker storage reset)

Dangerous operations carry explicit risk warnings:

```python
# devops/containers.py — docker storage driver error
{
    "id": "reset-storage",
    "risk": "high",                                    # ← UI shows warning
    "requires": {"has_systemd": True, "writable_rootfs": True},
    "strategy": "cleanup_retry",
    "cleanup_commands": [
        ["sudo", "systemctl", "stop", "docker"],
        ["sudo", "rm", "-rf", "/var/lib/docker"],      # ← destroys all data
        ["sudo", "systemctl", "start", "docker"],
    ],
}
```

The `risk: "high"` flag tells the UI to show a confirmation prompt before
executing cleanup_commands that delete data.

---

### 5. Version Skew Detection (kubectl)

Tool-specific handlers can detect **post-install** failures that generic
handlers would never catch:

```python
# devops/k8s.py — kubectl version skew
{
    "pattern": r"WARNING:.*version difference|version skew|...",
    "failure_id": "kubectl_version_skew",
    "options": [{
        "id": "reinstall-matching-version",
        "strategy": "manual",
        "instructions": (
            "1. Check your cluster version: kubectl version --short\n"
            "2. Download matching kubectl: curl -LO ...\n"
            "3. chmod +x kubectl && sudo mv kubectl /usr/local/bin/"
        ),
    }],
}
```

kubectl installed successfully, but version skew with the cluster
makes it unreliable. This is purely a tool-specific domain concern.

---

### 6. Architecture Mismatch Detection (node, kubectl)

Defense-in-depth against wrong-architecture binaries:

```python
# devops/k8s.py — kubectl exec format error
{
    "pattern": r"exec format error|cannot execute binary file.*Exec format",
    "failure_id": "kubectl_exec_format_error",
    "options": [
        {
            "id": "reinstall-correct-arch",
            "strategy": "switch_method",
            "method": "_default",                      # re-detect architecture
        },
        {
            "id": "install-via-apt",
            "strategy": "switch_method",
            "method": "apt",                           # apt auto-selects arch
        },
    ],
}
```

Catches Raspberry Pi 64-bit kernel + 32-bit userland mismatches
where `_default` downloads the wrong binary.

---

## Feature Coverage Summary

| Feature | Handlers Using It | Example |
|---------|------------------|---------|
| Regex pattern matching | 52 | Every handler |
| Multi-option remediation | 18 | docker daemon (4 options), python not found (3) |
| `env_fix` with commands | 8 | Start Docker, add docker group, start containerd |
| `switch_method` escalation | 15 | helm apt → get-helm-3, terraform apt → binary |
| `manual` instructions | 14 | Docker Desktop startup, kubectl version fix |
| `install_dep` | 5 | Install Docker, install Node |
| `install_packages` | 2 | containerd.io packages |
| `cleanup_retry` | 1 | Docker storage reset |
| `retry_with_modifier` | 1 | Docker with sudo |
| `requires` system gates | 10 | has_systemd, is_linux, not_root, not_container |
| `risk` classification | 3 | Docker storage reset (high), cgroup fallback (high) |
| Distro-aware `packages` | 2 | containerd per distro family |

---

## Difference from remediation_handlers

| Aspect | `remediation_handlers/` | `tool_failure_handlers/` |
|--------|------------------------|-------------------------|
| **Keyed by** | Install method (pip, npm, apt…) | Tool ID (docker, python, helm…) |
| **When matched** | After any method failure | After a specific tool fails |
| **Scope** | Cross-tool (pip failures for ANY tool) | Single tool (docker handlers only for docker) |
| **Layer** | L2 method → L1 infra → L0 bootstrap | Above L2 (checked first) |
| **Handlers** | 77 across 19 method families | 52 across 18 tools |
| **Focus** | Package manager mechanics | Tool-specific runtime, environment, configuration |

---

## Adding a New Handler

1. **Identify the domain** — What kind of tool is it?
   Docker → `devops/containers.py`. Python → `languages/python.py`.
   Trivy → `security/scanners.py`.

2. **Add the handler dict** to the appropriate `_TOOL_HANDLERS` list:
   ```python
   {
       "pattern": r"new_error_pattern_regex",
       "failure_id": "unique_failure_id",
       "category": "environment",              # environment, dependency, permissions,
                                                # configuration, compatibility, network
       "label": "Human-readable label",
       "description": "What went wrong and why.",
       "example_stderr": "Actual stderr that triggers this",
       "options": [
           {
               "id": "fix-it",
               "label": "Recommended fix",
               "description": "What this option does",
               "icon": "🔧",
               "recommended": True,
               "strategy": "env_fix",
               "fix_commands": [
                   ["sudo", "systemctl", "restart", "my-service"],
               ],
           },
       ],
   }
   ```

3. **Done.** No imports to update, no `__init__.py` changes,
   no consumer changes. The merge chain picks it up automatically.

### If adding a new tool to an existing domain:

1. Add `_NEW_TOOL_HANDLERS: list[dict]` in the appropriate file
2. Add the export in the domain `__init__.py` (`"new_tool": _NEW_TOOL_HANDLERS`)
3. That's it — consumers still just use `TOOL_FAILURE_HANDLERS`

### If adding a new domain:

1. Create `new_domain/__init__.py` exporting `NEW_DOMAIN_TOOL_HANDLERS`
2. Create `new_domain/tools.py` with `_TOOL_HANDLERS: list[dict]`
3. Add the import + merge in the top-level `__init__.py`

---

## Design Decisions

### Why tool-keyed, not method-keyed?

Method-family handlers catch _generic_ failures ("pip can't resolve dependencies").
Tool-specific handlers catch failures that only make sense for one tool:
"Docker daemon not running" is irrelevant for pip. "kubectl version skew"
is irrelevant for npm. Tool-keying prevents false matches and keeps the
search space small — only the handlers for the failing tool are scanned.

### Why domain-based file organization?

Same reason as recipes: the file name IS the documentation. A developer
debugging a Docker failure opens `devops/containers.py`. They don't scroll
through a 3,200-line monolith or search for `"docker":` in a giant dict.

### Why separate from remediation_handlers?

They serve different matching axes. `remediation_handlers` are keyed by
_install method_ (pip, npm, apt). `tool_failure_handlers` are keyed by
_tool ID_ (docker, python, helm). A tool installed via apt might hit an
apt-family handler OR a tool-specific handler depending on the error.
Mixing these in one structure would conflate two orthogonal lookup dimensions.

### Why `example_stderr` on every handler?

It's documentation that doubles as test data. The matching tests use these
examples to verify the regex patterns actually match real-world errors.
No example = untestable handler.
