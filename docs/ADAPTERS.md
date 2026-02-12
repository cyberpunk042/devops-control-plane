# Adapters Guide

> How to use and create adapters for the DevOps Control Plane.

---

## What is an Adapter?

An **adapter** is a pluggable component that executes actions against external
tools. The engine never talks to tools directly — it dispatches `Action` objects
through the `AdapterRegistry`, which routes them to the right adapter and
collects `Receipt` results.

Adapters **never raise exceptions**. All failures are captured in the `Receipt`.

---

## Built-in Adapters

| Adapter | Module | Tool | Description |
|---|---|---|---|
| `shell` | `src.adapters.shell.command` | `sh` | Execute arbitrary shell commands |
| `filesystem` | `src.adapters.shell.filesystem` | — | File and directory operations |
| `git` | `src.adapters.vcs.git` | `git` | Version control operations (status, commit, push, pull, log, branch, diff) |
| `docker` | `src.adapters.containers.docker` | `docker` | Container and Docker Compose operations (ps, images, build, up, down, logs) |
| `python` | `src.adapters.languages.python` | `python3` | Python toolchain (version, run, venv, pip install) |
| `node` | `src.adapters.languages.node` | `node` | Node.js toolchain (version, run, install, npm scripts) with auto-detect for npm/yarn/pnpm |

All adapters are registered automatically when the engine starts. Each adapter's
`is_available()` method checks if the underlying CLI tool exists on the system.

---

## The Adapter Protocol

Every adapter extends the `Adapter` ABC from `src/adapters/base.py`:

```python
from src.adapters.base import Adapter, ExecutionContext
from src.core.models.action import Receipt


class MyAdapter(Adapter):
    """Custom adapter implementation."""

    @property
    def name(self) -> str:
        return "my-adapter"

    def is_available(self) -> bool:
        """Check if the underlying tool exists."""
        return shutil.which("my-tool") is not None

    def validate(self, context: ExecutionContext) -> tuple[bool, str]:
        """Validate the action before execution."""
        command = context.action.params.get("command", "")
        if not command:
            return False, "Missing required param: 'command'"
        return True, ""

    def execute(self, context: ExecutionContext) -> Receipt:
        """Execute the action. NEVER raise — capture errors in Receipt."""
        try:
            result = do_something(context.action.params)
            return Receipt.success(
                adapter=self.name,
                action_id=context.action.id,
                output=result,
            )
        except Exception as e:
            return Receipt.failure(
                adapter=self.name,
                action_id=context.action.id,
                error=str(e),
            )
```

### Required Methods

| Method | Purpose |
|---|---|
| `name` (property) | Unique identifier, matches `adapter:` field in stack capabilities |
| `is_available()` | Quick check if the tool exists (e.g., `shutil.which("git")`) |
| `validate(context)` | Pre-flight validation, returns `(ok, error_message)` |
| `execute(context)` | Run the action, return a `Receipt` |

---

## ExecutionContext

The context object passed to `validate()` and `execute()`:

| Field | Type | Description |
|---|---|---|
| `action` | `Action` | The action to execute (contains `id`, `adapter`, `params`) |
| `project_root` | `str` | Absolute path to project root |
| `environment` | `str` | Target environment name (e.g., "dev") |
| `module_path` | `str | None` | Relative path to the module |
| `dry_run` | `bool` | If True, validate but don't execute |
| `params` | `dict` | Same as `action.params` (convenience shortcut) |
| `working_dir` | `str` (property) | Resolved `project_root/module_path` |

---

## Receipt

Actions return a `Receipt` with the result:

```python
# Success
Receipt.success(adapter="git", action_id="...", output="branch=main, dirty=False")

# Failure (NEVER raise — use this instead)
Receipt.failure(adapter="git", action_id="...", error="not a git repository")

# Skip (e.g., dry run)
Receipt.skip(adapter="git", action_id="...", reason="dry run")
```

Receipt fields: `status` ("ok" | "failed" | "skipped"), `output`, `error`,
`duration_ms`, `metadata`, `started_at`, `ended_at`.

---

## Registering an Adapter

Register your adapter with the `AdapterRegistry`:

```python
from src.adapters.registry import AdapterRegistry

registry = AdapterRegistry()
registry.register(MyAdapter())

# The adapter is selected when action.adapter == "my-adapter"
```

All built-in adapters are auto-registered in `src/core/use_cases/run.py`.
To add a new adapter to the default set, add it there.

In a stack definition, reference your adapter by name:

```yaml
capabilities:
  - name: deploy
    adapter: my-adapter       # Matches MyAdapter.name
    command: "deploy --env $ENV"
```

---

## Stack Capability Compatibility

All built-in adapters support a **raw command fallback**: if the action's
`params` contain a `command` key (as stack capabilities do), the adapter
will execute that command string directly via `subprocess`. This means you
can reference any adapter in a stack capability without needing structured
`operation` params — the adapter handles both patterns.

---

## Circuit Breaker Integration

The `AdapterRegistry` integrates with the circuit breaker system. If an
adapter fails repeatedly, its circuit breaker opens and subsequent requests
are short-circuited with a failure receipt until the breaker recovers.

---

## Testing Adapters

Use mock mode or direct instantiation:

```python
from src.adapters.registry import AdapterRegistry
from src.core.models.action import Action

def test_my_adapter():
    adapter = MyAdapter()
    registry = AdapterRegistry()
    registry.register(adapter)

    action = Action(
        id="test-1",
        adapter="my-adapter",
        capability="test",
        params={"command": "echo hello"},
    )

    receipt = registry.execute_action(
        action, project_root="/tmp", environment="dev",
    )
    assert receipt.ok
```

For mock mode testing:

```python
registry = AdapterRegistry(mock_mode=True)
# All actions return success without executing
```
