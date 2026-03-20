# 15 — Fix Transform Catalog

> **Document**: 15 of 37
> **Milestone**: M8 — Fix system
> **Status**: Draft

---

## 1. Purpose

This document catalogs every type of code transformation the fix engine can perform. Each transform type is a reusable operation that feature database entries reference in their `fix.transforms` list.

The fix engine doesn't know about `datetime.UTC` or `match/case`. It knows about transform TYPES — "replace an import name", "rewrite a method call", "add an import line". The feature database entry tells it WHICH transform to apply with WHAT parameters.

---

## 2. Transform Types

### 2.1 Import transforms

#### `replace_import_statement`
Replace an entire import statement with a different one.

```yaml
type: replace_import_statement
find:
  import_pattern: "import tomli as tomllib"
replace:
  import_statement: "import tomllib"
```

**AST operation**: Find `Import` or `ImportFrom` node matching the pattern. Replace the entire node.

**Edge cases**:
- Multi-line imports: `from x import (\n    a,\n    b\n)`
- Multiple imports on one line: `import a; import b` (Python — rare but valid)
- Import with comments: `import x  # noqa`

#### `replace_import_name`
Replace a specific name within an import statement, keeping other names.

```yaml
type: replace_import_name
find:
  import_module: datetime
  import_name: UTC
replace:
  import_name: timezone
```

Before: `from datetime import datetime, UTC`
After: `from datetime import datetime, timezone`

**AST operation**: Find `ImportFrom` node with matching module. In the `names` list, replace the matching alias.

**Edge cases**:
- Name is the only import: `from datetime import UTC` → `from datetime import timezone`
- Name is aliased: `from datetime import UTC as utc` → `from datetime import timezone` (alias removed since name changed)
- Name appears multiple times (invalid but possible): replace all

#### `add_import`
Add a new import statement to the file.

```yaml
type: add_import
import_statement: "from __future__ import annotations"
position: top       # "top" | "after_docstring" | "after_imports" | "before_usage"
```

**AST operation**: Parse the import statement. Insert at the specified position.

**Position rules**:
- `top`: After shebang, encoding declaration, and module docstring
- `after_docstring`: After the module docstring
- `after_imports`: After the last existing import block
- `before_usage`: Before the first usage of the imported name

#### `remove_import`
Remove an import statement entirely.

```yaml
type: remove_import
find:
  import_statement: "from __future__ import annotations"
```

**AST operation**: Find the matching import node. Remove it. Clean up blank lines left behind.

#### `remove_import_name`
Remove a specific name from an import, keeping other names.

```yaml
type: remove_import_name
find:
  import_module: datetime
  import_name: UTC
```

Before: `from datetime import datetime, UTC, timezone`
After: `from datetime import datetime, timezone`

If UTC is the only name: remove the entire import statement.

#### `unwrap_try_except_import`
Remove a try/except wrapper around an import, keeping just one branch.

```yaml
type: unwrap_try_except_import
find:
  try_import: "import tomllib"
  except_import: "import tomli as tomllib"
replace:
  keep: try      # Keep the try branch (stdlib), remove the except (backport)
```

Before:
```python
try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib
```
After:
```python
import tomllib
```

#### `wrap_in_try_except`
Wrap an import in a try/except block.

```yaml
type: wrap_in_try_except
find:
  import_module: tomllib
replace:
  try_import: "import tomllib"
  except_type: ModuleNotFoundError
  except_import: "import tomli as tomllib"
```

Before:
```python
import tomllib
```
After:
```python
try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib
```

---

### 2.2 Usage transforms

#### `replace_usage`
Replace all usages of an imported name with a different expression.

```yaml
type: replace_usage
find:
  name: UTC
  origin: import         # Only replace UTC that came from an import
replace:
  expression: "timezone.utc"
```

**AST operation**: Walk the file's AST. For each `Name` node where `id == "UTC"` that resolves to the import, replace with the new expression's AST.

**Scope tracking**: Only replace names that refer to the import, not local variables or parameters with the same name.

#### `replace_attribute`
Replace an attribute access pattern.

```yaml
type: replace_attribute
find:
  object: datetime
  attribute: UTC
replace:
  object: datetime
  attribute: "timezone.utc"
```

Before: `datetime.UTC`
After: `datetime.timezone.utc`

#### `rewrite_method_call`
Rewrite a method call to a different expression.

```yaml
type: rewrite_method_call
find:
  method: removeprefix
replace:
  template: "{receiver}[len({arg}):]  if {receiver}.startswith({arg}) else {receiver}"
  extract:
    receiver: call_receiver
    arg: call_args[0]
```

Before: `s.removeprefix("hello")`
After: `s[len("hello"):]  if s.startswith("hello") else s`

**Template variables**:
- `{receiver}`: The object the method is called on
- `{arg}`: First argument (or `{arg0}`, `{arg1}` for multiple)
- `{args}`: All arguments as comma-separated

**Complex receiver handling**: If receiver is a complex expression that shouldn't be evaluated twice:
```python
# Before: get_name().removeprefix("x")
# Naive: get_name()[len("x"):]  if get_name().startswith("x") else get_name()
#   → WRONG: calls get_name() three times
# Correct: introduce temp variable
_tmp = get_name()
_tmp[len("x"):]  if _tmp.startswith("x") else _tmp
```

The transform engine detects complex receivers (function calls, subscripts) and introduces a temporary variable when needed.

#### `rewrite_binary_op`
Rewrite a binary operation.

```yaml
type: rewrite_binary_op
find:
  operator: "|"
  context: dict_merge       # dict | dict, not type union
replace:
  template: "{**{left}, **{right}}"
  extract:
    left: left_operand
    right: right_operand
```

Before: `config = defaults | overrides`
After: `config = {**defaults, **overrides}`

---

### 2.3 Statement transforms

#### `rewrite_match_case`
Strategy: `manual` — no auto-transform available.

Match/case is too complex for mechanical rewriting. The fix entry has `strategy: manual` with instructions.

#### `rewrite_walrus`
Rewrite walrus operator to separate assignment and condition.

```yaml
type: rewrite_walrus
find:
  ast_type: NamedExpr
replace:
  style: split     # Split into separate assignment + condition
```

Before: `if (n := len(data)) > 10:`
After:
```python
n = len(data)
if n > 10:
```

#### `add_version_gate`
Wrap code in a `sys.version_info` check.

```yaml
type: add_version_gate
find:
  ast_type: any     # Applied to whatever AST node the detection found
replace:
  min_version: [3, 11]
  gate_type: if_else   # "if_else" | "if_only"
```

Before:
```python
from datetime import UTC
```
After:
```python
import sys
if sys.version_info >= (3, 11):
    from datetime import UTC
else:
    from datetime import timezone
    UTC = timezone.utc
```

---

### 2.4 Annotation transforms

#### `rewrite_annotation`
Rewrite a type annotation to a compatible form.

```yaml
type: rewrite_annotation
find:
  annotation_type: BinOp     # X | Y union
  operator: "|"
replace:
  template: "Union[{left}, {right}]"
  add_import: "from typing import Union"
```

Before: `def foo(x: int | str) -> None:`
After: `def foo(x: Union[int, str]) -> None:`

Only applied when `__future__` annotations is NOT present and the target is < 3.10.

#### `rewrite_builtin_generic`
Rewrite builtin generic type hints.

```yaml
type: rewrite_builtin_generic
find:
  annotation_type: Subscript
  annotation_value_name: list    # list[T] → List[T]
replace:
  typing_name: List
  add_import: "from typing import List"
```

Before: `def foo(items: list[int]) -> dict[str, Any]:`
After: `def foo(items: List[int]) -> Dict[str, Any]:`

Only applied when `__future__` annotations is NOT present and the target is < 3.9.

---

### 2.5 File-level transforms

#### `add_shebang`
Add or modify the shebang line.

#### `add_encoding`
Add encoding declaration.

#### `modify_docstring`
Modify module docstring (e.g., add version note).

These are rare and mostly for config/tooling changes, not compat fixes.

---

## 3. Transform Pipeline

### 3.1 Ordering rules

When multiple transforms apply to the same file:

1. **Import transforms first** — other transforms may depend on new imports
2. **Within imports**: adds before removes (add new import, then remove old)
3. **Usage transforms**: bottom-up by line number (prevent line shifts)
4. **Statement transforms**: bottom-up by line number
5. **Annotation transforms**: after usage transforms

### 3.2 Conflict detection

Two transforms conflict if they modify the same AST node:

```python
def detect_conflicts(transforms: list[Transform]) -> list[Conflict]:
    """Find transforms that target the same AST node.

    Conflicts are reported, not auto-resolved.
    The user must choose which transform to apply.
    """
```

### 3.3 AST vs text transforms

Most transforms operate on the AST level:
1. Parse file → AST
2. Apply transforms to AST nodes
3. Emit modified source from AST

Some transforms are simpler as text operations (e.g., `remove_import` for a simple one-line import). The engine supports both:
- AST transforms: precise, safe, handle formatting
- Text transforms: simple, fast, for cases where AST is overkill

The `type` field on each transform determines which engine handles it.

---

## 4. Source Code Emission

### 4.1 The problem

Modifying an AST and converting back to source code can lose formatting:
- Comments are not in the AST
- Blank lines may change
- Indentation style may change
- String quote style may change

### 4.2 Solutions per language

**Python**: Use `ast.unparse()` (3.9+) for modified nodes, but preserve original source for unchanged nodes. Alternative: use `libcst` (Concrete Syntax Tree) which preserves all formatting.

**JavaScript/TypeScript**: tree-sitter preserves the original text. Modify only the changed ranges. Use `recast` for JS AST transforms that preserve formatting.

**Go**: `go/format` (gofmt) normalizes formatting. Run after transform — formatting is standard.

**Rust**: `rustfmt` normalizes formatting. Run after transform.

**Other languages**: Each has its own formatter. Run the standard formatter after AST modification to normalize.

### 4.3 Minimal diff principle

The transform should produce the MINIMUM possible diff. Changing one import should not reformat the entire file. Strategies:
- Only emit AST for the modified nodes
- Splice the new text into the original source at the right byte offsets
- Preserve original indentation, quotes, trailing commas

---

## 5. Transform Testing

### 5.1 Each transform type has unit tests

```python
def test_replace_import_name():
    before = "from datetime import datetime, UTC\n"
    transform = ReplaceImportName(
        find={"import_module": "datetime", "import_name": "UTC"},
        replace={"import_name": "timezone"},
    )
    after = apply_transform(before, "python", transform)
    assert after == "from datetime import datetime, timezone\n"

def test_replace_import_name_sole_import():
    before = "from datetime import UTC\n"
    transform = ReplaceImportName(
        find={"import_module": "datetime", "import_name": "UTC"},
        replace={"import_name": "timezone"},
    )
    after = apply_transform(before, "python", transform)
    assert after == "from datetime import timezone\n"
```

### 5.2 Feature database entry tests exercise transforms

Every entry's `test.before` → `test.after` implicitly tests the transforms it uses. The validation pipeline (Document 07) catches broken transforms.

---

## 6. Integration Points

### 6.1 With Feature Database (Document 02)
- Each entry's `fix.transforms` list references transform types from this catalog
- New transform types require adding to this catalog AND implementing in the engine

### 6.2 With Fix Engine (Document 05)
- Fix engine instantiates transforms from the catalog
- Applies them via the transform pipeline

### 6.3 With Verification (Document 07)
- After transforms are applied, verification confirms they worked

### 6.4 With Language Backends
- Each backend implements the AST operations for its language
- Transform types are language-agnostic in definition, language-specific in implementation
