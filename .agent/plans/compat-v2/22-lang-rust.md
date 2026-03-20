# 22 — Rust Language Module

> **Document**: 22 of 37
> **Milestone**: M9 — Language modules & edge cases
> **Status**: Draft

---

## 1. Overview

**Versions covered**: Rust 1.56+ (edition 2021) through 1.80+
**Editions**: 2015, 2018, 2021, 2024
**Feature entries target**: 100+
**Parser**: tree-sitter-rust
**Import resolver**: Follow `use`/`mod` declarations, resolve via crate structure
**Package registry**: crates.io
**Formatter**: `rustfmt` (canonical)

---

## 2. Rust Version Model

Rust has TWO version axes:
1. **Compiler version** (1.56, 1.70, 1.80): Determines which features are stabilized
2. **Edition** (2015, 2018, 2021, 2024): Changes language semantics, set in `Cargo.toml`

A feature might require "Rust 1.65+ AND edition 2021". Both must be checked.

**MSRV** (Minimum Supported Rust Version): Declared in `Cargo.toml` as `rust-version = "1.70"`. This is the version floor equivalent.

---

## 3. Feature Database

### Edition-level features

```yaml
- id: rust.edition_2018.dyn_trait
  feature_name: "dyn Trait (required)"
  introduced: "edition_2018"
  description: "Bare trait objects (Box<Trait>) require 'dyn' keyword"
  detection:
    primary:
      ast_type: trait_bound
      match:
        missing_dyn: true
  fix:
    strategy: rewrite_expression
    transforms:
      - type: add_dyn_keyword
  severity: warning  # warning in 2015, error in 2018+

- id: rust.edition_2021.closure_captures
  feature_name: "precise closure captures"
  introduced: "edition_2021"
  description: "2021 edition captures individual fields, 2018 captures entire struct"
  detection:
    primary:
      ast_type: closure_expression
      match:
        captures_field: true  # Hard to detect — may need type info
  fix:
    strategy: manual
    manual_instructions: |
      In edition 2018, closures capture the entire variable.
      In edition 2021, they capture individual fields.
      If you drop a struct field in a closure, the struct is still usable in 2021 but not 2018.
      Add explicit `let _ = &whole_struct;` to force whole-struct capture if needed.

- id: rust.edition_2021.into_iterator_array
  feature_name: "IntoIterator for arrays"
  introduced: "edition_2021"
  description: "[T; N].into_iter() yields T in 2021, &T in 2018"
  detection:
    primary:
      ast_type: method_call_expression
      match:
        method: into_iter
        receiver_type: array
  fix:
    strategy: rewrite_expression
    transforms:
      - type: rewrite_method_call
        replace:
          template: "{receiver}.iter().copied()"
```

### Stabilized features by version

```yaml
- id: rust.1_65.let_else
  feature_name: "let-else statement"
  introduced: "1.65"
  detection:
    primary:
      ast_type: let_declaration
      match:
        has_else: true
  fix:
    strategy: rewrite_expression
    transforms:
      - type: rewrite_let_else
        replace:
          style: match_or_if_let
  test:
    before: |
      let Some(x) = opt else { return };
    after: |
      let x = match opt {
          Some(x) => x,
          None => return,
      };

- id: rust.1_70.once_lock
  feature_name: "std::sync::OnceLock"
  introduced: "1.70"
  detection:
    primary:
      ast_type: use_declaration
      match:
        path_contains: "sync::OnceLock"
  fix:
    strategy: replace_import
    backport:
      package: once_cell
      import_statement: "use once_cell::sync::OnceCell;"

- id: rust.1_75.async_fn_in_trait
  feature_name: "async fn in trait"
  introduced: "1.75"
  detection:
    primary:
      ast_type: function_item
      match:
        is_async: true
        context: trait_impl
  fix:
    strategy: manual
    manual_instructions: "Use async-trait crate: #[async_trait] attribute"
    backport:
      package: async-trait
```

---

## 4. Rust-Specific Edge Cases

### 4.1 Feature gates
Nightly Rust has unstable features behind `#![feature(...)]`. Stable Rust doesn't. If code uses `#![feature(x)]`, it's nightly-only. Flag as requiring nightly.

### 4.2 Conditional compilation
```rust
#[cfg(feature = "unstable")]
fn experimental() { ... }
```
Respect `#[cfg]` attributes — code behind feature flags may use newer Rust intentionally.

### 4.3 Proc macros
Procedural macros generate code at compile time. Generated code might use features above the MSRV. The engine should skip expanded macro output (analyze source, not expansion).

### 4.4 Cargo.toml edition field
```toml
[package]
edition = "2021"
rust-version = "1.70"
```
Both must be checked. Edition determines language semantics. rust-version determines API availability.

---

## 5. Integration Points

Standard LanguageBackend interface. Key Rust-specific aspects:
- Dual version axis (compiler version + edition)
- `Cargo.toml` parsing for MSRV and edition
- `cargo check` for verification
- `rustfmt` for post-transform formatting
- Feature gate detection for nightly code
- `cfg` attribute awareness for conditional compilation
