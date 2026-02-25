"""
L1 Domain — Error analysis (pure).

Parses stderr output from failed builds for known error patterns
and suggests remediation. No I/O, no subprocess.

Note: ``_analyse_install_failure`` is NOT here — it calls
``_get_system_deps`` which invokes L3 detection. It will go to
a higher layer.
"""

from __future__ import annotations

import re


def _parse_build_progress(output: str) -> dict:
    """Parse build output for progress information.

    Recognizes progress patterns from:
    - **ninja**: ``[45/100]``
    - **cmake**: ``[ 45%]``
    - **make**: counts targets (heuristic)

    Args:
        output: Combined stdout+stderr from the build command.

    Returns:
        ``{"total_targets": N, "completed": N, "percent": 0-100}``
        or empty dict if no progress detected.
    """
    if not output:
        return {}

    # Ninja: [N/Total]
    ninja_matches = re.findall(r"\[(\d+)/(\d+)\]", output)
    if ninja_matches:
        last = ninja_matches[-1]
        completed = int(last[0])
        total = int(last[1])
        return {
            "total_targets": total,
            "completed": completed,
            "percent": int(completed * 100 / total) if total > 0 else 0,
        }

    # CMake: [ 45%]
    cmake_matches = re.findall(r"\[\s*(\d+)%\]", output)
    if cmake_matches:
        percent = int(cmake_matches[-1])
        return {"percent": percent}

    # Make: count "Compiling" or "CC" lines as a rough heuristic
    compile_lines = re.findall(
        r"(?:^|\n)\s*(?:Compiling|CC|CXX|g\+\+|gcc)\s",
        output,
    )
    if compile_lines:
        return {
            "completed": len(compile_lines),
            "percent": None,  # can't determine total without reading Makefile
        }

    return {}


def _analyse_build_failure(
    tool: str,
    stderr: str,
    build_system: str = "",
) -> dict | None:
    """Analyse a build failure's stderr for common patterns.

    Returns a remediation dict with ``cause`` and ``suggestion``,
    or ``None`` if the error is unrecognized.

    Args:
        tool: Tool being built.
        stderr: stderr output from the failed build.
        build_system: Build system (``make``, ``cmake``, ``ninja``).

    Returns:
        ``{"cause": "...", "suggestion": "...", "confidence": "high|medium|low"}``
    """
    if not stderr:
        return None

    s = stderr.lower()

    # Missing header files
    if "fatal error:" in s and ".h" in s:
        # Extract the missing header
        m = re.search(r"fatal error:\s*(.+\.h):\s*no such file", s)
        header = m.group(1) if m else "unknown"
        return {
            "cause": f"Missing header file: {header}",
            "suggestion": f"Install the development package for {header}. "
                          f"Try: apt-get install -y {tool}-dev or the appropriate -devel package.",
            "confidence": "high",
        }

    # Missing library
    if "cannot find -l" in s:
        m = re.search(r"cannot find -l(\S+)", s)
        lib = m.group(1) if m else "unknown"
        return {
            "cause": f"Missing library: lib{lib}",
            "suggestion": f"Install lib{lib}-dev (Debian) or {lib}-devel (Fedora)",
            "confidence": "high",
        }

    # Out of memory (OOM during compilation)
    if "internal compiler error" in s and ("killed" in s or "virtual memory" in s):
        return {
            "cause": "Out of memory during compilation",
            "suggestion": "Reduce parallel jobs: try -j1 or -j2 instead of full parallelism",
            "confidence": "medium",
        }

    # CMake: package not found
    if "could not find" in s and "cmake" in (build_system or "cmake"):
        m = re.search(r"could not find.*?package\s+(\S+)", s)
        pkg = m.group(1) if m else "a required package"
        return {
            "cause": f"CMake package not found: {pkg}",
            "suggestion": f"Install the cmake package for {pkg} or set CMAKE_PREFIX_PATH",
            "confidence": "medium",
        }

    # Compiler not found
    if "cc: not found" in s or "g++: not found" in s or "gcc: not found" in s:
        return {
            "cause": "C/C++ compiler not found",
            "suggestion": "Install build-essential: apt-get install -y build-essential",
            "confidence": "high",
        }

    # Permission denied
    if "permission denied" in s:
        return {
            "cause": "Permission denied during build",
            "suggestion": "The build step may need sudo, or the build directory permissions need fixing",
            "confidence": "medium",
        }

    return None
