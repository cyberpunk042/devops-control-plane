# Compat V2 Database — Full Evolution Plan

> 1000 entries across 10 languages. Only 11% have automation.
> Goal: every entry has accurate detection and maximum automation.

---

## Current State (2026-03-20)

| Language | Entries | Auto | Manual | Info | Auto % |
|----------|---------|------|--------|------|--------|
| python | 443 | 215 | 17 | 211 | 49% (93% of non-info) |
| javascript | 254 | 239 | 0 | 15 | 94% ✅ |
| go | 69 | 67 | 0 | 2 | 97% ✅ |
| php | 42 | 42 | 0 | 0 | 100% ✅ |
| java | 35 | 32 | 0 | 3 | 91% ✅ |
| ruby | 36 | 22 | 0 | 14 | 61% ✅ |
| csharp | 33 | 33 | 0 | 0 | 100% ✅ |
| rust | 32 | 30 | 0 | 2 | 94% ✅ |
| elixir | 31 | 21 | 0 | 10 | 68% ✅ |
| typescript | 25 | 21 | 0 | 4 | 84% ✅ |
| **TOTAL** | **1000** | **722** | **17** | **261** | **72% (98% of actionable)** |

> Updated 2026-03-20. All non-Python languages at 100% auto of actionable.
> Python at 93% — 17 remaining are syntax-level (match/case, except*, etc.)

---

## Target State

| Language | Auto % Target | Priority | Reason |
|----------|---------------|----------|--------|
| python | 95%+ | P0 | Active project language |
| javascript | 80%+ | P1 | Common in web projects |
| typescript | 80%+ | P1 | Shares parser with JS |
| go | 80%+ | P2 | Common in DevOps |
| rust | 70%+ | P2 | Growing adoption |
| ruby | 70%+ | P3 | Established but stable |
| java | 70%+ | P3 | Enterprise |
| csharp | 70%+ | P3 | Enterprise |
| php | 60%+ | P3 | Established |
| elixir | 60%+ | P4 | Niche |

---

## Phase 1: Python to 95% (current focus)

### Done ✅
- Engine matchers: 30 matchers (16 original + 14 new)
- Detection fixes: 35 broad entries fixed with has_keyword, func_value_id
- Strategy upgrades: dataclass/field/zip kwargs → rewrite_expression (remove_keyword_arg)
- Backport transforms: importlib.resources.files → conditional_import
- Path.is_relative_to → rewrite
- ast.unparse → conditional_import
- bytes.removeprefix/removesuffix → rewrite_method_call
- Actionable findings for core module: 2481 → 205, 100% auto-fixable
- Audit script: permanent CI-ready quality checker

### Remaining Python work
- 152 manual entries still exist (many are import-based features for 3.9-3.13)
- Many of these are `from X import Y` where Y doesn't exist in older Python
  → Can be fixed with `conditional_import` transforms (try/except pattern)
- Some are truly new syntax (match/case, except*) → can't auto-fix downgrade
  but CAN show exact locations and guide
- Run the audit script on ALL Python entries, not just above-3.8

### Automation categories for remaining Python manual entries:
1. **Import-based (new stdlib modules/functions)**: ~80 entries
   - Pattern: `from asyncio import TaskGroup` → doesn't exist in 3.8
   - Fix: `conditional_import` with backport OR `remove_import` with code refactor
   - Estimate: 60% can get conditional_import transforms

2. **New method parameters**: ~20 entries (DONE — has_keyword + remove_keyword_arg)

3. **New syntax**: ~15 entries (match/case, except*, type statement, walrus)
   - Can't mechanically downgrade syntax
   - CAN show locations, guide, and suggest manual rewrites
   - These are legitimately manual

4. **Behavioral changes**: ~20 entries (already downgraded to info)

5. **Removed modules**: ~15 entries (cgi, aifc, audioop, etc.)
   - Can add conditional_import with suggested alternatives
   - Some have direct backport packages

---

## Phase 2: JavaScript/TypeScript (279 entries)

### What's needed:
- JS/TS parser backend (tree-sitter or regex-based)
- Detection rules need review (currently only Import-based)
- Fix transforms: mostly import rewrites and syntax downgrades
- Many ES2015-ES2024 features have Babel-style transforms

### Categories:
- **Import/require patterns**: module.exports → import/export
- **Syntax transforms**: optional chaining (?.), nullish coalescing (??)
- **API availability**: Array.at(), Object.hasOwn(), etc.
- **Node.js API**: new built-in modules, changed APIs

---

## Phase 3: Go (69 entries)

### What's needed:
- Go parser backend
- Detection: mostly import-based (new stdlib packages) + syntax (generics)
- Fix: conditional compilation, build tags, or version-specific import paths

---

## Phase 4: Other Languages (199 entries)

Rust, Ruby, Java, C#, PHP, Elixir — each needs:
- Parser backend or regex-based detection
- Language-specific fix transforms
- Review of all entries for detection accuracy

---

## Tracking

### Python Progress
- [ ] Run audit on ALL 443 Python entries (not just above-3.8)
- [ ] Categorize all 152 manual entries by fixability
- [ ] Add conditional_import transforms for import-based manual entries (~80)
- [ ] Add remove_keyword_arg transforms for remaining param-based entries
- [ ] Verify: target 95% auto on full Python set
- [ ] CI check: audit script runs on every database change

### Engine Progress
- [x] has_keyword matcher
- [x] has_keyword_value matcher
- [x] func_value_id matcher
- [x] func_value_attr matcher
- [x] arg_is_binop_bitor matcher
- [x] decorator_name matcher
- [x] module_is / module_startswith matcher
- [x] left_is_dict / right_is_dict matcher
- [x] remove_keyword_arg transform
- [ ] JS/TS parser backend
- [ ] Go parser backend
- [ ] Regex-based fallback for languages without AST parsers

### Database Quality
- [x] Audit script (audit_entries.py)
- [x] Fix script (fix_broad_entries.py)
- [x] Strategy upgrade script (fix_strategies.py)
- [ ] CI integration: audit runs on PR
- [ ] Per-entry test validation: detect → fix → re-detect cycle
