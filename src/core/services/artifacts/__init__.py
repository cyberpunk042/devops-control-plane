"""
Artifacts engine — target lifecycle management.

Manages artifact targets (CRUD) and orchestrates builds
for distributable program artifacts (CLI, packages, bundles).

This mirrors the pages engine pattern but for tool outputs
rather than static site content.
"""

from .engine import (  # noqa: F401
    get_targets,
    get_target,
    add_target,
    update_target,
    remove_target,
    get_build_status,
    build_target_stream,
)
