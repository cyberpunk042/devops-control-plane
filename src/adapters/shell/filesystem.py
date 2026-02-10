"""
Filesystem adapter — file and directory operations.

Provides a safe, receipt-returning interface for filesystem operations
that the engine can audit and dry-run.
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.adapters.base import Adapter, ExecutionContext
from src.core.models.action import Receipt

logger = logging.getLogger(__name__)


class FilesystemAdapter(Adapter):
    """File and directory operations with receipts.

    Action params:
        operation (str): One of 'exists', 'read', 'write', 'mkdir', 'list'.
        path (str): Target path (relative to working_dir or absolute).
        content (str): Content to write (for 'write' operation).
    """

    @property
    def name(self) -> str:
        return "filesystem"

    def is_available(self) -> bool:
        return True  # filesystem is always available

    def validate(self, context: ExecutionContext) -> tuple[bool, str]:
        operation = context.action.params.get("operation", "")
        if not operation:
            return False, "Missing required param: 'operation'"

        valid_ops = {"exists", "read", "write", "mkdir", "list"}
        if operation not in valid_ops:
            return False, f"Unknown operation '{operation}'. Valid: {', '.join(sorted(valid_ops))}"

        path = context.action.params.get("path", "")
        if not path:
            return False, "Missing required param: 'path'"

        if operation == "write" and "content" not in context.action.params:
            return False, "Missing required param: 'content' for write operation"

        return True, ""

    def execute(self, context: ExecutionContext) -> Receipt:
        operation = context.action.params["operation"]
        raw_path = context.action.params["path"]

        # Resolve path relative to working directory
        target = Path(raw_path)
        if not target.is_absolute():
            target = Path(context.working_dir) / target

        try:
            if operation == "exists":
                return self._exists(context, target)
            elif operation == "read":
                return self._read(context, target)
            elif operation == "write":
                return self._write(context, target)
            elif operation == "mkdir":
                return self._mkdir(context, target)
            elif operation == "list":
                return self._list(context, target)
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
                error=f"Filesystem error: {e}",
                metadata={"operation": operation, "path": str(target)},
            )

    def _exists(self, ctx: ExecutionContext, target: Path) -> Receipt:
        exists = target.exists()
        is_dir = target.is_dir() if exists else False
        return Receipt.success(
            adapter=self.name,
            action_id=ctx.action.id,
            output=str(exists),
            metadata={"exists": exists, "is_dir": is_dir, "path": str(target)},
        )

    def _read(self, ctx: ExecutionContext, target: Path) -> Receipt:
        if not target.is_file():
            return Receipt.failure(
                adapter=self.name,
                action_id=ctx.action.id,
                error=f"File not found: {target}",
            )
        content = target.read_text(encoding="utf-8")
        return Receipt.success(
            adapter=self.name,
            action_id=ctx.action.id,
            output=content,
            metadata={"path": str(target), "size": len(content)},
        )

    def _write(self, ctx: ExecutionContext, target: Path) -> Receipt:
        content = ctx.action.params["content"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return Receipt.success(
            adapter=self.name,
            action_id=ctx.action.id,
            output=f"Written {len(content)} bytes to {target}",
            metadata={"path": str(target), "size": len(content)},
        )

    def _mkdir(self, ctx: ExecutionContext, target: Path) -> Receipt:
        target.mkdir(parents=True, exist_ok=True)
        return Receipt.success(
            adapter=self.name,
            action_id=ctx.action.id,
            output=f"Directory created: {target}",
            metadata={"path": str(target)},
        )

    def _list(self, ctx: ExecutionContext, target: Path) -> Receipt:
        if not target.is_dir():
            return Receipt.failure(
                adapter=self.name,
                action_id=ctx.action.id,
                error=f"Not a directory: {target}",
            )
        entries = sorted(str(p.relative_to(target)) for p in target.iterdir())
        return Receipt.success(
            adapter=self.name,
            action_id=ctx.action.id,
            output="\n".join(entries),
            metadata={"path": str(target), "count": len(entries)},
        )
