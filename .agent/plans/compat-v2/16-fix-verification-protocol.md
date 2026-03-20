# 16 — Fix Verification Protocol

> **Document**: 16 of 37
> **Milestone**: M8 — Fix system
> **Status**: Draft

---

## 1. Purpose

This document specifies the exact protocol for verifying that a fix actually worked. It extends Document 07 (Verification Loop) with the detailed per-language verification commands, timing requirements, and failure classification.

---

## 2. Verification Protocol Steps

For every fix applied, run these checks in order. Stop on first failure.

```
Step 1: SYNTAX CHECK         (~1ms)    — Can the file be parsed?
Step 2: RE-DETECTION          (~5ms)    — Is the feature still present?
Step 3: IMPORT CHECK          (~100ms+) — Can the file be imported/compiled?
Step 4: RELATED IMPORTS CHECK (~200ms+) — Can files that import this file still import?
Step 5: CUSTOM CHECK          (varies)  — Entry-specific validation
```

### 2.1 Step 1: Syntax check

| Language | Command | Timeout |
|----------|---------|---------|
| Python | `ast.parse(source)` (in-process) | 1s |
| JavaScript | tree-sitter parse (in-process) | 1s |
| TypeScript | `tsc --noEmit --pretty false {file}` | 10s |
| Go | `go vet {file}` | 10s |
| Rust | `cargo check --message-format=short` | 30s |
| Ruby | `ruby -c {file}` | 5s |
| Java | `javac -d /dev/null {file}` | 15s |
| C# | `dotnet build --no-restore --nologo -v q` | 15s |
| PHP | `php -l {file}` | 5s |
| Elixir | `elixirc --no-halt {file}` | 10s |

### 2.2 Step 2: Re-detection

Run the SAME detection rule that originally found the feature. Must return 0 matches.

No external commands needed — this is the detection engine re-scanning the modified AST.

### 2.3 Step 3: Import check

| Language | Command | What it validates |
|----------|---------|-------------------|
| Python | `{venv_python} -c "import {module_path}"` | Module loads, all imports resolve |
| JavaScript | `node -e "require('{file}')"` | File evaluates without errors |
| TypeScript | (covered by step 1 tsc) | — |
| Go | `go build ./...` | Package compiles |
| Rust | (covered by step 1 cargo check) | — |
| Ruby | `ruby -e "require_relative '{file}'"` | File loads |
| Java | (covered by step 1 javac) | — |
| C# | (covered by step 1 dotnet build) | — |
| PHP | `php -r "require '{file}';"` | File includes without errors |
| Elixir | `mix compile --force {file}` | Module compiles |

Note: For compiled languages (Go, Rust, Java, C#), the syntax/compile check in step 1 already validates importability. Step 3 is most important for interpreted languages (Python, JS, Ruby, PHP).

### 2.4 Step 4: Related imports check

After fixing file A, check if files that IMPORT A can still import:

```python
def check_related_imports(
    fixed_file: str,
    import_graph: ImportGraph,
    backend: LanguageBackend,
    max_files: int = 10,
) -> list[VerificationCheck]:
    """Check that files importing the fixed file still work.

    Only checks direct importers (depth 1), not the full chain.
    Limits to max_files to avoid slow verification on highly-imported files.
    """
    importers = import_graph.direct_importers(fixed_file)[:max_files]
    results = []
    for importer in importers:
        check = backend.check_importable(Path(importer.source))
        results.append(VerificationCheck(
            check_type="related_import",
            passed=check,
            message=f"Importer {importer.source}: {'OK' if check else 'FAILED'}",
        ))
    return results
```

This catches cases where the fix breaks other files:
- Removed an import that other files rely on via re-export
- Changed a name that other files import
- Broke `__init__.py` that other files traverse

### 2.5 Step 5: Custom check

Optional per-entry check defined in the feature database:

```yaml
verification:
  custom_check:
    command: "python -c 'from datetime import timezone; print(timezone.utc)'"
    expected_exit_code: 0
    timeout: 5
```

---

## 3. Failure Classification

When verification fails, classify the failure to help the user understand what went wrong:

| Failure type | Meaning | User action |
|-------------|---------|-------------|
| `syntax_error` | Fix produced invalid syntax | Bug in transform — report |
| `feature_still_present` | Fix didn't remove the feature | Transform missed a pattern — edge case |
| `import_error` | Fixed file can't be imported | Fix broke a dependency or removed needed import |
| `related_import_error` | Other file that imports this one broke | Fix changed something others depend on |
| `custom_check_failed` | Entry-specific check failed | Review the custom check requirements |
| `timeout` | Check took too long | Large file or slow build system |

```python
@dataclass
class VerificationFailure:
    check_type: str                # Which check failed
    failure_type: str              # Classification above
    message: str                   # Human-readable error
    file: str                      # File that was checked
    line: int | None               # Line of error (if applicable)
    suggestion: str | None         # What the user can do
```

---

## 4. Verification Modes

### 4.1 Full verification (default)

All 5 steps run in order. Used for individual fixes and small batches.

### 4.2 Quick verification

Steps 1 and 2 only (syntax + re-detection). Skip import checks. Used for:
- Large batch fixes (100+ files) where full verification would be too slow
- Preliminary check before running full verification at the end

### 4.3 Final verification

Full verification PLUS re-run the module's test suite. Used at plan completion:

```python
def final_verification(
    module_dir: Path,
    language: str,
    target_version: str,
    test_command: str | None,
) -> FinalVerificationResult:
    """Complete verification including test execution.

    1. Re-scan entire module — 0 findings expected
    2. Import check on all module files
    3. Run test suite if available
    """
```

---

## 5. Performance Budget

Total verification time should not exceed 30 seconds for a typical module:

| Module size | Files fixed | Full verification time |
|------------|-------------|----------------------|
| Small (10 files) | 5 | ~2s |
| Medium (50 files) | 20 | ~10s |
| Large (200 files) | 50 | ~25s |
| Very large (500+ files) | 100+ | Use quick mode, full at end |

### 5.1 Parallelization

Steps 3 and 4 (import checks) can run in parallel across files. Step 2 (re-detection) is already fast. Step 1 (syntax) is in-process and instant.

---

## 6. Integration Points

### 6.1 With Verification Loop (Document 07)
- This document specifies the COMMANDS. Document 07 specifies the FLOW.
- Same verification engine, this adds language-specific details.

### 6.2 With Fix Engine (Document 05)
- Called after every fix application
- Results determine fix success/failure/rollback

### 6.3 With Rollback (Document 10)
- Failed verification triggers file rollback
- Verification report included in rollback report

### 6.4 With Lifecycle (Document 06)
- Verification results feed into step state determination
- Full verification at plan completion
