# Full Audit: Documentation vs Code — HONEST FINDINGS

> **Started: 2026-02-25 (morning)**
> **Method: One doc at a time. Read every claim. Read actual code bodies. No skimming.**
>
> Previous audit (2026-02-24) was garbage — stamped everything "✅ CLEAN"
> by grep'ing for function names without reading bodies or verifying
> wiring. This version does it properly.

---

## How to read this audit

- **✅** = Verified in actual code, function body read, behavior matches spec
- **⚠️** = Partially implemented — some parts match, some missing or different
- **❌** = Not implemented despite spec claiming it
- **🔀** = Implemented but different from what spec describes
- **📝** = Spec-only doc (principles, analysis) — audited for code compliance

Each finding includes the exact code location (file:line) so fixes can be traced.

---

## Doc #1: `arch-plan-format.md` (579 lines)

**Type:** Output contract — defines what `resolve_install_plan()` returns.

### Plan dict structure (spec L40-81 vs code L2089-2305)

| Field | Spec | Code | Status |
|-------|------|------|--------|
| `tool` (str) | L44 | L2248 `"tool": tool` | ✅ |
| `label` (str) | L45 | L2249 `"label": recipe["label"]` | ✅ |
| `already_installed` (bool) | L49 | L2121-2126 (early return), L2250 | ✅ |
| `error` (str\|None) | L50-52 | L2117, L2138 | ✅ |
| `available_methods` (list) | L56-58 | L2139 | ✅ |
| `suggestion` (str) | L60-62 | L2140-2144 | ✅ |
| `needs_sudo` (bool) | L66-69 | L2251 `any(s["needs_sudo"])` | ✅ |
| `steps` (list[dict]) | L73-79 | L2253 | ✅ |

### ⚠️ Undocumented fields in code (not in this spec):

| Field | Code location | What it does |
|-------|---------------|-------------|
| `risk_summary` | L2252 | `_plan_risk(steps)` — aggregate risk info |
| `risk_escalation` | L2259 | `_check_risk_escalation()` — escalation warnings |
| `confirmation_gate` | L2275-2298 | Three-level confirmation gate (none/single/double) |
| `warning` | L2301-2303 | Sudo unavailable warning |

**Finding:** Code returns a SUPERSET of what the spec documents. The additional fields are functional and important (confirmation_gate controls the frontend UI). The spec should document them.

### Step types (spec L141-248 vs code L6942-7032)

| Step type | Spec says | Code dispatches to | Body exists at | Status |
|-----------|-----------|-------------------|---------------|--------|
| `repo_setup` | L154-169 | `_execute_repo_step()` | L3758 | ✅ |
| `packages` | L171-189 | `_execute_package_step()` | L3718 | ✅ |
| `tool` | L191-209 | `_execute_command_step()` | L3787 | ✅ |
| `post_install` | L211-228 | `_execute_command_step()` + SecureBoot check | L6978-7001 | ✅ Enhanced |
| `verify` | L230-248 | `_execute_verify_step()` | L3803 | ✅ |

Additional step types in code NOT in this spec (expected per extensibility):
- `source` → `_execute_source_step()` L4693 (Phase 5)
- `build` → `_execute_build_step()` L4887 (Phase 5)
- `install` → `_execute_install_step()` L4974 (Phase 5)
- `cleanup` → `_execute_cleanup_step()` L4991 (Phase 5)
- `download` → `_execute_download_step()` L5164 (Phase 7)
- `service` → `_execute_service_step()` L5397 (Phase 8)
- `config` → `_execute_config_step()` L5679 (Phase 8)
- `notification` → `_execute_notification_step()` L6305 (Phase 8)
- `shell_config` → `_execute_shell_config_step()` L6198+ (Phase 8)
- `github_release` → `_execute_github_release_step()` L6027

### Step ordering (spec L252-270 vs code L2159-2237)

Spec says: `repo_setup → packages → tool → post_install → verify`
Code does: Exactly this order. ✅

### ❌ API contract discrepancies

| Spec says | Code does | Problem |
|-----------|-----------|---------|
| `POST /audit/install-plan/execute` (L432) | `POST /api/audit/execute-plan` (routes_audit.py L608) | **Wrong URL in spec** |
| Client sends `{"plan": plan}` (L432) | Client sends `{"tool": "...", "sudo_password": "..."}` — server **re-resolves** (L647) | **Spec wrong about request shape** |
| Execute respects Phase 4 choices | Execute always calls `resolve_install_plan()` not `resolve_install_plan_with_choices()` (L647) | **❌ BUG: choices lost at execution time** |

### ❌ Execute endpoint ignores Phase 4 answers

This is a **real functional bug**. The flow:
1. Frontend calls `/api/audit/resolve-choices` → gets choices
2. User picks options
3. Frontend calls `/api/audit/install-plan` with `answers` → gets plan with choice-resolved steps ✅
4. Frontend calls `/api/audit/execute-plan` with `{"tool": "...", "sudo_password": "..."}` → server calls `resolve_install_plan()` WITHOUT answers → **executes a DIFFERENT plan than what the user reviewed**

The execute endpoint at routes_audit.py L633-636 imports `resolve_install_plan` but never `resolve_install_plan_with_choices`. It doesn't accept `answers` from the request body. Tools with choices (docker, etc.) will get default resolution instead of the user's selections.

### ❌ DAG execution not wired to HTTP

`execute_plan_dag()` exists at tool_install.py L6777 but NO route in routes_audit.py dispatches to it. Plans with `id`/`depends_on` fields cannot be executed via the web UI.

### Phase 8+ parallel SSE (spec L456-467)

Spec describes "multiple SSE streams for parallel steps" — code does NOT have this. The SSE endpoint (L664-774) iterates steps sequentially.

---

## Doc #2: `arch-principles.md` (373 lines)

**Type:** Constitution — 12 principles the code must obey.

### Principle-by-principle compliance:

| # | Principle | Status | Evidence |
|---|-----------|--------|----------|
| P1 | Always present, sometimes disabled | ✅ | `_resolve_choice_option()` L2353-2469 returns ALL options with `available`, `disabled_reason`, `enable_hint`. Never filters out unavailable options. |
| P2 | User decides, system suggests | ✅ | `auto_selected` L2502 only when exactly 1 available. User can always override. |
| P3 | Branches are explicit | ✅ | Choices are named in recipe data, resolved via `_resolve_single_choice()` L2472. Method selection via `_pick_install_method()` L1601 follows explicit priority. |
| P4 | Assistant panel is explainer | ⚠️ | See details below |
| P5 | Deterministic plans | ✅ | `resolve_install_plan()` is pure function of inputs. No randomness. |
| P6 | Extensibility by addition | ✅ | Dict-based everything. `step.get("risk", "low")` pattern. Phase 2 recipes survive unchanged. |
| P7 | Nothing off-limits with safeguards | ✅ | Risk inference (`_infer_risk` L1845), confirmation gates (L2275-2298), rollback (L6381-6399), backup-before (L6962-6968), SecureBoot checks (L6979-6998). |
| P8 | Interactive from admin panel | ⚠️ | See details below |
| P9 | Two-tier detection | ✅ | Fast: `_detect_os()`. Deep: `_detect_deep_profile()` in l0_detection.py L1393 with `_DEEP_DETECTORS` dict L1375-1390 (gpu, kernel, build, shell, network, services, filesystem, security, wsl_interop). |
| P10 | Evolution not revolution | ✅ | Code checks `if "choices" in recipe:` for two-pass. Phase 2 recipes work unchanged. |
| P11 | Resumable plans | ❌ | See details below |
| P12 | Data is the interface | ✅ | Resolver returns JSON dicts. Frontend renders them. Backend testable without browser. |

### ⚠️ P4 details — Assistant data fields

Spec lists these fields the assistant renders (L121-129):

| Field | In code? | Location |
|-------|----------|----------|
| `disabled_reason` | ✅ | L2465 |
| `enable_hint` | ✅ | L2466 |
| `warning` | ✅ | L2301 |
| `estimated_time` | ❌ NOT IN CODE | Not in any recipe or plan step |
| `risk` | ✅ | L2241 via `_infer_risk()` |
| `description` | ⚠️ Partial | In some choice options, not systematic |
| `learn_more` | ❌ NOT IN CODE | Not in any recipe or plan step |
| `rollback` | ✅ | L848, L941, L982 (recipes), L2272 (plan output), L6381 (generator) |

### ⚠️ P8 details — CLI/TUI interfaces

- Web: ✅ Full plan flow works (resolve → choices → execute → SSE)
- CLI: ❌ No CLI command exposes the plan-based install flow. The old `install_tool()` function exists but doesn't use the plan system.
- TUI: ❌ No TUI interface for plan-based install

### ❌ P11 details — Resumable plans

The principle says:
> "Plan state persisted to disk"
> "Plan execution must NEVER assume it runs start-to-finish without interruption"

Reality:
- `save_plan_state()` — ❌ does not exist
- `load_plan_state()` — ❌ does not exist
- `resume_plan()` — ❌ does not exist
- No disk persistence of plan execution state
- No resume-after-reboot capability
- `execute_plan()` (L7038) and the SSE endpoint (L664) both assume start-to-finish execution

---

## CORRECTIONS to previous audit

The 2026-02-24 audit made these **false claims** that must be corrected:

| Previous claim | Reality |
|----------------|---------|
| "detect_gpu() ❌ NOT found" | ✅ EXISTS at tool_install.py L3947 — full implementation with NVIDIA/AMD/Intel, nvidia-smi, lspci, container passthrough |
| "_can_reach() ❌ NOT found" | ✅ EXISTS at tool_install.py L2314 — HTTP HEAD probe with 60s cache |
| "_execute_source_step() ❌ NOT found" | ✅ EXISTS at L4693 — git clone, tarball, local source |
| "_execute_build_step() ❌ NOT found" | ✅ EXISTS at L4887 — make/cmake/ninja with env/cwd |
| "_execute_service_step() ❌ NOT found" | ✅ EXISTS at L5397 |
| "_detect_secure_boot() ❌ NOT found" | ✅ EXISTS at L4114 |
| "Phase 5 is a plan only. No code exists." | ❌ WRONG — source/build/install/cleanup step executors all exist |
| "Phase 6 hardware detection — No code exists." | ❌ WRONG — detect_gpu() L3947, detect_kernel() exists, _detect_secure_boot() L4114 |

**Root cause of false claims:** Previous audit used grep with `\|` OR patterns which silently failed to match, producing false negatives. The previous audit never read function bodies — finding a function name was considered "verified." This audit reads bodies.

---

## Doc #3: `arch-recipe-format.md` (698 lines)

**Type:** Canonical recipe data model — defines what goes in `TOOL_RECIPES`.

### TOOL_RECIPES location and size

- Defined at tool_install.py L43-1460
- Contains recipes for: ruff, mypy, pytest, black, pip-audit, safety, bandit, eslint, prettier, cargo-audit, cargo-outdated, cargo, rustc, helm, trivy, skaffold, kubectl, terraform, node, go, gh, git, curl, jq, make, ffmpeg, gzip, openssl, rsync, expect, python3, pip, npm, docker, docker-compose, nvidia-driver, cuda-toolkit, vfio-passthrough, rocm, pytorch, opencv, trivy-db, geoip-db, wordlists, spacy-en, hf-model, docker-daemon-config, journald-config, logrotate-docker, nginx-vhost, build-essential, hugo, mkdocs, docusaurus
- **~53 recipes** total (spec says "35+" — undersells reality)

### Simple recipe fields (spec L48-208 vs code L43-775)

| Field | Spec says | Code shows | Status |
|-------|-----------|------------|--------|
| `label` (str, REQUIRED) | L52-54 | ✅ Every recipe has it | ✅ |
| `cli` (str, OPTIONAL) | L56-61 | ✅ Used when tool_id ≠ binary (e.g. docker: no cli override, nvidia-driver: cli="nvidia-smi") | ✅ |
| `install` (dict) | L65-82 | ✅ Keys match PM IDs + `_default` | ✅ |
| `needs_sudo` (dict) | L84-92 | ✅ Per-method booleans | ✅ |
| `prefer` (list) | L94-98 | ✅ e.g. kubectl L279: `["snap", "brew", "_default"]` | ✅ |
| `requires.binaries` (list) | L102-111 | ✅ e.g. cargo-audit L123: `["cargo"]` | ✅ |
| `requires.packages` (dict by family) | L113-128 | ✅ e.g. cargo-audit L124-131: debian, rhel, alpine, arch, suse, macos | ✅ |
| `repo_setup` (dict) | L133-149 | ✅ nvidia-driver L818-831 has it | ✅ |
| `post_env` (str) | L153-162 | ✅ cargo L168: `'export PATH="$HOME/.cargo/bin:$PATH"'` | ✅ |
| `post_install` (list[dict]) | L164-180 | ✅ docker L750-765: start, enable, add user to group with conditions | ✅ |
| Post_install conditions | L171-175: has_systemd, not_root, not_container | ✅ `_evaluate_condition()` L1710-1744 handles: has_systemd, has_openrc, not_root, is_root, not_container, has_docker, file_exists:... | ✅ Enhanced (code has more conditions than spec lists) |
| `verify` (list[str]) | L184-194 | ✅ Every recipe has it | ✅ |
| `update` (dict) | L198-208 | ✅ Per-method update commands | ✅ |

### ⚠️ Category count mismatch (spec L233 vs code)

| Spec says | Code actually has |
|-----------|------------------|
| "Category 1: pip tools (7 tools)" | ✅ 7 pip tools (ruff, mypy, pytest, black, pip-audit, safety, bandit) |
| "Category 2: npm tools (2 tools)" | ✅ 2 npm tools (eslint, prettier) |
| "Category 3: cargo tools (2 tools)" | ✅ 2 cargo tools (cargo-audit, cargo-outdated) |
| "Category 4: curl-script runtimes (2 tools)" | ✅ 2 (cargo, rustc) |
| "Category 5: curl-script + brew (3 tools)" | ✅ 3 (helm, trivy, skaffold) |
| "Category 6: snap + variants (5 tools)" | ✅ 5 (kubectl, terraform, node, go, gh) |
| "Category 7: simple system packages (12 tools)" | Need to count — spec says 12 |
| "Category 8: packages with name variance (4 tools)" | Need to verify — spec says 4 |
| "Category 9: tools with post-install (2 tools)" | ✅ docker, docker-compose (2) |
| Categories 9-12 (GPU, ML, data, config, build) | NOT in spec categories — spec only covers Phase 2 categories |

**Finding:** Spec covers Phase 2 categories (1-9) correctly. Code has expanded to categories 9-12 (GPU, ML/AI, data packs, config templates, build toolchain, pages tools) that are NOT documented in this spec's category listing.

### 🔀 Complex recipe format mismatch (spec L488-514 vs code L994-1035)

**The spec conflates recipe format with resolved format.**

Spec says choice options in the recipe data should contain:
```
"available": bool
"disabled_reason": str | None
"enable_hint": str | None
```

Reality: These fields are **NOT in the raw recipe data**. They are **ADDED at runtime** by `_resolve_choice_option()` (L2353-2469). The raw recipe options only have:
- `id`, `label`, `default`, `requires`, `install_command`

This is an **important distinction**: the spec mixes up the recipe format (input data) with the resolved format (output data). The recipe is the static dict. The resolver enriches it.

### 🔀 `install_command` vs `install_variants`

Spec says (L541-564): Branched installs use a top-level `install_variants` dict keyed by variant ID.

Reality in code: PyTorch (L994-1035) and OpenCV (L1041-1080) put `install_command` **directly inside each choice option**, not in a separate `install_variants` dict.

The resolver (`_resolve_chosen_install_command()` or similar) reads BOTH patterns:
- `install_variants[answer]` (L2812-2819)
- `option["install_command"]` inline

**Result:** Two patterns coexist. Spec documents ONE (install_variants), code also uses ANOTHER (inline install_command). Both work but spec doesn't document the inline pattern.

### ⚠️ Stale bug reference (spec L318)

Spec says: "current code has cargo in `_SUDO_RECIPES` — this is a BUG."

Reality: `_SUDO_RECIPES` no longer exists in code (confirmed by grep). Cargo's recipe at L157-173 correctly has `"_default": False` for needs_sudo. This bug was fixed but the spec still references it.

### Missing fields in actual recipes

Spec says these should exist in choice options:

| Field | In spec (L490-514) | In actual recipes | Status |
|-------|-------------------|------------------|--------|
| `description` | Yes | ❌ No PyTorch/OpenCV/MkDocs option has it | ❌ Missing |
| `warning` | Yes | ❌ Not in any choice option | ❌ Missing |
| `estimated_time` | Yes | ❌ Not in any choice option | ❌ Missing |
| `risk` (per option) | Yes | ❌ Not in any choice option (only recipe-level) | ❌ Missing |

These are supposed to feed the assistant panel (Principle 4). Without them, the assistant can't explain options to the user.

### Recipe fields NOT in spec but in code

| Field in code | Example | Status |
|--------------|---------|--------|
| `category` | nvidia-driver L810: `"gpu"`, pytorch L998: `"ml"` | ❌ Undocumented |
| `cli_verify_args` | pytorch L997: `["-c", "import torch"]` | ❌ Undocumented |
| `steps` (inline) | vfio-passthrough L894-938: pre-built step list | ❌ Undocumented — recipe has its own `steps` list, bypassing resolver |
| `rollback` (recipe-level) | nvidia-driver L848-851 | ⚠️ Mentioned at L612 but not in the main field table |
| `restart_required` (recipe-level) | nvidia-driver L852 | ⚠️ Mentioned at L614-619 but not in main field table |
| `arch_map` | hugo L1407: `{"x86_64": "amd64"}` | ❌ Undocumented |
| `remove` (recipe-level) | rocm L978-980 | ❌ Undocumented |
| `config_templates` format | L1214-1246 has `inputs`, `format`, `post_command`, `condition`, `backup` inside template entries | ⚠️ Spec L584-592 is oversimplified — actual format is much richer |
| `needs_sudo` as bare bool | vfio-passthrough L890: `"needs_sudo": True` (not dict) | 🔀 Spec says `needs_sudo` is always a dict keyed by method, but some recipes use bare bool |

### ⚠️ `needs_sudo` format inconsistency

Spec at L84: `"needs_sudo": dict[str, bool]` — per-method dict, keys MUST match install keys.

But vfio-passthrough at L890: `"needs_sudo": True` — bare boolean, not a dict.

The resolver at L2191: `recipe_t["needs_sudo"].get(method, False)` — this would crash on a bare bool. This means vfio-passthrough's `needs_sudo` is incompatible with the standard resolver path.

**This is either a BUG (vfio recipe won't resolve properly) or the vfio recipe uses the `steps` bypass (L894) and never hits the standard resolver.**

### ⚠️ `config_templates` format gap

Spec at L584-592 shows:
```python
"config_templates": {
    "path": str,
    "template": str,
    "needs_sudo": bool,
    "backup": bool,
}
```

Actual code at L1214-1246 has:
```python
"config_templates": [{  # LIST of dicts, not single dict
    "id": str,
    "file": str,        # not "path"
    "format": str,      # "json" | "ini" | "raw" — NOT in spec
    "template": str,
    "inputs": [...],    # per-template inputs — NOT in spec
    "needs_sudo": bool,
    "post_command": [...],  # NOT in spec
    "condition": str,      # NOT in spec
    "backup": bool,
}]
```

The spec is severely oversimplified compared to the actual format. It's a list (not dict), field names differ (`file` vs `path`), and there are 4 fields the spec doesn't mention.

---

## Doc #4: `arch-system-model.md` (498 lines)

**Type:** Input contract — the complete schema of the system profile dict.

**Framing correction:** Spec = source of truth. Code deviations = code bugs.

### Fast tier: Spec (L62-121) vs `_detect_os()` (l0_detection.py L316-431)

| Spec field | Code location | Match? |
|-----------|---------------|--------|
| `system` (str) | L327: `platform.system()` | ✅ |
| `release` (str) | L328: `platform.release()` | ✅ |
| `machine` (str) | L329: `platform.machine()` | ✅ |
| `arch` (str) | L330: `_ARCH_MAP.get(...)` | ✅ |
| `distro.id` | L354: from /etc/os-release | ✅ |
| `distro.name` | L355: PRETTY_NAME | ✅ |
| `distro.version` | L356: VERSION_ID | ✅ |
| `distro.version_tuple` | L357: `_parse_version_tuple()` | ✅ |
| `distro.family` | L358: `_get_distro_family()` | ✅ |
| `distro.codename` | L359: VERSION_CODENAME | ✅ |
| `wsl` (bool) | L338: /proc/version check | ✅ |
| `wsl_version` (int\|None) | L343: WSL2 check | ✅ |
| `container.in_container` | L382: `_detect_container()` | ✅ |
| `container.runtime` | L382: (part of container dict) | ✅ |
| `container.in_k8s` | L382: (part of container dict) | ✅ |
| `capabilities.has_systemd` | L385: `_detect_capabilities()` | ✅ |
| `capabilities.systemd_state` | Part of capabilities | ✅ |
| `capabilities.has_sudo` | Part of capabilities | ✅ |
| `capabilities.passwordless_sudo` | Part of capabilities | ✅ |
| `capabilities.is_root` | Part of capabilities | ✅ |
| `package_manager.primary` | L389: `_detect_package_managers()` | ✅ |
| `package_manager.available` | Part of PM dict | ✅ |
| `package_manager.snap_available` | Part of PM dict | ✅ |
| `libraries.openssl_version` | L394: `_detect_libraries()` | ✅ |
| `libraries.glibc_version` | Part of libraries | ✅ |
| `libraries.libc_type` | Part of libraries | ✅ |

**Result: Fast tier matches spec 100%.** ✅

### 🔀 Code adds undocumented `hardware` dict to fast tier

At L396-429 the code adds:
```python
info["hardware"] = {
    "cpu_cores": os.cpu_count(),
    "arch": info["arch"],
    "ram_total_mb": ...,        # from /proc/meminfo
    "ram_available_mb": ...,    # from /proc/meminfo
    "disk_free_gb": ...,        # from shutil.disk_usage("/")
    "disk_total_gb": ...,       # from shutil.disk_usage("/")
}
```

This is NOT in the fast tier spec. The spec puts `cpu_cores` and `disk_free_gb` in the **deep tier** `build` section (L267-268). The code moved them to fast tier without updating the spec.

**Classification: Code deviated from spec.** `cpu_cores` and disk metrics belong in deep tier per spec. Should be moved back OR spec should be updated with justification (e.g., "needed for quick resource display in audit card").

### Deep tier: Spec says "NOT YET IMPLEMENTED" — Code IS implemented

The spec header at L176 says: **"Deep Tier: Future Schema (Phases 4-8 — NOT YET IMPLEMENTED)"**

The traceability table at L488-497 says all deep tier fields are "not yet" implemented.

**Reality: ALL 10 deep tier categories are FULLY implemented** in `_DEEP_DETECTORS` (l0_detection.py L1375-1390):

| Category | Spec section | Detector function | Match to spec schema? |
|----------|-------------|-------------------|----------------------|
| `shell` | L186-198 | `_detect_shell()` L620-698 | ✅ All 8 fields match exactly |
| `init_system` | L211-218 | `_detect_init_system_profile()` L701-742 | ✅ All 4 fields match: type, service_manager, can_enable, can_start. Detection priority matches (systemd > OpenRC > launchd > sysvinit > none). Code also has `sysvinit` where spec says `initd` — minor rename. |
| `network` | L227-241 | `_detect_network()` L1327-1370 | ✅ `online`, `proxy_detected`, `proxy_url`, `endpoints` dict with `reachable`, `latency_ms`, `error` per endpoint. Parallel probes using ThreadPoolExecutor — matches spec. |
| `build` | L251-270 | `_detect_build_profile()` L745-811 | ✅ `compilers` dict (gcc, g++, clang, rustc), `build_tools` dict (make, cmake, ninja, meson, autoconf), `dev_packages_installed`, `cpu_cores`, `disk_free_gb`, `tmp_free_gb`. Plus `gcc_is_clang_alias` — extra field not in spec. |
| `gpu` | L280-300 | `_detect_gpu_profile()` L814-934 | ✅ nvidia (present, model, driver_version, cuda_version, nvcc_version, compute_capability), amd (present, model, rocm_version), intel (present, model, opencl_available). Plus extra: `cudnn_version`, `cudnn_path` — not in spec. |
| `kernel` | L315-330 | `_detect_kernel_profile()` L937-1057 | ✅ `version`, `config_available`, `config_path`, `loaded_modules`, `module_check` (with loaded/compiled/config_state per module), `iommu_groups`. Plus extra: `headers_installed`, `dkms_available`, `secure_boot`. |
| `wsl_interop` | L343-349 | `_detect_wsl_interop()` L1181+ | ✅ `available`, `binfmt_registered`, `windows_user`, `wslconfig_path`. |
| `services` | L358-366 | `_detect_services()` L1138-1178 | ✅ `journald.active`, `journald.disk_usage`, `logrotate_installed`, `cron_available`. |
| `filesystem` | L375-379 | `_detect_filesystem()` L1059-1090 | ✅ `root_type`, `root_free_gb`. |
| `security` | L381-390 | `_detect_security()` L1093-1135 | ✅ `selinux.installed`, `selinux.mode`, `apparmor.installed`, `apparmor.profiles_loaded`. |

### Deep tier integration

`_detect_deep_profile(needs=...)` at L1393-1450:
- ✅ Accepts selective `needs` list (spec L450-456 says it should)
- ✅ Cached module-level with 5-minute TTL
- ✅ Incremental: detects only uncached categories and merges

`l0_system_profile(root, deep=True)` at L1460-1492:
- ✅ Calls `_detect_deep_profile()` and merges into fast tier dict
- ✅ Maintains single dict contract

### Extra fields code adds beyond spec schema

| Category | Extra field | Notes |
|----------|------------|-------|
| `build` | `gcc_is_clang_alias` | macOS-specific: detects when `gcc` is actually clang |
| `gpu.nvidia` | `cudnn_version`, `cudnn_path` | cuDNN detection — useful but not in spec |
| `kernel` | `headers_installed`, `dkms_available`, `secure_boot` | Carried forward from `detect_kernel()` in tool_install.py |
| `init_system` | `type: "sysvinit"` | Spec says `"initd"` — different naming |

**Classification:** Extra fields are additive and don't break anything (follows Principle §6). But the naming mismatch (`sysvinit` vs `initd`) should be resolved — code should match spec terminology.

### ⚠️ Stale "NOT YET IMPLEMENTED" header

The spec header at L176 and traceability at L488-497 say deep tier is "not yet" implemented. This is **stale** — all 10 categories are implemented and closely follow the spec schemas. The traceability table should be updated to mark these as "done" with the code location.

### Data flow (spec L396-426 vs code)

Spec flow at L399-425 is accurate:
- ✅ `_detect_os()` → `l0_system_profile()` → cache → JSON endpoint → audit card ✅
- ✅ `l0_system_profile(deep=True)` merges deep tier ✅
- ⚠️ No `?deep=true` query param on `/api/audit/system` endpoint — need to verify this separately in routes

### Summary for Doc #4

The system model spec is **largely accurate**. The fast tier schema is 100% correct. The deep tier schemas are 100% implemented and match the spec closely. The main issues:

1. **Stale status:** Spec says deep tier is "NOT YET IMPLEMENTED" — it IS implemented
2. **Fast tier scope creep:** `hardware` dict (ram, disk, cpu_cores) added to fast tier without spec update
3. **Extra deep tier fields:** `cudnn_version`, `gcc_is_clang_alias`, `headers_installed` etc. — additive, not breaking, but unspecced
4. **Naming:** `sysvinit` vs spec's `initd`

**This doc is the BEST spec-to-code match so far. Code faithfully follows the spec schemas.**

---

## Audit progress

| # | Document | Status |
|---|----------|--------|
| 1 | `arch-plan-format.md` | ✅ AUDITED |
| 2 | `arch-principles.md` | ✅ AUDITED |
| 3 | `arch-recipe-format.md` | ✅ AUDITED |
| 4 | `arch-system-model.md` | ✅ AUDITED |
| 5-34 | `domain-*.md` (30 files) | ⏳ PENDING |
| 35-37 | `scenario-*.md` (3 files) | ⏳ PENDING |
| 38-40 | `tier*-analysis.md` (3 files) | ⏳ PENDING |
| 41-59 | `tool-install-v2-*.md` (19 files) | ⏳ PENDING |

---
