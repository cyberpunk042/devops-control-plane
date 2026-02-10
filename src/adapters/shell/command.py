"""
Shell command adapter — execute arbitrary shell commands.

This is the most fundamental adapter: it runs commands and captures
their output. Most other adapters are built on top of this pattern.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import time
from pathlib import Path

from src.adapters.base import Adapter, ExecutionContext
from src.core.models.action import Receipt

logger = logging.getLogger(__name__)


class ShellCommandAdapter(Adapter):
    """Execute shell commands and capture output.

    Action params:
        command (str): The command to execute.
        shell (bool): Whether to run through shell (default: True).
        timeout (int): Timeout in seconds (default: 300).
        cwd (str): Override working directory (default: context.working_dir).
    """

    @property
    def name(self) -> str:
        return "shell"

    def is_available(self) -> bool:
        # Shell is always available on Unix systems
        return shutil.which("sh") is not None

    def validate(self, context: ExecutionContext) -> tuple[bool, str]:
        command = context.action.params.get("command", "")
        if not command:
            return False, "Missing required param: 'command'"

        # Optionally validate working directory exists
        cwd = context.action.params.get("cwd", context.working_dir)
        if cwd and not Path(cwd).is_dir():
            return False, f"Working directory does not exist: {cwd}"

        return True, ""

    def execute(self, context: ExecutionContext) -> Receipt:
        command = context.action.params.get("command", "")
        use_shell = context.action.params.get("shell", True)
        timeout = context.action.params.get("timeout", 300)
        cwd = context.action.params.get("cwd", context.working_dir)

        logger.debug("Executing: %s (cwd=%s)", command, cwd)
        start = time.monotonic()

        try:
            result = subprocess.run(
                command if use_shell else command.split(),
                shell=use_shell,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            elapsed_ms = int((time.monotonic() - start) * 1000)
            output = result.stdout.strip()
            stderr = result.stderr.strip()

            if result.returncode == 0:
                return Receipt.success(
                    adapter=self.name,
                    action_id=context.action.id,
                    output=output,
                    duration_ms=elapsed_ms,
                    metadata={
                        "command": command,
                        "return_code": result.returncode,
                        "stderr": stderr,
                    },
                )
            else:
                return Receipt.failure(
                    adapter=self.name,
                    action_id=context.action.id,
                    error=stderr or f"Command exited with code {result.returncode}",
                    duration_ms=elapsed_ms,
                    metadata={
                        "command": command,
                        "return_code": result.returncode,
                        "stdout": output,
                    },
                )

        except subprocess.TimeoutExpired:
            return Receipt.failure(
                adapter=self.name,
                action_id=context.action.id,
                error=f"Command timed out after {timeout}s",
                metadata={"command": command, "timeout": timeout},
            )
        except Exception as e:
            return Receipt.failure(
                adapter=self.name,
                action_id=context.action.id,
                error=f"Command execution error: {e}",
                metadata={"command": command},
            )
