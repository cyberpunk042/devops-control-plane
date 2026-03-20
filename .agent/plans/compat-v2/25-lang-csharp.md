# 25 — C#/.NET Language Module

> **Document**: 25 of 37
> **Milestone**: M9 — Language modules & edge cases
> **Status**: Draft

---

## 1. Overview

**Versions covered**: C# 8.0 through 12.0
**Runtime**: .NET Core 3.1, .NET 5, 6 (LTS), 7, 8 (LTS)
**Feature entries target**: 80+
**Parser**: tree-sitter-c-sharp
**Import resolver**: Follow `using` declarations, resolve via namespace/project structure
**Package registry**: NuGet
**Formatter**: `dotnet format`

---

## 2. C# Version Model

C# version is tied to .NET version:
- C# 8 → .NET Core 3.1
- C# 9 → .NET 5
- C# 10 → .NET 6
- C# 11 → .NET 7
- C# 12 → .NET 8

The `<LangVersion>` in `.csproj` can override, but typically matches the target framework.

---

## 3. Feature Database Highlights

```yaml
# C# 8 — Nullable reference types
- id: csharp.8.nullable_references
  feature_name: "nullable reference types"
  introduced: "8"
  detection:
    primary:
      ast_type: nullable_type
      match:
        is_reference: true
    alternatives:
      - ast_type: project_property
        match:
          name: Nullable
          value: enable
  fix:
    strategy: manual
    manual_instructions: "Remove nullable annotations (?) and #nullable directives"

# C# 8 — Switch expressions
- id: csharp.8.switch_expression
  feature_name: "switch expression"
  introduced: "8"
  detection:
    primary:
      ast_type: switch_expression
  fix:
    strategy: manual
    manual_instructions: "Rewrite as switch statement"

# C# 8 — Using declarations (no braces)
- id: csharp.8.using_declaration
  feature_name: "using declaration (without braces)"
  introduced: "8"
  detection:
    primary:
      ast_type: using_declaration
  fix:
    strategy: rewrite_expression
    transforms:
      - type: wrap_in_using_block

# C# 9 — Records
- id: csharp.9.records
  feature_name: "record types"
  introduced: "9"
  detection:
    primary:
      ast_type: record_declaration
  fix:
    strategy: manual
    manual_instructions: "Replace with class implementing IEquatable<T>"

# C# 9 — Init-only properties
- id: csharp.9.init_only
  feature_name: "init-only setters"
  introduced: "9"
  detection:
    primary:
      ast_type: accessor_declaration
      match:
        keyword: init
  fix:
    strategy: rewrite_expression
    transforms:
      - type: replace_init_with_set

# C# 9 — Top-level statements
- id: csharp.9.top_level_statements
  feature_name: "top-level statements"
  introduced: "9"
  detection:
    primary:
      ast_type: compilation_unit
      match:
        has_top_level_statements: true
  fix:
    strategy: manual
    manual_instructions: "Wrap in Program class with Main method"

# C# 10 — Global using
- id: csharp.10.global_using
  feature_name: "global using directives"
  introduced: "10"
  detection:
    primary:
      ast_type: using_directive
      match:
        global: true
  fix:
    strategy: rewrite_expression
    transforms:
      - type: distribute_global_using
        replace:
          style: per_file_using

# C# 10 — File-scoped namespace
- id: csharp.10.file_scoped_namespace
  feature_name: "file-scoped namespace"
  introduced: "10"
  detection:
    primary:
      ast_type: file_scoped_namespace_declaration
  fix:
    strategy: rewrite_expression
    transforms:
      - type: wrap_in_namespace_block
  test:
    before: |
      namespace MyApp;
      class Foo { }
    after: |
      namespace MyApp
      {
          class Foo { }
      }

# C# 11 — Raw string literals
- id: csharp.11.raw_string_literal
  feature_name: 'raw string literals (""")'
  introduced: "11"
  detection:
    primary:
      ast_type: raw_string_literal_expression
  fix:
    strategy: rewrite_expression
    transforms:
      - type: rewrite_raw_string
        replace:
          style: verbatim_string_or_concat

# C# 11 — List patterns
- id: csharp.11.list_patterns
  feature_name: "list patterns"
  introduced: "11"
  detection:
    primary:
      ast_type: list_pattern
  fix:
    strategy: manual
    manual_instructions: "Rewrite as index checks and comparisons"

# C# 12 — Primary constructors
- id: csharp.12.primary_constructors
  feature_name: "primary constructors for classes"
  introduced: "12"
  detection:
    primary:
      ast_type: class_declaration
      match:
        has_parameter_list: true
  fix:
    strategy: manual
    manual_instructions: |
      Move parameters to a regular constructor:
        class Service(ILogger logger) { }
        →
        class Service {
            private readonly ILogger _logger;
            public Service(ILogger logger) { _logger = logger; }
        }

# C# 12 — Collection expressions
- id: csharp.12.collection_expressions
  feature_name: "collection expressions ([1, 2, 3])"
  introduced: "12"
  detection:
    primary:
      ast_type: collection_expression
  fix:
    strategy: rewrite_expression
    transforms:
      - type: rewrite_collection_expression
        replace:
          list: "new List<T> { items }"
          array: "new T[] { items }"
```

---

## 4. C#-Specific Edge Cases

### 4.1 Target framework vs language version
`.csproj` has both `<TargetFramework>` (runtime) and `<LangVersion>` (compiler). They're usually aligned but can diverge. Check both.

### 4.2 Source generators
Like Java annotation processors, source generators create code at compile time. Skip `Generated/` directories.

### 4.3 NuGet package compatibility
NuGet packages target specific .NET versions via target framework monikers (TFMs): `net6.0`, `net8.0`, `netstandard2.0`. A package targeting `net8.0` won't work on .NET 6.

### 4.4 Multi-targeting
```xml
<TargetFrameworks>net6.0;net8.0</TargetFrameworks>
```
Project builds for multiple frameworks. Code must be compatible with ALL targets. Use `#if` directives for framework-specific code.

---

## 5. Integration Points

Standard LanguageBackend. C#-specific:
- `.csproj` parsing for target framework and language version
- `dotnet build --no-restore` for verification
- NuGet API for package compatibility
- `dotnet format` for formatting
- Multi-target framework awareness
