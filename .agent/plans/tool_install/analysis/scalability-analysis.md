# Scalability Analysis — Tool Install Architecture

## Date: 2026-02-25
## Scope: Can this scale from 61 → 192+ recipes, 6 → 14 OS profiles, without confusion?

---

## 1. Architecture Verdict: SOLID, but 5 issues to fix first

The onion layer architecture (L0 Data → L1 Domain → L2 Resolver → L3 Detection →
L4 Execution → L5 Orchestration) is clean. Layer rules are respected.
The resolver pipeline (method selection → dep collection → plan assembly) is correct.

**But** there are 5 concrete issues that will cause confusion and bugs at scale.

---

## 2. Issue #1: Two Recipe Types, One Dict (CONFUSION)

### What's happening:

There are **three** recipe patterns coexisting in `TOOL_RECIPES`:

| Pattern | Count | Example | Has `install` | Has `steps` |
|---------|-------|---------|---------------|-------------|
| **Tool recipe** | 51 | ruff, kubectl | ✅ method-keyed | — |
| **Data pack** | 6 | trivy-db, wordlists | — | ✅ pre-built steps |
| **Config template** | 4 | docker-daemon-config | — | — (BROKEN) |

The resolver calls `resolve_install_plan()` for ALL of them, but it only knows
about tool recipes. Data packs and configs have no install methods → they error
with "No install method available."

### Why this blocks scaling:

When we add 130+ tools, we'll ALSO add configs (nginx, caddy, systemd units,
docker configs) and data packs (language models, DB schemas). The resolver
needs to handle all three types or they need different entry points.

### Fix:

Add a `type` field to every recipe: `"type": "tool"`, `"type": "data_pack"`,
or `"type": "config"`. The resolver detects this and dispatches accordingly:

- `tool` → current `resolve_install_plan()` flow
- `data_pack` → wrap `steps[]` into a plan directly (no method selection)
- `config` → wrap `config_templates[]` into config steps

---

## 3. Issue #2: Inconsistent Method Keys (CONFUSION)

### What's happening:

pip/npm tools use DIFFERENT patterns:

```python
# Pattern A: _default with pip command (7 tools)
"ruff": {"install": {"_default": _PIP + ["install", "ruff"]}}

# Pattern B: pip as method key (3 tools)
"pytorch": {"install": {"pip": _PIP + ["install", "torch"]}}

# Same inconsistency for npm:
"eslint":    {"install": {"_default": ["npm", "install", "-g", "eslint"]}}
"docusaurus": {"install": {"npm": ["npx", "create-docusaurus@latest", "..."]}}
```

### Why this blocks scaling:

Pattern A: `_default` is selected last (fallback). On Ubuntu, if `apt` has
a ruff package, the resolver will pick apt instead of pip.

Pattern B: `pip` as a method key is never selected by `_pick_install_method()`
because pip is not a system PM. It falls through to step 5 (any binary on PATH)
which checks `shutil.which("pip")`.

When we add 50+ pip tools and 20+ npm tools, half will use Pattern A and
half Pattern B — nobody will know which is correct.

### Fix:

**Standardize on one pattern per language PM:**

- pip tools that MUST use pip (venv installs): use `_default` ← current 7 tools
  are correct. These always install into the venv regardless of system PM.
- pip tools that could also come from apt/dnf: use `pip` + `apt` method keys
  ← pytorch is correct here, it has apt alternative.
- npm tools that MUST use npm: use `_default` ← eslint/prettier correct.
- npm tools that are really npx one-shots: use `npm` key ← docusaurus correct.

**Rule:** `_default` = "this works everywhere, use as fallback."
Specific PM key = "only use when this PM is available."

This is already how the resolver works — the naming just needs consistency.

---

## 4. Issue #3: needs_sudo Missing for Some Methods

### What's happening:

3 recipes have install methods with no matching `needs_sudo` entry:

```
mkdocs:   method "pip" → no needs_sudo["pip"]
opencv:   method "pip" → no needs_sudo["pip"]
pytorch:  method "pip" → no needs_sudo["pip"]
```

The resolver falls back to `False` when the key is missing, which happens
to be correct for pip. But at scale with 192+ recipes, this silent fallback
will cause real bugs (e.g., a dnf method missing needs_sudo → installs fail
without sudo).

### Fix:

Every install method key MUST have a matching needs_sudo key.
Add a recipe validator that catches this at import time (L0 data integrity).

---

## 5. Issue #4: Unknown Recipe Keys (NO SCHEMA)

### What's happening:

24 recipes use keys not recognized by the resolver:

| Key | Used by | Purpose |
|-----|---------|---------|
| `category` | 17 recipes | UI grouping |
| `config_templates` | 4 recipes | Config file generation |
| `cli_verify_args` | 3 recipes | Alternative verify args |
| `steps` | 6 recipes | Data pack steps |
| `arch_map` | 1 recipe | Architecture name mapping |
| `remove` | 1 recipe | Removal command |

These are not bugs per se — the resolver ignores unknown keys. But at 192+
recipes, there's no enforcement of which keys are valid, which are required,
which are optional.

### Fix:

Add a recipe schema definition (a dict of field specs) and a validator
function that runs at import time. Catches typos, missing fields, wrong types.

---

## 6. Issue #5: System Profile Shape Inconsistency

### What's happening:

The resolver reads the profile like this:
```python
pm = system_profile.get("package_manager", {}).get("primary", "apt")
family = system_profile.get("distro", {}).get("family", "debian")
```

But `_detect_os()` returns:
```python
info["distro"] = {"id": "ubuntu", "family": "debian", ...}
info["package_manager"] = {"primary": "apt", "snap_available": True, ...}
```

The README shows a DIFFERENT shape:
```python
{"distro": "ubuntu", "distro_family": "debian", "package_manager": {"primary": "apt"}}
```

The actual code is correct. The README doc is outdated. But for testing with
simulated profiles, we need ONE canonical shape.

### Fix:

Document the EXACT profile shape that the resolver consumes. Use that shape
for all simulated profiles in tests.

---

## 7. Interface Clarity (Who Calls What)

### Current interfaces are CLEAR:

```
CLI/TUI/WEB
    ↓ calls
routes_audit.py (HTTP)
    ↓ calls
resolve_install_plan(tool, system_profile) → plan dict
resolve_install_plan_with_choices(tool, system_profile, answers) → plan dict
resolve_choices(tool, system_profile) → choices list
    ↓ plan goes to
execute_plan(plan, sudo_password) → result dict (sync)
audit_execute_plan SSE route → step-by-step streaming
```

This is clean. No confusion at the interface level.

### Reusability is strong:

- Same resolver output feeds CLI, TUI, and WEB
- Same plan dict works for sync and streaming execution
- Same recipe dict works across all OS families
- Adding a new tool = add ONE recipe dict, zero code changes

---

## 8. Readiness Score

| Dimension | Score | Notes |
|-----------|-------|-------|
| Layer architecture | ✅ 9/10 | Clean onion, rules respected |
| Recipe format | ⚠️ 6/10 | 3 recipe types mixed, no schema validation |
| Method selection | ✅ 8/10 | Works correctly, minor naming inconsistency |
| Dependency resolution | ✅ 9/10 | Transitive, depth-first, batching works |
| OS adaptation | ✅ 9/10 | Family-keyed packages well designed |
| Interface clarity | ✅ 9/10 | Clear who calls what, data is the interface |
| Test infrastructure | ❌ 2/10 | No tests exist at all |
| Schema enforcement | ❌ 1/10 | No validation, silent fallbacks |

**Overall: 67% ready.** The architecture is sound but the data layer lacks
discipline. Fix the 5 issues BEFORE adding 130+ recipes.

---

## 9. Recommended Fix Order

1. **Recipe schema + validator** — Define what keys are valid, which are required
   per recipe type. Run at import time. This prevents 130+ recipes from drifting.

2. **Recipe type field** — Add `type: tool|data_pack|config` to every recipe.
   Update resolver to handle all three types.

3. **needs_sudo completeness** — Every method key gets a needs_sudo entry.

4. **Simulated OS profiles** — Define 14 canonical profiles for testing.

5. **Test framework** — parametric test: every recipe × every profile → valid plan.

Then: scale. Add recipes batch by batch with tests validating each batch.
