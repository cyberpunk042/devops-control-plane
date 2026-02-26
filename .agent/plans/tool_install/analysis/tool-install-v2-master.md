# Tool Install V2 — Master Index

Last updated: 2026-02-25 (morning — spec alignment pass, phase matrix updated)

This is the root document. All analysis, planning, and architecture
documents are organized here by domain and by phase.

This system is the CORE of the program — handling tool installation,
configuration, build, kernel management, and hardware detection, all
interactive from the Admin panel. Nothing is off-limits if it can be
automated with proper safeguards.

---

## Document Architecture

Documents are organized in TWO dimensions:
1. **By domain** — WHAT we're analyzing (concerns, capabilities)
2. **By phase** — WHEN we're building it (implementation order)

A domain analysis can inform multiple phases. A phase can draw from
multiple domain analyses. The two dimensions are cross-referenced.

### Naming convention

```
tool-install-v2-{category}-{topic}.md

Categories:
  domain-    Domain analysis (a concern, not tied to a phase)
  phase{N}-  Phase plan (implementation, tied to a milestone)
  scenario-  Scenario sets (traces, edge cases)
  arch-      Architecture & principles (cross-cutting)
```

---

## 1. Architecture & Principles

These define the system's identity. They GROW as understanding deepens.

| Document | Status | What it defines |
|----------|--------|----------------|
| `arch-principles.md` | ✅ DONE | 12 principles: always-present/sometimes-disabled, user-decides/system-suggests, explicit-branches, assistant-as-renderer, deterministic-plans, extensibility-by-addition, nothing-off-limits-with-safeguards, interactive-from-admin, two-tier-detection, evolution-not-revolution, resumable-plans, data-is-interface |
| `arch-recipe-format.md` | ✅ DONE | Canonical recipe format. Simple (Phase 2, 15 fields, 9 categories, 35+ tools) and complex extensions (Phases 4-8: choices, inputs, install_variants, data_packs, config_templates, risk, restart, kernel_config, hardware). Backward compatibility rules, migration mapping |
| `arch-system-model.md` | ✅ DONE | Complete system profile schema. Fast tier (implemented): OS, distro, WSL, container, capabilities, PM, libraries. Deep tier (future): shell, network, build, GPU, kernel, WSL interop, services, filesystem, security. Two-tier cache strategy, data flow, consumer mapping |
| `arch-plan-format.md` | ✅ DONE | Complete output contract. Phase 2: 5 step types (repo_setup, packages, tool, post_install, verify), linear ordering, 3 response shapes (success, already_installed, error). Phase 4-8: step IDs, DAG deps, risk levels, restart, choices/inputs, data packs, config templates. Determinism contract, API spec, extensibility rules |
| `tool-install-v2-implementation-status.md` | 🔄 LIVING | **Implementation audit.** Per-phase, per-item breakdown of what's in code vs. what specs define. Cross-cutting gaps (deep tier infra, routes, recipes, frontend). 5-tier priority order for closing gaps. Updated after each implementation sprint. |

## 2. Domain Analysis

Each domain is a CONCERN. Analyzed independently. Referenced by phases.

### 2a. Platform & Environment

| Document | Status | Domain |
|----------|--------|--------|
| `domain-platforms.md` | ✅ VERIFIED | All 6 families: debian, rhel, alpine, arch, suse, macos. PMs, install flags, dev-header naming, init systems, sudo, libc, snap, GUI. Architecture matrix (amd64/arm64/armv7). Platform × feature matrix. Recipe-to-platform mapping. Edge cases (unknown distro, ID_LIKE fallback) |
| `domain-containers.md` | ✅ VERIFIED | Detection (6 methods: .dockerenv, cgroup, environ, K8s env). 5 runtimes: Docker, containerd, Podman, LXC, nspawn. Limitation matrix (systemd, sudo, kernel, fs). Condition combos per environment. K8s specifics. Container-safe operations catalog. Common base images. Scenario traces S29-S33 |
| `domain-wsl.md` | ✅ VERIFIED | Detection (fast tier, /proc/version). WSL1 vs WSL2 architecture matrix. Impact: systemd (3 modes), Docker (3 approaches), snap, PATH pollution, filesystem perf. Interop: cross-OS commands, .wslconfig, path translation. Config files. Conditions (current + future). Common distros. Edge cases (conversion, Docker Desktop, GPU) |
| `domain-shells.md` | ✅ VERIFIED | 6 shells: bash, zsh, fish, sh, dash, ash. Profile file hierarchy per shell. PATH management: post_env (Phase 2) vs shell_config (Phase 4). Broken profile detection. Login/non-login/interactive mechanics. Restricted shells (rbash). Sandbox confinement (snap, Flatpak, SELinux, AppArmor, chroot). Shell-specific syntax. Idempotent writes |

### 2b. Package & Install Methods

| Document | Status | Domain |
|----------|--------|--------|
| `domain-package-managers.md` | ✅ VERIFIED | 8 PMs: apt, dnf, yum, apk, pacman, zypper, brew, snap. Detection order. Check/install/update/remove commands. PM-to-checker mapping (dpkg-query, rpm, apk, pacman, brew). Package naming across 6 families. Repo setup. Sudo rules. Error handling. Performance benchmarks. Batching |
| `domain-language-pms.md` | ✅ VERIFIED | pip (7 tools, _PIP constant, venv model, verify, private indexes), npm (2 tools, -g permissions, EACCES, nvm, npm as dep), cargo (2 tools, rustup chain, system pkg deps, post_env wrapping, build perf). Runtimes as dependencies. NOT IMPLEMENTED: go, gem, composer. Registry/network/proxy |
| `domain-binary-installers.md` | ✅ VERIFIED | curl-pipe-bash (rustup, helm, trivy) vs direct binary download (kubectl, skaffold). Security (HTTPS, TLS). Architecture detection (IMPLEMENTED interpolation). OS detection. Version mgmt (always-latest). Resolver _default as last resort. curl dependency. Install locations. Container/airgapped edge cases |
| `domain-repos.md` | ✅ VERIFIED | System PM repos (apt GPG+sources.list modern/legacy, dnf/rpm repos, PPA, COPR, apk, pacman/AUR, zypper, brew taps). Language registries (PyPI, npmjs, crates.io — config, auth, private mirrors). Trust model (GPG, HTTPS, risk levels). repo_setup schema + execution order. Default repos per platform. Edge cases (stale index, key expiry, proxies) |

### 2c. Build & Compilation

| Document | Status | Domain |
|----------|--------|--------|
| `domain-build-systems.md` | ✅ VERIFIED | 6 build tools: make, cmake, meson, autotools, ninja, cargo build. Detection (IMPLEMENTED in deep tier). cmake recursive dep problem (3 install methods). Build-essential meta-packages per family. Build flags/configuration via inputs. Performance benchmarks. Cross-compilation. Phase 2 (implicit cargo) vs Phase 5 (full pipeline) |
| `domain-compilers.md` | ✅ VERIFIED | gcc/g++ (6 families), clang (macOS aliasing gotcha — IMPLEMENTED), rustc (rustup toolchain mgmt), Go compiler. Meta-packages (build-essential, @development-tools, build-base, base-devel, Xcode CLI). libc: glibc vs musl vs libSystem binary compat. Version management (update-alternatives, rustup). Detection (IMPLEMENTED — schema differs from spec) |
| `domain-build-from-source.md` | ✅ VERIFIED | Full 6-stage pipeline: obtain (git/tarball) → deps → configure (cmake/autotools/meson) → compile (parallel, RAM limits, progress parsing) → install (/usr/local vs ~/.local) → cleanup. Step types IMPLEMENTED (source, build, install). Disk space reqs NOT IMPLEMENTED. Timeout/ccache/progress NOT IMPLEMENTED. cargo install as Phase 2 implicit build. OpenCV example recipe |

### 2d. Hardware & Kernel

| Document | Status | Domain |
|----------|--------|--------|
| `domain-gpu.md` | ✅ VERIFIED | 3 vendors: NVIDIA (CUDA, driver, compute capability — IMPLEMENTED detection + cuDNN), AMD (ROCm, HIP), Intel (OpenCL, oneAPI). Detection IMPLEMENTED. nvidia-driver recipe IMPLEMENTED. PyTorch variant selection. Container/VM/WSL2 GPU access. VFIO passthrough |
| `domain-kernel.md` | ✅ VERIFIED | Config detection IMPLEMENTED (3 locations, 4 states). Module loading + SecureBoot check IMPLEMENTED. Schema matches doc exactly (plus extra fields). Kernel recompilation pipeline (Phase 6+). Risk classification. Rollback. 5 safeguards. WSL kernel. 8 DevOps modules. Container kernel limitations |
| `domain-hardware-detect.md` | ✅ VERIFIED | CPU arch normalization (IMPLEMENTED — 3 entries vs doc's 6, armv7l→armhf mismatch). CPU features NOT IMPLEMENTED. RAM/disk detection IMPLEMENTED. Arch interpolation IMPLEMENTED. Network connectivity NOT IMPLEMENTED. IOMMU IMPLEMENTED. Phase matrix stale. Hardware constraint eval NOT IMPLEMENTED |

### 2e. Application Domains

| Document | Status | Domain |
|----------|--------|--------|
| `domain-ml-ai.md` | ✅ VERIFIED | PyTorch IMPLEMENTED (3 variants: cpu/cuda/rocm — differs from doc's 5). Variant selection + install_variants IMPLEMENTED. data_packs infrastructure IMPLEMENTED. Recipe structure differs (pip3 vs _PIP, hardcoded URLs vs template, hardware constraint format). TF, JAX, spaCy, HF, NLTK recipes NOT in code. Phase 7 label stale |
| `domain-data-packs.md` | ✅ VERIFIED | Pure Phase 7 spec — no implementation. Clean design doc. 5 types (spaCy, NLTK, HF, Tesseract, locale). Schema (11 fields). Size estimation + disk check functions NOT IMPLEMENTED. Multi-select UI NOT IMPLEMENTED. No data_packs in any recipe. Docstring-only reference in _resolve_choices() |
| `domain-devops-tools.md` | ✅ VERIFIED | **61 tools** (not 42). Old dict refs (_NO_SUDO/_SUDO_RECIPES, _TOOL_REQUIRES, _RUNTIME_DEPS) ALL STALE — replaced by unified TOOL_RECIPES. 8/9 "known issues" ALREADY FIXED. "Future" tools (pytorch, opencv, nvidia-driver, cuda-toolkit, rocm) ALREADY IN code. 19 undocumented tools. Doc needs major refresh |

### 2f. System Configuration

| Document | Status | Domain |
|----------|--------|--------|
| `domain-services.md` | ✅ VERIFIED | Init system detection IMPLEMENTED (not Phase 4). Schema matches exactly. Detection uses /run/systemd/system (differs from doc's systemctl). journald-config recipe IMPLEMENTED (not Phase 8). Conditional commands IMPLEMENTED (has_systemd, has_openrc, not_root, not_container, has_docker, file_exists). init.d can_enable smarter than doc |
| `domain-config-files.md` | ✅ VERIFIED | Entire config template system IMPLEMENTED (not Phase 8). All 4 doc examples ARE real recipes: docker-daemon-config, journald-config, logrotate-docker, nginx-vhost. _render_template + _validate_input IMPLEMENTED. Schema structure matches doc exactly. Phase labels stale |
| `domain-restart.md` | ✅ VERIFIED | Restart handling IMPLEMENTED (not Phase 8). All 3 levels used in recipes. Plan pause + state persistence (save_plan_state, load_plan_state) IMPLEMENTED. State dir differs from doc. _check_pending_plans() NOT IMPLEMENTED (no auto-scan on startup). Sensitive field stripping EXISTS |

### 2g. UX & Choice Architecture

| Document | Status | Domain |
|----------|--------|--------|
| `domain-choices.md` | ✅ VERIFIED | Choice system FULLY IMPLEMENTED (not Phase 4). resolve_choices() handles static/dynamic/PM version sources + GitHub API fetch + caching. depends_on IMPLEMENTED with parallel execution (not Phase 8). _evaluate_requires() function name wrong (done inline). PyTorch pattern correct but simplified |
| `domain-inputs.md` | ✅ VERIFIED | Input system IMPLEMENTED (not Phase 4). _validate_input handles select/number/text/path/boolean. _render_template handles {var} substitution + built-in vars (user, home, arch, distro, nproc). Config template recipes use input schema. Phase label stale |
| `domain-disabled-options.md` | ✅ VERIFIED | "Never remove" principle IMPLEMENTED. disabled_reason + enable_hint fields SET in choice resolver. Mostly design guidance doc. Schema fields part of resolve_choices() (verified in doc #21). generate_assistant_content() is frontend pseudocode. No stale phase labels |
| `domain-version-selection.md` | ✅ VERIFIED | Version selection IMPLEMENTED (not Phase 4/8). All 3 source types work: static, dynamic (GitHub API fetch + _VERSION_FETCH_CACHE), package_manager. Version constraints (kubectl ±1, CUDA matrix) NOT IMPLEMENTED. Phase labels stale |

### 2h. Safety & Risk

| Document | Status | Domain |
|----------|--------|--------|
| `domain-risk-levels.md` | ✅ VERIFIED | Risk system IMPLEMENTED (not Phase 3-8). risk field in recipes (high for kernel/GPU, low for pip). _infer_risk() matches doc pseudocode. Confirmation gates (type-to-confirm) NOT IMPLEMENTED (frontend concern) |
| `domain-rollback.md` | ✅ VERIFIED | Rollback IMPLEMENTED (not Phase 3-8). UNDO_COMMANDS catalog at line 6381 matches doc. _generate_rollback() at line 6441. Remove/uninstall uses catalog. Reversibility matrix is accurate design guidance |
| `domain-sudo-security.md` | ✅ VERIFIED | sudo -S -k pattern CORRECTLY documented — most accurate doc. needs_sudo per-PM in TOOL_RECIPES. Stale line refs (339/387/420/281) and old dict names (_SUDO_RECIPES, _NO_SUDO_RECIPES) — unified into TOOL_RECIPES |

### 2i. Infrastructure & Connectivity

| Document | Status | Domain |
|----------|--------|--------|
| `domain-network.md` | ✅ VERIFIED | Phase labels CORRECT — one of few docs accurately labeled as future. detect_network() NOT implemented. Network probing, proxy injection, air-gapped support all genuinely future work |
| `domain-parallel-execution.md` | ✅ VERIFIED | depends_on IMPLEMENTED in recipes + plan engine (not Phase 8). _add_implicit_deps() for linear fallback. DAG-aware but NOT truly parallel — executes synchronously. _has_cycle() NOT IMPLEMENTED. asyncio dispatch NOT IMPLEMENTED |
| `domain-pages-install.md` | ✅ VERIFIED | Pages unification ALREADY DONE (not Phase 3-4). hugo/mkdocs/docusaurus ALL in TOOL_RECIPES. Hugo uses apt/brew/snap NOT github_release binary download as doc recommends. pages_install.py still exists (not removed) |

## 3. Phase Plans

Implementation order. Each phase draws from domain analyses above.

### Existing files (current names → will be renamed when domain docs absorb content)

| Current file | Status | Maps to |
|-------------|--------|---------|
| `tool-install-v2-analysis.md` | 📦 LEGACY | Original analysis. Sections 1-3 valid as history |
| `tool-install-v2-phase1-system-detection.md` | ✅ DONE | Phase 1 impl plan + expansion roadmap |
| `tool-install-v2-phase2-index.md` | ✅ DONE | Phase 2 index (sub-phases 2.1-2.5) |
| `tool-install-v2-phase2.1-package-checking.md` | ✅ DONE | Phase 2.1 analysis |
| `tool-install-v2-phase2.2-dependency-declarations.md` | ✅ DONE | Phase 2.2 analysis |
| `tool-install-v2-phase2.3-resolver-engine.md` | ✅ DONE | Phase 2.3 analysis |
| `tool-install-v2-phase2.3-scenarios.md` | ✅ DONE | 55 resolver scenarios |
| `tool-install-v2-scope-expansion.md` | 🔄 EVOLVING | Scope expansion — will split into domain docs |
| `tool-install-v2-phase2-recipe-unification_draft.md` | 📦 SUPERSEDED | Early draft, replaced by Phase 2.2 |

### Phase plan matrix

| Phase | Status | Depends on (domains) | Summary |
|-------|--------|---------------------|---------|
| Phase 1 | ✅ DONE | platforms, containers, wsl | System detection (fast tier) |
| Phase 2.1 | ✅ DONE | package-managers | Multi-distro package checking — _is_pkg_installed, check_system_deps, _build_pkg_install_cmd |
| Phase 2.2 | ✅ DONE | devops-tools, package-managers, services | TOOL_RECIPES (50+ tools), _get_system_deps(), install_tool() rewritten, 3 consumers migrated |
| Phase 2.3 | ✅ DONE | package-managers, shells | Resolver engine — _pick_install_method, _collect_deps, resolve_install_plan, POST /audit/install-plan |
| Phase 2.4 | ✅ DONE | sudo-security, shells | Execution engine — _run_subprocess(), execute_plan_step(), execute_plan(), install_tool() rewritten as wrapper |
| Phase 2.5 | ✅ DONE | package-managers, language-pms | Version detection — VERSION_COMMANDS (42 tools), get_tool_version(), update_tool(), check_updates(), 3 new routes |
| Phase 3 | ✅ DONE | choices, inputs, disabled-options, pages-install | Frontend — streamSSE(), showStepModal(), installWithPlan(), POST /audit/install-plan/execute (SSE), resumeWithPlan(). All callers rewired. |
| Phase 4 | 🔍 NEEDS AUDIT | choices, inputs, version-selection, network | Impl-status doc claims 100%. Not independently verified against phase spec + domain docs. |
| Phase 5 | 🔍 NEEDS AUDIT | build-systems, compilers, build-from-source | Impl-status doc claims ~95%. Not independently verified against phase spec + domain docs. |
| Phase 6 | 🔍 NEEDS AUDIT | gpu, kernel, hardware-detect | Impl-status doc claims ~95%. Not independently verified against phase spec + domain docs. |
| Phase 7 | 🔍 NEEDS AUDIT | data-packs, ml-ai | Impl-status doc claims ~90%. Not independently verified against phase spec + domain docs. |
| Phase 8 | 🔍 NEEDS AUDIT | services, config-files, restart, parallel-execution | Impl-status doc claims ~95%. Not independently verified against phase spec + domain docs. |

> **📋 Full implementation audit:** See `tool-install-v2-implementation-status.md`
> for per-item breakdown with spec sources and impact analysis.

## 4. Scenarios

| Document | Status | Scope |
|----------|--------|-------|
| `tool-install-v2-phase2.3-scenarios.md` | ✅ DONE | 55 resolver scenarios for simple tools |
| `scenario-cross-domain.md` | ✅ DONE | 8 scenarios — Docker CE, PyTorch+CUDA, cargo-audit Alpine, DevOps stack, Hugo WSL2, OpenCV CUDA, Air-gapped K8s, ML env |
| `scenario-failure-modes.md` | ✅ DONE | 22 failure scenarios — auth, network, disk, permissions, tool errors, partial installs, env, timeouts |
| `scenario-interop.md` | ✅ DONE | 15 scenarios — WSL, Docker-in-Docker, SSH remote, CI/CD, K8s pods, Vagrant, ARM64, nested virt |

---

## 5. Document Lifecycle

```
🟡 TODO     → Not yet written
🔵 DRAFT    → Written but not reviewed/traced
✅ DONE     → Analyzed, traced, reviewed
📦 LEGACY   → Superseded but kept for context
🔄 EVOLVING → Being actively expanded/restructured
```

**Evolution rules:**
1. A domain doc can grow indefinitely — it covers a CONCERN
2. A phase doc is frozen once analysis is complete — it covers a MILESTONE
3. When a doc gets too large, split it. Update this index.
4. When understanding changes, update the doc. Don't create a new one
   unless the old one is fundamentally wrong.
5. Cross-references use filenames, not line numbers.
6. NOTHING is declared impossible. If it can be automated with safeguards,
   it gets a recipe. Kernel recompilation, GPU driver install, WSL kernel
   custom builds — all are in scope.

---

## 6. How to Navigate

- **"I want to understand the system"** → Read arch-principles.md,
  then arch-recipe-format.md, then arch-plan-format.md

- **"What does the system detect?"** → Read arch-system-model.md
  then the relevant domain docs (domain-gpu.md, domain-kernel.md, etc.)

- **"How does tool X get installed?"** → Read domain-devops-tools.md
  for simple tools, or the relevant domain doc for complex software

- **"What's the implementation plan?"** → Read the phase docs in order

- **"What could go wrong?"** → Read scenario-failure-modes.md

- **"Can we do X on platform Y?"** → Check domain-platforms.md
  and domain-containers.md / domain-wsl.md

- **"What's the user experience?"** → Read domain-choices.md,
  domain-disabled-options.md, and the arch-plan-format.md
