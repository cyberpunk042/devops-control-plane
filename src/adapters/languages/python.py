"""
Python adapter — Python toolchain operations.

Detects Python availability and version, runs Python-specific
commands through the adapter protocol.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import time

from src.adapters.base import Adapter, ExecutionContext
from src.core.models.action import Receipt

logger = logging.getLogger(__name__)


class PythonAdapter(Adapter):
    """Python language toolchain adapter.

    Detects the Python interpreter and provides operations like
    running scripts, managing virtual environments, and executing
    package managers.

    Action params:
        operation (str): One of 'version', 'run', 'venv', 'pip_install'.
        script (str): Script path (for 'run').
        args (list[str]): Arguments (for 'run').
        command (str): Raw command string (fallback for stack capabilities).
        timeout (int): Timeout in seconds (default: 300).
    """

    @property
    def name(self) -> str:
        return "python"

    def is_available(self) -> bool:
        return shutil.which("python3") is not None or shutil.which("python") is not None

    def _python_cmd(self) -> str:
        """Resolve the Python interpreter command."""
        if shutil.which("python3"):
            return "python3"
        return "python"

    def version(self) -> str | None:
        """Detect the Python version string."""
        try:
            result = subprocess.run(
                [self._python_cmd(), "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                # "Python 3.12.8" → "3.12.8"
                match = re.search(r"(\d+\.\d+\.\d+)", result.stdout + result.stderr)
                return match.group(1) if match else None
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return None

    def validate(self, context: ExecutionContext) -> tuple[bool, str]:
        operation = context.action.params.get("operation", "")
        command = context.action.params.get("command", "")

        if not operation and not command:
            return False, "Missing required param: 'operation' or 'command'"

        if operation:
            valid_ops = {"version", "run", "venv", "pip_install"}
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
            if operation == "version":
                return self._get_version(context)
            elif operation == "run":
                return self._run_script(context)
            elif operation == "venv":
                return self._create_venv(context)
            elif operation == "pip_install":
                return self._pip_install(context)
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
                error=f"Python error: {e}",
            )

    # ── Operations ──────────────────────────────────────────────

    def _get_version(self, ctx: ExecutionContext) -> Receipt:
        ver = self.version()
        if ver:
            return Receipt.success(
                adapter=self.name,
                action_id=ctx.action.id,
                output=ver,
                metadata={"version": ver, "interpreter": self._python_cmd()},
            )
        return Receipt.failure(
            adapter=self.name,
            action_id=ctx.action.id,
            error="Could not determine Python version",
        )

    def _run_script(self, ctx: ExecutionContext) -> Receipt:
        script = ctx.action.params.get("script", "")
        args = ctx.action.params.get("args", [])
        if not script:
            return Receipt.failure(
                adapter=self.name,
                action_id=ctx.action.id,
                error="Missing 'script' param",
            )
        cmd = [self._python_cmd(), script, *args]
        return self._exec(ctx, cmd)

    def _create_venv(self, ctx: ExecutionContext) -> Receipt:
        venv_path = ctx.action.params.get("path", ".venv")
        cmd = [self._python_cmd(), "-m", "venv", venv_path]
        return self._exec(ctx, cmd)

    def _pip_install(self, ctx: ExecutionContext) -> Receipt:
        packages = ctx.action.params.get("packages", [])
        requirements = ctx.action.params.get("requirements", "")
        editable = ctx.action.params.get("editable", False)

        cmd = [self._python_cmd(), "-m", "pip", "install"]
        if editable:
            cmd.extend(["-e", "."])
        elif requirements:
            cmd.extend(["-r", requirements])
        elif packages:
            cmd.extend(packages)
        else:
            cmd.extend(["-e", "."])

        return self._exec(ctx, cmd, timeout=600)

    # ── Helpers ─────────────────────────────────────────────────

    def _exec(
        self,
        ctx: ExecutionContext,
        cmd: list[str],
        timeout: int = 300,
    ) -> Receipt:
        timeout = ctx.action.params.get("timeout", timeout)
        start = time.monotonic()
        try:
            result = subprocess.run(
                cmd,
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
                    metadata={"command": " ".join(cmd), "return_code": 0},
                )
            else:
                return Receipt.failure(
                    adapter=self.name,
                    action_id=ctx.action.id,
                    error=result.stderr.strip() or f"Exit code {result.returncode}",
                    duration_ms=elapsed_ms,
                    metadata={"command": " ".join(cmd), "return_code": result.returncode},
                )
        except subprocess.TimeoutExpired:
            return Receipt.failure(
                adapter=self.name,
                action_id=ctx.action.id,
                error=f"Command timed out after {timeout}s",
                metadata={"command": " ".join(cmd)},
            )

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
