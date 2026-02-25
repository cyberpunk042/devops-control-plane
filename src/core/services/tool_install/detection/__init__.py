"""
L3 Detection — ``__init__.py`` re-exports all detection functions.

These functions READ system state but never WRITE.
Subprocess calls, file reads, env var reads — all read-only.
"""

from src.core.services.tool_install.detection.condition import (  # noqa: F401
    _evaluate_condition,
)
from src.core.services.tool_install.detection.environment import (  # noqa: F401
    detect_cpu_features,
    detect_nvm,
    detect_sandbox,
)
from src.core.services.tool_install.detection.hardware import (  # noqa: F401
    _detect_secure_boot,
    _extract_gpu_model,
    _extract_pci_id,
    _list_gpu_modules,
    _lspci_gpu,
    _nvidia_smi,
    _read_available_ram_mb,
    _read_cpu_model,
    _read_disk_free_mb,
    _read_total_ram_mb,
    _rocminfo,
    check_cuda_driver_compat,
    detect_build_toolchain,
    detect_gpu,
    detect_hardware,
    detect_kernel,
)
from src.core.services.tool_install.detection.install_failure import (  # noqa: F401
    _analyse_install_failure,
)
from src.core.services.tool_install.detection.network import (  # noqa: F401
    check_all_registries,
    check_alpine_community_repo,
    check_registry_reachable,
    detect_proxy,
)
from src.core.services.tool_install.detection.recipe_deps import (  # noqa: F401
    _get_system_deps,
)
from src.core.services.tool_install.detection.service_status import (  # noqa: F401
    DATA_DIRS,
    DATA_UPDATE_SCHEDULES,
    _detect_init_system,
    check_data_freshness,
    get_data_pack_usage,
    get_service_status,
)
from src.core.services.tool_install.detection.system_deps import (  # noqa: F401
    _is_pkg_installed,
    check_system_deps,
)
from src.core.services.tool_install.detection.tool_version import (  # noqa: F401
    VERSION_COMMANDS,
    _is_linux_binary,
    check_updates,
    get_tool_version,
)
