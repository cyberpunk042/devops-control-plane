# Tool Install Service

> The provisioning engine for the devops control plane.
> Handles EVERYTHING from simple CLI tool installs to complex
> multi-step software provisioning with GPU detection, kernel management,
> build-from-source chains, data pack downloads, and system configuration.

---

## How It Works

This is NOT a static script runner. It is an **adaptive resolution engine**
that reads the target machine, picks the right approach, resolves dependencies
transitively, and produces an executable plan — all before a single command runs.

### The Resolution Pipeline

```
      RECIPE                    SYSTEM PROFILE              USER CHOICES
   (what to install)         (what we're running on)      (optional overrides)
        │                          │                            │
        ▼                          ▼                            ▼
┌──────────────────────────────────────────────────────────────────────┐
│                        L2 RESOLVER                                   │
│                                                                      │
│  1. METHOD SELECTION                                                 │
│     Recipe says: install via apt, dnf, brew, snap, pip, cargo, or    │
│     _default. Resolver reads system profile → picks the RIGHT one.   │
│     Priority: recipe prefer → system primary PM → snap → _default    │
│     → any PM binary on PATH.                                         │
│                                                                      │
│  2. DEPENDENCY COLLECTION (transitive, depth-first)                  │
│     cargo-audit requires cargo → cargo requires rustup → rustup      │
│     has no deps. Walk bottom-up, collecting system packages           │
│     per distro family (debian→libssl-dev, rhel→openssl-devel).       │
│     Batchable system packages are grouped into ONE apt/dnf call.     │
│                                                                      │
│  3. REPO SETUP                                                       │
│     If the recipe declares repo_setup for this PM, those steps       │
│     go FIRST — add PPA, import GPG key, apt-get update — before      │
│     any package install.                                             │
│                                                                      │
│  4. POST-ENV PROPAGATION                                             │
│     rustup adds ~/.cargo/bin to PATH. The resolver propagates        │
│     this env to ALL subsequent steps so cargo is found immediately.  │
│                                                                      │
│  5. CHOICE RESOLUTION (when recipe has choices)                      │
│     Present all options — available AND unavailable (with reasons).   │
│     User picks. Resolver applies selection to the plan.              │
│     Auto-select when only one option is available.                   │
│                                                                      │
│  6. PLAN ASSEMBLY                                                    │
│     Ordered steps: repo_setup → packages → tools → post_install →   │
│     verify. Each step has: type, command, needs_sudo, label.         │
│                                                                      │
│  OUTPUT: A plan dict — deterministic for same inputs.                │
└──────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────────────────────────────────┐
│                        L4/L5 EXECUTION                               │
│                                                                      │
│  Each step dispatched to its type executor:                          │
│    repo_setup → _execute_repo_step                                   │
│    packages   → _execute_package_step                                │
│    tool       → _execute_command_step (or streaming via Popen)       │
│    verify     → _execute_verify_step                                 │
│    ...14 step types total                                            │
│                                                                      │
│  Execution modes:                                                    │
│    BLOCKING  — subprocess.run, returns result dict (fast steps)      │
│    STREAMING — Popen, yields lines live (long builds)                │
│    DAG       — parallel steps respecting PM lock constraints         │
│                                                                      │
│  On failure → _analyse_install_failure → remediation options         │
│  Plan state persisted → resumable after interruption                 │
└──────────────────────────────────────────────────────────────────────┘
```

### Platform Adaptation — Concrete Example

Same user action: **"Install cargo-audit"**

**On Ubuntu 22.04:**
```
1. repo_setup  — (none needed for cargo-audit on Ubuntu)
2. packages    — apt-get install -y pkg-config libssl-dev
3. tool        — curl ... | sh -s -- -y                    (install rustup)
4. tool        — cargo install cargo-audit                  (with PATH propagated)
5. verify      — cargo audit --version
```

**On Fedora 39:**
```
1. repo_setup  — (none needed)
2. packages    — dnf install -y pkgconf-pkg-config openssl-devel
3. tool        — curl ... | sh -s -- -y                    (install rustup)
4. tool        — cargo install cargo-audit
5. verify      — cargo audit --version
```

**On Alpine:**
```
1. repo_setup  — (none needed)
2. packages    — apk add pkgconf openssl-dev
3. tool        — curl ... | sh -s -- -y                    (install rustup)
4. tool        — cargo install cargo-audit
5. verify      — cargo audit --version
```

**On macOS:**
```
1. repo_setup  — (none needed)
2. packages    — brew install pkg-config openssl@3
3. tool        — curl ... | sh -s -- -y                    (install rustup)
4. tool        — cargo install cargo-audit
5. verify      — cargo audit --version
```

The user did NOTHING different. The resolver read the system profile and
picked the right packages, the right package manager commands, the right
flags. The recipe is ONE dict — the intelligence is in the resolver.

---

## Architecture (Onion Layers)

```
┌─────────────────────────────────────────────────┐
│ HTTP / SSE (routes_audit.py)                    │  Thin transport layer
└─────────────┬───────────────────────────────────┘
              │
┌─────────────▼───────────────────────────────────┐
│ L5 ORCHESTRATION                                │  Plan lifecycle
│  install_tool · execute_plan_dag · resume_plan  │  create → execute → persist → resume
└─────────────┬───────────────────────────────────┘
              │ composes
    ┌─────────┴─────────┐
    ▼                   ▼
┌──────────────┐  ┌──────────────┐
│ L2 RESOLVER  │  │ L4 EXECUTION │
│ Produces     │  │ Runs         │
│ plans from   │  │ commands     │
│ recipes +    │  │ writes files │
│ system state │  │ manages      │
│              │  │ plan state   │
└──────┬───────┘  └──────┬───────┘
       │ reads           │ reads
       ▼                 ▼
┌──────────────┐  ┌──────────────┐
│ L1 DOMAIN    │  │ L3 DETECTION │
│ Pure logic   │  │ Reads system │
│ risk, DAG,   │  │ hardware,    │
│ rollback,    │  │ versions,    │
│ validation   │  │ network,     │
│              │  │ packages     │
└──────┬───────┘  └──────────────┘
       │ reads
       ▼
┌──────────────┐
│ L0 DATA      │
│ 61 recipes   │
│ constants    │
│ undo catalog │
└──────────────┘
```

### Layer Rules

| Rule | Meaning |
|------|---------|
| Inner never imports outer | `risk.py` (L1) NEVER imports `subprocess_runner.py` (L4) |
| Outer can import inner | `orchestrator.py` (L5) imports `dag.py` (L1) + `step_executors.py` (L4) |
| L3 is read-only | Detection reads but NEVER writes/mutates |
| L2 is deterministic | Same inputs → same plan. Always. |
| All side effects in L4 | Subprocess calls that write, config changes, state persistence |

---

## Principles (from arch-principles.md)

These are invariants, not suggestions:

1. **Always present, sometimes disabled** — Every option at every choice point
   is returned. Unavailable options are marked `available: false` with a
   `disabled_reason` and `enable_hint`. Never filtered out.

2. **User decides, system suggests** — Resolver recommends defaults.
   User can override anything. No silent choices.

3. **Branches are explicit** — If install method changes per platform,
   that's a named choice with visible options. No hidden conditionals.

4. **Plans are deterministic** — Same inputs → same plan. Every time.
   No randomness, no time-dependent logic.

5. **Extensibility by addition** — New tool = add recipe dict. New step type =
   add handler. No restructuring. Phase 2's ruff recipe works unchanged in Phase 8.

6. **Nothing off-limits with safeguards** — Kernel modules, GPU drivers,
   bootloader updates — all automatable with proper risk levels,
   confirmation gates, backup steps, and rollback instructions.

7. **Data is the interface** — Resolver produces data (dicts/JSON). Frontend
   renders data. Backend testable without browser. CLI/TUI/WEB same data.

8. **Resumable plans** — Plans persist to disk. Interruptible and resumable
   after network failure, reboot, or browser close.

---

## Two-Tier Detection

| Tier | When | Budget | What |
|------|------|--------|------|
| **Fast** | Every audit scan | ~120ms | OS, distro, family, PMs, container, capabilities |
| **Deep** | On demand (cached) | ~2s | GPU, CUDA, kernel, disk, network, compilers |

The fast tier is `_detect_os()` from `l0_detection.py`. It feeds the
system profile that the resolver uses for method selection.

The deep tier lives in L3 Detection and runs when the user enters a
provisioning flow. Results are cached per session.

---

## Key Data Shapes

### Recipe (L0) — What CAN be installed

A recipe is a **declarative specification**, not a script. It declares
WHAT is needed per platform. The resolver figures out HOW.

```python
"cargo-audit": {
    "label": "cargo-audit",

    # Per-method install commands — resolver PICKS the right one
    "install": {
        "_default": ["cargo", "install", "cargo-audit"],      # universal fallback
        "apt":      ["apt-get", "install", "-y", "cargo-audit"],  # if packaged
    },

    # Per-method sudo — resolver READS the right one
    "needs_sudo": {"_default": False, "apt": True},

    # Dependencies — resolver WALKS these transitively
    "requires": {
        "binaries": ["cargo"],                  # → resolver recurses into "cargo" recipe
        "packages": {                            # → resolver reads distro family
            "debian": ["pkg-config", "libssl-dev"],
            "rhel":   ["pkgconf-pkg-config", "openssl-devel"],
            "alpine": ["pkgconf", "openssl-dev"],
            "arch":   ["pkgconf", "openssl"],
            "suse":   ["pkg-config", "libopenssl-devel"],
            "macos":  ["pkg-config", "openssl@3"],
        },
    },

    # Repo setup — resolver includes BEFORE package install, per PM
    "repo_setup": {
        "apt": [
            {"label": "Add PPA", "command": [...], "needs_sudo": True},
            {"label": "Update list", "command": ["apt-get", "update"], "needs_sudo": True},
        ],
    },

    # Environment propagation — resolver injects into subsequent steps
    "post_env": 'export PATH="$HOME/.cargo/bin:$PATH"',

    # Interactive choices — resolver presents, user decides
    "choices": [{
        "id": "variant",
        "label": "Installation variant",
        "options": [
            {"id": "stable", "label": "Stable", "available": true},
            {"id": "nightly", "label": "Nightly", "available": true},
        ],
    }],

    # Verification — resolver appends as final step
    "verify": ["cargo", "audit", "--version"],

    # Risk, rollback, restart — resolver includes in plan metadata
    "risk": "low",
    "rollback": {"_default": ["cargo", "uninstall", "cargo-audit"]},
    "restart_required": "shell",
}
```

### System Profile (L3 output → L2 input)

Produced by `_detect_os()`. This is what makes recipes platform-adaptive:

```python
{
    "os": "linux",
    "distro": "ubuntu",
    "distro_version": "22.04",
    "distro_family": "debian",        # ← used to pick system packages
    "arch": "x86_64",
    "package_manager": {
        "primary": "apt",              # ← used to pick install method
        "snap_available": True,        # ← snap fallback available?
    },
}
```

### Plan (L2 output → L5 input)

The resolver produces this. The executor consumes it.
Steps are ordered: repo_setup → packages → tools → post_install → verify.

```python
{
    "tool": "cargo-audit",
    "label": "cargo-audit",
    "needs_sudo": True,
    "already_installed": False,
    "steps": [...]  # Ordered list of step dicts
}
```

### Step Types

| Type | Executor | What It Does |
|------|----------|--------------|
| `repo_setup` | `_execute_repo_step` | Add PPA, RPM repo, GPG key |
| `packages` | `_execute_package_step` | Batched system package install |
| `tool` | `_execute_command_step` | Install a tool binary |
| `post_install` | `_execute_command_step` | Post-install config commands |
| `verify` | `_execute_verify_step` | Verify installation (exit 0) |
| `config` | `_execute_config_step` | Write/modify config files |
| `shell_config` | `_execute_shell_config_step` | Add lines to .bashrc/.zshrc |
| `service` | `_execute_service_step` | Start/enable systemd services |
| `download` | `_execute_download_step` | Download file to disk |
| `github_release` | `_execute_github_release_step` | Download GitHub release binary |
| `source` | `_execute_source_step` | Clone/checkout source repo |
| `build` | `_execute_build_step` | Build from source |
| `install` | `_execute_install_step` | Install built artifacts |
| `cleanup` | `_execute_cleanup_step` | Remove temp files |
| `notification` | `_execute_notification_step` | Emit user-facing messages |

---

## Execution Modes

| Mode | Implementation | Use Case |
|------|---------------|----------|
| **Blocking** | `subprocess.run(capture_output=True)` | Fast steps (packages, verify) — returns result dict |
| **Streaming** | `Popen(stdout=PIPE, stderr=STDOUT)` | Long steps (cargo install, builds) — yields lines live |
| **DAG** | `execute_plan_dag()` | Parallel steps respecting PM lock constraints |

---

## Security Invariants

| Invariant | Implementation |
|-----------|---------------|
| Password via stdin only | `sudo -S` with `stdin.write(password)` |
| Credentials never logged | Password never in command args |
| Cached sudo invalidated | `sudo -k` on every call |
| curl\|bash scripts verified | SHA256 check via `execution/script_verify.py` |

---

## Adding a New Tool

Add ONE recipe dict to `data/recipes.py`. The resolver handles everything else:

```python
"my-tool": {
    "label": "My Tool",
    "install": {
        "_default": ["pip", "install", "my-tool"],        # universal
        "apt": ["apt-get", "install", "-y", "my-tool"],   # if packaged for debian
    },
    "needs_sudo": {"_default": False, "apt": True},
    "requires": {
        "packages": {
            "debian": ["libfoo-dev"],
            "rhel": ["foo-devel"],
        },
    },
    "verify": ["my-tool", "--version"],
}
```

That's it. The resolver will:
- Pick apt on Ubuntu, dnf on Fedora, pip on anything else
- Install libfoo-dev or foo-devel depending on distro family
- Run pip install or apt-get install depending on selected method
- Verify the tool is installed

No code changes. No new step definitions. Just data.

---

## Layer Documentation

- **[L0 DATA](data/README.md)** — Recipes, constants, undo catalog
- **[L1 DOMAIN](domain/README.md)** — Risk, DAG, rollback, validation
- **[L2 RESOLVER](resolver/README.md)** — Method selection, dependency collection, plan resolution
- **[L3 DETECTION](detection/README.md)** — Hardware, packages, versions, network
- **[L4 EXECUTION](execution/README.md)** — Subprocess runner, step executors, plan state
- **[L5 ORCHESTRATION](orchestration/README.md)** — Plan lifecycle, tool management

---

## API Endpoints

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/tools/status` | GET | All tool availability (fast tier detection) |
| `/api/audit/resolve-choices` | POST | Choice questions for a tool |
| `/api/audit/install-plan` | POST | Resolve install plan |
| `/api/audit/install-plan/execute` | POST | Execute plan (SSE stream) |
| `/api/audit/install-plan/pending` | GET | List interrupted plans |
| `/api/audit/install-plan/resume` | POST | Resume interrupted plan |
| `/api/audit/install-tool` | POST | Legacy single-command install |
| `/api/audit/remediate` | POST | Run remediation command (SSE) |
| `/api/audit/check-deps` | POST | Check system package availability |
| `/api/audit/check-updates` | POST | Check if tool has updates |
| `/api/audit/tool-version` | POST | Get installed version |
| `/api/audit/update-tool` | POST | Update a tool |
