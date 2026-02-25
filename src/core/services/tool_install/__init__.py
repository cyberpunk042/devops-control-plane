"""
Tool installation service — package re-exports.

This ``__init__.py`` re-exports every public symbol from the original
monolith (``_monolith.py``) so that existing callers continue to work::

    from src.core.services.tool_install import install_tool  # still works

As the SRP decomposition progresses, individual imports will be
redirected to their new single-responsibility modules while this
file continues to re-export them at the same path.
"""

from src.core.services.tool_install._monolith import (  # noqa: F401
    # ── L0: Data ──
    TOOL_RECIPES,
    # ── L2: Resolver ──
    check_system_deps,
    resolve_choices,
    resolve_install_plan,
    resolve_install_plan_with_choices,
    # ── L3: Detection ──
    check_updates,
    detect_build_toolchain,
    detect_gpu,
    detect_kernel,
    get_service_status,
    get_tool_version,
    # ── L4: Execution ──
    execute_plan_step,
    # ── L5: Orchestration ──
    check_data_freshness,
    execute_plan_dag,
    get_data_pack_usage,
    install_tool,
    list_pending_plans,
    resume_plan,
    save_plan_state,
    update_tool,
)
