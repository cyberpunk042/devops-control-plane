# Code Hygiene Audit

> Generated: 2026-03-08 15:56 UTC  |  Style: **smart**

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Severity Tiers](#severity-tiers)
3. [Domain Analysis](#domain-analysis)
4. [Leaked Function Inventory](#leaked-function-inventory)
5. [Refactoring Impact](#refactoring-impact)
6. [Documentation Freshness Dashboard](#documentation-freshness-dashboard)
7. [Stale Reference Groups](#stale-reference-groups)
8. [Cross-Reference](#cross-reference)
9. [Fix Checklist](#fix-checklist)

## Executive Summary

> Your init hygiene is **fair** — 37/131 init files contain logic (3,454 lines). The worst offender is `src/ui/web/routes/tab_mesh/__init__.py` with 966 lines (28% of all init debt). Documentation freshness is **poor** at 67% — 13 stale references across 7 docs with code references.

| Metric | Value |
|--------|-------|
| Init files scanned | **131** |
| Clean init files | **94** (72%) |
| Init files with logic | **37** |
| Total leaked code lines | **3,454** |
| 🔧 Route handlers in init | **51** |
| ⌨️ CLI commands in init | **58** |
| 📋 Registration helpers | **8** |
| 🔩 Other functions | **46** |
| Leaked classes | **2** |
| Docs scanned | **121** |
| References found | **39** |
| Stale references | **13** |
| Doc freshness | **67%** |

## Severity Tiers

> Init files grouped by how much logic they contain, with function type breakdown.

### 🔴 Critical (12 files)

> ≥ 200 lines of init code

| File | Lines | Routes | CLI | Reg | Other | Migration |
|------|-------|--------|-----|-----|-------|-----------|
| `src/ui/web/routes/tab_mesh/__init__.py` | 966 | 9 | 0 | 0 | 13 | → split to route sub-modules |
| `src/core/data/__init__.py` | 298 | 0 | 0 | 1 | 2 | → move to registry.py |
| `src/core/services/audit/parsers/__init__.py` | 289 | 0 | 0 | 0 | 0 | → move class to own module |
| `src/ui/cli/docs/__init__.py` | 264 | 0 | 7 | 0 | 1 | → split to command sub-modules |
| `src/ui/web/routes/content/__init__.py` | 252 | 6 | 0 | 0 | 0 | → split to route sub-modules |
| `src/ui/cli/ci/__init__.py` | 236 | 0 | 7 | 0 | 3 | → split to command sub-modules |
| `src/ui/web/routes/smart_folders/__init__.py` | 232 | 5 | 0 | 0 | 1 | → split to route sub-modules |
| `src/ui/cli/dns/__init__.py` | 229 | 0 | 5 | 0 | 1 | → split to command sub-modules |
| `src/ui/web/routes/notifications/__init__.py` | 224 | 7 | 0 | 0 | 1 | → split to route sub-modules |
| `src/ui/cli/quality/__init__.py` | 221 | 0 | 9 | 0 | 2 | → split to command sub-modules |
| `src/ui/cli/packages/__init__.py` | 205 | 0 | 7 | 0 | 1 | → split to command sub-modules |
| `src/ui/web/routes/devops/__init__.py` | 203 | 5 | 0 | 0 | 1 | → split to route sub-modules |

### 🟡 Major (12 files)

> 50–199 lines of init code

| File | Lines | Routes | CLI | Reg | Other | Migration |
|------|-------|--------|-----|-----|-------|-----------|
| `src/ui/cli/metrics/__init__.py` | 197 | 0 | 4 | 0 | 1 | → split to command sub-modules |
| `src/ui/cli/backup/__init__.py` | 196 | 0 | 6 | 0 | 1 | → split to command sub-modules |
| `src/ui/web/routes/server/__init__.py` | 89 | 4 | 0 | 0 | 0 | → split to route sub-modules |
| `src/ui/web/routes/dev/__init__.py` | 86 | 3 | 0 | 0 | 0 | → split to route sub-modules |
| `src/ui/web/routes/config/__init__.py` | 85 | 3 | 0 | 0 | 1 | → split to route sub-modules |
| `src/ui/web/routes/dns/__init__.py` | 80 | 4 | 0 | 0 | 0 | → split to route sub-modules |
| `src/core/services/pages_builders/__init__.py` | 74 | 0 | 0 | 3 | 0 | → move to registry.py |
| `src/ui/web/routes/events/__init__.py` | 69 | 1 | 0 | 0 | 0 | → split to route sub-modules |
| `src/ui/web/routes/backup/__init__.py` | 67 | 2 | 0 | 0 | 0 | → split to route sub-modules |
| `src/ui/web/routes/project/__init__.py` | 67 | 2 | 0 | 0 | 1 | → split to route sub-modules |
| `src/ui/cli/infra/__init__.py` | 55 | 0 | 1 | 0 | 2 | → refactor to sub-modules |
| `src/core/services/artifacts/publishers/__init__.py` | 50 | 0 | 0 | 3 | 0 | → move to registry.py |

### 🟢 Minor (13 files)

> < 50 lines of init code

| File | Lines | Routes | CLI | Reg | Other | Migration |
|------|-------|--------|-----|-----|-------|-----------|
| `src/ui/cli/security/__init__.py` | 46 | 0 | 1 | 0 | 2 | → refactor to sub-modules |
| `src/core/services/artifacts/builders/__init__.py` | 43 | 0 | 0 | 1 | 0 | → move to registry.py |
| `src/ui/cli/vault/__init__.py` | 42 | 0 | 1 | 0 | 2 | → refactor to sub-modules |
| `src/ui/cli/pages/__init__.py` | 36 | 0 | 1 | 0 | 1 | → split to command sub-modules |
| `src/ui/cli/content/__init__.py` | 35 | 0 | 1 | 0 | 1 | → split to command sub-modules |
| `src/ui/cli/docker/__init__.py` | 35 | 0 | 1 | 0 | 1 | → split to command sub-modules |
| `src/ui/cli/k8s/__init__.py` | 35 | 0 | 1 | 0 | 1 | → split to command sub-modules |
| `src/ui/cli/scripts/__init__.py` | 35 | 0 | 1 | 0 | 1 | → split to command sub-modules |
| `src/ui/cli/terraform/__init__.py` | 35 | 0 | 1 | 0 | 1 | → split to command sub-modules |
| `src/ui/cli/audit/__init__.py` | 34 | 0 | 1 | 0 | 1 | → split to command sub-modules |
| `src/ui/cli/git/__init__.py` | 34 | 0 | 1 | 0 | 1 | → split to command sub-modules |
| `src/ui/cli/secrets/__init__.py` | 34 | 0 | 1 | 0 | 1 | → split to command sub-modules |
| `src/ui/cli/testing/__init__.py` | 34 | 0 | 1 | 0 | 1 | → split to command sub-modules |

## Domain Analysis

> Init files grouped by architectural layer — shows where logic leaks concentrate.

### ⌨️ CLI Commands (20 files, 84 functions, 2038 lines)

> ℹ️ **Pattern**: 13/20 files follow the `_resolve_project_root + group` boilerplate (37 lines avg). This is structural, not accidental.

| File | Lines | Type | Top Functions |
|------|-------|------|---------------|
| `src/ui/cli/quality/__init__.py` | 221 | 9 CLI commands | check, status, gen_config (+8) |
| `src/ui/cli/ci/__init__.py` | 236 | 7 CLI commands | workflows, coverage, status (+7) |
| `src/ui/cli/docs/__init__.py` | 264 | 7 CLI commands | status, links, gen_changelog (+5) |
| `src/ui/cli/packages/__init__.py` | 205 | 7 CLI commands | audit, status, outdated (+5) |
| `src/ui/cli/backup/__init__.py` | 196 | 6 CLI commands | create, preview, list_backups_cmd (+4) |
| `src/ui/cli/dns/__init__.py` | 229 | 5 CLI commands | status, generate, lookup (+3) |
| `src/ui/cli/metrics/__init__.py` | 197 | 4 CLI commands | health, report, summary (+2) |
| `src/ui/cli/infra/__init__.py` | 55 | 1 CLI, 2 other | _handle_generated, _resolve_project_root, infra |
| `src/ui/cli/security/__init__.py` | 46 | 1 CLI, 2 other | _detect_stack_names, _resolve_project_root, security |
| `src/ui/cli/vault/__init__.py` | 42 | 1 CLI, 2 other | _resolve_project_root, _env_path, vault |
| `src/ui/cli/audit/__init__.py` | 34 | 1 CLI commands | _resolve_project_root, audit |
| `src/ui/cli/content/__init__.py` | 35 | 1 CLI commands | _resolve_project_root, content |
| `src/ui/cli/docker/__init__.py` | 35 | 1 CLI commands | _resolve_project_root, docker |
| `src/ui/cli/git/__init__.py` | 34 | 1 CLI commands | _resolve_project_root, git |
| `src/ui/cli/k8s/__init__.py` | 35 | 1 CLI commands | _resolve_project_root, k8s |
| `src/ui/cli/pages/__init__.py` | 36 | 1 CLI commands | _resolve_project_root, pages |
| `src/ui/cli/scripts/__init__.py` | 35 | 1 CLI commands | _resolve_project_root, scripts |
| `src/ui/cli/secrets/__init__.py` | 34 | 1 CLI commands | _resolve_project_root, secrets |
| `src/ui/cli/terraform/__init__.py` | 35 | 1 CLI commands | _resolve_project_root, terraform |
| `src/ui/cli/testing/__init__.py` | 34 | 1 CLI commands | _resolve_project_root, testing |

### 🌐 Web Routes (12 files, 69 functions, 2420 lines)

| File | Lines | Type | Top Functions |
|------|-------|------|---------------|
| `src/ui/web/routes/tab_mesh/__init__.py` | 966 | 9 routes, 13 other | restart_chrome, cdp_diagnose, _modify_shortcut (+19) |
| `src/ui/web/routes/notifications/__init__.py` | 224 | 7 route handlers | list_notifications, log_frontend_error, list_errors (+5) |
| `src/ui/web/routes/content/__init__.py` | 252 | 6 route handlers | content_list, content_metadata, content_encrypt (+3) |
| `src/ui/web/routes/devops/__init__.py` | 203 | 5 route handlers | _ensure_registry, devops_cache_bust, integration_prefs_put (+3) |
| `src/ui/web/routes/smart_folders/__init__.py` | 232 | 5 route handlers | api_smart_folders_file, api_smart_folders_discover, api_smart_folders_list (+3) |
| `src/ui/web/routes/config/__init__.py` | 85 | 3 route handlers | api_config_save, api_config_content_folders, api_config_read (+1) |
| `src/ui/web/routes/dns/__init__.py` | 80 | 4 route handlers | dns_generate, dns_status, dns_lookup (+1) |
| `src/ui/web/routes/server/__init__.py` | 89 | 4 route handlers | server_settings_put, server_restart_route, server_status_route (+1) |
| `src/ui/web/routes/dev/__init__.py` | 86 | 3 route handlers | dev_scenarios, dev_status, dev_scenario_by_id |
| `src/ui/web/routes/project/__init__.py` | 67 | 2 route handlers | project_next, project_status, _root |
| `src/ui/web/routes/backup/__init__.py` | 67 | 2 route handlers | api_folder_tree, api_folders |
| `src/ui/web/routes/events/__init__.py` | 69 | 1 route handlers | event_stream |

### ⚙️ Core Services (4 files, 7 functions, 456 lines)

| File | Lines | Type | Top Functions |
|------|-------|------|---------------|
| `src/core/services/artifacts/publishers/__init__.py` | 50 | 3 registration helpers | _register_defaults, get_publisher, list_publishers |
| `src/core/services/pages_builders/__init__.py` | 74 | 3 registration helpers | list_builders, _register_defaults, get_builder |
| `src/core/services/artifacts/builders/__init__.py` | 43 | 1 registration helpers | get_builder |
| `src/core/services/audit/parsers/__init__.py` | 289 | 1 class |  |

### 💾 Core Data (1 files, 3 functions, 298 lines)

| File | Lines | Type | Top Functions |
|------|-------|------|---------------|
| `src/core/data/__init__.py` | 298 | 1 reg, 2 other | classify_key, get_registry, _load_json |

## Leaked Function Inventory

> Every function and class defined in non-clean init files. Grouped by file, sorted by body size. Only files with ≥ 50 lines shown (smaller files are in severity tiers).

### `src/ui/web/routes/tab_mesh/__init__.py` (966 lines, 22 functions)

| Function | Lines | Type | Decorators |
|----------|-------|------|------------|
| `restart_chrome` | 87 | route handler | route |
| `cdp_diagnose` | 83 | route handler | route |
| `_modify_shortcut` | 82 | utility | — |
| `_clone_profile_to_debug_dir` | 82 | utility | — |
| `trigger_chrome_signin` | 77 | route handler | route |
| `cdp_remediate` | 72 | route handler | route |
| `discover_target` | 67 | route handler | route |
| `_modify_shortcut_elevated` | 53 | utility | — |
| `focus_tab` | 52 | route handler | route |
| `_read_shortcut` | 32 | utility | — |
| `suggest_cdp` | 29 | route handler | route |
| `kill_chrome` | 25 | route handler | route |
| `cdp_status` | 24 | route handler | route |
| `_read_chrome_profiles` | 23 | utility | — |
| `_shortcut_locations` | 17 | trivial | — |
| `_get_chrome_version` | 16 | utility | — |
| `_get_windows_user` | 14 | utility | — |
| `_chrome_debug_data_dir_win` | 8 | trivial | — |
| `_is_wsl` | 7 | utility | — |
| `_wsl_to_win_path` | 4 | utility | — |
| `_chrome_data_dir` | 2 | trivial | — |
| `_chrome_data_dir_win` | 2 | trivial | — |

### `src/core/data/__init__.py` (298 lines, 3 functions, 1 class)

| Function | Lines | Type | Decorators |
|----------|-------|------|------------|
| `classify_key` | 12 | utility | — |
| `get_registry` | 10 | registration | — |
| `_load_json` | 7 | utility | — |

| class `DataRegistry` | 220 | class (23 methods) | — |

### `src/core/services/audit/parsers/__init__.py` (289 lines, 0 functions, 1 class)


| class `ParserRegistry` | 193 | class (12 methods) | — |

### `src/ui/cli/docs/__init__.py` (264 lines, 8 functions)

| Function | Lines | Type | Decorators |
|----------|-------|------|------------|
| `status` | 63 | CLI command | command, option, pass_context |
| `links` | 37 | CLI command | command, option, option, pass_context |
| `gen_changelog` | 33 | CLI command | command, option, option, option, pass_context |
| `coverage` | 30 | CLI command | command, option, pass_context |
| `gen_readme` | 26 | CLI command | command, option, pass_context |
| `_resolve_project_root` | 7 | utility | — |
| `docs` | 1 | CLI command | group |
| `generate` | 1 | CLI command | group |

### `src/ui/web/routes/content/__init__.py` (252 lines, 6 functions)

| Function | Lines | Type | Decorators |
|----------|-------|------|------------|
| `content_list` | 57 | route handler | route |
| `content_metadata` | 21 | route handler | route |
| `content_encrypt` | 19 | route handler | route, run_tracked |
| `content_decrypt` | 19 | route handler | route, run_tracked |
| `content_folders` | 15 | route handler | route |
| `content_all_folders` | 5 | route handler | route |

### `src/ui/cli/ci/__init__.py` (236 lines, 10 functions)

| Function | Lines | Type | Decorators |
|----------|-------|------|------------|
| `workflows` | 36 | CLI command | command, option, pass_context |
| `coverage` | 32 | CLI command | command, option, pass_context |
| `status` | 20 | CLI command | command, option, pass_context |
| `gen_ci` | 17 | CLI command | command, option, pass_context |
| `_detect_stack_names` | 17 | utility | — |
| `_handle_generated` | 17 | utility | — |
| `gen_lint` | 14 | CLI command | command, option, pass_context |
| `_resolve_project_root` | 7 | utility | — |
| `ci` | 1 | CLI command | group |
| `generate` | 1 | CLI command | group |

### `src/ui/web/routes/smart_folders/__init__.py` (232 lines, 6 functions)

| Function | Lines | Type | Decorators |
|----------|-------|------|------------|
| `api_smart_folders_file` | 42 | route handler | route |
| `api_smart_folders_discover` | 41 | route handler | route |
| `api_smart_folders_list` | 35 | route handler | route |
| `api_smart_folders_peek` | 34 | route handler | route |
| `api_smart_folders_tree` | 12 | route handler | route |
| `_load_config` | 2 | trivial | — |

### `src/ui/cli/dns/__init__.py` (229 lines, 6 functions)

| Function | Lines | Type | Decorators |
|----------|-------|------|------------|
| `status` | 51 | CLI command | command, option, pass_context |
| `generate` | 46 | CLI command | command, argument, option, option, option, option, option, option |
| `lookup` | 39 | CLI command | command, argument, option |
| `ssl` | 27 | CLI command | command, argument, option |
| `_resolve_project_root` | 7 | utility | — |
| `dns` | 1 | CLI command | group |

### `src/ui/web/routes/notifications/__init__.py` (224 lines, 8 functions)

| Function | Lines | Type | Decorators |
|----------|-------|------|------------|
| `list_notifications` | 32 | route handler | route |
| `log_frontend_error` | 31 | route handler | route |
| `list_errors` | 28 | route handler | route |
| `dismiss` | 22 | route handler | route |
| `badge` | 19 | route handler | route |
| `delete` | 13 | route handler | route |
| `ack` | 10 | route handler | route |
| `_root` | 2 | trivial | — |

### `src/ui/cli/quality/__init__.py` (221 lines, 11 functions)

| Function | Lines | Type | Decorators |
|----------|-------|------|------------|
| `check` | 43 | CLI command | command, option, option, option, option, pass_context |
| `status` | 36 | CLI command | command, option, pass_context |
| `gen_config` | 28 | CLI command | command, argument, option, pass_context |
| `_detect_stack_names` | 17 | utility | — |
| `_resolve_project_root` | 7 | utility | — |
| `lint` | 2 | CLI command | command, option, pass_context |
| `typecheck` | 2 | CLI command | command, pass_context |
| `test` | 2 | CLI command | command, pass_context |
| `fmt` | 2 | CLI command | command, option, pass_context |
| `quality` | 1 | CLI command | group |
| `generate` | 1 | CLI command | group |

### `src/ui/cli/packages/__init__.py` (205 lines, 8 functions)

| Function | Lines | Type | Decorators |
|----------|-------|------|------------|
| `audit` | 30 | CLI command | command, option, option, pass_context |
| `status` | 25 | CLI command | command, option, pass_context |
| `outdated` | 25 | CLI command | command, option, option, pass_context |
| `list_packages` | 21 | CLI command | command, option, option, pass_context |
| `update` | 14 | CLI command | command, argument, option, pass_context |
| `install` | 13 | CLI command | command, option, pass_context |
| `_resolve_project_root` | 7 | utility | — |
| `packages` | 1 | CLI command | group |

### `src/ui/web/routes/devops/__init__.py` (203 lines, 6 functions)

| Function | Lines | Type | Decorators |
|----------|-------|------|------------|
| `_ensure_registry` | 64 | utility | — |
| `devops_cache_bust` | 36 | route handler | route |
| `integration_prefs_put` | 10 | route handler | route |
| `devops_prefs_put` | 6 | route handler | route |
| `integration_prefs_get` | 4 | route handler | route |
| `devops_prefs_get` | 2 | route handler | route |

### `src/ui/cli/metrics/__init__.py` (197 lines, 5 functions)

| Function | Lines | Type | Decorators |
|----------|-------|------|------------|
| `health` | 85 | CLI command | command, option, pass_context |
| `report` | 47 | CLI command | command, pass_context |
| `summary` | 21 | CLI command | command, option, pass_context |
| `_resolve_project_root` | 7 | utility | — |
| `metrics` | 1 | CLI command | group |

### `src/ui/cli/backup/__init__.py` (196 lines, 7 functions)

| Function | Lines | Type | Decorators |
|----------|-------|------|------------|
| `create` | 51 | CLI command | command, argument, argument, option, option, option, option, option, pass_context |
| `preview` | 27 | CLI command | command, argument, option, pass_context |
| `list_backups_cmd` | 22 | CLI command | command, argument, option, option, pass_context |
| `folders` | 18 | CLI command | command, option, pass_context |
| `delete` | 11 | CLI command | command, argument, pass_context |
| `_resolve_project_root` | 7 | utility | — |
| `backup` | 1 | CLI command | group |

### `src/ui/web/routes/server/__init__.py` (89 lines, 4 functions)

| Function | Lines | Type | Decorators |
|----------|-------|------|------------|
| `server_settings_put` | 25 | route handler | route |
| `server_restart_route` | 23 | route handler | route |
| `server_status_route` | 5 | route handler | route |
| `server_settings_get` | 5 | route handler | route |

### `src/ui/web/routes/dev/__init__.py` (86 lines, 3 functions)

| Function | Lines | Type | Decorators |
|----------|-------|------|------------|
| `dev_scenarios` | 32 | route handler | route |
| `dev_status` | 15 | route handler | route |
| `dev_scenario_by_id` | 14 | route handler | route |

### `src/ui/web/routes/config/__init__.py` (85 lines, 4 functions)

| Function | Lines | Type | Decorators |
|----------|-------|------|------------|
| `api_config_save` | 15 | route handler | route, run_tracked |
| `api_config_content_folders` | 11 | route handler | route |
| `api_config_read` | 7 | route handler | route |
| `_config_path` | 6 | utility | — |

### `src/ui/web/routes/dns/__init__.py` (80 lines, 4 functions)

| Function | Lines | Type | Decorators |
|----------|-------|------|------------|
| `dns_generate` | 17 | route handler | route, run_tracked |
| `dns_status` | 10 | route handler | route |
| `dns_lookup` | 5 | route handler | route |
| `dns_ssl` | 5 | route handler | route |

### `src/core/services/pages_builders/__init__.py` (74 lines, 3 functions)

| Function | Lines | Type | Decorators |
|----------|-------|------|------------|
| `list_builders` | 10 | registration | — |
| `_register_defaults` | 4 | registration | — |
| `get_builder` | 4 | registration | — |

### `src/ui/web/routes/events/__init__.py` (69 lines, 1 function)

| Function | Lines | Type | Decorators |
|----------|-------|------|------------|
| `event_stream` | 37 | route handler | route |

### `src/ui/web/routes/backup/__init__.py` (67 lines, 2 functions)

| Function | Lines | Type | Decorators |
|----------|-------|------|------------|
| `api_folder_tree` | 4 | route handler | route |
| `api_folders` | 3 | route handler | route |

### `src/ui/web/routes/project/__init__.py` (67 lines, 3 functions)

| Function | Lines | Type | Decorators |
|----------|-------|------|------------|
| `project_next` | 14 | route handler | route |
| `project_status` | 13 | route handler | route |
| `_root` | 1 | trivial | — |

### `src/ui/cli/infra/__init__.py` (55 lines, 3 functions)

| Function | Lines | Type | Decorators |
|----------|-------|------|------------|
| `_handle_generated` | 17 | utility | — |
| `_resolve_project_root` | 7 | utility | — |
| `infra` | 1 | CLI command | group |

### `src/core/services/artifacts/publishers/__init__.py` (50 lines, 3 functions)

| Function | Lines | Type | Decorators |
|----------|-------|------|------------|
| `_register_defaults` | 13 | registration | — |
| `get_publisher` | 10 | registration | — |
| `list_publishers` | 3 | registration | — |

## Refactoring Impact

> If you fix these files, here's the impact on your init debt.

| Priority | File | Lines | % of Debt | Cumulative |
|----------|------|-------|-----------|------------|
| 1 | `src/ui/web/routes/tab_mesh/__init__.py` | 966 | 28.0% | 28.0% |
| 2 | `src/core/data/__init__.py` | 298 | 8.6% | 36.6% |
| 3 | `src/core/services/audit/parsers/__init__.py` | 289 | 8.4% | 45.0% |
| 4 | `src/ui/cli/docs/__init__.py` | 264 | 7.6% | 52.6% |
| 5 | `src/ui/web/routes/content/__init__.py` | 252 | 7.3% | 59.9% |
| 6 | `src/ui/cli/ci/__init__.py` | 236 | 6.8% | 66.7% |
| 7 | `src/ui/web/routes/smart_folders/__init__.py` | 232 | 6.7% | 73.5% |
| 8 | `src/ui/cli/dns/__init__.py` | 229 | 6.6% | 80.1% |
| 9 | `src/ui/web/routes/notifications/__init__.py` | 224 | 6.5% | 86.6% |
| 10 | `src/ui/cli/quality/__init__.py` | 221 | 6.4% | 93.0% |

> 📊 **Fixing the top 3 files eliminates 45% of all init debt.** Top 5 eliminates 60%.

## Documentation Freshness Dashboard

> Freshness of documents containing code references.  
> **Note**: Audit output files (`docs/audits/`) are excluded to avoid self-referential noise.

📚 **Overall**: `█████████████░░░░░░░` 66.7% (26/39 valid)

### Trust Tiers

| Tier | Docs | Status |
|------|------|--------|
| ✅ Trustworthy (100%) | 4 | All references valid |
| ⚠️ Mostly OK (≥80%) | 0 | Minor staleness |
| 🔴 Unreliable (<80%) | 3 | Significant staleness |

### Per-Document Freshness

`docs/PAGES.md`: `░░░░░░░░░░░░░░░░░░░░` 0% — ⚠️ 6 stale
`docs/DEVELOPMENT.md`: `█████████████░░░░░░░` 67% — ⚠️ 1 stale
`docs/CONSOLIDATION_AUDIT.md`: `██████████████░░░░░░` 71% — ⚠️ 6 stale

## Stale Reference Groups

> Stale references grouped by root cause. Multiple references to the same missing target are collapsed.

### `src/core/services/pages_builders/mybuilder.py` (6 refs across 1 doc)

> File does not exist

- `docs/PAGES.md` — L208, L210, L210, L210, L210, L211

### `src/core/services/content_crypto.py` (2 refs across 1 doc)

> File does not exist

- `docs/CONSOLIDATION_AUDIT.md` — L25, L273

### `src/core/services/content_release.py` (2 refs across 1 doc)

> File does not exist

- `docs/CONSOLIDATION_AUDIT.md` — L34, L276

### `src/core/services/content_optimize.py` (1 ref across 1 doc)

> File does not exist

- `docs/CONSOLIDATION_AUDIT.md` — L274

### `src/core/services/content_optimize_video.py` (1 ref across 1 doc)

> File does not exist

- `docs/CONSOLIDATION_AUDIT.md` — L275

### `tests/test_cli_mydomain.py` (1 ref across 1 doc)

> File does not exist

- `docs/DEVELOPMENT.md` — L149

## Cross-Reference

> Areas where init leaks and stale documentation overlap — potential hotspots for cleanup.

### `src/core/services/pages_builders/__init__.py`

- **Init issue**: 74 lines, 3 functions (3 registration helpers)
- **Stale doc**: `docs/PAGES.md` — 1 stale ref

## Fix Checklist

> Ordered by impact. Each item is independent — fix any one without the others.

1. 🔴 **Split `src/ui/web/routes/tab_mesh/__init__.py`** (966L, 9 routes, 13 other)  
   → split to route sub-modules  
   Impact: eliminates 28% of init debt
2. 🔴 **Split `src/core/data/__init__.py`** (298L, 1 reg, 2 other)  
   → move to registry.py  
   Impact: eliminates 9% of init debt
3. 🔴 **Split `src/core/services/audit/parsers/__init__.py`** (289L, 1 class)  
   → move class to own module  
   Impact: eliminates 8% of init debt
4. 🔴 **Split `src/ui/cli/docs/__init__.py`** (264L, 7 CLI commands)  
   → split to command sub-modules  
   Impact: eliminates 8% of init debt
5. 🔴 **Split `src/ui/web/routes/content/__init__.py`** (252L, 6 route handlers)  
   → split to route sub-modules  
   Impact: eliminates 7% of init debt
6. 🟡 **Update `docs/CONSOLIDATION_AUDIT.md`** (6 stale refs)  
   Update or remove broken code references
7. 🟡 **Update `docs/PAGES.md`** (6 stale refs)  
   Update or remove broken code references
8. 🟡 **Update `docs/DEVELOPMENT.md`** (1 stale ref)  
   Update or remove broken code references
