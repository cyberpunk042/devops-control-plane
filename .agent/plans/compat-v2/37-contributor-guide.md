# 37 — Contributor Guide

> **Document**: 37 of 37
> **Milestone**: Validation & migration
> **Status**: Draft

---

## 1. Purpose

How to contribute to the compat v2 system — adding features, fixing bugs, adding languages, adding entries to the feature database.

---

## 2. Adding a Feature Database Entry

This is the most common contribution. No engine code changes needed.

### Step 1: Identify the feature

- What language?
- What version was it introduced in?
- What category? (syntax, stdlib, typing, builtins, etc.)
- What error type does it cause? (import_error, syntax_error, runtime_error, etc.)

### Step 2: Write the detection rule

Find the AST node type that represents this feature. Use the language's AST explorer:
- Python: `python -c "import ast; print(ast.dump(ast.parse('your code'), indent=2))"`
- JS/TS: [AST Explorer](https://astexplorer.net/)
- Go: `go/ast` package

Write the detection rule matching that node type and attributes.

### Step 3: Write the fix

Determine the fix strategy:
- Can it be mechanically replaced? → `replace_import`, `rewrite_expression`, etc.
- Does it need a backport package? → `add_backport_import`
- Is it too complex for auto-fix? → `manual` with clear instructions

Write the transforms.

### Step 4: Write test cases

Write `test.before` and `test.after` code snippets:
- `before`: Code using the feature
- `after`: Code with the fix applied

Add `test.additional` for edge cases.

### Step 5: Add edge cases

Think about:
- Can this feature appear inside TYPE_CHECKING blocks?
- Can it appear inside try/except?
- Can it appear with aliases?
- Can it appear alongside other imports?
- Can it appear in annotations vs runtime?

Document each edge case with a test.

### Step 6: Validate

```
$ controlplane compat validate-db --entry your.entry.id
```

All test cases must pass:
1. Parse before → success
2. Detect in before → >= 1 match
3. Apply fix to before → produces output
4. Compare output with after → match
5. Detect in after → 0 matches
6. Parse after → success

### Step 7: Submit PR

The CI will run full database validation. Entry must pass before merge.

---

## 3. Adding a New Language

### Step 1: Create the backend

Create `backends/{language}_backend.py` implementing `LanguageBackend`:

```python
class KotlinBackend(LanguageBackend):
    language_id = "kotlin"
    file_extensions = [".kt", ".kts"]
    parser_name = "tree-sitter-kotlin"

    def parse_file(self, path): ...
    def walk_ast(self, ast): ...
    def node_type(self, node): ...
    def node_attributes(self, node): ...
    def node_location(self, node): ...
    def resolve_imports(self, file_path, project_root): ...
    def apply_transform(self, source, ast, node, transform): ...
    def check_syntax(self, file_path): ...
    def check_importable(self, file_path): ...
    def format_source(self, source): ...
    def query_package_registry(self, package, target_version): ...
    def parse_manifest(self, module_dir): ...
    def version_floor_from_manifest(self, module_dir): ...
```

If the language uses tree-sitter, extend `TreeSitterBackend` for common functionality.

### Step 2: Create language metadata

Create `database/entries/{language}/_meta.yml`:

```yaml
language: kotlin
display_name: Kotlin
file_extensions: [".kt", ".kts"]
parser: tree-sitter-kotlin
versions:
  - version: "1.5"
  - version: "1.6"
  ...
version_format: "major.minor"
package_registry:
  name: Maven Central
  api: "..."
```

### Step 3: Create feature entries

Create YAML files in `database/entries/{language}/`:
- Start with the most impactful features
- Each entry follows the schema (Document 02)
- Each entry has test cases
- Aim for 20+ entries minimum to be useful

### Step 4: Register the backend

Add to `backends/__init__.py`:
```python
from .kotlin_backend import KotlinBackend
BackendRegistry.register(KotlinBackend)
```

Add the stack mapping in the language detector.

### Step 5: Write tests

- Unit tests for the backend's parser, matcher, resolver
- Edge case tests for language-specific quirks
- E2E test with a fixture module

### Step 6: Document

Create the language module document (like Documents 19-27).

---

## 4. Fixing a Bug in Detection

### Step 1: Reproduce

Create a test case that demonstrates the bug:
```python
def test_false_positive_in_comment():
    """Bug: datetime.UTC in a comment should not be flagged."""
    code = '# Use datetime.UTC for timezone\nimport os\n'
    findings = detect(code, "python", target="3.8")
    assert len(findings) == 0  # Currently fails — the bug
```

### Step 2: Investigate

- Is it a detection rule issue? (wrong AST type, missing exclusion)
- Is it an edge case? (needs a new exclusion rule)
- Is it a backend issue? (parser producing unexpected nodes)

### Step 3: Fix

- If detection rule: update the YAML entry's `detection.exclude` list
- If edge case: add to the entry's `edge_cases` list
- If backend: fix the backend code

### Step 4: Verify

- The reproducing test case must now pass
- All existing tests must still pass
- Add the fix as a documented edge case if applicable

---

## 5. Fixing a Bug in a Fix Transform

### Step 1: Reproduce

Create a test case with the before/after that fails:
```python
def test_aliased_utc_fix():
    """Bug: fix doesn't handle 'from datetime import UTC as utc'."""
    before = "from datetime import UTC as utc\nnow = datetime.now(utc)\n"
    after = fix(before, "python.stdlib.datetime_utc")
    assert "utc" not in after  # Currently fails
    assert "timezone.utc" in after
```

### Step 2: Fix the transform

- Update the transform logic in the backend or the transform catalog
- May need a new transform type if the pattern is fundamentally different

### Step 3: Add edge case

Add the pattern to the entry's `edge_cases` and `test.additional`:
```yaml
edge_cases:
  - id: aliased_import
    description: "UTC imported with alias"
    test:
      before: |
        from datetime import UTC as utc
        now = datetime.now(utc)
      after: |
        from datetime import timezone
        now = datetime.now(timezone.utc)
```

### Step 4: Validate

```
$ controlplane compat validate-db --entry python.stdlib.datetime_utc
```

---

## 6. Code Style and Conventions

### 6.1 Python code
- Follow existing project conventions
- Type hints on all public functions
- Docstrings on all public classes and functions
- No `# noqa` without explanation

### 6.2 Feature database entries
- YAML format with consistent indentation (2 spaces)
- Every entry has `id`, `language`, `feature_name`, `introduced`, `detection`, `fix`, `test`
- Every entry has at least one test case
- Edge cases documented when applicable

### 6.3 Tests
- One test file per component
- Test names describe what's being tested: `test_datetime_utc_in_type_checking_excluded`
- Use fixtures for code snippets
- No mocking of AST parsing — use real parser

---

## 7. Release Process

### 7.1 Versioning

The feature database has its own version number:
```yaml
# database/_version.yml
version: "1.0.0"
entries_count: 1010
last_updated: "2026-03-19"
```

### 7.2 Changelog

When entries are added/modified:
```yaml
# database/CHANGELOG.yml
- version: "1.1.0"
  date: "2026-04-01"
  added:
    - python.stdlib.datetime_utc (3 edge cases)
    - python.stdlib.tomllib
  fixed:
    - python.builtins.str_removeprefix — handle complex receivers
```

---

## 8. Getting Help

- Architecture: Document 01 (system architecture)
- Feature database format: Document 02
- Detection engine: Document 03
- Fix engine: Document 05
- Edge cases: Document 28
- Language-specific: Documents 19-27
- Test plan: Document 35
