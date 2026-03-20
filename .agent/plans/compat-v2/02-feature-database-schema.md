# 02 — Feature Database Schema & Format

> **Document**: 2 of 37
> **Milestone**: M1 — Feature database & data model
> **Status**: Draft

---

## 1. Purpose

The feature database is the foundation of the entire system. Every version-specific language feature — across all 10 languages, both upgrade and downgrade directions — is an entry in this database. The database is the single source of truth for:

- What features exist in each language version
- How to detect them in source code (via AST)
- How to fix them when targeting a different version
- How to verify the fix worked
- What edge cases exist
- What the before/after code looks like

Without this database, nothing works. The analysis engine has nothing to match against. The fix engine has nothing to apply. The verification engine has nothing to check.

---

## 2. Design Principles

### 2.1 Data, not code
Feature entries are YAML data files, not Python code. This means:
- Non-programmers can contribute entries
- Entries are auditable — you can diff them, review them, version them
- The engine is generic — it doesn't know about datetime.UTC or match/case, it just processes entries
- Adding a new feature detection never requires changing engine code

### 2.2 Detection-fix coupling
Every entry that has a detection MUST have a fix. Every fix MUST reference a detection. They are fields on the SAME entry. You cannot add a detection without specifying how to fix it. You cannot add a fix without specifying what it fixes.

### 2.3 Testable
Every entry includes a `test` field with before/after source code. This serves as:
- Documentation of what the fix does
- Automated test case — run the detection on `before`, apply the fix, compare with `after`
- Edge case validation

### 2.4 Bidirectional
Every entry specifies its `direction`:
- `downgrade` — this feature needs to be REMOVED when targeting an older version
- `upgrade` — this feature can be ADDED when targeting a newer version (modernization)
- `both` — entry has transforms for both directions

---

## 3. Entry Schema

### 3.1 Top-level fields

```yaml
id: string                    # Unique identifier: "{language}.{category}.{name}"
                              # Examples: "python.stdlib.datetime_utc"
                              #           "javascript.es2020.optional_chaining"
                              #           "go.1_21.slices_package"

language: string              # One of: python, javascript, typescript, go, rust,
                              #         ruby, java, csharp, php, elixir

feature_name: string          # Human-readable name: "datetime.UTC"
                              #                      "Optional chaining (?. operator)"

introduced: string            # Version where this feature was added: "3.11", "ES2020", "1.21"

removed: string | null        # Version where this feature was removed (rare): "3.12" or null

deprecated: string | null     # Version where this feature was deprecated: "3.11" or null

category: string              # Language-specific category
                              # Python: stdlib, syntax, typing, builtins, exceptions
                              # JS/TS: es2015, es2016, ..., es2024, node_api
                              # Go: stdlib, syntax, generics
                              # Rust: edition2015, edition2018, edition2021, std
                              # Ruby: syntax, stdlib, core
                              # Java: syntax, api, jvm
                              # C#: syntax, api, runtime
                              # PHP: syntax, stdlib, extensions
                              # Elixir: syntax, stdlib, otp

description: string           # What this feature is and why it matters for compat

direction: string             # "downgrade" | "upgrade" | "both"

severity: string              # "error" — code will crash at runtime
                              # "warning" — code may behave differently
                              # "info" — style/modernization opportunity

tags: list[string]            # Searchable tags: ["import", "datetime", "stdlib"]
```

### 3.2 Detection rules

```yaml
detection:
  # Primary detection rule
  primary:
    ast_type: string            # AST node type to match
                                # Python: ImportFrom, Attribute, Match, BinOp, NamedExpr, etc.
                                # JS: OptionalMemberExpression, NullishCoalescing, etc.
    match:                      # Fields to match on the AST node
      key: value                # Language-specific — maps to AST node attributes
    context: string | null      # Optional: "module_level" | "function_body" | "class_body" | "any"

  # Additional detection rules (same feature can appear in multiple forms)
  # Example: datetime.UTC can be "from datetime import UTC" OR "datetime.UTC"
  alternatives:
    - ast_type: string
      match:
        key: value
      context: string | null

  # Patterns that look like this feature but are NOT (false positive exclusions)
  exclude:
    - ast_type: string
      match:
        key: value
      reason: string            # Why this is excluded
```

#### Python detection examples

```yaml
# from datetime import UTC
detection:
  primary:
    ast_type: ImportFrom
    match:
      module: datetime
      names_contains: UTC
  alternatives:
    # datetime.UTC (attribute access)
    - ast_type: Attribute
      match:
        value_type: Name
        value_id: datetime
        attr: UTC
  exclude:
    # Inside TYPE_CHECKING block — won't run at runtime
    - ast_type: ImportFrom
      match:
        module: datetime
        names_contains: UTC
      context: type_checking_block
      reason: "Import only used for type annotations, never executed"
```

```yaml
# match/case statement
detection:
  primary:
    ast_type: Match
    match: {}  # Any Match node — the node type itself is the feature
  alternatives: []
  exclude: []
```

```yaml
# walrus operator :=
detection:
  primary:
    ast_type: NamedExpr
    match: {}
  alternatives: []
  exclude: []
```

#### JavaScript detection examples

```yaml
# Optional chaining (?.)
detection:
  primary:
    ast_type: OptionalMemberExpression
    match: {}
  alternatives:
    - ast_type: OptionalCallExpression
      match: {}
  exclude: []
```

```yaml
# Nullish coalescing (??)
detection:
  primary:
    ast_type: LogicalExpression
    match:
      operator: "??"
  alternatives: []
  exclude: []
```

#### Go detection examples

```yaml
# slices package (Go 1.21)
detection:
  primary:
    ast_type: ImportSpec
    match:
      path: '"slices"'
  alternatives: []
  exclude: []
```

### 3.3 Fix strategy

```yaml
fix:
  strategy: string              # The type of fix to apply
                                # "replace_import" — change an import statement
                                # "replace_import_and_usages" — change import + all usages of imported name
                                # "rewrite_expression" — rewrite a code expression
                                # "add_import" — add a new import
                                # "remove_import" — remove an import
                                # "add_backport_import" — add a backport package import
                                # "wrap_in_try_except" — wrap in try/except for conditional import
                                # "add_version_gate" — add sys.version_info check
                                # "add_future_import" — add from __future__ import annotations
                                # "manual" — cannot be auto-fixed, provide instructions only
                                # "no_fix_needed" — upgrade direction, feature is now available

  # The actual transforms to apply (ordered)
  transforms:
    - type: string              # Transform type
      find: object              # What to find (references detection result)
      replace: object           # What to replace with
      scope: string             # "file" | "imported_name" | "expression"

  # Backport package info (if fix involves a backport)
  backport:
    package: string | null      # "backports.strenum", "tomli", etc.
    import_name: string | null  # What to import from the backport
    min_version: string | null  # Minimum backport version needed
    note: string | null         # Additional info

  # If strategy is "manual" — provide instructions
  manual_instructions: string | null
```

#### Fix examples

```yaml
# datetime.UTC → datetime.timezone.utc
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
        origin: import  # Only replace UTC that came from this import
      replace:
        expression: "timezone.utc"
  backport: null
  manual_instructions: null
```

```yaml
# match/case → if/elif chain
fix:
  strategy: manual
  transforms: []
  backport: null
  manual_instructions: |
    match/case statements must be manually rewritten as if/elif chains.
    Each `case Pattern:` becomes an `elif` with the equivalent condition.
    Structural pattern matching has no mechanical backport.
```

```yaml
# str.removeprefix() → manual slice
fix:
  strategy: rewrite_expression
  transforms:
    - type: rewrite_method_call
      find:
        method: removeprefix
        receiver_type: str
      replace:
        template: "{receiver}[len({arg}):]  if {receiver}.startswith({arg}) else {receiver}"
        extract:
          receiver: call_receiver
          arg: call_args[0]
  backport: null
  manual_instructions: null
```

```yaml
# tomllib → tomli backport
fix:
  strategy: add_backport_import
  transforms:
    - type: replace_import
      find:
        import_module: tomllib
      replace:
        import_statement: "import tomli as tomllib"
  backport:
    package: tomli
    import_name: tomli
    min_version: "1.0.0"
    note: "tomli is the backport of tomllib for Python < 3.11"
  manual_instructions: null
```

```yaml
# Optional chaining ?. (JS) → && chain
fix:
  strategy: rewrite_expression
  transforms:
    - type: rewrite_optional_chain
      find:
        ast_type: OptionalMemberExpression
      replace:
        template: "{base} && {base}.{property}"
        extract:
          base: object
          property: property
  backport: null
  manual_instructions: "Deep optional chains (a?.b?.c?.d) require careful rewriting"
```

### 3.4 Verification

```yaml
verification:
  re_detect: boolean            # After fix, re-run detection — must find 0 matches
                                # Default: true — almost always want this

  import_check: boolean         # After fix, verify file still imports/compiles
                                # Default: true for runtime features
                                # false for annotation-only features

  syntax_check: boolean         # After fix, verify file parses without syntax errors
                                # Default: true

  custom_check: string | null   # Optional custom verification command
                                # Example: "python -c 'from datetime import timezone; print(timezone.utc)'"
```

### 3.5 Edge cases

```yaml
edge_cases:
  - id: string                 # "python.datetime_utc.multi_import"
    description: string        # "UTC imported alongside other names"
    example: string            # "from datetime import datetime, UTC, timezone"
    handling: string            # "preserve other imports, only remove/replace UTC"
    test:
      before: string
      after: string
```

### 3.6 Test case

```yaml
test:
  # Minimal before/after proving the fix works
  before: |
    from datetime import UTC, datetime
    now = datetime.now(UTC)
    ts = datetime(2024, 1, 1, tzinfo=UTC)
  after: |
    from datetime import timezone, datetime
    now = datetime.now(timezone.utc)
    ts = datetime(2024, 1, 1, tzinfo=timezone.utc)

  # Additional test cases for edge cases
  additional:
    - name: "UTC as sole import"
      before: |
        from datetime import UTC
        now = datetime.now(UTC)
      after: |
        from datetime import timezone
        now = datetime.now(timezone.utc)

    - name: "datetime.UTC attribute access"
      before: |
        import datetime
        now = datetime.datetime.now(datetime.UTC)
      after: |
        import datetime
        now = datetime.datetime.now(datetime.timezone.utc)
```

---

## 4. File Organization

```
database/entries/
├── python/
│   ├── _meta.yml              ← Language metadata (versions, parser info)
│   ├── stdlib.yml             ← Standard library features
│   │                           datetime.UTC, tomllib, StrEnum, etc.
│   ├── syntax.yml             ← Syntax features
│   │                           match/case, walrus :=, except*, positional-only /
│   ├── typing.yml             ← Type annotation features
│   │                           X|Y union, builtin generics list[T], ParamSpec
│   ├── builtins.yml           ← Builtin method features
│   │                           str.removeprefix, str.removesuffix, dict |
│   └── exceptions.yml         ← Exception/error features
│                               ExceptionGroup, add_note
│
├── javascript/
│   ├── _meta.yml
│   ├── es2015.yml             ← let/const, arrow, class, template literals, Promise, etc.
│   ├── es2016.yml             ← Array.includes, **
│   ├── es2017.yml             ← async/await, Object.entries/values
│   ├── es2018.yml             ← rest/spread, async iteration, regex groups
│   ├── es2019.yml             ← flat/flatMap, Object.fromEntries, optional catch
│   ├── es2020.yml             ← ?., ??, BigInt, Promise.allSettled, globalThis
│   ├── es2021.yml             ← &&=, ||=, ??=, replaceAll, Promise.any
│   ├── es2022.yml             ← top-level await, .at(), class fields, #private
│   ├── es2023.yml             ← findLast, hashbang, change-array-by-copy
│   └── es2024.yml             ← Object.groupBy, Promise.withResolvers, ArrayBuffer
│
├── typescript/
│   ├── _meta.yml
│   ├── ts4.yml                ← Features from TypeScript 4.x
│   └── ts5.yml                ← Features from TypeScript 5.x (satisfies, const type params, decorators)
│
├── go/
│   ├── _meta.yml
│   ├── go1_18.yml             ← Generics, fuzzing, workspace
│   ├── go1_19.yml             ← Atomic types
│   ├── go1_20.yml             ← Errors wrapping, slice to array
│   ├── go1_21.yml             ← slices/maps/cmp packages, log/slog, min/max builtins
│   ├── go1_22.yml             ← for-range integers, ServeMux patterns
│   └── go1_23.yml             ← Iterators, unique package
│
├── rust/
│   ├── _meta.yml
│   ├── edition_2018.yml       ← dyn Trait, module paths, async/await (1.39)
│   ├── edition_2021.yml       ← Closure captures, IntoIterator for arrays
│   ├── edition_2024.yml       ← unsafe_op_in_unsafe_fn, gen blocks
│   └── std_features.yml       ← Stabilized std features by version
│
├── ruby/
│   ├── _meta.yml
│   ├── ruby3_0.yml            ← Ractor, Fiber scheduler, rightward assignment
│   ├── ruby3_1.yml            ← Pin operator, shorthand hash
│   ├── ruby3_2.yml            ← Data class, anonymous rest/keyword
│   └── ruby3_3.yml            ← it reference, Prism parser
│
├── java/
│   ├── _meta.yml
│   ├── java11.yml             ← var in lambda, HTTP client, String methods
│   ├── java14.yml             ← Records, switch expressions, text blocks
│   ├── java16.yml             ← Pattern matching instanceof, sealed classes
│   ├── java17.yml             ← Sealed classes (finalized), pattern matching
│   └── java21.yml             ← Virtual threads, pattern matching switch, string templates
│
├── csharp/
│   ├── _meta.yml
│   ├── csharp8.yml            ← Nullable references, switch expressions, using declarations
│   ├── csharp9.yml            ← Records, init-only, top-level statements
│   ├── csharp10.yml           ← Global usings, file-scoped namespaces
│   ├── csharp11.yml           ← Raw string literals, list patterns
│   └── csharp12.yml           ← Primary constructors, collection expressions
│
├── php/
│   ├── _meta.yml
│   ├── php8_0.yml             ← Union types, named args, match, null-safe, attributes
│   ├── php8_1.yml             ← Enums, fibers, readonly, intersection types
│   ├── php8_2.yml             ← DNF types, readonly classes, true/false/null types
│   └── php8_3.yml             ← Typed class constants, json_validate, Override attribute
│
└── elixir/
    ├── _meta.yml
    ├── elixir1_12.yml         ← Stepped ranges, then/1
    ├── elixir1_13.yml         ← Semantic rewriting
    ├── elixir1_14.yml         ← Debugging improvements, anti-patterns
    └── elixir1_15.yml         ← Duration module, set operations
```

---

## 5. Language Metadata (_meta.yml)

Each language directory has a `_meta.yml` that describes:

```yaml
language: python
display_name: Python
file_extensions: [".py"]
parser: ast                    # Which parser backend to use
                               # python: ast (stdlib)
                               # javascript: tree-sitter-javascript
                               # typescript: tree-sitter-typescript
                               # go: tree-sitter-go
                               # etc.

versions:
  # Ordered list of versions, oldest to newest
  - version: "3.7"
    eol: "2023-06-27"
    status: eol
  - version: "3.8"
    eol: "2024-10-14"
    status: eol
  - version: "3.9"
    eol: "2025-10-05"
    status: security
  - version: "3.10"
    eol: "2026-10-04"
    status: security
  - version: "3.11"
    eol: "2027-10-24"
    status: active
  - version: "3.12"
    eol: "2028-10-02"
    status: active
  - version: "3.13"
    eol: "2029-10-01"
    status: active

version_format: "major.minor"  # How versions are compared
                               # python: "major.minor" (3.8, 3.11)
                               # javascript: "ES{year}" (ES2020) or Node "major" (18, 20)
                               # go: "major.minor" (1.21)
                               # rust: "major.minor.patch" (1.75.0) + editions
                               # java: "major" (17, 21)

import_styles:
  - "import {module}"
  - "from {module} import {name}"
  - "from {module} import {name} as {alias}"

package_registry:
  name: PyPI
  api: "https://pypi.org/pypi/{package}/json"
  version_field: "requires_python"
```

---

## 6. Entry Validation

Every entry in the database is validated at load time:

### 6.1 Required fields
- `id` must be unique across all entries
- `language` must match the directory it's in
- `introduced` must be a valid version for the language
- `detection.primary` must be present
- `fix.strategy` must be present
- `test.before` and `test.after` must be present

### 6.2 Consistency checks
- If `fix.strategy` is not `manual` and not `no_fix_needed`, `fix.transforms` must be non-empty
- If `fix.backport` is specified, `fix.backport.package` must be non-empty
- `direction` must be one of `downgrade`, `upgrade`, `both`
- `severity` must be one of `error`, `warning`, `info`

### 6.3 Test validation
- Parse `test.before` with the language parser — must parse without errors
- Apply the detection rules to `test.before` — must find at least one match
- Apply the fix transforms to `test.before` — result must match `test.after`
- Apply the detection rules to `test.after` — must find zero matches

This validation runs as part of CI. A broken entry cannot be merged.

---

## 7. Entry Count Targets

### 7.1 Python (target: 200+ entries)

| Category | Estimated entries |
|----------|-------------------|
| stdlib (3.8–3.13) | 80+ |
| syntax (3.8–3.13) | 30+ |
| typing (3.8–3.13) | 40+ |
| builtins (3.8–3.13) | 30+ |
| exceptions (3.8–3.13) | 20+ |

### 7.2 JavaScript/TypeScript (target: 250+ entries)

| Category | Estimated entries |
|----------|-------------------|
| ES2015–ES2024 (10 years) | 200+ |
| TypeScript 4.x–5.x | 50+ |

### 7.3 Go (target: 100+ entries)

| Category | Estimated entries |
|----------|-------------------|
| Go 1.18–1.23 (6 versions) | 60+ |
| stdlib additions | 40+ |

### 7.4 Rust (target: 100+ entries)

| Category | Estimated entries |
|----------|-------------------|
| Edition changes | 20+ |
| Stabilized features | 80+ |

### 7.5 Ruby (target: 80+ entries)

| Category | Estimated entries |
|----------|-------------------|
| Ruby 3.0–3.3 | 80+ |

### 7.6 Java (target: 100+ entries)

| Category | Estimated entries |
|----------|-------------------|
| Java 11–21 | 100+ |

### 7.7 C# (target: 80+ entries)

| Category | Estimated entries |
|----------|-------------------|
| C# 8–12 | 80+ |

### 7.8 PHP (target: 60+ entries)

| Category | Estimated entries |
|----------|-------------------|
| PHP 8.0–8.3 | 60+ |

### 7.9 Elixir (target: 40+ entries)

| Category | Estimated entries |
|----------|-------------------|
| Elixir 1.12–1.15 | 40+ |

### Total: ~1010+ entries

---

## 8. Loading & Registry

### 8.1 Load pipeline

```
YAML files on disk
    │
    ▼
schema.py validates each entry
    │
    ▼
loader.py reads all .yml files from entries/{language}/
    │
    ▼
registry.py indexes entries by:
    - id (unique lookup)
    - language (all entries for a language)
    - version (all entries introduced in a version)
    - category (all entries in a category)
    - direction (all downgrade entries, all upgrade entries)
    │
    ▼
Analysis engine queries registry:
    "Give me all Python features introduced after 3.8"
    → returns all entries where language=python and introduced > 3.8
```

### 8.2 Registry API

```python
class FeatureRegistry:
    def get(self, feature_id: str) -> FeatureEntry | None
    def by_language(self, language: str) -> list[FeatureEntry]
    def above_version(self, language: str, version: str) -> list[FeatureEntry]
    def below_version(self, language: str, version: str) -> list[FeatureEntry]
    def by_category(self, language: str, category: str) -> list[FeatureEntry]
    def by_direction(self, language: str, direction: str) -> list[FeatureEntry]
    def search(self, query: str) -> list[FeatureEntry]
    def count(self) -> int
    def count_by_language(self) -> dict[str, int]
```

---

## 9. Contributing New Entries

Adding a new feature detection:

1. Create or edit the appropriate YAML file in `database/entries/{language}/`
2. Add the entry following the schema above
3. Include `test.before` and `test.after`
4. Run validation: `controlplane compat validate-db`
5. Validation will:
   - Parse the before/after code
   - Run detection on `before` — must match
   - Apply fix to `before` — must produce `after`
   - Run detection on `after` — must not match
6. Submit PR — CI runs the same validation

No engine code changes required. The engine is generic — it processes entries.
