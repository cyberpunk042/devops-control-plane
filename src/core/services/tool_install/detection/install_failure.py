"""
L3 Detection — Install failure analysis.

Parses stderr from failed installs for known patterns and
generates structured remediation options. Uses ``_get_system_deps``
which calls ``_detect_os()`` underneath.
"""

from __future__ import annotations

import re
from typing import Any

from src.core.services.tool_install.detection.recipe_deps import _get_system_deps


def _analyse_install_failure(
    tool: str, cli: str, stderr: str,
) -> dict[str, Any] | None:
    """Parse stderr from a failed install and return structured remediation.

    Returns None if no known pattern matched.
    Returns a dict with:
      - reason: human-readable explanation
      - options: list of actionable remediation paths
    """
    if not stderr:
        return None

    # ── Rust version mismatch ──
    # Pattern: "it requires rustc X.Y or newer, while the currently active
    #           rustc version is Z.W"
    # Hint:    "package_name X.Y.Z supports rustc A.B.C"
    rustc_req = re.search(
        r"requires rustc (\d+\.\d+(?:\.\d+)?)\s+or newer.*?"
        r"currently active rustc version is (\d+\.\d+(?:\.\d+)?)",
        stderr,
        re.DOTALL,
    )
    if rustc_req:
        required = rustc_req.group(1)
        current = rustc_req.group(2)

        # Try to extract the compatible fallback version
        compat = re.search(
            rf"`?{re.escape(tool)}\s+(\d+\.\d+\.\d+)`?\s+supports\s+rustc",
            stderr,
        )
        compat_ver = compat.group(1) if compat else None

        options: list[dict[str, Any]] = []

        # Option 1: Install compatible version
        if compat_ver:
            options.append({
                "id": "compatible-version",
                "label": "Compatible Version",
                "icon": "📦",
                "description": (
                    f"Install {tool}@{compat_ver} "
                    f"(works with your rustc {current})"
                ),
                "command": ["cargo", "install", f"{tool}@{compat_ver}"],
                "needs_sudo": False,
                "system_deps": _get_system_deps(tool),
            })

        # Option 2: Upgrade Rust via rustup
        options.append({
            "id": "upgrade-dep",
            "label": "Upgrade Rust",
            "icon": "⬆️",
            "description": (
                f"Install rustup + Rust {required}+, "
                f"then install latest {tool}"
            ),
            "system_deps": _get_system_deps(tool),
            "steps": [
                {
                    "label": "Install rustup + latest Rust",
                    "command": [
                        "bash", "-c",
                        "curl --proto '=https' --tlsv1.2 -sSf "
                        "https://sh.rustup.rs | sh -s -- -y",
                    ],
                    "needs_sudo": False,
                },
                {
                    "label": f"Install {tool}",
                    "command": [
                        "bash", "-c",
                        f'export PATH="$HOME/.cargo/bin:$PATH" && cargo install {tool}',
                    ],
                    "needs_sudo": False,
                },
            ],
        })

        # Option 3: Build from source
        # Cargo can build older commits that support the system rustc
        options.append({
            "id": "build-source",
            "label": "Build from Source",
            "icon": "🔧",
            "description": (
                f"Build {tool} from source using system rustc {current}"
            ),
            "command": [
                "bash", "-c",
                f"cargo install {tool} --locked 2>/dev/null "
                f"|| cargo install {tool}@{compat_ver}" if compat_ver
                else f"cargo install {tool} --locked",
            ],
            "needs_sudo": False,
            "system_deps": _get_system_deps(tool),
        })

        return {
            "type": "version_mismatch",
            "reason": (
                f"{tool} requires rustc {required}+ "
                f"(you have {current})"
            ),
            "options": options,
        }

    # ── npm / node not found ──
    if "npm: command not found" in stderr or "npm: not found" in stderr:
        return {
            "type": "missing_runtime",
            "reason": "npm is not installed",
            "options": [
                {
                    "id": "install-npm",
                    "label": "Install npm",
                    "icon": "📦",
                    "description": "Install npm via system packages",
                    "tool": "npm",
                    "needs_sudo": True,
                },
            ],
        }

    # ── pip not found ──
    if "No module named pip" in stderr or "pip: command not found" in stderr:
        return {
            "type": "missing_runtime",
            "reason": "pip is not installed",
            "options": [
                {
                    "id": "install-pip",
                    "label": "Install pip",
                    "icon": "📦",
                    "description": "Install pip via system packages",
                    "tool": "pip",
                    "needs_sudo": True,
                },
            ],
        }

    # ── Permission denied (npm global) ──
    if "EACCES" in stderr and "permission denied" in stderr.lower():
        return {
            "type": "permissions",
            "reason": "Permission denied — try with sudo",
            "options": [
                {
                    "id": "retry-sudo",
                    "label": "Retry with sudo",
                    "icon": "🔒",
                    "description": "Re-run the install with sudo privileges",
                    "retry_sudo": True,
                },
            ],
        }

    # ── GCC compiler bug (aws-lc-sys / memcmp) ──
    # Pattern: "COMPILER BUG DETECTED" from aws-lc-sys builder
    # See https://gcc.gnu.org/bugzilla/show_bug.cgi?id=95189
    if "COMPILER BUG DETECTED" in stderr or (
        "memcmp" in stderr and "gcc.gnu.org/bugzilla" in stderr
    ):
        return {
            "type": "compiler_bug",
            "reason": (
                f"Your GCC version has a known memcmp bug that prevents "
                f"building {tool}'s crypto dependencies (aws-lc-sys)"
            ),
            "options": [
                {
                    "id": "upgrade-gcc",
                    "label": "Install GCC 12+",
                    "icon": "⬆️",
                    "description": (
                        "Install a newer GCC (gcc-12) that doesn't have "
                        "the memcmp bug, then rebuild"
                    ),
                    "steps": [
                        {
                            "label": "Install gcc-12",
                            "command": [
                                "apt-get", "install", "-y",
                                "gcc-12", "g++-12",
                            ],
                            "needs_sudo": True,
                        },
                        {
                            "label": f"Install {tool} with gcc-12",
                            "command": [
                                "bash", "-c",
                                f'export CC=gcc-12 CXX=g++-12 '
                                f'PATH="$HOME/.cargo/bin:$PATH" '
                                f"&& cargo install {tool}",
                            ],
                            "needs_sudo": False,
                        },
                    ],
                },
                {
                    "id": "use-clang",
                    "label": "Build with Clang",
                    "icon": "🔧",
                    "description": (
                        "Use clang instead of gcc to avoid the compiler bug"
                    ),
                    "steps": [
                        {
                            "label": "Install clang",
                            "command": [
                                "apt-get", "install", "-y", "clang",
                            ],
                            "needs_sudo": True,
                        },
                        {
                            "label": f"Install {tool} with clang",
                            "command": [
                                "bash", "-c",
                                f'export CC=clang CXX=clang++ '
                                f'PATH="$HOME/.cargo/bin:$PATH" '
                                f"&& cargo install {tool}",
                            ],
                            "needs_sudo": False,
                        },
                    ],
                },
            ],
        }

    return None
