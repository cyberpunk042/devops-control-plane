---
description: Tool remediation workflow — failure handlers, availability gates, scenario validation across 19 system presets
---

# Tool Remediation Audit Workflow

> **Prerequisite:** Run `/tool-coverage-audit` first. This workflow assumes
> the tool already has a complete recipe with `cli`, `install`, `needs_sudo`,
> and `verify` fields.
>
> **Reference:** `.agent/plans/tool_install/per-tool-full-spectrum-analysis.md`
> §"Remediation Handlers" and §"Availability Computation"

---

## Phase 1: Identify the tool's failure surface

For the tool being audited, determine:

### 1.1 What install methods does it use?
- Which PMs are in its recipe? (`apt`, `dnf`, `pip`, `cargo`, `_default`, `source`, etc.)
- Each install method falls into a **method family** that already has handlers or doesn't

### 1.2 What can go wrong?
For each install method, list realistic failure scenarios:
- **Network issues** — download fails, DNS resolution, proxy
- **Permission issues** — needs sudo, read-only rootfs
- **Dependency missing** — compiler, runtime, C library
- **Environment conflict** — PEP 668 for pip, version mismatch for cargo
- **Method-specific** — PPA required, repo not configured, key not imported

---

## Phase 2: Check existing handler coverage

File: `src/core/services/tool_install/data/remediation_handlers.py`

### The three layers (evaluated bottom-up, most specific first)

| Layer | Location | Scope | Example |
|-------|----------|-------|---------|
| **Layer 3** | Recipe's `on_failure` field | This tool only | `terraform` state lock |
| **Layer 2** | `METHOD_FAMILY_HANDLERS[method]` | All tools using this PM | pip PEP 668, cargo version |
| **Layer 1** | `INFRA_HANDLERS` | All tools, all methods | network down, disk full |

### Check process

1. **Layer 1 (INFRA_HANDLERS):** These always apply. Check if they cover the
   generic failures for your tool. They usually do — network, permissions, disk
   are already handled.

2. **Layer 2 (METHOD_FAMILY_HANDLERS):** Check if your tool's install method
   has handlers already:

   | Method family | Currently has handlers? |
   |---------------|----------------------|
   | `pip` | ✅ PEP 668, missing pip |
   | `cargo` | ✅ rustc version, gcc bug |
   | `npm` | ❌ Not yet — add if tool exposes npm failures |
   | `go` | ❌ Not yet — add if tool exposes go failures |
   | `apt`/`dnf`/`apk` | Covered by INFRA_HANDLERS |
   | `_default` | Covered by INFRA_HANDLERS |
   | `source` | ❌ Partially — toolchain check in availability gate only |

3. **Layer 3 (recipe on_failure):** Does this specific tool have unique failures
   that no other tool sharing its method would have?

If all failures are covered by existing layers → **no handler work needed**. Done.

---

## Phase 3: Add new handlers (when needed)

### 3.1 Handler structure
```python
{
    "pattern": r"regex matching stderr",     # what we detect
    "failure_id": "unique_failure_id",       # for tracking
    "category": "environment",               # environment|dependency|permissions|compiler|network|configuration
    "label": "Human-readable title",
    "description": "Multi-line explanation of what went wrong and why.",
    "example_stderr": "actual error output",  # optional, for testing
    "options": [
        # ... remediation options ...
    ],
}
```

### 3.2 Option structure
```python
{
    "id": "option-id",
    "label": "What this does",
    "description": "How it fixes the issue",
    "icon": "📦",
    "recommended": True,                     # only ONE per handler
    "strategy": "install_dep",               # see strategies below
    "risk": "low",                           # low|medium|high
    # strategy-specific fields below
}
```

### 3.3 Strategies

| Strategy | What it does | Required fields |
|----------|-------------|-----------------|
| `install_dep` | Install a missing dependency | `dep` (tool ID) |
| `switch_method` | Try a different install method | `method` |
| `retry_with_modifier` | Re-run with extra args/env | `modifier` (dict) |
| `install_packages` | Install system packages | `packages` (per family) |
| `env_fix` | Run env setup commands | `fix_commands` (list of lists) |
| `manual` | Show instructions, user acts | `instructions` |

### 3.4 Where to add the handler

- **Tool-specific failure:** Add `on_failure` to the recipe in `recipes.py`
- **Method family failure:** Add to `METHOD_FAMILY_HANDLERS["method"]` in `remediation_handlers.py`
- **Cross-method infrastructure failure:** Add to `INFRA_HANDLERS` in `remediation_handlers.py` (rare)

### 3.5 `install_packages` — packages per family
When using the `install_packages` strategy, provide packages for ALL families:
```python
"packages": {
    "debian": ["libssl-dev"],
    "rhel": ["openssl-devel"],
    "alpine": ["openssl-dev"],
    "arch": ["openssl"],
    "suse": ["libopenssl-devel"],
    "macos": ["openssl@3"],
},
```
Check 3 validates that all families are covered.

---

## Phase 4: Check availability gates

File: `src/core/services/tool_install/domain/remediation_planning.py`

`_compute_availability()` determines if each remediation option is `ready`,
`locked`, or `impossible` on a given system.

### Current gates

| Gate | What it checks |
|------|---------------|
| **Native PM** | `apt`/`dnf`/`apk` etc. — impossible if system doesn't have this PM |
| **Installable PM** | `brew`/`snap` — locked if not installed (can be installed) |
| **snap systemd** | impossible if system has no systemd |
| **Language PM** | `pip`/`npm`/`cargo`/`go` — locked if CLI not on PATH |
| **Source toolchain** | Checks `requires_toolchain` — locked if build tools missing |
| **Read-only rootfs** | `install_packages` impossible on read-only root |

### When to add a new gate

Only if this tool introduces a capability not yet tracked. Examples:
- Tool needs GPU drivers → new `has_gpu` capability
- Tool needs specific kernel version → new `min_kernel` capability
- Tool needs Java runtime → could check `java` on PATH

If a new gate is needed:
1. Add capability to `dev_scenarios.py` system presets
2. Add gate check in `_compute_availability()`
3. Add the impossible reason to `SYSTEM_CORRECT_REASONS` in the test

---

## Phase 5: Validate remediation

```bash
// turbo
.venv/bin/python -m tests.test_remediation_coverage --verbose
```

| Check | What to look for |
|-------|-----------------|
| Check 2 | No "impossible deps" from your new handlers |
| Check 3 | No handler option errors (switch_method targets exist, packages cover all families) |
| Check 4 | **0 false impossibles** — your options should be ready/locked/impossible correctly on ALL 19 presets |

### If you see false impossibles in Check 4

1. Note the preset and option ID from the error line
2. Determine why `_compute_availability()` returned `impossible` for that option on that preset
3. Three possible fixes:
   - **Wrong gate:** Fix the gate logic in `remediation_planning.py`
   - **Legitimate impossible:** Add the reason to `SYSTEM_CORRECT_REASONS` or `SYSTEM_CORRECT_REASON_PATTERNS` in the test
   - **Missing recipe method:** Add the method to the recipe

```bash
// turbo
.venv/bin/python -m tests.test_remediation_coverage
```

---

## Phase 6: Confirm no regressions

- Total error count did not increase
- No NEW false impossibles appeared in Check 4
- Previously passing tools still pass

---

## The files you touch

| File | Responsibility | When |
|------|---------------|------|
| `data/remediation_handlers.py` | `METHOD_FAMILY_HANDLERS` — failure patterns per PM | When method family has new failure patterns |
| `data/remediation_handlers.py` | `INFRA_HANDLERS` — cross-method failures | Rare — new infra failure class |
| `data/recipes.py` | `on_failure` — tool-specific failures | When tool has unique failures |
| `domain/remediation_planning.py` | `_compute_availability()` — capability gates | When tool needs new gate |
| `dev_scenarios.py` | System presets — capability tracking | When new capability gate is added |
| `tests/test_remediation_coverage.py` | `SYSTEM_CORRECT_REASONS` — allowlisted impossibles | When new legitimate impossible is introduced |

---

## System presets tested by Check 4

| Preset | Family | PM | Arch | Notable |
|--------|--------|-----|------|---------|
| `debian_12` | debian | apt | x86_64 | |
| `ubuntu_2204` | debian | apt | x86_64 | |
| `raspbian_arm` | debian | apt | aarch64 | ARM, no snap |
| `fedora_39` | rhel | dnf | x86_64 | |
| `alpine_318` | alpine | apk | x86_64 | No systemd, no snap |
| `opensuse_15` | suse | zypper | x86_64 | |
| `macos_14` | macos | brew | arm64 | No apt/dnf |
| `arch_latest` | arch | pacman | x86_64 | |

All 19 presets are tested. Each remediation option is checked for correct
`ready`/`locked`/`impossible` state on every preset.

---

## What NOT to do

- Do NOT add handlers without real `pattern` regexes — they must match actual stderr
- Do NOT forget to cover all package families in `install_packages` options
- Do NOT set `"recommended": True` on more than one option per handler
- Do NOT add gates that break existing tools — check regressions
- Do NOT skip Check 4 — false impossibles mean users get told "impossible" when it's not
