# Tool Install V2 — Master Index

Last updated: 2026-02-24

This is the root document. All analysis, planning, and architecture
documents are organized here by domain and by phase.

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

These documents define the system's identity. They don't change per
phase — they GROW as we understand more.

| Document | Status | What it defines |
|----------|--------|----------------|
| `arch-principles.md` | 🟡 TODO | Core principles: decision trees, always-present/sometimes-disabled, user-decides/system-suggests, extensibility-by-addition, plans-are-deterministic |
| `arch-recipe-format.md` | 🟡 TODO | Canonical recipe format spec. Single source of truth for TOOL_RECIPES schema. Evolves as we add choices, inputs, risk levels |
| `arch-system-model.md` | 🟡 TODO | What the system detects and exposes: distro, pm, capabilities, hardware, kernel, shell, containers, GPU. The "input" contract |
| `arch-plan-format.md` | 🟡 TODO | What the resolver outputs: step types, nesting, conditions, restart points, risk levels. The "output" contract |

## 2. Domain Analysis

Each domain is a CONCERN. Analyzed independently. Referenced by phases.

### 2a. Platform & Environment

| Document | Status | Domain |
|----------|--------|--------|
| `domain-platforms.md` | 🟡 TODO | All platforms: Debian, RHEL, Alpine, Arch, SUSE, macOS, FreeBSD. Package managers, file paths, service systems, default shells |
| `domain-containers.md` | 🟡 TODO | Container runtimes: Docker, Podman, LXC. Detection, limitations (no systemd, read-only layers, no sudo), what works and what doesn't |
| `domain-wsl.md` | 🟡 TODO | WSL1 vs WSL2. Interop (running Windows commands from Linux). Kernel customization. systemd support. Path translation. GUI apps |
| `domain-shells.md` | 🟡 TODO | Shell types: bash, zsh, fish, sh, dash. Profile files. PATH management. Login vs non-login vs interactive. Broken profiles. Restricted shells. Sandboxing (snap, flatpak, SELinux) |

### 2b. Package & Install Methods

| Document | Status | Domain |
|----------|--------|--------|
| `domain-package-managers.md` | 🟡 TODO | All package managers: apt, dnf, yum, apk, pacman, zypper, brew, snap, flatpak. Commands, flags, package naming, repo setup, update, remove |
| `domain-language-pms.md` | 🟡 TODO | Language-level PMs: pip, npm, cargo, go modules, gem, composer. Global vs local. venv/nvm. Permission models. Private registries |
| `domain-binary-installers.md` | 🟡 TODO | Binary downloads: curl | bash, GitHub releases, direct downloads. Architecture detection (amd64, arm64). Signature verification. Install locations (/usr/local/bin, ~/.local/bin) |
| `domain-repos.md` | 🟡 TODO | Repository types: apt sources, dnf repos, PPA, COPR, AUR, Homebrew taps, Flatpak remotes, Docker registries, pip indexes, npm registries. Setup, authentication, trust (GPG keys) |

### 2c. Build & Compilation

| Document | Status | Domain |
|----------|--------|--------|
| `domain-build-systems.md` | 🟡 TODO | Build tools: cmake, make, meson, autotools, ninja, cargo build. Detection. Installation. Build flag management. Cross-compilation |
| `domain-compilers.md` | 🟡 TODO | Compilers: gcc, g++, clang, rustc, go. Toolchain packages (build-essential, Development Tools). Version management |
| `domain-build-from-source.md` | 🟡 TODO | Full pipeline: clone → configure → build → install. Progress reporting. Timeout management. Cache (ccache). Parallel builds |

### 2d. Hardware & Kernel

| Document | Status | Domain |
|----------|--------|--------|
| `domain-gpu.md` | 🟡 TODO | GPU: NVIDIA (CUDA, compute capability, driver), AMD (ROCm), Intel (OpenCL, oneAPI). Detection via lspci, nvidia-smi, rocm-smi. Driver installation |
| `domain-kernel.md` | 🟡 TODO | Kernel: config detection, module loading (modprobe), kernel recompilation, bootloader updates. WSL kernel customization. Safeguards. Rollback |
| `domain-hardware-detect.md` | 🟡 TODO | CPU (arch, features like AVX), RAM, storage, network interfaces. What matters for tool installation |

### 2e. Application Domains

| Document | Status | Domain |
|----------|--------|--------|
| `domain-ml-ai.md` | 🟡 TODO | ML/AI: PyTorch, TensorFlow, JAX, spaCy, HuggingFace. GPU variants. pip index switching. CUDA version matrix. Data/model downloads |
| `domain-data-packs.md` | 🟡 TODO | Data downloads: spaCy models, NLTK data, HuggingFace models, Tesseract language data, locale packs. Size estimation. Multi-select. Progress |
| `domain-devops-tools.md` | 🟡 TODO | Current scope: 35+ devops CLI tools. Categories, dependencies, lifecycle. This is what Phase 2 implements |

### 2f. System Configuration

| Document | Status | Domain |
|----------|--------|--------|
| `domain-services.md` | 🟡 TODO | Service managers: systemd, OpenRC, init.d, launchd, Windows services (via WSL interop). Start, stop, enable, status |
| `domain-config-files.md` | 🟡 TODO | Configuration: daemon.json, nginx.conf, journald.conf, logrotate. Template system. Input variables. Validation |
| `domain-restart.md` | 🟡 TODO | Restart: session (logout/login), service (systemctl restart), system (reboot). Resumable plans. State persistence. WSL shutdown |

### 2g. UX & Choice Architecture

| Document | Status | Domain |
|----------|--------|--------|
| `domain-choices.md` | 🟡 TODO | Decision trees: choice types (single, multi, conditional), branching, depends_on, auto-selection when forced. The UI contract |
| `domain-inputs.md` | 🟡 TODO | User inputs: text, number, path, select. Defaults. Validation (client + server). Template substitution into commands |
| `domain-disabled-options.md` | 🟡 TODO | Always-present/sometimes-disabled. Reasons. Enable hints. Risk levels. How the assistant panel uses this data |
| `domain-version-selection.md` | 🟡 TODO | Version choices: static lists, dynamic (API fetch), version constraints (kubectl ±1 minor from cluster), default selection |

### 2h. Safety & Risk

| Document | Status | Domain |
|----------|--------|--------|
| `domain-risk-levels.md` | 🟡 TODO | Risk tagging: low (pip install), medium (apt install), high (kernel rebuild). UI treatment per level. Confirmation gates. Double-confirm |
| `domain-rollback.md` | 🟡 TODO | Rollback: what can be undone (apt remove), what can't (kernel if boot fails). Backup before high-risk steps. Rollback instructions in plan |
| `domain-sudo-security.md` | 🟡 TODO | Sudo: password caching, root detection, capability-based (no sudo needed). Security model. Never storing passwords |

## 3. Phase Plans

Implementation order. Each phase draws from domain analyses above.

| Document | Status | Dependencies (domains) |
|----------|--------|----------------------|
| `phase1-system-detection.md` | ✅ DONE | platforms, containers, wsl |
| `phase2-index.md` | ✅ DONE | devops-tools, package-managers |
| `phase2.1-package-checking.md` | ✅ DONE | package-managers |
| `phase2.2-dependency-declarations.md` | ✅ DONE | devops-tools, package-managers, services |
| `phase2.3-resolver-engine.md` | ✅ DONE | package-managers, shells |
| `phase2.3-scenarios.md` | ✅ DONE | all phase 2 domains |
| `phase2.4-execution.md` | 🟡 TODO | sudo-security, shells |
| `phase2.5-updates.md` | 🟡 TODO | package-managers, language-pms |
| `phase3-frontend.md` | 🟡 TODO | choices, inputs, disabled-options |
| `phase4-decision-trees.md` | 🟡 TODO | choices, inputs, version-selection |
| `phase5-build-from-source.md` | 🟡 TODO | build-systems, compilers, build-from-source |
| `phase6-hardware.md` | 🟡 TODO | gpu, kernel, hardware-detect |
| `phase7-data-packs.md` | 🟡 TODO | data-packs, ml-ai |
| `phase8-system-config.md` | 🟡 TODO | services, config-files, restart |

## 4. Scenarios

| Document | Status | Scope |
|----------|--------|-------|
| `phase2.3-scenarios.md` | ✅ DONE | 55 resolver scenarios for simple tools |
| `scenario-cross-domain.md` | 🟡 TODO | Complex scenarios spanning multiple domains (OpenCV+CUDA+kernel, PyTorch+GPU+data) |
| `scenario-failure-modes.md` | 🟡 TODO | What goes wrong: broken PATH, missing sudo, disk full, network offline, permission denied, partial install |
| `scenario-interop.md` | 🟡 TODO | WSL interop, Docker-in-Docker, remote SSH install, CI/CD pipeline install |

## 5. Legacy & Superseded

| Document | Status | Notes |
|----------|--------|-------|
| `tool-install-v2-analysis.md` | 📦 LEGACY | Original analysis. Still valid for context. Superseded by domain docs |
| `tool-install-v2-phase2-recipe-unification_draft.md` | 📦 SUPERSEDED | Early draft. Replaced by phase2.2 |
| `tool-install-v2-scope-expansion.md` | 📦 EVOLVING | First scope expansion. Will be broken into domain docs |

---

## 6. Document Lifecycle

Documents go through states:

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
5. Cross-references use filenames, not line numbers (lines change).

---

## 7. How to Navigate

- **"I want to understand the system"** → Read arch-principles.md,
  then arch-recipe-format.md, then arch-plan-format.md

- **"What does the system detect?"** → Read arch-system-model.md
  plus the relevant domain docs (domain-platforms.md, domain-gpu.md, etc.)

- **"How does tool X get installed?"** → Read domain-devops-tools.md
  for simple tools, or the relevant domain doc for complex software

- **"What's the implementation plan?"** → Read the phase docs in order

- **"What could go wrong?"** → Read scenario-failure-modes.md

- **"Can we do X on platform Y?"** → Check domain-platforms.md
  and domain-containers.md / domain-wsl.md
