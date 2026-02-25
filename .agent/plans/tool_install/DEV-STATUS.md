# Tool Install — Wiring Status (2026-02-25)

## Current State: 100% Wired ✅

| Category | Count | % |
|----------|-------|---|
| **Referenced (alive)** | 137 | 100% |
| **Dead code** | 0 | 0% |
| **Total** | **137** | **100%** |

---

## All Fixes Applied (32 → 0 unwired)

### Backend Wiring (resolver + orchestrator)

| Fix | What | Functions wired |
|-----|------|-----------------|
| **Version constraint** | Resolver checks installed version before returning `already_installed`. Falls through to upgrade plan if version is below `minimum_version` or fails `version_constraint`. | `check_version_constraint`, `get_tool_version` |
| **Restart detection** | After plan completes, `detect_restart_needs` + `_batch_restarts` analyze completed steps. SSE `done` event includes `restart` + `restart_actions` fields. | `detect_restart_needs`, `_batch_restarts` |
| **Network pre-flight** | Before execute, infer required registries from step commands (pip→pypi, cargo→crates, npm→npm), probe reachability, emit `network_warning` SSE events. | `check_registry_reachable`, `detect_proxy` |
| **Build-from-source** | Resolver generates source→build→install→cleanup steps when method is `source`. Dispatches to autotools, cmake, or cargo-git plan generators. Validates toolchain first. | `_autotools_plan`, `_cmake_plan`, `_cargo_git_plan`, `_validate_toolchain`, `_substitute_install_vars` |
| **Offline cache in executor** | Before running download/github_release steps, checks for cached artifacts and substitutes local files. | `install_from_cache`, `load_cached_artifacts` |

### New API Routes

| Method | Path | Purpose | Functions wired |
|--------|------|---------|-----------------|
| POST | `/api/audit/system/deep-detect` | GPU/hardware/kernel/build/network/env detection | `detect_gpu`, `detect_hardware`, `detect_kernel`, `detect_build_toolchain`, `check_cuda_driver_compat`, `check_all_registries`, `detect_proxy`, `check_alpine_community_repo`, `detect_nvm`, `detect_sandbox`, `detect_cpu_features` |
| POST | `/api/audit/install-plan/execute-sync` | Synchronous (non-SSE) plan execution | `execute_plan` |
| POST | `/api/audit/install-plan/cancel` | Cancel interrupted plan | `cancel_plan`, `load_plan_state` |
| POST | `/api/audit/install-plan/archive` | Archive completed/cancelled plan | `archive_plan` |
| POST | `/api/audit/remove-tool` | Remove installed tool | `remove_tool` |
| POST | `/api/audit/install-plan/cache` | Pre-download for offline install | `cache_plan`, `_estimate_download_time` |
| GET | `/api/audit/install-cache/status` | Cache inventory | `cache_status`, `get_cache_dir` |
| POST | `/api/audit/install-cache/clear` | Clear cache | `clear_cache` |
| POST | `/api/audit/install-cache/artifacts` | Load cached artifact manifest | `load_cached_artifacts` |

### New SSE Events

| Event Type | When | Payload |
|------------|------|---------|
| `network_warning` | Before first step | `{registry, url, error, proxy_detected}` |
| `done.restart` | After all steps succeed | `{shell_restart, reboot_required, service_restart, reasons}` |
| `done.restart_actions` | After all steps succeed | `[{type, message, severity}, ...]` |

### Resolver Changes

- `already_installed` now includes `version_installed` field
- Version check: `minimum_version` (gte) and `version_constraint` (any type) evaluated before skipping
- Tool with outdated version generates upgrade plan instead of `already_installed`
- `source` method generates: toolchain validation → git clone → build (autotools/cmake/cargo) → cleanup
