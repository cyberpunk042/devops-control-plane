"""
Content Optimize Video — backward-compatible re-export shim.

The canonical logic now lives in ``src.core.services.content_optimize_video``.
"""

from src.core.services.content_optimize_video import (  # noqa: F401
    optimize_video,
    optimize_audio,
    cancel_active_optimization,
    get_optimization_status,
    extend_optimization,
    _parse_ffmpeg_progress,
    _ffmpeg_available,
    _detect_hw_encoder,
    _probe_media,
    _needs_video_reencode,
    _build_scale_filter,
    _ext_for_video_mime,
    _ext_for_audio_mime,
    _hw_encoder_cache,
    _active_ffmpeg_proc,
    _optimization_state,
)
