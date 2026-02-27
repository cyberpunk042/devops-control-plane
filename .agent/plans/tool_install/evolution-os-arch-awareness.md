# Evolution: OS & Arch Awareness for `_default` Install Methods

> **Created:** 2026-02-26
> **Status:** ✅ Complete — all phases implemented
> **Trigger:** Node.js audit revealed that `_default` commands are Linux-specific
> but the resolver treats them as universal. This is a systemic gap affecting 20+ tools.

---

## Problem Statement

The `_default` install method is meant to be the universal fallback — when no
system PM is available, download the binary directly. But today:

1. **`_default` is a flat `list[str]`** — a single bash command that hardcodes
   the OS (e.g. `linux`) in download URLs and OS-specific archive handling
   (`tar -xJf` for `.tar.xz`, `tar -xzf` for `.tar.gz`).

2. **The resolver has no OS gate** — `method_selection.py` treats `_default`
   as always-available. On macOS, `_default` is selected before `brew` because
   `prefer: ["_default", ...]` and the resolver doesn't know the command is
   Linux-only.

3. **`_substitute_install_vars` has no `{os}` variable** — only `{arch}`,
   `{user}`, `{home}`, `{distro}`, etc. Recipes cannot write
   OS-portable URLs.

4. **Raspbian userland arch is unreliable** — `platform.machine()` reports the
   kernel arch (`aarch64`) not the userland arch (`armv7l`). The system profiler
   does not detect this mismatch. This causes binary downloads to fetch the
   wrong architecture.

---

## Current Architecture

```
Recipe._default  →  list[str]  (flat command, e.g. bash -c "curl ... linux-{arch} ...")
                          ↓
method_selection.py  →  picks _default  (no OS check)
                          ↓
plan_resolution.py   →  injects arch_map into profile as _arch_map
                          ↓
build_helpers.py     →  _substitute_install_vars()  →  replaces {arch} only
                          ↓
subprocess_runner    →  executes the command
```

---

## Proposed Design

### Change 1: `_default` supports OS variants

Allow `_default` to be a **dict keyed by OS** instead of only a flat list:

```python
# Current (flat — works on Linux only):
"_default": ["bash", "-c", "curl ... linux-{arch}.tar.xz ..."]

# Evolved (OS-variant dict):
"_default": {
    "linux":  ["bash", "-c", "curl ... linux-{arch}.tar.xz ..."],
    "darwin": ["bash", "-c", "curl ... darwin-{arch}.tar.gz ..."],
}
```

**Backward compatible:** If `_default` is a `list`, treat it as today (assumed
universal — which in practice means Linux). If it's a `dict`, look up
`platform.system().lower()` to select the right variant.

**Resolution in `method_selection.py`:**

```python
# When evaluating _default availability:
default_cmd = install.get("_default")
if isinstance(default_cmd, dict):
    current_os = platform.system().lower()
    if current_os not in default_cmd:
        continue  # skip _default — no command for this OS
```

**Resolution in `plan_resolution.py`:**

When building the install plan, if `_default` is a dict, extract the
OS-specific command list before passing to `_substitute_install_vars`.

### Change 2: Add `{os}` to `_substitute_install_vars`

```python
# In build_helpers.py, _substitute_install_vars():
variables["os"] = platform.system().lower()  # "linux" or "darwin"
```

This enables recipes that CAN use a single URL pattern
(e.g. `https://example.com/{os}-{arch}.tar.gz`) to stay as a flat list.
Recipes with different archive formats per OS use the dict variant.

### Change 3: Detect real userland arch in system profiler

In the L0 system profiler, when `platform.machine()` reports `aarch64`,
cross-check with the actual userland:

```python
import struct

def _detect_real_arch() -> str:
    """Detect the actual userland architecture.

    On Raspbian, the kernel may be 64-bit (aarch64) while the
    userland is 32-bit (armv7l). We detect this by checking the
    pointer size of the running Python process.
    """
    machine = platform.machine().lower()
    pointer_bits = struct.calcsize("P") * 8

    if machine == "aarch64" and pointer_bits == 32:
        return "armv7l"  # 64-bit kernel, 32-bit userland
    return machine
```

This feeds into `_substitute_install_vars` via the system profile, so
`{arch}` resolves to the REAL userland arch on all platforms.

**Alternative approach:** Use `dpkg --print-architecture` on Debian-family
systems, which always reports the userland arch correctly (`armhf` on
32-bit Raspbian).

---

## Files Affected

| File | Change | Scope |
|------|--------|-------|
| `resolver/method_selection.py` | Handle `_default` as `dict\|list` in `select_method()` | ~10 lines |
| `resolver/plan_resolution.py` | Extract OS-specific command from dict `_default` | ~10 lines |
| `execution/build_helpers.py` | Add `{os}` variable to `_substitute_install_vars` | 1 line |
| `data/recipes.py` | Migrate `_default` entries to dict format where needed | Per-recipe |
| System profiler (L0) | Detect real userland arch | ~10 lines |
| `data/constants.py` | Document `{os}` in variable list | Comment only |

---

## Migration Path

1. **Phase 1:** ✅ Add structural support (method_selection + plan_resolution
   handle dict `_default`). Add `{os}` variable. Add userland arch detection.
   Fully backward compatible — existing flat `_default` entries work unchanged.

2. **Phase 2:** ✅ Migrated `node` (OS-variant dict with linux/darwin) and
   `go` (uses `{os}` placeholder — same archive format both OSes).

3. **Phase 3:** ✅ Batch-migrated all 32 remaining recipes with hardcoded
   `linux` in `_default` to `{"linux": [...]}` dict format. On macOS these
   now correctly fall through to `brew`. Darwin variants can be added
   per-tool as they are individually audited.

---

## What This Solves

| Problem | Before | After |
|---------|--------|-------|
| macOS gets Linux binary | _default selected, Linux ELF downloaded | _default skipped if no darwin variant; OR darwin variant used |
| Recipes can't vary by OS | Hardcode `linux` in URL | Use `{os}` placeholder or OS-variant dict |
| Raspbian wrong arch | `platform.machine()` lies | Userland detection via pointer size |
| `armv7l` → `armhf` by _IARCH_MAP | Wrong for tools using `armv7l` in URLs | Per-recipe `arch_map` overrides (already works, just need correct entries) |

---

## What This Does NOT Solve (parking lot)

- Windows/WSL2: `_default` on WSL2 reports Linux but some tools need
  Windows-native binaries. Out of scope for now.
- Per-architecture `_default` variants (e.g. different commands for x64 vs
  arm64 on the same OS). Not needed today — archive format is usually
  consistent within an OS.
