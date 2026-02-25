"""
L0 Data — CUDA / Driver compatibility matrix.

Source: https://docs.nvidia.com/cuda/cuda-toolkit-release-notes/
Maps minimum driver version required for each CUDA toolkit version.
"""

from __future__ import annotations

_CUDA_DRIVER_COMPAT: list[tuple[str, str]] = [
    # (cuda_version, min_driver_version)
    ("12.6", "560.28"),
    ("12.5", "555.42"),
    ("12.4", "550.54"),
    ("12.3", "545.23"),
    ("12.2", "535.86"),
    ("12.1", "530.30"),
    ("12.0", "525.60"),
    ("11.8", "520.61"),
    ("11.7", "515.43"),
    ("11.6", "510.39"),
    ("11.5", "495.29"),
    ("11.4", "470.42"),
    ("11.3", "465.19"),
    ("11.2", "460.27"),
    ("11.1", "455.23"),
    ("11.0", "450.36"),
    ("10.2", "440.33"),
    ("10.1", "418.39"),
    ("10.0", "410.48"),
]
