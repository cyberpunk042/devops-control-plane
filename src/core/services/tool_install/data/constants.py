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
#
# EVOLUTION NOTE (2026-02-26):
# This map was originally built for simplicity — one system, one naming
# convention (Go-style: amd64/arm64). As we expanded to full multi-arch
# coverage across 19 presets, we discovered that different upstream projects
# use different naming conventions for their GitHub release assets:
#
#   Go/Docker Hub style:  amd64, arm64          (used by Hugo, Trivy, etc.)
#   Raw uname -m style:   x86_64, aarch64       (used by Docker Compose, etc.)
#
# The global map normalizes to Go-style by default. Tools that use raw
# uname -m naming MUST declare a per-recipe `arch_map` override, which is
# injected by plan_resolution.py into the profile as `_arch_map` before
# variable substitution. See: docker-compose recipe, build_helpers.py
# `_substitute_install_vars()`.
#
# TODO: download.py's `_resolve_github_release_url` also uses this map
# directly for auto-matching. It should support a per-call arch_map
# parameter for consistency with the recipe path.
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
