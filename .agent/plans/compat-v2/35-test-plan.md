# 35 — Test Plan & Validation Strategy

> **Document**: 35 of 37
> **Milestone**: Validation & migration
> **Status**: Draft

---

## 1. Purpose

The test plan ensures the compat v2 system works correctly across all components, all languages, and all edge cases. Testing happens at four levels: unit, integration, end-to-end, and database validation.

---

## 2. Test Levels

### 2.1 Unit Tests

Test individual components in isolation.

| Component | What's tested | Test count target |
|-----------|--------------|-------------------|
| Feature database schema | Entry validation, required fields, type checks | 50+ |
| Feature registry | Load, query, filter, search | 30+ |
| AST detection (Python) | Each node type matching, exclusion rules | 100+ |
| AST detection (JS/TS) | Node matching per ES version | 80+ |
| AST detection (Go) | Node matching per Go version | 40+ |
| AST detection (other langs) | Node matching per version | 30+ per lang |
| Import resolver (Python) | Absolute, relative, star, dynamic imports | 40+ |
| Import resolver (JS) | ESM, CJS, aliases, re-exports | 30+ |
| Import resolver (other langs) | Language-specific resolution | 20+ per lang |
| Fix transforms | Each transform type: replace_import, rewrite_method, etc. | 60+ |
| Verification checks | Syntax, re-detection, import check | 30+ |
| State machine | Valid transitions, invalid transitions, persistence | 40+ |
| Batch runner | Sequential execution, stop conditions, progress events | 20+ |
| Rollback | Snapshot, rollback, discard, edge cases | 20+ |
| Version comparison | Per-language version parsing and comparison | 30+ |
| Dependency analysis | Manifest parsing, registry querying, compat check | 30+ |

**Total unit tests: ~700+**

### 2.2 Integration Tests

Test component interactions.

| Test area | What's tested | Test count |
|-----------|--------------|------------|
| Detection → Fix pipeline | Detect a finding, apply fix, verify fix removed it | 50+ (per feature type) |
| Analysis → Lifecycle | Analysis result determines correct step state | 20+ |
| Import resolver → Detection | Transitive findings correctly attributed | 15+ |
| Fix → Rollback | Failed fix triggers rollback, file restored | 10+ |
| Batch → State machine | Batch updates state machine correctly for each outcome | 15+ |
| API → Engine | Each API endpoint produces correct engine call | 20+ |
| CLI → Engine | Each CLI command produces correct output | 15+ |

**Total integration tests: ~150+**

### 2.3 End-to-End Tests

Full workflow tests using real module directories.

| Test scenario | Description |
|--------------|-------------|
| Python downgrade 3.11→3.8 | Create a module with datetime.UTC, tomllib, StrEnum. Run full plan. Verify all fixed. |
| Python upgrade 3.8→3.11 | Create a module with backports. Run upgrade plan. Verify backports removed. |
| JS downgrade ES2022→ES2018 | Create module with optional chaining, nullish coalescing. Run plan. |
| Go downgrade 1.21→1.18 | Create module with slices package, min/max. Run plan. |
| Transitive detection | Module A imports Module B which has incompatible code. Verify A's analysis shows transitive findings. |
| Module dependency order | Multiple modules with dependencies. Verify correct fix order. |
| Batch stop on failure | Run batch, one step fails. Verify batch stops, state is correct. |
| Rollback entire plan | Run plan, then rollback. Verify all files restored. |
| Edge case: TYPE_CHECKING | Code with TYPE_CHECKING imports. Verify not flagged. |
| Edge case: try/except import | Code with try/except backport pattern. Verify downgraded severity. |
| Edge case: version gate | Code with sys.version_info check. Verify not flagged. |

**Total E2E tests: ~30+**

### 2.4 Database Validation Tests

Every feature database entry is a test case:

```
For each entry in database/entries/**/*.yml:
  1. Parse test.before → must succeed
  2. Detect feature in test.before → must find >= 1 match
  3. Apply fix to test.before → must produce output
  4. Compare output with test.after → must match
  5. Detect feature in test.after → must find 0 matches
  6. Parse test.after → must succeed
  7. Repeat for each test.additional case
```

**Total database validation tests: ~1010+ entries × ~2.5 avg test cases = ~2500+ test cases**

---

## 3. Test Fixtures

### 3.1 Language fixtures

Pre-built source files for each language with known features:

```
tests/fixtures/
├── python/
│   ├── datetime_utc.py           # Uses datetime.UTC
│   ├── tomllib_usage.py          # Uses tomllib
│   ├── match_case.py             # Uses match/case
│   ├── removeprefix.py           # Uses str.removeprefix
│   ├── type_checking_import.py   # UTC inside TYPE_CHECKING
│   ├── try_except_backport.py    # try/except import pattern
│   ├── version_gate.py           # sys.version_info check
│   ├── star_import.py            # from module import *
│   ├── mixed_annotations.py      # Annotations + runtime usage
│   └── complex_module/           # Multi-file module for import testing
│       ├── __init__.py
│       ├── models.py             # Has datetime.UTC
│       ├── views.py              # Imports models
│       └── tests/
│           └── test_smoke.py
├── javascript/
│   ├── optional_chaining.js
│   ├── nullish_coalescing.js
│   ├── async_await.js
│   └── ...
├── go/
│   ├── slices_usage.go
│   ├── generics.go
│   └── ...
└── ... (per language)
```

### 3.2 Project fixtures

Pre-built multi-module project structures for E2E testing:

```
tests/fixtures/projects/
├── python_multi_module/
│   ├── project.yml
│   ├── src/
│   │   ├── core/
│   │   │   ├── models.py         # datetime.UTC
│   │   │   └── __init__.py
│   │   └── web/
│   │       ├── routes.py         # imports core.models
│   │       └── __init__.py
│   └── requirements.txt
└── js_mono_repo/
    ├── project.yml
    ├── packages/
    │   ├── api/
    │   │   ├── package.json
    │   │   └── src/
    │   └── shared/
    │       ├── package.json
    │       └── src/
    └── package.json
```

---

## 4. CI Integration

### 4.1 CI pipeline

```yaml
# .github/workflows/compat-tests.yml
jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - run: pytest tests/unit/ -v

  integration-tests:
    runs-on: ubuntu-latest
    steps:
      - run: pytest tests/integration/ -v

  e2e-tests:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.8", "3.9", "3.10", "3.11", "3.12"]
    steps:
      - run: pytest tests/e2e/ -v

  database-validation:
    runs-on: ubuntu-latest
    steps:
      - run: controlplane compat validate-db --verbose

  edge-case-tests:
    runs-on: ubuntu-latest
    steps:
      - run: pytest tests/edge_cases/ -v
```

### 4.2 PR checks

Every PR that touches the compat system must pass:
- All unit tests
- All integration tests
- Database validation (if entries changed)
- Edge case tests (if detection/fix code changed)

E2E tests run on merge to main (slower, full matrix).

### 4.3 Coverage target

| Component | Coverage target |
|-----------|----------------|
| Detection engine | 95%+ |
| Fix engine | 95%+ |
| State machine | 100% |
| Verification | 95%+ |
| Rollback | 95%+ |
| API routes | 90%+ |
| CLI commands | 85%+ |
| Language backends | 90%+ per language |

---

## 5. Performance Tests

### 5.1 Benchmarks

| Test | Target |
|------|--------|
| Parse 500 Python files | < 500ms |
| Detect 200 features across 500 files | < 1s |
| Fix 50 files with verification | < 15s |
| Full project analysis (5 modules, 2000 files) | < 5s |
| Build import graph (500 files) | < 500ms |
| Feature database load (1000 entries) | < 200ms |

### 5.2 Regression detection

Performance benchmarks run in CI. If a change makes any benchmark 2x slower, the CI warns (not fails — performance regressions need investigation, not blocking).

---

## 6. Integration Points

### 6.1 With Feature Database (Document 02)
- Database validation is a core test category
- Every entry is a test case

### 6.2 With Edge Case Framework (Document 28)
- Edge case tests validate exclusion rules and context handling
- 100+ edge case tests

### 6.3 With CI/CD
- Full test suite runs in CI
- Database validation prevents broken entries from merging
