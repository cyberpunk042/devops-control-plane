# E10 — Wizard Flow Automation: Architecture Exploration

> Milestone: Push automation to maximum across all languages.
> Complex steps get a wizard flow modal with live streaming, progress,
> failure handling, and user choices.
> Philosophy: if it's technically possible, automate it.

---

## Table of Contents

1. [What We're Building](#1-what-were-building)
2. [Package Registry API Map](#2-package-registry-api-map)
3. [Automation Gap Analysis](#3-automation-gap-analysis)
4. [Wizard Flow Modal Design](#4-wizard-flow-modal-design)
5. [Reusable Infrastructure](#5-reusable-infrastructure)
6. [Domain Boundaries](#6-domain-boundaries)
7. [Chunk Breakdown](#7-chunk-breakdown)

---

## 1. What We're Building

### Current State (after E9)

- 58 automatable steps (51%) — config edits, CI scanning, rescan, Python-specific
- 55 manual steps (49%) — dep compat checks, subprocess ops, code audits for non-Python

### Target State

```
TRULY MANUAL (human judgment only):
  - Run test suite              → user's CI/environment, can't automate
  - Replace incompatible syntax → requires understanding intent
  - Review stack baseline       → human decision

EVERYTHING ELSE → AUTOMATED:
  - Dep compat checks           → query package registry APIs (all 7 registries)
  - Package manager ops         → subprocess streaming (go mod tidy, bundle update, etc.)
  - Code audits (non-Python)    → grep for known version-gated patterns
  - Rust edition updates        → edit Cargo.toml edition field

COMPLEX MULTI-STEP → WIZARD FLOW:
  - Interactive dep updates     → wizard: check compat → show incompatible → present alternatives → user picks → apply
  - Subprocess operations       → wizard: preview command → confirm → stream output → handle errors
```

---

## 2. Package Registry API Map

All registries have free, no-auth-required JSON APIs for reads:

| Registry | URL Pattern | Version Field | Rate Limit |
|----------|-------------|---------------|------------|
| **PyPI** | `https://pypi.org/pypi/{pkg}/json` | `info.requires_python` | Generous |
| **npm** | `https://registry.npmjs.org/{pkg}` | `versions.{v}.engines.node` | 5M/month |
| **crates.io** | `https://crates.io/api/v1/crates/{name}` | `crate.rust_version` | User-Agent required |
| **RubyGems** | `https://rubygems.org/api/v1/gems/{name}.json` | `required_ruby_version` | 300/5min |
| **Packagist** | `https://packagist.org/packages/{vendor}/{pkg}.json` | `versions.{v}.require.php` | 10 concurrent |
| **Hex.pm** | `https://hex.pm/api/packages/{name}` | `releases[].requirements` | 100/min, User-Agent required |
| **Maven** | `https://search.maven.org/solrsearch/select?q=g:{g}+AND+a:{a}` | NOT in API (in POM) | None documented |
| **NuGet** | `https://api.nuget.org/v3/registration5-gz-semver2/{id}/index.json` | `dependencyGroups[].targetFramework` | None documented |

### Implementation Notes

- **npm**: Query latest version, check `engines.node` field
- **crates.io**: Direct `rust_version` field (MSRV), requires User-Agent header
- **RubyGems**: `required_ruby_version` field in gem info
- **Packagist**: `require.php` in version metadata
- **Hex.pm**: Requirements in release metadata, needs User-Agent
- **Maven**: No direct API for Java version — would need to fetch POM XML. Mark as partial.
- **NuGet**: `targetFramework` in dependency groups, requires navigating registration API

### Shared Query Pattern

All registries follow the same flow:

```
1. Scan module imports/dependencies (language-specific)
2. Map to package names
3. For each package: GET registry API → extract version constraint
4. Compare constraint against target version
5. Return compatibility report
```

We already have this for PyPI (`dep_checker.py`). The pattern generalizes.

---

## 3. Automation Gap Analysis

### Steps That Become Automated

| Step Type | Languages | Handler | How |
|-----------|-----------|---------|-----|
| Check dep compat | Node | `check_dep_compat_npm` | Query npm registry for engines.node |
| Check dep compat | Rust | `check_dep_compat_crates` | Query crates.io for rust_version |
| Check dep compat | Ruby | `check_dep_compat_rubygems` | Query rubygems.org for required_ruby_version |
| Check dep compat | PHP | `check_dep_compat_packagist` | Query packagist.org for require.php |
| Check dep compat | Elixir | `check_dep_compat_hex` | Query hex.pm for requirements |
| Run go mod tidy | Go | `run_go_mod_tidy` | Subprocess: `go mod tidy` |
| Run bundle update | Ruby | `run_bundle_update` | Subprocess: `bundle update` |
| Run composer update | PHP | `run_composer_update` | Subprocess: `composer update --dry-run` then `composer update` |
| Run dotnet restore | C# | `run_dotnet_restore` | Subprocess: `dotnet restore` |
| Run mix deps.get | Elixir | `run_mix_deps_get` | Subprocess: `mix deps.get` |
| Update Rust edition | Rust | `edit_cargo_toml_edition` | Edit edition field in Cargo.toml |

### Steps That Stay Manual (truly impossible)

| Step | Why |
|------|-----|
| Run test suite | User's CI, secrets, infrastructure |
| Replace incompatible syntax | Requires understanding code intent |
| Review stack baseline | Human judgment call |
| Check dep compat (Maven) | No Java version in Maven API — partial at best |
| Check dep compat (NuGet) | Complex API navigation — partial |

### Projected Coverage After This Milestone

```
Before: 58/113 = 51%
After:  ~85/113 = ~75%
Truly manual: ~28 steps (test suites + code rewrites + reviews)
```

---

## 4. Wizard Flow Modal Design

### When Does the Wizard Open?

The wizard opens when a step involves **multiple sub-operations** or **user choices mid-flow**:

1. **Dep compat check + alternatives** — checks N packages, finds incompatible ones, presents alternatives for each
2. **Subprocess operations** — needs confirmation, streams output, handles errors
3. **Interactive dep update** — walks user through each incompatible dep one by one

Single-shot operations (config edits, rescan) keep the current preview→apply inline pattern.

### Wizard Modal Architecture

```
┌─────────────────────────────────────────────────────┐
│  🔧 Automation Wizard: Check Dependency Compat       │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ✅ Step 1: Scan module imports          0.3s       │
│  ✅ Step 2: Query npm registry           2.1s       │
│     ├── express 4.18.2 ............... ✅ compat    │
│     ├── lodash 4.17.21 ............... ✅ compat    │
│     └── node-fetch 3.3.2 ............ ❌ needs ≥18 │
│  ⏳ Step 3: Find alternatives for node-fetch         │
│     ┌──────────────────────────────────────────┐    │
│     │ node-fetch 3.3.2 requires Node ≥18       │    │
│     │                                          │    │
│     │ Compatible versions:                     │    │
│     │   ○ node-fetch 2.7.0  (Node ≥10)  ← LTS │    │
│     │   ○ node-fetch 2.6.13 (Node ≥10)         │    │
│     │   ○ Skip — I'll handle this manually      │    │
│     │                                 [Next →]  │    │
│     └──────────────────────────────────────────┘    │
│  ⭕ Step 4: Summary                                 │
│                                                     │
│  ┌─ Log ──────────────────────────────────────────┐ │
│  │ Scanning 24 imports...                          │ │
│  │ Querying npm: express... OK                     │ │
│  │ Querying npm: lodash... OK                      │ │
│  │ Querying npm: node-fetch... INCOMPATIBLE        │ │
│  └─────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────┤
│                                       [Cancel]      │
└─────────────────────────────────────────────────────┘
```

### Wizard Event Protocol

Backend streams SSE events. Frontend consumes via existing `streamSSE()`.

```
EVENT TYPES:

wizard_start        → {type, total_steps, title}
step_start          → {type, step, label}
log                 → {type, step, line}
progress            → {type, step, percent}
step_done           → {type, step, elapsed_ms, result: {...}}
step_failed         → {type, step, error}

INTERACTIVE EVENTS (new):
choice_required     → {type, step, choice_id, prompt, options: [...]}
                      Frontend shows options, user picks, sends back via POST
choice_response     → POST /api/posture/module-wizard-choice
                      {wizard_id, choice_id, selected: "..."}

done                → {type, ok, summary, changes: [...]}
```

### The Choice Pause Pattern

When the wizard hits a step that needs user input:

```
Backend emits: choice_required {
    choice_id: "alt_node_fetch",
    prompt: "node-fetch 3.3.2 requires Node ≥18",
    options: [
        {value: "node-fetch@2.7.0", label: "Downgrade to 2.7.0 (Node ≥10)", recommended: true},
        {value: "node-fetch@2.6.13", label: "Downgrade to 2.6.13 (Node ≥10)"},
        {value: "skip", label: "Skip — handle manually"},
    ]
}

Backend PAUSES (waits for response).

Frontend shows options in the wizard.
User picks one.

Frontend POSTs: {wizard_id, choice_id, selected: "node-fetch@2.7.0"}

Backend RESUMES with the user's choice.
```

This is the same two-pass pattern as the existing choice modal (`showChoiceModal` → `showStepModal`),
but inline within the wizard flow instead of as separate modals.

### Implementation: Threading Model

The wizard backend needs to:
1. Start streaming SSE events
2. PAUSE mid-stream when a choice is needed
3. WAIT for user response via a separate POST
4. RESUME streaming

Options:
A) **Queue-based**: Backend puts choice on a queue, waits for response on another queue.
   Requires threading/async coordination.
B) **Two-phase**: Wizard runs phase 1 (scan + identify problems), returns results.
   Frontend shows choices. Then phase 2 runs with choices applied.
   Simpler, no mid-stream pausing.
C) **Polling**: Backend emits choice_required and closes stream.
   Frontend POSTs choice. Backend restarts stream from checkpoint.

**Recommendation: Option B (two-phase)**. It's simpler, matches the existing choice modal pattern,
and avoids threading complexity. The wizard has a "scanning" phase (streaming) and a "resolution"
phase (interactive, rendered client-side from scan results).

```
Phase 1: SCAN (SSE streaming)
  → Scan imports → query registry → identify incompatible deps
  → Returns: {compatible: [...], incompatible: [...], alternatives: {...}}

Phase 2: RESOLVE (client-side, no streaming)
  → Frontend walks user through each incompatible dep
  → User picks alternatives
  → Frontend collects all choices

Phase 3: APPLY (SSE streaming)
  → Backend receives choices
  → Applies changes (edit requirements, run package manager)
  → Streams results
```

---

## 5. Reusable Infrastructure

### From existing codebase:

| Component | Location | Reuse |
|-----------|----------|-------|
| `streamSSE()` | `_ops_modal.html` | Generic SSE reader — works for wizard |
| Step progress UI | `_ops_modal.html` | `.step-row`, `.step-icon`, status classes |
| Log area | `_ops_modal.html` | `.step-log-area` with auto-scroll |
| `_run_subprocess_streaming()` | `subprocess_runner.py` | Stream subprocess output |
| `_run_subprocess()` | `subprocess_runner.py` | Blocking subprocess for simple ops |
| Modal stacking | `_modal.html` | `replace: false` for wizard on top of plan |
| Confirmation gates | `_ops_modal.html` | Checkbox / type-to-confirm |
| `modalSteps()` | `_modal.html` | Step indicator with ✓/●/○ |
| PyPI dep checker | `dep_checker.py` | Pattern for all registry queries |
| Choice modal | `_ops_modal.html` | `showChoiceModal()` two-pass pattern |

### New components needed:

| Component | Purpose |
|-----------|---------|
| `wizard_modal.js` logic | In `_system_posture.html` — wizard open/stream/choice/apply flow |
| `wizard.py` backend | SSE streaming endpoint for wizard execution |
| Per-language dep scanners | Scan imports/deps for each language's ecosystem |
| Per-language registry clients | Query npm/crates/rubygems/packagist/hex APIs |
| Subprocess step handlers | `go mod tidy`, `bundle update`, etc. |

---

## 6. Domain Boundaries

### Where new code lives:

```
src/core/services/module_upgrade/
├── automation/
│   ├── config_editor.py         ← existing (all languages done)
│   ├── code_scanner.py          ← existing (Python, extend for others)
│   ├── dep_checker.py           ← existing (PyPI, extend for all registries)
│   ├── executor.py              ← existing (dispatch + rescan)
│   ├── registry_clients.py      ← NEW: npm, crates, rubygems, packagist, hex query functions
│   ├── subprocess_ops.py        ← NEW: go mod tidy, bundle update, composer update, etc.
│   ├── dep_scanner.py           ← NEW: per-language import/dependency scanning
│   └── wizard.py                ← NEW: wizard orchestration (phase 1 scan, phase 3 apply)
```

### SRP:
- `registry_clients.py` — ONLY queries registries. Pure HTTP. No business logic.
- `dep_scanner.py` — ONLY scans module files for dependencies. Returns package lists.
- `subprocess_ops.py` — ONLY runs package manager commands. Uses `_run_subprocess_streaming`.
- `wizard.py` — ONLY orchestrates the multi-phase wizard flow. Calls other modules.

---

## 7. Chunk Breakdown

### Chunk 1: Registry Clients + Dep Scanners

Create the HTTP query functions for all registries and the per-language dependency scanners.

**Files:**
- `registry_clients.py` — query functions for npm, crates, rubygems, packagist, hex
- `dep_scanner.py` — scan package.json deps, go.mod requires, Cargo.toml deps, Gemfile gems, composer.json require, mix.exs deps
- Update `dep_checker.py` — add handlers: `check_dep_compat_npm`, `check_dep_compat_crates`, `check_dep_compat_rubygems`, `check_dep_compat_packagist`, `check_dep_compat_hex`
- Update recipes — mark dep check steps as `automatable: true` with correct `automation_id`
- Update registry — add new handlers

### Chunk 2: Subprocess Operations

Create handlers that run package manager commands with streaming output.

**Files:**
- `subprocess_ops.py` — `run_go_mod_tidy`, `run_bundle_update`, `run_composer_update`, `run_dotnet_restore`, `run_mix_deps_get`
- Update recipes — add subprocess steps as automatable
- Update registry

### Chunk 3: Wizard Flow Modal

Build the wizard UI and backend streaming endpoint.

**Files:**
- Backend: `wizard.py` — SSE streaming endpoint for wizard execution
- Backend: route in `posture.py` — `POST /posture/module-wizard-execute`
- Frontend: wizard modal rendering + `streamSSE()` integration
- Frontend: choice/alternatives UI within wizard
- CSS: wizard-specific styles

### Chunk 4: Wire Everything Together

- Connect dep checkers to wizard flow (scan → show results → alternatives)
- Connect subprocess ops to wizard flow (confirm → stream → handle errors)
- Update all recipes with new automation_ids
- Final validation: automation coverage audit

---

## Open Questions

1. **Dep scanning for non-Python** — Python has `_scan_module_imports()` + dist-info mapping. Other languages need their own scanners:
   - Node: parse `package.json` dependencies
   - Go: parse `go.mod` require
   - Rust: parse `Cargo.toml` [dependencies]
   - Ruby: parse `Gemfile` gem entries
   - PHP: parse `composer.json` require
   - Elixir: parse `mix.exs` deps function
   These are all file parsing — straightforward but each is different.

2. **npm scoped packages** — `@scope/package` needs URL encoding in registry query. Handle it.

3. **Caching** — registry queries should be cached in `.state/` to avoid hammering APIs. TTL?

4. **Timeout/failure** — if a registry is down, wizard should skip that dep and note it, not fail entirely.

5. **Subprocess CWD** — package manager commands need to run in the module directory, not project root.
