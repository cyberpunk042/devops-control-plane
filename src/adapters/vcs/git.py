"""
Git adapter — version control operations.

Provides git operations (status, commit, push, pull, log, branch) through
the adapter protocol. Uses the git CLI — never raw API calls.
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


class GitAdapter(Adapter):
    """Git version control operations.

    Action params:
        operation (str): One of 'status', 'commit', 'push', 'pull', 'log',
                         'branch', 'diff', 'init'.
        message (str): Commit message (for 'commit').
        files (list[str]): Files to stage (for 'commit', default: all).
        branch (str): Target branch (for 'branch').
        count (int): Number of log entries (for 'log', default: 10).
        timeout (int): Timeout in seconds (default: 30).
    """

    @property
    def name(self) -> str:
        return "git"

    def is_available(self) -> bool:
        return shutil.which("git") is not None

    def validate(self, context: ExecutionContext) -> tuple[bool, str]:
        operation = context.action.params.get("operation", "")
        if not operation:
            # Fall back to command-style execution (stack capabilities use 'command')
            command = context.action.params.get("command", "")
            if command:
                return True, ""
            return False, "Missing required param: 'operation' or 'command'"

        valid_ops = {"status", "commit", "push", "pull", "log", "branch", "diff", "init"}
        if operation not in valid_ops:
            return False, f"Unknown operation '{operation}'. Valid: {', '.join(sorted(valid_ops))}"

        if operation == "commit":
            message = context.action.params.get("message", "")
            if not message:
                return False, "Missing required param: 'message' for commit operation"

        return True, ""

    def execute(self, context: ExecutionContext) -> Receipt:
        # If it's a raw command from stack capabilities, delegate to shell style
        command = context.action.params.get("command", "")
        if command and not context.action.params.get("operation"):
            return self._run_command(context, command)

        operation = context.action.params["operation"]
        try:
            if operation == "status":
                return self._status(context)
            elif operation == "commit":
                return self._commit(context)
            elif operation == "push":
                return self._push(context)
            elif operation == "pull":
                return self._pull(context)
            elif operation == "log":
                return self._log(context)
            elif operation == "branch":
                return self._branch(context)
            elif operation == "diff":
                return self._diff(context)
            elif operation == "init":
                return self._init(context)
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
                error=f"Git error: {e}",
            )

    # ── Operations ──────────────────────────────────────────────

    def _status(self, ctx: ExecutionContext) -> Receipt:
        """Branch, dirty state, ahead/behind."""
        cwd = ctx.working_dir
        branch = self._git(["rev-parse", "--abbrev-ref", "HEAD"], cwd)
        porcelain = self._git(["status", "--porcelain"], cwd)
        dirty = bool(porcelain.strip())

        return Receipt.success(
            adapter=self.name,
            action_id=ctx.action.id,
            output=f"branch={branch.strip()}, dirty={dirty}",
            metadata={
                "branch": branch.strip(),
                "dirty": dirty,
                "changes": len(porcelain.strip().splitlines()) if dirty else 0,
            },
        )

    def _commit(self, ctx: ExecutionContext) -> Receipt:
        message = ctx.action.params["message"]
        files = ctx.action.params.get("files", [])
        cwd = ctx.working_dir

        # Stage
        if files:
            for f in files:
                self._git(["add", f], cwd)
        else:
            self._git(["add", "-A"], cwd)

        # Commit
        output = self._git(["commit", "-m", message], cwd)
        return Receipt.success(
            adapter=self.name,
            action_id=ctx.action.id,
            output=output,
            metadata={"message": message},
        )

    def _push(self, ctx: ExecutionContext) -> Receipt:
        output = self._git(["push"], ctx.working_dir)
        return Receipt.success(
            adapter=self.name,
            action_id=ctx.action.id,
            output=output,
        )

    def _pull(self, ctx: ExecutionContext) -> Receipt:
        output = self._git(["pull"], ctx.working_dir)
        return Receipt.success(
            adapter=self.name,
            action_id=ctx.action.id,
            output=output,
        )

    def _log(self, ctx: ExecutionContext) -> Receipt:
        count = ctx.action.params.get("count", 10)
        output = self._git(
            ["log", f"--max-count={count}", "--oneline", "--no-decorate"],
            ctx.working_dir,
        )
        return Receipt.success(
            adapter=self.name,
            action_id=ctx.action.id,
            output=output,
            metadata={"count": count},
        )

    def _branch(self, ctx: ExecutionContext) -> Receipt:
        output = self._git(["branch", "--list", "--no-color"], ctx.working_dir)
        branches = [b.strip().lstrip("* ") for b in output.splitlines() if b.strip()]
        return Receipt.success(
            adapter=self.name,
            action_id=ctx.action.id,
            output=output,
            metadata={"branches": branches},
        )

    def _diff(self, ctx: ExecutionContext) -> Receipt:
        output = self._git(["diff", "--stat"], ctx.working_dir)
        return Receipt.success(
            adapter=self.name,
            action_id=ctx.action.id,
            output=output,
        )

    def _init(self, ctx: ExecutionContext) -> Receipt:
        output = self._git(["init"], ctx.working_dir)
        return Receipt.success(
            adapter=self.name,
            action_id=ctx.action.id,
            output=output,
        )

    # ── Helpers ─────────────────────────────────────────────────

    def _git(self, args: list[str], cwd: str, timeout: int = 30) -> str:
        """Run a git command and return stdout."""
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or f"git {args[0]} failed")
        return result.stdout

    def _run_command(self, ctx: ExecutionContext, command: str) -> Receipt:
        """Execute a raw git command string (for stack capability compatibility)."""
        timeout = ctx.action.params.get("timeout", 30)
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
