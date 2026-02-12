"""
Content Optimize — backward-compatible re-export shim.

The canonical logic now lives in ``src.core.services.content_optimize``.
"""

from src.core.services.content_optimize import (  # noqa: F401
    # Constants
    MAX_DIMENSION,
    WEBP_QUALITY,
    JPEG_QUALITY,
    TARGET_FORMAT,
    VIDEO_MAX_HEIGHT,
    VIDEO_BITRATE,
    AUDIO_BITRATE,
    VIDEO_CRF,
    VIDEO_SKIP_BELOW,
    TEXT_COMPRESS_THRESHOLD,
    LARGE_THRESHOLD_BYTES,
    IMAGE_OPTIMIZE_THRESHOLD,
    COMPRESSIBLE_MIMES,
    COMPRESSIBLE_EXTENSIONS,
    # Image
    optimize_image,
    should_optimize_image,
    # Text
    optimize_text,
    # Dispatcher
    optimize_media,
    classify_storage,
    # Internal helpers
    _has_meaningful_alpha,
    _mime_to_ext,
    _is_compressible,
    # Video re-exports (originally from content_optimize_video)
    optimize_video,
    optimize_audio,
    cancel_active_optimization,
    get_optimization_status,
    extend_optimization,
)
