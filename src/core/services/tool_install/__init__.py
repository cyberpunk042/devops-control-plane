"""
Tool installation service — package re-exports.

This ``__init__.py`` re-exports every public symbol so that
existing callers continue to work::

    from src.core.services.tool_install import install_tool  # still works

Each symbol now lives in its single-responsibility module inside the
appropriate onion layer (data → domain → resolver → detection →
execution → orchestration).
"""

# ── L0: Data ──
from src.core.services.tool_install.data.recipes import TOOL_RECIPES  # noqa: F401

# ── L2: Resolver ──
from src.core.services.tool_install.resolver.choice_resolution import (  # noqa: F401
    resolve_choices,
)
from src.core.services.tool_install.resolver.plan_resolution import (  # noqa: F401
    resolve_install_plan,
    resolve_install_plan_with_choices,
)

# ── L3: Detection ──
from src.core.services.tool_install.detection.hardware import (  # noqa: F401
    detect_build_toolchain,
    detect_gpu,
    detect_kernel,
)
from src.core.services.tool_install.detection.service_status import (  # noqa: F401
    check_data_freshness,
    get_data_pack_usage,
    get_service_status,
)
from src.core.services.tool_install.detection.system_deps import (  # noqa: F401
    check_system_deps,
)
from src.core.services.tool_install.detection.tool_version import (  # noqa: F401
    check_updates,
    get_tool_version,
)

# ── L4: Execution ──
from src.core.services.tool_install.execution.plan_state import (  # noqa: F401
    archive_plan,
    cancel_plan,
    list_pending_plans,
    load_plan_state,
    resume_plan,
    save_plan_state,
)
from src.core.services.tool_install.execution.tool_management import (  # noqa: F401
    update_tool,
)

# ── L5: Orchestration ──
from src.core.services.tool_install.orchestration.orchestrator import (  # noqa: F401
    execute_plan_dag,
    execute_plan_step,
    install_tool,
)
