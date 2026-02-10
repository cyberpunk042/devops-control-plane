# Adapters Guide

> How to create custom adapters for the DevOps Control Plane.

---

## What is an Adapter?

An **adapter** is a pluggable component that executes actions. The built-in `ShellCommandAdapter` runs shell commands, but you can create adapters for any execution target — Docker, Kubernetes, cloud APIs, CI/CD systems, etc.

---

## The Adapter Protocol

Every adapter implements the `Adapter` protocol defined in `src/adapters/protocol.py`:

```python
from src.adapters.protocol import Adapter, ExecutionContext
from src.core.models.action import Receipt


class MyAdapter(Adapter):
    """Custom adapter implementation."""

    @property
    def name(self) -> str:
        """Unique identifier for this adapter."""
        return "my-adapter"

    def can_handle(self, context: ExecutionContext) -> bool:
        """Whether this adapter can handle the given context."""
        return context.adapter == self.name

    def execute(self, context: ExecutionContext) -> Receipt:
        """Execute the action described by the context."""
        try:
            # Your execution logic here
            result = do_something(context.command, context.params)

            return Receipt.success(
                adapter=self.name,
                action_id=context.action_id,
                output=result,
            )
        except Exception as e:
            return Receipt.failure(
                adapter=self.name,
                action_id=context.action_id,
                output=str(e),
            )
```

---

## ExecutionContext

The context object passed to `execute()` contains:

| Field | Type | Description |
|---|---|---|
| `adapter` | `str` | Target adapter name |
| `action_id` | `str` | Unique action identifier |
| `command` | `str` | Command to execute |
| `project_root` | `str` | Absolute path to project root |
| `module_path` | `str` | Relative path to the module |
| `environment` | `str` | Target environment name |
| `dry_run` | `bool` | If True, simulate without executing |
| `params` | `dict` | Additional parameters |

---

## Receipt

Actions return a `Receipt` with the result:

```python
# Success
Receipt.success(adapter="my-adapter", action_id="...", output="all good")

# Failure
Receipt.failure(adapter="my-adapter", action_id="...", output="error details")

# Skip (e.g., dry run)
Receipt.skip(adapter="my-adapter", action_id="...", reason="dry run")
```

---

## Registering an Adapter

Register your adapter with the `AdapterRegistry`:

```python
from src.adapters.registry import AdapterRegistry

registry = AdapterRegistry()
registry.register(MyAdapter())

# The adapter will be selected when action.adapter == "my-adapter"
```

In a stack definition, reference your adapter:

```yaml
capabilities:
  - name: deploy
    adapter: my-adapter       # Matches MyAdapter.name
    command: "deploy --env $ENV"
```

---

## Example: Docker Adapter

```python
import subprocess
from src.adapters.protocol import Adapter, ExecutionContext
from src.core.models.action import Receipt


class DockerAdapter(Adapter):
    @property
    def name(self) -> str:
        return "docker"

    def can_handle(self, context: ExecutionContext) -> bool:
        return context.adapter == "docker"

    def execute(self, context: ExecutionContext) -> Receipt:
        if context.dry_run:
            return Receipt.skip(
                adapter=self.name,
                action_id=context.action_id,
                reason="dry run — would run docker command",
            )

        cmd = context.command
        workdir = f"{context.project_root}/{context.module_path}"

        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True,
                cwd=workdir, timeout=300,
            )

            if result.returncode == 0:
                return Receipt.success(
                    adapter=self.name,
                    action_id=context.action_id,
                    output=result.stdout,
                )
            else:
                return Receipt.failure(
                    adapter=self.name,
                    action_id=context.action_id,
                    output=result.stderr,
                )

        except subprocess.TimeoutExpired:
            return Receipt.failure(
                adapter=self.name,
                action_id=context.action_id,
                output="Command timed out after 300s",
            )
```

---

## Testing Adapters

Use mock mode and the test infrastructure:

```python
import pytest
from src.adapters.registry import AdapterRegistry
from src.core.models.action import Action, Receipt


def test_my_adapter():
    adapter = MyAdapter()
    registry = AdapterRegistry()
    registry.register(adapter)

    action = Action(
        id="test-1",
        adapter="my-adapter",
        capability="test",
        command="echo hello",
        module_name="api",
    )

    receipt = registry.execute_action(action, project_root="/tmp", environment="dev")
    assert receipt.ok
```

---

## Built-in Adapters

| Adapter | Module | Description |
|---|---|---|
| `shell` | `src.adapters.shell.command` | Executes shell commands via subprocess |

The shell adapter is registered by default and handles most use cases through stack capability commands.
