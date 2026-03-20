# 19 — Python Language Module

> **Document**: 19 of 37
> **Milestone**: M9 — Language modules & edge cases
> **Status**: Draft

---

## 1. Overview

Python is the primary language of this project and the most complex language module. It has the deepest feature database, the most edge cases, and the most mature AST tooling.

**Versions covered**: 3.7 through 3.13+
**Feature entries target**: 200+
**Parser**: `ast` stdlib module
**Import resolver**: Follow `import`/`from X import Y`/relative imports
**Package registry**: PyPI
**Formatter**: `black` or `autopep8` (optional post-transform)

---

## 2. AST Backend

### 2.1 Parser

```python
class PythonBackend(LanguageBackend):

    def parse_file(self, path: Path) -> ast.Module:
        source = path.read_text(encoding="utf-8", errors="ignore")
        try:
            return ast.parse(source, filename=str(path))
        except SyntaxError as e:
            raise ParseError(
                file=str(path),
                error_type="syntax",
                message=str(e),
                line=e.lineno,
            )
```

**Parser version consideration**: The `ast` module in the RUNNING Python parses the source. If running on Python 3.12, `ast.parse` can parse 3.12 syntax. If the target is 3.8, the parser still uses 3.12's `ast` — it produces nodes like `ast.Match` that don't exist in 3.8's ast module. This is fine — we're detecting those nodes as features above the target.

### 2.2 Node matching

```python
def match_feature(self, tree: ast.Module, rule: DetectionRule) -> list[Finding]:
    findings = []
    for node in ast.walk(tree):
        node_type = type(node).__name__
        if node_type != rule.ast_type:
            continue
        if self._matches_attributes(node, rule.match):
            if not self._excluded(node, rule):
                findings.append(self._make_finding(node, rule))
    return findings

def _matches_attributes(self, node: ast.AST, match: dict) -> bool:
    for key, expected in match.items():
        if key == "names_contains":
            # Special: check if a name is in the import's names list
            names = [alias.name for alias in getattr(node, "names", [])]
            if expected not in names:
                return False
        elif key == "value_type":
            val = getattr(node, "value", None)
            if val is None or type(val).__name__ != expected:
                return False
        elif key == "value_id":
            val = getattr(node, "value", None)
            if not isinstance(val, ast.Name) or val.id != expected:
                return False
        else:
            if getattr(node, key, None) != expected:
                return False
    return True
```

### 2.3 Import resolution

```python
def resolve_imports(self, file_path: Path, project_root: Path) -> list[ImportEdge]:
    source = file_path.read_text(encoding="utf-8", errors="ignore")
    tree = ast.parse(source)
    edges = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                resolved = self._resolve_module(alias.name, file_path, project_root)
                if resolved:
                    edges.append(ImportEdge(
                        source=str(file_path),
                        target=resolved,
                        import_type="import",
                        names_imported=[alias.asname or alias.name],
                        line=node.lineno,
                        is_conditional=self._is_in_try(node, tree),
                        is_type_only=self._is_in_type_checking(node, tree),
                    ))

        elif isinstance(node, ast.ImportFrom):
            if node.module is None:
                continue  # relative import with no module (from . import x)
            module_name = node.module
            if node.level > 0:
                # Relative import — resolve relative to current package
                module_name = self._resolve_relative(
                    node.module, node.level, file_path, project_root
                )
            resolved = self._resolve_module(module_name, file_path, project_root)
            if resolved:
                names = [alias.name for alias in node.names]
                edges.append(ImportEdge(
                    source=str(file_path),
                    target=resolved,
                    import_type="from_import_star" if names == ["*"] else "from_import",
                    names_imported=names,
                    line=node.lineno,
                    is_conditional=self._is_in_try(node, tree),
                    is_type_only=self._is_in_type_checking(node, tree),
                ))

    return edges
```

### 2.4 Import check

```python
def check_importable(self, file_path: Path) -> bool:
    """Check if a Python file can be imported.

    Uses the target Python venv if available, otherwise system Python.
    """
    module_path = self._file_to_module_path(file_path)
    result = subprocess.run(
        [self._python_path, "-c", f"import {module_path}"],
        capture_output=True, text=True, timeout=10,
        cwd=str(self._project_root),
    )
    return result.returncode == 0
```

---

## 3. Feature Database — Python 3.8 (baseline)

Features AT 3.8 (walrus operator, positional-only parameters) — these are the FLOOR for detecting "code that requires at least 3.8":

### 3.8 Features

```yaml
# Walrus operator :=
- id: python.syntax.walrus_operator
  language: python
  feature_name: "walrus operator :="
  introduced: "3.8"
  category: syntax
  error_type: syntax_error
  description: "Assignment expression using := operator"
  detection:
    primary:
      ast_type: NamedExpr
      match: {}
  fix:
    strategy: rewrite_expression
    transforms:
      - type: rewrite_walrus
        find:
          ast_type: NamedExpr
        replace:
          style: split
  test:
    before: |
      if (n := len(data)) > 10:
          print(n)
    after: |
      n = len(data)
      if n > 10:
          print(n)

# Positional-only parameters /
- id: python.syntax.positional_only_params
  language: python
  feature_name: "positional-only parameters (/)"
  introduced: "3.8"
  category: syntax
  error_type: syntax_error
  description: "Function parameters before / are positional-only"
  detection:
    primary:
      ast_type: FunctionDef
      match:
        has_posonlyargs: true
  fix:
    strategy: manual
    manual_instructions: |
      Remove the / separator and update callers to not use keyword arguments
      for these parameters. Alternatively, add runtime checks.
  test:
    before: |
      def greet(name, /, greeting="Hello"):
          return f"{greeting}, {name}"
    after: |
      def greet(name, greeting="Hello"):
          return f"{greeting}, {name}"
```

---

## 4. Feature Database — Python 3.9

```yaml
# str.removeprefix
- id: python.builtins.str_removeprefix
  language: python
  feature_name: "str.removeprefix()"
  introduced: "3.9"
  category: builtins
  error_type: runtime_error
  error_subtype: missing_method
  detection:
    primary:
      ast_type: Call
      match:
        func_attr: removeprefix
    alternatives:
      - ast_type: Attribute
        match:
          attr: removeprefix
  fix:
    strategy: rewrite_expression
    transforms:
      - type: rewrite_method_call
        find:
          method: removeprefix
        replace:
          template: "{receiver}[len({arg}):]  if {receiver}.startswith({arg}) else {receiver}"
  test:
    before: |
      result = path.removeprefix("/home/")
    after: |
      result = path[len("/home/"):]  if path.startswith("/home/") else path
  edge_cases:
    - id: complex_receiver
      description: "Method called on complex expression"
      example: "get_path().removeprefix('/home/')"
      handling: "Introduce temporary variable to avoid double evaluation"
      test:
        before: |
          result = get_path().removeprefix("/home/")
        after: |
          _tmp = get_path()
          result = _tmp[len("/home/"):]  if _tmp.startswith("/home/") else _tmp

# str.removesuffix
- id: python.builtins.str_removesuffix
  language: python
  feature_name: "str.removesuffix()"
  introduced: "3.9"
  category: builtins
  error_type: runtime_error
  error_subtype: missing_method
  detection:
    primary:
      ast_type: Call
      match:
        func_attr: removesuffix
  fix:
    strategy: rewrite_expression
    transforms:
      - type: rewrite_method_call
        find:
          method: removesuffix
        replace:
          template: "{receiver}[:-len({arg})]  if {receiver}.endswith({arg}) else {receiver}"
  test:
    before: |
      result = filename.removesuffix(".txt")
    after: |
      result = filename[:-len(".txt")]  if filename.endswith(".txt") else filename

# dict merge operator |
- id: python.builtins.dict_merge_operator
  language: python
  feature_name: "dict merge operator (|)"
  introduced: "3.9"
  category: builtins
  error_type: runtime_error
  error_subtype: unsupported_operator
  detection:
    primary:
      ast_type: BinOp
      match:
        op_type: BitOr
        # Context: both operands should be dicts
        # This is hard to verify statically — might need type inference
  fix:
    strategy: rewrite_expression
    transforms:
      - type: rewrite_binary_op
        find:
          operator: "|"
        replace:
          template: "{**{left}, **{right}}"
  test:
    before: |
      merged = defaults | overrides
    after: |
      merged = {**defaults, **overrides}
  edge_cases:
    - id: dict_update_operator
      description: "In-place merge with |="
      example: "config |= extra"
      handling: "Rewrite as config.update(extra)"
      test:
        before: |
          config |= extra
        after: |
          config.update(extra)

# builtin generics (list[int], dict[str, Any])
- id: python.typing.builtin_generics
  language: python
  feature_name: "builtin generic types (list[int], dict[str, Any])"
  introduced: "3.9"
  category: typing
  error_type: type_error
  description: "Using builtin types as generics in annotations without typing imports"
  detection:
    primary:
      ast_type: Subscript
      match:
        value_type: Name
        value_id_in: [list, dict, set, tuple, frozenset, type]
      context: annotation
    exclude:
      - context: type_checking_block
        reason: "TYPE_CHECKING blocks are not evaluated"
      - context: string_annotation
        reason: "String annotations are not evaluated"
  fix:
    strategy: add_future_import
    transforms:
      - type: add_import
        import_statement: "from __future__ import annotations"
        condition: not_already_present
    fallback:
      strategy: rewrite_annotation
      transforms:
        - type: rewrite_builtin_generic
          find:
            annotation_value_name: list
          replace:
            typing_name: List
            add_import: "from typing import List"
  test:
    before: |
      def process(items: list[int]) -> dict[str, int]:
          pass
    after: |
      from __future__ import annotations

      def process(items: list[int]) -> dict[str, int]:
          pass
```

---

## 5. Feature Database — Python 3.10

```yaml
# match/case
- id: python.syntax.match_case
  language: python
  feature_name: "match/case statement"
  introduced: "3.10"
  category: syntax
  error_type: syntax_error
  severity: error
  detection:
    primary:
      ast_type: Match
      match: {}
  fix:
    strategy: manual
    manual_instructions: |
      match/case must be rewritten as if/elif chains.

      Simple value matching:
        match command:
            case "quit": quit()
            case "hello": greet()
            case _: unknown()
        →
        if command == "quit": quit()
        elif command == "hello": greet()
        else: unknown()

      Structural pattern matching (destructuring) requires
      more complex rewriting and careful review.
  test:
    before: |
      match command:
          case "quit":
              return 0
          case _:
              return 1
    after: |
      if command == "quit":
          return 0
      else:
          return 1

# Union type X | Y in annotations
- id: python.typing.union_pipe
  language: python
  feature_name: "union type X | Y"
  introduced: "3.10"
  category: typing
  error_type: type_error
  direction: both
  detection:
    primary:
      ast_type: BinOp
      match:
        op_type: BitOr
      context: annotation
    exclude:
      - context: runtime
        reason: "Runtime X | Y (e.g., isinstance) is a separate feature"
  fix:
    strategy: add_future_import
    transforms:
      - type: add_import
        import_statement: "from __future__ import annotations"
        condition: not_already_present
  fix_upgrade:
    strategy: rewrite_annotation
    transforms:
      - type: rewrite_annotation
        find:
          annotation_type: Subscript
          annotation_value: Optional
        replace:
          template: "{inner} | None"
  test:
    before: |
      def foo(x: int | str) -> None:
          pass
    after: |
      from __future__ import annotations

      def foo(x: int | str) -> None:
          pass

# Parenthesized context managers
- id: python.syntax.parenthesized_context_managers
  language: python
  feature_name: "parenthesized context managers"
  introduced: "3.10"
  category: syntax
  error_type: syntax_error
  detection:
    primary:
      ast_type: With
      match:
        has_parenthesized_items: true
  fix:
    strategy: rewrite_expression
    transforms:
      - type: split_with_statement
        find:
          ast_type: With
        replace:
          style: nested_with
  test:
    before: |
      with (open("a") as f1,
            open("b") as f2):
          pass
    after: |
      with open("a") as f1:
          with open("b") as f2:
              pass
```

---

## 6. Feature Database — Python 3.11

```yaml
# datetime.UTC
- id: python.stdlib.datetime_utc
  language: python
  feature_name: "datetime.UTC"
  introduced: "3.11"
  category: stdlib
  error_type: import_error
  error_subtype: missing_name
  description: "datetime.UTC shorthand for datetime.timezone.utc"
  detection:
    primary:
      ast_type: ImportFrom
      match:
        module: datetime
        names_contains: UTC
    alternatives:
      - ast_type: Attribute
        match:
          value_type: Name
          value_id: datetime
          attr: UTC
    exclude:
      - context: type_checking_block
        reason: "TYPE_CHECKING imports are not executed"
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
  verification:
    re_detect: true
    import_check: true
  backport: null
  test:
    before: |
      from datetime import UTC, datetime
      now = datetime.now(UTC)
      ts = datetime(2024, 1, 1, tzinfo=UTC)
    after: |
      from datetime import timezone, datetime
      now = datetime.now(timezone.utc)
      ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
  edge_cases:
    - id: utc_sole_import
      description: "UTC is the only name imported from datetime"
      test:
        before: |
          from datetime import UTC
        after: |
          from datetime import timezone
    - id: utc_aliased
      description: "UTC imported with an alias"
      test:
        before: |
          from datetime import UTC as utc_tz
          now = datetime.now(utc_tz)
        after: |
          from datetime import timezone
          now = datetime.now(timezone.utc)
    - id: utc_attribute_access
      description: "datetime.UTC attribute form"
      test:
        before: |
          import datetime
          now = datetime.datetime.now(datetime.UTC)
        after: |
          import datetime
          now = datetime.datetime.now(datetime.timezone.utc)

# tomllib
- id: python.stdlib.tomllib
  language: python
  feature_name: "tomllib"
  introduced: "3.11"
  category: stdlib
  error_type: import_error
  error_subtype: missing_module
  detection:
    primary:
      ast_type: Import
      match:
        names_contains: tomllib
    alternatives:
      - ast_type: ImportFrom
        match:
          module: tomllib
  fix:
    strategy: add_backport_import
    transforms:
      - type: replace_import
        find:
          import_module: tomllib
        replace:
          import_statement: "import tomli as tomllib"
    alternative:
      strategy: wrap_in_try_except
      transforms:
        - type: conditional_import
          find:
            import_module: tomllib
          replace:
            try_import: "import tomllib"
            except_import: "import tomli as tomllib"
            except_type: ModuleNotFoundError
  backport:
    package: tomli
    min_version: "1.0.0"
    install_command: "pip install tomli>=1.0.0"
  test:
    before: |
      import tomllib
      with open("config.toml", "rb") as f:
          data = tomllib.load(f)
    after: |
      import tomli as tomllib
      with open("config.toml", "rb") as f:
          data = tomllib.load(f)

# enum.StrEnum
- id: python.stdlib.strenum
  language: python
  feature_name: "enum.StrEnum"
  introduced: "3.11"
  category: stdlib
  error_type: import_error
  error_subtype: missing_name
  detection:
    primary:
      ast_type: ImportFrom
      match:
        module: enum
        names_contains: StrEnum
    alternatives:
      - ast_type: Attribute
        match:
          value_id: enum
          attr: StrEnum
  fix:
    strategy: add_backport_import
    transforms:
      - type: replace_import_statement
        find:
          import_pattern: "from enum import StrEnum"
        replace:
          import_statement: "from backports.strenum import StrEnum"
    alternative:
      strategy: manual
      manual_instructions: |
        Define a simple StrEnum base class:
          class StrEnum(str, Enum):
              pass
  backport:
    package: backports.strenum
    min_version: "1.0.0"
  test:
    before: |
      from enum import StrEnum
      class Color(StrEnum):
          RED = "red"
    after: |
      from backports.strenum import StrEnum
      class Color(StrEnum):
          RED = "red"

# except* (ExceptionGroup)
- id: python.syntax.except_star
  language: python
  feature_name: "except* (exception groups)"
  introduced: "3.11"
  category: syntax
  error_type: syntax_error
  detection:
    primary:
      ast_type: TryStar
      match: {}
  fix:
    strategy: manual
    manual_instructions: |
      except* (exception groups) has no mechanical backport.
      Rewrite to use standard try/except with manual exception filtering.
      Consider the 'exceptiongroup' backport package for Python 3.7-3.10.
  backport:
    package: exceptiongroup
    min_version: "1.0.0"
    notes: "Provides ExceptionGroup class but NOT except* syntax"
  test:
    before: |
      try:
          async with TaskGroup() as tg:
              tg.create_task(fetch())
      except* ValueError as eg:
          for e in eg.exceptions:
              handle(e)
    after: |
      # Manual rewrite required — except* syntax not available
      try:
          async with TaskGroup() as tg:
              tg.create_task(fetch())
      except Exception as e:
          if isinstance(e, ValueError):
              handle(e)
          else:
              raise
```

---

## 7. Feature Database — Python 3.12+

```yaml
# type statement
- id: python.syntax.type_statement
  language: python
  feature_name: "type statement (type aliases)"
  introduced: "3.12"
  category: syntax
  error_type: syntax_error
  detection:
    primary:
      ast_type: TypeAlias
      match: {}
  fix:
    strategy: rewrite_expression
    transforms:
      - type: rewrite_type_alias
        find:
          ast_type: TypeAlias
        replace:
          template: "{name} = {value}"
          add_import: "from typing import TypeAlias"
  test:
    before: |
      type Point = tuple[int, int]
    after: |
      from typing import TypeAlias
      Point: TypeAlias = tuple[int, int]

# f-string nested expressions (3.12)
- id: python.syntax.fstring_nested
  language: python
  feature_name: "nested f-string expressions"
  introduced: "3.12"
  category: syntax
  error_type: syntax_error
  detection:
    primary:
      ast_type: JoinedStr
      match:
        has_nested_fstring: true
  fix:
    strategy: manual
    manual_instructions: |
      Extract the inner f-string to a variable:
        f"{'yes' if f'{x}' == 'hello' else 'no'}"
        →
        inner = f'{x}'
        f"{'yes' if inner == 'hello' else 'no'}"
```

---

## 8. Python-Specific Edge Cases

### 8.1 `__future__` annotations interaction

When `from __future__ import annotations` is present:
- ALL annotations become strings (deferred evaluation)
- `list[int]`, `int | str`, `dict[str, Any]` in annotations → SAFE
- Same expressions in RUNTIME code → STILL UNSAFE

The detection engine MUST check context:
```python
def _is_annotation_context(self, node: ast.AST, tree: ast.Module) -> bool:
    """Check if node is in an annotation context (type hint)."""
    # Walk up parents to see if node is inside:
    # - function parameter annotation
    # - function return annotation
    # - variable annotation
    # - class variable annotation
    # NOT: isinstance() argument, print() argument, assignment value
```

### 8.2 `TYPE_CHECKING` blocks

```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from some_module import HeavyClass  # Never executes at runtime
```

Imports inside `TYPE_CHECKING` blocks:
- Do NOT cause runtime errors
- Are annotation-only by nature
- Should be EXCLUDED from downgrade findings (unless the feature is a syntax error that prevents parsing)

### 8.3 Star imports

`from module import *` makes it impossible to know which names are available without resolving `__all__` from the source module. The engine should:
1. Try to read `__all__` from the imported module
2. If `__all__` exists, treat it as importing those names
3. If `__all__` doesn't exist, flag as "unresolvable star import — manual review needed"

### 8.4 Dynamic imports

```python
importlib.import_module("some.module")
__import__("some.module")
```

If the module name is a string literal, resolve it. If it's a variable, flag as "dynamic import — cannot analyze."

### 8.5 Conditional version checks

```python
import sys
if sys.version_info >= (3, 11):
    from datetime import UTC
else:
    from datetime import timezone
    UTC = timezone.utc
```

This code ALREADY handles both versions. The engine should NOT flag `datetime.UTC` here — it's inside a version gate. Detection must exclude nodes inside `sys.version_info` comparison blocks.

### 8.6 `try/except ImportError` patterns

```python
try:
    from datetime import UTC
except ImportError:
    from datetime import timezone
    UTC = timezone.utc
```

Similar to version gate — the code handles the missing import. The engine should flag this as `info` (already handled) rather than `error`.

### 8.7 Monkey-patching / runtime modifications

```python
import datetime
datetime.UTC = datetime.timezone.utc  # Monkey-patch
```

AST detection won't catch this as a feature USAGE — it's an assignment. This is an edge case that's acceptable to miss (it's extremely rare and inherently fragile code).

### 8.8 Metaclass and descriptor features

Some Python version features are about metaclass behavior, descriptor protocol changes, or MRO changes. These are behavioral changes that are nearly impossible to detect via AST:
- `__init_subclass__` (3.6)
- `__set_name__` (3.6)
- `__class_getitem__` (3.7)

These are documented as `behavioral_change` with `strategy: manual`.

---

## 9. Integration Points

### 9.1 With Feature Database (Document 02)
- Python entries stored in `database/entries/python/`
- Organized by: stdlib.yml, syntax.yml, typing.yml, builtins.yml, exceptions.yml

### 9.2 With AST Detection Engine (Document 03)
- PythonBackend implements LanguageBackend interface
- Uses `ast` stdlib for parsing and walking

### 9.3 With Import Resolver (Document 04)
- Python import resolution: absolute, relative, star, dynamic
- Package vs stdlib vs project detection

### 9.4 With Fix Engine (Document 05)
- Python transforms use `ast` for modification
- Source emission via `ast.unparse()` or `libcst` for formatting preservation

### 9.5 With Backport Registry (Document 17)
- Python has the most backport packages: tomli, typing_extensions, exceptiongroup, backports.strenum
