"""
Deep system detection endpoint.

Routes registered on ``audit_bp`` from the parent package.

Endpoints:
    POST /audit/system/deep-detect — GPU, kernel, hardware, build tools, network
"""

from __future__ import annotations

from flask import jsonify, request

from . import audit_bp


@audit_bp.route("/audit/system/deep-detect", methods=["POST"])
def audit_deep_detect():
    """Run deep system detection (GPU, kernel, hardware, build tools, network).

    This is the "deep tier" — takes ~2s, called on-demand before
    provisioning flows that need hardware/network info.

    Request body:
        {"checks": ["gpu", "hardware", "kernel", "build", "network", "environment"]}
        If empty, runs all checks.

    Response:
        {"gpu": {...}, "hardware": {...}, "kernel": {...},
         "build_toolchain": {...}, "network": {...}, "environment": {...}}
    """
    from src.core.services.tool_install import (
        detect_build_toolchain,
        detect_gpu,
        detect_kernel,
    )
    from src.core.services.tool_install.detection.environment import (
        detect_cpu_features,
        detect_nvm,
        detect_sandbox,
    )
    from src.core.services.tool_install.detection.hardware import detect_hardware
    from src.core.services.tool_install.detection.network import (
        check_all_registries,
        detect_proxy,
    )

    body = request.get_json(silent=True) or {}
    checks = body.get("checks", [])
    run_all = not checks

    result: dict = {}

    if run_all or "gpu" in checks:
        try:
            gpu_info = detect_gpu()
            # Auto-check CUDA/driver compat when both are available
            from src.core.services.tool_install.detection.hardware import check_cuda_driver_compat
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
            result["network"] = {
                "registries": check_all_registries(timeout=3),
                "proxy": detect_proxy(),
            }
            # Add Alpine community repo check if applicable
            from src.core.services.tool_install.detection.network import check_alpine_community_repo
            alpine_check = check_alpine_community_repo()
            if alpine_check.get("is_alpine"):
                result["network"]["alpine_community"] = alpine_check
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

    return jsonify(result)
