"""
L0 Data — Module-level constants and caches.

Pure data. No logic. No imports beyond stdlib.
"""

from __future__ import annotations

import sys

# Resolve pip via the current interpreter — avoids "pip not found" when
# running inside a venv where bare `pip` isn't on the system PATH.
_PIP: list[str] = [sys.executable, "-m", "pip"]

# Architecture name normalization.
_IARCH_MAP: dict[str, str] = {
    "x86_64": "amd64",
    "AMD64": "amd64",      # Windows / WSL2
    "aarch64": "arm64",
    "arm64": "arm64",      # macOS (Darwin reports arm64)
    "armv7l": "armhf",
    "i686": "i386",
    "i386": "i386",
}

# Runtime cache for version API fetches (GitHub releases, PyPI, etc.).
_VERSION_FETCH_CACHE: dict[str, dict] = {}

# Build timeout tiers (seconds).
BUILD_TIMEOUT_TIERS: dict[str, int] = {
    "small": 300,    # < 10k LOC
    "medium": 600,   # 10k-100k LOC
    "large": 1200,   # 100k-1M LOC
    "huge": 3600,    # 1M+ LOC (LLVM, Linux kernel)
}
