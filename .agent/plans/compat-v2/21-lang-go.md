# 21 — Go Language Module

> **Document**: 21 of 37
> **Milestone**: M9 — Language modules & edge cases
> **Status**: Draft

---

## 1. Overview

**Versions covered**: Go 1.18 through 1.23+
**Feature entries target**: 100+
**Parser**: tree-sitter-go (or `go/parser` via subprocess)
**Import resolver**: Follow `import` declarations, resolve via module path + `go.mod`
**Package registry**: Go module proxy (`proxy.golang.org`)
**Formatter**: `gofmt` (canonical — always applied after transforms)

---

## 2. Key Go Characteristics

### 2.1 Version model
Go versions are `1.X` (e.g., 1.18, 1.21). The `go` directive in `go.mod` sets the minimum version. Go has strong backward compatibility — code written for 1.18 almost always works on 1.23.

### 2.2 No `__future__` equivalent
Go doesn't have deferred annotation evaluation. Features are either available or not. No annotation vs runtime distinction needed.

### 2.3 Editions don't exist
Unlike Rust, Go has no edition system. Each version just adds features. Old features are virtually never removed.

### 2.4 `go.mod` is the source of truth
The `go` directive in `go.mod` declares the minimum Go version. This is the project's version floor.

---

## 3. Feature Database

### Go 1.18 (generics)

```yaml
- id: go.1_18.generics
  feature_name: "generics (type parameters)"
  introduced: "1.18"
  category: syntax
  error_type: syntax_error
  detection:
    primary:
      ast_type: type_parameter_list
  fix:
    strategy: manual
    manual_instructions: |
      Generics require Go 1.18+. Rewrite to use interface{} or
      code generation (go generate) for type-safe alternatives.

- id: go.1_18.fuzzing
  feature_name: "fuzzing support"
  introduced: "1.18"
  detection:
    primary:
      ast_type: function_declaration
      match:
        name_prefix: Fuzz
  fix:
    strategy: manual
    manual_instructions: "Remove fuzz tests or gate with build tags"

- id: go.1_18.any_alias
  feature_name: "any (alias for interface{})"
  introduced: "1.18"
  detection:
    primary:
      ast_type: type_identifier
      match:
        name: any
  fix:
    strategy: rewrite_expression
    transforms:
      - type: replace_identifier
        find: { name: any }
        replace: { expression: "interface{}" }
```

### Go 1.21 (builtins + new packages)

```yaml
- id: go.1_21.slices_package
  feature_name: "slices package"
  introduced: "1.21"
  detection:
    primary:
      ast_type: import_spec
      match:
        path: '"slices"'
  fix:
    strategy: replace_import
    transforms:
      - type: replace_import_statement
        find: { import_path: "slices" }
        replace: { import_path: "golang.org/x/exp/slices" }
  backport:
    package: "golang.org/x/exp/slices"

- id: go.1_21.maps_package
  feature_name: "maps package"
  introduced: "1.21"
  detection:
    primary:
      ast_type: import_spec
      match:
        path: '"maps"'
  fix:
    strategy: replace_import
    backport:
      package: "golang.org/x/exp/maps"

- id: go.1_21.slog
  feature_name: "log/slog structured logging"
  introduced: "1.21"
  detection:
    primary:
      ast_type: import_spec
      match:
        path: '"log/slog"'
  fix:
    strategy: replace_import
    backport:
      package: "golang.org/x/exp/slog"

- id: go.1_21.min_max_builtins
  feature_name: "min/max builtin functions"
  introduced: "1.21"
  detection:
    primary:
      ast_type: call_expression
      match:
        function_in: [min, max]
        is_builtin: true
  fix:
    strategy: rewrite_expression
    transforms:
      - type: add_helper_function
        function: |
          func min(a, b int) int { if a < b { return a }; return b }
          func max(a, b int) int { if a > b { return a }; return b }
        note: "May need multiple type-specific versions without generics"

- id: go.1_21.clear_builtin
  feature_name: "clear() builtin"
  introduced: "1.21"
  detection:
    primary:
      ast_type: call_expression
      match:
        function: clear
        is_builtin: true
  fix:
    strategy: rewrite_expression
    transforms:
      - type: rewrite_clear_map
        replace:
          template: "for k := range {receiver} { delete({receiver}, k) }"
      - type: rewrite_clear_slice
        replace:
          template: "{receiver} = {receiver}[:0]"
```

### Go 1.22

```yaml
- id: go.1_22.range_int
  feature_name: "for range over integer"
  introduced: "1.22"
  detection:
    primary:
      ast_type: for_statement
      match:
        range_over_int: true
  fix:
    strategy: rewrite_expression
    transforms:
      - type: rewrite_range_int
        replace:
          template: "for {var} := 0; {var} < {n}; {var}++ {"
  test:
    before: |
      for i := range 10 {
          fmt.Println(i)
      }
    after: |
      for i := 0; i < 10; i++ {
          fmt.Println(i)
      }

- id: go.1_22.servemux_patterns
  feature_name: "enhanced ServeMux routing patterns"
  introduced: "1.22"
  detection:
    primary:
      ast_type: call_expression
      match:
        method: HandleFunc
        arg_contains_pattern: true  # Pattern like "GET /api/{id}"
  fix:
    strategy: manual
    manual_instructions: "Use a third-party router (gorilla/mux, chi) for pattern routing"
```

---

## 4. Go-Specific Edge Cases

### 4.1 Build tags / constraints
```go
//go:build go1.21
```
Build tags conditionally include files based on Go version. Files with `go1.21` tag are only compiled on Go 1.21+. The engine should:
- Read build tags from file headers
- If a file has `//go:build go1.X` where X > target → skip (file won't compile anyway)
- If a file has no build tag → scan normally

### 4.2 Vendored dependencies
Go's `vendor/` directory contains dependency source code. Do NOT scan vendored code — it's external.

### 4.3 `go generate` output
Generated files (marked with `// Code generated ... DO NOT EDIT.`) should be skipped — they'll be regenerated.

### 4.4 CGo
Files using `import "C"` (CGo) have special parsing rules. tree-sitter may not handle CGo perfectly — flag as "CGo file, limited analysis."

---

## 5. Integration Points

Standard LanguageBackend interface. Key Go-specific aspects:
- `go.mod` parsing for version floor and module path
- `go vet` for syntax/import checking
- `gofmt` for post-transform formatting
- Build tag awareness for conditional compilation
- `golang.org/x/exp` as primary backport source
