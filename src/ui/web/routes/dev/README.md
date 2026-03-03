# Dev Routes — Developer Mode & Stage Debugger API

> **1 file · 86 lines · 3 endpoints · Blueprint: `dev_bp` · Prefix: `/api`**
>
> Owner-gated developer tools. These routes power two features:
> **Phase D0** — identity resolution (dev mode status based on git user vs
> project owners), and **Phase D1** — the scenario library for the stage
> debugger, which generates synthetic remediation responses across 19 system
> presets to test the tool installation pipeline without real tool failures.
> Only project owners see dev tools in the UI.

---

## How It Works

### Request Flow

```
Frontend
│
├── _dev_mode.html        → GET /api/dev/status
│                            Check identity. Toggle dev toolbar.
│
└── _stage_debugger.html  → GET /api/dev/scenarios
                             → GET /api/dev/scenarios/<scenario_id>
                             Load scenario library for debugging.
     │
     ▼
routes/dev/__init__.py              ← HTTP layer (this file)
     │
     ├── Phase D0:
     │   core/services/identity.py (117 lines)
     │   ├── get_git_user_name()     — run `git config user.name`
     │   ├── get_project_owners()    — parse owners[] from project.yml
     │   ├── is_owner()              — case-insensitive name match
     │   └── get_dev_mode_status()   — full status dict for frontend
     │
     └── Phase D1:
         core/services/dev_scenarios.py (903 lines)
         ├── SYSTEM_PRESETS           — 19 OS/distro/arch definitions
         ├── _generate_method_family_scenarios() — per method-family handler
         ├── _generate_infra_scenarios()          — per infra handler
         ├── _generate_bootstrap_scenarios()      — per bootstrap handler
         ├── _generate_chain_scenarios()           — escalation chains
         ├── generate_all_scenarios()              — combined output
         └── get_system_presets()                  — list preset IDs
```

### Identity Resolution Flow (Phase D0)

```
GET /api/dev/status
     │
     ▼
get_dev_mode_status(project_root)
     │
     ├── 1. Read git user:
     │   git -C <root> config user.name
     │   → "Cyberpunk 042" (or None if not configured)
     │
     ├── 2. Read project.yml owners:
     │   yaml_load → data["owners"]
     │   ├── Accept dict entries: {"name": "Cyberpunk 042"}
     │   └── Accept bare strings: "Cyberpunk 042"
     │   → ["Cyberpunk 042", "Other Dev"]
     │
     └── 3. Compare (case-insensitive, stripped):
         git_user.lower().strip() == any(owner.lower().strip())
              │
              ├── MATCH → { dev_mode: true, is_owner: true }
              └── NO MATCH → { dev_mode: false, is_owner: false }
```

### Scenario Generation Pipeline (Phase D1)

```
GET /api/dev/scenarios?system=debian_12
     │
     ▼
generate_all_scenarios("debian_12")
     │
     ├── 1. Validate system preset (fallback: "debian_12")
     │
     ├── 2. Generate 4 scenario families:
     │   ├── _generate_method_family_scenarios(preset)
     │   │   └── For each remediation handler tagged "method_family"
     │   │       → call build_remediation_response() with synthetic inputs
     │   │
     │   ├── _generate_infra_scenarios(preset)
     │   │   └── For each handler tagged "infrastructure"
     │   │       → call build_remediation_response() with synthetic inputs
     │   │
     │   ├── _generate_bootstrap_scenarios(preset)
     │   │   └── For each handler tagged "bootstrap"
     │   │       → call build_remediation_response() with synthetic inputs
     │   │
     │   └── _generate_chain_scenarios(preset)
     │       └── Generate escalation chains at various depths
     │           → call build_remediation_response() with pre-built state
     │
     ├── 3. For each scenario:
     │   ├── _build_synthetic_recipe(preset)
     │   │   → recipe with all common install methods for the OS
     │   ├── _synthesize_stderr(handler)
     │   │   → example_stderr or fallback to raw pattern
     │   └── _synthesize_exit_code(handler)
     │       → exit code matching the failure pattern
     │
     └── 4. Enrich with metadata:
         { _meta: { id, family, handler_id, system },
           toolId, toolLabel, remediation: { ... } }
```

### System Presets

```
19 presets organized by OS family:

Debian family (7):
  ubuntu_2004, ubuntu_2204, ubuntu_2404,
  debian_11, debian_12, raspbian_bookworm,
  wsl2_ubuntu_2204

RHEL family (4):
  fedora_39, fedora_41, centos_stream9, rocky_9

Alpine (2):
  alpine_318, alpine_320

Arch (1):
  arch_latest

SUSE (1):
  opensuse_15

macOS (2):
  macos_14_arm (Apple Silicon), macos_13_x86 (Intel)

Container edge cases (2):
  docker_debian_12, k8s_alpine_318
```

Each preset defines: system, arch, WSL status, distro info (id, family,
version, version_tuple, codename), package manager (primary, secondary),
container detection, library info (glibc version, libc type), hardware
(arch, cpu_cores), and Python defaults (version, PEP 668 status).

---

## File Map

```
routes/dev/
├── __init__.py     86 lines  — blueprint + all 3 endpoints
└── README.md                 — this file
```

Single-file package. The domain logic is in two core services:
- `identity.py` (117 lines) — D0 identity resolution
- `dev_scenarios.py` (903 lines) — D1 scenario library

---

## Per-File Documentation

### `__init__.py` — Blueprint + All Endpoints (86 lines)

| Function | Method | Route | What It Does |
|----------|--------|-------|-------------|
| `dev_status()` | GET | `/dev/status` | Dev mode status (identity match) |
| `dev_scenarios()` | GET | `/dev/scenarios` | All scenarios for a system preset |
| `dev_scenario_by_id()` | GET | `/dev/scenarios/<scenario_id>` | Single scenario by ID |

**Dev status — identity resolution:**

```python
from src.core.services.identity import get_dev_mode_status

root = current_app.config["PROJECT_ROOT"]
return jsonify(get_dev_mode_status(root))
```

Note: uses `current_app.config["PROJECT_ROOT"]` directly instead
of the `_project_root()` helper used by other routes. This is
because dev mode was implemented before the helper pattern was
standardized.

**Scenarios — full library for a system preset:**

```python
from src.core.services.dev_scenarios import (
    generate_all_scenarios,
    get_system_presets,
)

system = request.args.get("system", "debian_12")
presets = get_system_presets()

# Validate preset — fall back to debian_12 if invalid
if system not in presets:
    system = "debian_12"

scenarios = generate_all_scenarios(system)

return jsonify({
    "scenarios": scenarios,
    "system_presets": presets,
    "current_system": system,
})
```

The response includes:
- `scenarios[]` — all generated scenarios for the selected preset
- `system_presets[]` — list of valid preset IDs (for the dropdown)
- `current_system` — the resolved preset ID (after validation)

**Scenario by ID — deep linking:**

```python
from src.core.services.dev_scenarios import generate_all_scenarios

system = request.args.get("system", "debian_12")
scenarios = generate_all_scenarios(system)

for s in scenarios:
    if s["_meta"]["id"] == scenario_id:
        return jsonify(s)

return jsonify({"error": f"Scenario '{scenario_id}' not found"}), 404
```

Regenerates all scenarios, then finds by ID. This is acceptable
because scenario generation is deterministic and fast (~50ms).
The deep-link URL pattern allows linking from logs or chat
directly to a specific scenario.

---

## Dependency Graph

```
__init__.py (routes)
├── identity.py (117 lines)
│   ├── subprocess → git config user.name
│   ├── yaml → parse project.yml
│   └── No external dependencies
│
└── dev_scenarios.py (903 lines)
    ├── tool_install/resolver → build_remediation_response()
    ├── tool_install/data → remediation_handlers registry
    ├── SYSTEM_PRESETS dict → 19 OS definitions
    └── Synthetic recipe builder → fake recipes per preset
```

**All core imports are lazy** (inside handler functions). The dev
routes blueprint imports nothing from core at module level.

---

## Consumers

| Layer | Module | What It Uses |
|-------|--------|-------------|
| Server | `ui/web/server.py` | Imports `dev_bp`, registers at `/api` prefix |
| Frontend | `scripts/_dev_mode.html` | `GET /dev/status` (identity check → show/hide dev toolbar) |
| Frontend | `scripts/_stage_debugger.html` | `GET /dev/scenarios` (load scenario library) |
| Frontend | `scripts/_stage_debugger.html` | `GET /dev/scenarios/<id>` (deep-link to specific scenario) |

**Access control:** The UI checks `dev_mode` in the status response
before rendering the dev toolbar and stage debugger. The routes
themselves are not auth-gated — the identity check is informational,
not restrictive. Any user can call `/dev/status`, but only owners
see `dev_mode: true`.

---

## Service Delegation Map

```
Route Handler              →   Core Service Function
──────────────────────────────────────────────────────────────────
dev_status()               →   identity.get_dev_mode_status()
                                ├→ identity.get_git_user_name()
                                │    └→ subprocess: git config user.name
                                ├→ identity.get_project_owners()
                                │    └→ yaml.safe_load(project.yml)
                                └→ case-insensitive name comparison

dev_scenarios()            →   dev_scenarios.get_system_presets()
                            →   dev_scenarios.generate_all_scenarios()
                                ├→ _generate_method_family_scenarios()
                                ├→ _generate_infra_scenarios()
                                ├→ _generate_bootstrap_scenarios()
                                └→ _generate_chain_scenarios()
                                    └→ Each calls build_remediation_response()
                                       with synthetic inputs against real handlers

dev_scenario_by_id()       →   dev_scenarios.generate_all_scenarios()
                                └→ linear scan for matching _meta.id
```

---

## Data Shapes

### `GET /api/dev/status` response (owner match)

```json
{
    "dev_mode": true,
    "is_owner": true,
    "git_user": "Cyberpunk 042",
    "owners": ["Cyberpunk 042"]
}
```

### `GET /api/dev/status` response (no match)

```json
{
    "dev_mode": false,
    "is_owner": false,
    "git_user": "Some Contributor",
    "owners": ["Cyberpunk 042"]
}
```

### `GET /api/dev/status` response (no git user)

```json
{
    "dev_mode": false,
    "is_owner": false,
    "git_user": null,
    "owners": ["Cyberpunk 042"]
}
```

### `GET /api/dev/scenarios?system=debian_12` response

```json
{
    "scenarios": [
        {
            "_meta": {
                "id": "method_family_apt_not_found_debian_12",
                "family": "method_family",
                "handler_id": "apt_not_found",
                "system": "debian_12"
            },
            "toolId": "docker",
            "toolLabel": "Docker",
            "remediation": {
                "status": "resolved",
                "install_methods": [
                    {
                        "method": "apt",
                        "available": true,
                        "risk": "low",
                        "commands": ["sudo apt-get install -y docker.io"],
                        "post_install": ["sudo systemctl enable docker"]
                    }
                ],
                "escalation": null,
                "summary": "Package available via apt"
            }
        }
    ],
    "system_presets": [
        "ubuntu_2004", "ubuntu_2204", "ubuntu_2404",
        "debian_11", "debian_12", "raspbian_bookworm",
        "wsl2_ubuntu_2204",
        "fedora_39", "fedora_41", "centos_stream9", "rocky_9",
        "alpine_318", "alpine_320",
        "arch_latest",
        "opensuse_15",
        "macos_14_arm", "macos_13_x86",
        "docker_debian_12", "k8s_alpine_318"
    ],
    "current_system": "debian_12"
}
```

### `GET /api/dev/scenarios/<id>` response (found)

```json
{
    "_meta": {
        "id": "chain_depth2_debian_12",
        "family": "chain",
        "handler_id": "escalation_chain",
        "system": "debian_12"
    },
    "toolId": "terraform",
    "toolLabel": "Terraform",
    "remediation": {
        "status": "escalated",
        "current_method": "apt",
        "escalation": {
            "from": "apt",
            "to": "binary_download",
            "reason": "apt repository not configured",
            "depth": 2
        },
        "install_methods": [
            {
                "method": "binary_download",
                "available": true,
                "risk": "medium",
                "commands": ["wget https://releases.hashicorp.com/..."]
            }
        ]
    }
}
```

### `GET /api/dev/scenarios/<id>` response (not found)

```json
{
    "error": "Scenario 'nonexistent_id' not found"
}
```

---

## Advanced Feature Showcase

### 1. Synthetic Recipe Builder

Each system preset gets a tailored recipe with realistic install
methods so the scenario pipeline exercises real availability checks:

```python
# From dev_scenarios.py
def _build_synthetic_recipe(system_preset_id: str):
    preset = SYSTEM_PRESETS[system_preset_id]
    pkg_mgr = preset["distro"]["package_manager"]["primary"]

    recipe = {
        "install_methods": {
            pkg_mgr: {"commands": [f"{pkg_mgr} install -y <tool>"]},
            "pip": {"commands": ["pip install <tool>"]},
            "npm": {"commands": ["npm install -g <tool>"]},
            "cargo": {"commands": ["cargo install <tool>"]},
            "_default": {"commands": ["<manual instructions>"]},
            "source": {"commands": ["./configure && make && sudo make install"]},
        }
    }
    # All presets get common methods (pip, npm, cargo, _default, source)
    # in addition to their primary package manager
    return recipe
```

### 2. Scenario Families

Four distinct scenario families test different aspects of the
remediation pipeline:

| Family | Tests | Count |
|--------|-------|-------|
| `method_family` | Per-handler method resolution | ~20 scenarios |
| `infrastructure` | OS-level dependency handling | ~10 scenarios |
| `bootstrap` | Initial tool setup paths | ~5 scenarios |
| `chain` | Escalation at depth 1, 2, 3 | ~15 scenarios |

### 3. Cross-Preset Behavior Variance

The same handler produces different results on different presets.
For example, a Docker install scenario:
- On `debian_12`: resolves to `apt-get install docker.io`
- On `fedora_39`: resolves to `dnf install docker`
- On `alpine_318`: resolves to `apk add docker`
- On `macos_14_arm`: resolves to `brew install docker`
- On `k8s_alpine_318`: may not resolve (no package manager in container)

This variance is the entire point of the stage debugger — verifying
that remediation handlers produce correct commands per-OS.

### 4. Deterministic Regeneration

Scenario by ID regenerates the full list instead of caching:

```python
scenarios = generate_all_scenarios(system)  # regenerate all
for s in scenarios:
    if s["_meta"]["id"] == scenario_id:
        return jsonify(s)
```

This is intentional — scenarios are generated from handler code +
preset data, so regenerating is deterministic. If a handler is
modified, the scenarios immediately reflect the change. Caching
would require invalidation logic for an operation that takes ~50ms.

### 5. Owner Identity Without Authentication

Dev mode uses identity resolution (git user vs project.yml owners)
instead of authentication (password/token). This is a deliberate
design choice:

```python
# identity.py — no secrets, no tokens, no passwords
git_lower = git_user.lower().strip()
return any(name.lower().strip() == git_lower for name in owner_names)
```

The trade-off: anyone who sets their `git config user.name` to a
project owner's name gets dev access. This is acceptable because
dev tools are read-only (scenarios are synthetic, not production
data) and the project is a local control plane, not a public service.

---

## Design Decisions

### Why dev uses `current_app.config["PROJECT_ROOT"]` directly

The dev routes were implemented before the `_project_root()` helper
was standardized. Both resolve to the same value, but dev accesses
the Flask config directly. Updating to the helper pattern would be
a cleanup improvement but has zero functional impact.

### Why scenario_by_id regenerates instead of indexing

Generating all scenarios takes ~50ms. Adding a cache + index would
save ~49ms per deep-link request but add cache invalidation
complexity. Since deep-link requests are rare (debug-time only),
the simplicity of regeneration is preferred over the performance
of caching.

### Why system preset validation falls back instead of erroring

```python
if system not in presets:
    system = "debian_12"  # fallback, not error
```

The stage debugger is a development tool. If a frontend sends an
invalid preset (typo, deleted preset, etc.), showing debian_12
scenarios is more useful than showing an error page. The user can
simply select the correct preset from the dropdown.

### Why Phase D0 and D1 share a single file

Identity resolution and scenario generation are both "developer
tools" that share the same access pattern (owner-gated). Splitting
into separate files would create two 40-line files — too small to
justify the split. If more phases are added (D2, D3), splitting
would become appropriate.

### Why these endpoints have no auth decorator

Dev endpoints are informational, not destructive. `/dev/status`
returns whether the user IS an owner — it doesn't grant access.
`/dev/scenarios` returns synthetic test data — not production
secrets. The UI uses the status response to show/hide dev features
client-side, which is sufficient for a local dev tool.

---

## Coverage Summary

| Capability | Endpoint | Phase |
|-----------|----------|-------|
| Identity resolution | GET `/dev/status` | D0 |
| Scenario library | GET `/dev/scenarios` | D1 |
| Scenario deep-link | GET `/dev/scenarios/<id>` | D1 |
