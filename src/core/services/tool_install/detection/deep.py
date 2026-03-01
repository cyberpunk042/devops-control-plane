"""
Deep system detection — on-demand hardware, GPU, network, and environment probes.

Orchestrates the deep-tier detection modules (GPU, hardware, kernel,
build toolchain, network reachability, environment) into a single
result dict.  Takes ~2s, called on-demand before provisioning flows
that need hardware/network info.

No Flask dependency — pure service logic.
"""

from __future__ import annotations

from typing import Any


def deep_detect(checks: list[str] | None = None) -> dict[str, Any]:
    """Run deep system detection for the requested check categories.

    Args:
        checks: List of categories to run.  Valid values:
            ``"gpu"``, ``"hardware"``, ``"kernel"``, ``"build"``,
            ``"network"``, ``"environment"``.
            If empty or None, runs all checks.

    Returns:
        Dict keyed by category with detection results or error dicts.
    """
    from src.core.services.tool_install.detection.environment import (
        detect_cpu_features,
        detect_nvm,
        detect_sandbox,
    )
    from src.core.services.tool_install.detection.hardware import (
        check_cuda_driver_compat,
        detect_build_toolchain,
        detect_gpu,
        detect_hardware,
        detect_kernel,
    )
    from src.core.services.tool_install.detection.network import (
        check_all_registries,
        check_alpine_community_repo,
        detect_proxy,
    )

    run_all = not checks
    result: dict[str, Any] = {}

    if run_all or "gpu" in checks:
        try:
            gpu_info = detect_gpu()
            # Auto-check CUDA/driver compat when both are available
            nvidia = gpu_info.get("nvidia", {})
            if nvidia.get("cuda_version") and nvidia.get("driver_version"):
                compat = check_cuda_driver_compat(
                    nvidia["cuda_version"],
                    nvidia["driver_version"],
                )
                gpu_info["cuda_driver_compat"] = compat
            result["gpu"] = gpu_info
        except Exception as exc:
            result["gpu"] = {"error": str(exc)}

    if run_all or "hardware" in checks:
        try:
            result["hardware"] = detect_hardware()
        except Exception as exc:
            result["hardware"] = {"error": str(exc)}

    if run_all or "kernel" in checks:
        try:
            result["kernel"] = detect_kernel()
        except Exception as exc:
            result["kernel"] = {"error": str(exc)}

    if run_all or "build" in checks:
        try:
            result["build_toolchain"] = detect_build_toolchain()
        except Exception as exc:
            result["build_toolchain"] = {"error": str(exc)}

    if run_all or "network" in checks:
        try:
            net: dict[str, Any] = {
                "registries": check_all_registries(timeout=3),
                "proxy": detect_proxy(),
            }
            alpine_check = check_alpine_community_repo()
            if alpine_check.get("is_alpine"):
                net["alpine_community"] = alpine_check
            result["network"] = net
        except Exception as exc:
            result["network"] = {"error": str(exc)}

    if run_all or "environment" in checks:
        try:
            result["environment"] = {
                "nvm": detect_nvm(),
                "sandbox": detect_sandbox(),
                "cpu_features": detect_cpu_features(),
            }
        except Exception as exc:
            result["environment"] = {"error": str(exc)}

    return result
