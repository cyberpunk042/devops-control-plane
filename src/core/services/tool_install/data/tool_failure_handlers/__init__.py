"""
Tool-specific failure handlers — top-level package.

Re-exports TOOL_FAILURE_HANDLERS as the single public symbol.
Consumers continue to import from:
    src.core.services.tool_install.data.tool_failure_handlers
exactly as before the refactor.
"""

from __future__ import annotations

from .languages import LANGUAGE_TOOL_HANDLERS
from .devops import DEVOPS_TOOL_HANDLERS
from .security import SECURITY_TOOL_HANDLERS

TOOL_FAILURE_HANDLERS: dict[str, list[dict]] = {
    **LANGUAGE_TOOL_HANDLERS,
    **DEVOPS_TOOL_HANDLERS,
    **SECURITY_TOOL_HANDLERS,
}
