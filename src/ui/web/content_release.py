"""
Content Release — backward-compatible re-export shim.

The canonical logic now lives in ``src.core.services.content_release``.
"""

from src.core.services.content_release import (  # noqa: F401
    # Constants
    CONTENT_RELEASE_TAG,
    # State dicts (mutable — shared identity via re-export)
    _release_upload_status,
    _release_active_procs,
    # Public API
    cleanup_release_sidecar,
    upload_to_release_bg,
    get_release_status,
    get_all_release_statuses,
    cancel_release_upload,
    restore_large_files,
    list_release_assets,
    release_inventory,
    delete_release_asset,
    # Internal helpers
    _update_sidecar,
)
