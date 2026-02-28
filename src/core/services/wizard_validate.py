"""
Backward-compatibility shim — wizard validation.

All implementation has moved to ``src.core.services.wizard.validate``.
Import from the new location for new code.
"""

from src.core.services.wizard.validate import (  # noqa: F401, E402
    validate_wizard_state,
    check_required_tools,
)
