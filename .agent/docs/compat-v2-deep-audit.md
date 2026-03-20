# Compat V2 Pipeline Deep Audit — Exhaustive Gap Analysis

Date: 2026-03-20
Scope: ALL version plan + compat-v2 pipeline steps, handlers, frontend interactions, state tracking, error handling.

---

## A. PIPELINE COHERENCE — Step-by-Step Trace

### A1. `scan_incompatible_features` (code_scanner.py:46)
- **INPUT**: `UpgradeContext` (module_name, module_path, language, target_floor). Reads `compat.analysis.{module_name}` from mediator.
- **OUTPUT**: Dict with `findings[]`, `by_feature[]`, `auto_fixable_count`, `code_floor`. Consumed by: frontend preview modal, batch wizard log.
- **ASSUMPTIONS**: Compat analysis is already cached in mediator (dispatched during plan creation at posture.py:1081). Language is "python".
- **BREAKS IF**: Compat analysis was never dispatched (non-Python modules fall through silently). If mediator returns None for `compat.analysis.{module_name}`, handler returns `{"ok": False, "error": "Feature scan failed: ..."}`.

**GAP #1**: The scan handler calls `_m.get(f"compat.analysis.{ctx.module_name}")` which may trigger lazy computation, but if the compat system isn't loaded (e.g., registry not yet built), it fails with a generic error. No retry mechanism exists. The user sees "Feature scan failed" with no actionable guidance.

**GAP #2**: The scan is ONLY available for Python (`ctx.language != "python"` returns early). Non-Python languages get a silent "Code scanning only available for Python" info response — but the step still appears in their plan with an Automate button. Clicking it gives a confusing non-result.

**GAP #3**: Both `handle_scan_breaking_changes` and `handle_scan_incompatible_features` call the same `_scan_features()` internal function, producing identical results. The direction parameter ("upgrade" vs "downgrade") is passed but NEVER USED inside `_scan_features()` (code_scanner.py:323). The function always filters to `severity in ("error", "warning") and fix_strategy != "no_fix_needed"` regardless of direction.

### A2. `fix_compat_auto` (code_scanner.py:57)
- **INPUT**: `UpgradeContext` (with `_feature_hash` for per-feature filtering). Reads `compat.analysis.{module_name}` and `compat.orchestrator` from mediator.
- **OUTPUT**: Dict with `fixed_count`, `failed_count`, `files_fixed`, `files_rolled_back`, `duration_ms`.
- **ASSUMPTIONS**: Compat analysis exists AND compat orchestrator is loaded (for fix engine access). Findings have `fix_available=True`.
- **BREAKS IF**: Compat orchestrator not loaded. Analysis stale after previous fixes applied.

**GAP #4**: After `fix_compat_auto` applies fixes, the compat analysis cache is NOT invalidated. Subsequent scan/fix/guide steps still read the OLD analysis from the mediator cache. The `rescan_module` step busts the cache, but if the user runs fix steps individually (not in batch), intermediate steps see stale data. For example: running `fix_compat_auto` for feature A, then running `fix_compat_auto` for feature B — feature B's handler reads stale analysis that still includes feature A's findings, potentially trying to fix already-fixed code.

**GAP #5**: The `auto_fix` flag on `UpgradeContext` is set by `executor.py:105` but the `fix_compat_auto` handler at code_scanner.py:57 NEVER checks `ctx.auto_fix`. It uses `mode` ("preview" vs "execute") instead. The `auto_fix` toggle in the frontend is only checked by `wizard.py:wizard_batch()` which determines the mode. For individual step execution via `_modalApplyStep`, the auto_fix flag IS sent to the API (posture.py:1359) and passed to `execute_step`, but execute_step sets `ctx.auto_fix = auto_fix` which is never read by `fix_compat_auto`. The handler always executes if mode is "execute".

**GAP #6**: The per-feature hash filtering uses `_hl.md5(f.feature_name.encode()).hexdigest()[:8]` (code_scanner.py:89). This is a non-cryptographic 8-character hash collision risk. If two features hash to the same 8 chars, the fix handler would fix both when only one was intended.

### A3. `guide_incompatible_syntax` (code_scanner.py:760)
- **INPUT**: Same as scan — reads `compat.analysis.{module_name}` and `compat.orchestrator`.
- **OUTPUT**: Grouped findings with `rewrite_hint`, `example_before`, `example_after` per feature.
- **ASSUMPTIONS**: Same as scan. Also needs `compat.orchestrator.registry` for guide hints.
- **BREAKS IF**: Same as scan. Additionally, if `entry.fix` doesn't have `strategy` attribute, the line `entry.fix.strategy.value != "manual"` (code_scanner.py:815) will raise AttributeError.

**GAP #7**: The guide handler is read-only (`can_apply: False`) — it shows what needs manual fixing but provides no mechanism to actually apply changes. The frontend offers a "Mark reviewed" button and an "Add __future__" button, but the latter calls `wizardAddFuture()` which is a SEPARATE flow that applies ALL `__future__` fixes, not the specific ones shown in the guide. There's no per-file or per-finding fix action.

**GAP #8**: Duplicated comment at code_scanner.py:763-764: "Uses the compat v2 AST engine for accurate detection." appears twice.

### A4. `rescan_module` (executor.py:150)
- **INPUT**: `UpgradeContext` with `module_name` and `target_floor`.
- **OUTPUT**: Dict with `summary` and `findings_count` (remaining).
- **ASSUMPTIONS**: Mediator is available. Compat analysis path `compat.analysis.{module_name}` is valid.
- **BREAKS IF**: Mediator not initialized.

**GAP #9**: The rescan busts `compat.analysis.{module_name}` cache AND `posture.modules` cache. But it does NOT bust the `compat.orchestrator` cache. If the orchestrator has stale state (e.g., the fix engine's internal state), it may produce incorrect results on the fresh analysis.

**GAP #10**: After rescan, the step reports remaining findings count, but this count is NOT propagated back to the plan steps. The plan checklist in project.yml still shows the old step labels (e.g., "Scan — 5 finding(s)"). The labels are frozen at plan generation time and never updated to reflect current state.

### A5. `check_dep_compat_pypi` (dep_checker.py:32)
- **INPUT**: `UpgradeContext` with `language`, `module_path`, `target_floor`. Calls `module_intel._scan_module_imports()` and `_find_site_packages()`.
- **OUTPUT**: Dict with `findings[]` (each with `package`, `compatible`, `requires_python`).
- **ASSUMPTIONS**: `site-packages` exists and is readable. PyPI is reachable.
- **BREAKS IF**: No site-packages found (returns error). PyPI unreachable (individual packages marked as `unknown: True, compatible: True` — false positive).

**GAP #11**: The dep checker scans IMPORTS in .py files via `_scan_module_imports()`, then maps them to packages via `_build_import_mapping()` from site-packages. This means: (a) deps that are imported but NOT installed are mapped as their import name, not their pip package name (e.g., importing `yaml` but the package is `pyyaml`). (b) Deps listed in requirements.txt but NOT imported are completely missed. (c) Deps installed in a virtualenv different from the one running CDP are invisible.

**GAP #12**: The dep checker reads `requirements.txt` for pinned versions (dep_checker.py:91-105) but only for the module directory. If requirements are in a parent directory, a `requirements/` subdirectory, or in `pyproject.toml [project.dependencies]`, they're missed. The handler doesn't use `has_requirements_txt` from context or check `has_pyproject`.

**GAP #13**: When PyPI query fails, the package is marked `compatible: True, unknown: True` (dep_checker.py:169-175). This is a FALSE POSITIVE — the user sees a green checkmark for something that couldn't be verified. This silently passes through `should_mark_done()` which only blocks on explicitly `compatible=False` findings.

### A6. `run_pip_install` (subprocess_ops.py:112)
- **INPUT**: `UpgradeContext` with `module_name`, `target_floor`, `module_path`. Checks for venv pip.
- **OUTPUT**: Command stdout/stderr.
- **ASSUMPTIONS**: `requirements.txt` exists in module directory. Venv pip at `.venvs/{module}-{target}/bin/pip` if venv was set up.
- **BREAKS IF**: No requirements.txt (command fails with "no such file"). Venv not set up (falls back to system pip, which installs into the WRONG environment).

**GAP #14**: `run_pip_install` falls back to system `pip` if no venv exists (subprocess_ops.py:125-126). This installs packages into the system Python environment or whatever virtualenv CDP is running in — NOT the target version environment. This silently corrupts the host environment. There's no warning that the venv doesn't exist yet.

**GAP #15**: The handler hardcodes `"requirements.txt"` in the command (subprocess_ops.py:133). If the module uses `pyproject.toml` for dependencies, this step silently fails or installs nothing.

**GAP #16**: `run_pip_install` checks `venv_pip.is_file()` but not whether the venv's Python version matches the target. If the user created a venv manually with the wrong Python version, pip install would succeed but with the wrong version.

### A7. `setup_test_env` (test_env.py:83)
- **INPUT**: `UpgradeContext` with `target_floor`, `module_path`, `module_name`.
- **OUTPUT**: Dict with `venv_path` and `installed` list.
- **ASSUMPTIONS**: Python target version binary exists on PATH.
- **BREAKS IF**: Target Python not installed on system.

**GAP #17**: The venv is created at `.venvs/{module_name}-{target}` (test_env.py:100). The `module_name` is used directly — if module names contain special characters or are very long, this could create invalid directory names.

**GAP #18**: `setup_test_env` installs deps from `requirements.txt` OR `pyproject.toml` (editable install), but NOT both. If a module has both, only requirements.txt is used (test_env.py:188-213). Also, if neither exists, deps are NOT installed at all — only pytest is installed.

**GAP #19**: Pytest is installed via `venv_pip install pytest` (test_env.py:218) but the result is NOT checked for failure. If pytest installation fails (e.g., network issue), the step still reports success. The `installed` list includes "pytest" regardless.

**GAP #20**: The `_check_already_done()` function in executor.py:598-602 checks if `venv_dir / "bin" / "python"` exists to skip the step. But this doesn't verify that deps are installed. If the venv was created but dep installation failed, the step is skipped on retry.

### A8. `run_isolated_tests` (test_env.py:236)
- **INPUT**: `UpgradeContext` with `target_floor`, `module_path`, `module_name`.
- **OUTPUT**: Dict with `passed`, `failed`, `errors`, `skipped`, `output`, `compat_hints`.
- **ASSUMPTIONS**: Venv exists. Tests exist.
- **BREAKS IF**: No venv → error. No tests dir → runs pytest on entire module dir (including non-test files).

**GAP #21**: The test runner runs `venv_python -m pytest test_target -v --tb=short` with `cwd=str(ctx.project_root)` (test_env.py:286-289). The cwd is the PROJECT ROOT, not the module directory. This means: (a) imports in tests that use relative paths may break. (b) conftest.py at project root will be picked up, potentially interfering. (c) If the module path contains spaces or special chars, the test_target path could break.

**GAP #22**: The test runner does NOT install the MODULE ITSELF into the venv. It only installs deps from requirements.txt. So `import module_package` in tests will fail unless the module is on sys.path. The `test_compatibility.py` generated by `generate_smart_tests` does `importlib.import_module(module_path)` which requires the module to be importable. This is NOT guaranteed with the venv setup.

**GAP #23**: Test scope is controlled by `test_target = str(tests_dir) if tests_dir.is_dir() else str(module_dir)` (test_env.py:283). If `tests_dir` doesn't exist, pytest runs on the ENTIRE module directory, which may include non-test code that pytest tries to collect, causing spurious failures.

### A9. `edit_pyproject_requires_python` (config_editor.py:31)
- **INPUT**: `UpgradeContext` with `module_path`, `target_floor`.
- **OUTPUT**: Dict with `file`, `old_value`, `new_value`.
- **ASSUMPTIONS**: pyproject.toml exists (or will be created).
- **BREAKS IF**: pyproject.toml has complex TOML structure that regex can't handle.

**GAP #24**: The config editor uses regex to find and replace `requires-python` (config_editor.py:42-43). This can break on: (a) multi-line TOML values. (b) requires-python in a non-[project] section. (c) Comments containing `requires-python`. The regex `r'requires-python\s*=\s*"([^"]*)"'` only matches double-quoted values, missing single-quoted ones.

**GAP #25**: If `pyproject.toml` doesn't exist, the handler creates a MINIMAL file (config_editor.py:59-64) that may not be valid for the project's build system. It doesn't check for existing `setup.py` or `setup.cfg` that might conflict.

### A10. `generate_module_toml` (config_editor.py:508)
- **INPUT**: `UpgradeContext` with `module_path`, `module_name`, `target_floor`.
- **OUTPUT**: Creates `pyproject.toml` with name, version, requires-python, dependencies.
- **ASSUMPTIONS**: Module doesn't already have pyproject.toml (checked by `_check_already_done`).
- **BREAKS IF**: requirements.txt has complex entries (URLs, `-e`, `-r` references) that break when put in `dependencies = [...]`.

**GAP #26**: `generate_module_toml` reads deps from `requirements.txt` and puts them verbatim into `dependencies = ["dep_line", ...]` (config_editor.py:523-527). Lines with `-r`, `-e`, `--index-url`, or URL-based deps will produce invalid pyproject.toml.

**GAP #27**: The generated `pyproject.toml` sets `version = "0.1.0"` hardcoded (config_editor.py:531). This is arbitrary and doesn't reflect the actual module version if one exists elsewhere.

### A11. `scaffold_module_tests` (executor.py:214)
- **INPUT**: `UpgradeContext` with `module_path`, `module_name`, `target_floor`.
- **OUTPUT**: Creates `tests/__init__.py`, `tests/conftest.py`, `tests/test_smoke.py`.
- **ASSUMPTIONS**: No tests exist yet (checked by regex pattern).
- **BREAKS IF**: Tests exist in non-standard locations.

**GAP #28**: The smoke test generates `import {mod_package}` where `mod_package = ctx.module_path.replace("/", ".")` (executor.py:277-278). If the module path is `src/core/services/mymod`, the import becomes `import src.core.services.mymod`. This only works if `src` is a package with `__init__.py` at every level AND is on sys.path. The test will fail in the isolated venv where the module isn't installed.

### A12. `generate_smart_tests` (executor.py:306)
- **INPUT**: Same as scaffold.
- **OUTPUT**: Creates `tests/test_compatibility.py` with parametrized tests.
- **BREAKS IF**: Module has no `__init__.py` (exports detection fails). Dependencies listed in requirements.txt aren't importable by their pip name.

**GAP #29**: The `_MODULE_PATHS` list for import verification is built using `rel.replace("/", ".").replace(".py", "")` (executor.py:343). This converts file paths to import paths, but this mapping is incorrect for: (a) files inside namespace packages. (b) files with `-` or `.` in their names. (c) `__main__.py` files.

**GAP #30**: The `_DECLARED_DEPS` test does `importlib.import_module(dep)` but catches ImportError and calls `pytest.skip()` (executor.py:461). This means missing deps are SILENTLY SKIPPED, not reported as failures. The test suite will appear green even if deps aren't installed.

### A13. `update_ci_matrix` (code_scanner.py:646)
- **INPUT**: `UpgradeContext` with `project_root`, `module_path`, `target_floor`.
- **OUTPUT**: Read-only findings showing CI files with Python version references.
- **ASSUMPTIONS**: CI files are in standard locations.
- **BREAKS IF**: CI files use non-standard formats or variable interpolation.

**GAP #31**: `update_ci_matrix` is read-only (`can_apply: False`) — it shows what needs updating but NEVER actually updates anything. The user must manually edit CI files. But the step can be marked "done" via the executor's `should_mark_done()` logic, which returns True for scan steps with findings (executor.py:36-39). So the step gets auto-marked done in batch mode even though nothing was actually changed.

---

## B. MISSING PIPELINE STEPS

**GAP #32**: **No dependency DISCOVERY step.** The pipeline checks if KNOWN deps are compatible but doesn't discover deps that are imported in code but missing from requirements.txt. The `_scan_module_imports()` → `_build_import_mapping()` path in dep_checker.py maps imports to packages via site-packages, but if a package isn't installed, the import name is used as-is for the PyPI query. There's no step that says "you import X but X isn't in your requirements.txt."

**GAP #33**: **No dependency ADDITION step.** Even when incompatible deps are identified and alternatives selected, there's no step that writes the new version constraint to requirements.txt or pyproject.toml. The `module-pin-deps` API endpoint (posture.py:1459) exists but is NOT a pipeline step — it's only accessible from the remediation UI after a dep check failure in the wizard. There's no plan step for it.

**GAP #34**: **No pre-test validation gate.** Nothing checks "are all fix steps done before running tests?" The batch runner runs steps sequentially but doesn't validate preconditions. If a user runs `run_isolated_tests` before `fix_compat_auto`, the tests will fail on unfixed code, and the user gets a confusing error.

**GAP #35**: **No module installation step.** The test environment (venv) installs deps but NOT the module itself. Tests that import the module will fail. A `pip install -e .` or `PYTHONPATH` setup step is missing.

**GAP #36**: **No post-fix re-analysis step between fix and rescan.** After `fix_compat_auto`, the analysis cache is stale (GAP #4). The pipeline should invalidate analysis after each fix step, not just at the final rescan.

**GAP #37**: **No `fix_compat_auto` step in the UPGRADE recipe.** The Python upgrade recipe (python.json) includes `scan_breaking_changes` but not `fix_compat_auto`. The compat enrichment in generator.py adds fix steps dynamically from analysis, but only if compat analysis has findings. If no analysis is available (first-time scan), the upgrade recipe has no fix step at all.

**GAP #38**: **No requirements.txt generation/update step.** If a module has `pyproject.toml` but no `requirements.txt`, and the pipeline needs `requirements.txt` for `run_pip_install`, there's no step to generate it (e.g., `pip freeze` or `pip-compile`).

---

## C. FRONTEND FLOW GAPS

### C1. After EACH modal interaction

**GAP #39**: After `modulePlanAutomate` → preview → Apply, the modal closes and the step is marked done in the DOM, but the plan modal is NOT refreshed from the server. The checklist still shows old labels and descriptions. Only `_refreshPlanState()` runs, which updates progress bar and button visibility based on DOM state, not server state. If the server changed step labels (e.g., after rescan), the user sees stale text until they close and reopen the plan modal.

**GAP #40**: After `_modalApplyStep` succeeds (posture.html:2270-2284), `modalClose()` is called TWICE (posture.html:2272-2273). The first closes the apply-result modal, the second closes the plan modal. But the plan modal is needed to see the updated checklist. The user is left with no modal open and must re-navigate to see the plan.

**GAP #41**: After `modulePlanAddStep` and `modulePlanRemoveStep`, the plan modal is closed and reopened via `moduleOpenPlan(moduleName)` (posture.html:1996, 2012). This full refresh is correct but causes a visual flash. More importantly, if the posture data cache (`_modulePeekItems`) hasn't been updated yet (mediator.put happens async), the reopened modal may show stale data.

### C2. Plan modal refresh correctness

**GAP #42**: `moduleOpenPlan` fetches fresh data from `/api/posture/module-plan-detail` (posture.html:1851-1857), but the `met` and `overdue` flags come from `_modulePeekItems` (the cached posture data, posture.html:1846-1847), not from the fresh API response. The `module-plan-detail` endpoint doesn't return `met` or `overdue` — these are computed only in the posture enrichment layer. So the "Plan complete!" and "Plan overdue" banners may be stale.

### C3. Step completion state accuracy

**GAP #43**: Step completion is tracked by the `done` boolean in project.yml. But the step's `state` field (which can be "passed", "blocked", "needs_attention", "failed") is only set during plan GENERATION (generator.py:180). It is never updated after that. So a step that was "blocked" at generation time remains "blocked" even if the blocking module was subsequently fixed. The only way to clear the "blocked" state is to regenerate the entire plan (clear and recreate).

**GAP #44**: The `needs_attention` state from the batch wizard (wizard.py:381, 527) is communicated via SSE events but never persisted to project.yml. After a browser refresh, the state is lost and the step appears as either done or not done (no attention indicator).

### C4. Batch awareness of what's already done

**GAP #45**: `modulePlanRunBatch` collects undone steps from the DOM (posture.html:2344-2358). It checks `stepEl.classList.contains('done')` — a DOM-only check. If the server has marked a step done (e.g., from a concurrent session or API call) but the DOM hasn't been refreshed, the batch will re-run already-completed steps. However, `_check_already_done()` in executor.py provides some protection by checking for artifacts (e.g., existing venv, existing test files).

### C5. Loading feedback

**GAP #46**: When `modulePlanAutomate` is clicked, the automate button changes to "⏳" (posture.html:2047), but only for non-wizard steps (the fetch-based preview path). For wizard steps (dep_scan, subprocess, batch), the button state is NOT updated — the wizard modal just opens. If the SSE connection takes time to start, the user sees no feedback that clicking worked.

**GAP #47**: During batch execution, individual step DOM elements are updated as SSE events arrive (posture.html:2623-2635), but there's no progress indicator on the batch modal itself showing "3/7 complete". The wizard modal shows step icons (⏳/✅/❌) but no overall progress bar.

---

## D. HANDLER REGISTRY COMPLETENESS

### All registered handlers in `automation/__init__.py` (lines 84-162):

| Handler | Exists | Preview | Execute | Status |
|---|---|---|---|---|
| `edit_pyproject_requires_python` | Yes | Yes | Yes | OK |
| `edit_setup_py_python_requires` | Yes | Yes | Yes | OK |
| `edit_setup_cfg_python_requires` | Yes | Yes | Yes | OK |
| `edit_package_json_engines` | Yes | Yes | Yes | OK |
| `edit_go_mod_directive` | Yes | Yes | Yes | OK |
| `edit_cargo_toml_rust_version` | Yes | Yes | Yes | OK |
| `edit_gemfile_ruby_version` | Yes | Yes | Yes | OK |
| `edit_pom_java_version` | Yes | Yes | Yes | OK |
| `edit_csproj_target` | Yes | Yes | Yes | OK |
| `edit_composer_php_version` | Yes | Yes | Yes | OK |
| `edit_mix_elixir_version` | Yes | Yes | Yes | OK |
| `check_dep_compat_pypi` | Yes | Yes (same) | Yes (same) | Read-only |
| `update_deps_interactive` | Yes | Yes (same) | Yes (same) | Read-only |
| `check_dep_compat_npm` | Yes | Yes (same) | Yes (same) | Read-only |
| `update_deps_npm` | Yes | Yes (same) | Yes (same) | Read-only |
| `check_dep_compat_crates` | Yes | Yes (same) | Yes (same) | Read-only |
| `update_deps_crates` | Yes | Yes (same) | Yes (same) | Read-only |
| `check_dep_compat_rubygems` | Yes | Yes (same) | Yes (same) | Read-only |
| `update_deps_rubygems` | Yes | Yes (same) | Yes (same) | Read-only |
| `check_dep_compat_packagist` | Yes | Yes (same) | Yes (same) | Read-only |
| `update_deps_packagist` | Yes | Yes (same) | Yes (same) | Read-only |
| `check_dep_compat_hex` | Yes | Yes (same) | Yes (same) | Read-only |
| `update_deps_hex` | Yes | Yes (same) | Yes (same) | Read-only |
| `scan_breaking_changes` | Yes | Yes (same) | Yes (same) | Read-only |
| `scan_incompatible_features` | Yes | Yes (same) | Yes (same) | Read-only |
| `fix_compat_auto` | Yes | Yes | Yes | OK |
| `remove_future_annotations` | Yes | Yes | Yes | OK |
| `add_future_annotations` | Yes | Yes | Yes | OK |
| `modernize_type_hints` | Yes | Yes | Yes | OK |
| `guide_incompatible_syntax` | Yes | Yes (same) | Yes (same) | Read-only |
| `update_ci_matrix` | Yes | Yes (same) | Yes (same) | Read-only |
| `run_go_mod_tidy` | Yes | Yes | Yes | OK |
| `run_bundle_update` | Yes | Yes | Yes | OK |
| `run_composer_update` | Yes | Yes | Yes | OK |
| `run_dotnet_restore` | Yes | Yes | Yes | OK |
| `run_mix_deps_get` | Yes | Yes | Yes | OK |
| `run_cargo_check` | Yes | Yes | Yes | OK |
| `run_npm_install` | Yes | Yes | Yes | OK |
| `run_pip_install` | Yes | Yes | Yes | OK |
| `run_pytest` | Yes | Yes | Yes | OK |
| `run_npm_test` | Yes | Yes | Yes | OK |
| `run_go_test` | Yes | Yes | Yes | OK |
| `run_cargo_test` | Yes | Yes | Yes | OK |
| `run_bundle_exec_rspec` | Yes | Yes | Yes | OK |
| `run_mvn_test` | Yes | Yes | Yes | OK |
| `run_dotnet_test` | Yes | Yes | Yes | OK |
| `run_composer_test` | Yes | Yes | Yes | OK |
| `run_mix_test` | Yes | Yes | Yes | OK |
| `rescan_module` | Yes | Yes | Yes | OK |
| `scaffold_module_tests` | Yes | Yes | Yes | OK |
| `scaffold_parent_tests` | Yes | Yes | Yes | OK |
| `generate_smart_tests` | Yes | Yes | Yes | OK |
| `setup_test_env` | Yes | Yes | Yes | OK |
| `run_isolated_tests` | Yes | Yes | Yes | OK |
| `generate_module_toml` | Yes | Yes | Yes | OK |

**GAP #48**: The `blocked` automation_id is referenced in frontend (posture.html:1894, `stepState !== 'blocked'`) and in generator.py:357 (`_automation_id: "blocked"`), but there is NO handler registered for "blocked" in the registry. The executor returns `{"ok": False, "error": "This step cannot be automated"}` for it (executor.py:78-79). This is correct behavior but confusing — the step appears with a lock icon and cannot be interacted with.

**GAP #49**: Read-only handlers (scan, dep_check, guide, ci_matrix) return the SAME result for both preview and execute modes. But `should_mark_done()` still marks them done on "execute" (executor.py:137-139). This means clicking "Automate" on a scan step immediately marks it done, even though "automate" implies something actionable will happen. The user expects automation but gets a read-only report that auto-closes.

---

## E. CONTEXT OBJECT GAPS

`UpgradeContext` at `context.py:22-70`:

**GAP #50**: No `test_dir` field. Multiple handlers need to know where tests are (scaffold, generate_smart_tests, run_isolated_tests). Each computes `module_dir / "tests"` independently. If a module uses a non-standard test directory (e.g., `test/`, `spec/`), none of the handlers find it.

**GAP #51**: No `venv_path` field. Multiple handlers need the venv path (`setup_test_env`, `run_isolated_tests`, `run_pip_install`). Each computes `.venvs/{module_name}-{target}` independently. If the venv naming convention changes, all handlers must be updated.

**GAP #52**: No `completed_steps` field. The context doesn't track which steps have been completed. Handlers can't check "did the previous step run?" Each handler checks for artifacts independently (e.g., `_check_already_done()`), but this is incomplete.

**GAP #53**: No `findings` or `analysis_result` field. Every handler that needs compat analysis fetches it from the mediator independently. If 5 handlers run in sequence, they each call `_m.get(f"compat.analysis.{ctx.module_name}")` — 5 mediator lookups for the same data. The context should carry the analysis result.

**GAP #54**: No `requirements_file` field. Multiple handlers look for requirements.txt in different ways. The context has `has_requirements_txt` (bool) but not the path. If requirements are in `requirements/base.txt` or similar, handlers won't find them.

**GAP #55**: `_feature_hash` is set as a dynamic attribute via `ctx._feature_hash = ...` (executor.py:107). This is not declared in the dataclass and relies on Python's permissive attribute setting. It's fragile and invisible to type checkers.

**GAP #56**: No `project_config` field. The context calls `load_project()` to get module ref data, but doesn't carry the project config forward. Handlers that need project-level info (like project-wide Python version) must re-load the config.

---

## F. RECIPE GAPS

### Python recipe (`python.json`):

**GAP #57**: The upgrade recipe has `"condition": {"has_deps_floor": true}` for `check_dep_compat_pypi` (python.json:86). This means: if the module has NO detected dependency floor (i.e., no recognized third-party deps), the dep check step is EXCLUDED from the plan. But the module might still have deps in requirements.txt that need checking — `has_deps_floor` only reflects what the deep analysis detected, not what's in the requirements file.

**GAP #58**: The upgrade recipe includes `remove_future_annotations` with condition `{"has_future_import": true, "target_gte": "3.10"}` (python.json:140-143). The threshold "3.10" is wrong — `from __future__ import annotations` is still useful for runtime annotation access even on 3.10+. It only becomes truly unnecessary if ALL type hints use runtime-compatible syntax (PEP 604/585). The condition should be `target_gte: "3.12"` or be based on code analysis.

**GAP #59**: The downgrade recipe has `check_dep_compat_pypi` with condition `{"always": true}` (python.json:296-301), but the upgrade recipe has it with `{"has_deps_floor": true}` (python.json:86). Inconsistent — downgrade always checks deps, upgrade only checks if deps floor is known.

**GAP #60**: The downgrade recipe has `add_future_annotations` with condition `{"target_lt": "3.10"}` (python.json:275-279). But `add_future_annotations` in code_scanner.py uses the compat v2 engine to find findings with `fix_strategy == "add_future_import"`. If no compat analysis is available, the handler fails. The recipe condition doesn't check for compat availability.

**GAP #61**: Both upgrade and downgrade recipes include `run_pip_install` with condition `{"has_file": "requirements.txt"}` (python.json:107-110, 310-313). But `run_pip_install` should logically come AFTER `setup_test_env` (to use the venv pip), yet the recipe order puts it in the "deps" category which appears before "test" category. The generator's `_enrich_with_compat_analysis()` reorders steps (generator.py:266-302), but `run_pip_install` is classified under `venv_steps` only if its automation_id matches `"run_pip_install"` (generator.py:284), which it does, so it goes after `setup_test_env`. However, this ordering ONLY applies when compat enrichment runs. Without enrichment (no analysis), the recipe order is used, and deps come before test.

**GAP #62**: Neither recipe includes a step for `run_pytest` (the non-isolated test runner). Only `run_isolated_tests` is in the recipe. But `run_pytest` is registered as a handler. Users who don't have the target Python installed can't use `run_isolated_tests` but could use `run_pytest` — no recipe step for this fallback.

**GAP #63**: The `_common.json` tail includes a manual "Run test suite" step (with empty automation_id) that's deduplicated against language-specific test steps. But the deduplication is by category (generator.py:150), and the Python recipe already has test-category steps. So the common tail step is always skipped for Python. For other languages that don't have test steps in their recipes, it appears but is non-automatable (manual step). This is inconsistent.

---

## G. TEST ENVIRONMENT GAPS

**GAP #64**: The venv setup at `test_env.py:170-175` uses `python{target} -m venv .venvs/{module}-{target} --clear`. The `--clear` flag DESTROYS an existing venv and recreates it from scratch. If the user had manually installed additional packages, they're lost. The `_check_already_done()` in executor.py skips the step if the venv exists, but if the user re-runs the step explicitly, `--clear` wipes everything.

**GAP #65**: The venv pip upgrade at test_env.py:181-183 runs but its result is NOT checked. If pip upgrade fails (e.g., network issue), the old pip continues silently. Old pip may not handle modern package formats correctly.

**GAP #66**: `detect_python_versions()` scans for `python3.7` through `python3.14` (test_env.py:41). This hardcoded range will miss Python 3.15+ when it's released. Also, it doesn't check for `pyenv`, `asdf`, or `conda` managed Pythons that may not be on PATH as `pythonX.Y`.

**GAP #67**: Test dependencies beyond pytest are NOT installed. If the module's tests require `pytest-cov`, `pytest-asyncio`, `mock`, `responses`, etc., they must be in requirements.txt. There's no mechanism to detect test dependencies from `conftest.py`, `setup.cfg [options.extras_require] test`, or `pyproject.toml [project.optional-dependencies] test`.

**GAP #68**: The isolated test runner at test_env.py:286-289 runs `venv_python -m pytest test_target -v --tb=short` but does NOT set `PYTHONPATH` to include the module or project root. Tests that do `from src.core.services.X import Y` will fail with ImportError because the project isn't installed in the venv and isn't on the path.

---

## H. ERROR HANDLING GAPS

**GAP #69**: When a step fails in `wizard_batch`, the batch STOPS (wizard.py:534 `break`). The `done` event is emitted with `failed_step_id` and `failed_step_idx`. But the user can only: (a) close the modal, (b) use remediation buttons if available. There is no "Resume from step N" button. The user must click "Run batch" again, which skips already-done steps via DOM check, but this requires the plan modal to be visible underneath.

**GAP #70**: When `execute_step` catches a handler exception (executor.py:129-134), it returns `{"ok": False, "error": f"Automation failed: {exc}"}`. The original exception traceback is logged but the user only sees the generic message. For `PermissionError` and `FileNotFoundError`, specific messages are given (executor.py:120-127), but for all other exceptions, the error is opaque.

**GAP #71**: When `_mark_step_done` fails (executor.py:661), it logs the error but does NOT propagate it. The step result still shows `ok: True` even though the step was NOT marked done in project.yml. The user thinks the step is complete, but on page refresh, it appears undone.

**GAP #72**: The SSE stream in `posture_module_wizard` (posture.py:1404-1448) wraps the entire generator in a try/except that yields a `done` event with the error. But if the error occurs DURING an SSE event yield (e.g., broken pipe), the client may receive a partial event followed by stream termination. The `streamSSE` client-side function handles stream errors (ops_modal.html:965-967) but doesn't show the partially completed steps' results.

**GAP #73**: `should_mark_done()` at executor.py:17 has a subtle edge case: if `result["findings"]` contains a mix of dep findings (with `"compatible"` key) and non-dep findings (without `"compatible"` key), only the dep findings are checked for incompatibility. A step with 10 code scan findings and 1 compatible dep finding would be marked done, which is correct. But a step with 0 code scan findings and 0 dep findings would also be marked done (line 34: `return True`), even if `ok` is True but the step produced no useful output.

**GAP #74**: The frontend `_modalApplyStep` calls `modalClose()` twice (posture.html:2272-2273) on success. If only one modal is open, the second `modalClose()` is a no-op (presumably). But if the modal system tracks modals in a stack, the second close might close the plan modal underneath, leaving the user stranded.

---

## I. STATE TRACKING GAPS

**GAP #75**: Step completion states are persisted in `project.yml` as `done: true/false` (via `_mark_step_done` at executor.py:621). On server restart, the done states are preserved because they're in the YAML file. However, the `state` field (passed, blocked, needs_attention, failed) is NOT persisted — it's only generated during plan creation (generator.py:180) and SSE streaming (wizard.py). After server restart, all steps show as either done or pending, losing intermediate states.

**GAP #76**: The `_mark_step_done` function matches steps by `step["id"]` (executor.py:642). Step IDs contain UUID suffixes (e.g., `fix_compat_auto__abcdef12:a1b2c3d4`). If the plan is regenerated (cleared and recreated), ALL step IDs change (new UUIDs). Any step that was marked done via the old ID is lost.

**GAP #77**: There's no mechanism to re-run a step after completion. The `_refreshPlanState()` frontend function hides the Automate button when a step is done (posture.html:2457-2458). The user can uncheck the step manually (toggling the checkbox), which calls `modulePlanToggleStep` to set `done: false`, but this only changes the done flag — it doesn't reset any artifacts created by the step (venv, generated files, applied fixes).

**GAP #78**: Progress computation in the frontend uses DOM state (posture.html:2444-2453), not server state. If the DOM and server get out of sync (e.g., concurrent user, network failure during PATCH), the progress bar shows incorrect values.

**GAP #79**: The `_check_already_done()` function in executor.py:577-604 checks for SPECIFIC artifacts per step type. But it only covers 5 steps: `generate_module_toml`, `scaffold_module_tests`, `scaffold_parent_tests`, `generate_smart_tests`, and `setup_test_env`. All other steps (scans, fixes, dep checks, CI matrix, config edits, subprocess runs) have NO already-done check. Running them multiple times is either idempotent (scans) or potentially destructive (fixes applied twice, configs edited twice).

**GAP #80**: The `modernize_type_hints` handler (code_scanner.py:494) modifies code on execute but has no protection against running twice. If run twice, regex replacements could corrupt code — e.g., removing `from typing import` lines that still have needed names, or replacing `typing.Optional` that was already replaced.

---

## J. ADDITIONAL CROSS-CUTTING GAPS

**GAP #81**: **No undo/rollback capability.** Once a step is executed (config changed, code modified, venv created), there's no way to undo it from the UI. The `fix_compat_auto` handler has internal rollback for VERIFICATION failures (via the compat fix engine), but user-initiated rollback is not supported.

**GAP #82**: **No concurrent execution protection.** Two users (or two browser tabs) can execute the same step simultaneously. Both will read the same file, make the same change, and write back. For file modifications this is a race condition. For subprocess operations, two pip installs or two pytest runs could interfere.

**GAP #83**: **No audit trail.** Which steps were executed when, by whom, and what was the result — none of this is tracked. The `@tracked` decorator on API routes logs events, but the step-level execution history is not persisted. After the browser session ends, all execution history is lost.

**GAP #84**: **`wizard_batch` in wizard.py builds a new context but uses the SAME context for all steps.** If step 1 modifies context-relevant state (e.g., creating a pyproject.toml that changes `has_pyproject`), step 2 still sees the original context where `has_pyproject=False`. The context is built ONCE at the start and reused for all steps.

**GAP #85**: **The wizard's `run_pip_install` command mapping in wizard.py:303 hardcodes `["pip", "install", "-r", "requirements.txt"]`.** This ignores the venv pip that `subprocess_ops.py:handle_run_pip_install` correctly checks for. When `run_pip_install` runs through the BATCH wizard, it uses the wizard's command mapping, NOT the handler. Wait — actually, the batch wizard calls handlers directly (wizard.py:364), not the command mapping. The SUBPROCESS_COMMANDS mapping is only used by `wizard_type="subprocess"` (posture.py:1418-1426). But the frontend routes `run_pip_install` through `_openStepModal(moduleName, stepId, stepIndex, 'subprocess')` because `aid.startsWith('run_')` (posture.html:2032). So when run individually, `run_pip_install` goes through the SUBPROCESS wizard which uses the wrong command (system pip, no venv). When run in BATCH, it goes through `wizard_batch` which calls the handler correctly (venv-aware).

**GAP #86**: **Java/Go/Rust/Ruby/PHP/Elixir dep check handlers use `requires_python` as the field name for their constraint** (dep_checker.py:424-434). This is technically a naming issue — the findings dict key is `requires_python` even for Node.js engines.node, Rust MSRV, Ruby required_ruby_version, etc. The frontend treats this as a display label. Not a functional bug, but confusing for debugging.

**GAP #87**: **The `_find_crates_alternatives` function (dep_checker.py:545-555) uses `requires_python` as the key for its results**, perpetuating the naming issue. Same for `_find_packagist_alternatives` (dep_checker.py:600-608).

**GAP #88**: **No language-specific code scanning for non-Python languages.** The `scan_incompatible_features` and `fix_compat_auto` handlers are Python-only. The entire compat v2 AST engine is Python-only. Go, Rust, Node.js, Ruby, PHP, and Elixir modules get no code-level analysis — only dependency checking and config editing.

**GAP #89**: **Registry cache at `.state/registry_cache/` uses relative paths** (registry_clients.py:333). If the working directory changes between invocations, the cache is missed or duplicated.

**GAP #90**: **The `_wizardMarkDone` function (posture.html:3254-3274) calls `/api/posture/module-step-execute` with `mode: 'execute'`.** This means marking a step as "done" actually RE-EXECUTES the handler. For read-only handlers (scan, dep_check), this is harmless (they return the same result). For file-modifying handlers (config edit, fix), this would re-apply changes. For subprocess handlers (pip install, pytest), this would re-run the command. The intent is just to mark done, but the implementation runs the full handler.

**GAP #91**: **Plan generation in `_enrich_with_compat_analysis` (generator.py:252-259) skips config update steps when `current_floor == target`.** This calls `build_context()` AGAIN inside the enrichment loop (generator.py:253), which is a redundant full context build (module detection, deep analysis, file checks). Performance impact for large modules.

**GAP #92**: **The `_check_already_done` for `generate_smart_tests` (executor.py:594-595) checks for `test_compatibility.py` existence.** But `generate_smart_tests` OVERWRITES existing files (executor.py:483). So the "already done" check prevents re-generation, which means if the module code changed, the generated tests become stale with no way to regenerate without manually deleting the file.

---

## SUMMARY BY SEVERITY

### Critical (blocks core functionality):
- GAP #4: Stale analysis cache after fix steps
- GAP #14: `run_pip_install` falls back to system pip silently
- GAP #22: Module not installed in test venv → all import tests fail
- GAP #68: No PYTHONPATH in isolated test runner → import failures
- GAP #85: Individual `run_pip_install` via subprocess wizard uses wrong pip

### High (produces incorrect results or confusing UX):
- GAP #2: Non-Python scan steps appear with Automate button but do nothing useful
- GAP #10: Plan step labels frozen at generation time
- GAP #11: Dep checker maps imports incorrectly for uninstalled packages
- GAP #13: PyPI query failure = false positive (marked compatible)
- GAP #28: Generated smoke test import path may be wrong
- GAP #31: CI matrix step auto-marked done but nothing changed
- GAP #40: Double modalClose() after apply
- GAP #43: Blocked state never clears
- GAP #84: Context stale through batch execution
- GAP #90: "Mark as done" re-executes the handler

### Medium (missing functionality or incomplete flows):
- GAP #1: No retry on compat analysis failure
- GAP #7: Guide shows findings but no per-file fix action
- GAP #15: pip install hardcodes requirements.txt
- GAP #32: No dependency discovery step
- GAP #33: No dependency addition step
- GAP #34: No pre-test validation gate
- GAP #35: No module installation step
- GAP #37: No fix step in upgrade recipe without analysis
- GAP #38: No requirements.txt generation step
- GAP #50-56: Context object missing fields
- GAP #69: No "Resume from step N" in batch
- GAP #75: Intermediate states not persisted
- GAP #77: No re-run mechanism for completed steps
- GAP #81: No undo/rollback

### Low (edge cases, naming, cosmetics):
- GAP #3: Direction parameter unused in scan
- GAP #6: MD5 hash collision risk (8 chars)
- GAP #8: Duplicated comment
- GAP #17: Module name in venv path
- GAP #27: Hardcoded version "0.1.0"
- GAP #86-87: `requires_python` field naming for non-Python
- GAP #89: Relative cache path
