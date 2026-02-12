"""
Docker adapter — container and compose operations.

Provides Docker and Docker Compose operations through the adapter protocol.
Uses the docker CLI — never the Docker API directly.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import time
from pathlib import Path

from src.adapters.base import Adapter, ExecutionContext
from src.core.models.action import Receipt

logger = logging.getLogger(__name__)


class DockerAdapter(Adapter):
    """Docker and Docker Compose container operations.

    Action params:
        operation (str): One of 'ps', 'images', 'build', 'up', 'down',
                         'logs', 'exec', 'version'.
        compose (bool): Whether to use 'docker compose' (default: False).
        service (str): Target service name (for compose operations).
        command (str): Raw command string (fallback for stack capabilities).
        timeout (int): Timeout in seconds (default: 300).
    """

    @property
    def name(self) -> str:
        return "docker"

    def is_available(self) -> bool:
        return shutil.which("docker") is not None

    def validate(self, context: ExecutionContext) -> tuple[bool, str]:
        operation = context.action.params.get("operation", "")
        command = context.action.params.get("command", "")

        if not operation and not command:
            return False, "Missing required param: 'operation' or 'command'"

        if operation:
            valid_ops = {"ps", "images", "build", "up", "down", "logs", "exec", "version"}
            if operation not in valid_ops:
                return False, f"Unknown operation '{operation}'. Valid: {', '.join(sorted(valid_ops))}"

        return True, ""

    def execute(self, context: ExecutionContext) -> Receipt:
        # Raw command from stack capabilities
        command = context.action.params.get("command", "")
        if command and not context.action.params.get("operation"):
            return self._run_command(context, command)

        operation = context.action.params["operation"]
        try:
            if operation == "ps":
                return self._ps(context)
            elif operation == "images":
                return self._images(context)
            elif operation == "build":
                return self._build(context)
            elif operation == "up":
                return self._up(context)
            elif operation == "down":
                return self._down(context)
            elif operation == "logs":
                return self._logs(context)
            elif operation == "version":
                return self._version(context)
            else:
                return Receipt.failure(
                    adapter=self.name,
                    action_id=context.action.id,
                    error=f"Unknown operation: {operation}",
                )
        except Exception as e:
            return Receipt.failure(
                adapter=self.name,
                action_id=context.action.id,
                error=f"Docker error: {e}",
            )

    # ── Operations ──────────────────────────────────────────────

    def _ps(self, ctx: ExecutionContext) -> Receipt:
        if ctx.action.params.get("compose", False):
            output = self._docker(["compose", "ps", "--format", "table"], ctx)
        else:
            output = self._docker(["ps", "--format", "table {{.Names}}\\t{{.Status}}\\t{{.Ports}}"], ctx)
        return Receipt.success(
            adapter=self.name,
            action_id=ctx.action.id,
            output=output,
        )

    def _images(self, ctx: ExecutionContext) -> Receipt:
        output = self._docker(
            ["images", "--format", "table {{.Repository}}\\t{{.Tag}}\\t{{.Size}}"],
            ctx,
        )
        return Receipt.success(
            adapter=self.name,
            action_id=ctx.action.id,
            output=output,
        )

    def _build(self, ctx: ExecutionContext) -> Receipt:
        service = ctx.action.params.get("service", "")
        args = ["compose", "build"]
        if service:
            args.append(service)
        output = self._docker(args, ctx, timeout=600)
        return Receipt.success(
            adapter=self.name,
            action_id=ctx.action.id,
            output=output,
            metadata={"service": service or "all"},
        )

    def _up(self, ctx: ExecutionContext) -> Receipt:
        service = ctx.action.params.get("service", "")
        args = ["compose", "up", "-d"]
        if service:
            args.append(service)
        output = self._docker(args, ctx)
        return Receipt.success(
            adapter=self.name,
            action_id=ctx.action.id,
            output=output,
        )

    def _down(self, ctx: ExecutionContext) -> Receipt:
        output = self._docker(["compose", "down"], ctx)
        return Receipt.success(
            adapter=self.name,
            action_id=ctx.action.id,
            output=output,
        )

    def _logs(self, ctx: ExecutionContext) -> Receipt:
        service = ctx.action.params.get("service", "")
        args = ["compose", "logs", "--tail=50"]
        if service:
            args.append(service)
        output = self._docker(args, ctx, timeout=15)
        return Receipt.success(
            adapter=self.name,
            action_id=ctx.action.id,
            output=output,
        )

    def _version(self, ctx: ExecutionContext) -> Receipt:
        output = self._docker(["--version"], ctx)
        return Receipt.success(
            adapter=self.name,
            action_id=ctx.action.id,
            output=output,
        )

    # ── Helpers ─────────────────────────────────────────────────

    def _docker(self, args: list[str], ctx: ExecutionContext, timeout: int = 300) -> str:
        """Run a docker command and return stdout."""
        timeout = ctx.action.params.get("timeout", timeout)
        result = subprocess.run(
            ["docker", *args],
            cwd=ctx.working_dir,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or f"docker {args[0]} failed")
        return result.stdout.strip()

    def _run_command(self, ctx: ExecutionContext, command: str) -> Receipt:
        """Execute a raw command string (for stack capability compatibility)."""
        timeout = ctx.action.params.get("timeout", 300)
        start = time.monotonic()
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=ctx.working_dir,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            elapsed_ms = int((time.monotonic() - start) * 1000)
            if result.returncode == 0:
                return Receipt.success(
                    adapter=self.name,
                    action_id=ctx.action.id,
                    output=result.stdout.strip(),
                    duration_ms=elapsed_ms,
                    metadata={"command": command, "return_code": 0},
                )
            else:
                return Receipt.failure(
                    adapter=self.name,
                    action_id=ctx.action.id,
                    error=result.stderr.strip() or f"Exit code {result.returncode}",
                    duration_ms=elapsed_ms,
                    metadata={"command": command, "return_code": result.returncode},
                )
        except subprocess.TimeoutExpired:
            return Receipt.failure(
                adapter=self.name,
                action_id=ctx.action.id,
                error=f"Command timed out after {timeout}s",
                metadata={"command": command},
            )
