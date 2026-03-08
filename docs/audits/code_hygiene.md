# Code Hygiene Audit

> Generated: 2026-03-08 15:40 UTC  |  Style: **smart**

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Severity Tiers](#severity-tiers)
3. [Domain Analysis](#domain-analysis)
4. [Documentation Freshness Dashboard](#documentation-freshness-dashboard)
5. [Cross-Reference](#cross-reference)

## Executive Summary

| Metric | Value |
|--------|-------|
| Init files scanned | **131** |
| Clean init files | **94** (72%) |
| Init files with logic | **37** |
| Leaked functions | **163** |
| Leaked classes | **2** |
| Total leaked code lines | **3454** |
| Docs scanned | **123** |
| References found | **151** |
| Stale references | **39** |
| Doc freshness | **74%** |

## Severity Tiers

> Init files grouped by how much logic they contain. This is a **size observation**, not a judgment.

### 🔴 Critical (12 files)

> ≥ 200 lines of init code

| File | Total Lines | Functions | Classes |
|------|-----------|-----------|---------|
| `src/ui/web/routes/tab_mesh/__init__.py` | 966 | 22 | 0 |
| `src/core/data/__init__.py` | 298 | 3 | 1 |
| `src/core/services/audit/parsers/__init__.py` | 289 | 0 | 1 |
| `src/ui/cli/docs/__init__.py` | 264 | 8 | 0 |
| `src/ui/web/routes/content/__init__.py` | 252 | 6 | 0 |
| `src/ui/cli/ci/__init__.py` | 236 | 10 | 0 |
| `src/ui/web/routes/smart_folders/__init__.py` | 232 | 6 | 0 |
| `src/ui/cli/dns/__init__.py` | 229 | 6 | 0 |
| `src/ui/web/routes/notifications/__init__.py` | 224 | 8 | 0 |
| `src/ui/cli/quality/__init__.py` | 221 | 11 | 0 |
| `src/ui/cli/packages/__init__.py` | 205 | 8 | 0 |
| `src/ui/web/routes/devops/__init__.py` | 203 | 6 | 0 |

### 🟡 Major (12 files)

> 50–199 lines of init code

| File | Total Lines | Functions | Classes |
|------|-----------|-----------|---------|
| `src/ui/cli/metrics/__init__.py` | 197 | 5 | 0 |
| `src/ui/cli/backup/__init__.py` | 196 | 7 | 0 |
| `src/ui/web/routes/server/__init__.py` | 89 | 4 | 0 |
| `src/ui/web/routes/dev/__init__.py` | 86 | 3 | 0 |
| `src/ui/web/routes/config/__init__.py` | 85 | 4 | 0 |
| `src/ui/web/routes/dns/__init__.py` | 80 | 4 | 0 |
| `src/core/services/pages_builders/__init__.py` | 74 | 3 | 0 |
| `src/ui/web/routes/events/__init__.py` | 69 | 1 | 0 |
| `src/ui/web/routes/backup/__init__.py` | 67 | 2 | 0 |
| `src/ui/web/routes/project/__init__.py` | 67 | 3 | 0 |
| `src/ui/cli/infra/__init__.py` | 55 | 3 | 0 |
| `src/core/services/artifacts/publishers/__init__.py` | 50 | 3 | 0 |

### 🟢 Minor (13 files)

> < 50 lines of init code

| File | Total Lines | Functions | Classes |
|------|-----------|-----------|---------|
| `src/ui/cli/security/__init__.py` | 46 | 3 | 0 |
| `src/core/services/artifacts/builders/__init__.py` | 43 | 1 | 0 |
| `src/ui/cli/vault/__init__.py` | 42 | 3 | 0 |
| `src/ui/cli/pages/__init__.py` | 36 | 2 | 0 |
| `src/ui/cli/content/__init__.py` | 35 | 2 | 0 |
| `src/ui/cli/docker/__init__.py` | 35 | 2 | 0 |
| `src/ui/cli/k8s/__init__.py` | 35 | 2 | 0 |
| `src/ui/cli/scripts/__init__.py` | 35 | 2 | 0 |
| `src/ui/cli/terraform/__init__.py` | 35 | 2 | 0 |
| `src/ui/cli/audit/__init__.py` | 34 | 2 | 0 |
| `src/ui/cli/git/__init__.py` | 34 | 2 | 0 |
| `src/ui/cli/secrets/__init__.py` | 34 | 2 | 0 |
| `src/ui/cli/testing/__init__.py` | 34 | 2 | 0 |

## Domain Analysis

> Init files grouped by architectural layer — shows where logic leaks concentrate.

### ⌨️ CLI Commands (20 files, 84 functions, 2038 lines)

| File | Lines | Funcs | Top Functions |
|------|-------|-------|---------------|
| `src/ui/cli/quality/__init__.py` | 221 | 11 | check, status, gen_config (+8) |
| `src/ui/cli/ci/__init__.py` | 236 | 10 | workflows, coverage, status (+7) |
| `src/ui/cli/docs/__init__.py` | 264 | 8 | status, links, gen_changelog (+5) |
| `src/ui/cli/packages/__init__.py` | 205 | 8 | audit, status, outdated (+5) |
| `src/ui/cli/backup/__init__.py` | 196 | 7 | create, preview, list_backups_cmd (+4) |
| `src/ui/cli/dns/__init__.py` | 229 | 6 | status, generate, lookup (+3) |
| `src/ui/cli/metrics/__init__.py` | 197 | 5 | health, report, summary (+2) |
| `src/ui/cli/infra/__init__.py` | 55 | 3 | _handle_generated, _resolve_project_root, infra |
| `src/ui/cli/security/__init__.py` | 46 | 3 | _detect_stack_names, _resolve_project_root, security |
| `src/ui/cli/vault/__init__.py` | 42 | 3 | _resolve_project_root, _env_path, vault |
| `src/ui/cli/audit/__init__.py` | 34 | 2 | _resolve_project_root, audit |
| `src/ui/cli/content/__init__.py` | 35 | 2 | _resolve_project_root, content |
| `src/ui/cli/docker/__init__.py` | 35 | 2 | _resolve_project_root, docker |
| `src/ui/cli/git/__init__.py` | 34 | 2 | _resolve_project_root, git |
| `src/ui/cli/k8s/__init__.py` | 35 | 2 | _resolve_project_root, k8s |
| `src/ui/cli/pages/__init__.py` | 36 | 2 | _resolve_project_root, pages |
| `src/ui/cli/scripts/__init__.py` | 35 | 2 | _resolve_project_root, scripts |
| `src/ui/cli/secrets/__init__.py` | 34 | 2 | _resolve_project_root, secrets |
| `src/ui/cli/terraform/__init__.py` | 35 | 2 | _resolve_project_root, terraform |
| `src/ui/cli/testing/__init__.py` | 34 | 2 | _resolve_project_root, testing |

### 🌐 Web Routes (12 files, 69 functions, 2420 lines)

| File | Lines | Funcs | Top Functions |
|------|-------|-------|---------------|
| `src/ui/web/routes/tab_mesh/__init__.py` | 966 | 22 | restart_chrome, cdp_diagnose, _modify_shortcut (+19) |
| `src/ui/web/routes/notifications/__init__.py` | 224 | 8 | list_notifications, log_frontend_error, list_errors (+5) |
| `src/ui/web/routes/content/__init__.py` | 252 | 6 | content_list, content_metadata, content_encrypt (+3) |
| `src/ui/web/routes/devops/__init__.py` | 203 | 6 | _ensure_registry, devops_cache_bust, integration_prefs_put (+3) |
| `src/ui/web/routes/smart_folders/__init__.py` | 232 | 6 | api_smart_folders_file, api_smart_folders_discover, api_smart_folders_list (+3) |
| `src/ui/web/routes/config/__init__.py` | 85 | 4 | api_config_save, api_config_content_folders, api_config_read (+1) |
| `src/ui/web/routes/dns/__init__.py` | 80 | 4 | dns_generate, dns_status, dns_lookup (+1) |
| `src/ui/web/routes/server/__init__.py` | 89 | 4 | server_settings_put, server_restart_route, server_status_route (+1) |
| `src/ui/web/routes/dev/__init__.py` | 86 | 3 | dev_scenarios, dev_status, dev_scenario_by_id |
| `src/ui/web/routes/project/__init__.py` | 67 | 3 | project_next, project_status, _root |
| `src/ui/web/routes/backup/__init__.py` | 67 | 2 | api_folder_tree, api_folders |
| `src/ui/web/routes/events/__init__.py` | 69 | 1 | event_stream |

### ⚙️ Core Services (4 files, 7 functions, 456 lines)

| File | Lines | Funcs | Top Functions |
|------|-------|-------|---------------|
| `src/core/services/artifacts/publishers/__init__.py` | 50 | 3 | _register_defaults, get_publisher, list_publishers |
| `src/core/services/pages_builders/__init__.py` | 74 | 3 | list_builders, _register_defaults, get_builder |
| `src/core/services/artifacts/builders/__init__.py` | 43 | 1 | get_builder |
| `src/core/services/audit/parsers/__init__.py` | 289 | 0 |  |

### 💾 Core Data (1 files, 3 functions, 298 lines)

| File | Lines | Funcs | Top Functions |
|------|-------|-------|---------------|
| `src/core/data/__init__.py` | 298 | 3 | classify_key, get_registry, _load_json |

## Documentation Freshness Dashboard

> Visual freshness of each document containing code references.

📚 **Overall**: `███████████████░░░░░` 74.2% (112/151 valid)

### Per-Document Freshness

`docs/PAGES.md`: `░░░░░░░░░░░░░░░░░░░░` 0% — ⚠️ 6 stale
`docs/DEVELOPMENT.md`: `█████████████░░░░░░░` 67% — ⚠️ 1 stale
`docs/CONSOLIDATION_AUDIT.md`: `██████████████░░░░░░` 71% — ⚠️ 6 stale
`docs/audits/code_hygiene.md`: `███████████████░░░░░` 77% — ⚠️ 26 stale
`docs/ADAPTERS.md`: `████████████████████` 100% — ✅
`docs/ANALYSIS.md`: `████████████████████` 100% — ✅
`docs/tool_install/tools/bundler.md`: `████████████████████` 100% — ✅
`docs/tool_install/tools/ruby.md`: `████████████████████` 100% — ✅

### Stale References

| Document | Line | Reference | Issue |
|----------|------|-----------|-------|
| `docs/CONSOLIDATION_AUDIT.md` | L25 | `src/core/services/content_crypto.py` | File does not exist |
| `docs/CONSOLIDATION_AUDIT.md` | L34 | `src/core/services/content_release.py` | File does not exist |
| `docs/CONSOLIDATION_AUDIT.md` | L273 | `src/core/services/content_crypto.py` | File does not exist |
| `docs/CONSOLIDATION_AUDIT.md` | L274 | `src/core/services/content_optimize.py` | File does not exist |
| `docs/CONSOLIDATION_AUDIT.md` | L275 | `src/core/services/content_optimize_video.py` | File does not exist |
| `docs/CONSOLIDATION_AUDIT.md` | L276 | `src/core/services/content_release.py` | File does not exist |
| `docs/DEVELOPMENT.md` | L149 | `tests/test_cli_mydomain.py` | File does not exist |
| `docs/PAGES.md` | L208 | `src/core/services/pages_builders/mybuilder.py` | File does not exist |
| `docs/PAGES.md` | L210 | `info()` | Context file src/core/services/pages_builders/mybuilder.py does not exist |
| `docs/PAGES.md` | L210 | `detect()` | Context file src/core/services/pages_builders/mybuilder.py does not exist |
| `docs/PAGES.md` | L210 | `pipeline_stages()` | Context file src/core/services/pages_builders/mybuilder.py does not exist |
| `docs/PAGES.md` | L210 | `run_stage()` | Context file src/core/services/pages_builders/mybuilder.py does not exist |
| `docs/PAGES.md` | L211 | `config_schema()` | Context file src/core/services/pages_builders/mybuilder.py does not exist |
| `docs/audits/code_hygiene.md` | L172 | `src/core/services/content_crypto.py` | File does not exist |
| `docs/audits/code_hygiene.md` | L173 | `src/core/services/content_release.py` | File does not exist |
| `docs/audits/code_hygiene.md` | L174 | `src/core/services/content_crypto.py` | File does not exist |
| `docs/audits/code_hygiene.md` | L175 | `src/core/services/content_optimize.py` | File does not exist |
| `docs/audits/code_hygiene.md` | L176 | `src/core/services/content_optimize_video.py` | File does not exist |
| `docs/audits/code_hygiene.md` | L177 | `src/core/services/content_release.py` | File does not exist |
| `docs/audits/code_hygiene.md` | L178 | `tests/test_cli_mydomain.py` | File does not exist |
| `docs/audits/code_hygiene.md` | L179 | `src/core/services/pages_builders/mybuilder.py` | File does not exist |
| `docs/audits/code_hygiene.md` | L180 | `info()` | Context file src/core/services/pages_builders/mybuilder.py does not exist |
| `docs/audits/code_hygiene.md` | L181 | `detect()` | Context file src/core/services/pages_builders/mybuilder.py does not exist |
| `docs/audits/code_hygiene.md` | L182 | `pipeline_stages()` | Context file src/core/services/pages_builders/mybuilder.py does not exist |
| `docs/audits/code_hygiene.md` | L183 | `run_stage()` | Context file src/core/services/pages_builders/mybuilder.py does not exist |
| `docs/audits/code_hygiene.md` | L184 | `config_schema()` | Context file src/core/services/pages_builders/mybuilder.py does not exist |
| `docs/audits/code_hygiene.md` | L185 | `src/core/services/content_crypto.py` | File does not exist |
| `docs/audits/code_hygiene.md` | L186 | `src/core/services/content_release.py` | File does not exist |
| `docs/audits/code_hygiene.md` | L187 | `src/core/services/content_crypto.py` | File does not exist |
| `docs/audits/code_hygiene.md` | L188 | `src/core/services/content_optimize.py` | File does not exist |
| `docs/audits/code_hygiene.md` | L189 | `src/core/services/content_optimize_video.py` | File does not exist |
| `docs/audits/code_hygiene.md` | L190 | `src/core/services/content_release.py` | File does not exist |
| `docs/audits/code_hygiene.md` | L191 | `tests/test_cli_mydomain.py` | File does not exist |
| `docs/audits/code_hygiene.md` | L192 | `src/core/services/pages_builders/mybuilder.py` | File does not exist |
| `docs/audits/code_hygiene.md` | L193 | `info()` | Context file src/core/services/pages_builders/mybuilder.py does not exist |
| `docs/audits/code_hygiene.md` | L194 | `detect()` | Context file src/core/services/pages_builders/mybuilder.py does not exist |
| `docs/audits/code_hygiene.md` | L195 | `pipeline_stages()` | Context file src/core/services/pages_builders/mybuilder.py does not exist |
| `docs/audits/code_hygiene.md` | L196 | `run_stage()` | Context file src/core/services/pages_builders/mybuilder.py does not exist |
| `docs/audits/code_hygiene.md` | L197 | `config_schema()` | Context file src/core/services/pages_builders/mybuilder.py does not exist |

## Cross-Reference

> Areas where init leaks and stale documentation overlap — potential hotspots for cleanup.

| Init File | Related Stale Docs | Issue |
|-----------|-------------------|-------|
| `src/core/services/pages_builders/__init__.py` | `docs/PAGES.md` L208 | File does not exist |
| `src/core/services/pages_builders/__init__.py` | `docs/PAGES.md` L210 | Context file src/core/services/pages_builders/mybuilder.py does not exist |
| `src/core/services/pages_builders/__init__.py` | `docs/PAGES.md` L210 | Context file src/core/services/pages_builders/mybuilder.py does not exist |
| `src/core/services/pages_builders/__init__.py` | `docs/PAGES.md` L210 | Context file src/core/services/pages_builders/mybuilder.py does not exist |
| `src/core/services/pages_builders/__init__.py` | `docs/PAGES.md` L210 | Context file src/core/services/pages_builders/mybuilder.py does not exist |
| `src/core/services/pages_builders/__init__.py` | `docs/PAGES.md` L211 | Context file src/core/services/pages_builders/mybuilder.py does not exist |
| `src/core/services/pages_builders/__init__.py` | `docs/audits/code_hygiene.md` L179 | File does not exist |
| `src/core/services/pages_builders/__init__.py` | `docs/audits/code_hygiene.md` L180 | Context file src/core/services/pages_builders/mybuilder.py does not exist |
| `src/core/services/pages_builders/__init__.py` | `docs/audits/code_hygiene.md` L181 | Context file src/core/services/pages_builders/mybuilder.py does not exist |
| `src/core/services/pages_builders/__init__.py` | `docs/audits/code_hygiene.md` L182 | Context file src/core/services/pages_builders/mybuilder.py does not exist |
| `src/core/services/pages_builders/__init__.py` | `docs/audits/code_hygiene.md` L183 | Context file src/core/services/pages_builders/mybuilder.py does not exist |
| `src/core/services/pages_builders/__init__.py` | `docs/audits/code_hygiene.md` L184 | Context file src/core/services/pages_builders/mybuilder.py does not exist |
| `src/core/services/pages_builders/__init__.py` | `docs/audits/code_hygiene.md` L192 | File does not exist |
| `src/core/services/pages_builders/__init__.py` | `docs/audits/code_hygiene.md` L193 | Context file src/core/services/pages_builders/mybuilder.py does not exist |
| `src/core/services/pages_builders/__init__.py` | `docs/audits/code_hygiene.md` L194 | Context file src/core/services/pages_builders/mybuilder.py does not exist |
| `src/core/services/pages_builders/__init__.py` | `docs/audits/code_hygiene.md` L195 | Context file src/core/services/pages_builders/mybuilder.py does not exist |
| `src/core/services/pages_builders/__init__.py` | `docs/audits/code_hygiene.md` L196 | Context file src/core/services/pages_builders/mybuilder.py does not exist |
| `src/core/services/pages_builders/__init__.py` | `docs/audits/code_hygiene.md` L197 | Context file src/core/services/pages_builders/mybuilder.py does not exist |
