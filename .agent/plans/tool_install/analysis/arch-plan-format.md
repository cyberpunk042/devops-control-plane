# Architecture: Plan Format

> ⚠️ **PHASE LABELS MAY BE STALE** — As of 2026-02-25, code has evolved far beyond
> what the phase roadmaps suggest. Many features labeled "Phase 4-8 future" are
> ALREADY IMPLEMENTED. See `audit-domain-docs.md` and `audit-missing-pieces.md`
> for the verified truth. Code is the source of truth, not these phase labels.


> This document defines the OUTPUT CONTRACT — what the resolver
> produces. Every consumer (frontend, CLI, TUI, executor, logger)
> works with this data structure.
>
> The plan is the BRIDGE between resolver and execution. The resolver
> reads recipes + system profile → produces a plan. The executor
> reads the plan → runs commands. The frontend reads the plan →
> renders the step modal.
>
> Obeys: arch-principles §1 (always present, disabled options in plan),
>        §4 (data feeds the assistant), §5 (deterministic),
>        §6 (extensibility by addition), §11 (resumable),
>        §12 (data is the interface)

---

## Overview

The plan is a dict returned by `resolve_install_plan()`.
It flows through:

```
resolve_install_plan(tool, system_profile, selections?)
  → plan dict (returned to caller)
    → POST /audit/install-plan response (JSON to frontend)
      → frontend step modal (rendered plan)
      → execute_plan() (runs commands via SSE)
```

The plan is a SELF-CONTAINED document. A consumer receiving the plan
dict has EVERYTHING needed to render the UI and execute the install,
without making additional API calls for explanation text.

---

## Plan Structure (Phase 2 — Simple Tools)

```python
{
    # ── Plan identity ─────────────────────────────────────────

    "tool": str,             # tool ID (e.g., "cargo-outdated")
    "label": str,            # human-readable name (e.g., "cargo-outdated")

    # ── Resolution result ─────────────────────────────────────

    "already_installed": bool,  # True → tool is on PATH, nothing to do
    "error": str | None,        # Non-None → resolution failed
                                # e.g., "No install method available for
                                #        Terraform on this system"

    # ── Error context (only when error is set) ────────────────

    "available_methods": list[str] | None,
    # Methods the recipe supports but none works on this system.
    # Example: ["snap", "brew"] — the user could install snap or brew.

    "suggestion": str | None,
    # Human-readable suggestion for resolving the error.
    # Example: "Install snap or brew to enable Terraform installation."

    # ── Plan-level flags ──────────────────────────────────────

    "needs_sudo": bool,
    # True if ANY step in the plan needs sudo.
    # The frontend uses this to show the sudo password prompt
    # ONCE before execution starts.

    "risk_summary": {
        "level": str,          # "low" | "medium" | "high" — highest step risk
        "counts": {"low": int, "medium": int, "high": int},
        "has_high": bool,      # convenience flag
        "has_medium": bool,    # convenience flag
    },
    # Aggregate risk metadata computed by ``_plan_risk()``.
    # Frontend uses this for risk indicators and confirmation gate logic.

    "risk_escalation": {       # OPTIONAL — only if user choices raised risk
        "from": str,           # e.g. "low"
        "to": str,             # e.g. "high"
        "reason": str,         # human-readable explanation
    } | None,
    # Present when user's choice selections escalated the plan risk
    # above the recipe's base ``risk`` field.

    "confirmation_gate": {
        "type": str,           # "none" | "single" | "double"
        "required": bool,
        "reason": str | None,  # why confirmation is required
        "confirm_text": str | None,  # text user must type (double only)
        "high_risk_steps": list[dict] | None,  # details of high-risk steps
    },
    # Frontend must enforce confirmation before execution starts.
    # - "none": no confirmation required (all steps low risk)
    # - "single": checkbox confirmation (at least one medium-risk step)
    # - "double": type-to-confirm dialog (at least one high-risk step)

    "warning": str | None,
    # System-level warning. Currently: "This plan requires sudo but
    # sudo is not available on this system."

    # ── Steps ─────────────────────────────────────────────────

    "steps": list[dict],
    # Ordered list of steps to execute.
    # Steps are executed in order. Each step is independent —
    # the executor can retry, skip, or pause between steps.
    #
    # In Phase 2: strictly linear (step 1 → step 2 → step 3).
    # In Phase 8+: DAG-based (steps may run in parallel).
}
```

### Successful plan example

```python
{
    "tool": "cargo-outdated",
    "label": "cargo-outdated",
    "already_installed": False,
    "needs_sudo": True,
    "steps": [
        {"type": "packages", "label": "Install system packages",
         "command": ["apt-get", "install", "-y", "curl", "pkg-config",
                     "libssl-dev", "libcurl4-openssl-dev"],
         "needs_sudo": True, "packages": ["curl", "pkg-config",
                                           "libssl-dev", "libcurl4-openssl-dev"]},
        {"type": "tool", "label": "Install Cargo (Rust)",
         "tool_id": "cargo",
         "command": ["bash", "-c", "curl ... | sh -s -- -y"],
         "needs_sudo": False},
        {"type": "tool", "label": "Install cargo-outdated",
         "tool_id": "cargo-outdated",
         "command": ["bash", "-c",
                     'export PATH="$HOME/.cargo/bin:$PATH" '
                     '&& cargo install cargo-outdated'],
         "needs_sudo": False},
        {"type": "verify", "label": "Verify cargo-outdated",
         "command": ["bash", "-c",
                     'export PATH="$HOME/.cargo/bin:$PATH" '
                     '&& cargo outdated --version'],
         "needs_sudo": False},
    ],
}
```

### Already installed example

```python
{
    "tool": "git",
    "label": "Git",
    "already_installed": True,
    "steps": [],
}
```

### Error example

```python
{
    "tool": "terraform",
    "label": "Terraform",
    "error": "No install method available for Terraform on this system.",
    "available_methods": ["snap", "brew"],
    "suggestion": "Install snap or brew to enable Terraform installation.",
}
```

---

## Step Types (Phase 2)

Every step has these common fields:

```python
{
    "type": str,          # step type identifier (see table below)
    "label": str,         # human-readable description for UI
    "command": list[str], # subprocess.run() command
    "needs_sudo": bool,   # whether sudo is required
}
```

### Type: `repo_setup`

Runs BEFORE install. Sets up a package repository (GPG key, source list).

```python
{
    "type": "repo_setup",
    "label": "Add Docker GPG key",
    "tool_id": "docker",          # which tool needs this repo
    "command": ["bash", "-c", "curl ... | gpg --dearmor ..."],
    "needs_sudo": True,
}
```

**Emitted when:** recipe has `repo_setup` for the selected PM.
**Order:** FIRST in plan — before packages step.

### Type: `packages`

Batch system package install. Multiple packages in one command.

```python
{
    "type": "packages",
    "label": "Install system packages",
    "command": ["apt-get", "install", "-y", "curl", "pkg-config", "libssl-dev"],
    "needs_sudo": True,           # always, except brew
    "packages": ["curl", "pkg-config", "libssl-dev"],  # for UI display
}
```

**Emitted when:** any tool or dependency needs a system package.
**Order:** AFTER repo_setup, BEFORE tool steps.
**Batching:** all system packages from the entire dependency tree
are batched into ONE packages step.
**Special case:** `brew` → `needs_sudo: False`.

### Type: `tool`

Individual tool install (not batchable into system packages).

```python
{
    "type": "tool",
    "label": "Install Cargo (Rust)",
    "tool_id": "cargo",           # which tool this step installs
    "command": ["bash", "-c", "curl ... | sh -s -- -y"],
    "needs_sudo": False,
}
```

**Emitted when:** tool's install method is NOT the system's primary PM
(pip, cargo, npm, curl-script, snap, brew when system PM is apt, etc.)
**Order:** AFTER packages, in dependency order (deepest dep first).
**Env wrapping:** if an earlier tool step set `post_env`, later tool
steps have the env prepended via `_wrap_with_env()`.

### Type: `post_install`

Action after install: start service, add user to group, etc.

```python
{
    "type": "post_install",
    "label": "Start Docker daemon",
    "tool_id": "docker",
    "command": ["systemctl", "start", "docker"],
    "needs_sudo": True,
}
```

**Emitted when:** recipe has `post_install` steps AND the step's
`condition` evaluates to True against the system profile.
**Conditions:** `has_systemd`, `not_root`, `not_container`, `None`.
**Order:** AFTER all tool steps, BEFORE verify.

### Type: `verify`

Confirms the target tool is functional.

```python
{
    "type": "verify",
    "label": "Verify cargo-outdated",
    "command": ["bash", "-c",
               'export PATH="$HOME/.cargo/bin:$PATH" '
               '&& cargo outdated --version'],
    "needs_sudo": False,
}
```

**Emitted when:** recipe has `verify` field.
**Order:** LAST step in plan.
**Failure:** non-zero exit code means install completed but tool
isn't functional. The plan should warn, not error.

---

## Step Order (Phase 2 — Linear)

Steps are emitted in this fixed order:

```
1. repo_setup     (0 or more, from recipes that need repo config)
2. packages       (0 or 1, batched system packages)
3. tool           (0 or more, in dependency order, deepest first)
4. post_install   (0 or more, condition-filtered)
5. verify         (0 or 1, for the TARGET tool only)
```

**Why this order:**
- Repos must exist before packages can be installed from them
- System packages must exist before tools that compile against them
- Tool dependencies must be installed before the tools that need them
- Services must be started after the daemon is installed
- Verification runs after everything is in place

---

## Plan Extensions (Phases 4-8)

These fields are ADDED to steps and to the plan dict.
Existing Phase 2 plans are unaffected — they don't have these fields,
and consumers check for presence before using them.

### Step IDs and dependencies (Phase 8)

```python
{
    "type": "tool",
    "id": "step_3",               # unique step ID within plan
    "depends_on": ["step_1"],     # this step can start after step_1 completes
    # ... other fields unchanged
}
```

**Phase 2:** `id` and `depends_on` are absent. All steps are linear.
The executor runs them in list order.

**Phase 8+:** `id` is present on every step. `depends_on` lists
prerequisite step IDs. Steps with all deps satisfied can run in
parallel. The executor dispatches based on the DAG.

### Risk levels (Phase 6)

```python
{
    "type": "tool",
    "label": "Recompile kernel with CONFIG_VFIO_PCI=y",
    "risk": "high",               # "low" | "medium" | "high" | "critical"
    "warning": "Requires kernel rebuild and system reboot",
    "estimated_time": "20-60 minutes",
    "rollback": "Boot old kernel from GRUB menu if the new kernel fails",
    "backup_step": "step_2",      # ID of the backup step that precedes this
    # ... other fields unchanged
}
```

**Phase 2:** `risk` is absent. All Phase 2 steps are implicitly low-risk.

**Phase 6+:** `risk` drives UI treatment:
| Risk | UI treatment | Gate |
|------|-------------|------|
| low | Normal | None |
| medium | Yellow highlight | Single confirm |
| high | Red highlight, expanded warning | Double confirm |
| critical | Full-page warning, rollback shown | Typed confirmation |

### Restart declaration (Phase 8)

```python
{
    "type": "tool",
    "label": "Install kernel modules",
    "restart_required": "system",  # "session" | "service" | "system" | None
    # ... other fields unchanged
}
```

When a step has `restart_required`:
- The executor pauses after this step
- Plan state is persisted to disk
- A restart prompt is shown to the user
- After restart, the executor resumes at the next step

### Choices and disabled options (Phase 4)

When the resolver runs in two-pass mode (complex recipe), the FIRST
response is not a plan — it's a choice request:

```python
{
    "tool": "pytorch",
    "label": "PyTorch",
    "mode": "choices",            # tells frontend to render choice UI
    "choices": [
        {
            "id": "gpu_backend",
            "label": "GPU Backend",
            "type": "single",
            "options": [
                {"id": "cpu", "label": "CPU only",
                 "available": True, "default": True},
                {"id": "cuda", "label": "NVIDIA CUDA",
                 "available": False,
                 "disabled_reason": "No NVIDIA GPU detected",
                 "enable_hint": "Install NVIDIA GPU and CUDA drivers"},
                {"id": "rocm", "label": "AMD ROCm",
                 "available": False,
                 "disabled_reason": "No AMD GPU detected",
                 "enable_hint": "Install AMD GPU with ROCm support"},
            ],
        },
    ],
    "inputs": [
        {"id": "cuda_version", "label": "CUDA Version",
         "type": "select", "options": ["11.8", "12.1", "12.4"],
         "default": "12.4",
         "condition": {"gpu_backend": "cuda"}},
    ],
}
```

The frontend renders choices, user selects, then sends selections
back. The SECOND call produces the actual plan:

```python
POST /audit/install-plan
{
    "tool": "pytorch",
    "selections": {"gpu_backend": "cpu"},
    "inputs": {}
}
→ returns a normal plan dict with steps
```

**Phase 2:** `mode` is absent. Plan is returned directly.
**Phase 4+:** `mode: "choices"` means render choices first.

### Data packs (Phase 7)

When a recipe has `data_packs`, the plan includes download steps:

```python
{
    "type": "data_pack",
    "label": "Download spaCy English model (large)",
    "command": ["python", "-m", "spacy", "download", "en_core_web_lg"],
    "needs_sudo": False,
    "size_mb": 300,               # for progress UI
    "optional": True,             # user can skip
    "default": True,              # pre-selected
}
```

### Config templates (Phase 8)

```python
{
    "type": "config",
    "label": "Write Docker daemon.json",
    "path": "/etc/docker/daemon.json",
    "content": '{"storage-driver": "overlay2"}',  # resolved template
    "needs_sudo": True,
    "backup": True,               # back up existing file first
}
```

---

## Execution Flow

### Phase 2 (linear, simple)

```
Frontend receives plan
  → show step list in modal
  → user clicks "Execute"
  → POST /audit/install-plan/execute {"plan": plan}
  → SSE stream opens
  → for each step:
      → display step label
      → run command (with sudo if needed)
      → stream stdout/stderr to modal
      → mark step ✅ or ❌
  → close stream
  → re-run audit scan to refresh tool availability
```

### Phase 4+ (two-pass, choices)

```
Frontend requests plan
  → POST /audit/install-plan {"tool": "pytorch"}
  → response has mode: "choices"
  → render choice UI
  → user selects options, fills inputs
  → POST /audit/install-plan {"tool": "pytorch", "selections": {...}}
  → response is a normal plan dict
  → execute as above
```

### Phase 8+ (parallel, resumable)

```
Frontend receives plan with step IDs and depends_on
  → execute endpoint detects DAG shape (any step has depends_on)
  → dispatches to execute_plan_dag() via ThreadPoolExecutor
  → single SSE stream with events from queue-based bridge
    (parallel steps funnel events through queue.Queue → SSE generator)
  → if step declares restart_required:
      → persist plan state
      → show restart prompt
      → after restart, resume from persisted state via /resume endpoint
```

---

## Determinism Contract

Given the SAME inputs:
- `tool` (string)
- `system_profile` (dict from `_detect_os()`)
- `selections` (dict, Phase 4+)
- `inputs` (dict, Phase 4+)

The resolver MUST produce the SAME plan. Every time.

What CAN change between invocations:
- `shutil.which()` results (tool installed between calls)
- `_is_pkg_installed()` results (package installed between calls)
- Dynamic version lists (fetched from API, cached with TTL)

What MUST NOT change:
- Step type assignment (batchable vs tool)
- Step ordering (dependency order is deterministic)
- Method selection (same prefer + same PM = same method)
- Condition evaluation (same profile = same conditions)

---

## API Contract

### Request: `POST /audit/install-plan`

```python
# Phase 2 — simple
{"tool": "cargo-outdated"}

# Phase 4+ — with answers (choice selections)
{"tool": "pytorch", "answers": {"variant": "cpu"}}
```

### Request: `POST /audit/install-plan/execute`

```python
# Phase 2 — simple
{"tool": "cargo-outdated", "sudo_password": "..."}

# Phase 4+ — with answers
{"tool": "pytorch", "answers": {"variant": "cuda"}, "sudo_password": "..."}
```

Response is an SSE stream with events:
- `step_start` — step index, label, total count
- `log` — stdout/stderr line
- `step_done` — step completed (may include `elapsed_ms`, `skipped`)
- `step_failed` — step failed (includes `error`, may include `needs_sudo`)
- `done` — plan finished (includes `ok`, `plan_id`, `message`)

### Request: `GET /audit/install-plan/pending`

Returns a list of plans that can be resumed (status: paused, running, failed).

```python
# Response
{
    "plans": [
        {
            "plan_id": str,        # UUID
            "tool": str,           # tool ID
            "status": str,         # "paused" | "running" | "failed"
            "completed_count": int, # number of finished steps
            "total_steps": int,    # total number of steps in original plan
        },
    ]
}
```

### Request: `POST /audit/install-plan/resume`

Resumes a previously interrupted plan from its last completed step.

```python
{"plan_id": "abc123...", "sudo_password": "..."}
```

Response is an SSE stream with the same event types as `/execute`.
The `step` index in events is relative to the remaining steps (0-based).
Events include `resumed_offset` in `step_start` to indicate how many
steps were already completed before this resume.

### Response codes

| Code | Meaning |
|------|---------|
| 200 | Plan generated successfully (or already installed) |
| 400 | Missing or invalid `tool` parameter / `plan_id` |
| 422 | Tool exists but can't be installed on this system |

### Response shape

Always a JSON dict. Consumers check:
- `"error" in plan` → resolution failed
- `plan["already_installed"]` → nothing to do
- `plan.get("mode") == "choices"` → render choices (Phase 4+)
- Otherwise → `plan["steps"]` is the executable plan

---

## Extensibility Rules

1. **Adding new step types:** Add a new `"type"` value. Existing
   consumers skip unknown types (or render a generic fallback).

2. **Adding new fields to steps:** New fields (risk, restart, id,
   depends_on) are absent in Phase 2 plans. Consumers check for
   presence: `step.get("risk", "low")`.

3. **Adding new plan-level fields:** Same rule. New fields are
   additive. `plan.get("mode")` returns None for Phase 2 plans.

4. **Never changing the meaning of existing fields:** `"type": "tool"`
   always means a single tool install step. If we need a multi-step
   build, that's `"type": "build"` — a NEW type.

---

## Consumers

| Consumer | What it reads | Phase |
|----------|---------------|-------|
| Frontend step modal | steps, label, needs_sudo, type | 2 |
| Frontend assistant | label, suggestion, disabled_reason, warning, description, estimated_time, risk | 2, 4+ |
| SSE executor (linear) | command, needs_sudo | 2 |
| SSE executor (DAG) | command, needs_sudo, depends_on, id | 8 |
| Plan persist/resume | plan_id, steps, completed_steps, status | 8 |
| DAG dispatcher | id, depends_on | 8 |
| Risk UI | risk, warning, rollback | 6 |
| Choices UI | mode, choices, inputs | 4 |
| CLI executor | steps, command, sudo_password | 2 |

---

## Traceability

| Field | First defined in | Phase |
|-------|-----------------|-------|
| tool, label | phase2.3 §4 | 2 |
| already_installed | phase2.3 §4 | 2 |
| error, suggestion, available_methods | phase2.3 §7 scenario 7 | 2 |
| needs_sudo (plan-level) | phase2.3 §4 | 2 |
| steps | phase2.3 §4 | 2 |
| step.type (repo_setup, packages, tool, post_install, verify) | phase2.3 §4 | 2 |
| step.command, step.needs_sudo, step.label | phase2.3 §4 | 2 |
| step.tool_id | phase2.3 §4 | 2 |
| step.packages | phase2.3 §4 | 2 |
| step.id, step.depends_on | scope-expansion §2.17 | 8 |
| step.risk, step.warning, step.rollback | scope-expansion §2.5 | 6 |
| step.estimated_time | scope-expansion §2.5 | 6 |
| step.restart_required | scope-expansion §2.8 | 8 |
| step.backup_step | scope-expansion §2.5 | 6 |
| mode: "choices" | scope-expansion §2.1 | 4 |
| choices, inputs (plan-level) | scope-expansion §2.1, §2.2 | 4 |
| choice.option.description | scope-expansion §2.1 | 4 |
| choice.option.estimated_time | scope-expansion §2.1 | 4 |
| choice.option.risk, choice.option.warning | scope-expansion §2.1 | 4 |
| install_variants | scope-expansion §2.1 | 4 |
| plan_id | alignment-arch-docs (M1) | 8 |
| step.type: "data_pack" | scope-expansion §2.10 | 7 |
| step.type: "config" | scope-expansion §2.12 | 8 |
| step.type: "build" | scope-expansion §2.4 | 5 |
