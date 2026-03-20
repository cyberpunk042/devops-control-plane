# 23 — Ruby Language Module

> **Document**: 23 of 37
> **Milestone**: M9 — Language modules & edge cases
> **Status**: Draft

---

## 1. Overview

**Versions covered**: Ruby 2.7 through 3.3+
**Feature entries target**: 80+
**Parser**: tree-sitter-ruby (or Prism for Ruby 3.3+)
**Import resolver**: Follow `require`/`require_relative`/`load`
**Package registry**: RubyGems
**Formatter**: `rubocop` (optional)

---

## 2. Feature Database Highlights

```yaml
# Ruby 3.0 — Pattern matching
- id: ruby.3_0.pattern_matching
  feature_name: "pattern matching (case/in)"
  introduced: "3.0"
  detection:
    primary:
      ast_type: case_match
  fix:
    strategy: manual
    manual_instructions: "Rewrite as case/when with manual destructuring"

# Ruby 3.0 — Ractor
- id: ruby.3_0.ractor
  feature_name: "Ractor (actor-based concurrency)"
  introduced: "3.0"
  detection:
    primary:
      ast_type: constant
      match:
        name: Ractor
  fix:
    strategy: manual
    manual_instructions: "Use Thread or process-based concurrency"

# Ruby 3.0 — Endless method
- id: ruby.3_0.endless_method
  feature_name: "endless method definition"
  introduced: "3.0"
  detection:
    primary:
      ast_type: method
      match:
        endless: true
  fix:
    strategy: rewrite_expression
    transforms:
      - type: expand_endless_method
  test:
    before: |
      def double(x) = x * 2
    after: |
      def double(x)
        x * 2
      end

# Ruby 3.1 — Hash shorthand
- id: ruby.3_1.hash_shorthand
  feature_name: "hash value omission ({x:})"
  introduced: "3.1"
  detection:
    primary:
      ast_type: pair
      match:
        shorthand: true
  fix:
    strategy: rewrite_expression
    transforms:
      - type: expand_hash_shorthand
  test:
    before: |
      h = {x:, y:, z:}
    after: |
      h = {x: x, y: y, z: z}

# Ruby 3.1 — Pin operator in pattern matching
- id: ruby.3_1.pin_operator
  feature_name: "pin operator (^) in pattern matching"
  introduced: "3.1"
  detection:
    primary:
      ast_type: pin_expression

# Ruby 3.2 — Data class
- id: ruby.3_2.data_class
  feature_name: "Data class (immutable value object)"
  introduced: "3.2"
  detection:
    primary:
      ast_type: call
      match:
        receiver: Data
        method: define
  fix:
    strategy: manual
    manual_instructions: "Use Struct with freeze, or a gem like 'dry-struct'"

# Ruby 3.2 — Anonymous rest/keyword
- id: ruby.3_2.anonymous_rest
  feature_name: "anonymous rest (*, **) forwarding"
  introduced: "3.2"
  detection:
    primary:
      ast_type: restarg
      match:
        name: null
  fix:
    strategy: rewrite_expression
    transforms:
      - type: add_rest_name
  test:
    before: |
      def forward(*, **)
        other(*, **)
      end
    after: |
      def forward(*args, **kwargs)
        other(*args, **kwargs)
      end

# Ruby 3.3 — it reference
- id: ruby.3_3.it_reference
  feature_name: "it (implicit block parameter)"
  introduced: "3.3"
  detection:
    primary:
      ast_type: identifier
      match:
        name: it
        context: block_body_without_params
  fix:
    strategy: rewrite_expression
    transforms:
      - type: add_block_param
  test:
    before: |
      [1, 2, 3].map { it * 2 }
    after: |
      [1, 2, 3].map { |it| it * 2 }
```

---

## 3. Ruby-Specific Edge Cases

### 3.1 Monkey-patching
Ruby heavily uses monkey-patching (reopening classes). A gem might add methods to core classes that look like built-in features. The engine should not flag gem-added methods.

### 3.2 Refinements
```ruby
using SomeRefinement
```
Refinements modify class behavior in a scoped way. They can mask or provide features.

### 3.3 Bundler / Gemfile
Ruby projects use Bundler with `Gemfile` for dependency management. The `required_ruby_version` in `.gemspec` declares the version floor.

---

## 4. Integration Points

Standard LanguageBackend interface.
- tree-sitter-ruby or Prism parser
- `ruby -c` for syntax verification
- `require_relative` resolution for import chains
- RubyGems API for dependency analysis
- `rubocop` for optional post-transform formatting
