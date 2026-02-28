"""
Backward-compatibility shim — wizard operations (detection + helpers).

All implementation has moved to ``src.core.services.wizard.*``.
Import from the new locations for new code.
"""

from src.core.services.wizard.detect import wizard_detect  # noqa: F401, E402

# ── Setup re-exports (previously re-exported here) ─────────────────
from src.core.services.wizard.dispatch import (  # noqa: F401, E402
    wizard_setup,
    delete_generated_configs,
)
from src.core.services.wizard.setup_git import (  # noqa: F401, E402
    setup_git,
    setup_github,
)
from src.core.services.wizard.setup_infra import (  # noqa: F401, E402
    setup_docker,
    setup_k8s,
    setup_terraform,
    setup_pages,
)
from src.core.services.wizard.setup_ci import setup_ci  # noqa: F401, E402
from src.core.services.wizard.setup_dns import setup_dns  # noqa: F401, E402
