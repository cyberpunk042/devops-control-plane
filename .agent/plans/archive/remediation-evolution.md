# Remediation System — Evolution Plan

> **Created:** 2026-02-26
> **Status:** Phase 1–7 COMPLETE — Issues D+E deferred
> **Scope:** `src/core/services/tool_install/data/` + `domain/handler_matching.py` + `resolver/plan_resolution.py`

---

## 1. Problems Identified (5 issues)

### Issue A: Method Not Propagated to Steps (LATENT BUG — CRITICAL)

**The chain:**

1. `plan_resolution.py:180` — `method = ts["method"]` is resolved (e.g. `"_default"`, `"brew"`, `"apt"`)
2. `plan_resolution.py:337-343` — step dict is built **WITHOUT `method` key**
3. `orchestrator.py:261` — `step.get("method", plan.get("method", ""))` → gets `""` because neither exists
4. `install_failure.py:60` — `effective_method = method or _infer_method(stderr)` → falls through to heuristic keyword guessing
5. `handler_matching.py:132` — `METHOD_FAMILY_HANDLERS.get(method)` — if `_infer_method` guessed wrong, wrong handlers fire

**Impact:** For any tool installed via `_default`, the method reaching the cascade is whatever `_infer_method` guesses from stderr. If stderr doesn't contain keywords like "pip", "npm", "cargo", the method resolves to `"_default"` — which is correct for the key but misses the semantic information about what `_default` actually runs.

**Fix:** Attach `"method"` to every step dict in `plan_resolution.py`. This is a one-line fix with high correctness value.

---

### Issue B: Handler Cascade Has No Category-to-Family Intelligence (STRUCTURAL GAP)

**The problem:**

`handler_matching.py:_collect_all_options()` does exactly one Layer 2 lookup:

```python
method_handlers = METHOD_FAMILY_HANDLERS.get(method, [])
```

It does NOT:
1. Check the recipe's `category` to infer secondary families
2. Check the recipe's `requires.binaries` to infer install tooling
3. Check actual install command content

**Why this matters now:**

- `phpstan` is `category: "php"`, install via `_default` → `composer global require`
- `ruff` is `category: "python"`, install via `_default` → `pip install`

Both use `"_default"` as the method key. The cascade sees `METHOD_FAMILY_HANDLERS["_default"]`
for both. It never checks `METHOD_FAMILY_HANDLERS["pip"]` for ruff or any `composer` family for phpstan.

Currently compensated by:
1. Per-tool handlers (Layer 3) — duplicated across phpstan+phpunit
2. Test framework's `category_to_family` mapping — only validates coverage, doesn't fix runtime

**Why this matters at scale:**

Every `composer global require` tool will need the same 2 handlers duplicated in Layer 3.
Every `go install` tool will need GOPATH/version handlers duplicated.
This defeats the purpose of Layer 2.

---

### Issue C: Missing Install-Pattern Layer (ARCHITECTURE GAP)

**Current model:**

```
Layer 3: TOOL_FAILURE_HANDLERS[tool_id]     → per-tool
Layer 2: METHOD_FAMILY_HANDLERS[method_key] → per-PM key
Layer 1: INFRA_HANDLERS                     → cross-tool
Layer 0: BOOTSTRAP_HANDLERS                 → pkg mgr bootstrap
```

**What's missing:**

Between Layer 2 and Layer 3, there's a natural grouping: "install pattern."
Multiple tools share the exact same install command pattern and the exact same
failure modes, but they're not the same tool (Layer 3) and not the same PM key
(Layer 2).

| Pattern | Actual command | Tools sharing it | Shared failures |
|---------|---------------|-----------------|-----------------|
| `composer_global` | `composer global require X/Y` | phpstan, phpunit, (future: php-cs-fixer, laravel, phinx) | PHP memory limit, PHP version mismatch |
| `curl_pipe_bash` | `curl ... \| sh -s -- -y` | cargo, rustup, nvm, helm, starship | Script download failure, GPG key expired, arch mismatch |
| `go_install` | `go install github.com/...@latest` | golangci-lint, gopls, air, delve, buf | GOPATH permission, Go version too old |
| `github_release` | Download binary from GH releases | kubectl, terraform, gh, trivy, lazygit | Rate limit, arch mismatch, checksum |
| `pip_user` | `pip install --user X` | (varies) | PEP 668, pip too old, wheel build failure |

---

### Issue D: Tool Concept Scattered Across 3 Files (SRP / COHESION)

A tool's full definition lives in:
1. `recipes.py` — identity, install commands, deps, verify
2. `tool_failure_handlers.py` — per-tool failure handlers
3. `docs/tool_install/tools/*.md` — documentation

To understand, add, or audit a tool, you must read and edit 2-3 files.
At 296 tools, `recipes.py` is 5,800 lines. At 300, these files will be
10,000-15,000 lines each — unmaintainable.

---

### Issue E: Untyped Handler Dicts (MAINTENANCE RISK)

Every handler, option, and recipe field is `dict[str, Any]`.
- No IDE autocomplete
- Typos in keys pass silently until test-time
- Schema enforcement is test-only (`recipe_schema.py` + test framework)
- No distinction between required and optional fields at write-time

---

## 2. Fix Priority & Dependency Order

```
Issue A (method propagation)  ← INDEPENDENT, quick fix, HIGH VALUE
    │
    │  (A must land first — without method on steps, B sees wrong method)
    ▼
Issue B (cascade intelligence) ← DEPENDS ON A
    │
    │  (B gives us _default tools checking their real family)
    │  (But B alone still requires per-tool duplication for patterns)
    ▼
Issue C (install-pattern layer) ← DEPENDS ON B's approach
    │
    │  (C eliminates duplication across tools sharing a pattern)
    │  (C requires a field in the recipe: "install_via" or similar)
    ▼
Issue D (per-tool modules)  ← OPTIONAL, large refactor
    │                         can happen much later
    ▼
Issue E (typed dicts)       ← OPTIONAL, quality-of-life
                              can happen independently
```

---

## 3. Detailed Design Per Issue

### Fix A: Propagate Method to Steps

**File:** `src/core/services/tool_install/resolver/plan_resolution.py`

**Change:** At line 337-343, add `"method": method` to the step dict:

```python
steps.append({
    "type": "tool",
    "label": f"Install {recipe_t['label']}",
    "tool_id": tool_id,
    "command": cmd,
    "needs_sudo": sudo,
    "method": method,       # ← NEW: propagate for handler cascade
})
```

Also propagate `"method"` to the plan-level for the orchestrator's fallback:

```python
plan = {
    ...
    "method": method_for_target,  # ← NEW
}
```

**Risk:** Low. Additive change, doesn't break any existing consumer.
**Test impact:** None — tests don't assert step dict shape for method.
**Effort:** 5 minutes.

---

### Fix B: Cascade Checks Recipe Context

**File:** `src/core/services/tool_install/domain/handler_matching.py`

**Current cascade:**
```
L3: TOOL_FAILURE_HANDLERS[tool_id]
L2: METHOD_FAMILY_HANDLERS[method]
L1: INFRA_HANDLERS
L0: BOOTSTRAP_HANDLERS
```

**Proposed cascade (adds secondary family lookup):**
```
L3:   TOOL_FAILURE_HANDLERS[tool_id]
L2b:  METHOD_FAMILY_HANDLERS[install_via]    ← NEW (if recipe declares it)
L2a:  METHOD_FAMILY_HANDLERS[method]         ← existing
L1:   INFRA_HANDLERS
L0:   BOOTSTRAP_HANDLERS
```

**How `install_via` works:**

The recipe can optionally declare what the `_default` method ACTUALLY runs:

```python
"phpstan": {
    ...
    "install": {
        "_default": ["bash", "-c", "composer global require phpstan/phpstan"],
        "brew": ["brew", "install", "phpstan"],
    },
    "install_via": {"_default": "composer_global"},  # ← NEW FIELD
    ...
}
```

When the cascade processes a failure for phpstan with method="_default":
1. Checks `TOOL_FAILURE_HANDLERS["phpstan"]` (Layer 3)
2. Checks `install_via` → `"composer_global"` → `METHOD_FAMILY_HANDLERS["composer_global"]` (Layer 2b) ← NEW
3. Checks `METHOD_FAMILY_HANDLERS["_default"]` (Layer 2a) ← existing
4. Checks `INFRA_HANDLERS` (Layer 1)
5. Checks `BOOTSTRAP_HANDLERS` (Layer 0)

**Changes required:**

1. `handler_matching.py`: `_collect_all_options()` accepts optional `recipe` parameter (already does!),
   reads `recipe.get("install_via", {}).get(method)` to find the secondary family, scans it.

2. `remediation_handlers.py`: Add `METHOD_FAMILY_HANDLERS["composer_global"]` with the two
   handlers currently duplicated in phpstan and phpunit Layer 3.

3. `recipes.py`: Add `"install_via": {"_default": "composer_global"}` to phpstan and phpunit.

4. `tool_failure_handlers.py`: Remove the duplicated handlers from phpstan and phpunit
   (they'll be covered by the new `composer_global` method family).

**Risk:** Medium. Changes the cascade logic — must be carefully tested.
**Effort:** ~30 minutes.

---

### Fix C: Install-Pattern Families (in METHOD_FAMILY_HANDLERS)

This is enabled by Fix B. Once the cascade supports `install_via`, we define
shared families in `METHOD_FAMILY_HANDLERS`:

```python
METHOD_FAMILY_HANDLERS = {
    ...
    # Install-pattern families (used via install_via, not as method keys)
    "composer_global": [
        # Composer memory exhaustion during global require
        {...},
        # PHP version too old for the package
        {...},
    ],
    "curl_pipe_bash": [
        # Script download failure (distinct from generic network errors)
        {...},
        # GPG/signature verification failed
        {...},
    ],
    # etc.
}
```

These key names don't collide with PM method keys (apt, brew, npm, pip, cargo)
because they use distinct naming (`composer_global`, not `composer`).

**Note:** `composer` the PM vs `composer_global` the pattern are different:
- `composer` = Composer itself being installed (the PM)
- `composer_global` = using Composer to install something else

**Risk:** Low — additive to METHOD_FAMILY_HANDLERS.
**Effort:** Move existing handlers, define new pattern families over time.

---

### Fix D: Per-Tool Modules (FUTURE — large refactor)

**NOT proposed for now.** This would change the file structure from:

```
data/
  recipes.py           (5800 lines, 296 tools)
  tool_failure_handlers.py  (2900 lines)
  remediation_handlers.py   (3200 lines)
```

To something like:

```
data/
  recipes/
    __init__.py        (auto-loads all tool modules)
    _base.py           (shared structures, constants)
    php/
      phpstan.py       (recipe + on_failure in one file)
      phpunit.py
      composer.py
    rust/
      cargo.py
      rustup.py
    ...
  remediation_handlers.py  (method families + infra — stays as-is)
```

**Why defer:** The current single-file approach works with editor search.
The pain point is merge conflicts and cognitive load, not functionality.
This refactor has no correctness benefit — only maintainability. Do it
when the file sizes actually hurt (likely around 400+ tools).

---

### Fix E: TypedDict for Handlers (FUTURE — quality of life)

Define typed shapes:

```python
class RemediationOption(TypedDict):
    id: str
    label: str
    description: str
    icon: str
    recommended: bool
    strategy: str
    # Optional
    method: NotRequired[str]
    dep: NotRequired[str]
    modifier: NotRequired[dict]

class FailureHandler(TypedDict):
    pattern: str
    failure_id: str
    category: str
    label: str
    description: str
    options: list[RemediationOption]
    example_stderr: NotRequired[str]
    exit_code: NotRequired[int]
```

**Why defer:** Tests already validate shape. TypedDict adds IDE support
and catches typos earlier, but the delta is small since tests run fast.
Do it when handler count makes manual verification impractical.

---

## 4. Execution Plan

### Phase 1: Fix A (method propagation) — ✅ COMPLETE

- [x] Add `"method": method` to step dict in `plan_resolution.py`
- [x] Add `"method": method_for_target` to plan dict
- [x] Verify no test regressions
- [ ] Remove the `_infer_method` dependency (becomes true fallback only)

### Phase 2: Fix B + C (install_via + pattern families) — ✅ COMPLETE

- [x] Add `"install_via"` field to recipe schema (`recipe_schema.py`)
- [x] Add `"composer_global"` family to `METHOD_FAMILY_HANDLERS`
- [x] Move phpstan/phpunit duplicated handlers → `composer_global` family
- [x] Add `"install_via": {"_default": "composer_global"}` to phpstan/phpunit recipes
- [x] Update `handler_matching.py` to check `install_via` in cascade
- [x] Update `test_remediation_coverage.py` to validate `install_via` resolution
- [x] Run full test suite — phpstan 323/323, phpunit 323/323, composer 532/532

### Phase 3: Category-to-family (BRIDGE — tie up loose end) — ✅ COMPLETE

- [x] Clarified: `install_via` is explicit/authoritative (production cascade)
- [x] Clarified: `category_to_family` is heuristic safety net (test validation only)
- [x] Removed `"php": "composer_global"` — not all PHP tools use composer global (composer, php don't)
- [x] Added explanatory comments in `_get_all_families_for_tool`
- [x] Verified: php, composer, phpstan, phpunit all pass independently

### Phase 4: Go stack — connect 5 tools to `go` method family — ✅ COMPLETE

- [x] Added `install_via: {"_default": "go"}` to gopls, delve, air, mockgen, protoc-gen-go
- [x] Existing `METHOD_FAMILY_HANDLERS["go"]` (3 handlers) now fire at runtime for all 5 tools
- [x] No duplicated per-tool handlers needed — zero-effort handler inheritance
- [x] All 5 tools: 323/323 (100%) coverage
- [x] golangci-lint NOT included — uses `curl|bash`, not `go install` (different pattern)

### Phase 5: `curl_pipe_bash` — 43 tools connected — ✅ COMPLETE

- [x] Created `METHOD_FAMILY_HANDLERS["curl_pipe_bash"]` with 3 handlers:
  - `curl_tls_certificate` — TLS/cert failures (missing ca-certificates on Docker)
  - `curl_unsupported_arch` — install script can't find binary for OS/arch
  - `curl_script_not_found` — script URL 404/410 or returns HTML
- [x] Added `install_via: {"_default": "curl_pipe_bash"}` to 43 tools
- [x] All 43 tools: FULL COVERAGE (342–817 scenarios each depending on method count)
- [x] Previous stacks unaffected (PHP, Go all still 100%)
- [x] Largest single-batch install_via update — 43 tools connected in one pass

### Phase 6: `github_release` — 31 tools connected — ✅ COMPLETE

- [x] Created `METHOD_FAMILY_HANDLERS["github_release"]` with 3 handlers:
  - `github_rate_limit` — API rate limit exceeded (60/hr unauthenticated)
  - `github_asset_not_found` — no binary for this OS/arch in the release
  - `github_extract_failed` — archive extraction failure (partial download, HTML error page)
- [x] Added `install_via: {"_default": "github_release"}` to 31 tools
- [x] All 31 tools: FULL COVERAGE
- [x] Previous stacks unaffected (PHP, Go, curl|bash all still 100%)

### Phase 7: Connect pip/npm/cargo/go/gem — 82 tools — ✅ COMPLETE

- [x] No new handler definitions needed — METHOD_FAMILY_HANDLERS already has pip (11), npm (7+), cargo, gem families
- [x] Added `install_via` for 82 tools:
  - `pip`: 32 tools (ruff, black, pytest, ansible, numpy, mypy, etc.)
  - `npm`: 23 tools (eslint, prettier, yarn, tsx, playwright, etc.)
  - `cargo`: 18 tools (cargo-watch, delta, just, nushell, hyperfine, etc.)
  - `go`: 6 more tools (lazygit, shfmt, grpcurl, mage, age, dnsx)
  - `gem`: 3 tools (bundler, rubocop, asciidoctor)
- [x] All 82 tools: FULL COVERAGE
- [x] Example: ruff now gets 11 pip-specific handlers (PEP 668, venv, SSL, wheel, etc.)
- [x] Previous stacks unaffected

---

## 5. What We DON'T Do

1. **No class hierarchies** — the data-driven dict approach is correct for this system
2. **No per-tool file split** — premature until file sizes actually hurt
3. **No TypedDict** — tests catch shape errors; typing is a convenience upgrade
4. **No category_to_family in production cascade** — `install_via` is the proper solution;
   the category mapping was always a heuristic that belongs in test validation only

---

## 6. Success Criteria — ✅ ALL MET

- [x] `phpstan` and `phpunit` have 0 duplicated handlers in Layer 3 for memory/version
- [x] Handlers live in `METHOD_FAMILY_HANDLERS["composer_global"]` — shared by all composer-global tools
- [x] Adding a new composer-global tool (e.g. php-cs-fixer) requires NO handler duplication
- [x] The runtime cascade (`handler_matching.py`) delivers the same handlers that the test validates
- [x] Method propagation is explicit, not inferred from stderr heuristics
- [x] Full test suite passes across all connected tools
- [x] **163 tools** (55% of 299) connected to pattern families via `install_via`

## 7. Pattern Family Summary

| Family | Handlers | Tools | How connected |
|--------|----------|-------|---------------|
| `composer_global` | 2 | 2 | New family (Phase 2) |
| `go` | 3 | 11 | Existing family, newly connected |
| `curl_pipe_bash` | 3 | 43 | New family (Phase 5) |
| `github_release` | 3 | 31 | New family (Phase 6) |
| `pip` | 11 | 32 | Existing family, newly connected |
| `npm` | 7+ | 23 | Existing family, newly connected |
| `cargo` | varies | 18 | Existing family, newly connected |
| `gem` | varies | 3 | Existing family, newly connected |
| **Total** | | **163 tools** | |

## 8. Future Work (when needed)

- **Issue D** — per-tool module split (defer until ~400 tools)
- **Issue E** — TypedDict (defer until IDE support becomes critical)
