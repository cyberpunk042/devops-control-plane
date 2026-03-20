# 07 — Verification Loop Spec

> **Document**: 7 of 37
> **Milestone**: M6 — Verification loop
> **Status**: Draft

---

## 1. Purpose

The verification loop is the system's honesty guarantee. In v1, a fix could be "applied successfully" and then tests would fail because the fix didn't actually work. The system lied — it said the fix was applied, but the incompatibility was still there.

The verification loop ensures: **no fix is ever reported as successful unless it has been PROVEN to work.** Every fix goes through a detect → fix → re-detect → validate cycle. If any step in the cycle fails, the fix is rolled back and reported as failed.

---

## 2. The Verification Cycle

```
    ┌──────────────────────────────────────────┐
    │                                          │
    │   1. DETECT                              │
    │   AST detection finds incompatibility    │
    │   Finding: file X, line Y, feature Z     │
    │                                          │
    │   2. SNAPSHOT                             │
    │   Save original file content             │
    │                                          │
    │   3. FIX                                 │
    │   Apply transform to AST                 │
    │   Write modified source                  │
    │                                          │
    │   4. RE-DETECT                           │
    │   Re-parse the modified file             │
    │   Run SAME detection rule                │
    │   Must find 0 matches for this feature   │
    │                                          │
    │   5. SYNTAX CHECK                        │
    │   Parse the modified file                │
    │   Must have 0 syntax errors              │
    │                                          │
    │   6. IMPORT CHECK                        │
    │   Try to import/compile the file         │
    │   Must succeed                           │
    │                                          │
    │   7. VERDICT                             │
    │   All checks pass → VERIFIED             │
    │   Any check fails → ROLLBACK + FAILED    │
    │                                          │
    └──────────────────────────────────────────┘
```

---

## 3. Verification Steps

### 3.1 Re-detection

After the fix modifies the file, the detection engine re-scans it for the SAME feature:

```python
def verify_re_detection(
    file_path: Path,
    feature_id: str,
    detection_engine: DetectionEngine,
    language: str,
) -> VerificationCheck:
    """Re-run detection on a fixed file.

    The detection must find ZERO matches for the feature.
    If it still finds matches, the fix did not fully remove the incompatibility.
    """
    # Invalidate AST cache — file was just modified
    detection_engine.invalidate_cache(file_path)

    # Re-scan for this specific feature
    findings = detection_engine.analyze_file(
        file_path=file_path,
        language=language,
        target_version="*",  # Not filtering by version — checking specific feature
        feature_ids=[feature_id],  # Only check this feature
    )

    if findings:
        return VerificationCheck(
            check_type="re_detection",
            passed=False,
            message=f"Feature '{feature_id}' still detected at line(s): {[f.line for f in findings]}",
            details={"remaining_findings": len(findings)},
        )

    return VerificationCheck(
        check_type="re_detection",
        passed=True,
        message="Feature no longer detected",
    )
```

**Why this catches v1's failure:**
In v1, `_COMPAT_PATTERNS` searched for `"datetime.UTC"` but the code had `from datetime import UTC`. The search didn't match. The fix "succeeded" (nothing to replace) but the incompatibility remained. With re-detection, the AST detection would still find the `ImportFrom` node with `UTC` → fix verification FAILS → rollback → user sees "fix failed."

### 3.2 Syntax check

After modification, verify the file has valid syntax:

```python
def verify_syntax(
    file_path: Path,
    backend: LanguageBackend,
) -> VerificationCheck:
    """Parse the modified file — must have zero syntax errors."""
    try:
        backend.parse_file(file_path)
        return VerificationCheck(
            check_type="syntax",
            passed=True,
            message="File parses without errors",
        )
    except SyntaxError as e:
        return VerificationCheck(
            check_type="syntax",
            passed=False,
            message=f"Syntax error at line {e.lineno}: {e.msg}",
            details={"line": e.lineno, "error": str(e)},
        )
```

**Why this is needed:**
A buggy transform could produce invalid syntax. For example, incorrectly replacing an import might leave a dangling comma:
```python
# Before: from datetime import datetime, UTC
# Buggy fix: from datetime import datetime,     ← dangling comma, maybe valid maybe not
# Correct fix: from datetime import datetime, timezone
```
The syntax check catches this immediately.

### 3.3 Import check

After modification, verify the file can still be imported/compiled:

```python
def verify_import(
    file_path: Path,
    backend: LanguageBackend,
) -> VerificationCheck:
    """Verify the file can still be imported or compiled.

    Language-specific:
    - Python: subprocess python -c "import module_path"
    - JS/TS: subprocess node -e "require('./file')" or tsc --noEmit
    - Go: go build ./...
    - Rust: cargo check
    - etc.
    """
    try:
        importable = backend.check_importable(file_path)
        if importable:
            return VerificationCheck(
                check_type="import",
                passed=True,
                message="File imports successfully",
            )
        else:
            return VerificationCheck(
                check_type="import",
                passed=False,
                message="File failed to import",
            )
    except Exception as e:
        return VerificationCheck(
            check_type="import",
            passed=False,
            message=f"Import check error: {e}",
        )
```

**Import check per language:**

| Language | Command | What it checks |
|----------|---------|----------------|
| Python | `python -c "import {module_path}"` | Module loads without errors |
| JavaScript | `node -e "require('{file}')"` | File evaluates without errors |
| TypeScript | `tsc --noEmit {file}` | Type-checks without errors |
| Go | `go build {package}` | Package compiles |
| Rust | `cargo check` | Crate compiles |
| Ruby | `ruby -c {file}` | Syntax valid (no runtime check) |
| Java | `javac {file}` | Compiles without errors |
| C# | `dotnet build --no-restore` | Compiles |
| PHP | `php -l {file}` | Syntax valid |
| Elixir | `mix compile --warnings-as-errors` | Compiles |

**When to skip import check:**
- Annotation-only fixes (adding `__future__` import) — syntax check is sufficient
- Files that can't be imported standalone (e.g., they depend on runtime state)
- Configurable per entry: `verification.import_check: false`

### 3.4 Custom checks

Some entries may need custom verification beyond the standard checks:

```yaml
verification:
  re_detect: true
  import_check: true
  syntax_check: true
  custom_check:
    command: "python -c 'from datetime import timezone; assert hasattr(timezone, \"utc\")'"
    description: "Verify timezone.utc is available"
    timeout: 5
```

Custom checks run AFTER the standard checks. They're rare — most entries don't need them.

---

## 4. Data Model

```python
@dataclass
class VerificationCheck:
    """Result of a single verification check."""
    check_type: str           # "re_detection", "syntax", "import", "custom"
    passed: bool
    message: str
    details: dict | None = None
    duration_ms: int = 0


@dataclass
class VerificationResult:
    """Complete verification result for a fix."""
    file_path: str
    feature_id: str
    checks: list[VerificationCheck]
    all_passed: bool
    duration_ms: int

    @property
    def failed_checks(self) -> list[VerificationCheck]:
        return [c for c in self.checks if not c.passed]

    @property
    def errors(self) -> list[str]:
        return [c.message for c in self.checks if not c.passed]


@dataclass
class FileVerificationReport:
    """Verification report for all fixes in a file."""
    file_path: str
    fixes_applied: int
    fixes_verified: int
    fixes_failed: int
    rolled_back: bool
    verifications: list[VerificationResult]


@dataclass
class ModuleVerificationReport:
    """Verification report for all fixes in a module."""
    module_name: str
    files_fixed: int
    files_verified: int
    files_rolled_back: int
    total_fixes: int
    verified_fixes: int
    failed_fixes: int
    file_reports: list[FileVerificationReport]
    duration_ms: int
```

---

## 5. Verification Engine

```python
class Verifier:
    """Run verification checks on fixed files."""

    def __init__(
        self,
        detection_engine: DetectionEngine,
        backend_factory: Callable[[str], LanguageBackend],
    ):
        self._detection = detection_engine
        self._backend_factory = backend_factory

    def verify_fix(
        self,
        file_path: Path,
        feature_id: str,
        language: str,
        entry: FeatureEntry,
    ) -> VerificationResult:
        """Run all verification checks for a single fix.

        Runs checks in order:
        1. Re-detection (if entry.verification.re_detect)
        2. Syntax check (if entry.verification.syntax_check)
        3. Import check (if entry.verification.import_check)
        4. Custom check (if entry.verification.custom_check)

        Stops on first failure — no point checking import if syntax is broken.
        """

    def verify_file(
        self,
        file_path: Path,
        findings_fixed: list[Finding],
        language: str,
    ) -> FileVerificationReport:
        """Verify all fixes in a single file."""

    def verify_module(
        self,
        module_dir: Path,
        all_findings_fixed: list[Finding],
        language: str,
    ) -> ModuleVerificationReport:
        """Verify all fixes in a module."""
```

### 5.1 Check ordering

Checks run in this order for efficiency — fail fast on cheap checks:

1. **Syntax check** (~1ms) — cheapest, catches broken transforms immediately
2. **Re-detection** (~5ms) — verifies the feature is actually gone
3. **Import check** (~100ms–1s) — most expensive, only if previous checks passed
4. **Custom check** (variable) — only if all standard checks passed

If a check fails, subsequent checks are skipped. The first failure is sufficient to trigger rollback.

### 5.2 Batch verification

When multiple fixes are applied to the same file, verification runs ONCE after all fixes:

```python
def verify_file(self, file_path, findings_fixed, language):
    # 1. Syntax check — ONE time for the file
    syntax = verify_syntax(file_path, backend)
    if not syntax.passed:
        return FileVerificationReport(rolled_back=True, ...)

    # 2. Re-detection — for EACH feature that was fixed
    for finding in findings_fixed:
        re_detect = verify_re_detection(file_path, finding.feature_id, ...)
        if not re_detect.passed:
            return FileVerificationReport(rolled_back=True, ...)

    # 3. Import check — ONE time for the file
    import_check = verify_import(file_path, backend)
    if not import_check.passed:
        return FileVerificationReport(rolled_back=True, ...)

    return FileVerificationReport(rolled_back=False, ...)
```

This avoids running the expensive import check N times for N fixes in the same file.

---

## 6. Rollback on Verification Failure

### 6.1 File-level rollback

If ANY verification check fails for a file, ALL fixes to that file are rolled back:

```
File: src/core/models/action.py
Fixes applied: 2 (datetime.UTC, StrEnum)
Verification:
  ✅ Syntax check passed
  ✅ Re-detection: datetime.UTC — not found (good)
  ❌ Re-detection: StrEnum — STILL FOUND at line 15
  → ROLLBACK entire file
  → Both fixes undone (datetime.UTC fix is also reverted)
  → Report: "StrEnum fix did not fully remove the feature"
```

**Why file-level, not fix-level:**
Fixes in the same file may interact. Rolling back one fix while keeping another could produce an inconsistent state. Rolling back the entire file to its pre-fix state is always safe.

### 6.2 Module-level rollback

If too many files fail verification, the system can rollback the entire module:

```python
def should_rollback_module(report: ModuleVerificationReport) -> bool:
    """Decide if the entire module should be rolled back.

    Triggers:
    - More than 50% of files failed verification
    - Any file that was successfully fixed depends on a rolled-back file
    """
```

Module-level rollback is a safety net, not the normal path. Normally, each file's verification is independent.

### 6.3 Rollback reporting

```
Module: core
Files fixed: 14
Verification results:
  ✅ src/core/models/action.py — 2 fixes verified
  ✅ src/core/models/state.py — 1 fix verified
  ❌ src/core/engine/executor.py — 1 fix FAILED, rolled back
     → StrEnum still detected at line 45 after fix
     → Fix template may not handle "from enum import StrEnum" form
  ✅ src/core/observability/health.py — 1 fix verified
  ...

Summary: 13/14 files passed, 1 rolled back
Remaining incompatibilities: 1 (StrEnum in executor.py — fix needs improvement)
```

---

## 7. Entry Self-Test (Database Validation)

The verification loop also validates database entries themselves. Every entry's test case goes through the cycle:

```python
def validate_entry(entry: FeatureEntry, backend: LanguageBackend) -> EntryValidation:
    """Validate a database entry's test case.

    1. Parse entry.test.before — must succeed
    2. Run detection on entry.test.before — must find >= 1 match
    3. Apply fix to entry.test.before — must produce code
    4. Compare result with entry.test.after — must match
    5. Run detection on result — must find 0 matches
    6. Parse result — must succeed

    Runs the same checks for entry.test.additional test cases.
    """
```

**Validation result:**

```python
@dataclass
class EntryValidation:
    entry_id: str
    valid: bool
    test_cases_run: int
    test_cases_passed: int
    test_cases_failed: int
    failures: list[EntryTestFailure]

@dataclass
class EntryTestFailure:
    test_name: str              # "main" or additional test name
    step_failed: str            # "parse_before", "detection", "fix", "compare", "re_detection", "parse_after"
    message: str
    expected: str | None
    actual: str | None
```

### 7.1 CI integration

```
$ controlplane compat validate-db

Validating feature database...

Python (200 entries):
  ✅ python.stdlib.datetime_utc (3 tests)
  ✅ python.stdlib.tomllib (2 tests)
  ❌ python.stdlib.strenum (1 test)
     FAILED: re_detection found 1 match in test.after
     → Fix transform does not handle "from enum import StrEnum" form
  ✅ python.syntax.match_case (1 test, manual fix — detection-only validated)
  ...

Results: 199/200 passed, 1 failed

EXIT CODE: 1 (failure — cannot merge)
```

---

## 8. Continuous Verification

### 8.1 After any code change

When the user modifies code (outside the compat system), the system can re-verify:

```
User edits src/core/models/action.py manually
→ System detects file change
→ Re-runs detection on the file
→ If new incompatibilities introduced: warn
→ If previously fixed incompatibility re-introduced: alert
```

This is optional/on-demand, not automatic — we don't want to constantly scan on every save.

### 8.2 Plan re-validation

Before marking a plan as complete, re-scan the entire module:

```
All steps PASSED in the plan
→ Final verification: re-scan entire module for target version
→ 0 findings → plan truly complete
→ N findings → some incompatibilities crept back in → reopen relevant steps
```

This catches cases where:
- A fix was verified at step 5, but a later step re-introduced the pattern
- A merge brought in new incompatible code
- A dependency was updated and changed its behavior

---

## 9. Performance

### 9.1 Verification cost per fix

| Check | Cost | When skipped |
|-------|------|-------------|
| Syntax check | ~1ms | Never — always run |
| Re-detection | ~5ms | If entry.verification.re_detect is false |
| Import check | ~100ms–1s | If entry.verification.import_check is false |
| Custom check | Variable | If no custom check defined |

Total per fix: ~110ms–1s

### 9.2 Module-level cost

For a module with 15 fixes across 14 files:
- 14 syntax checks: ~14ms
- 15 re-detections: ~75ms
- 14 import checks: ~1.4s–14s
- Total: ~1.5s–15s

Acceptable for interactive use. The import check is the bottleneck — can be parallelized across files.

---

## 10. Integration Points

### 10.1 With Fix Engine (Document 05)
- Fix engine calls verifier after each fix
- Verification failure triggers rollback
- Verification success confirms the fix

### 10.2 With Detection Engine (Document 03)
- Re-detection uses the same detection engine
- AST cache is invalidated for modified files
- Same feature entries, same matching logic

### 10.3 With Lifecycle (Document 06)
- Verification results feed into `determine_state()`
- `all_passed: true` → step can be PASSED
- `all_passed: false` → step is FAILED

### 10.4 With Feature Database (Document 02)
- Entry validation uses the verification loop
- Each entry's test case goes through detect → fix → verify
- CI prevents broken entries from being merged
