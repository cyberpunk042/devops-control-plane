# Adapters

> **10 files. 1,235 lines. External tool bindings through a unified protocol.**
>
> Adapters are the bridge between the control plane engine and the outside world.
> Every external side effect — running a shell command, building a Docker image,
> committing to git — flows through an adapter. Adapters never raise exceptions;
> they capture everything in a `Receipt` and return it to the engine.

---

## How It Works

The adapter layer implements the classic **Adapter pattern** with a strict
protocol contract. The engine never talks to external tools directly — it
always goes through the registry.

```
┌──────────────────────────────────────────────────────────────────┐
│                         Engine / Use Cases                       │
│                                                                  │
│    run.py ─── creates Registry ─── registers all adapters       │
│    executor.py ─── calls registry.execute_action(action)         │
└──────────────┬───────────────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────────┐
│                        AdapterRegistry                           │
│                                                                  │
│  1. Resolve adapter by action.adapter name (or mock in test)    │
│  2. Build ExecutionContext from action + environment             │
│  3. Validate (adapter.validate)                                 │
│  4. Circuit breaker check (if wired)                            │
│  5. Execute (adapter.execute)                                   │
│  6. Record circuit breaker result                               │
│  7. Add timing → return Receipt                                 │
│                                                                  │
│  Mock mode: bypass all adapters → return instant success         │
│  Dry-run mode: validate only → return skip receipt               │
└──────────┬─────────┬─────────┬──────────┬───────────┬───────────┘
           │         │         │          │           │
           ▼         ▼         ▼          ▼           ▼
       ┌───────┐ ┌───────┐ ┌───────┐ ┌────────┐ ┌────────┐
       │ Shell │ │Docker │ │  Git  │ │ Python │ │  Node  │
       │Command│ │Adapter│ │Adapter│ │Adapter │ │Adapter │
       └───┬───┘ └───┬───┘ └───┬───┘ └───┬────┘ └───┬────┘
           │         │         │          │           │
           ▼         ▼         ▼          ▼           ▼
       subprocess  docker    git CLI   python/pip  node/npm
                   CLI                              /yarn
```

### The 4-Method Contract

Every adapter implements exactly 4 abstract methods:

```
┌─────────────────────────────────────────────────┐
│              Adapter Protocol                    │
│                                                  │
│  name        → str         "docker", "git", ... │
│  is_available → bool       tool installed?       │
│  validate    → (ok, err)   params correct?       │
│  execute     → Receipt     do the work           │
│                                                  │
│  Rule: execute() NEVER raises.                   │
│  All failures are captured in Receipt.           │
└─────────────────────────────────────────────────┘
```

### Execution Flow (single action)

```
Action { adapter: "docker", id: "build-app", params: {operation: "build"} }
  │
  ├─ Registry resolves "docker" → DockerAdapter instance
  │
  ├─ ExecutionContext built:
  │     action      = Action
  │     project_root = "."
  │     environment  = "dev"
  │     working_dir  = project_root (or module_path if set)
  │
  ├─ adapter.validate(context) → (True, "")
  │     └─ checks: operation is valid, params present
  │
  ├─ Circuit breaker check → allow_request()
  │
  ├─ adapter.execute(context)
  │     └─ DockerAdapter._build(ctx)
  │           └─ subprocess: docker compose build
  │           └─ returns Receipt.success(output="...")
  │
  ├─ Circuit breaker records: success
  │
  └─ Receipt returned with duration_ms added
```

### Mock Mode

The registry supports a global mock mode for testing:

```
registry = AdapterRegistry(mock_mode=True)
# OR after creation:
registry.set_mock_mode(True, mock_adapter=MockAdapter())

# All execute_action calls now go through MockAdapter
# MockAdapter always returns Receipt.success() by default
# Can be configured per-action:
mock.set_failure("build-app", "Simulated build failure")
```

---

## File Map

```
src/adapters/
├── __init__.py              Re-exports (15 lines)
├── base.py                  Adapter ABC + ExecutionContext (86 lines)
├── mock.py                  MockAdapter test double (84 lines)
├── registry.py              AdapterRegistry dispatch (215 lines)
├── Dockerfile               Container build spec (27 lines)
├── containers/
│   ├── __init__.py          Re-exports DockerAdapter (5 lines)
│   └── docker.py            Docker/Compose operations (220 lines)
├── languages/
│   ├── __init__.py          Re-exports (6 lines)
│   ├── python.py            Python interpreter/pip/venv (240 lines)
│   └── node.py              Node.js/npm/yarn/pnpm (254 lines)
├── shell/
│   ├── __init__.py          Empty (1 line)
│   ├── command.py           Shell command execution (113 lines)
│   └── filesystem.py        File/directory operations (145 lines)
└── vcs/
    ├── __init__.py           Re-exports GitAdapter (5 lines)
    └── git.py                Git operations (246 lines)
```

---

## Per-File Documentation

### `base.py` — Adapter Protocol (86 lines)

The foundation. Defines the abstract contract that all adapters implement.

**Classes:**

| Class | Role |
|-------|------|
| `ExecutionContext` | Pydantic model — the adapter's view of the world: action, project root, environment, dry-run flag, resolved params |
| `Adapter` | ABC with 4 abstract methods: `name`, `is_available`, `validate`, `execute` |

**ExecutionContext fields:**

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `action` | `Action` | required | The action to execute (from core models) |
| `project_root` | `str` | `"."` | Root directory of the project |
| `environment` | `str` | `"dev"` | Target environment name |
| `module_path` | `str \| None` | `None` | Module path relative to root |
| `dry_run` | `bool` | `False` | Whether to simulate only |
| `params` | `dict` | `{}` | Resolved parameters from the action |

**Key property:**

- `working_dir` → resolves to `project_root/module_path` or just `project_root`

**Design contract:**

- `is_available()` — must be fast, must never raise
- `validate()` — returns `(bool, str)` tuple, not exceptions
- `execute()` — **MUST never raise**. All failures go in `Receipt.failure()`

---

### `mock.py` — Universal Test Double (84 lines)

A complete mock adapter that simulates any adapter for testing without
touching external tools.

**Class: `MockAdapter(Adapter)`**

| Method | What It Does |
|--------|-------------|
| `__init__(adapter_name, available, default_output)` | Creates a mock with configurable name and default response |
| `name` | Returns the configured adapter name (default: `"mock"`) |
| `call_log` | Property: list of all `ExecutionContext` instances received |
| `call_count` | Property: number of times `execute` was called |
| `is_available()` | Returns the configured `available` flag |
| `set_response(action_id, receipt)` | Set a custom `Receipt` for a specific action ID |
| `set_failure(action_id, error)` | Convenience: configure a specific action to return `Receipt.failure()` |
| `validate(context)` | Always returns `(True, "")` — mocks don't validate |
| `execute(context)` | Logs the call, returns custom response if set, else `Receipt.success()` |
| `reset()` | Clears call log and custom responses |

**Usage pattern:**

```python
mock = MockAdapter(adapter_name="docker")
mock.set_failure("deploy", "Docker daemon not running")

registry = AdapterRegistry()
registry.set_mock_mode(True, mock_adapter=mock)
result = registry.execute_action(action)
# result.failed == True, result.error == "Docker daemon not running"
assert mock.call_count == 1
```

---

### `registry.py` — Central Dispatch (215 lines)

The single point of adapter management. The engine never talks to adapters
directly — always through the registry.

**Class: `AdapterRegistry`**

| Method | What It Does |
|--------|-------------|
| `__init__(mock_mode, circuit_breakers)` | Creates registry, optionally with mock mode and circuit breaker integration |
| `mock_mode` | Property: whether mock mode is active |
| `set_mock_mode(enabled, mock_adapter)` | Toggle mock mode; optionally provide a custom mock |
| `register(adapter)` | Register an adapter instance by its `.name` |
| `unregister(name)` | Remove an adapter from the registry |
| `get(name)` | Look up an adapter by name, returns `None` if not found |
| `list_adapters()` | List all registered adapter names |
| `adapter_status()` | Get availability status of all adapters (`{name: {available, type}}`) |
| `execute_action(action, ...)` | **Main dispatch** — resolve → validate → execute → return Receipt |

**`execute_action` flow in detail:**

```
1. Build ExecutionContext from action + args
2. Mock mode?
   ├─ Yes + custom mock  → use mock adapter
   ├─ Yes + no mock      → return Receipt.success() immediately
   └─ No                 → look up by action.adapter name
3. Adapter not found? → Receipt.failure("No adapter registered for '...'")
4. adapter.validate(context) → failure? → Receipt.failure("Validation failed: ...")
5. Dry run? → Receipt.skip("[dry-run] Would execute ...")
6. Circuit breaker OPEN? → Receipt.failure("Circuit breaker OPEN for ...")
7. adapter.execute(context)
   └─ Exception? (defense in depth) → Receipt.failure("Unexpected error: ...")
8. Circuit breaker record: success or failure
9. Add duration_ms to receipt
10. Return receipt
```

**Circuit breaker integration:**

The registry optionally accepts a `CircuitBreakerRegistry` from
`src.core.reliability.circuit_breaker`. When wired:

- Before execution: checks if the adapter's circuit is open (too many failures)
- After execution: records success/failure for the circuit
- When open: fast-fails with a descriptive error (no subprocess call)

---

### `containers/docker.py` — Docker Adapter (220 lines)

Wraps the `docker` CLI for container and compose operations.

**Class: `DockerAdapter(Adapter)`**

| Method | What It Does |
|--------|-------------|
| `name` | Returns `"docker"` |
| `is_available()` | Checks `shutil.which("docker")` |
| `validate(context)` | Ensures `operation` or `command` param exists; validates operation names |
| `execute(context)` | Routes to operation handler or raw command |
| `_ps(ctx)` | List containers: `docker ps` or `docker compose ps` |
| `_images(ctx)` | List images: `docker images` with table format |
| `_build(ctx)` | Build service: `docker compose build [service]`, 600s timeout |
| `_up(ctx)` | Start services: `docker compose up -d [service]` |
| `_down(ctx)` | Stop services: `docker compose down` |
| `_logs(ctx)` | Get logs: `docker compose logs --tail=50 [service]` |
| `_version(ctx)` | Get version: `docker --version` |
| `_docker(args, ctx, timeout)` | Helper: runs `docker <args>` via subprocess, raises on non-zero |
| `_run_command(ctx, command)` | Fallback: execute a raw shell command string |

**Valid operations:** `ps`, `images`, `build`, `up`, `down`, `logs`, `exec`, `version`

**Action params:**

| Param | Type | Default | Purpose |
|-------|------|---------|---------|
| `operation` | `str` | — | Which docker operation to run |
| `compose` | `bool` | `False` | Use `docker compose` prefix |
| `service` | `str` | `""` | Target service name |
| `command` | `str` | `""` | Raw command string (fallback) |
| `timeout` | `int` | `300` | Command timeout in seconds |

---

### `languages/python.py` — Python Adapter (240 lines)

Wraps the Python interpreter for language-specific operations.

**Class: `PythonAdapter(Adapter)`**

| Method | What It Does |
|--------|-------------|
| `name` | Returns `"python"` |
| `is_available()` | Checks `shutil.which("python3")` or `shutil.which("python")` |
| `_python_cmd` | Property: resolves the correct interpreter command |
| `version` | Property: detects the installed Python version string |
| `validate(context)` | Ensures `operation` or `command` param exists |
| `execute(context)` | Routes to operation handler |
| `_get_version(ctx)` | Returns Python version, pip version, and venv path info |
| `_run_script(ctx)` | Runs a Python script: `python3 <script>` |
| `_create_venv(ctx)` | Creates a virtual environment: `python3 -m venv <path>` |
| `_pip_install(ctx)` | Installs packages via pip with optional requirements file |
| `_exec(ctx, cmd, timeout)` | Helper: runs a command via subprocess with full error handling |
| `_run_command(ctx, command)` | Fallback: execute a raw command string |

**Valid operations:** `version`, `run_script`, `create_venv`, `pip_install`

---

### `languages/node.py` — Node.js Adapter (254 lines)

Wraps Node.js and its ecosystem of package managers.

**Class: `NodeAdapter(Adapter)`**

| Method | What It Does |
|--------|-------------|
| `name` | Returns `"node"` |
| `is_available()` | Checks `shutil.which("node")` |
| `_detect_package_manager(cwd)` | Auto-detects npm/yarn/pnpm from lock files |
| `version` | Property: detects Node.js version |
| `validate(context)` | Ensures `operation` or `command` param exists |
| `execute(context)` | Routes to operation handler |
| `_get_version(ctx)` | Returns node, npm, and detected package manager versions |
| `_run_node(ctx)` | Runs a Node.js script: `node <script>` |
| `_install(ctx)` | Installs packages using the detected package manager |
| `_run_script(ctx)` | Runs an npm script: `<pm> run <script>` |
| `_exec(ctx, cmd, timeout)` | Helper: subprocess execution with error handling |
| `_run_command(ctx, command)` | Fallback: raw command execution |

**Valid operations:** `version`, `run`, `install`, `run_script`

**Smart package manager detection:**

```
yarn.lock    → yarn
pnpm-lock.yaml → pnpm
package-lock.json → npm (default)
```

---

### `shell/command.py` — Shell Command Adapter (113 lines)

The most fundamental adapter. Runs arbitrary shell commands.

**Class: `ShellCommandAdapter(Adapter)`**

| Method | What It Does |
|--------|-------------|
| `name` | Returns `"shell"` |
| `is_available()` | Checks `shutil.which("sh")` — always true on Unix |
| `validate(context)` | Ensures `command` param exists; validates CWD if provided |
| `execute(context)` | Runs the command via `subprocess.run`, captures stdout/stderr |

**Action params:**

| Param | Type | Default | Purpose |
|-------|------|---------|---------|
| `command` | `str` | required | The command to execute |
| `shell` | `bool` | `True` | Run through shell interpreter |
| `timeout` | `int` | `300` | Timeout in seconds |
| `cwd` | `str` | `working_dir` | Override working directory |

**Receipt metadata includes:** command string, return code, stderr (on success), stdout (on failure)

---

### `shell/filesystem.py` — Filesystem Adapter (145 lines)

Wraps file/directory operations in the receipt-returning protocol so the
engine can audit and dry-run filesystem changes.

**Class: `FilesystemAdapter(Adapter)`**

| Method | What It Does |
|--------|-------------|
| `name` | Returns `"filesystem"` |
| `is_available()` | Always `True` — filesystem is always available |
| `validate(context)` | Ensures `operation` and `path` params; validates `content` for writes |
| `execute(context)` | Routes to operation handler |
| `_exists(ctx, target)` | Checks if path exists, returns `{exists, is_dir}` metadata |
| `_read(ctx, target)` | Reads file content, returns as output string |
| `_write(ctx, target)` | Writes content to file, creates parent dirs if needed |
| `_mkdir(ctx, target)` | Creates directory with `parents=True, exist_ok=True` |
| `_list(ctx, target)` | Lists directory contents, sorted alphabetically |

**Valid operations:** `exists`, `read`, `write`, `mkdir`, `list`

---

### `vcs/git.py` — Git Adapter (246 lines)

Wraps the `git` CLI for version control operations.

**Class: `GitAdapter(Adapter)`**

| Method | What It Does |
|--------|-------------|
| `name` | Returns `"git"` |
| `is_available()` | Checks `shutil.which("git")` |
| `validate(context)` | Validates operation, ensures `message` for commits, `files` for stage |
| `execute(context)` | Routes to operation handler |
| `_status(ctx)` | Branch name, dirty state, ahead/behind, staged/modified/untracked counts |
| `_commit(ctx)` | Stages files (if provided) + commits with message |
| `_push(ctx)` | Pushes to remote (origin by default) |
| `_pull(ctx)` | Pulls with `--rebase` from remote |
| `_log(ctx)` | Shows last N commits in oneline format |
| `_branch(ctx)` | Lists branches, marks current with `*` |
| `_diff(ctx)` | Shows working directory diff |
| `_init(ctx)` | Initializes a new git repository |
| `_git(args, cwd, timeout)` | Helper: runs `git <args>` via subprocess |
| `_run_command(ctx, command)` | Fallback: raw command execution |

**Valid operations:** `status`, `commit`, `push`, `pull`, `log`, `branch`, `diff`, `init`

**Commit params:**

| Param | Type | Default | Purpose |
|-------|------|---------|---------|
| `message` | `str` | required | Commit message |
| `files` | `list[str]` | `[]` | Specific files to stage before commit |

---

## Dependency Graph

```
base.py                      ← standalone (imports from core/models only)
    │
    ├── mock.py              ← imports Adapter, ExecutionContext from base
    │
    ├── registry.py          ← imports Adapter, ExecutionContext from base
    │                          imports CircuitBreakerRegistry from core/reliability
    │
    ├── containers/docker.py ← imports Adapter, ExecutionContext from base
    │
    ├── languages/python.py  ← imports Adapter, ExecutionContext from base
    │
    ├── languages/node.py    ← imports Adapter, ExecutionContext from base
    │
    ├── shell/command.py     ← imports Adapter, ExecutionContext from base
    │
    ├── shell/filesystem.py  ← imports Adapter, ExecutionContext from base
    │
    └── vcs/git.py           ← imports Adapter, ExecutionContext from base
```

**All leaf adapters follow the same import pattern:** `base.Adapter` + `base.ExecutionContext`
+ `core.models.action.Receipt`. No adapter imports another adapter.

**External core dependencies:**

| Import | Used By |
|--------|---------|
| `src.core.models.action.Action` | `base.py`, `registry.py` |
| `src.core.models.action.Receipt` | All adapters + `registry.py` |
| `src.core.reliability.circuit_breaker.CircuitBreakerRegistry` | `registry.py` only |

---

## Consumers

| Layer | Module | What It Uses |
|-------|--------|-------------|
| Engine | `core/engine/executor.py` | `AdapterRegistry` — dispatches actions |
| Use Cases | `core/use_cases/run.py` | `AdapterRegistry` — creates and populates the registry |
| Use Cases | `core/use_cases/run.py` | All 6 concrete adapters — registers each one |
| `__init__.py` | `src/adapters/__init__.py` | Re-exports `Adapter`, `AdapterRegistry`, `ExecutionContext`, `MockAdapter` |

**Registration happens in `core/use_cases/run.py`:**

```python
registry = AdapterRegistry()
registry.register(ShellCommandAdapter())
registry.register(FilesystemAdapter())
registry.register(GitAdapter())
registry.register(DockerAdapter())
registry.register(PythonAdapter())
registry.register(NodeAdapter())
```

---

## Design Decisions

### Why the Adapter Pattern?

The engine needs to orchestrate external tools (docker, git, python, npm, etc.)
without being coupled to any of them. The adapter pattern provides:

1. **Uniform interface** — the engine calls `execute_action()` for everything
2. **Testability** — swap all adapters for `MockAdapter` in one call
3. **Validation** — every action is validated before execution
4. **Safety** — adapters never raise, so the engine always gets a result
5. **Circuit breaking** — automatic failure detection and fast-fail

### Why `Receipt` instead of exceptions?

Adapters perform **external side effects** (subprocess calls, file I/O). These
can fail in unpredictable ways. Instead of trying/catching everywhere:

- `Receipt.success()` — tool ran, here's the output
- `Receipt.failure()` — tool failed, here's why
- `Receipt.skip()` — dry-run, nothing was done

The engine always gets structured feedback, never an unhandled exception.

### Why separate `shell/command.py` and `shell/filesystem.py`?

They serve different purposes:

- **ShellCommandAdapter** — runs arbitrary commands, captures output
- **FilesystemAdapter** — structured file operations (read/write/list)

Keeping them separate means filesystem operations can be audited and dry-run
independently of shell commands. A filesystem write can be prevented in
dry-run mode, while a shell read command might still be allowed.

### Why `_run_command` on every adapter?

Several adapters (Docker, Python, Node, Git) have a `_run_command` fallback
that executes raw command strings. This exists for **stack capability
compatibility** — when the engine's stack definitions include raw commands
for a specific tool, the adapter can still execute them without routing
through the shell adapter.

### Why `shutil.which()` for availability?

Every adapter checks tool availability using `shutil.which()`:

- Fast (stat call, not subprocess)
- Never raises
- Works cross-platform
- Returns `None` if not found (clean boolean check)

### Why circuit breakers at the registry level?

Circuit breakers are wired at the registry, not inside individual adapters.
This keeps adapters simple (4 methods only) and centralizes failure tracking.
The registry checks/records circuit state around every `execute_action` call.

---

## Adding a New Adapter

Step-by-step process to add a new adapter (e.g., `terraform`):

### 1. Create the adapter file

```python
# src/adapters/infrastructure/terraform.py
from src.adapters.base import Adapter, ExecutionContext
from src.core.models.action import Receipt

class TerraformAdapter(Adapter):
    @property
    def name(self) -> str:
        return "terraform"

    def is_available(self) -> bool:
        return shutil.which("terraform") is not None

    def validate(self, context: ExecutionContext) -> tuple[bool, str]:
        operation = context.action.params.get("operation", "")
        if not operation:
            return False, "Missing required param: 'operation'"
        valid = {"init", "plan", "apply", "destroy"}
        if operation not in valid:
            return False, f"Unknown operation '{operation}'"
        return True, ""

    def execute(self, context: ExecutionContext) -> Receipt:
        # Route to operation handlers, return Receipt
        ...
```

### 2. Create the sub-package `__init__.py`

```python
# src/adapters/infrastructure/__init__.py
"""Infrastructure adapters — terraform, pulumi."""
from src.adapters.infrastructure.terraform import TerraformAdapter
__all__ = ["TerraformAdapter"]
```

### 3. Register in `core/use_cases/run.py`

```python
from src.adapters.infrastructure.terraform import TerraformAdapter
registry.register(TerraformAdapter())
```

### 4. Rules to follow

- **NEVER raise from `execute()`** — capture all errors in `Receipt.failure()`
- **Keep `is_available()` fast** — use `shutil.which()`, not subprocess
- **Return structured metadata** — include command, return code, etc.
- **Support `_run_command` fallback** — for stack capability raw commands
- **One adapter per tool** — don't mix docker + terraform in one adapter

---

## Data Shapes

### ExecutionContext

```python
ExecutionContext(
    action=Action(
        id="build-app",
        adapter="docker",
        params={"operation": "build", "service": "web"},
    ),
    project_root="/home/user/project",
    environment="dev",
    module_path=None,          # or "src/services/api"
    dry_run=False,
    params={"operation": "build", "service": "web"},  # from action
)
```

### Receipt (success)

```python
Receipt(
    adapter="docker",
    action_id="build-app",
    status="success",
    ok=True,
    failed=False,
    output="Building 3 services...\nSuccessfully built",
    error=None,
    duration_ms=4520,
    metadata={"service": "all"},
)
```

### Receipt (failure)

```python
Receipt(
    adapter="docker",
    action_id="build-app",
    status="failed",
    ok=False,
    failed=True,
    output=None,
    error="docker compose build failed: Dockerfile not found",
    duration_ms=150,
    metadata={"command": "docker compose build", "return_code": 1},
)
```

### AdapterRegistry status

```python
registry.adapter_status()
# {
#     "shell": {"name": "shell", "available": True, "type": "ShellCommandAdapter"},
#     "docker": {"name": "docker", "available": True, "type": "DockerAdapter"},
#     "git": {"name": "git", "available": False, "type": "GitAdapter"},
#     ...
# }
```
