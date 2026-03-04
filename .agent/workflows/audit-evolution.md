---
description: Execution workflow for audit system evolution — every layer, every language, every step
---

# Audit System Evolution — Execution Workflow

> This workflow guides the actual execution of `.agent/plans/audit-system-overhaul.md`.
> It is the **process discipline document** — not the plan (what), but the how.

---

## Guiding Principles

1. **This is an EVOLUTION, not a patch.** Every layer (L0, L1, L2, scoring, models,
   directive) evolves together. We don't "add JS support to L2" while L0 is still
   returning `PythonInfo` as if the world is Python.

2. **Every layer does its FULL JOB.** L0 detects ALL runtimes, not just Python.
   L1 parses ALL manifests, not just 7 of 13. L2 analyzes ALL file types, not just `.py`.
   Scoring reflects ALL languages, not just Python health.

3. **The plan is ALIVE.** If we discover during execution that a step needs splitting,
   merging, reordering, or rethinking — we STOP, DISCUSS, UPDATE THE PLAN, then continue.
   The plan serves us, we don't serve the plan.

4. **Vertical slices over horizontal layers.** When possible, evolve a feature all the
   way through (model → parser → quality → scoring → directive) rather than doing all
   models first, then all parsers, then all scoring. This gives us working end-to-end
   value sooner.

5. **No silent assumptions.** If the current layer's code reveals something the plan
   didn't account for, SAY IT. Don't hide it. Don't assume you can fix it later.

---

## What Each Layer Currently Does vs. What It Should Do

### L0 — Detection (l0_detection.py)
**CURRENTLY**: Detects OS, Python runtime, venvs, system tools, modules, manifests.
- `_detect_python()` — returns `PythonInfo` (Python-specific: version, implementation, executable, prefix)
- `_detect_venv()` — returns `VenvInfo` (Python-specific: venvs, active_prefix)
- `_detect_tools()` — scans PATH for tools (already multi-lang: node, go, rust, etc.)
- `_detect_modules()` — reads project.yml (already multi-stack)
- `_detect_manifests()` — finds manifest files (already multi-ecosystem)

**EVOLUTION**:
- `_detect_python()` → `_detect_runtimes()` — detect ALL runtime environments:
  Python (version, venvs), Node (version, nvm, npm/yarn/pnpm), Go (version, GOPATH),
  Rust (version, cargo), Ruby (version, rbenv/rvm, bundler), Java (version, maven/gradle),
  .NET (version, SDK), PHP (version, composer), etc.
- `_detect_venv()` → absorbed into `_detect_runtimes()` as per-language env detection
- models.py: `PythonInfo` → `RuntimeInfo` (language-agnostic), `VenvInfo` → absorbed
  into per-runtime env data

### L1 — Classification (l1_classification.py + l1_parsers.py)
**CURRENTLY**: Parses 7 manifest types, classifies deps against catalog, detects
frameworks/ORMs/clients/crossovers.
- `l1_parsers.py` PARSERS: requirements.txt, pyproject.toml, package.json, go.mod,
  Cargo.toml, Gemfile, mix.exs

**EVOLUTION**:
- Add missing manifest parsers: pom.xml (Maven), build.gradle (Gradle), composer.json
  (PHP), *.csproj/*.sln (.NET), Package.swift (Swift), *.cabal/stack.yaml (Haskell)
- Catalog coverage for all ecosystems (already partially there)

### L2 — Source Analysis (l2_quality.py, l2_structure.py)
**CURRENTLY**: Python-only. `parse_tree()` → `rglob("*.py")` → `_file_health()` with
5 Python dimensions.

**EVOLUTION**:
- `parse_tree()` → scans ALL file types through parser registry
- `_file_health()` → uses per-language quality rubrics
- `_detect_hotspots()` → language-aware thresholds
- `_build_import_graph()` → all languages' import systems
- `_naming_analysis()` → per-language naming conventions

### Scoring (scoring.py)
**CURRENTLY**: Complexity uses ecosystem count + module count + deps. Quality uses
Python-specific checks (ruff, mypy, black) with hardcoded tool IDs.

**EVOLUTION**:
- Quality tooling dimension: language-adaptive tool checks (eslint for JS, clippy
  for Rust, not just ruff/mypy)
- Code health dimension: multi-language aggregate from L2
- Structure dimension: not Python-venv-specific

### Models (models.py)
**CURRENTLY**: `PythonInfo`, `VenvInfo`, `L0Result` — Python-centric envelope.

**EVOLUTION**:
- `RuntimeInfo` — language-agnostic runtime detection
- `L0Result` — replaces `python` + `venv` with `runtimes: list[RuntimeInfo]`
- `FileAnalysis-related types` live in `parsers/_base.py`

---

## Execution Steps — Per Work Session

### Before EVERY change:

1. **Read the plan** — `.agent/plans/audit-system-overhaul.md` — confirm which sub-phase
   we're on and what it requires.

2. **Read the coverage tracker** — `.agent/plans/audit-coverage-tracker.md` — confirm
   current state of coverage.

3. **Read the source files** being modified — FULL content, not outlines. Understand
   every function, every access pattern, every consumer.

4. **State the change out loud** — Before writing code, describe:
   - What file(s) are being modified
   - What the change does
   - What consumers will be affected
   - What backward compatibility guarantees are maintained
   - What tests / verification will confirm the change worked

5. **Wait for acknowledgment** — The user drives. Get confirmation before executing.

### During EVERY change:

1. **One file at a time** — Don't edit 5 files in parallel. Edit one, verify it's right,
   then move to the next.

2. **Verify after each file** — Does the web server still start? Do imports resolve?
   Are there syntax errors?

3. **Announce regressions immediately** — If something breaks, say so. Don't try to
   fix it silently and hope we don't notice.

### After EVERY sub-phase:

1. **Update the coverage tracker** — Change ❌ → 🔧 → ✅ as appropriate.

2. **Update the plan** — Mark the sub-phase as complete. Add notes about anything
   discovered during execution that affects future phases.

3. **Verify the web server** — `./manage.sh web` still starts and serves the admin panel.

4. **Verify the audit** — The audit directive still renders. Existing Python audit data
   still displays correctly.

---

## Phase Execution Order (Recommended)

The plan has 8 phases. But the execution order should be **vertical slices**, not
horizontal layers. Here's the recommended order:

### Chunk 1: Foundation + Python Parser Migration (Plan Phase 1)
**Goal**: New model, registry, Python parser migrated, fallback parser. No new languages
yet, but the architecture is ready for them.

Steps:
1. `_base.py` — universal `FileAnalysis`, `SymbolInfo`, `ImportInfo`, `SymbolLocation`
2. `parsers/__init__.py` — `ParserRegistry` class
3. `python_parser.py` — refactor to implement `BaseParser`, output universal model
4. `_fallback_parser.py` — generic line-counter for any unknown file type
5. `parse_tree()` — now routes through registry, scans all extensions
6. `l2_quality.py` — adapt to universal model (but still only Python rubric)
7. `l2_structure.py` — adapt to universal model (but still only Python imports)
8. **Verify**: audit card still renders exactly as before for Python modules

### Chunk 2: Models Evolution (Plan Phase 1 extension)
**Goal**: L0 models become language-agnostic.

Steps:
1. `models.py` — `RuntimeInfo` replaces `PythonInfo` + `VenvInfo`
2. `l0_detection.py` — `_detect_runtimes()` replaces `_detect_python()` + `_detect_venv()`
3. `l0_detection.py` — Python remains the first runtime detected; others added progressively
4. `scoring.py` — adapt quality tooling dimension to not hardcode Python tool IDs
5. **Verify**: L0 system profile still returns correct Python data, just in new shape

### Chunk 3: First New Language End-to-End (Plan Phase 2 partial)
**Goal**: JavaScript/TypeScript works end-to-end: parser → quality → structure → directive.
This is the proof that the architecture works for non-Python.

Steps:
1. `javascript_parser.py` — regex-based JS/TS parser
2. Quality rubric for JS added to rubric registry
3. `l2_quality.py` — test that JS files get scored
4. `l2_structure.py` — JS/TS imports feed into import graph
5. Directive renders multi-language breakdown
6. **Verify**: audit card shows "22 Python · 66 JS" for this project

### Chunk 4: Templates (Plan Phase 2 partial)
**Goal**: Jinja2/template files properly parsed and scored.

### Chunk 5: Config + CSS (Plan Phase 2-3)
**Goal**: YAML, JSON, Dockerfile, CSS files parsed.

### Chunk 6-N: More languages, scoring, streaming, intelligence (Plan Phases 3-8)
**Goal**: Progressive expansion following the same vertical-slice pattern.

---

## Chunk Boundaries

A chunk is complete when:
- [ ] All files in the chunk are edited
- [ ] Web server starts without errors
- [ ] Existing audit card displays correctly (no regression)
- [ ] New capability is visible (if applicable)
- [ ] Coverage tracker is updated
- [ ] Plan is updated

A chunk NEVER starts before the previous chunk is complete and verified.

---

## Red Flags — STOP Immediately If:

- The audit card breaks for Python (regression)
- Import errors appear in the web server logs
- A change requires touching more than 3 files simultaneously
- You're making a change you didn't announce first
- You're "fixing" something the user didn't ask to fix
- The plan and the code have diverged and you're not sure which is right

---

## Files Involved (complete list)

### Audit engine files (will be modified):
- `src/core/services/audit/models.py` — TypedDicts for all layers
- `src/core/services/audit/parsers/__init__.py` — parser registry
- `src/core/services/audit/parsers/_base.py` — NEW: base parser + universal model
- `src/core/services/audit/parsers/python_parser.py` — refactor to base interface
- `src/core/services/audit/parsers/*.py` — NEW: language-specific parsers (one per chunk)
- `src/core/services/audit/l0_detection.py` — runtime detection evolution
- `src/core/services/audit/l1_parsers.py` — new manifest parsers
- `src/core/services/audit/l1_classification.py` — minor: wider ecosystem support
- `src/core/services/audit/l2_quality.py` — rubric-based scoring
- `src/core/services/audit/l2_structure.py` — multi-lang import graphs
- `src/core/services/audit/scoring.py` — language-adaptive scoring
- `src/core/services/audit/__init__.py` — re-exports

### Directive files (will be modified in Phase 6):
- `src/ui/web/directives/audit_directive.py` — rendering logic
- `src/ui/web/templates/scripts/content/_preview.html` — code peeking JS

### Tracking documents:
- `.agent/plans/audit-system-overhaul.md` — master plan
- `.agent/plans/audit-coverage-tracker.md` — living coverage dashboard
- `.agent/workflows/audit-evolution.md` — THIS file
