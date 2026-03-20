# 05 — Detection-Fix Coupling Spec

> **Document**: 5 of 37
> **Milestone**: M4 — Detection-fix coupling
> **Status**: Draft

---

## 1. The Problem This Solves

In v1, detection and fix were completely separate systems:

```
Detection:  _RUNTIME_FEATURES has regex r"\bdatetime\.UTC\b"
            → Detects: "datetime.UTC" (attribute access form)

Fix:        _COMPAT_PATTERNS has search: "datetime.UTC"
            → Searches for string "datetime.UTC" in source code
            → Does NOT find "from datetime import UTC" (import form)

Result:     Detection finds the pattern (sometimes).
            Fix searches for a DIFFERENT string.
            Fix fails silently.
            User sees "No occurrences found."
```

The detection and fix were written at different times, by different logic, with different search strings. They were never tested together. They were never validated to produce the same result.

This document specifies the architecture where detection and fix are ONE unit — inseparable, co-validated, and tested as a pair.

---

## 2. The Coupling Rule

### 2.1 Absolute constraint

**A detection without a fix is incomplete.**
**A fix without a detection is blind.**
**They are fields on the SAME database entry.**

```yaml
# This is ONE entry. Detection and fix live together.
id: python.stdlib.datetime_utc
detection:
  primary:
    ast_type: ImportFrom
    match:
      module: datetime
      names_contains: UTC
fix:
  strategy: replace_import_and_usages
  transforms:
    - type: replace_import_name
      find:
        import_module: datetime
        import_name: UTC
      replace:
        import_name: timezone
    - type: replace_usage
      find:
        name: UTC
        origin: import
      replace:
        expression: "timezone.utc"
```

The fix's `find` block references the EXACT same thing the detection finds. Not a separate search string. Not a regex. The SAME AST-level match.

### 2.2 What "coupled" means concretely

1. **Same entry**: Detection and fix are fields on the same `FeatureEntry` object
2. **Same AST nodes**: The fix operates on the EXACT AST nodes the detection identified — same file, same line, same node
3. **Fix receives findings**: The fix engine gets a `Finding` object that contains the AST node reference, not a string to search for
4. **Co-validated**: The entry's test case runs detection on `before`, applies fix, and verifies `after` — proving they work together
5. **Never separated**: There is no API that allows running a detection without having a fix available, or running a fix without a prior detection

---

## 3. Fix Strategies

Each fix strategy is a type of code transformation. The strategy determines HOW the fix engine modifies the code.

### 3.1 `replace_import`

Replace an import statement with a different one.

```yaml
strategy: replace_import
transforms:
  - type: replace_import_statement
    find:
      import_module: tomllib
    replace:
      import_statement: "import tomli as tomllib"
```

**Input AST**: `Import(names=[alias(name='tomllib')])`
**Output AST**: `Import(names=[alias(name='tomli', asname='tomllib')])`

**What the fix engine does:**
1. Find the `Import` or `ImportFrom` AST node identified by the detection
2. Replace it with the new import statement
3. Preserve surrounding whitespace and comments

### 3.2 `replace_import_and_usages`

Replace an import AND all usages of the imported name in the file.

```yaml
strategy: replace_import_and_usages
transforms:
  - type: replace_import_name
    find:
      import_module: datetime
      import_name: UTC
    replace:
      import_name: timezone
  - type: replace_usage
    find:
      name: UTC
      origin: import    # Only replace UTC that came from this import
    replace:
      expression: "timezone.utc"
```

**What the fix engine does:**
1. Find the import node
2. In the import's names list, replace `UTC` with `timezone`
3. Walk the rest of the file's AST
4. Find every `Name` node where `id == 'UTC'` that resolves to this import
5. Replace each with `Attribute(value=Name('timezone'), attr='utc')`
6. Handle edge case: if `datetime` and `UTC` are imported together (`from datetime import datetime, UTC`), only replace `UTC`, keep `datetime`

**Scope tracking:**
The `origin: import` constraint is critical. It means: only replace `UTC` that came from `from datetime import UTC`. If there's a local variable also called `UTC`, don't touch it.

The fix engine uses the AST's scope information:
- The import creates a name binding at module level
- Any `Name(id='UTC')` node that resolves to that binding → replace
- Any `Name(id='UTC')` that's a local variable, function parameter, etc. → leave alone

### 3.3 `rewrite_expression`

Rewrite an expression to a compatible form.

```yaml
strategy: rewrite_expression
transforms:
  - type: rewrite_method_call
    find:
      method: removeprefix
      receiver_type: any    # Any object's .removeprefix() call
    replace:
      template: "{receiver}[len({arg}):]  if {receiver}.startswith({arg}) else {receiver}"
      extract:
        receiver: call_receiver    # The object the method is called on
        arg: call_args[0]          # First argument to the method
```

**Input**: `s.removeprefix("prefix")`
**Output**: `s[len("prefix"):]  if s.startswith("prefix") else s`

**What the fix engine does:**
1. Find the `Call` AST node where `func.attr == 'removeprefix'`
2. Extract the receiver expression (`s`) and first argument (`"prefix"`)
3. Build the replacement expression from the template
4. Replace the entire `Call` node with the new expression
5. Handle edge case: if receiver is a complex expression (`get_name().removeprefix("x")`), may need a temporary variable to avoid double evaluation

### 3.4 `add_backport_import`

Replace a stdlib import with a backport package import.

```yaml
strategy: add_backport_import
transforms:
  - type: replace_import
    find:
      import_module: tomllib
    replace:
      import_statement: "import tomli as tomllib"
backport:
  package: tomli
  min_version: "1.0.0"
```

**What the fix engine does:**
1. Find the `Import` or `ImportFrom` node for `tomllib`
2. Replace with `import tomli as tomllib`
3. Report that `tomli` needs to be added to the project's dependencies
4. The lifecycle system can then trigger a dependency installation step

### 3.5 `wrap_in_try_except`

Wrap an import in a try/except for conditional compatibility.

```yaml
strategy: wrap_in_try_except
transforms:
  - type: conditional_import
    find:
      import_module: tomllib
    replace:
      try_import: "import tomllib"
      except_import: "import tomli as tomllib"
      except_type: ModuleNotFoundError
```

**Input:**
```python
import tomllib
```

**Output:**
```python
try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib
```

**What the fix engine does:**
1. Find the import node
2. Wrap it in a `Try` node with the except clause
3. Preserve the original import as the try branch
4. Add the backport import as the except branch

### 3.6 `add_version_gate`

Wrap code in a `sys.version_info` check.

```yaml
strategy: add_version_gate
transforms:
  - type: version_conditional
    find:
      ast_type: Match    # match/case statement
    replace:
      min_version: [3, 10]
      fallback: manual   # No mechanical fallback for match/case
```

**Output:**
```python
import sys
if sys.version_info >= (3, 10):
    match command:
        case "quit":
            quit()
else:
    # match/case requires Python 3.10+
    if command == "quit":
        quit()
```

Note: This strategy is rare and complex. For most features like match/case, the fix strategy should be `manual` with instructions, not `add_version_gate`.

### 3.7 `add_future_import`

Add `from __future__ import annotations` to make annotation-only features compatible.

```yaml
strategy: add_future_import
transforms:
  - type: add_import
    import_statement: "from __future__ import annotations"
    position: top    # After shebang, encoding, and docstring
```

**What the fix engine does:**
1. Check if the file already has `from __future__ import annotations`
2. If yes → nothing to do
3. If no → insert at the top (after shebang, encoding declaration, module docstring)

### 3.8 `manual`

Cannot be auto-fixed. Provide instructions only.

```yaml
strategy: manual
transforms: []
manual_instructions: |
  match/case statements must be manually rewritten as if/elif chains.
  Each `case Pattern:` becomes an `elif` with the equivalent condition.
  Structural pattern matching has no mechanical backport.
```

**What the system does:**
- Detection still works — finds all match/case usages
- Fix is NOT available — `fix_available: false` in findings
- User sees the manual instructions
- Step state → NEEDS_ATTENTION (not FAILED — the detection worked, fix is just manual)

### 3.9 `no_fix_needed`

For upgrade direction — the feature is now available, no fix needed.

```yaml
strategy: no_fix_needed
direction: upgrade
```

When upgrading to a version that supports this feature, no code changes are needed. The entry exists for informational purposes — "you can now use match/case."

---

## 4. Fix Engine Architecture

```python
class FixEngine:
    """Apply fixes to source code based on detection findings."""

    def __init__(
        self,
        registry: FeatureRegistry,
        backend_factory: Callable[[str], LanguageBackend],
    ):
        self._registry = registry
        self._backend_factory = backend_factory

    def fix_finding(
        self,
        finding: Finding,
        project_root: Path,
    ) -> FixResult:
        """Fix a single finding.

        1. Look up the feature entry
        2. Get the fix strategy and transforms
        3. Read the file
        4. Parse to AST
        5. Apply transforms
        6. Emit modified source
        7. Write file
        8. Verify the fix
        9. If verification fails → rollback

        Returns FixResult with success/failure details.
        """

    def fix_file(
        self,
        file_path: Path,
        findings: list[Finding],
        project_root: Path,
    ) -> list[FixResult]:
        """Fix all findings in a single file.

        Applies all fixes to the same AST in order,
        then writes the file once. More efficient than
        fixing one finding at a time.
        """

    def fix_module(
        self,
        module_dir: Path,
        findings: list[Finding],
        project_root: Path,
    ) -> ModuleFixResult:
        """Fix all findings in a module.

        Groups findings by file, fixes each file,
        verifies each fix, reports results.
        Only fixes direct findings (not transitive).
        """
```

### 4.1 FixResult

```python
@dataclass
class FixResult:
    finding: Finding
    success: bool
    file_path: str
    strategy: str
    verification: VerificationResult | None
    error: str | None
    rollback_applied: bool

    # What changed
    original_source: str | None    # For rollback
    modified_source: str | None    # What was written
    diff: str | None               # Unified diff of changes

@dataclass
class VerificationResult:
    re_detect_passed: bool         # Re-detection found 0 matches
    import_check_passed: bool      # File still imports/compiles
    syntax_check_passed: bool      # File parses without errors
    all_passed: bool               # All checks passed
    errors: list[str]              # Any error messages
```

### 4.2 Fix ordering within a file

When a file has multiple findings, fixes must be applied in the right order:

1. **Bottom-up by line number**: Apply fixes starting from the last line in the file, working upward. This prevents line number shifts from invalidating subsequent fixes.

2. **Import fixes first**: Import-level fixes (replace_import, add_backport_import) before usage-level fixes (replace_usage, rewrite_expression). The usage fixes may depend on the new import being in place.

3. **Non-overlapping**: Two fixes should never modify the same AST node. If they do, it's a conflict — report it, don't apply either.

### 4.3 Rollback mechanism

```python
class Rollback:
    """Manage rollback of failed fixes."""

    def __init__(self):
        self._snapshots: dict[str, str] = {}  # file_path → original content

    def snapshot(self, file_path: Path) -> None:
        """Save a copy of the file before modification."""

    def rollback(self, file_path: Path) -> bool:
        """Restore the file to its pre-fix state."""

    def rollback_all(self) -> list[str]:
        """Rollback all snapshotted files. Returns list of rolled-back files."""

    def discard(self, file_path: Path) -> None:
        """Discard the snapshot (fix was verified, no rollback needed)."""
```

**Rollback flow:**
```
1. Before fix: rollback.snapshot(file_path) → saves original content
2. Apply fix transforms → write modified file
3. Verify fix:
   a. If verification passes → rollback.discard(file_path)
   b. If verification fails → rollback.rollback(file_path) → restores original
4. Report result
```

---

## 5. Validation: Proving Detection and Fix Work Together

### 5.1 Entry self-test

Every database entry has a `test` field with `before` and `after` source code. The validation pipeline:

```
1. Parse test.before with language parser → must succeed
2. Run detection on test.before → must find >= 1 match
3. Apply fix transforms to test.before → produces modified code
4. Compare modified code with test.after → must match
5. Run detection on test.after → must find 0 matches
6. Parse test.after with language parser → must succeed
```

If ANY step fails, the entry is INVALID and cannot be loaded into the registry.

### 5.2 Edge case tests

Each entry can have additional test cases in `test.additional`:

```yaml
test:
  additional:
    - name: "UTC imported with other names"
      before: |
        from datetime import datetime, UTC, timezone
        now = datetime.now(UTC)
      after: |
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
    - name: "UTC aliased"
      before: |
        from datetime import UTC as utc_tz
        now = datetime.now(utc_tz)
      after: |
        from datetime import timezone
        now = datetime.now(timezone.utc)
```

Each additional test case goes through the same 6-step validation.

### 5.3 CI validation

The full entry validation runs in CI on every PR that modifies database entries:

```
controlplane compat validate-db

Validating 1,010 entries across 10 languages...

  Python: 200 entries
    ✅ python.stdlib.datetime_utc — 3 test cases passed
    ✅ python.stdlib.tomllib — 2 test cases passed
    ✅ python.syntax.match_case — 1 test case passed (manual fix)
    ❌ python.stdlib.strenum — test.after still matches detection!
       → Fix did not fully remove the feature. Check transforms.
    ...

  JavaScript: 250 entries
    ✅ javascript.es2020.optional_chaining — 4 test cases passed
    ...

Results: 1,009 passed, 1 failed
```

---

## 6. Fix Scope Rules

### 6.1 Module-scoped fixes

The fix engine ONLY modifies files within the module being fixed. If a finding is transitive (in a dependency module), the fix engine does NOT touch it. Instead:

```
Finding: src/core/models/action.py uses datetime.UTC
Module being fixed: web (src/ui/web)
Finding is transitive: YES (core is a dependency)

Fix engine response:
  "Cannot fix — this file belongs to module 'core', not 'web'.
   Run the version plan for 'core' first."
```

### 6.2 Why module-scoped

A module is a module. It has its own version plan, its own target version, its own checklist. Fixing files outside the module:
- Violates the module boundary
- Could break the other module's own version plan
- Creates confusion about which plan "owns" the fix
- Makes rollback across plans impossible to coordinate

### 6.3 Cross-module recommendations

While the fix is scoped to the module, the ANALYSIS is not. The analysis shows:

```
Module: web
Direct findings: 1 (fixable)
Transitive findings: 14 (in module 'core')

Recommendation:
  1. Run version plan for 'core' first — fixes 14 transitive findings
  2. Then run version plan for 'web' — fixes 1 direct finding
  3. After both: web's tests should pass
```

---

## 7. Integration Points

### 7.1 With Feature Database (Document 02)
- Fix strategy and transforms are fields on each entry
- Entry validation proves detection and fix work together
- Fix engine loads entries from registry to get fix instructions

### 7.2 With Detection Engine (Document 03)
- Detection findings are the INPUT to the fix engine
- Each finding carries the `feature_id` linking to the database entry
- After fix, detection engine re-scans for verification

### 7.3 With Import Resolver (Document 04)
- Import graph tells the fix engine which findings are transitive (don't fix)
- Import graph tells the user which modules need fixing first

### 7.4 With Lifecycle (Document 06)
- Fix results determine step state transitions
- All fixes verified → PASSED
- Some fixes failed → FAILED with details
- Manual-only findings → NEEDS_ATTENTION with instructions
- Transitive-only findings → BLOCKED with module dependency info

### 7.5 With Verification (Document 07)
- Fix engine calls verifier after every fix
- Verifier re-runs detection, import checks, syntax checks
- Failed verification → rollback
