# Cross-Cutting Services — Shared Utilities at the Services Root

> **14 standalone files · 3,674 lines · Not part of any domain package**
>
> These files live at `core/services/` root level (not inside any
> domain folder) because they serve multiple domains. They provide
> infrastructure that any domain can consume: event broadcasting,
> module detection, project probing, run tracking, audit recording,
> cache staleness monitoring, terminal spawning, markdown transforms,
> identity resolution, tool requirements, config CRUD, and dev/test
> scenario support.
>
> Together they form the "connective tissue" between the 27 domain
> packages.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                  Cross-Cutting Service Files                        │
│                                                                     │
│  ┌─ Infrastructure ──────────────────────────────────────────────┐ │
│  │ event_bus.py       — Thread-safe pub/sub (SSE backbone)       │ │
│  │ staleness_watcher.py — Background mtime polling               │ │
│  │ run_tracker.py     — Decorator + ctx mgr for Run tracking     │ │
│  │ audit_helpers.py   — Shared audit recording (make_auditor)    │ │
│  │ audit_staging.py   — Pending audit snapshot staging           │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  ┌─ Detection & Probing ─────────────────────────────────────────┐ │
│  │ detection.py       — Module/stack matching engine             │ │
│  │ project_probes.py  — Per-integration readiness checks         │ │
│  │ config_ops.py      — project.yml CRUD + content folder scan   │ │
│  │ identity.py        — Git user / project owner resolution      │ │
│  │ tool_requirements.py — Missing tool checker with recipes      │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  ┌─ Transform & Terminal ────────────────────────────────────────┐ │
│  │ md_transforms.py   — Admonition conversion, link rewriting   │ │
│  │ terminal_ops.py    — Terminal emulator detection + spawn      │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  ┌─ Dev/Test Support ────────────────────────────────────────────┐ │
│  │ dev_scenarios.py   — 19 synthetic system presets for testing  │ │
│  │ dev_overrides.py   — X-Dev-System-Override header handling    │ │
│  └──────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

---

## File-by-File Documentation

### `event_bus.py` — Thread-Safe Pub/Sub (360 lines · 9 consumers)

The central nervous system for real-time state communication. All
state changes (cache lifecycle, system events, staleness notifications)
publish through this bus. SSE clients subscribe to receive events.

**Class: `EventBus`**

| Method | What It Does |
|--------|-------------|
| `__init__(buffer_size=500, subscriber_queue_size=200)` | Create bus with bounded replay buffer |
| `instance_id` | Property: server instance identifier (boot timestamp) |
| `seq` | Property: current monotonic sequence number |
| `subscriber_count` | Property: number of active SSE subscribers |
| `publish(event_type, key, data, **kw)` | Broadcast event to all subscribers + replay buffer |
| `subscribe(since=0, heartbeat_interval=30)` | Generator: yield events for SSE client (blocks between) |
| `add_listener(q)` / `remove_listener(q)` | Register/unregister internal listener queues |
| `snapshot()` | Return current state for HTML pre-injection |

**Module-level singleton:**

```python
bus = EventBus()
# Usage:
from src.core.services.event_bus import bus
bus.publish("cache:done", key="docker", data={...}, duration_s=2.51)
```

**Event schema:**

```python
{
    "seq": 42,              # monotonic sequence number
    "type": "cache:done",   # <domain>:<action>
    "key": "docker",        # resource identifier
    "data": { ... },        # event-specific payload
    "ts": 1739648400.0,     # timestamp
    "v": 1,                 # schema version
}
```

**Thread safety:** All state is protected by `threading.Lock`.
Subscriber queues are bounded; overflow drops oldest events (non-blocking).

**Consumers:**

| Consumer | Usage |
|----------|-------|
| `devops/cache.py` | Publishes `cache:start`, `cache:done`, `cache:error` |
| `staleness_watcher.py` | Publishes `state:stale` events |
| `run_tracker.py` | Publishes `run:start`, `run:done` events |
| `routes/sse.py` | SSE endpoint subscribes for browser streaming |
| `routes/devops/__init__.py` | State snapshot for HTML pre-injection |
| Web server startup | Initializes and starts the bus |

---

### `detection.py` — Module/Stack Detection Engine (300 lines · 14 consumers)

Core intelligence layer that examines a project's filesystem to detect
modules and match them against stack definitions. Used during project
setup, wizard configuration, and dashboard status.

**Dataclass: `DetectionResult`**

| Field/Method | What It Does |
|-------------|-------------|
| `modules: list[Module]` | Matched modules with stack + version |
| `unmatched_refs: list[str]` | Module refs from config that couldn't be matched |
| `extra_detections: list[Module]` | Modules found on disk not in config |
| `total_detected` | Property: count of all detections |
| `total_modules` | Property: count of configured modules |
| `get_module(name)` | Lookup by module name |
| `to_dict()` | Serialize to dict for API responses |

**Functions:**

| Function | What It Does |
|----------|-------------|
| `match_stack(directory, stacks)` | Match a directory against stack detection rules |
| `detect_version(directory, stack_name)` | Extract version from config files (package.json, pyproject.toml, etc.) |
| `detect_language(stack_name)` | Infer language from stack name (prefix matching) |
| `detect_modules(project, project_root, stacks)` | Full module detection pipeline |

**Stack matching rules:**
- `files_any_of` — at least one must exist
- `files_all_of` — all must exist
- `content_contains` — file must contain a specific string

**Dependencies:** `core.models.module`, `core.models.project`, `core.models.stack`

---

### `project_probes.py` — Integration Readiness Checks (485 lines · 2 consumers)

Per-integration readiness probes. Each probe checks whether a specific
integration (git, Docker, K8s, Terraform, etc.) is configured and
working. The `run_all_probes()` function runs all probes and returns
a map for the dashboard.

**Probes (10):**

| Probe | What It Checks |
|-------|---------------|
| `probe_project(root)` | project.yml exists + configured |
| `probe_git(root)` | Git repo, branch, remote, status, uncommitted changes |
| `probe_github(root)` | gh CLI authenticated, repo linked |
| `probe_docker(root)` | Docker/Compose available, Dockerfiles present |
| `probe_cicd(root)` | CI/CD workflow files detected |
| `probe_k8s(root)` | kubectl available, manifests present, cluster connectivity |
| `probe_terraform(root)` | Terraform CLI, .tf files, initialized |
| `probe_pages(root)` | Pages segments, builders, site config |
| `probe_dns(root)` | DNS zone files, CDN configs, CNAME |

**Utilities:**

| Function | What It Does |
|----------|-------------|
| `has_cmd(cmd)` | Check if command is on PATH (shutil.which) |
| `count_glob(root, pattern)` | Count files matching glob |
| `run_all_probes(root)` | Run all 10 probes, return full status map |
| `suggest_next(statuses)` | Recommend next integration to configure |
| `compute_progress(statuses)` | Overall setup progress percentage |

**Progress computation:** Each probe returns `ready: bool`. Progress =
(ready count / total probes) × 100.

---

### `config_ops.py` — Project Configuration CRUD (327 lines · 1 consumer)

Read and write `project.yml`, detect content folders with auto-suggestion,
manage infrastructure directories (.ledger, .state, releases/).

**Functions:**

| Function | What It Does |
|----------|-------------|
| `read_config(project_root, config_path)` | Parse project.yml → structured dict |
| `save_config(project_root, config, config_path)` | Write wizard data back to project.yml |
| `detect_content_folders(root, include_hidden)` | Scan for content dirs + suggest common ones |

**Constants:**

| Constant | What It Contains |
|----------|-----------------|
| `_COMMON_CONTENT_DIRS` | Set of well-known names: "docs", "blog", "content", etc. |
| `_SKIP_DIRS` | Directories to skip: ".git", "node_modules", "dist", etc. |
| `_INFRA_DIRS` | Infrastructure directories: .ledger, .state, releases/ |

**Infrastructure directories** carry extra metadata: role, icon,
description, shared flag, and runtime `exists` check.

---

### `identity.py` — Git User / Owner Resolution (116 lines · 2 consumers)

Reads `git config user.name` and matches against `project.yml` owners.
No network calls, no external dependencies beyond PyYAML.

**Functions:**

| Function | What It Does |
|----------|-------------|
| `get_git_user_name(root)` | Read git user.name via subprocess |
| `get_project_owners(root)` | Parse owners from project.yml (accepts dicts or strings) |
| `is_owner(root)` | Case-insensitive check: git user == any owner |
| `get_dev_mode_status(root)` | Full status dict for frontend (dev_mode, is_owner, git_user, owners) |

**Used by:** `dev_overrides.py` (owner verification for system preset
overrides), web routes (dev mode badge).

---

### `run_tracker.py` — Run Tracking (379 lines · 26 consumers)

Decorator + context manager for wrapping any action as a tracked "Run".
Persists runs to `.state/runs.jsonl` and publishes SSE events.

**Run type taxonomy:**

| Type | Meaning |
|------|---------|
| `install` | Package/tool installation |
| `build` | Build artifacts (images, sites) |
| `deploy` | Deploy to target (cluster, cloud, pages) |
| `destroy` | Tear down resources |
| `scan` | Detect / audit / check |
| `generate` | Generate config files |
| `backup` / `restore` | Backup / restore operations |
| `git` / `ci` | Git and CI/CD operations |

**Two patterns:**

```python
# Pattern 1: Decorator (for Flask route handlers)
@bp.route("/k8s/apply", methods=["POST"])
@run_tracked("deploy", "deploy:k8s")
def k8s_apply():
    ...

# Pattern 2: Context manager (for service functions)
with tracked_run(root, "deploy", "deploy:k8s", summary="Apply manifests") as run:
    result = k8s_ops.k8s_apply(root, path)
    run["result"] = result
```

**Functions:**

| Function | What It Does |
|----------|-------------|
| `tracked_run(root, type, subtype, summary)` | Context manager: create + track + record a Run |
| `run_tracked(type, subtype, summary_key, ok_key)` | Decorator for Flask routes |
| `load_runs(root, n=50)` | Load latest N runs from runs.jsonl |
| `get_run_local(root, run_id)` | Get single run by ID |

**SSE integration:** Publishes `run:start` and `run:done` events
on the EventBus. The decorator also injects `run_id` into the JSON
response body.

**Persistence:** Runs are appended to `.state/runs.jsonl` (JSONL format,
capped at 200 entries).

---

### `audit_helpers.py` — Shared Audit Recording (81 lines · 36 consumers)

Single source of truth for recording audit events. Replaces 17+
identical `_audit()` copy-paste functions across service modules.

**Functions:**

| Function | What It Does |
|----------|-------------|
| `audit_event(card, label, summary, **kw)` | Record an audit event if project root is registered |
| `make_auditor(card)` | Factory: create a module-level `_audit` function pre-bound to a card |

**Factory pattern:**

```python
from src.core.services.audit_helpers import make_auditor

_audit = make_auditor("vault")
_audit("🔒 Locked", "Vault locked by user", action="locked")
```

**Fail-safe:** If no project root is set (unit tests), silently returns.
Never raises. The `make_auditor` factory binds the card name once so
individual call sites don't repeat it.

**36 consumers** — this is the most widely imported cross-cutting utility
in the codebase.

---

### `audit_staging.py` — Pending Audit Snapshots (333 lines · 3 consumers)

Staging area for audit snapshots awaiting save-to-git or discard.
Each cache computation stages a snapshot; the user then decides to
save (promote to ledger) or discard.

**Lifecycle:**

```
get_cached() computes fresh result
  → stage_audit(card_key, data)     → pending staging
  → list_pending()                  → user sees pending audits
  → save_audit(snapshot_id)         → promote to .ledger/ + git commit + tag
  → discard_audit(snapshot_id)      → drop without trace
```

**Functions:**

| Function | What It Does |
|----------|-------------|
| `stage_audit(root, card_key, status, elapsed_s, data, summary)` | Stage a pending snapshot |
| `list_pending(root)` | List all pending snapshots (metadata only) |
| `get_pending(root, snapshot_id)` | Get full snapshot including data blob |
| `save_audit(root, snapshot_id)` | Promote to ledger branch |
| `save_all_pending(root)` | Save all pending snapshots |
| `discard_audit(root, snapshot_id)` | Remove from staging |
| `discard_all_pending(root)` | Discard all pending |

**Snapshot ID format:** `<card_key>_<YYYYMMDD>_<HHMMSS>` — safe for
filenames and git tag names.

**Thread safety:** File operations protected by `threading.Lock`.

**Migration:** Handles old list format (pre-2026-03) automatically
on `_load_pending()`.

---

### `staleness_watcher.py` — Background Mtime Polling (123 lines · 1 consumer)

Daemon thread that polls filesystem mtime for proactive cache
invalidation. When a file changes after the cache was written,
publishes `state:stale` on the EventBus.

**Functions:**

| Function | What It Does |
|----------|-------------|
| `start_watcher(root)` | Start daemon thread, returns Thread |
| `_poll_loop(root)` | Main loop: check mtimes every 5s |
| `_publish_stale(key, current_mtime, cached_mtime)` | Publish `state:stale` event (fail-safe) |

**Design decisions (from docstring):**
1. Mtime polling (not inotify/watchdog) — zero new dependencies
2. Notify only, don't recompute — avoids storm during active editing
3. Debounce via `_last_stale` — each key fires once per mtime change
4. Daemon thread — stops automatically on server shutdown

**Poll interval:** 5 seconds. ~30 stat() calls per cycle — negligible.

---

### `terminal_ops.py` — Terminal Detection & Spawn (350 lines · 2 consumers)

Detect available terminal emulators on the host, spawn interactive
terminal sessions from the web UI (for tool install, manual commands).

**Terminal registry (5 entries):**

| Terminal | Label | apt Package |
|----------|-------|-------------|
| `gnome-terminal` | GNOME Terminal | gnome-terminal |
| `xfce4-terminal` | XFCE Terminal | xfce4-terminal |
| `kitty` | Kitty | kitty |
| `alacritty` | Alacritty | alacritty |
| `x-terminal-emulator` | System Default | (meta) |

**Functions:**

| Function | What It Does |
|----------|-------------|
| `detect_terminal()` | First available AND working terminal (smoke-tested) |
| `terminal_status()` | Full report: working[], broken[], installable[] |
| `spawn_terminal(command, cwd, title, wait_after)` | Spawn terminal running a command |
| `spawn_terminal_script(script_content, cwd, script_name, title)` | Write bash script + spawn |

**Smoke testing:** `_smoke_test_terminal()` actually launches each
terminal with `exit 0` and checks if it crashes within 2 seconds.
This distinguishes "installed but broken" from "working".

**Fallback:** If no terminal works, returns `{"ok": False, "fallback": True,
"command": "..."}` so the frontend can show a copy-paste command.

---

### `md_transforms.py` — Markdown Transform Utilities (217 lines · 0 direct consumers)

Cross-builder compatibility transforms for Markdown files. Used
internally by the pages builders pipeline.

**Transforms:**

| Function | What It Does |
|----------|-------------|
| `admonitions_to_docusaurus(content)` | MkDocs `!!!` → Docusaurus `:::` format |
| `admonitions_to_mkdocs(content)` | Docusaurus `:::` → MkDocs `!!!` format |
| `enrich_frontmatter(content, filepath)` | Add title from filename if missing |
| `rewrite_links(content, segment_path, base_url)` | Fix relative links for segments |
| `transform_directory(source, target, format, segment, base)` | Batch transform all .md files |

**Note:** 0 direct `import` consumers found because builders import
from the pages_builders package which re-exports these transforms.

---

### `tool_requirements.py` — Missing Tool Checker (67 lines · 12 consumers)

Check which tools a card needs and which are missing, enriched with
install recipe information.

**Function:**

```python
check_required_tools(["kubectl", "helm"])
→ [
    {
        "id": "kubectl",
        "label": "kubectl",
        "install_type": "sudo",
        "has_recipe": True,
        "needs_sudo": True,
    }
]  # only missing tools returned
```

**Dependencies:** `audit.l0_detection.detect_tools` (tool availability),
`tool_install.TOOL_RECIPES` (recipe lookup).

**12 consumers** — used by every card status function that depends on
external CLI tools.

---

### `dev_scenarios.py` — Synthetic System Presets (902 lines · 2 consumers)

Generates synthetic remediation responses for the Stage Debugger.
Contains 19 system presets covering major Linux distributions, WSL,
musl-based systems, and ARM architectures.

**`SYSTEM_PRESETS` dict (19 entries):**

| Family | Presets |
|--------|---------|
| Debian | ubuntu_2004, ubuntu_2204, ubuntu_2404, debian_11, debian_12, raspbian_bookworm |
| WSL | wsl2_ubuntu_2204 |
| RHEL | fedora_39, fedora_41, centos_stream9, rocky_9 |
| Alpine | alpine_318 (musl-based) |
| Arch | arch_rolling |
| macOS | macos_13_intel, macos_14_arm |
| ARM | debian_arm64_rpi4, ubuntu_arm64_server |
| Docker | docker_debian12, docker_alpine |

Each preset includes: system, arch, wsl flag, distro details, package
manager, libraries (glibc/musl), hardware, Python version + PEP 668 flag.

---

### `dev_overrides.py` — System Profile Override (72 lines · 3 consumers)

Resolves system profile with dev override support. When a project
owner has the stage debugger active, API calls include
`X-Dev-System-Override` header. This module checks the header, verifies
ownership, and returns the synthetic preset instead of real OS detection.

**Function:**

```python
resolve_system_profile(project_root)
→ (system_profile_dict, is_override: bool)
```

**Safety:** Only project owners can use overrides. Non-owners get
the real profile with a warning logged.

**Dependencies:** `identity.is_owner`, `dev_scenarios.SYSTEM_PRESETS`,
`audit.l0_detection._detect_os`

---

## Consumer Frequency

| File | Consumers | Role |
|------|-----------|------|
| `audit_helpers.py` | 36 | Most imported — every service that records events |
| `run_tracker.py` | 26 | Every action route uses `@run_tracked` |
| `detection.py` | 14 | Every module-detection path |
| `tool_requirements.py` | 12 | Every card that depends on CLI tools |
| `event_bus.py` | 9 | All SSE + cache + staleness producers |
| `audit_staging.py` | 3 | Cache pipeline + audit routes |
| `dev_overrides.py` | 3 | Audit routes with stage debugger support |
| `project_probes.py` | 2 | Project status route + wizard |
| `identity.py` | 2 | Dev overrides + web routes |
| `terminal_ops.py` | 2 | Terminal routes |
| `dev_scenarios.py` | 2 | Dev overrides + stage debugger |
| `config_ops.py` | 1 | Wizard config save |
| `staleness_watcher.py` | 1 | Web server startup |
| `md_transforms.py` | 0* | Used indirectly via pages_builders |

---

## Dependency Graph

```
event_bus.py          ← standalone (threading, queue, deque)
  ↑
  ├── staleness_watcher.py  (publishes state:stale)
  ├── run_tracker.py        (publishes run:start, run:done)
  └── devops/cache.py       (publishes cache:done)

audit_helpers.py      ← core.context, devops/cache.record_event
  ↑
  └── 36 service modules (make_auditor)

audit_staging.py      ← devops/cache, ledger
  ↑
  └── devops/cache.get_cached, audit routes

detection.py          ← core.models (Module, Project, Stack)
  ↑
  └── wizard, project status

project_probes.py     ← shutil.which, subprocess, project.yml
  ↑
  └── project status route, wizard

config_ops.py         ← PyYAML, project.yml
  ↑
  └── wizard config save

identity.py           ← subprocess (git), PyYAML
  ↑
  └── dev_overrides.py, web routes

tool_requirements.py  ← audit.l0_detection, tool_install.TOOL_RECIPES
  ↑
  └── 12 card status functions

dev_scenarios.py      ← standalone (large data dict)
  ↑
  └── dev_overrides.py, stage debugger route

dev_overrides.py      ← Flask request, identity, dev_scenarios, audit.l0
  ↑
  └── audit routes

terminal_ops.py       ← subprocess, shutil.which
  ↑
  └── terminal routes

md_transforms.py      ← re, pathlib
  ↑
  └── pages_builders (indirect)

run_tracker.py        ← event_bus, ledger
  ↑
  └── 26 route handlers
```

---

## Backward Compatibility Shims

In addition to the cross-cutting files above, the services root also
contains ~35 re-export shim files (2-9 lines each). These exist
because domains were refactored from flat files into packages:

```python
# backup_ops.py (2 lines)
"""Backup ops — backward-compat re-export hub."""
from src.core.services.backup import *  # noqa: F401, F403
```

**Shim categories:**

| Pattern | Count | Examples |
|---------|-------|---------|
| Simple wildcard re-export | ~25 | `backup_ops.py`, `ci_ops.py`, `dns_cdn_ops.py` |
| Named re-export (multiple sub-modules) | ~8 | `git_ops.py`, `secrets_ops.py`, `vault_env_ops.py` |
| Mixed (re-export + small bridge logic) | ~2 | `terraform_ops.py`, `docker_ops.py` |

**Rule:** New code should import from the package directly (e.g.,
`from src.core.services.vault.core import lock_vault`). Shims exist
for backward compatibility during the refactor.

---

## Design Decisions

### Why these files are NOT in domain packages

Each domain package has a clear single-domain responsibility (vault,
docker, k8s, etc.). These files serve multiple domains simultaneously:

- `audit_helpers.py` is imported by 36 different modules across 15+ domains
- `run_tracker.py` decorates route handlers from every domain
- `event_bus.py` is the shared communication bus

Putting them in any one domain would create a false ownership claim.

### Why `event_bus` is a module-level singleton

The EventBus needs exactly one instance per process. Module-level
`bus = EventBus()` ensures this without dependency injection complexity.
All producers and consumers import the same instance.

### Why `audit_helpers` uses a factory pattern

The `make_auditor("vault")` factory creates a pre-bound `_audit(label,
summary)` function. This eliminates repeating the card name at every
call site across 36 modules. It also provides a drop-in replacement
for the old copy-pasted `_audit()` functions.

### Why `staleness_watcher` uses mtime polling instead of inotify

1. Zero new dependencies (no watchdog/pyinotify)
2. Reuses existing `_max_mtime()` from devops_cache
3. ~30 stat() calls per 5-second cycle — negligible overhead
4. Works identically on all platforms (Linux, macOS, WSL)

### Why `dev_scenarios` is 902 lines

Each of the 19 system presets is a complete system profile dict with
distro details, package manager, library versions, hardware info, and
Python configuration. This data is inherently voluminous — it represents
the diversity of real-world deployment targets.

### Why `terminal_ops` smoke-tests each terminal

`shutil.which("gnome-terminal")` only checks if the binary exists on
PATH. In WSL, headless servers, and Docker containers, terminals can
be "installed" but non-functional. The 2-second smoke test catches
these cases.
