"""
Operation pipeline — the core generator for dependency operations.

Every dependency operation (install, update, rollback) goes through
this pipeline.  It yields ``OpEvent``s — transport-agnostic.
The SSE route wraps these in JSON framing, tests collect them,
CLI prints them.

Lifecycle::

    Snapshot → Build command → Execute + Parse → Done sentinel

The pipeline is the ONLY place where dependency commands are executed.

Usage::

    for event in run_operation(root, "pip:.", "install", registry=reg):
        ...  # SSE, print, collect — caller decides

    for event in run_batch_operation(root, ["pip:.", "npm:frontend"], "install", registry=reg):
        ...
"""

from __future__ import annotations

import logging
import sys
import time
import uuid
from pathlib import Path
from typing import Iterator, Literal

from .ecosystem import EcosystemRegistry
from .models import OpEvent
from .state import create_snapshot, restore_snapshot
from .subprocess_stream import stream_subprocess

logger = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════════
#  Scope parsing
# ═════════════════════════════════════════════════════════════════


def _parse_scope(scope: str) -> tuple[str, str]:
    """Parse a TreeNode.id into ``(ecosystem_id, relative_path)``.

    Examples::

        "pip:."          → ("pip", ".")
        "npm:frontend"   → ("npm", "frontend")
        "go:services/api" → ("go", "services/api")
    """
    parts = scope.split(":", 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return scope, "."


# ═════════════════════════════════════════════════════════════════
#  Timeline event emission
# ═════════════════════════════════════════════════════════════════


def _emit_timeline_event(
    action: str,
    scope: str,
    status: str,
    duration_ms: int,
    resolved_count: int,
    warning_count: int,
    error_count: int,
    correlation_id: str,
) -> None:
    """Emit a timeline event at operation boundaries.  Fail-safe."""
    try:
        from src.core.services.events.emit import emit_event

        if status == "ok":
            event_type = f"dependency.{action}.completed"
            summary = f"Dependencies {action}ed: {scope} — {resolved_count} packages"
        else:
            event_type = f"dependency.{action}.failed"
            summary = f"Dependency {action} failed: {scope}"

        emit_event(
            event_type,
            summary=summary,
            correlation_id=correlation_id,
            status=status,
            duration_ms=duration_ms,
            detail={
                "scope": scope,
                "action": action,
                "resolved": resolved_count,
                "warnings": warning_count,
                "errors": error_count,
            },
        )
    except Exception:
        logger.debug("Failed to emit timeline event", exc_info=True)


# ═════════════════════════════════════════════════════════════════
#  Single-ecosystem pipeline
# ═════════════════════════════════════════════════════════════════


def run_operation(
    project_root: Path,
    scope: str,
    action: Literal["install", "update", "rollback", "clean"],
    *,
    registry: EcosystemRegistry,
    packages: list[str] | None = None,
    dev: bool = False,
    frozen: bool = True,
    snapshot_id: str | None = None,
    correlation_id: str | None = None,
    target_python: str | None = None,
    break_system: bool = False,
    force_reinstall: bool = False,
) -> Iterator[OpEvent]:
    """Execute a dependency operation and stream events.

    This is the ONLY place where dependency commands are executed.
    All routes, CLI, and automation call this function.

    Args:
        project_root: Absolute project root.
        scope: TreeNode.id — ``"pip:."``, ``"npm:frontend"``, etc.
        action: Operation type.
        registry: Ecosystem adapter registry.
        packages: For update — specific packages (``None`` = all).
        dev: Include dev dependencies.
        frozen: Use lock file for install.
        snapshot_id: For rollback — which snapshot to restore.
        correlation_id: Chain ID for timeline grouping.
        target_python: Python binary to use (for pip venv targeting).
            ``None`` = use adapter default (``sys.executable``).
        break_system: If True, add ``--break-system-packages`` (PEP 668).

    Yields:
        ``OpEvent`` — typed, transport-agnostic events.
    """
    # ── 1. Resolve adapter ────────────────────────────────────
    ecosystem_id, rel_path = _parse_scope(scope)
    adapter = registry.get(ecosystem_id)

    if adapter is None:
        yield OpEvent(type="error", scope=scope,
                       message=f"Unknown ecosystem: {ecosystem_id}",
                       severity="error")
        return

    # Check availability against the TARGET Python, not the server's own
    if target_python:
        # Target-specific check: can the target python run pip?
        import subprocess as _sp
        try:
            _r = _sp.run([target_python, "-m", "pip", "--version"],
                         capture_output=True, timeout=5)
            target_available = _r.returncode == 0
        except Exception:
            target_available = False
        # Fallback: check uv for the target
        if not target_available:
            try:
                import shutil as _sh
                target_available = _sh.which("uv") is not None
            except Exception:
                pass
        if not target_available:
            yield OpEvent(type="error", scope=scope,
                           message=f"pip not available in target {target_python}",
                           severity="error")
            return
    elif not adapter.is_available():
        # Last chance: check if uv is available as fallback
        import shutil as _sh
        if ecosystem_id == "pip" and _sh.which("uv"):
            pass  # uv will handle pip commands via rewriting below
        else:
            yield OpEvent(type="error", scope=scope,
                           message=f"{adapter.cli} not installed or not in PATH",
                           severity="error")
            return

    directory = project_root / rel_path
    if not directory.is_dir():
        yield OpEvent(type="error", scope=scope,
                       message=f"Directory not found: {rel_path}",
                       severity="error")
        return

    t0 = time.monotonic()
    chain_id = correlation_id or f"dependency:{uuid.uuid4().hex[:8]}"

    # Emit start timeline event
    try:
        from src.core.services.events.emit import emit_event
        emit_event(
            f"dependency.{action}.started",
            summary=f"Dependency {action}: {scope}",
            correlation_id=chain_id,
        )
    except Exception:
        pass

    # ── 2. Snapshot (before install/update, not rollback) ─────
    if action != "rollback":
        files_to_snap = adapter.snapshot_files(directory)
        if files_to_snap:
            try:
                snap = create_snapshot(project_root, scope, [ecosystem_id], files_to_snap)
                yield OpEvent(type="snapshot_created", scope=scope,
                               message=f"Backed up {len(snap.files)} files")
            except Exception as exc:
                logger.warning("Snapshot failed: %s", exc)
                # Non-fatal — continue without snapshot

    # ── 3. Build command ──────────────────────────────────────
    if action == "install":
        cmd = adapter.install_cmd(directory, dev=dev, frozen=frozen)
    elif action == "update":
        if packages and len(packages) == 1:
            cmd = adapter.update_single_cmd(directory, packages[0])
        else:
            cmd = adapter.update_cmd(directory, packages)
        if force_reinstall and cmd:
            cmd.append("--force-reinstall")
    elif action == "clean":
        # Uninstall packages
        if packages:
            cmd = [sys.executable, "-m", "pip", "uninstall", "-y"] + packages
        else:
            # Ecosystem clean — uninstall all packages from manifest
            # Get package names from the tree
            eco_pkgs = []
            try:
                from src.core.services.mediator import get_mediator
                m = get_mediator()
                tree_result = m.get("dependency.tree")
                if tree_result and tree_result.get("data"):
                    for eco_node in tree_result["data"].get("children", []):
                        if eco_node.get("id") == scope:
                            for pkg_node in eco_node.get("children", []):
                                name = pkg_node.get("label", "").split(" ")[0]
                                if name:
                                    eco_pkgs.append(name)
            except Exception:
                pass
            if eco_pkgs:
                cmd = [sys.executable, "-m", "pip", "uninstall", "-y"] + eco_pkgs
            else:
                yield OpEvent(type="error", scope=scope,
                               message="No packages found to clean",
                               severity="error")
                return
    elif action == "rollback":
        if not snapshot_id:
            yield OpEvent(type="error", scope=scope,
                           message="snapshot_id required for rollback",
                           severity="error")
            return
        restored = restore_snapshot(project_root, snapshot_id)
        if restored is None:
            yield OpEvent(type="error", scope=scope,
                           message=f"Snapshot not found: {snapshot_id}",
                           severity="error")
            return
        yield OpEvent(type="rollback_start", scope=scope,
                       message=f"Restored {len(restored.files)} files from {snapshot_id}")
        cmd = adapter.restore_cmd(directory)
    else:
        yield OpEvent(type="error", scope=scope,
                       message=f"Unknown action: {action}",
                       severity="error")
        return

    # ── 3b. Target rewriting (venv selection for pip) ───────
    if cmd and target_python:
        # Replace the python binary in the command
        if cmd[0] == sys.executable:
            cmd[0] = target_python

        # If the target has no pip but has uv, rewrite pip commands to uv pip
        if "-m" in cmd and "pip" in cmd:
            import subprocess as _sp
            try:
                _check = _sp.run([target_python, "-m", "pip", "--version"],
                                 capture_output=True, timeout=5)
                has_pip = _check.returncode == 0
            except Exception:
                has_pip = False

            if not has_pip:
                import shutil as _sh
                if _sh.which("uv"):
                    # Rewrite: [python, -m, pip, install, ...] → [uv, pip, install, ...]
                    # Extract the pip subcommand (install, list, etc.) and args
                    pip_idx = cmd.index("pip") if "pip" in cmd else -1
                    if pip_idx >= 0:
                        pip_args = cmd[pip_idx + 1:]  # everything after "pip"
                        cmd = ["uv", "pip"] + pip_args
                        # Set VIRTUAL_ENV so uv targets the right env
                        import os
                        venv_dir = os.path.dirname(os.path.dirname(target_python))
                        os.environ["VIRTUAL_ENV"] = venv_dir

    # Also rewrite for the server's own venv if pip is missing
    if cmd and not target_python and "-m" in cmd and "pip" in cmd:
        import subprocess as _sp2
        try:
            _check2 = _sp2.run([cmd[0], "-m", "pip", "--version"],
                               capture_output=True, timeout=5)
            if _check2.returncode != 0:
                import shutil as _sh2
                if _sh2.which("uv"):
                    pip_idx2 = cmd.index("pip") if "pip" in cmd else -1
                    if pip_idx2 >= 0:
                        pip_args2 = cmd[pip_idx2 + 1:]
                        cmd = ["uv", "pip"] + pip_args2
        except Exception:
            pass

    if break_system and cmd and "-m" in cmd and "pip" in cmd:
        if "--break-system-packages" not in cmd:
            cmd.append("--break-system-packages")

    yield OpEvent(type="operation_start", scope=scope,
                   command=" ".join(cmd))

    # ── 4. Execute + parse ────────────────────────────────────
    parser = adapter.create_output_parser(scope)

    for chunk in stream_subprocess(cmd, cwd=directory, timeout=300):
        if chunk.type == "line":
            # Always yield raw log
            yield OpEvent(type="log", scope=scope, line=chunk.line)
            # Parse for structured events
            for parsed_event in parser.feed_line(chunk.line, chunk.stream):
                yield parsed_event

        elif chunk.type == "done":
            # Finalize parser
            for final_event in parser.finalize(chunk.exit_code):
                yield final_event

            # ── 5. Done sentinel ──────────────────────────────
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            status = "ok" if chunk.ok else "error"
            done_type = "rollback_done" if action == "rollback" else "operation_done"
            msg = (
                f"{parser.resolved_count} packages"
                if chunk.ok
                else (chunk.error or f"Exit code {chunk.exit_code}")
            )

            yield OpEvent(
                type=done_type,
                scope=scope,
                status=status,
                count=parser.resolved_count,
                duration_ms=elapsed_ms,
                message=msg,
                detail={
                    "warnings": len(parser.warnings),
                    "errors": len(parser.errors),
                    "exit_code": chunk.exit_code,
                },
            )

            # Emit timeline event
            _emit_timeline_event(
                action, scope, status, elapsed_ms,
                parser.resolved_count,
                len(parser.warnings),
                len(parser.errors),
                chain_id,
            )


# ═════════════════════════════════════════════════════════════════
#  Batch pipeline (Global scope)
# ═════════════════════════════════════════════════════════════════


def run_batch_operation(
    project_root: Path,
    scopes: list[str],
    action: Literal["install", "update", "clean"],
    *,
    registry: EcosystemRegistry,
    correlation_id: str | None = None,
    **kwargs: object,
) -> Iterator[OpEvent]:
    """Run an operation across multiple ecosystems sequentially.

    Wraps individual ``run_operation()`` calls in batch_start/batch_done.

    Args:
        project_root: Absolute project root.
        scopes: List of TreeNode.ids — ``["pip:.", "npm:frontend"]``.
        action: ``"install"`` or ``"update"``.
        registry: Ecosystem adapter registry.
        correlation_id: Shared chain ID for the entire batch.
        **kwargs: Passed through to ``run_operation()`` (dev, frozen, etc.).

    Yields:
        ``OpEvent`` — includes batch envelope events.
    """
    chain_id = correlation_id or f"dependency-batch:{uuid.uuid4().hex[:8]}"

    yield OpEvent(
        type="batch_start",
        message=f"Batch {action}: {len(scopes)} ecosystems",
        detail={"ecosystems": scopes, "action": action},
    )

    t0 = time.monotonic()
    total_resolved = 0
    total_warnings = 0
    total_errors = 0
    failed: list[str] = []

    for scope in scopes:
        for event in run_operation(
            project_root, scope, action,
            registry=registry,
            correlation_id=chain_id,
            **kwargs,  # type: ignore[arg-type]
        ):
            yield event
            if event.type == "operation_done":
                total_resolved += event.count
                total_warnings += event.detail.get("warnings", 0)
                total_errors += event.detail.get("errors", 0)
                if event.status == "error":
                    failed.append(scope)

    elapsed_ms = int((time.monotonic() - t0) * 1000)

    yield OpEvent(
        type="batch_done",
        status="error" if failed else "ok",
        count=total_resolved,
        duration_ms=elapsed_ms,
        message=(
            f"All done — {total_resolved} packages"
            if not failed
            else f"Batch failed — {len(failed)} ecosystem(s)"
        ),
        detail={
            "warnings": total_warnings,
            "errors": total_errors,
            "failed": failed,
        },
    )
