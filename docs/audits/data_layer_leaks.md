# Data Layer Leak Audit

> Generated: 2026-03-08 17:10 UTC  |  Style: **smart**

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Architecture Map](#architecture-map)
3. [🔴 Inline Data Leaks](#-inline-data-leaks-tier-1)
4. [🟠 Wrong-Layer Definitions](#-wrong-layer-definitions-tier-2)
5. [🔄 Data Duplication Map](#-data-duplication-map)
6. [🟡 Import Direction Violations](#-import-direction-violations-tier-3)
7. [🟢 Lateral Service Coupling](#-lateral-service-coupling-tier-4)
8. [Fix Checklist](#fix-checklist)

## Executive Summary

> Your data architecture is **poor**. 315 data boundary issues detected. 126 inline data blobs in function bodies, 156 module constants in wrong layers, 3 duplication groups, 30 import boundary violations. 211 lateral service couplings (advisory).

| Tier | Count | Severity |
|------|-------|----------|
| 🔴 Inline data (in functions) | 852 (126 real, 726 structural) | Critical |
| 🟠 Wrong-layer definitions | 156 | Major |
| 🔄 Duplicated constants | 3 groups | Major |
| 🟡 Import violations | 30 | Moderate |
| 🟢 Lateral coupling | 211 | Advisory |

## Architecture Map

> Detected layers from directory structure.

| Layer | Files | Package |
|-------|-------|---------|
| core-services | 417 | — |
| ui-routes | 120 | — |
| ui-cli | 61 | — |
| core-data | 17 | — |
| adapters | 14 | — |
| core-models | 7 | — |
| other | 6 | — |
| core-usecases | 5 | — |
| core-observability | 4 | — |
| ui-web | 4 | — |
| core-config | 3 | — |
| core-persistence | 3 | — |
| core-reliability | 3 | — |
| core-engine | 2 | — |
| core-security | 1 | — |

```
Allowed dependency flow:

  UI (routes, CLI)
      │
      ▼
  Use Cases / Services
      │
      ▼
  Data / Models / Persistence / Config

  ❌  UI → Data/Persistence (skip services)
  ⚠️  Services/X → Services/Y (lateral)
```

## 🔴 Inline Data Leaks (Tier 1)

> Data literals found inside function bodies. Sorted by item count.
> Classification: 🔴 = data leak, ⚪ = response/result construction, 🔵 = mixed/constructed.

### 🔴 Real Data Leaks

> These should probably be extracted to `core/data/` or `core/models/`.

| File | Function | Line | Type | Items | Assigned To | Why |
|------|----------|------|------|-------|-------------|-----|
| `src/core/services/audit/parsers/python_parser.py` | _get_stdlib_modules() | 48 | set | 94 | `_STDLIB_MODULES` | All-string set with 94 items |
| `src/ui/web/routes/content/preview.py` | content_preview_encrypted() | 227 | set | 24 | `TEXT_SUFFIXES` | All-string set with 24 items |
| `src/ui/web/server.py` | create_app() | 150 | set | 23 | — | All-string set with 23 items |
| `src/core/services/tool_install/detection/hardware.py` | detect_build_toolchain() | 418 | dict | 13 | `_patterns` | All-static dict with 13 literal key-value pairs |
| `src/ui/web/routes/tab_mesh/__init__.py` | _clone_profile_to_debug_dir() | 487 | list | 13 | `essentials` | All-string list with 13 items |
| `src/core/services/artifacts/builders/__init__.py` | get_builder() | 24 | dict | 12 | `_BUILDERS` | Assigned to UPPER_CASE variable _BUILDERS |
| `src/core/services/artifacts/workflow_gen.py` | _resolve_primary_stack() | 395 | list | 12 | `priority` | All-string list with 12 items |
| `src/ui/web/routes/artifacts/api.py` | list_builders() | 199 | list | 12 | `known` | All-string list with 12 items |
| `src/core/services/backup/extras.py` | file_tree_scan() | 118 | set | 11 | `allowed_types` | All-string set with 11 items |
| `src/core/services/content/optimize_video.py` | _detect_hw_encoder() | 168 | list | 11 | — | All-string list with 11 items |
| `src/core/services/dns/cdn_ops.py` | _extract_domains_from_configs() | 255 | list | 11 | — | All-string list with 11 items |
| `src/core/services/config_ops.py` | save_config() | 212 | set | 10 | `_WIZARD_KEYS` | All-string set with 10 items |
| `src/core/services/env/ops.py` | env_validate() | 268 | list | 10 | `placeholder_patterns` | All-string list with 10 items |
| `src/core/services/pages_builders/audit_directive.py` | render_html() | 1332 | dict | 10 | `_FILE_TYPE_LABELS` | Assigned to UPPER_CASE variable _FILE_TYPE_LABELS |
| `src/core/services/content/optimize_video.py` | _ext_for_audio_mime() | 280 | dict | 9 | — | All-static dict with 9 literal key-value pairs |
| `src/core/services/docs_svc/generate.py` | generate_readme() | 178 | list | 9 | — | All-string list with 9 items |
| `src/core/services/k8s/pod_builder.py` | _api_version_for_kind() | 548 | dict | 9 | `mapping` | All-static dict with 9 literal key-value pairs |
| `src/core/services/smart_folders.py` | _glob_walk() | 262 | set | 9 | `_SKIP` | All-string set with 9 items |
| `src/core/services/testing/run.py` | test_coverage() | 132 | list | 9 | — | All-string list with 9 items |
| `src/core/services/tool_install/detection/hardware.py` | _list_gpu_modules() | 116 | set | 9 | `relevant` | All-string set with 9 items |
| `src/adapters/containers/docker.py` | validate() | 50 | set | 8 | `valid_ops` | All-string set with 8 items |
| `src/adapters/vcs/git.py` | validate() | 51 | set | 8 | `valid_ops` | All-string set with 8 items |
| `src/core/services/audit/narrative.py` | _friendly_name() | 580 | dict | 8 | — | All-static dict with 8 literal key-value pairs |
| `src/core/services/audit/parsers/js_parser.py` | extensions() | 349 | set | 8 | — | All-string set with 8 items |
| `src/core/services/docs_svc/generate.py` | generate_readme() | 269 | list | 8 | — | All-string list with 8 items |
| `src/core/services/git/gh_auth.py` | gh_auth_device_start() | 303 | list | 8 | — | All-string list with 8 items |
| `src/ui/web/routes/content/preview.py` | content_preview_encrypted() | 188 | set | 8 | — | All-string set with 8 items |
| `src/ui/web/routes/scripts/registry.py` | scripts_coverage() | 143 | dict | 8 | — | All-static dict with 8 literal key-value pairs |
| `src/core/services/audit/l0_os_detection.py` | _detect_package_managers() | 202 | list | 7 | `_PM_BINARIES` | Assigned to UPPER_CASE variable _PM_BINARIES |
| `src/core/services/content/optimize.py` | optimize_media() | 280 | set | 7 | `skip_mimes` | All-string set with 7 items |
| `src/core/services/content/optimize.py` | _mime_to_ext() | 352 | dict | 7 | — | All-static dict with 7 literal key-value pairs |
| `src/core/services/content/optimize_video.py` | _ext_for_video_mime() | 267 | dict | 7 | — | All-static dict with 7 literal key-value pairs |
| `src/core/services/pages_builders/docusaurus.py` | _stage_install() | 787 | list | 7 | `cmd` | All-string list with 7 items |
| `src/core/services/project_probes.py` | probe_github() | 154 | list | 7 | — | All-string list with 7 items |
| `src/core/services/tool_install/data/recipe_schema.py` | _validate_option() | 483 | set | 7 | `_VALID_REQUIRES_CONDITIONS` | All-string set with 7 items |
| `src/core/services/tool_install/domain/remediation_planning.py` | _compute_availability() | 131 | dict | 7 | `_REQUIRES_CHECKS` | Assigned to UPPER_CASE variable _REQUIRES_CHECKS |
| `src/ui/cli/metrics/__init__.py` | health() | 68 | dict | 7 | `probe_icons` | All-static dict with 7 literal key-value pairs |
| `src/ui/cli/metrics/__init__.py` | health() | 78 | dict | 7 | `probe_names` | All-static dict with 7 literal key-value pairs |
| `src/ui/web/routes/content/preview.py` | content_preview_encrypted() | 214 | set | 7 | — | All-string set with 7 items |
| `src/core/services/artifacts/discovery.py` | _detect_release_scripts() | 1425 | list | 6 | — | All-string list with 6 items |
| `src/core/services/k8s/wizard_generate.py` | _build_env_example() | 686 | list | 6 | `lines` | All-string list with 6 items |
| `src/core/services/packages_svc/actions.py` | _go_outdated() | 143 | list | 6 | — | All-string list with 6 items |
| `src/core/services/pages_builders/docusaurus.py` | _compute_workspace_hash() | 833 | set | 6 | `extensions` | All-string set with 6 items |
| `src/core/services/quality/ops.py` | quality_status() | 268 | list | 6 | `quality_tool_ids` | All-string list with 6 items |
| `src/core/services/scripts/config.py` | load_scripts_config() | 50 | list | 6 | — | All-string list with 6 items |
| `src/core/services/terraform/generate.py` | generate_terraform_k8s() | 392 | list | 6 | — | All-string list with 6 items |
| `src/core/services/testing/ops.py` | testing_status() | 163 | dict | 6 | `_fw_tool_map` | All-static dict with 6 literal key-value pairs |
| `src/core/services/trace/trace_recorder.py` | generate_summary() | 515 | dict | 6 | `_LABELS` | Assigned to UPPER_CASE variable _LABELS |
| `src/core/services/wizard/dispatch.py` | delete_generated_configs() | 71 | list | 6 | — | All-string list with 6 items |
| `src/adapters/shell/filesystem.py` | validate() | 40 | set | 5 | `valid_ops` | All-string set with 5 items |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 674 | dict | 5 | — | All-static dict with 5 literal key-value pairs |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 707 | dict | 5 | — | All-static dict with 5 literal key-value pairs |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 716 | dict | 5 | — | All-static dict with 5 literal key-value pairs |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 725 | dict | 5 | — | All-static dict with 5 literal key-value pairs |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 734 | dict | 5 | — | All-static dict with 5 literal key-value pairs |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 743 | dict | 5 | — | All-static dict with 5 literal key-value pairs |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 765 | dict | 5 | — | All-static dict with 5 literal key-value pairs |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 793 | dict | 5 | — | All-static dict with 5 literal key-value pairs |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 805 | dict | 5 | — | All-static dict with 5 literal key-value pairs |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 814 | dict | 5 | — | All-static dict with 5 literal key-value pairs |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 823 | dict | 5 | — | All-static dict with 5 literal key-value pairs |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 832 | dict | 5 | — | All-static dict with 5 literal key-value pairs |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 841 | dict | 5 | — | All-static dict with 5 literal key-value pairs |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 854 | dict | 5 | — | All-static dict with 5 literal key-value pairs |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 892 | dict | 5 | — | All-static dict with 5 literal key-value pairs |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 904 | dict | 5 | — | All-static dict with 5 literal key-value pairs |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 913 | dict | 5 | — | All-static dict with 5 literal key-value pairs |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 922 | dict | 5 | — | All-static dict with 5 literal key-value pairs |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 967 | dict | 5 | — | All-static dict with 5 literal key-value pairs |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 976 | dict | 5 | — | All-static dict with 5 literal key-value pairs |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 985 | dict | 5 | — | All-static dict with 5 literal key-value pairs |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 994 | dict | 5 | — | All-static dict with 5 literal key-value pairs |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 1006 | dict | 5 | — | All-static dict with 5 literal key-value pairs |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 1015 | dict | 5 | — | All-static dict with 5 literal key-value pairs |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 1024 | dict | 5 | — | All-static dict with 5 literal key-value pairs |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 1033 | dict | 5 | — | All-static dict with 5 literal key-value pairs |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 1042 | dict | 5 | — | All-static dict with 5 literal key-value pairs |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 1054 | dict | 5 | — | All-static dict with 5 literal key-value pairs |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 1063 | dict | 5 | — | All-static dict with 5 literal key-value pairs |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 1072 | dict | 5 | — | All-static dict with 5 literal key-value pairs |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 1084 | dict | 5 | — | All-static dict with 5 literal key-value pairs |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 1093 | dict | 5 | — | All-static dict with 5 literal key-value pairs |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 1102 | dict | 5 | — | All-static dict with 5 literal key-value pairs |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 1114 | dict | 5 | — | All-static dict with 5 literal key-value pairs |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 1123 | dict | 5 | — | All-static dict with 5 literal key-value pairs |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 1132 | dict | 5 | — | All-static dict with 5 literal key-value pairs |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 1144 | dict | 5 | — | All-static dict with 5 literal key-value pairs |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 1153 | dict | 5 | — | All-static dict with 5 literal key-value pairs |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 1162 | dict | 5 | — | All-static dict with 5 literal key-value pairs |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 1206 | dict | 5 | — | All-static dict with 5 literal key-value pairs |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 1215 | dict | 5 | — | All-static dict with 5 literal key-value pairs |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 1224 | dict | 5 | — | All-static dict with 5 literal key-value pairs |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 1236 | dict | 5 | — | All-static dict with 5 literal key-value pairs |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 1245 | dict | 5 | — | All-static dict with 5 literal key-value pairs |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 1254 | dict | 5 | — | All-static dict with 5 literal key-value pairs |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 1263 | dict | 5 | — | All-static dict with 5 literal key-value pairs |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 1275 | dict | 5 | — | All-static dict with 5 literal key-value pairs |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 776 | dict | 5 | — | All-static dict with 5 literal key-value pairs |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 784 | dict | 5 | — | All-static dict with 5 literal key-value pairs |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 865 | dict | 5 | — | All-static dict with 5 literal key-value pairs |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 873 | dict | 5 | — | All-static dict with 5 literal key-value pairs |
| `src/core/services/artifacts/publishers/github_release.py` | publish() | 75 | list | 5 | — | All-string list with 5 items |
| `src/core/services/artifacts/publishers/github_release.py` | publish() | 88 | list | 5 | — | All-string list with 5 items |
| `src/core/services/artifacts/publishers/github_release.py` | publish() | 108 | list | 5 | — | All-string list with 5 items |
| `src/core/services/audit/l0_deep_detectors.py` | _detect_shell() | 42 | dict | 5 | `_profile_map` | All-static dict with 5 literal key-value pairs |
| `src/core/services/audit/l0_deep_detectors.py` | _detect_shell() | 49 | dict | 5 | `_rc_map` | All-static dict with 5 literal key-value pairs |
| `src/core/services/audit/l0_hw_detectors.py` | _detect_kernel_profile() | 206 | list | 5 | `_MODULES_TO_CHECK` | All-string list with 5 items |
| `src/core/services/audit/l2_repo.py` | _repo_health_score() | 340 | dict | 5 | `weights` | All-static dict with 5 literal key-value pairs |
| `src/core/services/audit/parsers/jvm_parser.py` | _extract_java_symbols() | 415 | dict | 5 | `kind_map` | All-static dict with 5 literal key-value pairs |
| `src/core/services/backup/extras.py` | file_tree_scan() | 130 | list | 5 | — | All-string list with 5 items |
| `src/core/services/devops/activity.py` | _extract_summary() | 46 | dict | 5 | — | All-static dict with 5 literal key-value pairs |
| `src/core/services/dns/cdn_ops.py` | _extract_domains_from_configs() | 240 | list | 5 | `config_files` | All-string list with 5 items |
| `src/core/services/dns/cdn_ops.py` | ssl_check() | 400 | list | 5 | — | All-string list with 5 items |
| `src/core/services/git/ops.py` | git_diff() | 556 | dict | 5 | — | All-static dict with 5 literal key-value pairs |
| `src/core/services/pages_builders/audit_directive.py` | _filter_to_scope() | 570 | dict | 5 | `risk_summary` | All-static dict with 5 literal key-value pairs |
| `src/core/services/pages_builders/sphinx.py` | config_schema() | 58 | dict | 5 | — | All-static dict with 5 literal key-value pairs |
| `src/core/services/testing/run.py` | run_tests() | 252 | list | 5 | `cmd` | All-string list with 5 items |
| `src/core/services/tool_install/data/recipe_schema.py` | _validate_handler_list() | 664 | set | 5 | `_handler_req` | All-string set with 5 items |
| `src/core/services/tool_install/data/recipe_schema.py` | _validate_handler_list() | 665 | set | 5 | `_handler_opt` | All-string set with 5 items |
| `src/core/services/tool_install/execution/build_helpers.py` | _validate_toolchain() | 61 | set | 5 | `essential_tools` | All-string set with 5 items |
| `src/core/services/wizard/helpers.py` | _wizard_gh_environments() | 102 | list | 5 | — | All-string list with 5 items |
| `src/core/services/wizard/helpers.py` | _wizard_pages_status() | 232 | list | 5 | `_DEFAULT_DIRS` | All-string list with 5 items |
| `src/ui/cli/metrics/__init__.py` | health() | 51 | dict | 5 | `grade_colors` | All-static dict with 5 literal key-value pairs |
| `src/ui/cli/secrets/status.py` | generate() | 74 | list | 5 | — | All-string list with 5 items |
| `src/ui/cli/security/observe.py` | posture() | 72 | dict | 5 | `grade_colors` | All-static dict with 5 literal key-value pairs |
| `src/ui/web/routes/content/preview.py` | content_preview_encrypted() | 201 | set | 5 | — | All-string set with 5 items |

### ⚪ Response / Result Construction (not leaks)

> These are API responses or result dicts — acceptable.

| File | Function | Line | Type | Items | Why it's OK |
|------|----------|------|------|-------|-------------|
| `src/core/services/wizard/detect.py` | wizard_detect() | 338 | dict | 26 | Directly returned from function |
| `src/core/services/audit/parsers/template_parser.py` | _analyze_jinja2() | 335 | dict | 16 | Directly returned from function |
| `src/core/services/git/ops.py` | git_status() | 319 | dict | 16 | Directly returned from function |
| `src/core/services/k8s/detect.py` | k8s_status() | 244 | dict | 16 | Directly returned from function |
| `src/core/services/audit/l0_detection.py` | _detect_runtime() | 184 | dict | 13 | Directly returned from function |
| `src/core/services/artifacts/discovery.py` | _detect_pip_package() | 1350 | dict | 12 | Directly returned from function |
| `src/core/services/artifacts/discovery.py` | _detect_container() | 1394 | dict | 12 | Directly returned from function |
| `src/core/services/artifacts/discovery.py` | _detect_npm_package() | 1478 | dict | 12 | Directly returned from function |
| `src/core/services/artifacts/discovery.py` | _detect_cargo_package() | 1518 | dict | 12 | Directly returned from function |
| `src/core/services/artifacts/discovery.py` | _detect_go_module() | 1564 | dict | 12 | Directly returned from function |
| `src/core/services/artifacts/discovery.py` | _detect_ruby_gem() | 1609 | dict | 12 | Directly returned from function |
| `src/core/services/artifacts/discovery.py` | _detect_java_package() | 1666 | dict | 12 | Directly returned from function |
| `src/core/services/artifacts/discovery.py` | _detect_dotnet_package() | 1694 | dict | 12 | Directly returned from function |
| `src/core/services/artifacts/discovery.py` | _detect_elixir_package() | 1734 | dict | 12 | Directly returned from function |
| `src/core/services/audit/parsers/template_parser.py` | _analyze_go_template() | 388 | dict | 12 | Directly returned from function |
| `src/core/services/chat/refs_resolve.py` | _resolve_run() | 71 | dict | 12 | Directly returned from function |
| `src/core/services/git/gh_api.py` | gh_repo_info() | 243 | dict | 12 | Directly returned from function |
| `src/core/services/artifacts/engine.py` | get_publishable_artifacts() | 544 | dict | 11 | Directly returned from function |
| `src/core/services/audit/parsers/template_parser.py` | _analyze_pug() | 441 | dict | 11 | Directly returned from function |
| `src/core/services/ledger/worktree.py` | ledger_sync_status() | 451 | dict | 11 | Directly returned from function |
| `src/core/services/project_index.py` | index_status() | 664 | dict | 11 | Directly returned from function |
| `src/core/services/terraform/ops.py` | terraform_status() | 220 | dict | 11 | Directly returned from function |
| `src/core/services/audit/parsers/_base.py` | to_dict() | 204 | dict | 10 | Directly returned from function |
| `src/core/services/chat/refs_resolve.py` | _resolve_release() | 295 | dict | 10 | Directly returned from function |
| `src/core/services/project_probes.py` | probe_git() | 124 | dict | 10 | Directly returned from function |
| `src/core/services/terraform/ops.py` | terraform_status() | 140 | dict | 10 | Directly returned from function |
| `src/core/services/tool_install/domain/remediation_planning.py` | build_remediation_response() | 534 | dict | 10 | Directly returned from function |
| `src/core/observability/metrics.py` | to_dict() | 95 | dict | 9 | Directly returned from function |
| `src/core/reliability/retry_queue.py` | to_dict() | 60 | dict | 9 | Directly returned from function |
| `src/core/services/audit/l0_hw_detectors.py` | _detect_kernel_profile() | 266 | dict | 9 | Directly returned from function |
| `src/core/services/project_probes.py` | run_all_probes() | 434 | dict | 9 | Directly returned from function |
| `src/core/services/smart_folder_peek.py` | peek_topic() | 201 | dict | 9 | Directly returned from function |
| `src/core/services/tool_install/orchestration/orchestrator.py` | execute_plan() | 367 | dict | 9 | Directly returned from function |
| `src/core/engine/executor.py` | to_dict() | 81 | dict | 8 | Directly returned from function |
| `src/core/services/audit/l2_structure.py` | _aggregate_stats() | 375 | dict | 8 | Directly returned from function |
| `src/core/services/audit/parsers/template_parser.py` | _analyze_handlebars() | 411 | dict | 8 | Directly returned from function |
| `src/core/services/audit/parsers/template_parser.py` | _analyze_sfc() | 477 | dict | 8 | Directly returned from function |
| `src/core/services/chat/refs_resolve.py` | _resolve_commit() | 146 | dict | 8 | Directly returned from function |
| `src/core/services/chat/refs_resolve.py` | _resolve_audit() | 230 | dict | 8 | Directly returned from function |
| `src/core/services/project_probes.py` | probe_k8s() | 282 | dict | 8 | Directly returned from function |
| `src/core/services/project_probes.py` | probe_dns() | 417 | dict | 8 | Directly returned from function |
| `src/core/services/scripts/executor.py` | execute_script() | 295 | dict | 8 | Directly returned from function |
| `src/core/services/scripts/executor.py` | execute_script() | 203 | dict | 8 | Directly returned from function |
| `src/core/services/scripts/executor.py` | execute_script() | 217 | dict | 8 | Directly returned from function |
| `src/core/services/scripts/executor.py` | execute_script() | 231 | dict | 8 | Directly returned from function |
| `src/core/services/testing/run.py` | _parse_pytest_output() | 334 | dict | 8 | Directly returned from function |
| `src/core/services/tool_install/detection/hardware.py` | detect_hardware() | 396 | dict | 8 | Directly returned from function |
| `src/core/services/tool_install/execution/chain_state.py` | create_chain() | 84 | dict | 8 | Directly returned from function |
| `src/core/services/tool_install/resolver/dynamic_dep_resolver.py` | resolve_dep_install() | 405 | dict | 8 | Directly returned from function |
| `src/core/services/tool_install/resolver/dynamic_dep_resolver.py` | resolve_dep_install() | 479 | dict | 8 | Directly returned from function |
| `src/core/services/tool_install/resolver/dynamic_dep_resolver.py` | resolve_dep_install() | 421 | dict | 8 | Directly returned from function |
| `src/core/services/tool_install/resolver/dynamic_dep_resolver.py` | resolve_dep_install() | 441 | dict | 8 | Directly returned from function |
| `src/core/services/tool_install/resolver/dynamic_dep_resolver.py` | resolve_dep_install() | 459 | dict | 8 | Directly returned from function |
| `src/core/services/wizard/helpers.py` | _wizard_scripts_status() | 297 | dict | 8 | Directly returned from function |
| `src/core/reliability/circuit_breaker.py` | to_dict() | 111 | dict | 7 | Directly returned from function |
| `src/core/services/audit/l0_deep_detectors.py` | _detect_build_profile() | 357 | dict | 7 | Directly returned from function |
| `src/core/services/audit/l2_repo.py` | _git_history() | 174 | dict | 7 | Directly returned from function |
| `src/core/services/audit/l2_structure.py` | _build_import_graph() | 115 | dict | 7 | Directly returned from function |
| `src/core/services/audit/parsers/template_parser.py` | _analyze_mdx() | 495 | dict | 7 | Directly returned from function |
| `src/core/services/backup/archive.py` | upload_backup() | 592 | dict | 7 | Directly returned from function |
| `src/core/services/chat/refs_resolve.py` | _resolve_trace() | 118 | dict | 7 | Directly returned from function |
| `src/core/services/content/crypto.py` | _parse_envelope() | 386 | dict | 7 | Directly returned from function |
| `src/core/services/dns/cdn_ops.py` | dns_cdn_status() | 159 | dict | 7 | Directly returned from function |
| `src/core/services/dns/cdn_ops.py` | dns_lookup() | 360 | dict | 7 | Directly returned from function |
| `src/core/services/docker/detect.py` | docker_status() | 146 | dict | 7 | Directly returned from function |
| `src/core/services/env/ops.py` | env_diff() | 199 | dict | 7 | Directly returned from function |
| `src/core/services/git/gh_api.py` | gh_status() | 75 | dict | 7 | Directly returned from function |
| `src/core/services/git/gh_repo.py` | gh_repo_rename() | 210 | dict | 7 | Directly returned from function |
| `src/core/services/project_probes.py` | probe_github() | 176 | dict | 7 | Directly returned from function |
| `src/core/services/smart_folder_peek.py` | peek_module() | 98 | dict | 7 | Directly returned from function |
| `src/core/services/terraform/generate.py` | terraform_to_docker_registry() | 610 | dict | 7 | Directly returned from function |
| `src/core/services/tool_install/detection/environment.py` | detect_cpu_features() | 211 | dict | 7 | Directly returned from function |
| `src/core/services/tool_install/execution/offline_cache.py` | cache_plan() | 145 | dict | 7 | Directly returned from function |
| `src/core/services/tool_install/execution/plan_state.py` | resume_plan() | 191 | dict | 7 | Directly returned from function |
| `src/core/services/tool_install/orchestration/orchestrator.py` | execute_plan_dag() | 502 | dict | 7 | Directly returned from function |
| `src/core/services/tool_install/resolver/choice_resolution.py` | resolve_choices() | 271 | dict | 7 | Directly returned from function |
| `src/core/services/wizard/detect.py` | _wizard_stack_defaults() | 506 | dict | 7 | Directly returned from function |
| `src/core/services/wizard/detect.py` | _generic_stack_defaults() | 534 | dict | 7 | Directly returned from function |
| `src/core/use_cases/config_check.py` | to_dict() | 25 | dict | 7 | Directly returned from function |
| `src/ui/cli/content/optimize.py` | optimize() | 61 | dict | 7 | Argument to jsonify/json.dumps/Response |
| `src/ui/web/routes/api/audit.py` | api_audit_activity() | 69 | dict | 7 | Argument to jsonify/json.dumps/Response |
| `src/ui/web/routes/changelog.py` | changelog_get() | 56 | dict | 7 | Directly returned from function |
| `src/ui/web/routes/changelog.py` | _serialize_section() | 56 | dict | 7 | Directly returned from function |
| `src/ui/web/routes/content/preview.py` | content_preview_encrypted() | 239 | dict | 7 | Argument to jsonify/json.dumps/Response |
| `src/core/services/artifacts/discovery.py` | detect_makefile_evolution() | 309 | dict | 6 | Directly returned from function |
| `src/core/services/artifacts/discovery.py` | detect_makefile_evolution() | 286 | dict | 6 | Directly returned from function |
| `src/core/services/artifacts/discovery.py` | _propose_new_makefile() | 1291 | dict | 6 | Directly returned from function |
| `src/core/services/audit/l2_quality.py` | _naming_analysis() | 285 | dict | 6 | Directly returned from function |
| `src/core/services/audit/parsers/template_parser.py` | _analyze_erb() | 361 | dict | 6 | Directly returned from function |
| `src/core/services/audit/parsers/template_parser.py` | _analyze_razor() | 462 | dict | 6 | Directly returned from function |
| `src/core/services/audit/parsers/template_parser.py` | _analyze_heex() | 541 | dict | 6 | Directly returned from function |
| `src/core/services/chat/refs_resolve.py` | _resolve_thread() | 98 | dict | 6 | Directly returned from function |
| `src/core/services/ci/ops.py` | _parse_github_workflow() | 259 | dict | 6 | Directly returned from function |
| `src/core/services/ci/ops.py` | _parse_github_workflow() | 218 | dict | 6 | Directly returned from function |
| `src/core/services/ci/ops.py` | _parse_gitlab_ci() | 343 | dict | 6 | Directly returned from function |
| `src/core/services/ci/ops.py` | _parse_gitlab_ci() | 318 | dict | 6 | Directly returned from function |
| `src/core/services/content/listing.py` | _scan_folder() | 81 | dict | 6 | Directly returned from function |
| `src/core/services/content/outline.py` | extract_outline() | 985 | dict | 6 | Directly returned from function |
| `src/core/services/content/outline.py` | extract_outline() | 1035 | dict | 6 | Directly returned from function |
| `src/core/services/content/release_sync.py` | release_inventory() | 265 | dict | 6 | Directly returned from function |
| `src/core/services/docker/containers.py` | docker_exec_cmd() | 664 | dict | 6 | Directly returned from function |
| `src/core/services/docker/detect.py` | docker_status() | 123 | dict | 6 | Directly returned from function |
| `src/core/services/env/infra_ops.py` | env_card_status() | 277 | dict | 6 | Directly returned from function |
| `src/core/services/env/infra_ops.py` | env_card_status() | 199 | dict | 6 | Directly returned from function |
| `src/core/services/git/auth.py` | check_auth() | 214 | dict | 6 | Directly returned from function |
| `src/core/services/git/auth.py` | check_auth() | 168 | dict | 6 | Directly returned from function |
| `src/core/services/git/auth.py` | check_auth() | 131 | dict | 6 | Directly returned from function |
| `src/core/services/git/auth.py` | check_auth() | 142 | dict | 6 | Directly returned from function |
| `src/core/services/git/auth.py` | check_auth() | 156 | dict | 6 | Directly returned from function |
| `src/core/services/git/auth.py` | check_auth() | 190 | dict | 6 | Directly returned from function |
| `src/core/services/git/auth.py` | check_auth() | 203 | dict | 6 | Directly returned from function |
| `src/core/services/git/auth.py` | _classify_error() | 296 | dict | 6 | Directly returned from function |
| `src/core/services/git/auth.py` | _classify_error() | 274 | dict | 6 | Directly returned from function |
| `src/core/services/git/auth.py` | _classify_error() | 287 | dict | 6 | Directly returned from function |
| `src/core/services/metrics/ops.py` | project_health() | 443 | dict | 6 | Directly returned from function |
| `src/core/services/packages_svc/actions.py` | _pip_audit() | 248 | dict | 6 | Directly returned from function |
| `src/core/services/pages/discovery.py` | init_pages_from_project() | 511 | dict | 6 | Directly returned from function |
| `src/core/services/server_lifecycle.py` | server_status() | 41 | dict | 6 | Directly returned from function |
| `src/core/services/terminal_ops.py` | spawn_terminal() | 304 | dict | 6 | Directly returned from function |
| `src/core/services/terraform/generate.py` | terraform_to_docker_registry() | 650 | dict | 6 | Directly returned from function |
| `src/core/services/testing/ops.py` | _count_tests() | 311 | dict | 6 | Directly returned from function |
| `src/core/services/tool_install/detection/service_status.py` | get_service_status() | 131 | dict | 6 | Directly returned from function |
| `src/core/services/tool_install/orchestration/orchestrator.py` | execute_plan() | 390 | dict | 6 | Directly returned from function |
| `src/core/services/tool_install/orchestration/orchestrator.py` | execute_plan() | 245 | dict | 6 | Directly returned from function |
| `src/core/services/tool_install/resolver/choice_resolution.py` | _resolve_choice_option() | 131 | dict | 6 | Directly returned from function |
| `src/core/services/tool_install/resolver/choice_resolution.py` | resolve_choices() | 450 | dict | 6 | Directly returned from function |
| `src/core/services/tool_install/resolver/choice_resolution.py` | resolve_choices() | 286 | dict | 6 | Directly returned from function |
| `src/core/services/tool_install/resolver/plan_resolution.py` | _resolve_data_pack_plan() | 605 | dict | 6 | Directly returned from function |
| `src/core/services/tool_install/resolver/plan_resolution.py` | _resolve_config_plan() | 660 | dict | 6 | Directly returned from function |
| `src/ui/web/routes/changelog.py` | changelog_get() | 82 | dict | 6 | Argument to jsonify/json.dumps/Response |
| `src/ui/web/routes/metrics/health.py` | project_health() | 89 | dict | 6 | Argument to jsonify/json.dumps/Response |
| `src/ui/web/routes/scripts/registry.py` | scripts_list() | 64 | dict | 6 | Argument to jsonify/json.dumps/Response |
| `src/ui/web/routes/trace/recording.py` | trace_stop() | 72 | dict | 6 | Argument to jsonify/json.dumps/Response |
| `src/core/services/artifacts/builders/base.py` | evt_pipeline_done() | 80 | dict | 5 | Directly returned from function |
| `src/core/services/artifacts/engine.py` | build_target_stream() | 216 | dict | 5 | Argument to jsonify/json.dumps/Response |
| `src/core/services/artifacts/engine.py` | build_target_stream() | 228 | dict | 5 | Argument to jsonify/json.dumps/Response |
| `src/core/services/artifacts/engine.py` | publish_target_stream() | 581 | dict | 5 | Argument to jsonify/json.dumps/Response |
| `src/core/services/artifacts/engine.py` | publish_target_stream() | 593 | dict | 5 | Argument to jsonify/json.dumps/Response |
| `src/core/services/artifacts/engine.py` | publish_target_stream() | 627 | dict | 5 | Argument to jsonify/json.dumps/Response |
| `src/core/services/audit/l2_repo.py` | _git_object_weight() | 102 | dict | 5 | Directly returned from function |
| `src/core/services/audit/l2_repo.py` | _detect_large_files() | 257 | dict | 5 | Directly returned from function |
| `src/core/services/audit/models.py` | make_meta() | 36 | dict | 5 | Directly returned from function |
| `src/core/services/audit/parsers/template_parser.py` | _analyze_haml() | 511 | dict | 5 | Directly returned from function |
| `src/core/services/audit/parsers/template_parser.py` | _analyze_slim() | 525 | dict | 5 | Directly returned from function |
| `src/core/services/audit/scoring.py` | _compute_trend() | 396 | dict | 5 | Directly returned from function |
| `src/core/services/audit/scoring.py` | _compute_trend() | 376 | dict | 5 | Directly returned from function |
| `src/core/services/audit_staging.py` | save_audit() | 250 | dict | 5 | Directly returned from function |
| `src/core/services/backup/archive.py` | preview_backup() | 404 | dict | 5 | Directly returned from function |
| `src/core/services/chat/refs_resolve.py` | _resolve_release() | 271 | dict | 5 | Directly returned from function |
| `src/core/services/chat/refs_resolve.py` | _resolve_code() | 318 | dict | 5 | Directly returned from function |
| `src/core/services/detection.py` | to_dict() | 48 | dict | 5 | Directly returned from function |
| `src/core/services/dns/cdn_ops.py` | _detect_cdn_provider() | 221 | dict | 5 | Directly returned from function |
| `src/core/services/dns/cdn_ops.py` | ssl_check() | 415 | dict | 5 | Directly returned from function |
| `src/core/services/dns/cdn_ops.py` | generate_dns_records() | 558 | dict | 5 | Directly returned from function |
| `src/core/services/docs_svc/ops.py` | check_links() | 363 | dict | 5 | Directly returned from function |
| `src/core/services/env/ops.py` | env_validate() | 290 | dict | 5 | Directly returned from function |
| `src/core/services/git/gh_api.py` | gh_user() | 213 | dict | 5 | Directly returned from function |
| `src/core/services/git/gh_api.py` | check_github_status() | 340 | dict | 5 | Directly returned from function |
| `src/core/services/git/gh_auth.py` | gh_auth_device_start_http() | 783 | dict | 5 | Directly returned from function |
| `src/core/services/git/gh_repo.py` | gh_repo_create() | 68 | dict | 5 | Directly returned from function |
| `src/core/services/git/history.py` | git_history_reset() | 185 | dict | 5 | Directly returned from function |
| `src/core/services/k8s/cluster.py` | cluster_status() | 118 | dict | 5 | Directly returned from function |
| `src/core/services/k8s/helm_generate.py` | _build_values_yaml() | 93 | dict | 5 | Directly returned from function |
| `src/core/services/k8s/validate.py` | validate_manifests() | 145 | dict | 5 | Directly returned from function |
| `src/core/services/ledger/ledger_ops.py` | save_audit_snapshot() | 107 | dict | 5 | Argument to jsonify/json.dumps/Response |
| `src/core/services/metrics/ops.py` | project_summary() | 498 | dict | 5 | Directly returned from function |
| `src/core/services/packages_svc/actions.py` | _cargo_outdated() | 177 | dict | 5 | Directly returned from function |
| `src/core/services/packages_svc/actions.py` | _pip_audit() | 284 | dict | 5 | Directly returned from function |
| `src/core/services/packages_svc/actions.py` | _npm_audit() | 308 | dict | 5 | Directly returned from function |
| `src/core/services/packages_svc/actions.py` | _cargo_audit() | 340 | dict | 5 | Directly returned from function |
| `src/core/services/packages_svc/actions.py` | _cargo_audit() | 320 | dict | 5 | Directly returned from function |
| `src/core/services/project_probes.py` | probe_docker() | 208 | dict | 5 | Directly returned from function |
| `src/core/services/project_probes.py` | probe_terraform() | 308 | dict | 5 | Directly returned from function |
| `src/core/services/quality/ops.py` | quality_run() | 364 | dict | 5 | Directly returned from function |
| `src/core/services/secrets/gh_ops.py` | push_secrets() | 435 | dict | 5 | Directly returned from function |
| `src/core/services/security/posture.py` | security_posture() | 294 | dict | 5 | Directly returned from function |
| `src/core/services/security/scan.py` | gitignore_analysis() | 283 | dict | 5 | Directly returned from function |
| `src/core/services/smart_folders.py` | resolve() | 193 | dict | 5 | Directly returned from function |
| `src/core/services/stream_subprocess.py` | stream_run() | 106 | dict | 5 | Directly returned from function |
| `src/core/services/stream_subprocess.py` | stream_run() | 115 | dict | 5 | Directly returned from function |
| `src/core/services/stream_subprocess.py` | stream_run() | 164 | dict | 5 | Directly returned from function |
| `src/core/services/stream_subprocess.py` | stream_run() | 138 | dict | 5 | Directly returned from function |
| `src/core/services/terraform/ops.py` | terraform_validate() | 294 | dict | 5 | Directly returned from function |
| `src/core/services/testing/ops.py` | testing_status() | 179 | dict | 5 | Directly returned from function |
| `src/core/services/testing/run.py` | test_coverage() | 185 | dict | 5 | Directly returned from function |
| `src/core/services/tool_install/domain/remediation_planning.py` | _build_chain_context() | 578 | dict | 5 | Directly returned from function |
| `src/core/services/tool_install/domain/remediation_planning.py` | _build_chain_context() | 570 | dict | 5 | Directly returned from function |
| `src/core/services/tool_install/execution/download.py` | _resolve_github_release_url() | 135 | dict | 5 | Directly returned from function |
| `src/core/services/tool_install/execution/step_executors.py` | _execute_shell_config_step() | 924 | dict | 5 | Directly returned from function |
| `src/core/services/tool_install/execution/step_executors.py` | _execute_rollback() | 989 | dict | 5 | Directly returned from function |
| `src/core/services/tool_install/execution/subprocess_runner.py` | _run_subprocess() | 113 | dict | 5 | Directly returned from function |
| `src/core/services/tool_install/execution/tool_management.py` | update_tool() | 117 | dict | 5 | Directly returned from function |
| `src/core/services/tool_install/orchestration/orchestrator.py` | execute_plan_dag() | 553 | dict | 5 | Directly returned from function |
| `src/core/services/tool_install/resolver/plan_resolution.py` | resolve_install_plan() | 126 | dict | 5 | Directly returned from function |
| `src/core/services/tool_install/resolver/plan_resolution.py` | resolve_install_plan() | 108 | dict | 5 | Directly returned from function |
| `src/ui/web/routes/audit/tool_install.py` | tools_status() | 227 | dict | 5 | Argument to jsonify/json.dumps/Response |
| `src/ui/web/routes/content/peek.py` | peek_refs() | 90 | dict | 5 | Argument to jsonify/json.dumps/Response |
| `src/ui/web/routes/content/peek.py` | peek_refs() | 44 | dict | 5 | Argument to jsonify/json.dumps/Response |
| `src/ui/web/routes/content/peek.py` | peek_refs() | 55 | dict | 5 | Argument to jsonify/json.dumps/Response |
| `src/ui/web/routes/content/peek.py` | peek_refs() | 88 | dict | 5 | Argument to jsonify/json.dumps/Response |
| `src/ui/web/routes/content/preview.py` | content_preview() | 87 | dict | 5 | Argument to jsonify/json.dumps/Response |
| `src/ui/web/routes/content/preview.py` | content_preview() | 91 | dict | 5 | Argument to jsonify/json.dumps/Response |
| `src/ui/web/routes/content/preview.py` | content_preview_encrypted() | 192 | dict | 5 | Argument to jsonify/json.dumps/Response |
| `src/ui/web/routes/content/preview.py` | content_preview_encrypted() | 205 | dict | 5 | Argument to jsonify/json.dumps/Response |
| `src/ui/web/routes/content/preview.py` | content_preview_encrypted() | 218 | dict | 5 | Argument to jsonify/json.dumps/Response |
| `src/ui/web/routes/pages/api.py` | patch_script() | 397 | dict | 5 | Argument to jsonify/json.dumps/Response |
| `src/ui/web/routes/smart_folders/__init__.py` | api_smart_folders_discover() | 117 | dict | 5 | Argument to jsonify/json.dumps/Response |
| `src/ui/web/routes/smart_folders/__init__.py` | api_smart_folders_file() | 185 | dict | 5 | Argument to jsonify/json.dumps/Response |

### 🔵 Constructed / Mixed (review manually)

> Mix of static and computed values — might be either.

| File | Function | Line | Type | Items | Reason |
|------|----------|------|------|-------|--------|
| `src/core/services/terraform/generate.py` | generate_terraform_k8s() | 345 | list | 32 | list with computed/mixed values |
| `src/core/services/pages_builders/audit_directive.py` | precompute_audit_data() | 1946 | dict | 31 | Mixed static and computed values |
| `src/core/services/content/optimize_video.py` | optimize_video() | 405 | list | 22 | list with computed/mixed values |
| `src/core/services/artifacts/engine.py` | detect_publish_capabilities() | 266 | dict | 21 | Mixed static and computed values |
| `src/core/services/terraform/generate.py` | generate_terraform_k8s() | 310 | list | 21 | list with computed/mixed values |
| `src/core/services/detection.py` | detect_language() | 187 | dict | 20 | Mixed static and computed values |
| `src/core/services/audit/l0_detection.py` | _detect_manifests() | 299 | list | 19 | list with computed/mixed values |
| `src/core/services/k8s/detect.py` | _detect_kustomize() | 500 | dict | 19 | Mixed static and computed values |
| `src/core/services/terraform/generate.py` | generate_terraform_k8s() | 408 | list | 19 | list with computed/mixed values |
| `src/core/services/audit/parsers/rust_parser.py` | _compute_metrics() | 551 | dict | 17 | Mixed static and computed values |
| `src/core/services/content/optimize_video.py` | optimize_video() | 425 | list | 16 | list with computed/mixed values |
| `src/core/services/secrets/ops.py` | generate_key() | 226 | list | 16 | list with computed/mixed values |
| `src/core/services/audit/parsers/css_parser.py` | _compute_metrics() | 293 | dict | 15 | Mixed static and computed values |
| `src/core/services/audit/parsers/go_parser.py` | _compute_metrics() | 552 | dict | 15 | Mixed static and computed values |
| `src/core/services/wizard/detect.py` | wizard_detect() | 78 | dict | 15 | All values are computed (calls/lookups) |
| `src/core/services/wizard/detect.py` | wizard_detect() | 98 | dict | 14 | Mixed static and computed values |
| `src/ui/web/routes/scripts/registry.py` | scripts_info() | 90 | dict | 14 | Mixed static and computed values |
| `src/core/services/audit/parsers/_base.py` | to_dict() | 241 | dict | 13 | All values are computed (calls/lookups) |
| `src/core/services/audit/parsers/_base.py` | to_dict() | 224 | dict | 13 | All values are computed (calls/lookups) |
| `src/ui/cli/scripts/info.py` | script_info() | 37 | dict | 13 | Mixed static and computed values |
| `src/core/services/artifacts/discovery.py` | detect_artifact_targets() | 109 | dict | 12 | Mixed static and computed values |
| `src/core/services/artifacts/discovery.py` | detect_artifact_targets() | 127 | dict | 12 | Mixed static and computed values |
| `src/core/services/artifacts/discovery.py` | detect_artifact_targets() | 145 | dict | 12 | Mixed static and computed values |
| `src/core/services/artifacts/discovery.py` | detect_artifact_targets() | 163 | dict | 12 | Mixed static and computed values |
| `src/core/services/artifacts/discovery.py` | detect_artifact_targets() | 185 | dict | 12 | Mixed static and computed values |
| `src/core/services/artifacts/discovery.py` | detect_artifact_targets() | 203 | dict | 12 | Mixed static and computed values |
| `src/core/services/artifacts/discovery.py` | detect_artifact_targets() | 221 | dict | 12 | Mixed static and computed values |
| `src/core/services/artifacts/discovery.py` | _detect_makefile_targets() | 418 | dict | 12 | Mixed static and computed values |
| `src/core/services/audit/l2_structure.py` | _analyze_modules() | 201 | dict | 12 | Mixed static and computed values |
| `src/core/services/audit/parsers/config_parser.py` | _analyze_dockerfile() | 374 | dict | 12 | Mixed static and computed values |
| `src/core/services/audit/parsers/jvm_parser.py` | _compute_java_metrics() | 538 | dict | 12 | Mixed static and computed values |
| `src/core/services/audit/parsers/jvm_parser.py` | _compute_kotlin_metrics() | 732 | dict | 12 | Mixed static and computed values |
| `src/core/services/chat/refs_autocomplete.py` | autocomplete() | 51 | dict | 12 | Mixed static and computed values |
| `src/core/services/docker/containers.py` | docker_inspect() | 590 | dict | 12 | Mixed static and computed values |
| `src/core/services/audit/l1_classification.py` | l1_dependencies() | 203 | dict | 11 | Mixed static and computed values |
| `src/core/services/audit/parsers/jvm_parser.py` | _compute_scala_metrics() | 923 | dict | 11 | Mixed static and computed values |
| `src/core/services/content/optimize_video.py` | optimize_audio() | 626 | list | 11 | list with computed/mixed values |
| `src/core/services/docker/detect.py` | docker_status() | 105 | dict | 11 | Mixed static and computed values |
| `src/core/services/env/infra_ops.py` | env_card_status() | 260 | dict | 11 | Mixed static and computed values |
| `src/core/services/k8s/detect.py` | _detect_helm_charts() | 328 | dict | 11 | Mixed static and computed values |
| `src/core/services/pages_builders/audit_directive.py` | render_html() | 1700 | dict | 11 | All values are computed (calls/lookups) |
| `src/core/services/terraform/generate.py` | generate_terraform_k8s() | 454 | list | 11 | list with computed/mixed values |
| `src/ui/cli/metrics/__init__.py` | report() | 161 | list | 11 | list with computed/mixed values |
| `src/core/services/audit/parsers/c_parser.py` | _compute_metrics() | 282 | dict | 10 | Mixed static and computed values |
| `src/core/services/audit/parsers/config_parser.py` | _analyze_hcl() | 317 | dict | 10 | Mixed static and computed values |
| `src/core/services/audit/parsers/config_parser.py` | _analyze_sql() | 537 | dict | 10 | Mixed static and computed values |
| `src/core/services/config_ops.py` | read_config() | 127 | dict | 10 | All values are computed (calls/lookups) |
| `src/core/services/config_ops.py` | detect_content_folders() | 306 | dict | 10 | Mixed static and computed values |
| `src/core/services/content/optimize_video.py` | _probe_media() | 189 | list | 10 | list with computed/mixed values |
| `src/core/services/content/optimize_video.py` | _build_scale_filter() | 247 | list | 10 | list with computed/mixed values |
| `src/core/services/content/optimize_video.py` | optimize_video() | 457 | dict | 10 | Mixed static and computed values |
| `src/core/services/ledger/worktree.py` | notes_append() | 1033 | list | 10 | list with computed/mixed values |
| `src/core/services/pages_builders/docusaurus.py` | _stage_scaffold() | 393 | dict | 10 | Mixed static and computed values |
| `src/core/services/pages_builders/hugo.py` | preview() | 189 | list | 10 | list with computed/mixed values |
| `src/core/services/project_index.py` | _save_to_disk() | 194 | dict | 10 | Mixed static and computed values |
| `src/core/services/vault/core.py` | lock_vault() | 313 | dict | 10 | Mixed static and computed values |
| `src/core/services/wizard/detect.py` | wizard_detect() | 236 | dict | 10 | Mixed static and computed values |
| `src/ui/web/routes/tab_mesh/__init__.py` | cdp_diagnose() | 826 | dict | 10 | Mixed static and computed values |
| `src/ui/web/server.py` | create_app() | 187 | dict | 10 | Mixed static and computed values |
| `src/ui/web/server.py` | _inject_data_catalogs() | 187 | dict | 10 | Mixed static and computed values |
| `src/core/services/artifacts/discovery.py` | _detect_release_scripts() | 1437 | dict | 9 | Mixed static and computed values |
| `src/core/services/artifacts/engine.py` | publish_target_stream() | 638 | dict | 9 | Mixed static and computed values |
| `src/core/services/audit/l0_deep_detectors.py` | _probe_endpoint() | 186 | list | 9 | list with computed/mixed values |
| `src/core/services/audit/l0_detection.py` | _detect_modules() | 280 | dict | 9 | Mixed static and computed values |
| `src/core/services/audit/parsers/_base.py` | to_dict() | 210 | dict | 9 | All values are computed (calls/lookups) |
| `src/core/services/audit/parsers/config_parser.py` | _analyze_shell() | 490 | dict | 9 | Mixed static and computed values |
| `src/core/services/audit/parsers/config_parser.py` | _analyze_graphql() | 607 | dict | 9 | Mixed static and computed values |
| `src/core/services/audit_staging.py` | stage_audit() | 146 | dict | 9 | Mixed static and computed values |
| `src/core/services/chat/refs_autocomplete.py` | _autocomplete_commits() | 268 | list | 9 | list with computed/mixed values |
| `src/core/services/content/file_ops.py` | upload_content_file() | 251 | dict | 9 | Mixed static and computed values |
| `src/core/services/content/listing.py` | list_folder_contents_recursive() | 248 | dict | 9 | Mixed static and computed values |
| `src/core/services/content/listing.py` | _add_file() | 248 | dict | 9 | Mixed static and computed values |
| `src/core/services/content/optimize_video.py` | optimize_video() | 351 | list | 9 | list with computed/mixed values |
| `src/core/services/content/release.py` | upload_to_release_bg() | 195 | list | 9 | list with computed/mixed values |
| `src/core/services/content/release.py` | _do_upload() | 195 | list | 9 | list with computed/mixed values |
| `src/core/services/content/release_sync.py` | restore_large_files() | 103 | list | 9 | list with computed/mixed values |
| `src/core/services/dev_scenarios.py` | _generate_method_family_scenarios() | 493 | dict | 9 | Mixed static and computed values |
| `src/core/services/k8s/detect.py` | k8s_status() | 208 | dict | 9 | Mixed static and computed values |
| `src/core/services/pages/discovery.py` | list_builders_detail() | 59 | dict | 9 | Mixed static and computed values |
| `src/core/services/pages/discovery.py` | list_builders_detail() | 46 | dict | 9 | All values are computed (calls/lookups) |
| `src/core/services/pages_builders/mkdocs.py` | preview() | 256 | list | 9 | list with computed/mixed values |
| `src/core/services/secrets/ops.py` | generate_key() | 201 | list | 9 | list with computed/mixed values |
| `src/core/services/tool_install/orchestration/orchestrator.py` | execute_plan() | 341 | dict | 9 | Mixed static and computed values |
| `src/core/services/vault/io.py` | export_vault_file() | 85 | dict | 9 | Mixed static and computed values |
| `src/core/services/wizard/detect.py` | wizard_detect() | 181 | dict | 9 | Mixed static and computed values |
| `src/core/services/audit/l0_deep_detectors.py` | _detect_shell() | 57 | dict | 8 | Mixed static and computed values |
| `src/core/services/audit/l0_hw_detectors.py` | _detect_gpu_profile() | 129 | dict | 8 | Mixed static and computed values |
| `src/core/services/audit/l1_classification.py` | l1_structure() | 244 | dict | 8 | Mixed static and computed values |
| `src/core/services/audit/l2_quality.py` | _detect_hotspots() | 161 | dict | 8 | Mixed static and computed values |
| `src/core/services/audit/l2_quality.py` | _detect_hotspots() | 172 | dict | 8 | Mixed static and computed values |
| `src/core/services/audit/l2_quality.py` | _detect_hotspots() | 184 | dict | 8 | Mixed static and computed values |
| `src/core/services/audit/parsers/config_parser.py` | _analyze_markdown() | 659 | dict | 8 | Mixed static and computed values |
| `src/core/services/audit/scoring.py` | _quality_score() | 260 | dict | 8 | Mixed static and computed values |
| `src/core/services/audit_staging.py` | list_pending() | 182 | dict | 8 | Mixed static and computed values |
| `src/core/services/backup/archive.py` | create_backup() | 152 | dict | 8 | Mixed static and computed values |
| `src/core/services/chat/refs_resolve.py` | resolve_ref() | 39 | dict | 8 | Mixed static and computed values |
| `src/core/services/config_ops.py` | read_config() | 101 | dict | 8 | Mixed static and computed values |
| `src/core/services/content/listing.py` | list_folder_contents() | 132 | dict | 8 | Mixed static and computed values |
| `src/core/services/content/listing.py` | _add_file() | 132 | dict | 8 | Mixed static and computed values |
| `src/core/services/content/outline.py` | _build_glossary_tree() | 1229 | dict | 8 | Mixed static and computed values |
| `src/core/services/content/release_sync.py` | restore_large_files() | 68 | list | 8 | list with computed/mixed values |
| `src/core/services/content/release_sync.py` | list_release_assets() | 158 | list | 8 | list with computed/mixed values |
| `src/core/services/dev_scenarios.py` | _generate_infra_scenarios() | 542 | dict | 8 | Mixed static and computed values |
| `src/core/services/dev_scenarios.py` | _generate_bootstrap_scenarios() | 590 | dict | 8 | Mixed static and computed values |
| `src/core/services/devops/activity.py` | record_scan_activity() | 704 | dict | 8 | Mixed static and computed values |
| `src/core/services/devops/activity.py` | record_event() | 766 | dict | 8 | Mixed static and computed values |
| `src/core/services/devops/activity.py` | load_activity() | 842 | dict | 8 | Mixed static and computed values |
| `src/core/services/error_log.py` | log_error() | 170 | dict | 8 | Mixed static and computed values |
| `src/core/services/k8s/wizard_detect.py` | skaffold_status() | 94 | dict | 8 | Mixed static and computed values |
| `src/core/services/k8s/wizard_detect.py` | skaffold_status() | 105 | dict | 8 | Mixed static and computed values |
| `src/core/services/ledger/ledger_ops.py` | list_saved_audits() | 228 | dict | 8 | Mixed static and computed values |
| `src/core/services/ledger/worktree.py` | notes_show() | 1055 | list | 8 | list with computed/mixed values |
| `src/core/services/packages_svc/actions.py` | package_install() | 446 | dict | 8 | Mixed static and computed values |
| `src/core/services/pages/build_stream.py` | build_segment_stream() | 170 | dict | 8 | Mixed static and computed values |
| `src/core/services/pages_builders/mkdocs.py` | config_schema() | 55 | list | 8 | list with computed/mixed values |
| `src/core/services/pages_builders/raw.py` | _stage_source() | 78 | list | 8 | list with computed/mixed values |
| `src/core/services/quality/ops.py` | quality_status() | 249 | dict | 8 | Mixed static and computed values |
| `src/core/services/quality/ops.py` | quality_run() | 340 | dict | 8 | Mixed static and computed values |
| `src/core/services/quality/ops.py` | quality_run() | 351 | dict | 8 | Mixed static and computed values |
| `src/core/services/tool_install/detection/hardware.py` | detect_kernel() | 295 | dict | 8 | Mixed static and computed values |
| `src/core/services/tool_install/resolver/choice_resolution.py` | resolve_choices() | 395 | dict | 8 | Mixed static and computed values |
| `src/core/services/tool_install/resolver/choice_resolution.py` | resolve_choices() | 409 | dict | 8 | Mixed static and computed values |
| `src/core/services/wizard/detect.py` | wizard_detect() | 282 | dict | 8 | Mixed static and computed values |
| `src/core/services/wizard/helpers.py` | _wizard_pages_status() | 199 | dict | 8 | Mixed static and computed values |
| `src/ui/cli/scripts/list.py` | list_scripts() | 32 | dict | 8 | All values are computed (calls/lookups) |
| `src/ui/web/routes/scripts/registry.py` | scripts_coverage() | 156 | dict | 8 | Mixed static and computed values |
| `src/core/services/audit/l0_detection.py` | _detect_tools() | 242 | dict | 7 | Mixed static and computed values |
| `src/core/services/audit/l0_detection.py` | l0_system_profile() | 446 | dict | 7 | Mixed static and computed values |
| `src/core/services/audit/l2_structure.py` | _build_import_graph() | 81 | dict | 7 | Mixed static and computed values |
| `src/core/services/audit/parsers/config_parser.py` | _analyze_yaml() | 175 | dict | 7 | Mixed static and computed values |
| `src/core/services/audit/parsers/config_parser.py` | _analyze_protobuf() | 732 | dict | 7 | Mixed static and computed values |
| `src/core/services/backup/archive.py` | create_backup() | 205 | dict | 7 | Mixed static and computed values |
| `src/core/services/backup/restore.py` | restore_backup() | 240 | dict | 7 | Mixed static and computed values |
| `src/core/services/chat/refs_autocomplete.py` | _autocomplete_branches() | 320 | list | 7 | list with computed/mixed values |
| `src/core/services/chat/refs_autocomplete.py` | _autocomplete_users() | 527 | list | 7 | list with computed/mixed values |
| `src/core/services/chat/refs_autocomplete.py` | _autocomplete_releases() | 787 | list | 7 | list with computed/mixed values |
| `src/core/services/chat/refs_resolve.py` | _resolve_commit() | 137 | list | 7 | list with computed/mixed values |
| `src/core/services/content/outline.py` | extract_outline() | 1002 | dict | 7 | Mixed static and computed values |
| `src/core/services/content/outline.py` | extract_outline() | 1017 | dict | 7 | Mixed static and computed values |
| `src/core/services/dev_scenarios.py` | _generate_chain_scenarios() | 640 | dict | 7 | Mixed static and computed values |
| `src/core/services/dev_scenarios.py` | _generate_chain_scenarios() | 675 | dict | 7 | Mixed static and computed values |
| `src/core/services/devops/activity.py` | _extract_detail() | 542 | dict | 7 | All values are computed (calls/lookups) |
| `src/core/services/dns/cdn_ops.py` | ssl_check() | 390 | list | 7 | list with computed/mixed values |
| `src/core/services/docker/containers.py` | docker_containers() | 190 | dict | 7 | All values are computed (calls/lookups) |
| `src/core/services/docker/containers.py` | docker_stats() | 340 | dict | 7 | All values are computed (calls/lookups) |
| `src/core/services/event_bus.py` | publish() | 159 | dict | 7 | Mixed static and computed values |
| `src/core/services/git/auth.py` | check_auth() | 182 | list | 7 | list with computed/mixed values |
| `src/core/services/k8s/cluster.py` | k8s_events() | 342 | dict | 7 | All values are computed (calls/lookups) |
| `src/core/services/ledger/worktree.py` | _create_orphan_branch() | 722 | list | 7 | list with computed/mixed values |
| `src/core/services/metrics/ops.py` | project_health() | 400 | dict | 7 | Mixed static and computed values |
| `src/core/services/notifications.py` | create_notification() | 178 | dict | 7 | Mixed static and computed values |
| `src/core/services/packages_svc/ops.py` | _detect_pm_for_dir() | 143 | dict | 7 | Mixed static and computed values |
| `src/core/services/pages_builders/mkdocs.py` | _stage_build() | 217 | list | 7 | list with computed/mixed values |
| `src/core/services/pages_builders/sphinx.py` | _stage_build() | 195 | list | 7 | list with computed/mixed values |
| `src/core/services/run_tracker.py` | tracked_run() | 238 | dict | 7 | Mixed static and computed values |
| `src/core/services/terraform/generate.py` | generate_terraform_k8s() | 443 | list | 7 | list with computed/mixed values |
| `src/core/services/tool_install/detection/environment.py` | detect_sandbox() | 39 | dict | 7 | Mixed static and computed values |
| `src/core/services/tool_install/execution/build_helpers.py` | _autotools_plan() | 270 | dict | 7 | Mixed static and computed values |
| `src/core/services/tool_install/execution/build_helpers.py` | _cmake_plan() | 341 | dict | 7 | Mixed static and computed values |
| `src/core/services/tool_install/execution/chain_state.py` | escalate_chain() | 145 | dict | 7 | Mixed static and computed values |
| `src/core/services/tool_install/execution/offline_cache.py` | _download_to_cache() | 290 | list | 7 | list with computed/mixed values |
| `src/core/services/tool_install/orchestration/orchestrator.py` | execute_plan() | 307 | dict | 7 | Mixed static and computed values |
| `src/core/services/tool_install/orchestration/orchestrator.py` | execute_plan_dag() | 493 | dict | 7 | Mixed static and computed values |
| `src/core/services/tool_install/resolver/plan_resolution.py` | resolve_install_plan() | 389 | dict | 7 | Mixed static and computed values |
| `src/core/services/tool_install/resolver/plan_resolution.py` | _resolve_config_plan() | 631 | dict | 7 | Mixed static and computed values |
| `src/core/services/vault/io.py` | detect_secret_files() | 239 | dict | 7 | Mixed static and computed values |
| `src/core/services/vault/io.py` | detect_secret_files() | 250 | dict | 7 | Mixed static and computed values |
| `src/core/services/wizard/detect.py` | wizard_detect() | 151 | dict | 7 | Mixed static and computed values |
| `src/core/services/wizard/detect.py` | wizard_detect() | 249 | dict | 7 | Mixed static and computed values |
| `src/core/services/wizard/detect.py` | wizard_detect() | 299 | dict | 7 | Mixed static and computed values |
| `src/core/services/wizard/detect.py` | _wizard_stack_defaults() | 518 | dict | 7 | Mixed static and computed values |
| `src/core/services/wizard/detect.py` | _generic_stack_defaults() | 546 | dict | 7 | Mixed static and computed values |
| `src/ui/web/cdp_client.py` | _curl_exe_put() | 116 | list | 7 | list with computed/mixed values |
| `src/ui/web/routes/content/outline.py` | content_glossary() | 129 | dict | 7 | Mixed static and computed values |
| `src/ui/web/routes/content/preview.py` | content_preview() | 126 | dict | 7 | Mixed static and computed values |
| `src/ui/web/routes/pages/api.py` | list_segments() | 105 | dict | 7 | All values are computed (calls/lookups) |
| `src/ui/web/routes/pages/api.py` | _compute() | 105 | dict | 7 | All values are computed (calls/lookups) |
| `src/ui/web/routes/scripts/registry.py` | scripts_detect() | 209 | dict | 7 | Mixed static and computed values |
| `src/ui/web/routes/scripts/registry.py` | scripts_templates() | 255 | dict | 7 | All values are computed (calls/lookups) |
| `src/core/services/artifacts/builders/docker.py` | build() | 212 | list | 6 | list with computed/mixed values |
| `src/core/services/artifacts/discovery.py` | _detect_makefile_targets() | 374 | dict | 6 | Mixed static and computed values |
| `src/core/services/artifacts/engine.py` | _save_build_status() | 190 | dict | 6 | Mixed static and computed values |
| `src/core/services/artifacts/engine.py` | _resolve_publish_options_for_stacks() | 406 | dict | 6 | Mixed static and computed values |
| `src/core/services/artifacts/engine.py` | _add_entries() | 406 | dict | 6 | Mixed static and computed values |
| `src/core/services/artifacts/release_notes.py` | _get_commits() | 156 | list | 6 | list with computed/mixed values |
| `src/core/services/audit/l0_hw_detectors.py` | _detect_kernel_profile() | 217 | list | 6 | list with computed/mixed values |
| `src/core/services/audit/l0_hw_detectors.py` | _check_module() | 217 | list | 6 | list with computed/mixed values |
| `src/core/services/audit/l0_os_detection.py` | _detect_os() | 329 | dict | 6 | Mixed static and computed values |
| `src/core/services/audit/l0_os_detection.py` | _detect_os() | 339 | dict | 6 | Mixed static and computed values |
| `src/core/services/audit/l0_os_detection.py` | _detect_os() | 348 | dict | 6 | Mixed static and computed values |
| `src/core/services/audit/l2_quality.py` | _detect_hotspots() | 137 | dict | 6 | Mixed static and computed values |
| `src/core/services/audit/l2_quality.py` | _detect_hotspots() | 148 | dict | 6 | Mixed static and computed values |
| `src/core/services/audit/l2_quality.py` | _detect_hotspots() | 201 | dict | 6 | Mixed static and computed values |
| `src/core/services/audit/l2_quality.py` | _naming_analysis() | 263 | dict | 6 | Mixed static and computed values |
| `src/core/services/audit/l2_quality.py` | _naming_analysis() | 274 | dict | 6 | Mixed static and computed values |
| `src/core/services/audit/l2_risk.py` | _make_finding() | 90 | dict | 6 | Mixed static and computed values |
| `src/core/services/audit/parsers/_base.py` | to_dict() | 259 | dict | 6 | All values are computed (calls/lookups) |
| `src/core/services/audit/parsers/css_parser.py` | _compute_metrics() | 312 | dict | 6 | Mixed static and computed values |
| `src/core/services/audit/scoring.py` | _complexity_score() | 114 | dict | 6 | Mixed static and computed values |
| `src/core/services/backup/archive.py` | list_backups() | 300 | dict | 6 | Mixed static and computed values |
| `src/core/services/backup/restore.py` | restore_backup() | 103 | dict | 6 | Mixed static and computed values |
| `src/core/services/backup/restore.py` | wipe_folder() | 402 | dict | 6 | Mixed static and computed values |
| `src/core/services/chat/chat_ops.py` | send_message() | 250 | dict | 6 | Mixed static and computed values |
| `src/core/services/chat/refs_autocomplete.py` | _autocomplete_commits() | 275 | list | 6 | list with computed/mixed values |
| `src/core/services/chat/refs_autocomplete.py` | _autocomplete_audits() | 501 | dict | 6 | Mixed static and computed values |
| `src/core/services/chat/refs_autocomplete.py` | _autocomplete_audits() | 400 | dict | 6 | Mixed static and computed values |
| `src/core/services/chat/refs_autocomplete.py` | _autocomplete_audits() | 441 | dict | 6 | Mixed static and computed values |
| `src/core/services/chat/refs_resolve.py` | _resolve_branch() | 166 | list | 6 | list with computed/mixed values |
| `src/core/services/ci/ops.py` | ci_workflows() | 202 | dict | 6 | Mixed static and computed values |
| `src/core/services/content/file_advanced.py` | save_encrypted_content() | 253 | dict | 6 | Mixed static and computed values |
| `src/core/services/content/file_ops.py` | upload_content_file() | 289 | dict | 6 | Mixed static and computed values |
| `src/core/services/content/optimize_video.py` | optimize_video() | 438 | list | 6 | list with computed/mixed values |
| `src/core/services/content/outline.py` | extract_outline() | 1056 | dict | 6 | Mixed static and computed values |
| `src/core/services/content/outline.py` | extract_folder_glossary() | 1132 | dict | 6 | Mixed static and computed values |
| `src/core/services/content/release.py` | upload_to_release_bg() | 231 | list | 6 | list with computed/mixed values |
| `src/core/services/content/release.py` | delete_release_asset() | 422 | list | 6 | list with computed/mixed values |
| `src/core/services/content/release.py` | _do_upload() | 231 | list | 6 | list with computed/mixed values |
| `src/core/services/dns/cdn_ops.py` | generate_dns_records() | 528 | list | 6 | list with computed/mixed values |
| `src/core/services/docker/detect.py` | _parse_dockerfile() | 170 | dict | 6 | Mixed static and computed values |
| `src/core/services/docs_svc/generate.py` | generate_readme() | 215 | list | 6 | list with computed/mixed values |
| `src/core/services/env/infra_ops.py` | iac_status() | 77 | dict | 6 | Mixed static and computed values |
| `src/core/services/event_bus.py` | _make_ready_event() | 313 | dict | 6 | Mixed static and computed values |
| `src/core/services/event_bus.py` | _make_snapshot_event() | 339 | dict | 6 | Mixed static and computed values |
| `src/core/services/git/auth.py` | get_remote_url() | 60 | list | 6 | list with computed/mixed values |
| `src/core/services/git/auth.py` | key_has_passphrase() | 86 | list | 6 | list with computed/mixed values |
| `src/core/services/git/auth.py` | add_https_credentials() | 458 | list | 6 | list with computed/mixed values |
| `src/core/services/git/ops.py` | git_diff() | 483 | dict | 6 | Mixed static and computed values |
| `src/core/services/git/ops.py` | git_diff() | 546 | dict | 6 | Mixed static and computed values |
| `src/core/services/git/ops.py` | git_diff() | 518 | dict | 6 | Mixed static and computed values |
| `src/core/services/k8s/cluster.py` | k8s_pod_logs() | 210 | list | 6 | list with computed/mixed values |
| `src/core/services/k8s/cluster.py` | k8s_storage_classes() | 454 | dict | 6 | Mixed static and computed values |
| `src/core/services/k8s/helm.py` | helm_values() | 59 | list | 6 | list with computed/mixed values |
| `src/core/services/k8s/helm_generate.py` | generate_helm_chart() | 179 | dict | 6 | Mixed static and computed values |
| `src/core/services/k8s/validate_cross_domain.py` | _cross_cutting() | 1222 | list | 6 | list with computed/mixed values |
| `src/core/services/k8s/wizard_detect.py` | k8s_env_namespaces() | 177 | dict | 6 | Mixed static and computed values |
| `src/core/services/k8s/wizard_generate.py` | _sync_rules_for_language() | 468 | dict | 6 | Mixed static and computed values |
| `src/core/services/metrics/ops.py` | _probe_structure() | 358 | list | 6 | list with computed/mixed values |
| `src/core/services/packages_svc/actions.py` | _pip_audit() | 272 | dict | 6 | All values are computed (calls/lookups) |
| `src/core/services/pages/build_stream.py` | build_segment_stream() | 158 | dict | 6 | Mixed static and computed values |
| `src/core/services/pages/discovery.py` | detect_pages_setup() | 289 | dict | 6 | Mixed static and computed values |
| `src/core/services/pages/discovery.py` | detect_pages_setup() | 306 | dict | 6 | Mixed static and computed values |
| `src/core/services/pages/engine.py` | add_segment() | 108 | dict | 6 | All values are computed (calls/lookups) |
| `src/core/services/pages/engine.py` | build_segment() | 218 | dict | 6 | Mixed static and computed values |
| `src/core/services/pages_builders/custom.py` | config_schema() | 69 | list | 6 | list with computed/mixed values |
| `src/core/services/pages_builders/docusaurus.py` | preview() | 1074 | list | 6 | list with computed/mixed values |
| `src/core/services/pages_builders/hugo.py` | _stage_scaffold() | 115 | list | 6 | list with computed/mixed values |
| `src/core/services/run_tracker.py` | tracked_run() | 190 | dict | 6 | Mixed static and computed values |
| `src/core/services/scripts/config.py` | save_scripts_config() | 67 | dict | 6 | Mixed static and computed values |
| `src/core/services/secrets/gh_ops.py` | push_secrets() | 373 | list | 6 | list with computed/mixed values |
| `src/core/services/secrets/gh_ops.py` | push_secrets() | 403 | list | 6 | list with computed/mixed values |
| `src/core/services/security/posture.py` | security_posture() | 61 | dict | 6 | Mixed static and computed values |
| `src/core/services/security/posture.py` | security_posture() | 103 | dict | 6 | Mixed static and computed values |
| `src/core/services/security/posture.py` | security_posture() | 157 | dict | 6 | Mixed static and computed values |
| `src/core/services/security/posture.py` | security_posture() | 258 | dict | 6 | Mixed static and computed values |
| `src/core/services/security/posture.py` | security_posture() | 72 | dict | 6 | Mixed static and computed values |
| `src/core/services/security/posture.py` | security_posture() | 114 | dict | 6 | Mixed static and computed values |
| `src/core/services/security/posture.py` | security_posture() | 168 | dict | 6 | Mixed static and computed values |
| `src/core/services/security/posture.py` | security_posture() | 200 | dict | 6 | Mixed static and computed values |
| `src/core/services/security/posture.py` | security_posture() | 210 | dict | 6 | Mixed static and computed values |
| `src/core/services/security/posture.py` | security_posture() | 222 | dict | 6 | Mixed static and computed values |
| `src/core/services/security/posture.py` | security_posture() | 269 | dict | 6 | Mixed static and computed values |
| `src/core/services/security/scan.py` | scan_secrets() | 81 | dict | 6 | Mixed static and computed values |
| `src/core/services/terraform/generate.py` | generate_terraform_k8s() | 381 | list | 6 | list with computed/mixed values |
| `src/core/services/tool_install/domain/remediation_planning.py` | build_remediation_response() | 522 | dict | 6 | Mixed static and computed values |
| `src/core/services/tool_install/execution/build_helpers.py` | _autotools_plan() | 262 | dict | 6 | Mixed static and computed values |
| `src/core/services/tool_install/execution/build_helpers.py` | _autotools_plan() | 281 | dict | 6 | Mixed static and computed values |
| `src/core/services/tool_install/execution/build_helpers.py` | _cmake_plan() | 333 | dict | 6 | Mixed static and computed values |
| `src/core/services/tool_install/execution/build_helpers.py` | _cmake_plan() | 352 | dict | 6 | Mixed static and computed values |
| `src/core/services/tool_install/execution/offline_cache.py` | cache_plan() | 90 | dict | 6 | Mixed static and computed values |
| `src/core/services/tool_install/execution/offline_cache.py` | cache_plan() | 109 | dict | 6 | Mixed static and computed values |
| `src/core/services/tool_install/execution/step_executors.py` | _execute_service_step() | 408 | dict | 6 | Mixed static and computed values |
| `src/core/services/tool_install/execution/step_executors.py` | _execute_service_step() | 417 | dict | 6 | Mixed static and computed values |
| `src/core/services/tool_install/execution/step_executors.py` | _execute_service_step() | 426 | dict | 6 | Mixed static and computed values |
| `src/core/services/tool_install/execution/subprocess_runner.py` | _run_subprocess_streaming() | 217 | dict | 6 | Mixed static and computed values |
| `src/core/services/tool_install/orchestration/orchestrator.py` | execute_plan_dag() | 544 | dict | 6 | Mixed static and computed values |
| `src/core/services/tool_install/orchestration/stream.py` | stream_step_execution() | 241 | dict | 6 | Mixed static and computed values |
| `src/core/services/tool_install/path_refresh.py` | refresh_server_path() | 29 | list | 6 | list with computed/mixed values |
| `src/core/services/tool_install/resolver/choice_resolution.py` | resolve_choices() | 413 | dict | 6 | Mixed static and computed values |
| `src/core/services/tool_install/resolver/plan_resolution.py` | resolve_install_plan() | 337 | dict | 6 | Mixed static and computed values |
| `src/core/services/tool_install/resolver/plan_resolution.py` | resolve_install_plan() | 223 | dict | 6 | Mixed static and computed values |
| `src/core/services/tool_install/resolver/plan_resolution.py` | resolve_install_plan() | 244 | dict | 6 | Mixed static and computed values |
| `src/core/services/wizard/detect.py` | wizard_detect() | 152 | dict | 6 | Mixed static and computed values |
| `src/core/services/wizard/detect.py` | wizard_detect() | 162 | dict | 6 | Mixed static and computed values |
| `src/core/services/wizard/detect.py` | wizard_detect() | 171 | dict | 6 | Mixed static and computed values |
| `src/core/services/wizard/detect.py` | wizard_detect() | 202 | dict | 6 | Mixed static and computed values |
| `src/core/services/wizard/detect.py` | wizard_detect() | 210 | dict | 6 | Mixed static and computed values |
| `src/core/services/wizard/detect.py` | wizard_detect() | 222 | dict | 6 | Mixed static and computed values |
| `src/core/services/wizard/detect.py` | wizard_detect() | 267 | dict | 6 | Mixed static and computed values |
| `src/core/services/wizard/helpers.py` | _wizard_pages_status() | 254 | dict | 6 | Mixed static and computed values |
| `src/core/services/wizard/helpers.py` | _wizard_scripts_status() | 309 | dict | 6 | All values are computed (calls/lookups) |
| `src/core/use_cases/status.py` | to_dict() | 58 | dict | 6 | All values are computed (calls/lookups) |
| `src/ui/cli/audit/install.py` | install() | 153 | dict | 6 | Mixed static and computed values |
| `src/ui/cli/audit/install.py` | install() | 164 | dict | 6 | Mixed static and computed values |
| `src/ui/cli/audit/install.py` | install() | 135 | dict | 6 | Mixed static and computed values |
| `src/ui/cli/audit/resume.py` | resume() | 91 | dict | 6 | Mixed static and computed values |
| `src/ui/cli/audit/resume.py` | resume() | 100 | dict | 6 | Mixed static and computed values |
| `src/ui/cli/scripts/info.py` | script_info() | 51 | dict | 6 | All values are computed (calls/lookups) |
| `src/ui/web/routes/artifacts/api.py` | makefile_patch() | 256 | list | 6 | list with computed/mixed values |
| `src/ui/web/routes/audit/async_scan.py` | _run_scan() | 113 | list | 6 | list with computed/mixed values |
| `src/ui/web/routes/audit/async_scan.py` | _get_compute_fn() | 219 | dict | 6 | Mixed static and computed values |
| `src/ui/web/routes/audit/async_scan.py` | audit_scan_status() | 291 | dict | 6 | All values are computed (calls/lookups) |
| `src/ui/web/routes/audit/tool_execution.py` | audit_execute_plan() | 485 | dict | 6 | Mixed static and computed values |
| `src/ui/web/routes/audit/tool_execution.py` | audit_execute_plan() | 401 | dict | 6 | Mixed static and computed values |
| `src/ui/web/routes/audit/tool_execution.py` | audit_execute_plan() | 419 | dict | 6 | Mixed static and computed values |
| `src/ui/web/routes/audit/tool_execution.py` | audit_execute_plan() | 259 | dict | 6 | Mixed static and computed values |
| `src/ui/web/routes/audit/tool_execution.py` | audit_execute_plan() | 353 | dict | 6 | Mixed static and computed values |
| `src/ui/web/routes/audit/tool_execution.py` | audit_resume_plan() | 684 | dict | 6 | Mixed static and computed values |
| `src/ui/web/routes/audit/tool_execution.py` | audit_resume_plan() | 701 | dict | 6 | Mixed static and computed values |
| `src/ui/web/routes/audit/tool_execution.py` | audit_resume_plan() | 733 | dict | 6 | Mixed static and computed values |
| `src/ui/web/routes/audit/tool_execution.py` | audit_resume_plan() | 637 | dict | 6 | Mixed static and computed values |
| `src/ui/web/routes/audit/tool_execution.py` | generate() | 485 | dict | 6 | Mixed static and computed values |
| `src/ui/web/routes/audit/tool_execution.py` | generate() | 401 | dict | 6 | Mixed static and computed values |
| `src/ui/web/routes/audit/tool_execution.py` | generate() | 419 | dict | 6 | Mixed static and computed values |
| `src/ui/web/routes/audit/tool_execution.py` | generate() | 353 | dict | 6 | Mixed static and computed values |
| `src/ui/web/routes/audit/tool_execution.py` | generate() | 684 | dict | 6 | Mixed static and computed values |
| `src/ui/web/routes/audit/tool_execution.py` | generate() | 701 | dict | 6 | Mixed static and computed values |
| `src/ui/web/routes/audit/tool_execution.py` | generate() | 733 | dict | 6 | Mixed static and computed values |
| `src/ui/web/routes/audit/tool_execution.py` | generate() | 637 | dict | 6 | Mixed static and computed values |
| `src/ui/web/routes/audit/tool_execution.py` | generate_dag() | 259 | dict | 6 | Mixed static and computed values |
| `src/ui/web/routes/scripts/registry.py` | scripts_info() | 105 | dict | 6 | All values are computed (calls/lookups) |
| `src/ui/web/routes/smart_folders/__init__.py` | api_smart_folders_list() | 51 | dict | 6 | Mixed static and computed values |
| `src/ui/web/routes/tab_mesh/__init__.py` | restart_chrome() | 637 | list | 6 | list with computed/mixed values |
| `src/core/engine/executor.py` | build_actions() | 163 | dict | 5 | Mixed static and computed values |
| `src/core/services/artifacts/builders/docker.py` | build() | 157 | dict | 5 | Mixed static and computed values |
| `src/core/services/artifacts/builders/go.py` | build() | 60 | dict | 5 | All values are computed (calls/lookups) |
| `src/core/services/artifacts/builders/script.py` | build() | 86 | dict | 5 | All values are computed (calls/lookups) |
| `src/core/services/artifacts/discovery.py` | _analyze_makefile_operability() | 556 | dict | 5 | Mixed static and computed values |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 600 | dict | 5 | Mixed static and computed values |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 610 | dict | 5 | Mixed static and computed values |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 620 | dict | 5 | Mixed static and computed values |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 630 | dict | 5 | Mixed static and computed values |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 640 | dict | 5 | Mixed static and computed values |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 664 | dict | 5 | Mixed static and computed values |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 688 | dict | 5 | Mixed static and computed values |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 654 | dict | 5 | Mixed static and computed values |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 756 | dict | 5 | Mixed static and computed values |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 883 | dict | 5 | Mixed static and computed values |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 937 | dict | 5 | Mixed static and computed values |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 946 | dict | 5 | Mixed static and computed values |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 955 | dict | 5 | Mixed static and computed values |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 1176 | dict | 5 | Mixed static and computed values |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 1185 | dict | 5 | Mixed static and computed values |
| `src/core/services/artifacts/discovery.py` | _propose_target_additions() | 1194 | dict | 5 | Mixed static and computed values |
| `src/core/services/artifacts/publishers/github_release.py` | publish() | 55 | list | 5 | list with computed/mixed values |
| `src/core/services/artifacts/publishers/github_release.py` | publish() | 173 | list | 5 | list with computed/mixed values |
| `src/core/services/artifacts/release_notes.py` | _find_previous_tag() | 139 | list | 5 | list with computed/mixed values |
| `src/core/services/audit/l0_detection.py` | _detect_runtime() | 158 | dict | 5 | Mixed static and computed values |
| `src/core/services/audit/l0_os_detection.py` | _detect_capabilities() | 165 | dict | 5 | Mixed static and computed values |
| `src/core/services/audit/l1_classification.py` | _identify_clients() | 106 | dict | 5 | Mixed static and computed values |
| `src/core/services/audit/l1_classification.py` | _detect_crossovers() | 139 | dict | 5 | Mixed static and computed values |
| `src/core/services/audit/l1_classification.py` | l1_clients() | 416 | dict | 5 | Mixed static and computed values |
| `src/core/services/audit/l1_classification.py` | l1_clients() | 380 | dict | 5 | Mixed static and computed values |
| `src/core/services/audit/l2_quality.py` | l2_quality() | 418 | dict | 5 | Mixed static and computed values |
| `src/core/services/audit/l2_repo.py` | _repo_health_score() | 347 | dict | 5 | All values are computed (calls/lookups) |
| `src/core/services/audit/l2_risk.py` | _dependency_findings() | 268 | dict | 5 | Mixed static and computed values |
| `src/core/services/audit/l2_risk.py` | _generate_action_items() | 560 | dict | 5 | All values are computed (calls/lookups) |
| `src/core/services/audit/l2_risk.py` | l2_risks() | 658 | dict | 5 | Mixed static and computed values |
| `src/core/services/audit/l2_risk.py` | l2_risks() | 675 | dict | 5 | Mixed static and computed values |
| `src/core/services/audit/l2_structure.py` | _cross_module_deps() | 284 | dict | 5 | Mixed static and computed values |
| `src/core/services/audit/l2_structure.py` | l2_structure() | 425 | dict | 5 | Mixed static and computed values |
| `src/core/services/audit/parsers/config_parser.py` | _analyze_json() | 225 | dict | 5 | Mixed static and computed values |
| `src/core/services/audit/parsers/config_parser.py` | _analyze_makefile() | 428 | dict | 5 | Mixed static and computed values |
| `src/core/services/audit/parsers/multilang_parser.py` | _analyze_csharp() | 306 | dict | 5 | Mixed static and computed values |
| `src/core/services/audit/parsers/multilang_parser.py` | _analyze_elixir() | 374 | dict | 5 | Mixed static and computed values |
| `src/core/services/audit/scoring.py` | _quality_score() | 279 | dict | 5 | Mixed static and computed values |
| `src/core/services/backup/archive.py` | folder_tree() | 56 | dict | 5 | Mixed static and computed values |
| `src/core/services/backup/archive.py` | _scan_dirs() | 56 | dict | 5 | Mixed static and computed values |
| `src/core/services/backup/extras.py` | file_tree_scan() | 157 | dict | 5 | Mixed static and computed values |
| `src/core/services/backup/extras.py` | _scan() | 157 | dict | 5 | Mixed static and computed values |
| `src/core/services/backup/restore.py` | restore_backup() | 210 | dict | 5 | Mixed static and computed values |
| `src/core/services/changelog/engine.py` | bootstrap_changelog() | 470 | list | 5 | list with computed/mixed values |
| `src/core/services/chat/refs_autocomplete.py` | _autocomplete_runs() | 131 | dict | 5 | Mixed static and computed values |
| `src/core/services/chat/refs_autocomplete.py` | _autocomplete_commits() | 299 | dict | 5 | Mixed static and computed values |
| `src/core/services/chat/refs_autocomplete.py` | _autocomplete_code() | 633 | dict | 5 | Mixed static and computed values |
| `src/core/services/chat/refs_autocomplete.py` | _content_vault_files() | 722 | dict | 5 | Mixed static and computed values |
| `src/core/services/ci/ops.py` | _parse_github_workflow() | 248 | dict | 5 | Mixed static and computed values |
| `src/core/services/content/crypto_ops.py` | encrypt_content_file() | 60 | dict | 5 | Mixed static and computed values |
| `src/core/services/content/file_ops.py` | upload_content_file() | 297 | dict | 5 | Mixed static and computed values |
| `src/core/services/content/listing.py` | list_folder_contents() | 199 | dict | 5 | Mixed static and computed values |
| `src/core/services/content/listing.py` | list_folder_contents_recursive() | 312 | dict | 5 | Mixed static and computed values |
| `src/core/services/content/listing.py` | _walk() | 312 | dict | 5 | Mixed static and computed values |
| `src/core/services/content/release.py` | upload_to_release_bg() | 272 | dict | 5 | Mixed static and computed values |
| `src/core/services/content/release.py` | _do_upload() | 272 | dict | 5 | Mixed static and computed values |
| `src/core/services/dev_scenarios.py` | _build_synthetic_recipe() | 418 | dict | 5 | Mixed static and computed values |
| `src/core/services/devops/activity.py` | _extract_detail() | 312 | list | 5 | list with computed/mixed values |
| `src/core/services/dns/cdn_ops.py` | generate_dns_records() | 474 | list | 5 | list with computed/mixed values |
| `src/core/services/docker/containers.py` | docker_images() | 225 | dict | 5 | All values are computed (calls/lookups) |
| `src/core/services/docker/containers.py` | docker_compose_status() | 279 | dict | 5 | All values are computed (calls/lookups) |
| `src/core/services/docker/detect.py` | _parse_compose_service_details() | 397 | dict | 5 | All values are computed (calls/lookups) |
| `src/core/services/docs_svc/ops.py` | docs_status() | 108 | list | 5 | list with computed/mixed values |
| `src/core/services/docs_svc/ops.py` | docs_status() | 71 | dict | 5 | Mixed static and computed values |
| `src/core/services/docs_svc/ops.py` | docs_coverage() | 235 | dict | 5 | Mixed static and computed values |
| `src/core/services/docs_svc/ops.py` | docs_coverage() | 247 | dict | 5 | Mixed static and computed values |
| `src/core/services/docs_svc/ops.py` | check_links() | 355 | dict | 5 | Mixed static and computed values |
| `src/core/services/docs_svc/ops.py` | check_links() | 338 | dict | 5 | Mixed static and computed values |
| `src/core/services/env/ops.py` | generate_env_example() | 318 | list | 5 | list with computed/mixed values |
| `src/core/services/git/auth.py` | add_https_credentials() | 471 | list | 5 | list with computed/mixed values |
| `src/core/services/git/auth.py` | set_git_identity() | 620 | list | 5 | list with computed/mixed values |
| `src/core/services/git/gh_api.py` | check_github_status() | 326 | dict | 5 | Mixed static and computed values |
| `src/core/services/git/gh_auth.py` | gh_auth_device_start() | 443 | dict | 5 | Mixed static and computed values |
| `src/core/services/git/gh_auth.py` | gh_auth_device_poll_http() | 1034 | dict | 5 | Mixed static and computed values |
| `src/core/services/git/gh_auth.py` | _bg_gh_login() | 1034 | dict | 5 | Mixed static and computed values |
| `src/core/services/git/ops.py` | git_status() | 305 | dict | 5 | All values are computed (calls/lookups) |
| `src/core/services/git/ops.py` | git_log() | 355 | dict | 5 | All values are computed (calls/lookups) |
| `src/core/services/identity.py` | get_git_user_name() | 28 | list | 5 | list with computed/mixed values |
| `src/core/services/k8s/cluster.py` | get_resources() | 161 | dict | 5 | All values are computed (calls/lookups) |
| `src/core/services/k8s/helm.py` | helm_upgrade() | 128 | list | 5 | list with computed/mixed values |
| `src/core/services/k8s/helm_generate.py` | _build_values_yaml() | 122 | dict | 5 | Mixed static and computed values |
| `src/core/services/k8s/validate_cross_domain.py` | _validate_cross_domain() | 83 | dict | 5 | Mixed static and computed values |
| `src/core/services/k8s/wizard.py` | _svc_env_to_resources() | 67 | dict | 5 | Mixed static and computed values |
| `src/core/services/k8s/wizard.py` | _svc_env_to_resources() | 75 | dict | 5 | Mixed static and computed values |
| `src/core/services/k8s/wizard.py` | _svc_volumes_to_pvc_resources() | 100 | dict | 5 | Mixed static and computed values |
| `src/core/services/k8s/wizard.py` | wizard_state_to_resources() | 147 | dict | 5 | Mixed static and computed values |
| `src/core/services/k8s/wizard.py` | wizard_state_to_resources() | 337 | dict | 5 | Mixed static and computed values |
| `src/core/services/k8s/wizard.py` | wizard_state_to_resources() | 389 | dict | 5 | Mixed static and computed values |
| `src/core/services/k8s/wizard.py` | wizard_state_to_resources() | 363 | dict | 5 | Mixed static and computed values |
| `src/core/services/k8s/wizard.py` | wizard_state_to_resources() | 404 | dict | 5 | Mixed static and computed values |
| `src/core/services/k8s/wizard.py` | wizard_state_to_resources() | 423 | dict | 5 | Mixed static and computed values |
| `src/core/services/k8s/wizard.py` | wizard_state_to_resources() | 448 | dict | 5 | Mixed static and computed values |
| `src/core/services/k8s/wizard.py` | wizard_state_to_resources() | 166 | dict | 5 | Mixed static and computed values |
| `src/core/services/k8s/wizard.py` | wizard_state_to_resources() | 409 | dict | 5 | Mixed static and computed values |
| `src/core/services/ledger/worktree.py` | ledger_sync_status() | 427 | dict | 5 | Mixed static and computed values |
| `src/core/services/ledger/worktree.py` | ledger_sync_status() | 436 | dict | 5 | Mixed static and computed values |
| `src/core/services/metrics/ops.py` | project_summary() | 484 | dict | 5 | All values are computed (calls/lookups) |
| `src/core/services/packages_svc/actions.py` | _npm_outdated() | 127 | dict | 5 | Mixed static and computed values |
| `src/core/services/pages/build_stream.py` | build_segment_stream() | 125 | dict | 5 | Mixed static and computed values |
| `src/core/services/pages/build_stream.py` | build_segment_stream() | 139 | dict | 5 | Mixed static and computed values |
| `src/core/services/pages/build_stream.py` | build_segment_stream() | 145 | dict | 5 | Mixed static and computed values |
| `src/core/services/pages/discovery.py` | list_feature_categories() | 90 | dict | 5 | Mixed static and computed values |
| `src/core/services/pages/discovery.py` | detect_pages_setup() | 326 | dict | 5 | Mixed static and computed values |
| `src/core/services/pages/engine.py` | deploy_to_ghpages() | 401 | list | 5 | list with computed/mixed values |
| `src/core/services/pages/pipeline_scanner.py` | _analyze_shell_script() | 256 | dict | 5 | Mixed static and computed values |
| `src/core/services/pages/pipeline_scanner.py` | _analyze_shell_script() | 282 | dict | 5 | Mixed static and computed values |
| `src/core/services/pages_builders/audit_directive.py` | _filter_to_scope() | 549 | dict | 5 | Mixed static and computed values |
| `src/core/services/pages_builders/docusaurus.py` | pipeline_stages() | 98 | list | 5 | list with computed/mixed values |
| `src/core/services/pages_builders/docusaurus.py` | _stage_source() | 178 | list | 5 | list with computed/mixed values |
| `src/core/services/pages_builders/docusaurus.py` | _stage_scaffold() | 641 | dict | 5 | Mixed static and computed values |
| `src/core/services/pages_builders/docusaurus.py` | _stage_scaffold() | 668 | dict | 5 | Mixed static and computed values |
| `src/core/services/pages_builders/docusaurus.py` | _stage_build() | 965 | list | 5 | list with computed/mixed values |
| `src/core/services/pages_builders/hugo.py` | config_schema() | 50 | list | 5 | list with computed/mixed values |
| `src/core/services/pages_builders/hugo.py` | _stage_build() | 151 | list | 5 | list with computed/mixed values |
| `src/core/services/pages_builders/sphinx.py` | config_schema() | 52 | list | 5 | list with computed/mixed values |
| `src/core/services/pages_builders/sphinx.py` | _stage_scaffold() | 175 | list | 5 | list with computed/mixed values |
| `src/core/services/project_index.py` | _build_peek_cache() | 426 | dict | 5 | All values are computed (calls/lookups) |
| `src/core/services/project_index.py` | _build_loop() | 489 | dict | 5 | Mixed static and computed values |
| `src/core/services/project_index.py` | _refresh_loop() | 589 | dict | 5 | Mixed static and computed values |
| `src/core/services/scripts/executor.py` | execute_script() | 286 | dict | 5 | Mixed static and computed values |
| `src/core/services/scripts/registry.py` | get_scripts_summary() | 550 | dict | 5 | All values are computed (calls/lookups) |
| `src/core/services/secrets/env_ops.py` | list_environments() | 40 | list | 5 | list with computed/mixed values |
| `src/core/services/secrets/env_ops.py` | create_environment() | 83 | list | 5 | list with computed/mixed values |
| `src/core/services/secrets/env_ops.py` | cleanup_environment() | 131 | list | 5 | list with computed/mixed values |
| `src/core/services/smart_folders.py` | discover() | 84 | dict | 5 | Mixed static and computed values |
| `src/core/services/terraform/generate.py` | generate_terraform_k8s() | 432 | list | 5 | list with computed/mixed values |
| `src/core/services/testing/run.py` | test_inventory() | 92 | dict | 5 | Mixed static and computed values |
| `src/core/services/tool_install/detection/hardware.py` | detect_gpu() | 138 | dict | 5 | Mixed static and computed values |
| `src/core/services/tool_install/detection/hardware.py` | detect_gpu() | 140 | dict | 5 | Mixed static and computed values |
| `src/core/services/tool_install/domain/restart.py` | _batch_restarts() | 80 | dict | 5 | Mixed static and computed values |
| `src/core/services/tool_install/execution/build_helpers.py` | _substitute_install_vars() | 201 | dict | 5 | All values are computed (calls/lookups) |
| `src/core/services/tool_install/execution/build_helpers.py` | _cmake_plan() | 325 | list | 5 | list with computed/mixed values |
| `src/core/services/tool_install/execution/build_helpers.py` | _cmake_plan() | 344 | list | 5 | list with computed/mixed values |
| `src/core/services/tool_install/execution/build_helpers.py` | _cargo_git_plan() | 394 | dict | 5 | Mixed static and computed values |
| `src/core/services/tool_install/execution/offline_cache.py` | cache_plan() | 135 | dict | 5 | Mixed static and computed values |
| `src/core/services/tool_install/execution/offline_cache.py` | cache_plan() | 125 | dict | 5 | Mixed static and computed values |
| `src/core/services/tool_install/execution/script_verify.py` | download_and_verify_script() | 112 | list | 5 | list with computed/mixed values |
| `src/core/services/tool_install/orchestration/stream.py` | stream_step_execution() | 272 | dict | 5 | Mixed static and computed values |
| `src/core/services/tool_install/orchestration/stream.py` | stream_step_execution() | 84 | dict | 5 | Mixed static and computed values |
| `src/core/services/tool_install/orchestration/stream.py` | stream_step_execution() | 202 | dict | 5 | Mixed static and computed values |
| `src/core/services/tool_install/orchestration/stream.py` | _save_state() | 300 | dict | 5 | Mixed static and computed values |
| `src/core/services/tool_install/resolver/choice_resolution.py` | resolve_choices() | 311 | dict | 5 | All values are computed (calls/lookups) |
| `src/core/services/tool_install/resolver/plan_resolution.py` | resolve_install_plan() | 418 | dict | 5 | Mixed static and computed values |
| `src/core/services/tool_install/resolver/plan_resolution.py` | resolve_install_plan() | 167 | dict | 5 | Mixed static and computed values |
| `src/core/services/tool_install/resolver/plan_resolution.py` | resolve_install_plan() | 156 | dict | 5 | Mixed static and computed values |
| `src/core/services/tool_install/resolver/plan_resolution.py` | resolve_install_plan() | 360 | dict | 5 | Mixed static and computed values |
| `src/core/services/tool_install/resolver/plan_resolution.py` | resolve_install_plan() | 208 | dict | 5 | Mixed static and computed values |
| `src/core/services/tool_install/resolver/plan_resolution.py` | resolve_install_plan() | 273 | dict | 5 | Mixed static and computed values |
| `src/core/services/tool_install/resolver/plan_resolution.py` | resolve_install_plan_with_choices() | 539 | dict | 5 | Mixed static and computed values |
| `src/core/services/tool_requirements.py` | check_required_tools() | 47 | dict | 5 | Mixed static and computed values |
| `src/core/services/tool_requirements.py` | check_required_tools() | 57 | dict | 5 | Mixed static and computed values |
| `src/core/services/vault/env_crud.py` | add_keys() | 98 | dict | 5 | Mixed static and computed values |
| `src/core/services/vault/env_ops.py` | get_templates() | 304 | dict | 5 | Mixed static and computed values |
| `src/core/services/vault/io.py` | list_env_keys() | 372 | dict | 5 | Mixed static and computed values |
| `src/core/services/vault/io.py` | list_env_sections() | 488 | dict | 5 | Mixed static and computed values |
| `src/core/services/wizard/detect.py` | _wizard_stack_defaults() | 511 | dict | 5 | Mixed static and computed values |
| `src/core/services/wizard/detect.py` | _generic_stack_defaults() | 539 | dict | 5 | Mixed static and computed values |
| `src/core/services/wizard/helpers.py` | _wizard_config_data() | 28 | dict | 5 | All values are computed (calls/lookups) |
| `src/core/services/wizard/helpers.py` | _wizard_pages_status() | 179 | dict | 5 | Mixed static and computed values |
| `src/core/services/wizard/setup_ci.py` | setup_ci() | 297 | dict | 5 | Mixed static and computed values |
| `src/core/services/wizard/setup_ci.py` | setup_ci() | 427 | dict | 5 | Mixed static and computed values |
| `src/core/services/wizard/setup_dns.py` | setup_dns() | 392 | dict | 5 | Mixed static and computed values |
| `src/core/services/wizard/setup_git.py` | setup_git() | 90 | list | 5 | list with computed/mixed values |
| `src/core/services/wizard/setup_git.py` | setup_git() | 45 | list | 5 | list with computed/mixed values |
| `src/ui/cli/audit/install.py` | install() | 179 | dict | 5 | Mixed static and computed values |
| `src/ui/cli/audit/resume.py` | resume() | 115 | dict | 5 | Mixed static and computed values |
| `src/ui/cli/docs/__init__.py` | status() | 87 | list | 5 | list with computed/mixed values |
| `src/ui/web/cdp_client.py` | _curl_exe_get() | 96 | list | 5 | list with computed/mixed values |
| `src/ui/web/routes/audit/tool_execution.py` | audit_execute_plan() | 525 | dict | 5 | Mixed static and computed values |
| `src/ui/web/routes/audit/tool_execution.py` | audit_execute_plan() | 500 | dict | 5 | Mixed static and computed values |
| `src/ui/web/routes/audit/tool_execution.py` | audit_execute_plan() | 286 | dict | 5 | Mixed static and computed values |
| `src/ui/web/routes/audit/tool_execution.py` | audit_execute_plan() | 438 | dict | 5 | Mixed static and computed values |
| `src/ui/web/routes/audit/tool_execution.py` | audit_pending_plans() | 564 | dict | 5 | All values are computed (calls/lookups) |
| `src/ui/web/routes/audit/tool_execution.py` | audit_resume_plan() | 745 | dict | 5 | Mixed static and computed values |
| `src/ui/web/routes/audit/tool_execution.py` | audit_resume_plan() | 757 | dict | 5 | Mixed static and computed values |
| `src/ui/web/routes/audit/tool_execution.py` | audit_resume_plan() | 622 | dict | 5 | Mixed static and computed values |
| `src/ui/web/routes/audit/tool_execution.py` | audit_resume_plan() | 719 | dict | 5 | Mixed static and computed values |
| `src/ui/web/routes/audit/tool_execution.py` | generate() | 525 | dict | 5 | Mixed static and computed values |
| `src/ui/web/routes/audit/tool_execution.py` | generate() | 500 | dict | 5 | Mixed static and computed values |
| `src/ui/web/routes/audit/tool_execution.py` | generate() | 286 | dict | 5 | Mixed static and computed values |
| `src/ui/web/routes/audit/tool_execution.py` | generate() | 438 | dict | 5 | Mixed static and computed values |
| `src/ui/web/routes/audit/tool_execution.py` | generate() | 745 | dict | 5 | Mixed static and computed values |
| `src/ui/web/routes/audit/tool_execution.py` | generate() | 757 | dict | 5 | Mixed static and computed values |
| `src/ui/web/routes/audit/tool_execution.py` | generate() | 622 | dict | 5 | Mixed static and computed values |
| `src/ui/web/routes/audit/tool_execution.py` | generate() | 719 | dict | 5 | Mixed static and computed values |
| `src/ui/web/routes/changelog.py` | changelog_cut_release() | 284 | dict | 5 | Mixed static and computed values |
| `src/ui/web/routes/content/__init__.py` | content_list() | 153 | dict | 5 | Mixed static and computed values |
| `src/ui/web/routes/content/peek.py` | peek_refs() | 92 | dict | 5 | All values are computed (calls/lookups) |
| `src/ui/web/routes/content/peek.py` | peek_resolve() | 167 | dict | 5 | All values are computed (calls/lookups) |
| `src/ui/web/routes/scripts/registry.py` | scripts_detect() | 230 | dict | 5 | All values are computed (calls/lookups) |
| `src/ui/web/routes/scripts/registry.py` | scripts_detect() | 221 | dict | 5 | All values are computed (calls/lookups) |

## 🟠 Wrong-Layer Definitions (Tier 2)

> Module-level constants and type definitions that live outside their canonical layer.

### core-services (140 definitions, 1214 total items)

| File | Symbol | Line | Type | Items | Move to |
|------|--------|------|------|-------|---------|
| `src/core/services/peek.py` | `_COMMON_KEYWORDS` | 379 | Set | 54 | `core/data/catalogs/code_keywords.py` |
| `src/core/services/pages_builders/audit_directive.py` | `_EXT_LANG_MAP` | 440 | Dict | 45 | `core/data/catalogs/file_extensions.py` |
| `src/core/services/content/crypto.py` | `CODE_EXTS` | 74 | Set | 41 | `core/data/catalogs/file_extensions.py` |
| `src/core/services/peek.py` | `_CODE_EXTS` | 35 | Set | 41 | `core/data/catalogs/file_extensions.py` |
| `src/core/services/peek.py` | `_COMMON_PASCAL` | 391 | Set | 38 | `core/data/catalogs/peek_data.py` |
| `src/core/services/pages_builders/audit_directive.py` | `ScopedAuditData` | 342 | dataclass | 34 | `core/models/scoped_audit_data.py` |
| `src/core/services/peek.py` | `_KNOWN_FILENAMES` | 59 | Set | 21 | `core/data/catalogs/peek_data.py` |
| `src/core/services/content/crypto.py` | `_CONFIG_FILENAMES` | 96 | Set | 19 | `core/data/catalogs/crypto_data.py` |
| `src/core/services/content/file_advanced.py` | `_EXCLUDED_DIRS` | 56 | Set | 19 | `core/data/catalogs/file_advanced_data.py` |
| `src/core/services/scripts/models.py` | `ScriptMeta` | 50 | dataclass | 19 | `core/models/script_meta.py` |
| `src/core/services/content/optimize.py` | `COMPRESSIBLE_EXTENSIONS` | 70 | Set | 17 | `core/data/catalogs/file_extensions.py` |
| `src/core/services/chat/refs_autocomplete.py` | `_CODE_EXT_ICONS` | 569 | Dict | 16 | `core/data/catalogs/file_extensions.py` |
| `src/core/services/project_index.py` | `ProjectIndex` | 82 | dataclass | 16 | `core/models/project_index.py` |
| `src/core/services/run_tracker.py` | `RUN_TYPES` | 33 | Dict | 16 | `core/data/catalogs/types.py` |
| `src/core/services/tool_install/data/recipe_schema.py` | `VALID_METHOD_KEYS` | 33 | Set | 14 | `core/data/catalogs/recipe_schema_data.py` |
| `src/core/services/tool_install/data/recipe_schema.py` | `_SOURCE_SPEC_FIELDS` | 49 | Set | 14 | `core/data/catalogs/recipe_schema_data.py` |
| `src/core/services/audit/models.py` | `RuntimeInfo` | 70 | TypedDict | 13 | `core/models/runtime_info.py` |
| `src/core/services/audit/parsers/_base.py` | `FileMetrics` | 108 | dataclass | 13 | `core/models/file_metrics.py` |
| `src/core/services/content/optimize.py` | `COMPRESSIBLE_MIMES` | 64 | Set | 13 | `core/data/catalogs/mime_types.py` |
| `src/core/services/ledger/models.py` | `Run` | 36 | BaseModel | 13 | `core/models/run.py` |
| `src/core/services/tool_install/data/recipe_schema.py` | `_COMMON_FIELDS` | 133 | Set | 13 | `core/data/catalogs/recipe_schema_data.py` |
| `src/core/services/tool_install/data/remediation_handlers/constants.py` | `VALID_CATEGORIES` | 27 | Set | 13 | `core/data/catalogs/constants_data.py` |
| `src/core/services/trace/models.py` | `SessionTrace` | 44 | BaseModel | 13 | `core/models/session_trace.py` |
| `src/core/services/audit/parsers/_base.py` | `SymbolInfo` | 72 | dataclass | 12 | `core/models/symbol_info.py` |
| `src/core/services/k8s/wizard.py` | `_STRIP_TOP` | 470 | Set | 12 | `core/data/catalogs/wizard_data.py` |
| `src/core/services/audit/models.py` | `L1StructResult` | 171 | TypedDict | 11 | `core/models/l1_struct_result.py` |
| `src/core/services/audit/parsers/config_parser.py` | `_ANALYZERS` | 749 | Dict | 11 | `core/data/catalogs/config_parser_data.py` |
| `src/core/services/chat/models.py` | `ChatMessage` | 47 | BaseModel | 11 | `core/models/chat_message.py` |
| `src/core/services/chat/refs_autocomplete.py` | `_CATEGORY_ICONS` | 651 | Dict | 11 | `core/data/catalogs/refs_autocomplete_data.py` |
| `src/core/services/content/crypto.py` | `SCRIPT_EXTS` | 81 | Set | 11 | `core/data/catalogs/file_extensions.py` |
| `src/core/services/content/crypto.py` | `CONFIG_EXTS` | 85 | Set | 11 | `core/data/catalogs/file_extensions.py` |
| `src/core/services/peek.py` | `_SCRIPT_EXTS` | 42 | Set | 11 | `core/data/catalogs/file_extensions.py` |
| `src/core/services/peek.py` | `_CONFIG_EXTS` | 46 | Set | 11 | `core/data/catalogs/file_extensions.py` |
| `src/core/services/tool_install/data/remediation_handlers/constants.py` | `VALID_STRATEGIES` | 11 | Set | 11 | `core/data/catalogs/constants_data.py` |
| `src/core/services/audit/models.py` | `L1DepsResult` | 145 | TypedDict | 10 | `core/models/l1_deps_result.py` |
| `src/core/services/audit/parsers/_base.py` | `FileAnalysis` | 161 | dataclass | 10 | `core/models/file_analysis.py` |
| `src/core/services/content/crypto.py` | `DATA_EXTS` | 89 | Set | 10 | `core/data/catalogs/file_extensions.py` |
| `src/core/services/artifacts/engine.py` | `ArtifactTarget` | 27 | dataclass | 9 | `core/models/artifact_target.py` |
| `src/core/services/audit/models.py` | `ModuleInfo` | 95 | TypedDict | 9 | `core/models/module_info.py` |
| `src/core/services/devops/cache.py` | `_INTEGRATION_KEYS` | 598 | Set | 9 | `core/data/catalogs/cache_data.py` |
| `src/core/services/k8s/validate_cross_domain.py` | `_TF_DATABASE_RESOURCES` | 727 | Set | 9 | `core/data/catalogs/validate_cross_domain_data.py` |
| `src/core/services/ledger/models.py` | `RunEvent` | 75 | BaseModel | 9 | `core/models/run_event.py` |
| `src/core/services/pages_builders/audit_directive.py` | `AuditDataBundle` | 245 | dataclass | 9 | `core/models/audit_data_bundle.py` |
| `src/core/services/pages_builders/base.py` | `ConfigField` | 96 | dataclass | 9 | `core/models/config_field.py` |
| `src/core/services/scripts/models.py` | `ScriptConfig` | 123 | dataclass | 9 | `core/models/script_config.py` |
| `src/core/services/artifacts/publishers/base.py` | `ArtifactPublishResult` | 28 | dataclass | 8 | `core/models/artifact_publish_result.py` |
| `src/core/services/audit/parsers/_base.py` | `ImportInfo` | 35 | dataclass | 8 | `core/models/import_info.py` |
| `src/core/services/changelog/models.py` | `CCMessage` | 22 | dataclass | 8 | `core/models/c_c_message.py` |
| `src/core/services/content/crypto.py` | `IMAGE_EXTS` | 70 | Set | 8 | `core/data/catalogs/file_extensions.py` |
| `src/core/services/content/crypto.py` | `DOC_EXTS` | 73 | Set | 8 | `core/data/catalogs/file_extensions.py` |
| `src/core/services/pages/pipeline_scanner.py` | `DetectedScript` | 29 | dataclass | 8 | `core/models/detected_script.py` |
| `src/core/services/tool_install/data/recipe_schema.py` | `_OPTION_COMMON_OPTIONAL` | 71 | Set | 8 | `core/data/catalogs/recipe_schema_data.py` |
| `src/core/services/trace/models.py` | `TraceEvent` | 28 | BaseModel | 8 | `core/models/trace_event.py` |
| `src/core/services/wizard/dispatch.py` | `_SETUP_ACTIONS` | 30 | Dict | 8 | `core/data/catalogs/dispatch_data.py` |
| `src/core/services/audit/models.py` | `L0Result` | 114 | TypedDict | 7 | `core/models/l0_result.py` |
| `src/core/services/ci/ops.py` | `_CI_PROVIDERS` | 60 | Dict | 7 | `core/data/catalogs/ops_data.py` |
| `src/core/services/content/crypto.py` | `ARCHIVE_EXTS` | 93 | Set | 7 | `core/data/catalogs/file_extensions.py` |
| `src/core/services/git/gh_api.py` | `_OUTAGE_PATTERNS` | 350 | List | 7 | `core/data/catalogs/gh_api_data.py` |
| `src/core/services/pages/pipeline_scanner.py` | `DetectedFramework` | 43 | dataclass | 7 | `core/models/detected_framework.py` |
| `src/core/services/pages_builders/base.py` | `BuilderInfo` | 49 | dataclass | 7 | `core/models/builder_info.py` |
| `src/core/services/pages_builders/base.py` | `StageResult` | 83 | dataclass | 7 | `core/models/stage_result.py` |
| `src/core/services/pages_builders/base.py` | `PipelineResult` | 119 | dataclass | 7 | `core/models/pipeline_result.py` |
| `src/core/services/peek.py` | `_DATA_EXTS` | 51 | Set | 7 | `core/data/catalogs/file_extensions.py` |
| `src/core/services/artifacts/discovery.py` | `_VENV_COMMANDS` | 440 | Set | 6 | `core/data/catalogs/discovery_data.py` |
| `src/core/services/artifacts/engine.py` | `ArtifactBuildResult` | 42 | dataclass | 6 | `core/models/artifact_build_result.py` |
| `src/core/services/audit/models.py` | `DependencyInfo` | 129 | TypedDict | 6 | `core/models/dependency_info.py` |
| `src/core/services/audit/models.py` | `ClientInfo` | 185 | TypedDict | 6 | `core/models/client_info.py` |
| `src/core/services/audit/models.py` | `L1ClientsResult` | 194 | TypedDict | 6 | `core/models/l1_clients_result.py` |
| `src/core/services/audit/parsers/_base.py` | `SymbolLocation` | 140 | dataclass | 6 | `core/models/symbol_location.py` |
| `src/core/services/audit/parsers/multilang_parser.py` | `_ANALYZERS` | 531 | Dict | 6 | `core/data/catalogs/multilang_parser_data.py` |
| `src/core/services/chat/models.py` | `Thread` | 83 | BaseModel | 6 | `core/models/thread.py` |
| `src/core/services/k8s/common.py` | `_MANIFEST_DIRS` | 44 | List | 6 | `core/data/catalogs/common_data.py` |
| `src/core/services/pages/pipeline_scanner.py` | `DetectedCI` | 56 | dataclass | 6 | `core/models/detected_c_i.py` |
| `src/core/services/pages/pipeline_scanner.py` | `PipelineScanResult` | 68 | dataclass | 6 | `core/models/pipeline_scan_result.py` |
| `src/core/services/pages/pipeline_scanner.py` | `_SCRIPT_PATTERNS` | 105 | List | 6 | `core/data/catalogs/pipeline_scanner_data.py` |
| `src/core/services/pages_builders/base.py` | `SegmentConfig` | 62 | dataclass | 6 | `core/models/segment_config.py` |
| `src/core/services/pages_builders/base.py` | `BuildResult` | 132 | dataclass | 6 | `core/models/build_result.py` |
| `src/core/services/pages_builders/template_engine.py` | `FEATURE_CATEGORIES` | 164 | List | 6 | `core/data/catalogs/template_engine_data.py` |
| `src/core/services/scripts/models.py` | `ScriptParameter` | 24 | dataclass | 6 | `core/models/script_parameter.py` |
| `src/core/services/scripts/registry.py` | `SHEBANG_LANGUAGES` | 31 | Dict | 6 | `core/data/catalogs/registry_data.py` |
| `src/core/services/tool_install/data/recipe_schema.py` | `VALID_FAMILIES` | 39 | Set | 6 | `core/data/catalogs/recipe_schema_data.py` |
| `src/core/services/tool_install/data/recipe_schema.py` | `VALID_BUILD_SYSTEMS` | 45 | Set | 6 | `core/data/catalogs/recipe_schema_data.py` |
| `src/core/services/audit/catalog.py` | `LibraryInfo` | 29 | TypedDict | 5 | `core/models/library_info.py` |
| `src/core/services/audit/models.py` | `AuditMeta` | 19 | TypedDict | 5 | `core/models/audit_meta.py` |
| `src/core/services/audit/models.py` | `OSInfo` | 62 | TypedDict | 5 | `core/models/o_s_info.py` |
| `src/core/services/audit/models.py` | `ToolInfo` | 87 | TypedDict | 5 | `core/models/tool_info.py` |
| `src/core/services/content/crypto.py` | `VIDEO_EXTS` | 71 | Set | 5 | `core/data/catalogs/file_extensions.py` |
| `src/core/services/content/crypto.py` | `AUDIO_EXTS` | 72 | Set | 5 | `core/data/catalogs/file_extensions.py` |
| `src/core/services/content/listing.py` | `DEFAULT_CONTENT_DIRS` | 20 | List | 5 | `core/data/catalogs/listing_data.py` |
| `src/core/services/k8s/validate_cluster.py` | `_LOCAL_CLUSTER_TYPES` | 17 | Set | 5 | `core/data/catalogs/types.py` |
| `src/core/services/k8s/validate_cross_domain.py` | `_TF_REGISTRY_RESOURCES` | 556 | Set | 5 | `core/data/catalogs/validate_cross_domain_data.py` |
| `src/core/services/k8s/validate_cross_domain.py` | `_TF_IAM_RESOURCES` | 736 | Set | 5 | `core/data/catalogs/validate_cross_domain_data.py` |
| `src/core/services/k8s/validate_cross_domain.py` | `_CI_SETUP_VERSION_ACTIONS` | 1179 | Dict | 5 | `core/data/catalogs/validate_cross_domain_data.py` |
| `src/core/services/k8s/validate_cross_resource.py` | `_WORKLOAD_KINDS` | 11 | Set | 5 | `core/data/catalogs/types.py` |
| `src/core/services/k8s/validate_security.py` | `_WORKLOAD_KINDS` | 14 | Set | 5 | `core/data/catalogs/types.py` |
| `src/core/services/k8s/validate_strategy.py` | `_WORKLOAD_KINDS` | 27 | Set | 5 | `core/data/catalogs/types.py` |
| `src/core/services/pages_builders/audit_directive.py` | `DirectiveMatch` | 45 | dataclass | 5 | `core/models/directive_match.py` |
| `src/core/services/peek.py` | `PeekCandidate` | 72 | dataclass | 5 | `core/models/peek_candidate.py` |
| `src/core/services/peek.py` | `PeekReference` | 82 | dataclass | 5 | `core/models/peek_reference.py` |
| `src/core/services/tool_install/resolver/method_selection.py` | `_NON_DERIVABLE_METHODS` | 260 | Set | 5 | `core/data/catalogs/method_selection_data.py` |
| `src/core/services/audit/models.py` | `ManifestInfo` | 107 | TypedDict | 4 | `core/models/manifest_info.py` |
| `src/core/services/audit/models.py` | `CrossoverInfo` | 138 | TypedDict | 4 | `core/models/crossover_info.py` |
| `src/core/services/audit/models.py` | `ComponentInfo` | 158 | TypedDict | 4 | `core/models/component_info.py` |
| `src/core/services/audit/narrative.py` | `Observation` | 23 | dataclass | 4 | `core/models/observation.py` |
| `src/core/services/audit/parsers/_rubrics.py` | `QualityDimension` | 31 | dataclass | 4 | `core/models/quality_dimension.py` |
| `src/core/services/changelog/models.py` | `ChangelogEntry` | 104 | dataclass | 4 | `core/models/changelog_entry.py` |
| `src/core/services/k8s/validate_cluster.py` | `_INFRA_REQUIREMENTS` | 20 | Dict | 4 | `core/data/catalogs/validate_cluster_data.py` |
| `src/core/services/k8s/validate_env_aware.py` | `_PROD_PATTERNS` | 16 | Set | 4 | `core/data/catalogs/validate_env_aware_data.py` |
| `src/core/services/k8s/validate_env_aware.py` | `_DEV_PATTERNS` | 18 | Set | 4 | `core/data/catalogs/validate_env_aware_data.py` |
| `src/core/services/pages_builders/audit_directive.py` | `AuditScope` | 97 | dataclass | 4 | `core/models/audit_scope.py` |
| `src/core/services/pages_builders/audit_directive.py` | `_STRENGTH_ORDER` | 406 | Dict | 4 | `core/data/catalogs/audit_directive_data.py` |
| `src/core/services/pages_builders/audit_directive.py` | `_SEV_EMOJI` | 941 | Dict | 4 | `core/data/catalogs/audit_directive_data.py` |
| `src/core/services/peek.py` | `_DOC_EXTS` | 50 | Set | 4 | `core/data/catalogs/file_extensions.py` |
| `src/core/services/peek.py` | `SymbolEntry` | 92 | dataclass | 4 | `core/models/symbol_entry.py` |
| `src/core/services/project_index.py` | `IndexSymbolEntry` | 71 | dataclass | 4 | `core/models/index_symbol_entry.py` |
| `src/core/services/scripts/registry.py` | `SCRIPT_EXTENSIONS` | 28 | Set | 4 | `core/data/catalogs/file_extensions.py` |
| `src/core/services/tool_install/data/recipe_schema.py` | `_OPTION_COMMON_REQUIRED` | 69 | Set | 4 | `core/data/catalogs/recipe_schema_data.py` |
| `src/core/services/artifacts/builders/base.py` | `ArtifactStageInfo` | 29 | dataclass | 3 | `core/models/artifact_stage_info.py` |
| `src/core/services/audit/l0_deep_detectors.py` | `_NETWORK_ENDPOINTS` | 160 | List | 3 | `core/data/catalogs/l0_deep_detectors_data.py` |
| `src/core/services/audit/models.py` | `EntrypointInfo` | 165 | TypedDict | 3 | `core/models/entrypoint_info.py` |
| `src/core/services/audit/models.py` | `ScoreBreakdownItem` | 208 | TypedDict | 3 | `core/models/score_breakdown_item.py` |
| `src/core/services/audit/models.py` | `AuditScores` | 219 | TypedDict | 3 | `core/models/audit_scores.py` |
| `src/core/services/audit/narrative.py` | `Recommendation` | 419 | dataclass | 3 | `core/models/recommendation.py` |
| `src/core/services/changelog/models.py` | `ChangelogSection` | 122 | dataclass | 3 | `core/models/changelog_section.py` |
| `src/core/services/changelog/models.py` | `Changelog` | 166 | dataclass | 3 | `core/models/changelog.py` |
| `src/core/services/detection.py` | `DetectionResult` | 26 | dataclass | 3 | `core/models/detection_result.py` |
| `src/core/services/k8s/validate_cross_domain.py` | `_TF_PROVIDER_REGISTRY_HINTS` | 565 | Dict | 3 | `core/data/catalogs/validate_cross_domain_data.py` |
| `src/core/services/k8s/validate_structural.py` | `_SCALABLE_KINDS` | 12 | Set | 3 | `core/data/catalogs/types.py` |
| `src/core/services/k8s/validate_structural.py` | `_VALID_CONCURRENCY_POLICIES` | 15 | Set | 3 | `core/data/catalogs/validate_structural_data.py` |
| `src/core/services/pages_builders/audit_directive.py` | `_SEVERITY_COLOR` | 949 | Dict | 3 | `core/data/catalogs/audit_directive_data.py` |
| `src/core/services/pages_builders/base.py` | `StageInfo` | 74 | dataclass | 3 | `core/models/stage_info.py` |
| `src/core/services/tool_install/data/recipe_schema.py` | `RECIPE_TYPES` | 30 | Set | 3 | `core/data/catalogs/types.py` |
| `src/core/services/tool_install/data/recipe_schema.py` | `_FIELDS_BY_TYPE` | 187 | Dict | 3 | `core/data/catalogs/types.py` |
| `src/core/services/tool_install/data/recipe_schema.py` | `_REQUIRED_BY_TYPE` | 194 | Dict | 3 | `core/data/catalogs/types.py` |
| `src/core/services/tool_install/data/remediation_handlers/constants.py` | `VALID_AVAILABILITY` | 25 | Set | 3 | `core/data/catalogs/constants_data.py` |
| `src/core/services/tool_install/domain/remediation_planning.py` | `_FALLBACK_ACTIONS` | 39 | List | 3 | `core/data/catalogs/remediation_planning_data.py` |
| `src/core/services/tool_install/domain/risk.py` | `_RISK_ORDER` | 17 | Dict | 3 | `core/data/catalogs/risk_data.py` |
| `src/core/services/vault/core.py` | `_RATE_LIMIT_TIERS` | 80 | List | 3 | `core/data/catalogs/core_data.py` |
| `src/core/services/audit/models.py` | `ScoreResult` | 214 | TypedDict | 2 | `core/models/score_result.py` |
| `src/core/services/chat/models.py` | `MessageFlags` | 40 | BaseModel | 2 | `core/models/message_flags.py` |

### core-usecases (4 definitions, 27 total items)

| File | Symbol | Line | Type | Items | Move to |
|------|--------|------|------|-------|---------|
| `src/core/use_cases/status.py` | `StatusResult` | 17 | dataclass | 9 | `core/models/status_result.py` |
| `src/core/use_cases/run.py` | `RunResult` | 35 | dataclass | 7 | `core/models/run_result.py` |
| `src/core/use_cases/detect.py` | `DetectResult` | 25 | dataclass | 6 | `core/models/detect_result.py` |
| `src/core/use_cases/config_check.py` | `ConfigCheckResult` | 15 | dataclass | 5 | `core/models/config_check_result.py` |

### core-reliability (3 definitions, 22 total items)

| File | Symbol | Line | Type | Items | Move to |
|------|--------|------|------|-------|---------|
| `src/core/reliability/circuit_breaker.py` | `CircuitBreaker` | 36 | dataclass | 10 | `core/models/circuit_breaker.py` |
| `src/core/reliability/retry_queue.py` | `RetryItem` | 22 | dataclass | 9 | `core/models/retry_item.py` |
| `src/core/reliability/circuit_breaker.py` | `CircuitBreakerRegistry` | 140 | dataclass | 3 | `core/models/circuit_breaker_registry.py` |

### core-observability (5 definitions, 16 total items)

| File | Symbol | Line | Type | Items | Move to |
|------|--------|------|------|-------|---------|
| `src/core/observability/health.py` | `ComponentHealth` | 23 | dataclass | 4 | `core/models/component_health.py` |
| `src/core/observability/health.py` | `SystemHealth` | 41 | dataclass | 3 | `core/models/system_health.py` |
| `src/core/observability/metrics.py` | `Counter` | 18 | dataclass | 3 | `core/models/counter.py` |
| `src/core/observability/metrics.py` | `Gauge` | 33 | dataclass | 3 | `core/models/gauge.py` |
| `src/core/observability/metrics.py` | `Histogram` | 54 | dataclass | 3 | `core/models/histogram.py` |

### ui-routes (1 definitions, 10 total items)

| File | Symbol | Line | Type | Items | Move to |
|------|--------|------|------|-------|---------|
| `src/ui/web/routes/audit/async_scan.py` | `ScanTask` | 44 | dataclass | 10 | `core/models/scan_task.py` |

### core-engine (2 definitions, 8 total items)

| File | Symbol | Line | Type | Items | Move to |
|------|--------|------|------|-------|---------|
| `src/core/engine/executor.py` | `ExecutionPlan` | 30 | dataclass | 4 | `core/models/execution_plan.py` |
| `src/core/engine/executor.py` | `ExecutionReport` | 44 | dataclass | 4 | `core/models/execution_report.py` |

### adapters (1 definitions, 6 total items)

| File | Symbol | Line | Type | Items | Move to |
|------|--------|------|------|-------|---------|
| `src/adapters/base.py` | `ExecutionContext` | 22 | BaseModel | 6 | `core/models/execution_context.py` |

## 🔄 Data Duplication Map

> Same or overlapping constants found in multiple files. These need a single canonical home.

### Group 1

| File | Symbol | Items |
|------|--------|-------|
| `src/core/services/content/crypto.py` | `CODE_EXTS` | 41 |
| `src/core/services/peek.py` | `_CODE_EXTS` | 41 |

> 💡 Suggested canonical home: `core/data/catalogs/file_extensions.py`

### Group 2

| File | Symbol | Items |
|------|--------|-------|
| `src/core/services/content/crypto.py` | `SCRIPT_EXTS` | 11 |
| `src/core/services/peek.py` | `_SCRIPT_EXTS` | 11 |

> 💡 Suggested canonical home: `core/data/catalogs/file_extensions.py`

### Group 3

| File | Symbol | Items |
|------|--------|-------|
| `src/core/services/content/crypto.py` | `CONFIG_EXTS` | 11 |
| `src/core/services/peek.py` | `_CONFIG_EXTS` | 11 |

> 💡 Suggested canonical home: `core/data/catalogs/file_extensions.py`

## 🟡 Import Direction Violations (Tier 3)

> Modules in higher layers importing directly from lower data layers.

### Boilerplate Patterns (many files, same import)

> These are structural — every CLI module imports the same config helper.

- **`src.core.config.loader`** (`find_project_file`) — 21 files import this
  - `src/ui/cli/audit/__init__.py`:L23
  - `src/ui/cli/backup/__init__.py`:L20
  - `src/ui/cli/ci/__init__.py`:L22
  - `src/ui/cli/content/__init__.py`:L24
  - `src/ui/cli/dns/__init__.py`:L20
  - … and 16 more
- **`src.core.config.loader`** (`load_project`) — 4 files import this
  - `src/ui/cli/ci/__init__.py`:L117
  - `src/ui/cli/ci/__init__.py`:L164
  - `src/ui/cli/ci/__init__.py`:L201
  - `src/ui/cli/quality/__init__.py`:L28
- **`src.core.config.stack_loader`** (`discover_stacks`) — 4 files import this
  - `src/ui/cli/ci/__init__.py`:L118
  - `src/ui/cli/ci/__init__.py`:L202
  - `src/ui/cli/quality/__init__.py`:L29
  - `src/ui/web/routes/api/stacks.py`:L15

### Individual Violations

| File | Line | Import | Names | From Layer | To Layer | Lazy? |
|------|------|--------|-------|-----------|----------|-------|
| `src/ui/web/routes/api/audit.py` | 15 | src.core.persistence.audit | AuditWriter | ui-routes | core-persistence | ✓ |

## 🟢 Lateral Service Coupling (Tier 4)

> Services importing from sibling service sub-packages.

**211** lateral imports across **104** unique pairs (13 import private symbols).

### Coupling Pairs (sorted by frequency)

| Source | → | Target | Imports | Private? |
|--------|---|--------|---------|----------|
| backup | → | content | 12 | ⚠️ |
| wizard | → | devops | 10 |  |
| pages | → | pages_builders | 7 |  |
| chat | → | ledger | 6 | ⚠️ |
| content | → | audit_helpers | 6 |  |
| metrics | → | devops | 6 |  |
| ci | → | generators | 5 | ⚠️ |
| artifacts | → | git | 4 |  |
| chat | → | content | 4 |  |
| docker | → | generators | 4 |  |
| k8s | → | audit_helpers | 4 |  |
| ledger | → | git_auth | 4 |  |
| pages_builders | → | config_ops | 4 |  |
| vault | → | audit_helpers | 4 |  |
| wizard | → | git_ops | 4 |  |
| audit | → | tool_install | 3 |  |
| backup | → | audit_helpers | 3 |  |
| git | → | tool_requirements | 3 |  |
| ledger | → | event_bus | 3 |  |
| secrets | → | audit_helpers | 3 |  |
| terraform | → | audit_helpers | 3 |  |
| tool_install | → | audit | 3 | ⚠️ |
| wizard | → | k8s | 3 | ⚠️ |
| wizard | → | pages | 3 |  |
| audit | → | devops | 2 | ⚠️ |
| chat | → | git | 2 |  |
| chat | → | run_tracker | 2 |  |
| chat | → | trace | 2 |  |
| chat | → | audit_staging | 2 |  |
| docker | → | audit_helpers | 2 |  |
| docker | → | tool_requirements | 2 |  |
| docs_svc | → | detection | 2 |  |
| ledger | → | git | 2 |  |
| metrics | → | detection | 2 |  |
| pages | → | config_ops | 2 |  |
| pages_builders | → | audit | 2 |  |
| scripts | → | stream_subprocess | 2 |  |
| security | → | devops | 2 |  |
| testing | → | audit_helpers | 2 |  |
| wizard | → | detection | 2 |  |
| wizard | → | terraform | 2 |  |
| wizard | → | dns | 2 |  |
| wizard | → | security | 2 |  |
| wizard | → | scripts | 2 |  |
| artifacts | → | detection | 1 |  |
| audit | → | detection | 1 |  |
| audit | → | security | 1 |  |
| audit | → | packages_svc | 1 |  |
| audit | → | docs_svc | 1 |  |
| audit | → | testing | 1 |  |
| audit | → | env | 1 |  |
| chat | → | event_bus | 1 |  |
| chat | → | devops | 1 |  |
| ci | → | audit_helpers | 1 |  |
| ci | → | detection | 1 |  |
| ci | → | tool_requirements | 1 |  |
| devops | → | event_bus | 1 |  |
| devops | → | audit_staging | 1 |  |
| dns | → | audit_helpers | 1 |  |
| dns | → | tool_requirements | 1 |  |
| docker | → | detection | 1 |  |
| docs_svc | → | tool_requirements | 1 |  |
| env | → | vault_io | 1 |  |
| env | → | audit_helpers | 1 |  |
| git | → | event_bus | 1 |  |
| git | → | terminal_ops | 1 |  |
| git | → | audit_helpers | 1 |  |
| k8s | → | tool_requirements | 1 |  |
| k8s | → | docker | 1 |  |
| k8s | → | ci_ops | 1 |  |
| k8s | → | terraform | 1 |  |
| metrics | → | git_ops | 1 |  |
| metrics | → | docker_ops | 1 |  |
| metrics | → | ci_ops | 1 |  |
| metrics | → | packages_svc | 1 |  |
| metrics | → | env | 1 |  |
| metrics | → | quality | 1 |  |
| packages_svc | → | tool_requirements | 1 |  |
| pages | → | smart_folders | 1 | ⚠️ |
| pages | → | audit_helpers | 1 |  |
| pages_builders | → | smart_folders | 1 | ⚠️ |
| pages_builders | → | devops | 1 | ⚠️ |
| pages_builders | → | ledger | 1 |  |
| pages_builders | → | peek | 1 |  |
| quality | → | tool_requirements | 1 |  |
| scripts | → | run_tracker | 1 |  |
| security | → | tool_requirements | 1 |  |
| security | → | vault | 1 |  |
| security | → | packages_svc | 1 |  |
| security | → | detection | 1 |  |
| security | → | audit_helpers | 1 |  |
| terraform | → | tool_requirements | 1 |  |
| testing | → | tool_requirements | 1 |  |
| tool_install | → | audit_helpers | 1 |  |
| trace | → | ledger | 1 |  |
| trace | → | event_bus | 1 |  |
| trace | → | chat | 1 |  |
| wizard | → | audit_helpers | 1 |  |
| wizard | → | project_probes | 1 |  |
| wizard | → | docker_ops | 1 |  |
| wizard | → | env | 1 |  |
| wizard | → | ci_ops | 1 |  |
| wizard | → | generators | 1 | ⚠️ |
| wizard | → | tool_install | 1 |  |

### Top Files by Lateral Import Count

| File | Lateral Imports | Targets |
|------|-----------------|---------|
| `src/core/services/wizard/helpers.py` | 15 | ci_ops, dns, docker_ops, env, git_ops, k8s, pages, scripts, security, terraform |
| `src/core/services/metrics/ops.py` | 14 | ci_ops, detection, devops, docker_ops, env, git_ops, packages_svc, quality |
| `src/core/services/chat/refs_autocomplete.py` | 8 | audit_staging, content, devops, ledger, run_tracker, trace |
| `src/core/services/ledger/worktree.py` | 8 | event_bus, git, git_auth |
| `src/core/services/pages_builders/audit_directive.py` | 8 | audit, config_ops, devops, ledger, smart_folders |
| `src/core/services/wizard/setup_infra.py` | 8 | devops, k8s, pages, terraform |
| `src/core/services/audit/l2_risk.py` | 7 | devops, docs_svc, env, packages_svc, security, testing |
| `src/core/services/chat/chat_ops.py` | 7 | event_bus, git, ledger |
| `src/core/services/ci/ops.py` | 6 | audit_helpers, detection, generators, tool_requirements |
| `src/core/services/docker/generate.py` | 6 | audit_helpers, detection, generators |

## Fix Checklist

> Ordered by impact. Each item is independent.

1. 🔄 **Deduplicate `src/core/services/content/crypto.py:CODE_EXTS` + `src/core/services/peek.py:_CODE_EXTS`**  
   Same data in multiple files — create single canonical source
2. 🔄 **Deduplicate `src/core/services/content/crypto.py:SCRIPT_EXTS` + `src/core/services/peek.py:_SCRIPT_EXTS`**  
   Same data in multiple files — create single canonical source
3. 🔄 **Deduplicate `src/core/services/content/crypto.py:CONFIG_EXTS` + `src/core/services/peek.py:_CONFIG_EXTS`**  
   Same data in multiple files — create single canonical source
4. 🔴 **Extract `src/core/services/audit/parsers/python_parser.py`:L48 (set, 94 items from _get_stdlib_modules())**  
   → move to core/data/
5. 🔴 **Extract `src/ui/web/routes/content/preview.py`:L227 (set, 24 items from content_preview_encrypted())**  
   → move to core/data/
6. 🔴 **Extract `src/ui/web/server.py`:L150 (set, 23 items from create_app())**  
   → move to core/data/
7. 🔴 **Extract `src/core/services/tool_install/detection/hardware.py`:L418 (dict, 13 items from detect_build_toolchain())**  
   → move to core/data/
8. 🔴 **Extract `src/ui/web/routes/tab_mesh/__init__.py`:L487 (list, 13 items from _clone_profile_to_debug_dir())**  
   → move to core/data/
9. 🟠 **Move `_COMMON_KEYWORDS` from `src/core/services/peek.py` (54 items)**  
   → `core/data/catalogs/code_keywords.py`
10. 🟠 **Move `_EXT_LANG_MAP` from `src/core/services/pages_builders/audit_directive.py` (45 items)**  
   → `core/data/catalogs/file_extensions.py`
11. 🟠 **Move `CODE_EXTS` from `src/core/services/content/crypto.py` (41 items)**  
   → `core/data/catalogs/file_extensions.py`
12. 🟠 **Move `_CODE_EXTS` from `src/core/services/peek.py` (41 items)**  
   → `core/data/catalogs/file_extensions.py`
13. 🟠 **Move `_COMMON_PASCAL` from `src/core/services/peek.py` (38 items)**  
   → `core/data/catalogs/peek_data.py`
14. 🟡 **Fix `src/ui/web/routes/api/audit.py`:L15 — imports `AuditWriter` from core-persistence**  
   → go through a service instead
