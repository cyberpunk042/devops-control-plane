# Version Compatibility System v2

AST-based detection, coupled detection-fix, verification loop, multi-language support.

## Why v2

v1 had systemic failures:
- Regex detection missed `datetime.UTC` entirely — 18 files undetected
- Fix searched for `"datetime.UTC"` but code had `from datetime import UTC` — different string
- Steps auto-marked done on failure
- No transitive import awareness — web's tests failed because core had incompatible code
- No verification — fixes were accepted without proving they worked

## Architecture

```
orchestrator.py          ← Single entry point
├── database/            ← Feature entries (YAML), schema, registry
│   └── entries/         ← Per-language feature databases
│       ├── python/      ← 21 entries (stdlib, syntax, typing, builtins, exceptions)
│       ├── javascript/  ← 5 entries (ES2020)
│       └── go/          ← 5 entries (Go 1.21)
├── analysis/            ← AST detection, import chains, version resolver
├── backends/            ← Language-specific AST parsing (Python implemented)
├── fix/                 ← Transform engine, rollback, verification
└── lifecycle/           ← State machine, step executor, batch runner
```

## Quick Start

```python
from src.core.services.compat.orchestrator import CompatOrchestrator

compat = CompatOrchestrator.create()

# Assess a target
assessment = compat.assess("core", "3.8")
print(f"Achievable: {assessment.achievable}")
print(f"Fixes needed: {assessment.code_fixes_auto} auto + {assessment.code_fixes_manual} manual")

# Analyze with transitive imports
result = compat.analyze("web", "3.8", include_transitive=True)
print(f"Direct: {len(result.direct_findings)}, Transitive: {len(result.transitive_findings)}")

# Fix all auto-fixable findings
fix_result = compat.fix_all("core", "3.8")
print(f"Fixed: {fix_result.verified_fixes}/{fix_result.total_fixes}")
```

## API Routes

- `POST /api/compat/analyze` — Analyze a module
- `POST /api/compat/assess` — Pre-plan assessment
- `POST /api/compat/fix/apply-all` — Apply all auto-fixes
- `GET /api/compat/features` — Browse feature database
- `GET /api/compat/features/stats` — Database statistics

## Feature Database

31 entries across 3 languages. Each entry has:
- AST-based detection (not regex)
- Coupled fix transforms
- Verification rules
- Edge cases with tests
- Before/after test cases

## Key Principles

1. **Never guess** — AST, not regex
2. **Never disconnect** — detection and fix are one unit
3. **Never lie** — step state reflects reality (FAILED = FAILED, never auto-marked done)
4. **Never silo** — follow import chains across module boundaries
5. **Never skip verification** — every fix proves itself
6. **Never auto-mark** — only verified success marks done

## Spec Documents

37 documents in `.agent/plans/compat-v2/` covering full architecture,
all 10 language modules, edge cases, and migration plan.
