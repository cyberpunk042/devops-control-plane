"""
L3 Detection — Install failure analysis.

Thin dispatcher that delegates to the remediation domain layer.
Backward compatible: old callers pass (tool, cli, stderr) and
get the legacy response shape. New callers pass method +
system_profile and get the full §6 response.

History: this file previously contained 5 hardcoded patterns
(rust version mismatch, npm missing, pip missing, EACCES, GCC bug).
Those patterns now live in data/remediation_handlers.py and are
evaluated by domain/handler_matching.py.
"""

from __future__ import annotations

from typing import Any

from src.core.services.tool_install.domain.remediation_planning import (
    build_remediation_response,
    to_legacy_remediation,
)


def _analyse_install_failure(
    tool: str,
    cli: str,
    stderr: str,
    *,
    exit_code: int = 1,
    method: str = "",
    system_profile: dict | None = None,
) -> dict[str, Any] | None:
    """Parse stderr from a failed install and return structured remediation.

    **Backward compatible** — old callers pass ``(tool, cli, stderr)`` and
    get the legacy response shape (``{"reason": ..., "options": [...]}``).
    New callers also pass ``method`` and ``system_profile`` to get the
    full §6 response shape.

    Args:
        tool: Tool ID that failed.
        cli: CLI name of the tool (for PATH checks).
        stderr: stderr output from the failed command.
        exit_code: Process exit code (default 1).
        method: Install method used (e.g. ``"pip"``, ``"cargo"``).
            If empty, inferred from stderr heuristics.
        system_profile: Phase 1 ``_detect_os()`` output. If None,
            availability checks will be limited.

    Returns:
        None if no handler matched.
        If ``method`` is provided: full §6 response dict.
        If ``method`` is empty (legacy caller): legacy response dict.
    """
    if not stderr and exit_code not in (137,):
        return None

    # Infer method from stderr if not provided (legacy callers)
    effective_method = method or _infer_method(stderr)

    response = build_remediation_response(
        tool_id=tool,
        step_idx=0,
        step_label=f"install {tool}",
        exit_code=exit_code,
        stderr=stderr,
        method=effective_method,
        system_profile=system_profile,
    )

    if response is None:
        return None

    # Legacy callers (no method provided) get the old shape
    if not method:
        return to_legacy_remediation(response)

    return response


def _infer_method(stderr: str) -> str:
    """Best-effort method inference from stderr content.

    Used when legacy callers don't pass the method.
    """
    lower = stderr.lower()

    if any(kw in lower for kw in (
        "cargo", "rustc", "crate",
        "compiler bug detected", "memcmp", "gcc.gnu.org",
        "cannot find -l", "linker `cc`",
    )):
        return "cargo"
    if "pip" in lower or "externally-managed" in lower:
        return "pip"
    if "npm" in lower or "eacces" in lower:
        return "npm"
    if "apt" in lower or "dpkg" in lower:
        return "apt"
    if "dnf" in lower:
        return "dnf"
    if "snap" in lower or "snapd" in lower:
        return "snap"
    if "brew" in lower or "formulae" in lower:
        return "brew"

    return "_default"
