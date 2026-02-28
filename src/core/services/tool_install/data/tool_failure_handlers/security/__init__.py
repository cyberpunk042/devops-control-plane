"""
Tool-specific failure handlers — Security tools.

Merges handlers from: scanners
"""

from __future__ import annotations

from .scanners import _TRIVY_HANDLERS

SECURITY_TOOL_HANDLERS: dict[str, list[dict]] = {
    "trivy": _TRIVY_HANDLERS,
}
