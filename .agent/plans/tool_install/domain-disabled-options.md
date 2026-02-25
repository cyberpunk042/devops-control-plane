# Domain: Disabled Options

> This document catalogs the "always-present, sometimes-disabled"
> pattern for tool install options. Why options are never removed,
> the disabled_reason/enable_hint/learn_more fields, risk level
> indicators, and how the assistant panel uses this data to
> provide context-aware guidance.
>
> SOURCE DOCS: scope-expansion §2.15 (disabled options principle),
>              domain-choices §disabled option format,
>              domain-choices §UI treatment,
>              domain-gpu §constraint evaluation

---

## The Core Principle

**Options that can't be used on this system are NEVER removed.
They are returned with `available: False` and a reason.**

### Why never remove

If unavailable options are removed:

| What user sees | What user thinks |
|---------------|-----------------|
| Only "CPU" option | "This tool only supports CPU" |
| No ROCm option | "PyTorch doesn't support AMD GPUs" |
| No source build option | "This can only be installed via pip" |

The user doesn't know what they're missing. They can't learn.
They can't plan for the future.

### What we do instead

| What user sees | What user learns |
|---------------|-----------------|
| "CUDA 12.1" (grayed out, reason shown) | "I need an NVIDIA GPU for this" |
| "ROCm 5.7" (grayed out, enable hint) | "If I add an AMD GPU, I can use ROCm" |
| "Build from source" (grayed out, deps listed) | "I need cmake and gcc first" |

---

## Disabled Option Schema

### Full format

```python
{
    # Standard option fields
    "id": str,
    "label": str,
    "description": str,

    # Availability
    "available": False,

    # Why disabled (required when available=False)
    "disabled_reason": str,

    # How to enable (optional but strongly recommended)
    "enable_hint": str,

    # Link for more information (optional)
    "learn_more": str,

    # Risk level of this option (independent of availability)
    "risk": str,            # "low" | "medium" | "high"

    # What constraint failed
    "failed_constraint": str,
}
```

### Fields explained

| Field | When | Purpose |
|-------|------|---------|
| `disabled_reason` | Always when `available: False` | One-line explanation of why |
| `enable_hint` | When there's a path to enabling | Actionable instruction |
| `learn_more` | When external docs help | URL to vendor/docs |
| `risk` | Always (enabled or disabled) | Safety indicator |
| `failed_constraint` | For programmatic use | Machine-readable constraint ID |

---

## Reason Categories

### Hardware missing

```python
{"disabled_reason": "No NVIDIA GPU detected (lspci shows no NVIDIA device)",
 "enable_hint": "Install a compatible NVIDIA GPU and the proprietary NVIDIA driver",
 "learn_more": "https://developer.nvidia.com/cuda-gpus",
 "failed_constraint": "hardware.gpu.nvidia.present"}
```

### Software missing

```python
{"disabled_reason": "cmake not installed (required for build from source)",
 "enable_hint": "Install cmake: sudo apt-get install cmake",
 "failed_constraint": "binaries.cmake"}
```

### Version incompatible

```python
{"disabled_reason": "CUDA 12.4 requires NVIDIA driver ≥535.54 (found: 525.60)",
 "enable_hint": "Update NVIDIA driver: sudo apt-get install nvidia-driver-535",
 "failed_constraint": "hardware.gpu.nvidia.driver_version"}
```

### Platform unsupported

```python
{"disabled_reason": "snap not available on Alpine Linux",
 "enable_hint": "Use the 'binary download' method instead",
 "failed_constraint": "capabilities.snap_available"}
```

### Network unavailable

```python
{"disabled_reason": "pip install requires internet access (network offline)",
 "enable_hint": "Connect to the internet or use an offline package cache",
 "failed_constraint": "network.online"}
```

### Permission insufficient

```python
{"disabled_reason": "System package install requires sudo (not available in container)",
 "enable_hint": "Run the container with --privileged or use a user-space alternative",
 "failed_constraint": "capabilities.has_sudo"}
```

### Auth missing

```python
{"disabled_reason": "LLaMA 2 model requires Hugging Face access token",
 "enable_hint": "Get a token at https://huggingface.co/settings/tokens and set HF_TOKEN",
 "learn_more": "https://huggingface.co/meta-llama/Llama-2-7b-hf",
 "failed_constraint": "auth.hf_token"}
```

### Disk space insufficient

```python
{"disabled_reason": "Stable Diffusion requires 10 GB free disk space (found: 4.2 GB)",
 "enable_hint": "Free up disk space or select a smaller model",
 "failed_constraint": "hardware.disk_free_gb"}
```

---

## Risk Level Indicators

### Risk applies to ALL options (not just disabled)

```python
# Enabled + low risk
{"id": "pip", "label": "pip install", "available": True,
 "risk": "low"}

# Enabled + high risk
{"id": "kernel_rebuild", "label": "Rebuild kernel with module",
 "available": True, "risk": "high",
 "warning": "Kernel rebuild may prevent boot if misconfigured"}

# Disabled + high risk
{"id": "vfio_passthrough", "label": "GPU passthrough (VFIO)",
 "available": False, "risk": "high",
 "disabled_reason": "No IOMMU groups detected",
 "warning": "Requires kernel configuration and system reboot"}
```

### Risk levels

| Risk | Meaning | UI treatment |
|------|---------|-------------|
| `low` | Reversible, user-space | No special indicator |
| `medium` | System-level, needs sudo | ⚠️ Yellow indicator |
| `high` | May affect system boot/stability | 🔴 Red indicator + warning text |

### Mapping operations to risk

| Operation | Risk | Why |
|-----------|------|-----|
| pip install | low | User-space, pip uninstall reverses |
| apt-get install | medium | System-level, needs sudo |
| systemctl enable | medium | Changes boot behavior |
| Kernel module load | medium | Can be unloaded |
| Docker group add | medium | Security implication |
| Kernel recompile | high | May prevent boot |
| Driver install | high | May break display |
| GRUB modification | high | May prevent boot |
| VFIO passthrough | high | GPU becomes unusable for host |

---

## Assistant Panel Integration

### How the assistant uses disabled option data

The assistant panel reads the disabled option fields and
generates contextual guidance:

```
┌─ Assistant ──────────────────────────────────────┐
│                                                    │
│ 💡 About your options                              │
│                                                    │
│ CPU only is selected automatically because no      │
│ dedicated GPU was detected on this system.          │
│                                                    │
│ 🔒 CUDA 11.8, CUDA 12.1, CUDA 12.4                │
│ These options require an NVIDIA GPU. The system     │
│ scan found no NVIDIA device via lspci.              │
│                                                    │
│ To enable GPU acceleration:                        │
│ • Install a compatible NVIDIA GPU (Kepler or newer) │
│ • Install the proprietary NVIDIA driver             │
│ • Install the CUDA toolkit                         │
│                                                    │
│ 🔒 ROCm 5.7                                       │
│ Requires an AMD GPU with ROCm support.             │
│                                                    │
│ 📖 Learn more about CUDA GPUs                      │
│    https://developer.nvidia.com/cuda-gpus           │
│                                                    │
└────────────────────────────────────────────────────┘
```

### Data flow

```
1. Resolver evaluates constraints
   └── Sets available, disabled_reason, enable_hint per option

2. API returns full option list (including disabled)
   └── Frontend receives all options

3. Frontend renders choice UI
   └── Enabled options: selectable
   └── Disabled options: grayed out with 🔒

4. Frontend sends option data to assistant panel
   └── Assistant renders contextual guidance

5. User changes selection
   └── Assistant updates guidance for new context
```

### Assistant content generation

```python
def generate_assistant_content(choice: dict) -> str:
    """Generate assistant HTML from choice data."""
    parts = []

    # Explain disabled options
    disabled = [o for o in choice["options"] if not o["available"]]
    if disabled:
        parts.append("<h4>🔒 Unavailable options</h4>")
        for opt in disabled:
            parts.append(f"<p><strong>{opt['label']}</strong>: "
                        f"{opt['disabled_reason']}</p>")
            if opt.get("enable_hint"):
                parts.append(f"<p>💡 {opt['enable_hint']}</p>")
            if opt.get("learn_more"):
                parts.append(f"<p>📖 <a href='{opt['learn_more']}'>Learn more</a></p>")

    # Warn about high-risk enabled options
    risky = [o for o in choice["options"]
             if o["available"] and o.get("risk") == "high"]
    if risky:
        parts.append("<h4>⚠️ High-risk options</h4>")
        for opt in risky:
            parts.append(f"<p><strong>{opt['label']}</strong>: "
                        f"{opt.get('warning', 'Proceed with caution')}</p>")

    return "\n".join(parts)
```

---

## Multiple Disabled Reasons

### When multiple constraints fail

An option can fail MULTIPLE constraints. Show the primary one:

```python
# CUDA 12.4 on system with old GPU + old driver
{
    "id": "cuda124",
    "available": False,
    "disabled_reason": "No NVIDIA GPU detected",
    # Primary reason (checked first in priority order)
    "all_failures": [
        "No NVIDIA GPU detected",
        "Compute capability ≥7.0 required",
        "Driver ≥535.54 required",
    ],
}
```

### Constraint check priority

Check in order of "most fundamental first":

1. Hardware present? (GPU, CPU features)
2. Software installed? (binary, library)
3. Version compatible? (driver, framework)
4. Permission available? (sudo, root)
5. Network available? (online, proxy)
6. Disk space sufficient? (free GB)
7. Auth available? (tokens, keys)

Stop at the first failure — that's the `disabled_reason`.
Store all failures in `all_failures` for the assistant.

---

## Edge Cases

| Case | Impact | Handling |
|------|--------|---------|
| ALL options disabled | User can't proceed | Show "Prerequisites needed" with full list |
| Only one available | Auto-select, no choice needed | Auto-select + explain why |
| Option was available, now isn't | User confusion (system changed) | Re-evaluate on page load |
| Risk high + available | User might not notice | Warning text + confirmation gate |
| disabled_reason too long | UI overflow | Truncate to 100 chars, full text in tooltip |
| learn_more URL dead | Broken link | Test URLs periodically, degrade gracefully |
| enable_hint requires purchase | Misleading | Be honest: "requires NVIDIA GPU hardware" |
| Container: many disabled | Overwhelming list | Group by reason category |
| Same reason for multiple options | Repetitive | Group: "CUDA 11.8, 12.1, 12.4: No NVIDIA GPU" |

---

## Traceability

| Topic | Source |
|-------|--------|
| Core principle (never remove) | scope-expansion §2.15 |
| disabled_reason + enable_hint + learn_more | scope-expansion §2.15 (code example) |
| Assistant needs disabled data | scope-expansion §2.15 ("assistant can't explain") |
| Constraint evaluation | domain-choices §constraint evaluation |
| Option schema | domain-choices §option schema |
| Risk levels | domain-kernel §risk classification |
| GPU constraints | domain-gpu §compute capability |
| UI treatment | domain-choices §UI treatment |
| Assistant panel | assistant-content-principles |
