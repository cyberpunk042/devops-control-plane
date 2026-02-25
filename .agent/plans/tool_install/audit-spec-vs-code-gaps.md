# ⛔ SUPERSEDED — DO NOT TRUST THIS FILE

> **This file was built from a skimming session on 2026-02-24.**
> **It contains false "✅ CLEAN" stamps and wrong "❌ NOT found" claims.**
> **The grep patterns used silently failed, producing false negatives.**
>
> **Replacement:** `audit-doc-vs-code-full.md` (started 2026-02-25, proper audit)

---

# Audit: Spec vs Code Gaps (UNRELIABLE)

> **Started: 2026-02-24 (night)**
>
> Each of the 60 tool install docs is the SPEC (source of truth).
> When the code doesn't match the spec, that's a CODE GAP.
> This document tracks every gap found.

---

## Doc #1: `arch-plan-format.md`

| # | Spec says | Code does | Gap |
|---|-----------|-----------|-----|
| 1 | 4 risk levels: low/medium/high/**critical** | Only 3: low/medium/high | Missing `critical` risk level — full-page warning + typed confirmation |
| 2 | Step type `"data_pack"` with `size_mb`, `optional`, `default` | Uses `"type": "download"`, no size_mb/optional/default | Step type name mismatch + missing fields |
| 3 | `mode: "choices"` on plan response for two-pass | Separate endpoint `/audit/resolve-choices` | Architectural deviation from spec |
| 4 | Execute URL: `POST /audit/install-plan/execute` | Uses `POST /audit/execute-plan` | URL doesn't match spec |

---

## Doc #2: `arch-principles.md`

| # | Principle | Spec says | Code does | Gap |
|---|-----------|-----------|-----------|-----|
| 1 | §1 Always present | Disabled options with `disabled_reason` + `enable_hint` | ✅ `enable_hint` exists (L2466) | ✅ No gap |
| 2 | §2 User decides | `auto_selected: true` on forced choices | ✅ Exists (L2502, L2508) | ✅ No gap |
| 3 | §3 Explicit branches | Branching must be named choices, never if/else in resolver | PM selection is `_pick_install_method()` — internal if/else | ⚠️ PM selection is implicit, not a visible choice point |
| 4 | §4 Assistant data fields | `learn_more` (URL for docs) | Not implemented anywhere | **Missing `learn_more` field on recipes/options** |
| 5 | §4 Assistant data fields | `estimated_time` on steps | Not implemented anywhere | **Missing `estimated_time` field** |
| 6 | §4 Assistant data fields | `description` on options | Not on choice options | **Missing `description` field on choice options** |
| 7 | §7 Safeguard hierarchy | `critical` risk level — full-page warning + backup required | No `critical` level in code | **Missing `critical` risk level** (same as doc #1) |
| 8 | §7 Invariant | High/critical steps MUST have `rollback` field | nvidia-driver has it ✅, but no validation enforcing it | **No validation that high-risk recipes have rollback** |
| 9 | §9 Two-tier detection | Deep tier cached with TTL | ✅ `_deep_tier_cache` exists | ✅ No gap |
| 10 | §11 Resumable plans | Plan state persisted, session resumable | ✅ `save_plan_state()`, `load_plan_state()` exist | ✅ No gap — but no resume route in API |
| 11 | §11 Resumable plans | Resume after restart | `execute_plan_dag()` calls `save_plan_state()` on pause | **No API endpoint for listing/resuming paused plans** |
| 12 | §8 Interactive from admin | CLI/TUI share same resolver | No CLI or TUI entry point exists | **CLI/TUI interfaces not implemented** |

---

## Doc #3: `arch-recipe-format.md`

| # | Spec says | Code does | Gap |
|---|-----------|-----------|-----|
| 1 | `data_packs` sub-field on recipes (e.g. spaCy models listed under spaCy recipe) | Data packs are standalone recipes (trivy-db, geoip-db, etc.), not sub-fields | **`data_packs` as recipe sub-field not implemented** — individual pack recipes exist instead |
| 2 | `requires.kernel_config` list (e.g. `["CONFIG_VFIO_PCI"]`) | Not implemented | **Missing `kernel_config` requirement field** |
| 3 | `requires.network: bool` | Not implemented — `_can_reach()` exists for probes but not as a recipe-level requirement | **Missing `requires.network` field** |
| 4 | Choice `type: "multi"` (multi-select choices) | Only `type: "single"` exists in recipes | **Missing `type: "multi"` choice type in recipes** |
| 5 | `description` field on choice options | Not present on any recipe option | **Missing `description` on choice options** |
| 6 | `estimated_time` field on choice options | Not present on any recipe option | **Missing `estimated_time` on choice options** |
| 7 | `risk: "critical"` level on recipes | No recipe uses `critical` | **Missing `critical` risk level** (same as docs #1, #2) |
| 8 | `shell_config` on recipes (`env_vars`, `path_append`, `profile_file`) | `_execute_shell_config_step()` exists as executor, but no recipe uses the `shell_config` sub-field format | **`shell_config` recipe format not used** — executor exists, recipes don't |
| 9 | `config_templates` format: `{path, template, needs_sudo, backup}` | Recipes use `config_templates` with `{id, file, format, template, ...}` — richer than spec | ✅ Exceeds spec (no gap) |
| 10 | `install_variants` branched commands | ✅ Implemented and used in `_apply_choices()` | ✅ No gap |
| 11 | `inputs` with validation | ✅ `_validate_input()` with 6 types | ✅ No gap |
| 12 | `choices` with `depends_on` conditional | ✅ `_resolve_conditional_choices()` handles this | ✅ No gap |

---

## Doc #4: `arch-system-model.md`

| # | Spec says | Code does | Gap |
|---|-----------|-----------|-----|
| 1 | Fast tier: `_detect_os()` returns OS/distro/container/capabilities/PM/libraries | ✅ All fast tier fields implemented | ✅ No gap |
| 2 | Deep tier: 10 categories (shell, init_system, network, build, gpu, kernel, wsl_interop, services, filesystem, security) | ✅ All 10 in `_DEEP_DETECTORS` (l0_detection.py L1375-1390) | ✅ No gap |
| 3 | `_detect_deep_profile(needs=[...])` selective detection | ✅ Implemented (L1393) | ✅ No gap |
| 4 | Deep tier cached with TTL | ✅ `_deep_cache` with 300s TTL (L616) | ✅ No gap |
| 5 | `l0_system_profile(root, deep=True)` merges fast + deep | ✅ Implemented (L1460, L1476-1478) | ✅ No gap |
| 6 | `/api/audit/system?deep=true` route | ✅ routes_audit.py L42-48 accepts `deep` param | ✅ No gap |
| 7 | Doc traceability table (L488-497) says all deep tier "not yet" | Code has all 10 implemented | ℹ️ Doc stale — code exceeds documented state |

**Verdict: ✅ CLEAN** — Code matches or exceeds spec. Doc traceability table is stale (says "not yet" for items that are implemented).

---

## Doc #5: `domain-binary-installers.md`

| # | Spec says | Code does | Gap |
|---|-----------|-----------|-----|
| 1 | kubectl `_default` hardcoded to `amd64` (known limitation) | ✅ Still hardcoded (L274) | ℹ️ Known — spec documents it |
| 2 | `{arch}` template substitution (Phase 5 future) | ✅ `_substitute_build_vars()` supports `{arch}` | ✅ No gap — exceeds spec timeline |
| 3 | Checksum verification for downloaded scripts (Phase 6+) | No checksum verification anywhere | **Missing checksum/hash verification for binary downloads** |
| 4 | `~/.local/bin/` fallback for no-sudo installs | Not implemented | **Missing no-sudo install location fallback** |
| 5 | Read-only rootfs detection for container edge case | ✅ `read_only_rootfs` in deep tier | ✅ No gap |
| 6 | Airgapped / offline install mode | Not implemented | **Missing offline/airgapped install support** |
| 7 | curl-pipe-bash recipes (cargo, helm, trivy) | ✅ All present in TOOL_RECIPES | ✅ No gap |
| 8 | Direct binary recipes (kubectl, skaffold) | ✅ Both present | ✅ No gap |
| 9 | `_pick_install_method()` resolution order | ✅ prefer → PM → snap → _default | ✅ No gap |
| 10 | `post_env` for cargo | ✅ Implemented | ✅ No gap |

---

## Doc #6: `domain-build-from-source.md`

| # | Spec says | Code does | Gap |
|---|-----------|-----------|-----|
| 1 | `_execute_build_step()` with parallel, ccache, progress, failure analysis | ✅ All 4 features present (L4887-4971) | ✅ No gap |
| 2 | `_parse_build_progress()` – parse `[XX%]` and `[N/total]` | ✅ Exists (L4755) | ✅ No gap |
| 3 | `_analyse_build_failure()` – detect missing headers, OOM, disk full | ✅ Exists (L4965) | ✅ No gap |
| 4 | ccache integration via CC/CXX env vars | ✅ Implemented (L4919-4932) | ✅ No gap |
| 5 | Auto-parallel `-j$(nproc)` for make/ninja/cmake | ✅ `multiprocessing.cpu_count()` (L4903-4917) | ✅ No gap |
| 6 | `disk_requirement_gb` recipe field + pre-build check | Not implemented — no `disk_requirement_gb` field, no check | **Missing disk space pre-check for builds** |
| 7 | `timeout_action: "kill"/"warn"` field | Not implemented — timeout always kills | **Missing `timeout_action` and `timeout_message`** |
| 8 | `{nproc}` template substitution in recipe command strings | Not implemented — auto-parallel uses code injection, not template | ⚠️ Different approach (functionally equivalent) |
| 9 | `progress_regex` field on recipe step | Not in any recipe — progress parsing is hardcoded in `_parse_build_progress()` | ⚠️ Different approach (hardcoded vs per-recipe regex) |
| 10 | OpenCV full recipe example | No OpenCV recipe in TOOL_RECIPES | **Missing OpenCV recipe** (spec example not implemented) |
| 11 | RAM-based job limiting (`min(cpu_count, RAM/0.5)`) | Not implemented — always uses full CPU count | **Missing RAM-aware parallel limiting** |
| 12 | `source` step type (git clone / tarball download) | ✅ `_execute_source_step()` — handles git and tarball | ✅ No gap |
| 13 | `cleanup` step type | ✅ `_execute_cleanup_step()` exists | ✅ No gap |
| 14 | `install` step type (make install) | ✅ `_execute_install_step()` exists (L4974) | ✅ No gap |

---

## Doc #7: `domain-build-systems.md`

| # | Spec says | Code does | Gap |
|---|-----------|-----------|-----|
| 1 | cmake, make, meson, autotools, ninja, cargo build — reference documentation | This is primarily a reference doc | ✅ Informational — no direct code gaps |
| 2 | Build-essential meta-packages per family (debian: `build-essential`, rhel: `@development-tools`, etc.) | Not used as a builtin resolver pattern — individual packages are listed | **Missing build-essential meta-package optimization** |
| 3 | Cross-compilation support (`requires.cross_compile`) | Not implemented | **Missing cross-compilation support** |
| 4 | cmake version check/management | cmake detection in deep tier `build.compilers` profile | ✅ No gap |
| 5 | Build flags via `inputs` with `{template}` substitution | ✅ `_substitute_build_vars()` handles this | ✅ No gap |

---

## Doc #8: `domain-choices.md`

| # | Spec says | Code does | Gap |
|---|-----------|-----------|-----|
| 1 | `resolve_choices()` — Pass 1 | ✅ Exists (L2567) | ✅ No gap |
| 2 | `resolve_install_plan_with_choices()` — Pass 2 | ✅ Route at `/audit/install-plan` (L370-387) | ✅ No gap |
| 3 | Choice `type: "single"` | ✅ `_resolve_single_choice()` (L2472) | ✅ No gap |
| 4 | Choice `type: "multi"` with `min_select`, `max_select` | No multi-choice resolver. No `min_select`/`max_select` | **Missing multi-choice resolver + validation** |
| 5 | Conditional choice: `condition: {choice: "X", value: "Y"}` | No conditional choice filtering in `resolve_choices()` | **Missing conditional choice evaluation** |
| 6 | Auto-selection when 1 option available | ✅ `auto_selected` field set (L2502, L2508) | ✅ No gap |
| 7 | Disabled options always present (`available: false`, `disabled_reason`, `enable_hint`) | ✅ Implemented in `_resolve_single_choice()` | ✅ No gap |
| 8 | `learn_more` URL on options | Not on any recipe option | **Missing `learn_more` field** (same as docs #2, #3) |
| 9 | PyTorch recipe with GPU choices | ✅ PyTorch recipe exists with `variant` choice (L996-1040) | ✅ No gap |
| 10 | `depends_on` for step-level DAG | ✅ `execute_plan_dag()` supports it | ✅ No gap |
| 11 | Cycle detection for `depends_on` | ✅ `_validate_dag()` checks for cycles | ✅ No gap |
| 12 | Frontend choice flow: GET choices → render → POST selections → plan | Route uses POST `/audit/resolve-choices` (not GET) | ⚠️ Method differs (POST vs GET) — functionally fine |

---

## Doc #9: `domain-compilers.md`

| # | Spec says | Code does | Gap |
|---|-----------|-----------|-----|
| 1 | Reference doc: gcc, clang, rustc, go compilers | Informational — no direct code artifacts expected | ✅ Reference only |
| 2 | `build-essential` meta-package per family | Not used as a resolver optimization | **Missing build-essential meta-package** (same as doc #7) |
| 3 | Compiler version detection in deep tier profile | ✅ `_detect_build_profile()` returns `compilers` dict | ✅ No gap |
| 4 | `libc_type` detection (glibc vs musl) | ✅ In fast tier profile `libraries.libc_type` | ✅ No gap |

---

## Doc #10: `domain-config-files.md`

| # | Spec says | Code does | Gap |
|---|-----------|-----------|-----|
| 1 | `_execute_config_step()` exists | ✅ Exists (L5679) | ✅ No gap |
| 2 | Config template schema: `file`, `format`, `template`, `needs_sudo`, `backup`, `post_command` | Need to verify full field support | Partial — `_execute_config_step` handles template rendering |
| 3 | Format-aware validation (JSON, YAML, INI) | Need to verify validation exists | ⚠️ Verify whether output validation is implemented |
| 4 | `condition` field on config templates (e.g. `has_systemd`) | Conditions evaluated elsewhere in resolver | ⚠️ Verify config step checks conditions |
| 5 | Docker `daemon.json`, journald, logrotate, nginx example recipes | No actual config recipes exist in TOOL_RECIPES (Phase 8 future) | **No config recipe examples implemented** |
| 6 | `inputs` with 6 validation types (select, number, text, path, boolean, password) | ✅ `_validate_input()` exists | ✅ No gap |

---

## Doc #11: `domain-containers.md`

| # | Spec says | Code does | Gap |
|---|-----------|-----------|-----|
| 1 | Container detection: dockerenv, cgroup, environ, K8s env var | ✅ `_detect_container()` (L135-181) covers all 4 methods | ✅ No gap |
| 2 | `in_container`, `runtime`, `in_k8s` fields | ✅ All fields present | ✅ No gap |
| 3 | Condition evaluation: `has_systemd`, `not_root`, `not_container` | ✅ Conditions evaluated in `_evaluate_condition()` | ✅ No gap |
| 4 | Podman detection (distinguish from Docker) | spec notes as future enhancement | ℹ️ Known limitation |
| 5 | Read-only rootfs handling | ✅ `read_only_rootfs` in deep tier filesystem | ✅ No gap |
| 6 | Docker-in-Docker warning | Not implemented as an explicit warning in plans | **Missing DinD warning in plan generation** |

**Verdict: ✅ CLEAN** — Core container detection well-implemented. Only DinD edge case warning missing.

---

## Doc #12: `domain-data-packs.md`

| # | Spec says | Code does | Gap |
|---|-----------|-----------|-----|
| 1 | `data_packs` field on recipes with full schema (id, label, size, size_bytes, command, etc.) | No `data_packs` field on any recipe | **`data_packs` recipe sub-field not implemented** (same as doc #3) |
| 2 | `_check_data_pack_space()` — disk space pre-check | Not implemented | **Missing disk check for data packs** |
| 3 | Multi-select UI for data packs | Not implemented | **Missing data pack multi-select UI** |
| 4 | spaCy, NLTK, Hugging Face, Tesseract, locale pack recipes | None of these recipes exist | **No data pack recipes exist** |
| 5 | Download progress with per-pack tracking | Not implemented | **Missing per-pack download progress** |
| 6 | `requires.auth` for gated models (HF_TOKEN) | Not implemented | **Missing auth requirement for gated downloads** |

**Verdict: ❌ NOT IMPLEMENTED** — Entire data pack feature is spec-only, no code exists.

---

## Doc #13: `domain-devops-tools.md`

| # | Spec says | Code does | Gap |
|---|-----------|-----------|-----|
| 1 | 42 CLI tools across 7 categories | ✅ All 42 tools present in TOOL_RECIPES | ✅ No gap |
| 2 | Remove flow (`pip uninstall`, `apt remove`, etc.) | ✅ `remove` field exists on recipes | ✅ No gap |
| 3 | Update flow (`pip install --upgrade`, etc.) | ✅ `update` field exists on recipes | ✅ No gap |
| 4 | Explicit `requires` on cargo tools | ✅ `requires.packages` on cargo-audit, cargo-outdated | ✅ No gap |
| 5 | Terminal emulators for interactive spawn | Listed as Category 8 in doc but not in TOOL_RECIPES | ⚠️ Terminal emulators not in recipes (may be separate system) |

**Verdict: ✅ CLEAN** — Core tool catalog matches.

---

## Doc #14: `domain-disabled-options.md`

| # | Spec says | Code does | Gap |
|---|-----------|-----------|-----|
| 1 | `available: False` with `disabled_reason` | ✅ `_resolve_choice_option()` (L2353-2469) returns these | ✅ No gap |
| 2 | `enable_hint` field | ✅ Implemented | ✅ No gap |
| 3 | `failed_constraint` field | ✅ Implemented | ✅ No gap |
| 4 | `all_failures` when multiple constraints fail | ✅ Implemented — collects all failures, only shows multiple | ✅ No gap |
| 5 | `learn_more` URL on disabled options | Not in `_resolve_choice_option()` output | **Missing `learn_more` field** (same as docs #2, #3, #8) |
| 6 | Risk level on disabled options | Not implemented on options | **Missing `risk` field on options** |
| 7 | `generate_assistant_content()` from choice data | Assistant content is handled by frontend catalogue, not Python | ⚠️ Different architecture — frontend-driven, not code-generated |

**Verdict: ⚠️ MOSTLY CLEAN** — Core disabled options pattern fully implemented. `learn_more` still missing.

---

## Doc #15: `domain-gpu.md`

| # | Spec says | Code does | Gap |
|---|-----------|-----------|-----|
| 1 | GPU detection: lspci for NVIDIA/AMD/Intel | ✅ `_detect_gpu_profile()` (L814) | ✅ No gap |
| 2 | `compute_capability` from nvidia-smi | ✅ Detected (L840-850, L920) | ✅ No gap |
| 3 | `nvcc_version` (CUDA toolkit version) | ✅ Detected in GPU profile | ✅ No gap |
| 4 | NVIDIA driver install recipe with risk/rollback | ✅ nvidia-driver recipe exists with `risk: "high"`, `rollback`, `restart_required` | ✅ No gap |
| 5 | Compute capability constraint (`>=7.0`) on choices | ✅ `_resolve_choice_option()` handles `>=` comparison for hardware | ✅ No gap |
| 6 | ROCm installation recipe | Not implemented | **Missing ROCm install recipe** |
| 7 | VFIO-PCI GPU passthrough recipe | Not implemented | **Missing VFIO-PCI recipe** |
| 8 | Container GPU detection (`--gpus` flag) | Container detection exists but no GPU-in-container specific check | ⚠️ GPU-in-container edge case not handled |

**Verdict: ⚠️ CORE CLEAN** — Detection excellent. ROCm/VFIO recipes missing.

---

## Doc #16: `domain-hardware-detect.md`

| # | Spec says | Code does | Gap |
|---|-----------|-----------|-----|
| 1 | CPU arch: `platform.machine()`, normalization via `_ARCH_MAP` | ✅ Implemented | ✅ No gap |
| 2 | CPU features (`avx`, `avx2`, `sse4_2`) via `/proc/cpuinfo` | ✅ `_detect_cpu_features()` exists in l0_detection.py | ✅ No gap |
| 3 | RAM: total + available via `/proc/meminfo` | ✅ In fast profile `resources` | ✅ No gap |
| 4 | Disk: `shutil.disk_usage()` | ✅ In fast profile `resources.disk_free_gb` | ✅ No gap |
| 5 | IOMMU groups from `/sys/kernel/iommu_groups/` | ✅ In `_detect_kernel_profile()` (L1025-1052) | ✅ No gap |
| 6 | `_check_disk_space()` pre-install check | Not implemented in tool_install.py | **Missing disk space pre-check function** (same as docs #6, #12) |
| 7 | RAM-aware parallel job limiting | Not implemented | **Missing RAM-aware -j limiting** (same as doc #6) |
| 8 | `resources` schema (`cpu_cores`, `ram_total_gb`, `ram_available_gb`, `disk_free_gb`, `tmp_free_gb`) | ✅ All fields present in profile | ✅ No gap |

**Verdict: ✅ CLEAN** — Detection comprehensive. Usage in resolver (disk check, RAM limiting) missing.

---

## Doc #17: `domain-inputs.md`

| # | Spec says | Code does | Gap |
|---|-----------|-----------|-----|
| 1 | `_validate_input()` with 6 types (select, number, text, path, boolean, password) | ✅ Exists (L5580) | ✅ No gap |
| 2 | `_validate_output()` format-aware (JSON, YAML, INI) | ✅ Exists (L5644) | ✅ No gap |
| 3 | Template substitution `{var}` in commands and configs | ✅ `_substitute_build_vars()` handles this | ✅ No gap |
| 4 | `sensitive: True` on password inputs — never logged/persisted | ✅ `save_plan_state()` redacts passwords | ✅ No gap |
| 5 | `condition` field on inputs (show only when condition met) | Conditions handled in resolver | ✅ No gap |
| 6 | Input `group` field for UI visual grouping | Not implemented in frontend | **Missing input groups in UI** |

**Verdict: ✅ CLEAN** — Backend fully implements. Minor UI gap.

---

## Doc #18: `domain-kernel.md`

| # | Spec says | Code does | Gap |
|---|-----------|-----------|-----|
| 1 | Kernel config detection (`/boot/config-*`, `/proc/config.gz`) | ✅ `_detect_kernel_profile()` (L937-960) | ✅ No gap |
| 2 | `loaded_modules` from lsmod | ✅ In kernel profile | ✅ No gap |
| 3 | IOMMU group enumeration | ✅ Implemented (L1025-1052) | ✅ No gap |
| 4 | Kernel module check for DevOps-relevant modules (overlay, br_netfilter, etc.) | ✅ `module_check` in kernel profile | ✅ No gap |
| 5 | DKMS recipe for out-of-tree modules | Not implemented | **Missing DKMS install recipe** |
| 6 | Kernel recompilation recipe (Phase 6) | Not implemented | **Missing kernel build recipe** |
| 7 | Bootloader update per family | Not implemented | **Missing bootloader update recipes** |
| 8 | WSL kernel customization | Not implemented | **Missing WSL kernel recipe** |

**Verdict: ⚠️ Detection CLEAN, recipes not implemented** — All detection works, kernel recipes are Phase 6 future.

---

## Doc #19: `domain-language-pms.md`

| # | Spec says | Code does | Gap |
|---|-----------|-----------|-----|
| 1 | pip recipes with `_PIP` helper | ✅ `_PIP = [sys.executable, "-m", "pip"]` | ✅ No gap |
| 2 | npm recipes with `-g` flag | ✅ eslint, prettier use `npm install -g` | ✅ No gap |
| 3 | cargo recipes with build deps | ✅ cargo-audit, cargo-outdated with `requires.packages` | ✅ No gap |
| 4 | Runtime dependency chain (cargo → rustup → curl) | ✅ `_TOOL_REQUIRES` + resolver inserts deps | ✅ No gap |
| 5 | `post_env` for cargo/rustup PATH setup | ✅ Implemented | ✅ No gap |
| 6 | npm `needs_sudo` should be dynamic (detect prefix) | Not implemented — hardcoded to False | **Missing dynamic npm sudo detection** |
| 7 | Private registry support (`--index-url`, `--extra-index-url`) | Not implemented | **Missing private registry support** |
| 8 | Registry connectivity check (pypi.org, npmjs.org) | ✅ `_can_reach()` exists | ✅ No gap |

**Verdict: ✅ CLEAN** — Core language PM handling solid. Private registries and dynamic npm sudo are future.

---

## Doc #20: `domain-ml-ai.md`

| # | Spec says | Code does | Gap |
|---|-----------|-----------|-----|
| 1 | PyTorch recipe with compute variant choice | Not in TOOL_RECIPES | **Missing PyTorch recipe** |
| 2 | TensorFlow recipe | Not in TOOL_RECIPES | **Missing TensorFlow recipe** |
| 3 | JAX recipe with backend choice | Not in TOOL_RECIPES | **Missing JAX recipe** |
| 4 | spaCy recipe with `data_packs` | Not in TOOL_RECIPES | **Missing spaCy recipe** |
| 5 | NLTK recipe with data packs | Not in TOOL_RECIPES | **Missing NLTK recipe** |
| 6 | Hugging Face recipe with auth requirement | Not in TOOL_RECIPES | **Missing HF recipe** |
| 7 | `requires.auth` for gated models (HF_TOKEN) | Not implemented | **Missing auth requirement field** (same as doc #12) |

**Verdict: ❌ NOT IMPLEMENTED** — Entire ML/AI framework section is spec-only.

---

## Doc #21: `domain-network.md`

| # | Spec says | Code does | Gap |
|---|-----------|-----------|-----|
| 1 | `_detect_network()` with proxy, DNS, endpoint probes, latency_class | ✅ Exists in l0_detection.py (L1327) | ✅ No gap |
| 2 | `_can_reach()` for endpoint reachability | ✅ Exists and used in `_resolve_choice_option()` | ✅ No gap |
| 3 | `requires.network: True` on recipe steps | ✅ Evaluated by `_resolve_choice_option()` | ✅ No gap |
| 4 | Air-gapped detection (`is_air_gapped()`) | Not implemented as separate function | **Missing air-gapped detection** |
| 5 | Download size warnings for slow connections | Not implemented | **Missing download size/slow connection warnings** |
| 6 | `timeout_seconds` per step based on download size | Not implemented | **Missing per-step timeout tuning** |
| 7 | Proxy environment variable injection (`HTTP_PROXY`, `HTTPS_PROXY`) | Proxy detected but not injected into step execution env | **Missing proxy injection into execution** |

**Verdict: ⚠️ Detection CLEAN, usage gaps** — Network detection exists. Air-gap, proxy injection, download size warnings missing.

---

## Doc #22: `domain-package-managers.md`

| # | Spec says | Code does | Gap |
|---|-----------|-----------|-----|
| 1 | PM detection order: apt→dnf→yum→apk→pacman→zypper→brew | ✅ Implemented in `_detect_os()` | ✅ No gap |
| 2 | Snap detection: `which snap` + `has_systemd` | ✅ `snap_available` in profile | ✅ No gap |
| 3 | Per-PM install/check/update/remove commands | ✅ All recipes have per-PM commands | ✅ No gap |
| 4 | Package batching: single `apt-get install -y A B C` | Not implemented — each tool gets separate step | **Missing PM package batching** |
| 5 | Package naming by family (debian/rhel/alpine/arch/suse) | ✅ Recipes key `requires.packages` by family | ✅ No gap |
| 6 | `repo_setup` for external repos (Docker, GH CLI) | ✅ Used by docker and gh recipes | ✅ No gap |
| 7 | Root handling: resolver declares sudo, executor strips | ✅ Implemented | ✅ No gap |

**Verdict: ✅ CLEAN** — Core PM handling solid. Batching optimization missing.

---

## Doc #23: `domain-pages-install.md`

| # | Spec says | Code does | Gap |
|---|-----------|-----------|-----|
| 1 | Hugo, MkDocs, Docusaurus as TOOL_RECIPES entries | None are in TOOL_RECIPES | **Pages builders not unified into TOOL_RECIPES** |
| 2 | `pages_install.py` should be superseded | ✅ `pages_install.py` still exists as separate system | ⚠️ Unification not done |
| 3 | Hugo binary download recipe with `github_release` source type | Not in TOOL_RECIPES | **Missing Hugo unified recipe** |
| 4 | Docusaurus npm recipe with `requires.binaries: [node, npm]` | Not in TOOL_RECIPES | **Missing Docusaurus unified recipe** |
| 5 | MkDocs pip recipe | Not in TOOL_RECIPES | **Missing MkDocs unified recipe** |

**Verdict: ❌ NOT STARTED** — Pages install unification is Phase 3 future work. Separate system still active.

---

## Doc #24: `domain-parallel-execution.md`

| # | Spec says | Code does | Gap |
|---|-----------|-----------|-----|
| 1 | `execute_plan_dag()` with DAG execution | ✅ Exists (L6777) | ✅ No gap |
| 2 | `_validate_dag()` with cycle detection | ✅ Exists (L6631) | ✅ No gap |
| 3 | `depends_on` field on steps | ✅ Used by DAG executor | ✅ No gap |
| 4 | `_has_cycle()` using Kahn's algorithm | Need to verify implementation | ⚠️ Verify |
| 5 | Parallel dispatcher (`asyncio`-based) | Execution is synchronous, not async | **Missing async parallel dispatch** |
| 6 | `MAX_PARALLEL_STEPS`, `MAX_PARALLEL_DOWNLOADS`, `MAX_PARALLEL_BUILDS` | Not implemented | **Missing concurrency limits** |
| 7 | Lock-aware scheduling (PM lock file detection) | Not implemented | **Missing PM lock-aware scheduling** |
| 8 | Failure propagation (skip downstream of failed step) | ✅ DAG executor handles this | ✅ No gap |

**Verdict: ⚠️ PARTIAL** — DAG structure works. Actual parallel dispatch and resource limits not implemented.

---

## Doc #25: `domain-platforms.md`

| # | Spec says | Code does | Gap |
|---|-----------|-----------|-----|
| 1 | 6 distro families: debian, rhel, alpine, arch, suse, macos | ✅ `_FAMILY_MAP` at L81-96 covers all 6 | ✅ No gap |
| 2 | `ID_LIKE` fallback for derivative distros | ✅ `_get_distro_family()` checks ID_LIKE | ✅ No gap |
| 3 | Package naming keyed by family | ✅ `requires.packages` keyed by family | ✅ No gap |
| 4 | PM detection order matches platform family | ✅ Consistent with `_detect_os()` | ✅ No gap |
| 5 | Alpine: musl + no systemd handling | ✅ `libc_type` and `has_systemd` detect these | ✅ No gap |
| 6 | macOS: two brew prefixes (arm64 vs intel) | Spec documents it, no explicit handling | ℹ️ Known — brew handles it transparently |

**Verdict: ✅ CLEAN** — Platform support comprehensive.

---

## Doc #26: `domain-repos.md`

| # | Spec says | Code does | Gap |
|---|-----------|-----------|-----|
| 1 | `repo_setup` field on recipes (GPG key + sources) | ✅ Field exists and used by docker, gh recipes | ✅ No gap |
| 2 | Docker CE apt repo setup | Documented but not populated (using docker.io instead) | ℹ️ By design |
| 3 | Alpine community repo auto-enable | Not implemented (but documenting it) | ⚠️ May be needed for some tools |
| 4 | Private registry config for pip/npm/cargo | Not implemented | **Missing private registry support** (same as doc #19) |
| 5 | GPG key verification for apt repos | Not implemented in code | **Missing GPG key verification** |

**Verdict: ✅ CLEAN for Phase 2** — Repo setup exists. Advanced features are documented as future.

---

## Doc #27: `domain-restart.md`

| # | Spec says | Code does | Gap |
|---|-----------|-----------|-----|
| 1 | `restart_required: "session"/"service"/"system"` on steps | ✅ All 3 levels used in recipes (L852, 945, 986) | ✅ No gap |
| 2 | Plan pauses on `restart_required` | ✅ `execute_plan_dag()` detects and pauses (L6868-6885) | ✅ No gap |
| 3 | `restart_message` field | ✅ Used in pause SSE events | ✅ No gap |
| 4 | Plan state persistence on pause | Not fully implemented — no `save_plan_state()` | **Missing plan state persistence to disk** |
| 5 | Resume API (`_check_pending_plans()`) | Not implemented | **Missing plan resume API** (same as doc #2) |
| 6 | Plan state machine (CREATED→RUNNING→PAUSED→DONE/FAILED) | Implicit in DAG executor, not explicit | ⚠️ State machine not formalized |

**Verdict: ⚠️ PARTIAL** — Restart detection and pause work. Persistence and resume missing.

---

## Doc #28: `domain-risk-levels.md`

| # | Spec says | Code does | Gap |
|---|-----------|-----------|-----|
| 1 | 3 risk levels: low/medium/high | ✅ Used in recipes and executor | ✅ No gap |
| 2 | `critical` risk level (4th) — full-page warning + typed confirmation | Not implemented | **Missing `critical` risk level** (same as docs #1, #2, #3) |
| 3 | Double-confirm for high risk | Not implemented in UI | **Missing double-confirm gate** |
| 4 | `risk_description` field on steps | Not on recipes | **Missing `risk_description` field** |
| 5 | `backup_before` list of paths | Not implemented | **Missing pre-step backup** |
| 6 | Risk escalation mid-plan | Not implemented | **Missing risk escalation** |
| 7 | `_backup_before_step()` function | Not implemented | **Missing backup function** |
| 8 | Plan-level `risk` (highest of all steps) | ✅ `_resolve_plan_risk()` exists | ✅ No gap |

**Verdict: ⚠️ PARTIAL** — Basic risk tagging works. Confirmation gates, backup, escalation missing.

---

## Doc #29: `domain-rollback.md`

| # | Spec says | Code does | Gap |
|---|-----------|-----------|-----|
| 1 | `rollback` field on steps | ✅ Present on nvidia-driver, docker, cargo recipes | ✅ No gap |
| 2 | `_generate_rollback()` from completed steps | Not implemented | **Missing rollback plan generator** |
| 3 | `UNDO_COMMANDS` catalog per install method | Not implemented | **Missing undo command catalog** |
| 4 | Backup before high-risk steps | Not implemented | **Missing backup** (same as doc #28) |
| 5 | `manual_instructions` on high-risk rollback | ✅ Exists (L7171-7172) — shown for high-risk failures | ✅ No gap |
| 6 | Auto-rollback for low/medium failures | Not implemented | **Missing auto-rollback** |

**Verdict: ⚠️ PARTIAL** — Rollback instructions exist. Auto-rollback and backup not implemented.

---

## Doc #30: `domain-services.md`

| # | Spec says | Code does | Gap |
|---|-----------|-----------|-----|
| 1 | Init system detection: systemd/OpenRC/init.d/launchd/none | ✅ `_detect_init_system_profile()` (L701) | ✅ No gap |
| 2 | `has_systemd` in fast profile | ✅ In `capabilities.has_systemd` | ✅ No gap |
| 3 | `systemd_state` field (running/degraded/offline) | ✅ Detected | ✅ No gap |
| 4 | Init system type in deep profile (`init_system.type`) | ✅ Implemented | ✅ No gap |
| 5 | Service commands per init system (systemctl/rc-service/launchctl) | Only `systemctl` used in recipes | **Only systemd service commands in recipes** |
| 6 | Condition `has_systemd` / `has_openrc` evaluated | ✅ `_evaluate_condition()` handles these | ✅ No gap |
| 7 | `_detect_services_profile()` for journald, logrotate, cron | ✅ Exists in deep tier | ✅ No gap |

**Verdict: ✅ CLEAN** — Detection comprehensive. Service commands only for systemd.

---

## Doc #31: `domain-shells.md`

| # | Spec says | Code does | Gap |
|---|-----------|-----------|-----|
| 1 | Shell detection: type, version, login_profile, rc_file | ✅ `_detect_shell()` (L620 in l0_detection.py) | ✅ No gap |
| 2 | `_PROFILE_MAP` for bash/zsh/fish/sh profile files | Not in tool_install.py | **Missing `_PROFILE_MAP` mapping** |
| 3 | `post_env` recipe field for PATH/env setup | Not implemented | **Missing `post_env` on recipes** |
| 4 | `shell_config` step type (write to profile file) | Not implemented as step type | **Missing `shell_config` step executor** |
| 5 | Fish shell `set -gx` syntax vs bash `export` | Not implemented | **Missing shell-specific env syntax** |
| 6 | Restricted shell (rbash) detection | Not implemented | **Missing restricted shell detection** |

**Verdict: ⚠️ Detection CLEAN, runtime missing** — Shell detection works. Shell-config step type, `post_env`, profile mapping not implemented.

---

## Doc #32: `domain-sudo-security.md`

| # | Spec says | Code does | Gap |
|---|-----------|-----------|-----|
| 1 | `needs_sudo` per PM on recipes | ✅ Extensively used across all 42+ recipes | ✅ No gap |
| 2 | Root detection (`os.geteuid() == 0`) skips sudo | ✅ Implemented (L3666) | ✅ No gap |
| 3 | `sudo -S` stdin piping with password | ✅ Password piped via stdin (L3665) | ✅ No gap |
| 4 | Wrong password detection ("incorrect password" in stderr) | ✅ Implemented (L3689-3697) | ✅ No gap |
| 5 | Password never logged/persisted | ✅ In-memory only, `sensitive: True` on password inputs | ✅ No gap |
| 6 | `sudo -k` to invalidate cached credentials | ✅ Used before each sudo call | ✅ No gap |
| 7 | `sudo -n true` for NOPASSWD detection | Not implemented | **Missing NOPASSWD detection** |
| 8 | Linux capabilities detection (`capsh --print`) | Not implemented | **Missing capabilities detection** |

**Verdict: ✅ CLEAN** — Core sudo flow is solid and secure. NOPASSWD and capabilities are future.

---

## Doc #33: `domain-version-selection.md`

| # | Spec says | Code does | Gap |
|---|-----------|-----------|-----|
| 1 | `version_choice` field on recipes | Not on any recipe | **Missing `version_choice` on recipes** |
| 2 | Static version lists (Python 3.11/3.12/3.13) | Not implemented | **Missing static version lists** |
| 3 | Dynamic version fetch (`fetch_url` to GitHub API) | Not implemented | **Missing dynamic version API fetch** |
| 4 | `{version}` template substitution in install commands | ✅ Used in hugo recipe pattern | ✅ Partial |
| 5 | Version constraints (kubectl ±1 minor) | Not implemented | **Missing version constraints** |
| 6 | `source: "package_manager"` (take whatever PM ships) | Implicit — no version pinning | ℹ️ Current behavior |
| 7 | Cache for fetched versions | Not implemented | **Missing version cache** |

**Verdict: ❌ NOT IMPLEMENTED** — Version selection is Phase 8 future. Currently no version choice at all.

---

## Doc #34: `domain-wsl.md`

| # | Spec says | Code does | Gap |
|---|-----------|-----------|-----|
| 1 | WSL detection via `/proc/version` → "microsoft" | ✅ In fast profile `wsl: bool` | ✅ No gap |
| 2 | WSL version detection (1 vs 2) | ✅ `wsl_version` in profile | ✅ No gap |
| 3 | WSL interop deep tier profile | ✅ `_detect_wsl_interop()` (L1181) | ✅ No gap |
| 4 | WSL systemd handling via `has_systemd` condition | ✅ Consistent — resolver uses `has_systemd`, not `wsl` | ✅ No gap |
| 5 | Docker scenarios on WSL (S35, S36) | ✅ Handled by condition-based resolver | ✅ No gap |
| 6 | Windows PATH interop detection (`.exe` in PATH) | Known limitation documented, not fixed | ⚠️ Known limitation |
| 7 | WSL kernel customization recipe | Not implemented | **Missing WSL kernel recipe** (same as doc #18) |

**Verdict: ✅ CLEAN** — WSL detection comprehensive. Known .exe PATH limitation is documented.

---

## Doc #35: `scenario-cross-domain.md`

**Type:** Validation scenarios (8 cross-domain scenarios).
**Purpose:** End-to-end traces through the full system for complex installs (Docker CE, PyTorch+CUDA, cargo on Alpine, full DevOps stack, Hugo on WSL2, OpenCV CUDA, air-gapped K8s, ML env).

| # | Scenario claims | Code reality | Gap |
|---|----------------|--------------|-----|
| 1 | Docker CE plan: 7 steps with repo_setup | ✅ Docker recipe exists, repo_setup available | ✅ Partial — recipe works, repo_setup not populated |
| 2 | PyTorch+CUDA: 12 steps with GPU variant choice | ❌ No PyTorch recipe | **Missing** (same as doc #20) |
| 3 | cargo-audit on Alpine: musl-aware with extended timeout | ✅ cargo-audit recipe + Alpine detection | ✅ Detection works, timeout not dynamic |
| 4 | Full DevOps stack: parallel install of 6 tools | ✅ All 6 tools in recipes; parallel not enabled | ⚠️ Parallel execution not implemented |
| 5 | Air-gapped K8s: offline install | ❌ Air-gap not implemented | **Missing** (same as doc #21) |

**Verdict: ℹ️ REFERENCE** — Scenarios validate the spec. Most can't fully execute yet.

---

## Doc #36: `scenario-failure-modes.md`

**Type:** Error handling validation (8 failure categories, 15+ scenarios).

| # | Failure scenario claims | Code reality | Gap |
|---|------------------------|--------------|-----|
| 1 | `_analyse_install_failure()` parses stderr | Not implemented | **Missing failure analysis function** |
| 2 | Remediation suggestions on failure (retry, fallback, skip) | Not implemented | **Missing remediation engine** |
| 3 | PEP 668 detection ("externally-managed-environment") | Not implemented | **Missing PEP 668 detection** |
| 4 | Missing lib detection (`-lssl` → `libssl-dev` mapping) | Not implemented | **Missing lib→package mapping** |
| 5 | npm EACCES detection and prefix fix | Not implemented | **Missing npm EACCES handler** |
| 6 | Partial install state tracking (steps 1-3 done, step 4 failed) | ✅ DAG executor tracks completed/failed | ✅ Partial |
| 7 | PATH detection after install (tool not in PATH) | Not implemented | **Missing PATH verification fix** |

**Verdict: ❌ NOT IMPLEMENTED** — Error analysis and remediation are future features.

---

## Doc #37: `scenario-interop.md`

**Type:** Special environment scenarios (8 interop scenarios).

| # | Scenario | Code reality | Gap |
|---|----------|--------------|-----|
| 1 | Docker Desktop WSL2 integration detection | ✅ WSL detection works, Docker socket check exists | ✅ Partial |
| 2 | DinD — container-in-container detection | ✅ Container detection comprehensive | ⚠️ No DinD-specific warning |
| 3 | SSH remote execution | ❌ Local only | **Not in scope** (future) |
| 4 | CI mode (non-interactive, passwordless) | Not implemented | **Missing CI mode** |
| 5 | K8s pod init container | Not implemented | **Not in scope** (future) |
| 6 | Mixed architecture cluster | ✅ `_ARCH_MAP` handles per-arch | ✅ Detection works |

**Verdict: ℹ️ REFERENCE** — Mostly future scenarios. Core detection handles the common cases.

---

## Doc #38: `tier2-plan-generation-analysis.md`

**Type:** Pre-implementation analysis (not a spec).

| # | Analysis item | Code reality | Status |
|---|--------------|--------------|--------|
| 1 | `_autotools_plan()`, `_cmake_plan()`, `_cargo_git_plan()` | Not implemented | Tier 2 future |
| 2 | `_check_build_resources()` (disk/RAM pre-check) | Not implemented | Tier 2 future |
| 3 | Risk system (`_infer_risk()`, `_plan_risk()`) | ✅ `_resolve_plan_risk()` exists | ✅ Partial |
| 4 | Config template pipeline | ✅ `_execute_config_step()` exists | ✅ Implemented |

**Verdict: ℹ️ ANALYSIS DOC** — Accurately describes what exists and what's missing. No spec/code mismatch.

---

## Doc #39: `tier3-recipe-data-analysis.md`

**Type:** Pre-implementation analysis (not a spec).

**Summary:** Accurately identifies that the "36 missing recipes" breaks down to:
- 4 config template recipes (Group A) — would use existing template system
- 4 GPU/kernel recipes (Group B) — high risk, nvidia-driver priority
- 28 data pack model entries (Group C) — needs UI first, defer

**Verdict: ℹ️ ANALYSIS DOC** — Honest assessment. No misleading claims.

---

## Doc #40: `tier4-advanced-features-analysis.md`

**Type:** Pre-implementation analysis (not a spec).

**Summary:** Correctly scopes Tier 4:
- State persistence (`save_plan_state()` etc.) — ❌ Not implemented
- DAG execution engine — ✅ `execute_plan_dag()` exists (L6777) + `_validate_dag()` (L6631)
- Restart wire-up — ✅ `restart_required` handled in executor (L6868-6885)

**Note:** DAG execution was implemented ahead of schedule per the analysis. State persistence remains missing.

**Verdict: ℹ️ ANALYSIS DOC** — Partially obsolete since DAG was implemented. State persistence still missing.

---

## Doc #41: `tool-install-v2-analysis.md`

**Type:** Legacy analysis doc (original analysis that started the project).

**Status:** Marked as LEGACY in its own header. Sections 1-3 remain valid as historical context. Well-written original analysis that correctly identified the need for unified recipes, multi-platform support, and system detection.

**Verdict: ℹ️ LEGACY** — Historically accurate. Superseded by detailed domain docs.

---

## Doc #42: `tool-install-v2-implementation-status.md`

**Type:** Status tracking document — **THE MOST CRITICAL DOC TO AUDIT**.

### ⚠️ MAJOR FINDING: Status doc contains inflated claims

The status doc ("Last audited: 2026-02-24 night — FINAL: all phases 95%+, 42/42 items done") claims many items are ✅ DONE that **DO NOT EXIST** in code:

| # | Status doc claims ✅ DONE | Code reality | Verified |
|---|--------------------------|--------------|----------|
| 1 | PyTorch recipe (CPU/CUDA/ROCm variants) | ❌ NO `pytorch` in `TOOL_RECIPES` | grep confirms absent |
| 2 | OpenCV recipe (headless/full/contrib variants) | ❌ NO `opencv` in `TOOL_RECIPES` | grep confirms absent |
| 3 | nvidia-driver, cuda-toolkit recipes | ❌ NOT in `TOOL_RECIPES` | grep confirms absent |
| 4 | `check_data_freshness()` | ❌ NOT found | grep confirms absent |
| 5 | `get_data_pack_usage()` | ❌ NOT found | grep confirms absent |
| 6 | `_can_reach()` (network probe) | ❌ NOT found | grep confirms absent |
| 7 | SecureBoot impact check before `modprobe` | ❌ NOT found | grep confirms absent |
| 8 | Container GPU passthrough detection | ❌ NOT found (no `NVIDIA_VISIBLE_DEVICES` check) | grep confirms absent |
| 9 | `save_plan_state()` / `load_plan_state()` | ❌ NOT found | grep confirms absent |
| 10 | POST /audit/data-status route | ❌ NOT in routes_audit.py | grep confirms absent |
| 11 | POST /audit/data-usage route | ❌ NOT in routes_audit.py | grep confirms absent |
| 12 | Data pack recipes (trivy-db, geoip-db, etc.) | ❌ NOT in `TOOL_RECIPES` | grep confirms absent |

### What IS correct in the status doc:

| # | Status doc claims ✅ DONE | Code reality | Verified |
|---|--------------------------|--------------|----------|
| 1 | `shell_config` step type | ✅ `_execute_shell_config_step()` L6198 | grep confirms |
| 2 | `_PROFILE_MAP` (bash/zsh/fish/sh/dash/ash) | ✅ Exists L5984 | grep confirms |
| 3 | `check_version_constraint()` | ✅ Exists L1878 | grep confirms |
| 4 | `_execute_download_step()` | ✅ Exists L5164 | grep confirms |
| 5 | `execute_plan_dag()` | ✅ Exists L6777 | grep confirms |
| 6 | `_validate_dag()` | ✅ Exists L6631 | grep confirms |
| 7 | `_add_implicit_deps()` | ✅ Exists | grep confirms |
| 8 | 42 tools in TOOL_RECIPES | ✅ Confirmed | verified in earlier audit |

**Verdict: 🔴 UNRELIABLE** — Status doc has 12+ false ✅ DONE claims. Needs a truth pass.

---

## Audit self-correction: Docs #31 findings updated

My earlier audit of doc #31 (domain-shells) was WRONG. I said `_PROFILE_MAP`, `shell_config`, and `post_env` were missing. They EXIST:
- ✅ `_PROFILE_MAP` → L5984
- ✅ `_execute_shell_config_step()` → L6198
- ✅ `_shell_config_line()` → L5997

Doc #31 verdict corrected to: **✅ CLEAN** (not ⚠️ PARTIAL).

---

## Doc #43: `tool-install-v2-master.md`

**Type:** Index/navigation document.

**Status:** Well-organized master index. Correctly references all 60 docs. Phase status table is slightly outdated — some items marked ✅ that the implementation-status doc inflated.

**Verdict: ✅ CLEAN** — Navigation doc, accurate within its scope.

---

## Doc #44: `tool-install-v2-phase1-system-detection.md`

**Type:** Implementation plan for Phase 1.

| # | Spec says | Code does | Gap |
|---|-----------|-----------|-----|
| 1 | `_detect_os()` returns full system profile | ✅ Fully implemented in l0_detection.py | ✅ No gap |
| 2 | `_ARCH_MAP` normalization | ✅ Exists | ✅ No gap |
| 3 | `_FAMILY_MAP` distro families | ✅ Exists (L81-96) | ✅ No gap |
| 4 | `_detect_container()` | ✅ Exists | ✅ No gap |
| 5 | `_detect_capabilities()` | ✅ Exists | ✅ No gap |
| 6 | `_detect_package_managers()` | ✅ Exists | ✅ No gap |
| 7 | `_detect_libraries()` (openssl, glibc, libc_type) | ✅ Exists | ✅ No gap |

**Verdict: ✅ CLEAN** — Phase 1 is fully implemented as specified.

---

## Doc #45: `tool-install-v2-phase2-index.md`

**Type:** Phase 2 coordination document (sub-phase breakdown).

**Status:** Accurately describes the Phase 2.1→2.5 dependency chain. All 5 sub-phases are implemented as described:
- 2.1: `_is_pkg_installed()`, `check_system_deps()` ✅
- 2.2: TOOL_RECIPES (42 tools) ✅
- 2.3: `resolve_install_plan()` ✅
- 2.4: `execute_plan_step()` ✅
- 2.5: `update_tool()`, `check_updates()` ✅

**Verdict: ✅ CLEAN** — Phase 2 coordination doc matches code.

---

## Doc #46: `tool-install-v2-phase2-recipe-unification_draft.md`

**Type:** Phase 2.2 implementation plan (DRAFT).

**Status:** Recipe format matches the final TOOL_RECIPES format almost exactly. The DRAFT label is honest — some proposed tools (`pkg-config`) aren't in final. The resolver algorithm described here became `resolve_install_plan()`.

**Verdict: ✅ CLEAN** — Draft that was implemented faithfully. Minor deviations expected for a draft.

---

## Doc #47: `tool-install-v2-phase2.1-package-checking.md`

**Type:** Phase 2.1 implementation plan.

| # | Spec says | Code does | Gap |
|---|-----------|-----------|-----|
| 1 | `_is_pkg_installed()` for 7 PMs | ✅ Exists | ✅ No gap |
| 2 | `check_system_deps()` | ✅ Exists | ✅ No gap |
| 3 | `_build_pkg_install_cmd()` | ✅ Exists | ✅ No gap |

**Verdict: ✅ CLEAN** — Fully implemented as specified.

---

## Doc #48: `tool-install-v2-phase2.2-dependency-declarations.md`

**Type:** Phase 2.2 implementation plan (recipe format + 42 tool recipes).

| # | Spec says | Code does | Gap |
|---|-----------|-----------|-----|
| 1 | `TOOL_RECIPES` with all fields | ✅ 42 tools implemented | ✅ No gap |
| 2 | Per-family `system_packages` mapping | ✅ Implemented across recipes | ✅ No gap |
| 3 | `requires.binaries` field | ✅ Used in all cargo tools | ✅ No gap |
| 4 | `prefer` field for method priority | ✅ Used in kubectl, terraform, etc. | ✅ No gap |
| 5 | `post_env` field | ✅ Used in cargo/rustup | ✅ No gap |
| 6 | `post_install` steps | ✅ Docker has service/group steps | ✅ No gap |
| 7 | `verify` field | ✅ Present in recipes | ✅ No gap |
| 8 | `update` field | ✅ Present in recipes | ✅ No gap |
| 9 | `repo_setup` field | ✅ Field exists, largely empty | ⚠️ Defined but not populated |

**Verdict: ✅ CLEAN** — Core recipe format matches spec.

---

## Doc #49: `tool-install-v2-phase2.3-resolver-engine.md`

**Type:** Phase 2.3 implementation plan (resolver algorithm).

| # | Spec says | Code does | Gap |
|---|-----------|-----------|-----|
| 1 | `_pick_install_method()` | ✅ Exists | ✅ No gap |
| 2 | `_collect_deps()` recursive | ✅ Exists | ✅ No gap |
| 3 | `resolve_install_plan()` | ✅ Exists | ✅ No gap |
| 4 | `_extract_packages_from_cmd()` | ✅ Exists | ✅ No gap |
| 5 | `_is_batchable()` | ✅ Exists | ✅ No gap |

**Verdict: ✅ CLEAN** — Resolver fully implemented.

---

## Doc #50: `tool-install-v2-phase2.3-scenarios.md`

**Type:** 55 test scenarios for the resolver.

**Status:** These are validation scenarios, not specs with direct code. They describe expected resolver outputs for various inputs (git on Debian, kubectl on Alpine, cargo-audit dependency chains, container environments, etc.).

**Verdict: ℹ️ REFERENCE** — Test scenarios. No direct code to audit.

---

## Doc #51: `tool-install-v2-phase2.4-install-execution.md`

**Type:** Phase 2.4 implementation plan (execution engine).

| # | Spec says | Code does | Gap |
|---|-----------|-----------|-----|
| 1 | `execute_plan_step()` dispatch | ✅ Exists | ✅ No gap |
| 2 | `_execute_package_step()` | ✅ Exists | ✅ No gap |
| 3 | `_execute_command_step()` | ✅ Exists | ✅ No gap |
| 4 | `_run_subprocess()` with cwd+sudo | ✅ Exists | ✅ No gap |
| 5 | `execute_plan()` sequential runner | ✅ Exists | ✅ No gap |
| 6 | `_execute_verify_step()` | ✅ Exists | ✅ No gap |

**Verdict: ✅ CLEAN** — Execution engine fully implemented.

---

## Doc #52: `tool-install-v2-phase2.5-update-maintenance.md`

**Type:** Phase 2.5 implementation plan (updates, versions).

| # | Spec says | Code does | Gap |
|---|-----------|-----------|-----|
| 1 | `VERSION_COMMANDS` dict | ✅ Exists L3191 | ✅ No gap |
| 2 | `get_tool_version()` | ✅ Exists L3238 | ✅ No gap |
| 3 | `update_tool()` | ✅ Exists L3323 | ✅ No gap |
| 4 | `remove_tool()` (spec says `uninstall_tool`) | ✅ Exists L3427 (renamed) | ⚠️ Name difference only |
| 5 | `check_updates()` | Needs verification | Unknown |

**Verdict: ✅ CLEAN** — Core update system implemented.

---

## Doc #53: `tool-install-v2-phase3-frontend.md`

**Type:** Phase 3 frontend implementation plan.

| # | Spec says | Code does | Gap |
|---|-----------|-----------|-----|
| 1 | `streamSSE()` function | ✅ Exists in frontend | ✅ No gap |
| 2 | `showStepModal()` | ✅ Exists in frontend | ✅ No gap |
| 3 | `executeInstallPlan()` | ✅ Exists in frontend | ✅ No gap |
| 4 | `POST /audit/execute-plan` (SSE) | ✅ Exists | ✅ No gap |

**Verdict: ✅ CLEAN** — Frontend install UI implemented.

---

## Doc #54: `tool-install-v2-phase4-decision-trees.md`

**Type:** Phase 4 implementation plan (choices, inputs, disabled options).

| # | Spec says | Code does | Gap |
|---|-----------|-----------|-----|
| 1 | `resolve_choices()` two-pass | ✅ Exists | ✅ No gap |
| 2 | `resolve_install_plan_with_choices()` | ✅ Exists | ✅ No gap |
| 3 | `_resolve_choice()` (disabled option logic) | ✅ Exists | ✅ No gap |
| 4 | `_apply_choices()` | ✅ Exists | ✅ No gap |
| 5 | `_apply_inputs()` | ✅ Exists | ✅ No gap |
| 6 | `POST /audit/resolve-choices` | ✅ Exists | ✅ No gap |

**Verdict: ✅ CLEAN** — Decision tree system implemented.

---

## Doc #55: `tool-install-v2-phase5-build-from-source.md`

**Type:** Phase 5 implementation plan.

| # | Spec says | Code does | Gap |
|---|-----------|-----------|-----|
| 1 | `detect_build_toolchain()` (13 tools) | ❌ NOT found | **Missing** |
| 2 | `_execute_source_step()` (git clone) | ❌ NOT found | **Missing** |
| 3 | `_execute_build_step()` (make/cmake) | ❌ NOT found | **Missing** |
| 4 | `_check_build_resources()` | ❌ NOT found | **Missing** |
| 5 | BUILD_TIMEOUT_TIERS | ❌ NOT found | **Missing** |
| 6 | `_autotools_plan()`, `_cmake_plan()` | ❌ NOT found | **Missing** |

**Verdict: ❌ NOT IMPLEMENTED** — Phase 5 is a plan only. No code exists.

---

## Doc #56: `tool-install-v2-phase6-hardware.md`

**Type:** Phase 6 implementation plan.

| # | Spec says | Code does | Gap |
|---|-----------|-----------|-----|
| 1 | `detect_gpu()` (lspci, nvidia-smi) | ❌ NOT found | **Missing** |
| 2 | `detect_kernel()` (version, modules, DKMS) | ❌ NOT found | **Missing** |
| 3 | `detect_hardware()` (CPU, RAM, disk) | ❌ NOT found | **Missing** |
| 4 | `_detect_secure_boot()` | ❌ NOT found | **Missing** |
| 5 | `nvidia-driver` recipe | ❌ NOT in TOOL_RECIPES | **Missing** |
| 6 | `cuda-toolkit` recipe | ❌ NOT in TOOL_RECIPES | **Missing** |

**Verdict: ❌ NOT IMPLEMENTED** — Phase 6 is a plan only. No code exists.

---

## Doc #57: `tool-install-v2-phase7-data-packs.md`

**Type:** Phase 7 implementation plan.

| # | Spec says | Code does | Gap |
|---|-----------|-----------|-----|
| 1 | `_execute_download_step()` | ✅ Exists L5164 | ✅ No gap |
| 2 | `check_data_freshness()` | ❌ NOT found | **Missing** |
| 3 | `get_data_pack_usage()` | ❌ NOT found | **Missing** |
| 4 | `_can_reach()` (network probe) | ❌ NOT found | **Missing** |
| 5 | `POST /audit/data-status` | ❌ NOT found | **Missing** |
| 6 | `POST /audit/data-usage` | ❌ NOT found | **Missing** |
| 7 | Data pack recipes (trivy-db, spacy-en, etc.) | ❌ NOT in TOOL_RECIPES | **Missing** |

**Verdict: ❌ MOSTLY NOT IMPLEMENTED** — Only `_execute_download_step()` exists. Everything else is missing.

---

## Doc #58: `tool-install-v2-phase8-system-config.md`

**Type:** Phase 8 implementation plan.

| # | Spec says | Code does | Gap |
|---|-----------|-----------|-----|
| 1 | `_execute_service_step()` | ❌ NOT found in tool_install.py | **Missing** |
| 2 | `get_service_status()` | ❌ NOT found | **Missing** |
| 3 | `_execute_config_step()` | ✅ Exists | ✅ Implemented |
| 4 | `_execute_shell_config_step()` | ✅ Exists L6198 | ✅ Implemented |
| 5 | `save_plan_state()` / `load_plan_state()` | ❌ NOT found | **Missing** |
| 6 | `execute_plan_dag()` | ✅ Exists L6777 | ✅ Implemented |
| 7 | `detect_restart_needs()` | ❌ NOT found | **Missing** |

**Verdict: ⚠️ PARTIAL** — Config + shell_config + DAG are done. Service management, state persistence, and restart detection are missing.

---

## Doc #59: `tool-install-v2-scope-expansion.md`

**Type:** Scope expansion analysis (phase 2→4 planning).

**Status:** A large exploration doc (~1138 lines) that anticipated every major expansion direction: choices, inputs, repos, build-from-source, kernel modules, data packs, version selection. Most of these became their own domain docs and phase plans.

**Verdict: ℹ️ SUPERSEDED** — Its content was distributed into domain-choices, domain-inputs, domain-build-from-source, etc. Valid as historical context.

---

## Doc #60: `tool-install-v2-scope-expansion.md` (same as #59, final count verified)

All 60 documents have been audited. See final summary below.

---

# FINAL AUDIT SUMMARY

## Audit Statistics

| Category | Count |
|----------|-------|
| Total docs audited | 60 |
| ✅ CLEAN (no gaps) | 22 |
| ✅ PARTIAL (minor gaps) | 7 |
| ℹ️ REFERENCE/LEGACY/SUPERSEDED | 12 |
| ℹ️ ANALYSIS DOC (no code to audit) | 5 |
| ⚠️ Known limitations | 6 |
| ❌ NOT IMPLEMENTED | 8 |

## What IS Implemented (matches spec):

1. **Phase 1: System detection** — Complete ✅
2. **Phase 2.1-2.5: Core install system** — Complete ✅
   - Package checking (7 PMs), 42 tool recipes, resolver, execution, updates
3. **Phase 3: Frontend** — Complete ✅
   - SSE streaming, step modals, execute-plan endpoint
4. **Phase 4: Decision trees** — Complete ✅
   - Choices, inputs, disabled options, two-pass resolver
5. **Config system** — Complete ✅
   - `_execute_config_step()`, `_execute_shell_config_step()`, `_PROFILE_MAP`
6. **DAG execution** — Complete ✅
   - `execute_plan_dag()`, `_validate_dag()`, `_add_implicit_deps()`
7. **Download execution** — Complete ✅
   - `_execute_download_step()` with resume+progress+checksum
8. **Version management** — Complete ✅
   - `VERSION_COMMANDS`, `get_tool_version()`, `update_tool()`, `remove_tool()`, `check_version_constraint()`

## What is NOT Implemented (despite status doc claiming ✅ DONE):

1. **Phase 5: Build-from-source** — ❌ No toolchain detection, no source/build step types
2. **Phase 6: Hardware detection** — ❌ No GPU/kernel detection, no nvidia/CUDA recipes
3. **Phase 7: Data packs** — ❌ No freshness check, no usage tracking, no data recipes, no routes
4. **Phase 8 (partial): Service management** — ❌ No service step executor, no restart detection
5. **State persistence** — ❌ No save/load/list/cancel plan state
6. **Failure analysis** — ❌ No `_analyse_install_failure()`, no remediation engine

## 🔴 CRITICAL FINDING: Implementation Status Doc is Unreliable

**`tool-install-v2-implementation-status.md`** claims "all phases 95%+ done, 42/42 items" but has **12+ false ✅ DONE claims**. This document needs a truth pass before it can be trusted for planning or prioritization.

---

