"""
Wizard domain — public API.

Re-exports all public functions so consumers can do:

    from src.core.services.wizard import wizard_detect, wizard_setup, ...

Or import directly from submodules for narrower coupling:

    from src.core.services.wizard.detect import wizard_detect
    from src.core.services.wizard.setup_ci import setup_ci
"""

# ── Detection ───────────────────────────────────────────────────────
from src.core.services.wizard.detect import wizard_detect  # noqa: F401

# ── Dispatch + deletion ────────────────────────────────────────────
from src.core.services.wizard.dispatch import (  # noqa: F401
    wizard_setup,
    delete_generated_configs,
)

# ── Setup actions ──────────────────────────────────────────────────
from src.core.services.wizard.setup_git import (  # noqa: F401
    setup_git,
    setup_github,
)
from src.core.services.wizard.setup_infra import (  # noqa: F401
    setup_docker,
    setup_k8s,
    setup_terraform,
    setup_pages,
)
from src.core.services.wizard.setup_ci import setup_ci  # noqa: F401
from src.core.services.wizard.setup_dns import setup_dns  # noqa: F401

# ── Validation ─────────────────────────────────────────────────────
from src.core.services.wizard.validate import (  # noqa: F401
    validate_wizard_state,
    check_required_tools,
)
