# Domain: Choices

> This document catalogs the decision tree architecture for tool
> installation: choice types (single, multi, conditional),
> branching, depends_on, auto-selection when only one option,
> constraint evaluation, and the two-pass resolver.
>
> SOURCE DOCS: scope-expansion §2.14 (branching decision trees),
>              scope-expansion §2.15 (disabled options),
>              scope-expansion §3 (recipe format evolution),
>              arch-plan-format (plan format schema)

---

## Overview

Simple tools (ruff, git, jq) have NO choices — one install
command per platform. Complex tools (PyTorch, OpenCV) have
MULTIPLE decision points that create a branching tree.

### Simple vs complex

| Type | Example | Choices | Resolver |
|------|---------|---------|----------|
| Simple | ruff, git, curl | None | Single-pass: recipe → plan |
| Complex | PyTorch, OpenCV | GPU variant, method, version | Two-pass: discover → select → plan |

### Detection

```python
if "choices" in recipe:
    # Two-pass: return choices first, then resolve with selections
else:
    # Single-pass: resolve directly (current behavior)
```

### Phase 2 vs Phase 4

| Phase | Choice capability |
|-------|------------------|
| Phase 2 | No choices. All 42 tools are simple recipes. Platform variant is automatic (not a user choice). |
| Phase 4 | Full decision tree: choices, inputs, constraints, two-pass resolver. |

---

## Choice Types

### Single choice (radio buttons)

User picks exactly ONE option:

```python
{
    "id": "method",
    "type": "single",
    "label": "Install Method",
    "options": [
        {"id": "pip", "label": "pip (recommended)", "default": True},
        {"id": "system", "label": "System package"},
        {"id": "source", "label": "Build from source",
         "warning": "Build takes 20-60 minutes"},
    ],
}
```

### Multi choice (checkboxes)

User picks ZERO or MORE options:

```python
{
    "id": "extras",
    "type": "multi",
    "label": "Extra Components",
    "options": [
        {"id": "contrib", "label": "Contrib modules", "default": True},
        {"id": "cuda", "label": "CUDA support",
         "requires": {"hardware": {"gpu.nvidia.present": True}}},
        {"id": "tests", "label": "Include test suite"},
    ],
    "min_select": 0,
    "max_select": None,
}
```

### Conditional choice

Appears ONLY when a previous choice has a specific value:

```python
{
    "id": "cuda_version",
    "type": "single",
    "label": "CUDA Version",
    "condition": {"choice": "gpu", "value": "cuda"},
    # Only shown when gpu == "cuda"
    "options": [
        {"id": "cu118", "label": "CUDA 11.8"},
        {"id": "cu121", "label": "CUDA 12.1", "default": True},
        {"id": "cu124", "label": "CUDA 12.4"},
    ],
}
```

---

## Choice Schema

### Full schema

```python
{
    "id": str,              # unique identifier
    "type": str,            # "single" | "multi"
    "label": str,           # display label
    "description": str,     # optional longer text
    "options": list[dict],  # list of option objects
    "condition": dict,      # when to show this choice
    "min_select": int,      # for multi: minimum selections (default 0)
    "max_select": int,      # for multi: maximum selections (default None)
    "depends_on": list[str],# other choice IDs that must be resolved first
}
```

### Option schema

```python
{
    "id": str,              # unique identifier
    "label": str,           # display label
    "description": str,     # optional explanation
    "available": bool,      # True if selectable on this system
    "default": bool,        # pre-selected?
    "disabled_reason": str, # why unavailable (if available=False)
    "enable_hint": str,     # how to make it available
    "learn_more": str,      # URL for more info
    "warning": str,         # caution text (still selectable)
    "note": str,            # informational text
    "requires": dict,       # hardware/software requirements
    "risk": str,            # "low" | "medium" | "high"
}
```

---

## Branching

### Tree structure

```
Install OpenCV
├─ CHOICE: method? → [pip, system, source]
│  ├─ pip
│  │  ├─ CHOICE: variant? → [full, headless]
│  │  ├─ CHOICE: version? → [4.9, 4.10]
│  │  └─ LEAF: pip install opencv-python==4.10.0
│  ├─ system
│  │  ├─ CONSTRAINT: package available?
│  │  └─ LEAF: apt-get install python3-opencv
│  └─ source
│     ├─ CHOICE: gpu? → [none, cuda, rocm]
│     │  ├─ cuda
│     │  │  ├─ CONSTRAINT: nvidia GPU?
│     │  │  ├─ CHOICE: cuda version? → [11.8, 12.1, 12.4]
│     │  │  │  └─ CONSTRAINT: driver compat?
│     │  │  └─ ... build flags
│     │  └─ none
│     ├─ CHOICE: extra modules? → [contrib, no-contrib]
│     ├─ REQUIRES: cmake, gcc, python3-dev, numpy
│     └─ LEAF: cmake -B build ... && make && make install
```

### How branching works

1. Each CHOICE creates a branch point
2. User's selection determines which branch to follow
3. Selecting one branch may REVEAL new choices (conditional)
4. Selecting one branch may HIDE previous choices
5. The final LEAF is the concrete install command

### Dependency between choices

```python
# cuda_version depends on gpu choice being "cuda"
{
    "id": "cuda_version",
    "depends_on": ["gpu"],
    "condition": {"choice": "gpu", "value": "cuda"},
}
```

When `gpu` changes from "cuda" to "none":
- `cuda_version` choice disappears from UI
- Its value is cleared from selections

---

## Two-Pass Resolver

### Pass 1: Discovery

Returns WHAT choices exist for this tool on this system:

```python
def resolve_choices(tool: str, profile: dict) -> dict:
    recipe = TOOL_RECIPES[tool]
    if "choices" not in recipe:
        return {"tool": tool, "choices": []}

    choices = []
    for choice_def in recipe["choices"]:
        choice = {
            "id": choice_def["id"],
            "type": choice_def["type"],
            "label": choice_def["label"],
            "options": [],
        }
        for opt in choice_def["options"]:
            option = {
                "id": opt["id"],
                "label": opt["label"],
                "available": _evaluate_requires(opt.get("requires"), profile),
            }
            if not option["available"]:
                option["disabled_reason"] = _get_reason(opt["requires"], profile)
                option["enable_hint"] = opt.get("enable_hint")
            choices.append(option)
        choices.append(choice)

    return {"tool": tool, "choices": choices}
```

### Pass 2: Plan generation

Takes user selections and generates the concrete install plan:

```python
def resolve_install_plan(tool: str, profile: dict,
                          selections: dict) -> dict:
    recipe = TOOL_RECIPES[tool]
    variant_key = _resolve_variant(recipe, selections)
    install_cmd = recipe["install_variants"][variant_key]

    steps = []
    # 1. System deps
    # 2. Runtime deps
    # 3. Install command (with template substitution)
    # 4. Post-install
    # 5. Verify
    # 6. Data packs (if selected)

    return {"tool": tool, "steps": steps}
```

### Frontend flow

```
1. Frontend calls: GET /api/tool/{name}/choices
   └── Backend: resolve_choices(tool, profile) → choices JSON

2. Frontend renders choice UI (radio buttons, checkboxes)
   └── User makes selections
   └── Conditional choices appear/disappear

3. Frontend calls: POST /api/tool/{name}/plan
   └── Body: {"selections": {"method": "source", "gpu": "cuda", ...}}
   └── Backend: resolve_install_plan(tool, profile, selections) → plan

4. Frontend shows plan preview
   └── User confirms

5. Frontend calls: POST /api/tool/{name}/execute
   └── Backend executes plan steps via SSE
```

---

## Constraint Evaluation

### How constraints work

```python
def _evaluate_requires(requires: dict | None,
                        profile: dict) -> bool:
    if not requires:
        return True

    if "hardware" in requires:
        hw = requires["hardware"]
        if hw.get("gpu.nvidia.present"):
            if not profile.get("gpu", {}).get("nvidia", {}).get("present"):
                return False
        if hw.get("gpu.amd.present"):
            if not profile.get("gpu", {}).get("amd", {}).get("present"):
                return False

    if "binaries" in requires:
        for binary in requires["binaries"]:
            if not shutil.which(binary):
                return False

    if "network" in requires:
        if not profile.get("network", {}).get("online"):
            return False

    return True
```

### Constraint types

| Constraint | Example | Source |
|-----------|---------|--------|
| GPU present | `gpu.nvidia.present: True` | domain-gpu |
| Compute capability | `gpu.nvidia.compute_capability: ">=7.0"` | domain-gpu |
| Binary exists | `binaries: ["cmake"]` | shutil.which() |
| Package manager | `pm: "apt"` | Fast profile |
| Init system | `init: "systemd"` | domain-services |
| Network | `network: True` | Connectivity check |
| Disk space | `disk_free_gb: ">=10.0"` | domain-hardware-detect |
| Architecture | `arch: "amd64"` | Fast profile |
| Auth | `auth: "hf_token"` | domain-ml-ai |

---

## Auto-Selection

### When only one option is available

If constraint evaluation leaves only ONE available option,
it can be auto-selected:

```python
def _auto_select(choice: dict) -> str | None:
    available = [o for o in choice["options"] if o["available"]]
    if len(available) == 1:
        return available[0]["id"]
    return None
```

### When forced by system

```
CHOICE: Compute Platform → [CPU, CUDA 11.8, CUDA 12.1, ROCm]

System has no GPU:
  CPU        ✅ available
  CUDA 11.8  ❌ disabled (no NVIDIA GPU)
  CUDA 12.1  ❌ disabled (no NVIDIA GPU)
  ROCm       ❌ disabled (no AMD GPU)

→ Auto-select CPU (only option)
→ Show note: "CPU selected automatically (no GPU detected)"
```

### When forced by depends_on

```
CHOICE: Install Method → user picks "pip"

CHOICE: cmake version?
→ Not shown (cmake only needed for source build)
→ No selection needed
```

---

## Disabled Options

### Always present, never removed

**Critical principle:** Options that can't be used are NOT
removed from the list. They are returned with `available: False`.

Why? The assistant panel needs to explain:
- What's unavailable and why
- How to enable it
- What the user is missing

### Disabled option format

```python
{
    "id": "cuda",
    "label": "NVIDIA CUDA acceleration",
    "available": False,
    "disabled_reason": "No NVIDIA GPU detected (lspci shows no NVIDIA device)",
    "enable_hint": "Install a compatible NVIDIA GPU and the "
                   "proprietary NVIDIA driver to enable CUDA support",
    "learn_more": "https://developer.nvidia.com/cuda-gpus",
}
```

### UI treatment

```
┌─ Compute Platform ─────────────────────────────┐
│                                                  │
│  ● CPU only                              ✅     │
│    Works on any system                          │
│                                                  │
│  ○ CUDA 11.8                             🔒     │
│    No NVIDIA GPU detected                       │
│    ℹ️ Install NVIDIA GPU + driver to enable      │
│                                                  │
│  ○ CUDA 12.1                             🔒     │
│    No NVIDIA GPU detected                       │
│                                                  │
│  ○ ROCm 5.7                              🔒     │
│    No AMD GPU detected                          │
│                                                  │
└──────────────────────────────────────────────────┘
```

---

## Complex Example: PyTorch

```python
"pytorch": {
    "label": "PyTorch",
    "choices": [
        {
            "id": "compute",
            "type": "single",
            "label": "Compute Platform",
            "options": [
                {"id": "cpu", "label": "CPU only", "default": True},
                {"id": "cuda118", "label": "CUDA 11.8",
                 "requires": {"hardware": {"gpu.nvidia.present": True}}},
                {"id": "cuda121", "label": "CUDA 12.1",
                 "requires": {"hardware": {"gpu.nvidia.present": True}}},
                {"id": "cuda124", "label": "CUDA 12.4",
                 "requires": {"hardware": {"gpu.nvidia.present": True,
                              "gpu.nvidia.compute_capability": ">=7.0"}}},
                {"id": "rocm57", "label": "ROCm 5.7",
                 "requires": {"hardware": {"gpu.amd.present": True}}},
            ],
        },
    ],
    "install_variants": {
        "cpu":      {"command": _PIP + ["install", "torch", "--index-url",
                     "https://download.pytorch.org/whl/cpu"]},
        "cuda118":  {"command": _PIP + ["install", "torch", "--index-url",
                     "https://download.pytorch.org/whl/cu118"]},
        "cuda121":  {"command": _PIP + ["install", "torch", "--index-url",
                     "https://download.pytorch.org/whl/cu121"]},
        "cuda124":  {"command": _PIP + ["install", "torch", "--index-url",
                     "https://download.pytorch.org/whl/cu124"]},
        "rocm57":   {"command": _PIP + ["install", "torch", "--index-url",
                     "https://download.pytorch.org/whl/rocm5.7"]},
    },
}
```

---

## Plan Step Dependencies (depends_on)

### For parallel execution (Phase 8)

```python
"steps": [
    {"id": "step1", "type": "packages", "label": "Install build deps"},
    {"id": "step2", "type": "tool", "label": "Build tool A",
     "depends_on": ["step1"]},
    {"id": "step3", "type": "tool", "label": "Build tool B",
     "depends_on": ["step1"]},
    # step2 and step3 can run in parallel
    {"id": "step4", "type": "verify", "label": "Verify all",
     "depends_on": ["step2", "step3"]},
]
```

### Rules

| Rule | Description |
|------|------------|
| No depends_on | Step runs after previous step (linear) |
| depends_on: [X] | Step runs after step X completes |
| depends_on: [X, Y] | Step runs after BOTH X and Y complete |
| Cycle detection | depends_on must not create cycles |
| Phase 2 | All steps are linear (no depends_on) |
| Phase 8 | Steps can declare dependencies for parallelism |

---

## Edge Cases

| Case | Impact | Handling |
|------|--------|---------|
| All options disabled | User can't proceed | Show explanation, suggest prerequisites |
| Only one option available | Unnecessary choice | Auto-select, show note |
| Conditional choice has no trigger | Never shown | Validate recipe at load time |
| Circular depends_on | Infinite loop | Cycle detection on recipe load |
| User changes earlier choice | Later choices invalidated | Clear dependent selections |
| Choice references unknown choice | broken recipe | Validate recipe at load time |
| No GPU but GPU tool requested | All GPU options disabled | Auto-select CPU |
| Network offline + choice needs download | Option disabled | Disable with reason |

---

## Traceability

| Topic | Source |
|-------|--------|
| Branching decision trees | scope-expansion §2.14 |
| Disabled options principle | scope-expansion §2.15 |
| Two-pass resolver | scope-expansion §2.14 (Pass 1/Pass 2) |
| Simple vs complex recipes | scope-expansion §3 (recipe format) |
| PyTorch choices | scope-expansion §2.10, domain-ml-ai |
| GPU constraint evaluation | domain-gpu §hardware constraints |
| Parallel step deps | scope-expansion §2.17 (depends_on) |
| Phase 4 roadmap | scope-expansion §Phase 4 |
| Plan format | arch-plan-format |
