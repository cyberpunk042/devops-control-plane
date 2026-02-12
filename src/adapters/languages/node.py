"""
Node.js adapter — Node/npm/yarn/pnpm toolchain operations.

Detects Node.js availability and version, runs Node-specific
commands through the adapter protocol.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import time
from pathlib import Path

from src.adapters.base import Adapter, ExecutionContext
from src.core.models.action import Receipt

logger = logging.getLogger(__name__)


class NodeAdapter(Adapter):
    """Node.js language toolchain adapter.

    Detects the Node interpreter and package managers, provides
    operations for running scripts, installing packages, and
    executing npm/yarn/pnpm commands.

    Action params:
        operation (str): One of 'version', 'run', 'install', 'script'.
        script (str): npm script name (for 'script').
        package_manager (str): 'npm', 'yarn', or 'pnpm' (default: auto-detect).
        command (str): Raw command string (fallback for stack capabilities).
        timeout (int): Timeout in seconds (default: 300).
    """

    @property
    def name(self) -> str:
        return "node"

    def is_available(self) -> bool:
        return shutil.which("node") is not None

    def _detect_package_manager(self, cwd: str) -> str:
        """Auto-detect the package manager from lock files."""
        cwd_path = Path(cwd)
        if (cwd_path / "pnpm-lock.yaml").exists():
            return "pnpm"
        if (cwd_path / "yarn.lock").exists():
            return "yarn"
        return "npm"

    def version(self) -> str | None:
        """Detect the Node.js version string."""
        try:
            result = subprocess.run(
                ["node", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                # "v20.11.0" → "20.11.0"
                ver = result.stdout.strip().lstrip("v")
                return ver
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return None

    def validate(self, context: ExecutionContext) -> tuple[bool, str]:
        operation = context.action.params.get("operation", "")
        command = context.action.params.get("command", "")

        if not operation and not command:
            return False, "Missing required param: 'operation' or 'command'"

        if operation:
            valid_ops = {"version", "run", "install", "script"}
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
                return self._run_node(context)
            elif operation == "install":
                return self._install(context)
            elif operation == "script":
                return self._run_script(context)
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
                error=f"Node error: {e}",
            )

    # ── Operations ──────────────────────────────────────────────

    def _get_version(self, ctx: ExecutionContext) -> Receipt:
        ver = self.version()
        npm_ver = None
        try:
            r = subprocess.run(
                ["npm", "--version"], capture_output=True, text=True, timeout=5,
            )
            if r.returncode == 0:
                npm_ver = r.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        if ver:
            return Receipt.success(
                adapter=self.name,
                action_id=ctx.action.id,
                output=f"node={ver}, npm={npm_ver or 'N/A'}",
                metadata={"node_version": ver, "npm_version": npm_ver},
            )
        return Receipt.failure(
            adapter=self.name,
            action_id=ctx.action.id,
            error="Could not determine Node.js version",
        )

    def _run_node(self, ctx: ExecutionContext) -> Receipt:
        script = ctx.action.params.get("script", "")
        args = ctx.action.params.get("args", [])
        if not script:
            return Receipt.failure(
                adapter=self.name,
                action_id=ctx.action.id,
                error="Missing 'script' param",
            )
        cmd = ["node", script, *args]
        return self._exec(ctx, cmd)

    def _install(self, ctx: ExecutionContext) -> Receipt:
        pm = ctx.action.params.get("package_manager", "")
        if not pm:
            pm = self._detect_package_manager(ctx.working_dir)
        cmd = [pm, "install"]
        return self._exec(ctx, cmd, timeout=600)

    def _run_script(self, ctx: ExecutionContext) -> Receipt:
        script = ctx.action.params.get("script", "")
        if not script:
            return Receipt.failure(
                adapter=self.name,
                action_id=ctx.action.id,
                error="Missing 'script' param for npm run",
            )
        pm = ctx.action.params.get("package_manager", "")
        if not pm:
            pm = self._detect_package_manager(ctx.working_dir)
        cmd = [pm, "run", script]
        return self._exec(ctx, cmd)

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
