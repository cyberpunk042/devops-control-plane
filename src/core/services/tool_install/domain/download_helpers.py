"""
L1 Domain — Download helpers (pure).

Size formatting and download time estimation.
No I/O, no subprocess.

Note: ``_verify_checksum`` is NOT here — it reads files.
It will go to L4 (execution).
"""

from __future__ import annotations


def _fmt_size(n: int | float) -> str:
    """Format byte count to human-readable string."""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _estimate_download_time(size_bytes: int) -> dict[str, str]:
    """Estimate download time at various connection speeds."""
    speeds = {
        "10 Mbps": 10 * 1024 * 1024 / 8,
        "50 Mbps": 50 * 1024 * 1024 / 8,
        "100 Mbps": 100 * 1024 * 1024 / 8,
    }
    result: dict[str, str] = {}
    for label, speed in speeds.items():
        secs = int(size_bytes / speed)
        if secs < 60:
            result[label] = f"{secs}s"
        elif secs < 3600:
            result[label] = f"{secs // 60}m {secs % 60}s"
        else:
            result[label] = f"{secs // 3600}h {(secs % 3600) // 60}m"
    return result
