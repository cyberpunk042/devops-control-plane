"""
Content Optimize — media optimization pipeline for the Content Vault.

Ported from continuity-orchestrator/src/content/media_optimize.py.
Every file uploaded through the Content Vault goes through this pipeline
automatically during upload — optimization is NOT a manual step.

Image pipeline (requires Pillow):
    1. Resize to max 2048px longest side
    2. Strip alpha when not needed (RGBA → RGB)
    3. Convert to WebP (lossy, quality 85)

Video pipeline (requires ffmpeg — see content_optimize_video.py):
    1. Probe input for codec, resolution, bitrate
    2. If already H.264/AAC at ≤1080p → skip or fast remux
    3. Otherwise → full re-encode with H.264 CRF + bitrate cap
    4. Prefer GPU (NVENC) if available — 10-30x faster
    5. Only keep result if actually smaller

Audio pipeline (requires ffmpeg — see content_optimize_video.py):
    1. Re-encode to AAC in M4A container (96 kbps)
    2. Only keep if smaller

Text pipeline:
    1. Gzip compress files > 100 KB
    2. Stored as .gz on disk

Storage tier rules (post-optimization size):
    ≤ 2 MB  → git-tracked (stays in content folder)
    > 2 MB  → large/ subfolder (gitignored)
"""

from __future__ import annotations

import gzip
import io
import logging
from pathlib import Path
from typing import Tuple

logger = logging.getLogger(__name__)

from src.core.services.audit_helpers import make_auditor

_audit = make_auditor("content")

# ── Defaults ─────────────────────────────────────────────────

MAX_DIMENSION = 2048       # px — longest side (images)
WEBP_QUALITY = 85          # lossy WebP quality
JPEG_QUALITY = 85          # fallback JPEG quality
TARGET_FORMAT = "WEBP"     # preferred image output format

VIDEO_MAX_HEIGHT = 1080    # px — max vertical resolution
VIDEO_BITRATE = "1500k"    # video bitrate cap (1.5 Mbps)
AUDIO_BITRATE = "96k"      # audio bitrate cap (96k AAC)
VIDEO_CRF = 28             # H.264 constant rate factor
VIDEO_SKIP_BELOW = 10 * 1024 * 1024  # don't re-encode videos under 10 MB

TEXT_COMPRESS_THRESHOLD = 100 * 1024  # gzip text files above 100 KB
LARGE_THRESHOLD_BYTES = 2 * 1024 * 1024  # > 2 MB → large/ tier
IMAGE_OPTIMIZE_THRESHOLD = 100 * 1024  # optimize images above 100 KB

COMPRESSIBLE_MIMES = {
    "text/plain", "text/csv", "text/html", "text/xml", "text/markdown",
    "text/tab-separated-values", "text/css", "text/javascript",
    "application/json", "application/xml", "application/ld+json",
    "application/x-ndjson", "application/sql",
}
COMPRESSIBLE_EXTENSIONS = {
    ".csv", ".json", ".xml", ".md", ".txt", ".log", ".sql",
    ".tsv", ".ndjson", ".jsonl", ".yml", ".yaml", ".toml",
    ".html", ".css", ".js", ".svg",
}


# ── Re-exports from video sub-module ────────────────────────
# (callers import from content_optimize — these proxy transparently)

from src.core.services.content_optimize_video import (  # noqa: E402, F401
    optimize_video,
    optimize_audio,
    cancel_active_optimization,
    get_optimization_status,
    extend_optimization,
)


# ═════════════════════════════════════════════════════════════════
#  Image optimization
# ═════════════════════════════════════════════════════════════════


def optimize_image(
    data: bytes,
    mime_type: str,
    *,
    max_dimension: int = MAX_DIMENSION,
    quality: int = WEBP_QUALITY,
    target_format: str = TARGET_FORMAT,
) -> Tuple[bytes, str, str]:
    """
    Optimize an image: resize + convert to WebP.

    Matches the orchestrator's behavior exactly.

    Returns:
        Tuple of (optimized_bytes, new_mime_type, new_extension).
        If optimization fails or doesn't apply, returns original unchanged.
    """
    try:
        from PIL import Image
    except ImportError:
        logger.warning("Pillow not installed — skipping image optimization")
        ext = _mime_to_ext(mime_type)
        return data, mime_type, ext

    # Only optimize raster images
    if not mime_type.startswith("image/") or mime_type in (
        "image/svg+xml",
        "image/gif",  # animated GIFs would break
    ):
        ext = _mime_to_ext(mime_type)
        return data, mime_type, ext

    try:
        img = Image.open(io.BytesIO(data))
        original_size = len(data)
        original_dims = img.size

        # ── Resize if over max dimension ─────────────────────
        w, h = img.size
        if max(w, h) > max_dimension:
            ratio = max_dimension / max(w, h)
            new_w = int(w * ratio)
            new_h = int(h * ratio)
            img = img.resize((new_w, new_h), Image.LANCZOS)
            logger.debug(
                f"Resized: {w}x{h} → {new_w}x{new_h} "
                f"(max_dim={max_dimension})"
            )

        # ── Convert color mode ───────────────────────────────
        fmt = target_format.upper()

        if fmt == "JPEG" and img.mode in ("RGBA", "LA", "P"):
            bg = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            bg.paste(img, mask=img.split()[-1] if "A" in img.mode else None)
            img = bg
        elif fmt == "WEBP" and img.mode == "P":
            img = img.convert("RGBA")
        elif fmt in ("JPEG", "WEBP") and img.mode == "RGBA":
            if not _has_meaningful_alpha(img):
                img = img.convert("RGB")

        # ── Encode ───────────────────────────────────────────
        buf = io.BytesIO()
        save_kwargs = {"quality": quality, "optimize": True}
        if fmt == "WEBP":
            save_kwargs["method"] = 4  # compression effort (0-6)
        img.save(buf, format=fmt, **save_kwargs)
        optimized = buf.getvalue()

        new_mime = f"image/{fmt.lower()}"
        new_ext = f".{fmt.lower()}"

        pct = len(optimized) / original_size * 100
        logger.info(
            f"Image optimized: {original_dims[0]}x{original_dims[1]} "
            f"({mime_type}) → {img.size[0]}x{img.size[1]} "
            f"({new_mime}): "
            f"{original_size:,} → {len(optimized):,} bytes "
            f"({pct:.0f}%)"
        )

        return optimized, new_mime, new_ext

    except Exception as e:
        logger.warning(f"Image optimization failed: {e} — using original")
        ext = _mime_to_ext(mime_type)
        return data, mime_type, ext


# ═════════════════════════════════════════════════════════════════
#  Text / document compression
# ═════════════════════════════════════════════════════════════════


def _is_compressible(mime_type: str, original_name: str = "") -> bool:
    """Check if a file is text/document that benefits from gzip."""
    if mime_type in COMPRESSIBLE_MIMES:
        return True
    if mime_type.startswith("text/"):
        return True
    ext = Path(original_name).suffix.lower() if original_name else ""
    return ext in COMPRESSIBLE_EXTENSIONS


def optimize_text(
    data: bytes,
    mime_type: str,
    original_name: str = "",
) -> Tuple[bytes, str, str, bool]:
    """Gzip compress text/document files."""
    original_size = len(data)

    if original_size < TEXT_COMPRESS_THRESHOLD:
        import mimetypes as mt
        ext = mt.guess_extension(mime_type) or Path(original_name).suffix or ".bin"
        return data, mime_type, ext, False

    compressed = gzip.compress(data, compresslevel=9)

    if len(compressed) >= original_size:
        import mimetypes as mt
        ext = mt.guess_extension(mime_type) or Path(original_name).suffix or ".bin"
        logger.info(
            f"Text compression did not help ({original_size:,} → "
            f"{len(compressed):,} bytes), keeping original"
        )
        return data, mime_type, ext, False

    pct = len(compressed) / original_size * 100
    import mimetypes as mt
    base_ext = mt.guess_extension(mime_type) or Path(original_name).suffix or ".bin"
    gz_ext = base_ext + ".gz"

    logger.info(
        f"Text compressed: {original_size:,} → {len(compressed):,} bytes "
        f"({pct:.0f}%) [{mime_type}]"
    )

    return compressed, mime_type, gz_ext, True


# ═════════════════════════════════════════════════════════════════
#  Universal dispatcher
# ═════════════════════════════════════════════════════════════════


def optimize_media(
    data: bytes,
    mime_type: str,
    original_name: str = "",
) -> Tuple[bytes, str, str, bool]:
    """
    Universal optimization dispatcher — picks the best optimizer.

    Nothing escapes without a compression attempt if it's large enough.

    Returns:
        Tuple of (optimized_bytes, new_mime_type, new_extension, was_optimized).
    """
    try:
        # ── Images ──
        if should_optimize_image(len(data), mime_type):
            opt_data, opt_mime, opt_ext = optimize_image(data, mime_type)
            was_optimized = len(opt_data) < len(data)
            return opt_data, opt_mime, opt_ext, was_optimized

        # ── Video ──
        if mime_type.startswith("video/"):
            opt_data, opt_mime, opt_ext = optimize_video(data, mime_type)
            was_optimized = len(opt_data) < len(data)
            return opt_data, opt_mime, opt_ext, was_optimized

        # ── Audio ──
        if mime_type.startswith("audio/"):
            opt_data, opt_mime, opt_ext = optimize_audio(data, mime_type)
            was_optimized = len(opt_data) < len(data)
            return opt_data, opt_mime, opt_ext, was_optimized

        # ── Text / document (gzip) ──
        if _is_compressible(mime_type, original_name):
            return optimize_text(data, mime_type, original_name)

        # ── Fallback: try gzip for anything unknown but large ──
        skip_mimes = {
            "application/zip", "application/gzip", "application/x-tar",
            "application/x-7z-compressed", "application/x-bzip2",
            "application/x-xz", "application/x-rar-compressed",
        }
        if mime_type not in skip_mimes and len(data) > TEXT_COMPRESS_THRESHOLD:
            compressed = gzip.compress(data, compresslevel=6)
            if len(compressed) < len(data) * 0.9:
                import mimetypes as mt
                base_ext = mt.guess_extension(mime_type) or ".bin"
                logger.info(
                    f"Generic gzip: {len(data):,} → {len(compressed):,} bytes "
                    f"({len(compressed)/len(data)*100:.0f}%) [{mime_type}]"
                )
                return compressed, mime_type, base_ext + ".gz", True

        # No optimization available
        import mimetypes as mt
        ext = mt.guess_extension(mime_type) or Path(original_name).suffix or ".bin"
        return data, mime_type, ext, False

    except Exception as e:
        logger.error(
            f"Optimization failed unexpectedly for {original_name} "
            f"({mime_type}, {len(data):,} bytes): {e}",
            exc_info=True,
        )
        import mimetypes as mt
        ext = mt.guess_extension(mime_type) or Path(original_name).suffix or ".bin"
        return data, mime_type, ext, False


# ── Decision helpers ─────────────────────────────────────────


def should_optimize_image(size_bytes: int, mime_type: str) -> bool:
    """Check if an image should be optimized before storing."""
    if not mime_type.startswith("image/"):
        return False
    if mime_type in ("image/svg+xml", "image/gif"):
        return False
    return size_bytes > IMAGE_OPTIMIZE_THRESHOLD


def classify_storage(size_bytes: int) -> str:
    """Determine storage tier based on post-optimization file size.

    Returns:
        "git"   — tracked in git (≤ 2 MB)
        "large" — large/ subfolder, gitignored (> 2 MB)
    """
    if size_bytes > LARGE_THRESHOLD_BYTES:
        return "large"
    return "git"


# ═════════════════════════════════════════════════════════════════
#  Internal helpers
# ═════════════════════════════════════════════════════════════════


def _has_meaningful_alpha(img) -> bool:  # type: ignore[no-untyped-def]
    """Check if an RGBA image actually uses transparency."""
    if img.mode != "RGBA":
        return False
    alpha = img.split()[-1]
    extrema = alpha.getextrema()
    return extrema[0] < 255


def _mime_to_ext(mime_type: str) -> str:
    """Map image MIME type to file extension."""
    return {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "image/svg+xml": ".svg",
        "image/bmp": ".bmp",
        "image/tiff": ".tiff",
    }.get(mime_type, ".bin")
