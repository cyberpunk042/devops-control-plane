# Missing Pieces — Consolidated from Audit

> **Created:** 2026-02-25
> **Source:** `audit-doc-vs-code-full.md` + `audit-domain-docs.md`
> **Cross-checked against:** SRP-refactored codebase (post-monolith deletion)

---

## Audit corrections (items the audit flagged ❌ that actually exist)

| Audit claim | Reality | Location |
|-------------|---------|----------|
| P11: `save_plan_state()` ❌ | ✅ EXISTS | `execution/plan_state.py` |
| P11: `load_plan_state()` ❌ | ✅ EXISTS | `execution/plan_state.py` |
| P11: `resume_plan()` ❌ | ✅ EXISTS | `execution/plan_state.py` |
| Cycle detection ❌ | ✅ EXISTS | `domain/dag.py:_validate_dag()` |
| Build error analysis ❌ | ✅ EXISTS | `domain/error_analysis.py:_analyse_build_failure()` |
| `_SUDO_RECIPES` ❌ | N/A — intentionally replaced by per-recipe `needs_sudo` dict |
| cuDNN not in doc schema | ⚠️ Doc gap, not code gap — code HAS cuDNN detection |

---

## Real missing pieces — by priority

### 🔴 HIGH — Functional bugs

| # | Issue | Source | Impact |
|---|-------|--------|--------|
| H1 | **Execute endpoint ignores Phase 4 answers** — `/api/audit/execute-plan` calls `resolve_install_plan()` without `answers`, so tools with choices (docker, pytorch) execute with defaults instead of user selections | audit-full L87-95 | **BUG**: User's choice is discarded at execution time |
| H2 | **API contract mismatch** — spec says `POST /audit/install-plan/execute` but code has `POST /api/audit/execute-plan`; request shape also differs | audit-full L79-85 | Spec needs update, or code needs new route |
| H3 | **DAG execution not wired to HTTP** — `execute_plan_dag()` exists but no route dispatches to it | audit-full L97-99 | Plans with `depends_on` can't run from web UI |

### 🟡 MEDIUM — Missing capabilities

| # | Issue | Source | Impact |
|---|-------|--------|--------|
| M1 | **`~/.local/bin` fallback** when sudo unavailable — binary downloads always target `/usr/local/bin/` | domain-binary L169-174 | No-sudo environments can't install binaries |
| M2 | **Checksum verification for curl scripts** — downloaded install scripts not integrity-checked | domain-binary L157-161 | Security gap for curl-pipe-bash |
| M3 | **Build timeout management** — no timeout for cargo/build steps, can run forever | domain-build-systems L216-222 | Build hangs block the entire plan |
| M4 | **Disk space/OOM pre-build checks** — no validation before cargo builds | domain-language-pms L130-135 | Cargo builds fail silently from disk/OOM |
| M5 | **`disk_requirement_gb` pre-build check** — recipe field not used | domain-build-source L273-279 | No pre-flight disk validation |
| M6 | **npm prefix detection for dynamic sudo** — hardcoded `needs_sudo: False` | domain-language-pms L109-114 | Global npm installs fail without sudo |
| M7 | **Version constraints** — no `version_constraint` field in recipes (kubectl ±1, PyTorch→CUDA) | domain-version L723-729 | Users can install incompatible versions |
| M8 | **Confirmation gates (UI)** — no type-to-confirm for high-risk steps | domain-risk L747-753 | Dangerous operations lack double-confirm |

### 🟢 LOW — Nice-to-have / edge-case

| # | Issue | Source | Impact |
|---|-------|--------|--------|
| L1 | ELF binary check on WSL PATH | domain-wsl L36-45 | WSL only, false "installed" for Windows .exe |
| L2 | `ash` explicit entry in profile maps | domain-shells L50-58 | Works by fallback already |
| L3 | Sandbox/confinement detection (snap, Flatpak, SELinux, AppArmor) | domain-shells L62-70 | Only matters in sandboxed envs |
| L4 | Brew batch check optimization | domain-shells L72-80 | Performance only, ~2s saving |
| L5 | nvm detection | domain-language-pms L116-120 | Affects version-specific node installs |
| L6 | Network registry reachability per-PM | domain-language-pms L122-128 | Better error messages on network failures |
| L7 | Alpine community repo detection | domain-repos L188-193 | Alpine containers only |
| L8 | Corporate proxy/registry blocking | domain-repos L195-200 | Enterprise environments |
| L9 | Go compiler in detection list | domain-compilers L245-250 | `go version` not parsed as compiler |
| L10 | ccache integration | domain-build L224, domain-build-source L289 | Performance optimization for rebuilds |
| L11 | `progress_regex` build progress | domain-build-source L281-287 | Better build UX, not correctness |
| L12 | CPU features detection (/proc/cpuinfo flags) | domain-hardware L392-396 | SIMD optimization detection |
| L13 | Hardware constraint evaluation function | domain-hardware L398-402 | Inline in resolver, not separate function |
| L14 | Offline/airgapped binary install | domain-binary L163-167 | Requires pre-download infrastructure |
| L15 | True async parallel dispatch | domain-parallel L846-852 | DAG runs sequentially, correct but slow |
| L16 | `_check_pending_plans()` auto-scan on startup | domain-restart L596-603 | Must know plan_id to resume |
| L17 | Parallel SSE streams for DAG steps | audit-full L101-103 | Sequential SSE, DAG parallelism not streamed |

### 📝 DOC-ONLY — Spec needs updating (no code change)

| # | Issue | Notes |
|---|-------|-------|
| D1 | `estimated_time` field not in any recipe/plan | Spec claims it, code never had it |
| D2 | `learn_more` field not in any recipe/plan | Spec claims it, code never had it |
| D3 | `description` not systematic in choice options | Some options have it, most don't |
| D4 | Undocumented plan fields: `risk_summary`, `risk_escalation`, `confirmation_gate` | Code returns them, spec doesn't document them |
| D5 | `config_templates` spec severely oversimplified | Real format is richer (list, `id`, `format`, `inputs`, `post_command`) |
| D6 | `needs_sudo` can be bare bool or dict | Spec says always dict, vfio uses bare bool |
| D7 | 30+ stale "Phase N future" labels across all domain docs | Code implemented them, docs not updated |
| D8 | `_ARCH_MAP` in doc vs code have different entries | armv7 vs armhf, missing AMD64/arm64/i686 |
| D9 | `build_tools` detection schema (bool vs version) | Code returns bool, spec says {available, version} |
| D10 | State directory path (spec vs code differ) | `~/.local/share/` vs `<project>/.state/` |
| D11 | All line number references in both audit docs are now wrong | Monolith deleted, code is in SRP modules now |

---

## Recommended work order

1. **H1 first** — the choices-lost-at-execution bug is a functional regression
2. **H3** — wire DAG execution to HTTP
3. **M3** — build timeouts (prevents hung processes)
4. **M1** — `~/.local/bin` fallback (usability)
5. **M2** — checksum verification (security)
6. **D7** — batch-update all stale phase labels in docs
7. Everything else by priority band
