"""
Pages engine — backward-compatible re-export shim.

The canonical pages engine logic now lives in
``src.core.services.pages_engine``. This module re-exports every
public symbol so existing imports continue to work.
"""

# ── Re-export everything from the canonical location ─────────────────
from src.core.services.pages_engine import (  # noqa: F401
    # Constants
    PAGES_WORKSPACE,
    # Config I/O
    _load_project_yml,
    _save_project_yml,
    _get_pages_config,
    _set_pages_config,
    # Segment CRUD
    get_segments,
    get_segment,
    add_segment,
    update_segment,
    remove_segment,
    # Pages metadata
    get_pages_meta,
    set_pages_meta,
    # Build
    build_segment,
    get_build_status,
    # Merge
    merge_segments,
    _generate_hub_page,
    # Deploy
    deploy_to_ghpages,
    # Gitignore
    ensure_gitignore,
    # Preview
    start_preview,
    stop_preview,
    list_previews,
    _cleanup_dead_previews,
    _preview_servers,
    _MAX_PREVIEWS,
    # CI
    generate_ci_workflow,
)

# Re-export builder types (routes_pages_api.py imports SegmentConfig etc.)
from src.core.services.pages_builders import (  # noqa: F401
    BuildResult,
    SegmentConfig,
    get_builder,
    list_builders,
    run_pipeline,
    BuilderInfo,
    PageBuilder,
    PipelineResult,
    StageResult,
    StageInfo,
    ConfigField,
    LogStream,
)
