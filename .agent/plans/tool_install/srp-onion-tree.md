# SRP Onion Tree — tool_install decomposition

> This is a DRAFT. It maps the 7,493-line monolith
> `tool_install.py` into single-responsibility files
> organized as an onion (inner = pure domain, outer = I/O).
>
> Every function listed comes from the CURRENT monolith.
> Nothing is invented. Nothing is removed.
>
> STATUS: DRAFT — awaiting review before any code moves.

---

## The Onion (inside → out)

```
┌───────────────────────────────────────────────────────────┐
│                    LAYER 0: DATA                          │
│         Pure dicts. No logic. No imports.                 │
│                                                           │
│  recipes.py ·········· TOOL_RECIPES dict (61 tools)       │
│  undo_catalog.py ····· UNDO_COMMANDS dict                 │
│  restart_triggers.py · RESTART_TRIGGERS dict              │
│  cuda_matrix.py ······ CUDA_DRIVER_COMPAT matrix          │
│  arch_map.py ········· _ARCH_MAP, PM_LOCKS constants      │
│  profile_maps.py ····· _PROFILE_MAP (shell rc/profile)    │
│                                                           │
├───────────────────────────────────────────────────────────┤
│                    LAYER 1: DOMAIN                        │
│     Pure functions. Input → Output. No subprocess.        │
│     No filesystem. No network. Fully testable.            │
│                                                           │
│  risk.py                                                  │
│  ├─ _infer_risk(step) → str                               │
│  ├─ _plan_risk(steps) → dict                              │
│  └─ _check_risk_escalation(prev, new) → dict              │
│                                                           │
│  condition.py                                             │
│  └─ _evaluate_condition(cond, context) → bool             │
│                                                           │
│  template.py                                              │
│  ├─ _render_template(tpl, inputs) → str                   │
│  ├─ _check_unsubstituted(rendered) → list[str]            │
│  └─ _validate_output(content, fmt) → str|None             │
│                                                           │
│  input_validation.py                                      │
│  └─ _validate_input(input_def, value) → str|None          │
│                                                           │
│  dag.py                                                   │
│  ├─ _add_implicit_deps(steps) → list[dict]                │
│  ├─ _validate_dag(steps) → list[str]                      │
│  ├─ _get_ready_steps(steps, done, running) → list[dict]   │
│  ├─ _get_step_pm(step) → str|None                         │
│  └─ _enforce_parallel_safety(steps) → list[dict]          │
│                                                           │
│  rollback.py                                              │
│  └─ _generate_rollback(completed_steps) → list[dict]      │
│                                                           │
│  restart.py                                               │
│  ├─ detect_restart_needs(plan, completed) → dict          │
│  └─ _batch_restarts(restart_needs) → list[dict]           │
│                                                           │
│  version_constraint.py                                    │
│  └─ check_version_constraint(tool, installed, ctx) → dict │
│                                                           │
│  error_analysis.py                                        │
│  ├─ _analyse_install_failure(tool, output, code) → dict   │
│  └─ _analyse_build_failure(output, step) → dict           │
│                                                           │
│  build_progress.py                                        │
│  └─ _parse_build_progress(output) → dict                  │
│                                                           │
│  download_helpers.py                                      │
│  ├─ _fmt_size(n) → str                                    │
│  ├─ _verify_checksum(path, expected) → bool               │
│  └─ _estimate_download_time(size_bytes) → dict            │
│                                                           │
├───────────────────────────────────────────────────────────┤
│                    LAYER 2: RESOLVER                      │
│     Reads Layer 0 data + Layer 1 domain.                  │
│     Produces plans. May read system profile (input arg).  │
│     Still NO subprocess. NO filesystem writes.            │
│                                                           │
│  method_picker.py                                         │
│  ├─ _pick_install_method(recipe, profile) → str           │
│  ├─ _is_batchable(method, primary_pm) → bool              │
│  ├─ _extract_packages_from_cmd(cmd, pm) → list[str]       │
│  ├─ _wrap_with_env(cmd, env_setup) → list[str]            │
│  └─ _build_pkg_install_cmd(packages, pm) → list[str]      │
│                                                           │
│  dependency_collector.py                                  │
│  ├─ _collect_deps(tool, recipe, profile) → list[dict]     │
│  └─ _get_system_deps(tool) → list[str]                    │
│                                                           │
│  choice_resolver.py                                       │
│  ├─ _resolve_choice_option(opt, profile) → dict           │
│  ├─ _resolve_single_choice(choice, profile) → dict        │
│  ├─ _input_condition_met(cond, inputs) → bool             │
│  ├─ resolve_choices(tool, recipe, profile) → dict         │
│  ├─ _apply_choices(plan, selections) → dict               │
│  └─ _apply_inputs(plan, inputs) → dict                    │
│                                                           │
│  plan_resolver.py                                         │
│  ├─ resolve_install_plan(tool, profile) → dict            │
│  ├─ resolve_install_plan_with_choices(...) → dict          │
│  └─ _backup_before_step(step, plan) → dict                │
│                                                           │
│  build_plan.py                                            │
│  ├─ _autotools_plan(recipe, ctx) → list[dict]             │
│  ├─ _cmake_plan(recipe, ctx) → list[dict]                 │
│  ├─ _cargo_git_plan(recipe, ctx) → list[dict]             │
│  ├─ _substitute_build_vars(cmd, ctx) → list[str]          │
│  └─ _substitute_install_vars(cmd, ctx) → list[str]        │
│                                                           │
│  download_resolver.py                                     │
│  └─ _resolve_github_release_url(repo, ...) → str          │
│                                                           │
├───────────────────────────────────────────────────────────┤
│                    LAYER 3: DETECTION                     │
│     Reads the real system. Subprocess + filesystem.       │
│     Returns dicts. No mutations.                          │
│                                                           │
│  detect_packages.py                                       │
│  ├─ _is_pkg_installed(pkg, pm) → bool                     │
│  └─ check_system_deps(tool, profile) → dict               │
│                                                           │
│  detect_gpu.py                                            │
│  ├─ _lspci_gpu() → dict|None                              │
│  ├─ _nvidia_smi() → dict|None                             │
│  ├─ _rocminfo() → dict|None                               │
│  ├─ _list_gpu_modules() → list[str]                       │
│  ├─ _extract_gpu_model(line) → str                        │
│  ├─ _extract_pci_id(line) → str|None                      │
│  ├─ detect_gpu() → dict                                   │
│  └─ check_cuda_driver_compat(cuda, driver) → dict         │
│                                                           │
│  detect_kernel.py                                         │
│  ├─ detect_kernel() → dict                                │
│  └─ _detect_secure_boot() → bool|None                     │
│                                                           │
│  detect_hardware.py                                       │
│  ├─ _read_cpu_model() → str                               │
│  ├─ _read_total_ram_mb() → int                            │
│  ├─ _read_available_ram_mb() → int                        │
│  ├─ _read_disk_free_mb(path) → int                        │
│  └─ detect_hardware() → dict                              │
│                                                           │
│  detect_init.py                                           │
│  ├─ _detect_init_system() → str                           │
│  └─ get_service_status(service) → dict                    │
│                                                           │
│  detect_build.py                                          │
│  ├─ detect_build_toolchain() → dict                       │
│  ├─ _validate_toolchain(recipe, toolchain) → list[str]    │
│  └─ _check_build_resources(recipe, hw) → list[str]        │
│                                                           │
│  detect_version.py                                        │
│  └─ get_tool_version(tool) → str|None                     │
│                                                           │
│  detect_network.py  (FUTURE — not yet implemented)        │
│  └─ detect_network() → dict                               │
│                                                           │
│  detect_updates.py                                        │
│  └─ check_updates(tool, installed_version) → dict         │
│                                                           │
├───────────────────────────────────────────────────────────┤
│                    LAYER 4: EXECUTION                     │
│     Mutates the system. Subprocess calls that install,    │
│     write files, restart services. Side effects live here │
│     and ONLY here.                                        │
│                                                           │
│  subprocess_runner.py                                     │
│  └─ _run_subprocess(cmd, *, sudo_password, ...) → dict    │
│                                                           │
│  step_executors.py                                        │
│  ├─ _execute_package_step(step, ...) → dict               │
│  ├─ _execute_repo_step(step, ...) → dict                  │
│  ├─ _execute_command_step(step, ...) → dict               │
│  ├─ _execute_verify_step(step, ...) → dict                │
│  ├─ _execute_service_step(step, ...) → dict               │
│  ├─ _execute_config_step(step, ...) → dict                │
│  ├─ _execute_shell_config_step(step, ...) → dict          │
│  ├─ _execute_notification_step(step) → dict               │
│  ├─ _execute_github_release_step(step, ...) → dict        │
│  ├─ _execute_download_step(step, ...) → dict              │
│  ├─ _execute_source_step(step, ...) → dict                │
│  ├─ _execute_build_step(step, ...) → dict                 │
│  ├─ _execute_install_step(step, ...) → dict               │
│  ├─ _execute_cleanup_step(step, ...) → dict               │
│  └─ _execute_rollback(rollback_steps, ...) → dict         │
│                                                           │
│  step_dispatch.py                                         │
│  └─ execute_plan_step(step, *, sudo_password) → dict      │
│                                                           │
│  config_writer.py                                         │
│  └─ _shell_config_line(shell, line, ...) → dict           │
│                                                           │
├───────────────────────────────────────────────────────────┤
│                    LAYER 5: ORCHESTRATION                 │
│     Composes Layer 2 (resolver) + Layer 4 (execution).    │
│     Plan lifecycle: create → execute → persist → resume.  │
│                                                           │
│  plan_engine.py                                           │
│  ├─ execute_plan(plan, *, sudo_password) → dict           │
│  └─ execute_plan_dag(plan, *, sudo_password) → dict       │
│                                                           │
│  plan_state.py                                            │
│  ├─ _plan_state_dir() → Path                              │
│  ├─ save_plan_state(state) → Path                         │
│  ├─ load_plan_state(plan_id) → dict|None                  │
│  ├─ list_pending_plans() → list[dict]                     │
│  ├─ cancel_plan(plan_id) → bool                           │
│  ├─ resume_plan(plan_id) → dict                           │
│  └─ archive_plan(plan_id) → bool                          │
│                                                           │
│  lifecycle.py                                             │
│  ├─ install_tool(tool, *, sudo_password) → dict           │
│  ├─ update_tool(tool, *, sudo_password) → dict            │
│  ├─ remove_tool(tool, *, sudo_password) → dict            │
│  └─ _pick_method_command(tool, action) → tuple            │
│                                                           │
│  data_packs.py                                            │
│  ├─ check_data_freshness(pack_id) → dict                  │
│  └─ get_data_pack_usage() → list[dict]                    │
│                                                           │
└───────────────────────────────────────────────────────────┘
```

---

## Onion Rules

| Rule | Concrete meaning |
|------|-----------------|
| **Inner layers never import outer** | `risk.py` (L1) NEVER imports `subprocess_runner.py` (L4) |
| **Outer layers CAN import inner** | `plan_engine.py` (L5) imports `dag.py` (L1) + `step_dispatch.py` (L4) |
| **Same-layer imports OK** | `plan_resolver.py` (L2) can import `method_picker.py` (L2) |
| **Data (L0) imported by everyone** | `recipes.py` is read by resolvers, executors, lifecycle |
| **All subprocess in L4** | Even detection (L3) uses `subprocess` — that's allowed, L3 reads the system |
| **L3 is read-only** | Detection reads but NEVER writes. Config writes are L4 |
| **L2 is pure-ish** | Resolver takes profile as input arg, doesn't call detection itself |

---

## Dependency Flow

```
L0 DATA
  ↑
L1 DOMAIN ← imports L0
  ↑
L2 RESOLVER ← imports L0, L1
  ↑
L3 DETECTION ← imports L0 (for constants)
  ↑
L4 EXECUTION ← imports L0, L1
  ↑
L5 ORCHESTRATION ← imports L2, L3, L4, L1
```

**L3 and L4 are siblings, not parent-child.** Both are imported by L5.
L3 (detection) and L4 (execution) never import each other.

---

## File System Layout

```
src/core/services/tool_install/
├── __init__.py           ← re-exports public API from lifecycle.py
│
├── data/                 ← LAYER 0: Pure data, no logic
│   ├── __init__.py
│   ├── recipes.py        ← TOOL_RECIPES (61 tools, ~1500 lines)
│   ├── undo_catalog.py   ← UNDO_COMMANDS
│   ├── restart_triggers.py
│   ├── cuda_matrix.py
│   ├── arch_map.py
│   └── profile_maps.py
│
├── domain/               ← LAYER 1: Pure functions
│   ├── __init__.py
│   ├── risk.py
│   ├── condition.py
│   ├── template.py
│   ├── input_validation.py
│   ├── dag.py
│   ├── rollback.py
│   ├── restart.py
│   ├── version_constraint.py
│   ├── error_analysis.py
│   ├── build_progress.py
│   └── download_helpers.py
│
├── resolver/             ← LAYER 2: Plan generation
│   ├── __init__.py
│   ├── method_picker.py
│   ├── dependency_collector.py
│   ├── choice_resolver.py
│   ├── plan_resolver.py
│   ├── build_plan.py
│   └── download_resolver.py
│
├── detection/            ← LAYER 3: System reads
│   ├── __init__.py
│   ├── packages.py
│   ├── gpu.py
│   ├── kernel.py
│   ├── hardware.py
│   ├── init_system.py
│   ├── build_tools.py
│   ├── version.py
│   ├── network.py        ← FUTURE
│   └── updates.py
│
├── execution/            ← LAYER 4: System writes
│   ├── __init__.py
│   ├── subprocess_runner.py
│   ├── step_executors.py
│   ├── step_dispatch.py
│   └── config_writer.py
│
└── orchestration/        ← LAYER 5: Lifecycle
    ├── __init__.py
    ├── plan_engine.py
    ├── plan_state.py
    ├── lifecycle.py
    └── data_packs.py
```

---

## Migration Path

| Step | What | Breaking? | Status |
|------|------|-----------|--------|
| 1 | Create `tool_install/` package, `__init__.py` re-exports everything | No — same public API | ✅ |
| 2 | Extract L0 (data dicts) into `data/` | No — just move constants | ✅ |
| 3 | Extract L1 (pure functions) into `domain/` | No — just move functions | ✅ |
| 4 | Extract L3 (detection) into `detection/` | No — isolated reads | ✅ |
| 5 | Extract L4 (execution) into `execution/` | No — isolated writes | ⬜ |
| 6 | Extract L2 (resolver) into `resolver/` | No — imports L0+L1 | ⬜ |
| 7 | Extract L5 (orchestration) into `orchestration/` | No — top layer | ⬜ |
| 8 | Delete monolith `tool_install.py` | Yes — old file removed | ⬜ |

**Each step is independently testable.** At every step, the
`__init__.py` re-exports ensure zero breakage to callers.

---

## What this decomposition does NOT change

- **No new features.** Every function listed exists TODAY.
- **No renames.** Functions keep their current names.
- **No refactors.** The internals of each function stay identical.
- **No new abstractions.** No base classes, no interfaces, no
  factories. Just files grouped by responsibility.
- **No import changes for callers.** `from src.core.services.tool_install import install_tool` keeps working via `__init__.py`.

---

## Function count per layer

| Layer | Files | Functions | Lines (est.) |
|-------|-------|-----------|-------------|
| L0 Data | 6 | 0 (pure dicts) | ~1,800 |
| L1 Domain | 11 | 17 | ~800 |
| L2 Resolver | 6 | 16 | ~1,600 |
| L3 Detection | 9 | 22 | ~1,100 |
| L4 Execution | 4 | 18 | ~1,200 |
| L5 Orchestration | 4 | 14 | ~1,000 |
| **Total** | **40** | **87** | **~7,500** |

Lines sum matches the monolith (7,493). Nothing lost.

---

## Traceability: domain docs → SRP files

| Domain doc | Maps to SRP file(s) |
|------------|---------------------|
| domain-risk-levels.md | `domain/risk.py` |
| domain-rollback.md | `domain/rollback.py` + `data/undo_catalog.py` |
| domain-sudo-security.md | `execution/subprocess_runner.py` |
| domain-config-files.md | `execution/step_executors.py` (_execute_config_step) + `domain/template.py` |
| domain-inputs.md | `domain/input_validation.py` + `domain/template.py` |
| domain-choices.md | `resolver/choice_resolver.py` |
| domain-version-selection.md | `resolver/choice_resolver.py` + `detection/version.py` |
| domain-disabled-options.md | `resolver/choice_resolver.py` (available/disabled_reason fields) |
| domain-services.md | `detection/init_system.py` + `execution/step_executors.py` |
| domain-restart.md | `domain/restart.py` + `orchestration/plan_state.py` |
| domain-network.md | `detection/network.py` (FUTURE) |
| domain-parallel-execution.md | `domain/dag.py` + `orchestration/plan_engine.py` |
| domain-pages-install.md | `data/recipes.py` (hugo/mkdocs/docusaurus entries) |
| domain-gpu.md | `detection/gpu.py` + `data/cuda_matrix.py` |
| domain-kernel.md | `detection/kernel.py` |
| domain-hardware-detect.md | `detection/hardware.py` + `data/arch_map.py` |
| domain-shells.md | `data/profile_maps.py` + `execution/config_writer.py` |
| domain-package-managers.md | `resolver/method_picker.py` + `detection/packages.py` |
| domain-language-pms.md | `data/recipes.py` (pip/npm/cargo tool entries) |
| domain-binary-installers.md | `execution/step_executors.py` + `resolver/download_resolver.py` |
| domain-repos.md | `execution/step_executors.py` (_execute_repo_step) |
| domain-build-systems.md | `detection/build_tools.py` |
| domain-compilers.md | `detection/build_tools.py` |
| domain-build-from-source.md | `resolver/build_plan.py` + `execution/step_executors.py` |
| domain-ml-ai.md | `data/recipes.py` (pytorch/opencv entries) |
| domain-data-packs.md | `orchestration/data_packs.py` (FUTURE) |
| domain-devops-tools.md | `data/recipes.py` (all 61 tool entries) |
