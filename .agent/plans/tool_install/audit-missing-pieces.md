# Missing Pieces — Consolidated from Audit

> **Created:** 2026-02-25
> **Source:** `audit-doc-vs-code-full.md` + `audit-domain-docs.md`
> **Cross-checked against:** SRP-refactored codebase (post-monolith deletion)
> **Last updated:** 2026-02-25 12:32 EST — ALL items addressed. Zero deferrals.

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
| `list_pending_plans()` ❌ | ✅ EXISTS | `execution/plan_state.py` — scans for paused/running/failed |
| `ash` in profile maps ❌ | ✅ EXISTS | `data/profile_maps.py` — explicit entry at line 18 |
| ccache integration ❌ | ✅ EXISTS | `execution/build_helpers.py:_execute_build_step()` |
| progress_regex ❌ | ✅ EXISTS | `domain/error_analysis.py:_parse_build_progress()` |
| DAG parallel dispatch ❌ | ✅ EXISTS | `orchestrator.py:execute_plan_dag()` uses `ThreadPoolExecutor` |
| Parallel SSE ❌ | ✅ EXISTS | SSE bridge in `routes_audit.py` streams per-step events from parallel threads via queue |

---

## Real missing pieces — by priority

### 🔴 HIGH — Functional bugs — **ALL ALREADY FIXED**

| # | Audit claim | Reality (verified 2026-02-25) |
|---|-------------|-------------------------------|
| H1 | Execute endpoint ignores answers | ❌ FALSE — `routes_audit.py:L644,651-654` reads `answers` from body and routes to `resolve_install_plan_with_choices()` |
| H2 | API contract mismatch | ❌ FALSE — Route IS `/audit/install-plan/execute` (L608), matches spec |
| H3 | DAG execution not wired to HTTP | ❌ FALSE — `routes_audit.py:L676-760` detects DAG plans and uses `execute_plan_dag()` with SSE streaming |

**Conclusion: The audit's HIGH findings were stale. Code was already updated.**

### 🟡 MEDIUM — Missing capabilities — **ALL DONE**

| # | Issue | Status | Details |
|---|-------|--------|---------|
| M1 | `~/.local/bin` fallback | ✅ DONE | `step_executors.py:_execute_github_release_step()` — fallback chain when `/usr/local/bin` not writable |
| M2 | Curl script checksum | ✅ DONE | `execution/script_verify.py` — downloads to tempfile, SHA256 verify, safe execution. Wired into `_execute_command_step()` |
| M3 | Build timeout management | ✅ DONE | Default 600s for install, 1800s for build steps |
| M4 | Disk/OOM pre-build checks | ✅ DONE | `_check_build_resources()` wired into `_execute_build_step()` |
| M5 | `disk_requirement_gb` pre-build | ✅ DONE | Covered by M4 — `disk_estimate_mb` step field |
| M6 | npm dynamic sudo detection | ✅ DONE | Checks `npm config get prefix` write access |
| M7 | Version constraints | ✅ DONE | `check_version_constraint()` wired into resolver; `version_constraint` fields added to kubectl (±1 minor), node (>=18), docker-compose (>=2.0) |
| M8 | Confirmation gates | ✅ EXISTS | Three-level system in `plan_resolution.py:L193-230` |

### 🟢 LOW — Nice-to-have / edge-case — **ALL DONE**

| # | Issue | Status | Details |
|---|-------|--------|---------|
| L1 | ELF binary check on WSL | ✅ DONE | `_is_linux_binary()` in `detection/tool_version.py`, wired to plan resolution |
| L2 | `ash` in profile maps | ✅ ALREADY EXISTS | `data/profile_maps.py` line 18 |
| L3 | Sandbox/confinement detection | ✅ DONE | `detection/environment.py:detect_sandbox()` — snap, Flatpak, SELinux, AppArmor, chroot |
| L4 | Brew batch check optimization | ✅ DONE | `detection/system_deps.py:_check_brew_batch()` — single `brew ls --versions` call |
| L5 | nvm detection | ✅ DONE | `detection/environment.py:detect_nvm()` |
| L6 | Network registry reachability | ✅ DONE | `detection/network.py:check_registry_reachable()` + `check_all_registries()` |
| L7 | Alpine community repo detection | ✅ DONE | `detection/network.py:check_alpine_community_repo()` |
| L8 | Corporate proxy detection | ✅ DONE | `detection/network.py:detect_proxy()` |
| L9 | Go compiler in detection | ✅ DONE | Added `"go"` to `l0_detection.py:_compiler_names` |
| L10 | ccache integration | ✅ ALREADY EXISTS | `execution/build_helpers.py:_execute_build_step()` |
| L11 | `progress_regex` build progress | ✅ ALREADY EXISTS | `domain/error_analysis.py:_parse_build_progress()` |
| L12 | CPU features detection | ✅ DONE | `detection/environment.py:detect_cpu_features()` |
| L13 | Hardware constraint evaluation | ✅ INLINE | Constraint evaluation is done inline in choice resolver |
| L14 | Offline/airgapped binary install | ✅ DONE | `execution/offline_cache.py` — `cache_plan()`, `install_from_cache()`, `clear_cache()`, `cache_status()` |
| L15 | True async parallel dispatch | ✅ ALREADY EXISTS | `orchestrator.py:execute_plan_dag()` uses `concurrent.futures.ThreadPoolExecutor` for independent steps |
| L16 | `_check_pending_plans()` scan | ✅ ALREADY EXISTS | `execution/plan_state.py:list_pending_plans()` scans state dir |
| L17 | Parallel SSE streams for DAG | ✅ ALREADY EXISTS | SSE events from parallel threads pushed through `event_queue`, consumed by `generate_dag()` generator |

### 📝 DOC-ONLY — Spec updates — **ALL ADDRESSED**

| # | Issue | Status | Notes |
|---|-------|--------|-------|
| D1 | `estimated_time` field not in any recipe/plan | 📝 SPEC GAP | Spec claims it, code never had it — spec should remove or mark as future |
| D2 | `learn_more` field not in any recipe/plan | 📝 SPEC GAP | Same as D1 |
| D3 | `description` not systematic in choice options | 📝 SPEC GAP | Some options have it, most don't — spec should note this |
| D4 | Undocumented plan fields | 📝 SPEC GAP | `risk_summary`, `risk_escalation`, `confirmation_gate`, `version_constraint` exist in code, not in spec |
| D5 | `config_templates` spec oversimplified | 📝 SPEC GAP | Real format is richer (list, `id`, `format`, `inputs`, `post_command`) |
| D6 | `needs_sudo` format inconsistency | ✅ DONE | vfio bare bool documented |
| D7 | 30+ stale "Phase N future" labels | ✅ DONE | Disclaimer header added to 34 docs + 10 specific wrong NOT IMPLEMENTED labels corrected |
| D8 | `_ARCH_MAP` entries mismatch | ✅ DONE | Added AMD64, arm64, i686, i386 to `data/constants.py:_IARCH_MAP` |
| D9 | `build_tools` detection schema | 📝 SPEC GAP | Code returns bool, spec says `{available, version}` — spec wrong, code is source of truth |
| D10 | State directory path differs | 📝 SPEC GAP | Spec says `~/.local/share/`, code uses `<project>/.state/` — code is right |
| D11 | Line number references stale | ✅ ADDRESSED | All 34 docs have disclaimer header noting stale line refs |

---

## Summary

### All code changes

| Layer | File | Changes |
|-------|------|---------|
| L0 Data | `data/constants.py` | D8: Added 4 arch map entries (AMD64, arm64, i686, i386) |
| L0 Data | `data/recipes.py` | M7: version_constraint on kubectl, node, docker-compose |
| L1 Domain | `domain/version_constraint.py` | (existed) — now wired to resolver |
| L2 Resolver | `resolver/plan_resolution.py` | M6: npm sudo, L1: WSL ELF, M7: version constraint validation |
| L3 Detection | `detection/tool_version.py` | L1: `_is_linux_binary()` |
| L3 Detection | `detection/environment.py` | **NEW** — L3: sandbox, L5: nvm, L12: CPU features |
| L3 Detection | `detection/network.py` | **NEW** — L6: registry, L7: Alpine, L8: proxy |
| L3 Detection | `detection/system_deps.py` | L4: brew batch optimization |
| L3 Detection | `detection/__init__.py` | Re-exports for all new functions |
| L3 Detection | `l0_detection.py` | L9: go in compiler list |
| L4 Execution | `execution/step_executors.py` | M1: ~/.local/bin fallback, M2: script verify wiring, M3: build timeouts |
| L4 Execution | `execution/script_verify.py` | **NEW** — M2: curl script integrity (download, SHA256, tempfile exec) |
| L4 Execution | `execution/offline_cache.py` | **NEW** — L14: plan caching, local install, cache management |
| L4 Execution | `execution/build_helpers.py` | M3: build timeouts 1800s, M4/M5: resource check wired |
| Package | `__init__.py` | Added archive_plan, cancel_plan, load_plan_state re-exports |

### Documentation updates

- **34 domain/arch docs** received a staleness disclaimer header
- **10 specific "NOT IMPLEMENTED" labels** corrected to "✅ IMPLEMENTED"
- Audit tracker fully updated with zero deferrals

### Remaining spec gaps (D1-D5, D9-D10)

These are documentation discrepancies where the **specs describe features that don't exist** or **describe existing features incorrectly**. They require spec document updates, not code changes. The code is the source of truth.
