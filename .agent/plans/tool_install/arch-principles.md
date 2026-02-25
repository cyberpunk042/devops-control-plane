# Architecture: Principles

> ⚠️ **PHASE LABELS MAY BE STALE** — As of 2026-02-25, code has evolved far beyond
> what the phase roadmaps suggest. Many features labeled "Phase 4-8 future" are
> ALREADY IMPLEMENTED. See `audit-domain-docs.md` and `audit-missing-pieces.md`
> for the verified truth. Code is the source of truth, not these phase labels.


> This is the constitution of the tool installation system.
> Every other document in this directory references these principles.
> Every design decision must trace back to one or more of these.
>
> If a principle needs to change, change it HERE and propagate.
> Principles are not suggestions — they are invariants.

---

## Identity

This system is the provisioning engine for the devops control plane.
It handles EVERYTHING from simple CLI tool installs to complex
multi-step software provisioning with GPU detection, kernel management,
build-from-source chains, data pack downloads, and system configuration.

Nothing is off-limits. If it can be automated with proper safeguards,
it gets a recipe and it's available from the admin panel.

The system exists across three interfaces:
- **CLI** (root commands, console scripts)
- **TUI** (terminal UI, interactive)
- **WEB** (admin panel — the primary interface for provisioning)

All three interfaces share the SAME resolver, SAME recipes, SAME
execution engine. The web admin panel is where the full interactive
experience lives — choices, disabled options, risk warnings, progress,
the assistant panel explaining everything.

---

## Principles

### 1. Always present, sometimes disabled

Every option at every choice point is ALWAYS returned in the response.
If an option can't be used on this system, it is marked
`available: false` with a `disabled_reason` and an `enable_hint`.

**Why:** The assistant panel needs to tell the user what they're
missing and how to get it. If we remove unavailable options from the
response, the user will never know that CUDA acceleration exists for
PyTorch, or that building from source would give them more features.

**Example:**
```json
{
    "id": "cuda",
    "label": "NVIDIA CUDA acceleration",
    "available": false,
    "disabled_reason": "No NVIDIA GPU detected (lspci shows no device)",
    "enable_hint": "Install a compatible NVIDIA GPU and CUDA drivers"
}
```

**Invariant:** No code path may filter out unavailable options from
any response. Rendering logic may STYLE them differently (greyed out,
crossed out, collapsed), but they MUST be present in the data.

---

### 2. User decides, system suggests

The resolver recommends defaults based on detected system state.
The user can accept defaults or override any choice.

When only one option is available at a choice point, it is
auto-selected and the user is informed — but the choice point
STILL appears in the data (with the single available option marked
as `auto_selected: true` and the disabled alternatives visible).

**Why:** The user owns their system. The system is a tool, not an
authority. If the user wants to install the CPU version of PyTorch
on a machine with an NVIDIA GPU, that's their choice.

**Invariant:** The resolver NEVER silently makes a choice that would
change what gets installed. Automatic selection only applies when
there is exactly ONE available option at a forced choice point.

---

### 3. Branches are explicit

Every decision point is a named choice with visible options.
No hidden conditional logic. No implicit fallbacks.

If the install method changes based on the detected platform, that's
a choice point — even if the system auto-selects because only one
option is available.

**Why:** Hidden logic creates debugging nightmares. When something
goes wrong, the user must be able to see every decision the system
made, why it made that decision, and what the alternatives were.

**Concrete form:**
```
Install Docker
├── CHOICE: install method
│   ├── apt (available on Debian/Ubuntu)
│   ├── dnf (available on Fedora/RHEL)
│   ├── brew (available on macOS)
│   └── snap (available if snapd + systemd)
├── AUTO-SELECTED: apt (on this Ubuntu 22.04 system)
└── The three unavailable options are in the response with reasons
```

**Invariant:** If a recipe produces different commands on different
systems, the branching logic must be a named choice in the recipe
format — never an if/else buried in resolver code.

---

### 4. The assistant panel is the explainer

All informational data flows FROM the resolver data TO the assistant
panel. The assistant panel does not generate information — it
RENDERS the information that the resolver already computed.

Data fields that feed the assistant:
- `disabled_reason` — why an option is unavailable
- `enable_hint` — what to do to make it available
- `warning` — risk or cost information
- `estimated_time` — how long a step will take
- `risk` — low / medium / high
- `description` — what this option does differently
- `learn_more` — URL for external documentation
- `rollback` — what to do if things go wrong

**Why:** The assistant panel is not a separate system with its own
logic. It's a RENDERER of resolver data. This means the backend is
the single source of truth for all explanations, and they can be
tested without a browser.

**Invariant:** No informational text in the assistant panel may be
hardcoded in frontend JavaScript. All explanation text must originate
from the recipe data or resolver response.

---

### 5. Plans are deterministic

Given the same inputs (tool + system profile + user selections),
the resolver MUST produce the exact same plan. Every time.

No randomness. No time-dependent logic (except for dynamic version
lists, which are cached with TTL). No external fetches during
resolution (only during execution).

**Why:** Reproducibility. If a user reports "this plan didn't work,"
we can reproduce it by replaying the same inputs. If resolution
depended on which GitHub API response we got at 3am, debugging
becomes impossible.

**Invariant:** `resolve_install_plan(tool, profile, selections)`
is a pure function of its inputs (modulo dynamic version cache).

---

### 6. Extensibility by addition

The system grows by ADDING, never by restructuring.

- Adding a new key to a recipe dict doesn't break existing recipes
- Adding a new step type to the plan format doesn't break existing plans
- Adding a new field to the system profile doesn't break existing consumers
- Adding a new phase doesn't break existing phases

**Format implications:**
- Recipes are dicts (not tuples, not arrays with positional meaning)
- Plans are dicts with typed step lists
- System profiles are dicts with nested dicts
- API responses are dicts (JSON objects, not arrays)

**The compatibility test:** Can Phase 2's simple recipe for `ruff`
still work unchanged after Phase 6 adds GPU detection, Phase 7 adds
data packs, and Phase 8 adds restart management? Yes — because ruff's
recipe has no `choices`, no `gpu`, no `data_packs`, no `restart`.
The resolver sees the recipe has no complex fields and resolves it
via single-pass. Same code path. Same result.

**Invariant:** No PR may add functionality by changing the meaning
of an existing field. New capabilities = new fields.

---

### 7. Nothing is off-limits with safeguards

Kernel recompilation, GPU driver installation, bootloader updates,
kernel module loading, service restarts, group membership changes —
all are automatable. The system provides the recipe. The user
decides whether to execute.

**Safeguard hierarchy:**

| Risk level | UI treatment | Gate |
|-----------|-------------|------|
| `low` | Normal step, auto-proceed if previous succeeded | None |
| `medium` | Yellow highlight, "Confirm?" prompt | Single confirm |
| `high` | Red highlight, expanded warning, backup shown | Double confirm |
| `critical` | Full-page warning, rollback instructions, backup required | Explicit typed confirmation |

**Mandatory safeguards for high/critical operations:**
1. **Confirmation gate** — never auto-executed
2. **Backup step** — save current state before modifying
3. **Rollback instructions** — in the plan output, visible to user
4. **Restart awareness** — mark which restart type is needed
5. **Estimated time** — user knows upfront (kernel build: 20-60 min)

**Invariant:** No recipe may include a `risk: "high"` or
`risk: "critical"` step without a corresponding `rollback` field
in the recipe or step data.

---

### 8. Interactive from the admin panel

Everything the system can do is accessible from the web admin UI.
The full experience: browse tools → see choices → configure inputs →
review plan → confirm → execute → see progress → verify.

The CLI and TUI are alternative interfaces. They have the same
capabilities (same resolver, same execution) but may present choices
differently (CLI: flags/prompts, TUI: interactive menus).

**The admin panel is NOT a thin wrapper.** It is the PRIMARY
interface for the provisioning system. The resolver response is
designed FOR the admin panel — choices, disabled options, risk
levels, progress streams — all are structured for rich web rendering.

**Invariant:** Any new capability added to the resolver must be
renderable in the admin panel. If we add a new choice type, the
frontend must handle it. If we add a new step type, the step modal
must render it.

---

### 9. Two-tier detection

The system detects the environment in TWO tiers:

**Fast tier** (runs every L0 audit scan, ~120ms budget):
- OS, distro, family, version
- Package managers available
- Container environment
- Capabilities (systemd, sudo, root)
- Library versions (openssl, glibc)

**Deep tier** (runs on demand, cached with TTL, ~2s budget):
- GPU hardware (NVIDIA, AMD, Intel)
- CUDA/ROCm version and capabilities
- Kernel config and loaded modules
- Disk space and filesystem type
- Network connectivity and proxy
- Shell type and health
- Compiler availability and build toolchain

**Why:** GPU detection (`lspci`, `nvidia-smi`) can take 200-500ms.
Running this on every audit scan wastes time. The deep tier runs
when the user enters a provisioning flow (opens an install modal,
starts a complex recipe) and is cached for the session.

**Invariant:** Fast tier detections NEVER call external tools that
could take >200ms. Deep tier detections ALWAYS have a timeout and
ALWAYS cache results.

---

### 10. Evolution, not revolution

The system grows phase by phase. Each phase is independently
shippable and valuable. No phase exists solely to "prepare" for
a future phase — each phase solves real problems NOW.

Simple recipes (Phase 2) → choice trees (Phase 4) →
build-from-source (Phase 5) → GPU/kernel (Phase 6).

At no point does an earlier phase need to be "thrown away" to
support a later phase. Phase 2's ruff recipe still works unchanged
in Phase 8.

**What this means for code:**
- Phase 2 code checks `if "choices" in recipe:` — if not, single-pass
- Phase 4 adds the `choices` handling — existing code untouched
- Phase 6 adds GPU to system profile — existing profile consumers
  don't need changes, they just don't use the GPU fields

**Invariant:** No phase implementation may require modifying
the fundamental structure of a previous phase's data format.
Growth is additive.

---

### 11. Resumable plans

Plans can be interrupted (network failure, system restart, user
closes browser) and resumed later.

**What this requires:**
- Plan state persisted to disk (which steps completed, which failed)
- Session-aware: plan bound to a session, resumable from same session
- Restart-aware: steps that declare `restart_required: "system"` cause
  the plan to persist and offer resume after reboot

**Why:** Kernel recompilation takes 20-60 minutes, then needs a
reboot. Without resumable plans, the user would have to re-run
everything after reboot. With resumable plans, the execution picks
up at the next step.

**Invariant:** Plan execution must NEVER assume it runs
start-to-finish without interruption.

---

### 12. Data is the interface

The resolver produces DATA (dicts, JSON). The frontend renders DATA.
There is no "smart backend that generates HTML" or "smart frontend
that decides what to install."

The DATA contains:
- What to install (commands)
- Why (descriptions, explanations)
- What could go wrong (risks, warnings)
- What's available and what's not (choices, disabled options)
- How long it will take (time estimates)
- What to do if it fails (rollback instructions)

**Why:** This separation means:
- Backend can be tested without browser
- Frontend can be redesigned without touching resolver
- CLI/TUI/WEB all consume the same data
- Data can be serialized, cached, compared, logged

**Invariant:** The resolver response must be self-contained —
a consumer receiving the JSON response has EVERYTHING needed to
render the full install experience, without making additional
API calls for explanation text.

---

## Cross-reference

These principles are applied in:

| Document | Which principles it must obey |
|----------|-------------------------------|
| `arch-recipe-format.md` | 1, 3, 6, 7, 12 |
| `arch-system-model.md` | 9, 6 |
| `arch-plan-format.md` | 1, 4, 5, 6, 7, 11, 12 |
| All `domain-*.md` docs | 1, 7, 8 |
| All `phase*.md` docs | 6, 10 |

---

## Traceability

| Principle | First stated in | Real scenario that demands it |
|-----------|----------------|-------------------------------|
| Always present/disabled | scope-expansion §2.15 | CUDA option invisible → user never learns about GPU acceleration |
| User decides | scope-expansion §8.2 | User wants CPU PyTorch on GPU machine for testing |
| Explicit branches | scope-expansion §2.14 | OpenCV has 5+ choice points, hidden logic is undebuggable |
| Assistant = renderer | scope-expansion §8.4 | Frontend hardcoded text gets stale, untestable |
| Deterministic plans | scope-expansion §8.5 | "It worked yesterday" must be reproducible |
| Extensibility by addition | scope-expansion §5 | Phase 2 recipe must survive unchanged through Phase 8 |
| Nothing off-limits | scope-expansion §2.5 | Kernel module loading IS automatable with safeguards |
| Interactive from admin | scope-expansion §8.8 | CLI/TUI/WEB share resolver, admin panel is primary UX |
| Two-tier detection | phase1 §10 | nvidia-smi takes 300ms, shouldn't run on every L0 scan |
| Evolution not revolution | user rules (meanings.md) | Each phase is shippable, nothing gets thrown away |
| Resumable plans | scope-expansion §2.8 | Kernel reboot interrupts plan execution |
| Data is interface | (new, consolidation) | Backend testable without browser, CLI/TUI/WEB same data |
