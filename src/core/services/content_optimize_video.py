"""
Content Optimize — Video & Audio optimization (ffmpeg pipeline).

Split from content_optimize.py. Handles video and audio re-encoding using
ffmpeg, including GPU (NVENC) acceleration detection, progress tracking,
and cancellation support.

Exports:
    optimize_video()       — probe + re-encode video → H.264 MP4
    optimize_audio()       — re-encode audio → AAC M4A
    cancel_active_optimization() — kill active ffmpeg process
    get_optimization_status()    — frontend polling for progress
    extend_optimization()        — extend encoding deadline
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import tempfile
import time as _time
from pathlib import Path
from typing import Optional, Tuple

from src.core.services.content_optimize import (
    VIDEO_MAX_HEIGHT,
    VIDEO_BITRATE,
    AUDIO_BITRATE,
    VIDEO_CRF,
    VIDEO_SKIP_BELOW,
)

logger = logging.getLogger(__name__)

from src.core.services.audit_helpers import make_auditor

_audit = make_auditor("content")


# ═════════════════════════════════════════════════════════════════
#  State / globals
# ═════════════════════════════════════════════════════════════════

# Cache for hardware encoder detection
_hw_encoder_cache: dict = {}

# Active ffmpeg process reference for cancellation
_active_ffmpeg_proc: Optional[subprocess.Popen] = None

# Optimization state for frontend polling
# { "status": "encoding"|"done"|"idle", "elapsed": float, "deadline": float,
#   "deadline_warning": bool, "encoder": str, "fps": str, "speed": str,
#   "time": str, "duration_sec": float }
_optimization_state: dict = {"status": "idle"}


# ═════════════════════════════════════════════════════════════════
#  Public API — status / cancellation
# ═════════════════════════════════════════════════════════════════


def cancel_active_optimization() -> bool:
    """Kill the active ffmpeg process if one is running."""
    global _active_ffmpeg_proc, _optimization_state
    if _active_ffmpeg_proc is not None and _active_ffmpeg_proc.poll() is None:
        _active_ffmpeg_proc.kill()
        try:
            _active_ffmpeg_proc.wait(timeout=5)
        except Exception:
            pass
        logger.info("Killed active ffmpeg process (user cancelled)")
        _active_ffmpeg_proc = None
        _optimization_state = {"status": "idle"}
        return True
    _active_ffmpeg_proc = None
    _optimization_state = {"status": "idle"}
    return False


def get_optimization_status() -> dict:
    """Return current optimization state for frontend polling."""
    return dict(_optimization_state)


def extend_optimization(extra_seconds: int = 300) -> dict:
    """Extend the current optimization deadline."""
    if _optimization_state.get("status") != "encoding":
        return {"success": False, "message": "No active encoding"}

    old_deadline = _optimization_state.get("deadline", 0)
    _optimization_state["deadline"] = old_deadline + extra_seconds
    _optimization_state["deadline_warning"] = False
    logger.info(
        f"Optimization deadline extended by {extra_seconds}s "
        f"→ {_optimization_state['deadline']:.0f}s total"
    )
    return {
        "success": True,
        "message": f"Extended by {extra_seconds // 60} min",
        "new_deadline": _optimization_state["deadline"],
    }


# ═════════════════════════════════════════════════════════════════
#  ffmpeg helpers
# ═════════════════════════════════════════════════════════════════


def _parse_ffmpeg_progress(line: str) -> dict:
    """Extract progress info from an ffmpeg stderr line.

    Example: frame= 1234 fps=125 q=28.0 size= 5120kB time=00:01:23.45 ...
    """
    info: dict = {}
    m = re.search(r'fps=\s*(\S+)', line)
    if m:
        info['fps'] = m.group(1)
    m = re.search(r'speed=\s*(\S+)', line)
    if m:
        info['speed'] = m.group(1)
    m = re.search(r'time=\s*(\S+)', line)
    if m:
        info['time'] = m.group(1)
    m = re.search(r'frame=\s*(\d+)', line)
    if m:
        info['frame'] = int(m.group(1))
    m = re.search(r'size=\s*(\S+)', line)
    if m:
        info['size'] = m.group(1)
    return info


def _ffmpeg_available() -> bool:
    """Check if ffmpeg is on PATH."""
    return shutil.which("ffmpeg") is not None


def _detect_hw_encoder() -> Optional[str]:
    """Detect if NVIDIA NVENC is available for H.264 encoding.

    Tests by running a tiny encode — some systems have the encoder listed
    but it fails at runtime if no GPU is present or drivers are wrong.
    Result is cached for the process lifetime.
    """
    if "h264" in _hw_encoder_cache:
        return _hw_encoder_cache["h264"]

    _hw_encoder_cache["h264"] = None  # default: no hw encoder

    if not _ffmpeg_available():
        return None

    try:
        # Check if h264_nvenc is listed
        check = subprocess.run(
            ["ffmpeg", "-encoders"],
            capture_output=True, text=True, timeout=5,
        )
        if "h264_nvenc" not in check.stdout:
            logger.debug("NVENC not listed in ffmpeg encoders")
            return None

        # Verify it actually works with a tiny test encode
        test = subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=256x256:d=0.1:r=30",
             "-c:v", "h264_nvenc", "-f", "null", "-"],
            capture_output=True, text=True, timeout=10,
        )
        if test.returncode == 0:
            _hw_encoder_cache["h264"] = "h264_nvenc"
            logger.info("🚀 NVIDIA NVENC detected — will use GPU-accelerated encoding")
            return "h264_nvenc"
        else:
            logger.debug(f"NVENC test encode failed: {test.stderr[:200]}")
            return None

    except Exception as e:
        logger.debug(f"NVENC detection failed: {e}")
        return None


def _probe_media(file_path: Path) -> Optional[dict]:
    """Probe a media file for codec, resolution, bitrate info."""
    try:
        proc = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration,size,bit_rate",
                "-show_entries", "stream=codec_name,codec_type,width,height,bit_rate",
                "-of", "json",
                str(file_path),
            ],
            capture_output=True, text=True, timeout=15,
        )
        if proc.returncode != 0:
            return None
        return json.loads(proc.stdout)
    except Exception as e:
        logger.debug(f"ffprobe failed: {e}")
        return None


def _needs_video_reencode(
    probe: dict,
    file_size: int,
    max_height: int = VIDEO_MAX_HEIGHT,
) -> tuple:
    """Decide whether a video needs re-encoding.

    Philosophy: CRF-based re-encoding almost always reduces file size
    compared to source material. We ALWAYS try for files above VIDEO_SKIP_BELOW.
    The caller keeps the original if the result isn't smaller.
    """
    if file_size < VIDEO_SKIP_BELOW:
        return False, f"file under {VIDEO_SKIP_BELOW // (1024*1024)} MB"

    streams = probe.get("streams", [])
    video_stream = None
    for s in streams:
        if s.get("codec_type") == "video" or (video_stream is None and "width" in s):
            video_stream = s

    if not video_stream:
        return False, "no video stream found"

    height = video_stream.get("height", 0)
    if height > max_height:
        return True, f"resolution {height}p → downscale to {max_height}p"

    # Always try re-encoding for large files
    fmt = probe.get("format", {})
    total_bitrate = int(fmt.get("bit_rate", 0))
    file_mb = file_size / (1024 * 1024)
    return True, (
        f"{file_mb:.0f} MB, {total_bitrate//1000}kbps → "
        f"re-encoding with CRF {VIDEO_CRF} + maxrate {VIDEO_BITRATE}"
    )


def _build_scale_filter(input_path: Path, max_height: int) -> Optional[str]:
    """Probe video dimensions and return an ffmpeg scale filter if needed."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=height",
                "-of", "csv=p=0",
                str(input_path),
            ],
            capture_output=True, text=True, timeout=10,
        )
        height = int(result.stdout.strip())
        if height > max_height:
            return f"scale=-2:{max_height}"
    except (ValueError, subprocess.TimeoutExpired, Exception) as e:
        logger.debug(f"Could not probe video dimensions: {e}")

    return None


def _ext_for_video_mime(mime_type: str) -> str:
    """Map video MIME type to file extension."""
    return {
        "video/mp4": ".mp4",
        "video/webm": ".webm",
        "video/quicktime": ".mov",
        "video/x-msvideo": ".avi",
        "video/x-matroska": ".mkv",
        "video/ogg": ".ogv",
        "video/3gpp": ".3gp",
    }.get(mime_type, ".mp4")


def _ext_for_audio_mime(mime_type: str) -> str:
    """Map audio MIME type to file extension."""
    return {
        "audio/mpeg": ".mp3",
        "audio/mp4": ".m4a",
        "audio/aac": ".aac",
        "audio/ogg": ".ogg",
        "audio/wav": ".wav",
        "audio/x-wav": ".wav",
        "audio/webm": ".weba",
        "audio/flac": ".flac",
        "audio/x-flac": ".flac",
    }.get(mime_type, ".m4a")


# ═════════════════════════════════════════════════════════════════
#  Video optimization
# ═════════════════════════════════════════════════════════════════


def optimize_video(
    data: bytes,
    mime_type: str,
    *,
    max_height: int = VIDEO_MAX_HEIGHT,
    video_bitrate: str = VIDEO_BITRATE,
    audio_bitrate: str = AUDIO_BITRATE,
    crf: int = VIDEO_CRF,
) -> Tuple[bytes, str, str]:
    """
    Optimize a video: probe first, then re-encode only if needed.

    Smart pipeline:
    1. Probe input for codec, resolution, bitrate
    2. If already optimal and MP4 → skip (return as-is)
    3. If codec is fine but container is wrong → fast stream copy
    4. Otherwise → full re-encode (GPU NVENC if available, else CPU libx264)

    Returns:
        Tuple of (optimized_bytes, new_mime_type, new_extension).
    """
    if not _ffmpeg_available():
        logger.info("ffmpeg not available — storing video as-is")
        ext = _ext_for_video_mime(mime_type)
        return data, mime_type, ext

    original_size = len(data)
    timeout_secs = 600
    tmpdir = tempfile.mkdtemp(prefix="media_opt_")

    try:
        in_ext = _ext_for_video_mime(mime_type)
        in_path = Path(tmpdir) / f"input{in_ext}"
        out_path = Path(tmpdir) / "output.mp4"

        in_path.write_bytes(data)

        # ── Probe first ──
        probe = _probe_media(in_path)
        if probe:
            needs_reencode, reason = _needs_video_reencode(probe, original_size, max_height)
            if not needs_reencode:
                if mime_type == "video/mp4":
                    logger.info(
                        f"Video already optimal ({reason}), keeping as-is "
                        f"({original_size:,} bytes)"
                    )
                    return data, mime_type, in_ext
                else:
                    # Fast remux to MP4 container (stream copy, no re-encode)
                    logger.info(
                        f"Video codecs optimal ({reason}), remuxing to MP4 container"
                    )
                    cmd = [
                        "ffmpeg", "-y",
                        "-i", str(in_path),
                        "-c", "copy",
                        "-movflags", "+faststart",
                        str(out_path),
                    ]
                    proc = subprocess.run(
                        cmd, capture_output=True, text=True, timeout=120,
                    )
                    if proc.returncode == 0 and out_path.exists():
                        remuxed = out_path.read_bytes()
                        logger.info(
                            f"Remuxed: {original_size:,} → {len(remuxed):,} bytes"
                        )
                        return remuxed, "video/mp4", ".mp4"
                    return data, mime_type, in_ext
            else:
                logger.info(f"Video needs re-encoding: {reason}")
        else:
            logger.info("Could not probe video — attempting full re-encode")

        # ── Full re-encode needed ──
        scale_filter = _build_scale_filter(in_path, max_height)

        # Adaptive timeout using video duration
        size_mb = original_size / (1024 * 1024)
        duration_sec = 0.0
        if probe:
            try:
                duration_sec = float(probe.get("format", {}).get("duration", 0))
            except (ValueError, TypeError):
                duration_sec = 0.0

        if duration_sec > 0:
            timeout_secs = max(900, min(14400, int(duration_sec * 1.5)))
            logger.info(
                f"Video encode timeout: {timeout_secs}s "
                f"(duration={duration_sec:.0f}s, size={size_mb:.0f} MB)"
            )
        else:
            timeout_secs = max(900, min(14400, int(size_mb / 50 * 180)))
            logger.info(
                f"Video encode timeout: {timeout_secs}s "
                f"(no duration probe, size={size_mb:.0f} MB)"
            )

        # ── Build encoding command ──
        # Prefer GPU (NVENC) if available — 10-30x faster than CPU
        hw_encoder = _detect_hw_encoder()

        cmd = ["ffmpeg", "-y", "-i", str(in_path)]

        if hw_encoder == "h264_nvenc":
            cmd.extend([
                "-c:v", "h264_nvenc",
                "-preset", "medium",
                "-rc", "vbr_hq",
                "-qmin", str(crf - 2),
                "-qmax", str(crf + 4),
                "-b:v", video_bitrate,
                "-maxrate", video_bitrate,
                "-bufsize", "3M",
                "-profile:v", "high",
                "-pix_fmt", "yuv420p",
                "-gpu", "0",
            ])
            encoder_label = "NVENC (GPU)"
            # NVENC is much faster — reduce timeout
            if duration_sec > 0:
                timeout_secs = max(300, min(3600, int(duration_sec * 0.3)))
            else:
                timeout_secs = max(300, min(3600, int(size_mb / 100 * 30)))
        else:
            cmd.extend([
                "-c:v", "libx264",
                "-preset", "fast",
                "-threads", "0",      # use all CPU cores
                "-crf", str(crf),
                "-maxrate", video_bitrate,
                "-bufsize", "3M",
                "-profile:v", "high",
                "-pix_fmt", "yuv420p",
            ])
            encoder_label = "libx264 (CPU)"

        # Audio + container settings
        cmd.extend([
            "-c:a", "aac",
            "-b:a", audio_bitrate,
            "-movflags", "+faststart",
        ])

        if scale_filter:
            cmd.extend(["-vf", scale_filter])

        cmd.append(str(out_path))

        logger.info(
            f"Starting video re-encode: {encoder_label}, "
            f"{original_size/1024/1024:.0f} MB, timeout={timeout_secs}s"
        )

        # Initialize optimization state for frontend polling
        global _active_ffmpeg_proc, _optimization_state

        _optimization_state = {
            "status": "encoding",
            "encoder": encoder_label,
            "deadline": timeout_secs,
            "deadline_warning": False,
            "elapsed": 0,
            "fps": "",
            "speed": "",
            "time": "00:00:00",
            "size_mb": size_mb,
            "duration_sec": duration_sec,
        }

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        _active_ffmpeg_proc = proc

        stderr_lines: list = []
        start_time = _time.monotonic()
        last_log_time = start_time
        last_state_update = start_time
        grace_deadline = None

        try:
            while True:
                retcode = proc.poll()

                line = proc.stderr.readline()
                if line:
                    stderr_lines.append(line.rstrip())
                    now = _time.monotonic()
                    elapsed = now - start_time

                    progress = _parse_ffmpeg_progress(line)
                    if progress and (now - last_state_update >= 2.0):
                        _optimization_state.update({
                            "elapsed": round(elapsed, 1),
                            "fps": progress.get("fps", _optimization_state.get("fps", "")),
                            "speed": progress.get("speed", _optimization_state.get("speed", "")),
                            "time": progress.get("time", _optimization_state.get("time", "")),
                        })
                        last_state_update = now

                    if now - last_log_time >= 5.0:
                        progress_line = line.strip()
                        logger.info(
                            f"ffmpeg [{elapsed:.0f}s]: {progress_line[:120]}"
                        )
                        last_log_time = now

                if retcode is not None:
                    remaining = proc.stderr.read()
                    if remaining:
                        stderr_lines.extend(remaining.rstrip().split('\n'))
                    break

                # ── Soft deadline with grace period ──
                elapsed = _time.monotonic() - start_time
                current_deadline = _optimization_state.get("deadline", timeout_secs)

                if elapsed > current_deadline:
                    if not _optimization_state.get("deadline_warning"):
                        _optimization_state["deadline_warning"] = True
                        grace_deadline = _time.monotonic() + 60
                        logger.warning(
                            f"Optimization deadline reached ({current_deadline:.0f}s). "
                            f"Grace period: 60s. User can extend."
                        )

                    elif grace_deadline and _time.monotonic() > grace_deadline:
                        logger.warning(
                            f"Grace period expired — killing ffmpeg "
                            f"(elapsed={elapsed:.0f}s, deadline={current_deadline:.0f}s)"
                        )
                        proc.kill()
                        proc.wait()
                        raise subprocess.TimeoutExpired(cmd, current_deadline)

                    if not _optimization_state.get("deadline_warning"):
                        grace_deadline = None

        except subprocess.TimeoutExpired:
            raise

        _active_ffmpeg_proc = None
        _optimization_state = {"status": "idle"}
        stderr_text = '\n'.join(stderr_lines)
        elapsed_total = _time.monotonic() - start_time
        logger.info(f"ffmpeg finished in {elapsed_total:.0f}s (rc={proc.returncode})")

        if proc.returncode != 0:
            if proc.returncode == -9:
                logger.info("ffmpeg killed (cancelled by user)")
            else:
                logger.warning(
                    f"ffmpeg video optimization failed (rc={proc.returncode}): "
                    f"{stderr_text[-500:]}"
                )
            return data, mime_type, in_ext

        if not out_path.exists():
            logger.warning("ffmpeg produced no output file")
            return data, mime_type, in_ext

        optimized = out_path.read_bytes()
        new_mime = "video/mp4"
        new_ext = ".mp4"

        if len(optimized) >= original_size:
            logger.info(
                f"Video optimization did not reduce size "
                f"({original_size:,} → {len(optimized):,}), keeping original"
            )
            return data, mime_type, in_ext

        pct = len(optimized) / original_size * 100
        logger.info(
            f"Video optimized: {original_size:,} → {len(optimized):,} bytes "
            f"({pct:.0f}%) [{mime_type} → {new_mime}]"
        )

        return optimized, new_mime, new_ext

    except subprocess.TimeoutExpired:
        logger.warning(
            f"ffmpeg video optimization timed out ({timeout_secs}s) "
            f"for {original_size/1024/1024:.0f} MB file"
        )
        ext = _ext_for_video_mime(mime_type)
        return data, mime_type, ext
    except Exception as e:
        logger.warning(f"Video optimization error: {e}")
        ext = _ext_for_video_mime(mime_type)
        return data, mime_type, ext
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ═════════════════════════════════════════════════════════════════
#  Audio optimization
# ═════════════════════════════════════════════════════════════════


def optimize_audio(
    data: bytes,
    mime_type: str,
    *,
    bitrate: str = AUDIO_BITRATE,
) -> Tuple[bytes, str, str]:
    """Optimize audio: re-encode to AAC in M4A container."""
    if not _ffmpeg_available():
        logger.info("ffmpeg not available — storing audio as-is")
        ext = _ext_for_audio_mime(mime_type)
        return data, mime_type, ext

    original_size = len(data)
    tmpdir = tempfile.mkdtemp(prefix="media_opt_")

    try:
        in_ext = _ext_for_audio_mime(mime_type)
        in_path = Path(tmpdir) / f"input{in_ext}"
        out_path = Path(tmpdir) / "output.m4a"

        in_path.write_bytes(data)

        cmd = [
            "ffmpeg", "-y",
            "-i", str(in_path),
            "-c:a", "aac",
            "-b:a", bitrate,
            "-movflags", "+faststart",
            str(out_path),
        ]

        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120,
        )

        if proc.returncode != 0:
            logger.warning(
                f"ffmpeg audio optimization failed (rc={proc.returncode}): "
                f"{proc.stderr[-500:]}"
            )
            return data, mime_type, in_ext

        if not out_path.exists():
            return data, mime_type, in_ext

        optimized = out_path.read_bytes()
        new_mime = "audio/mp4"
        new_ext = ".m4a"

        if len(optimized) >= original_size:
            logger.info(
                f"Audio optimization did not reduce size "
                f"({original_size:,} → {len(optimized):,}), keeping original"
            )
            return data, mime_type, in_ext

        pct = len(optimized) / original_size * 100
        logger.info(
            f"Audio optimized: {original_size:,} → {len(optimized):,} bytes "
            f"({pct:.0f}%) [{mime_type} → {new_mime}]"
        )

        return optimized, new_mime, new_ext

    except subprocess.TimeoutExpired:
        logger.warning("ffmpeg audio optimization timed out (120s)")
        ext = _ext_for_audio_mime(mime_type)
        return data, mime_type, ext
    except Exception as e:
        logger.warning(f"Audio optimization error: {e}")
        ext = _ext_for_audio_mime(mime_type)
        return data, mime_type, ext
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
