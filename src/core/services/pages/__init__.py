"""Pages — segment engine, build, preview, CI, discovery, install."""
from __future__ import annotations
from .engine import (  # noqa: F401
    get_segments, get_segment, add_segment, update_segment, remove_segment,
    get_pages_meta, set_pages_meta, build_segment, get_build_status,
    merge_segments, deploy_to_ghpages, ensure_gitignore,
    start_preview, stop_preview, list_previews,
    generate_ci_workflow,
    list_builders_detail, list_feature_categories, resolve_file_to_segments,
    detect_best_builder, init_pages_from_project,
    install_builder_stream, install_builder_events,
    build_segment_stream,
)
