# 26 — PHP Language Module

> **Document**: 26 of 37
> **Milestone**: M9 — Language modules & edge cases
> **Status**: Draft

---

## 1. Overview

**Versions covered**: PHP 7.4 through 8.3
**Feature entries target**: 60+
**Parser**: tree-sitter-php
**Import resolver**: Follow `use`/`require`/`include`, resolve via PSR-4 autoloading
**Package registry**: Packagist
**Formatter**: `php-cs-fixer` (optional)

---

## 2. Feature Database Highlights

```yaml
# PHP 8.0 — Union types
- id: php.8_0.union_types
  feature_name: "union types (int|string)"
  introduced: "8.0"
  detection:
    primary:
      ast_type: union_type
  fix:
    strategy: manual
    manual_instructions: "Remove type declarations or use PHPDoc @param/@return annotations"

# PHP 8.0 — Named arguments
- id: php.8_0.named_arguments
  feature_name: "named arguments"
  introduced: "8.0"
  detection:
    primary:
      ast_type: named_argument
  fix:
    strategy: rewrite_expression
    transforms:
      - type: convert_to_positional
  test:
    before: |
      array_slice($array, offset: 2, length: 5);
    after: |
      array_slice($array, 2, 5);

# PHP 8.0 — Match expression
- id: php.8_0.match_expression
  feature_name: "match expression"
  introduced: "8.0"
  detection:
    primary:
      ast_type: match_expression
  fix:
    strategy: rewrite_expression
    transforms:
      - type: rewrite_match_to_switch

# PHP 8.0 — Null-safe operator
- id: php.8_0.nullsafe_operator
  feature_name: "null-safe operator (?->)"
  introduced: "8.0"
  detection:
    primary:
      ast_type: nullsafe_member_access_expression
  fix:
    strategy: rewrite_expression
    transforms:
      - type: rewrite_nullsafe
        replace:
          template: "({base} !== null ? {base}->{property} : null)"

# PHP 8.0 — Attributes (#[])
- id: php.8_0.attributes
  feature_name: "attributes (#[Attribute])"
  introduced: "8.0"
  detection:
    primary:
      ast_type: attribute_list
  fix:
    strategy: manual
    manual_instructions: "Replace with PHPDoc annotations or remove"

# PHP 8.1 — Enums
- id: php.8_1.enums
  feature_name: "enum declaration"
  introduced: "8.1"
  detection:
    primary:
      ast_type: enum_declaration
  fix:
    strategy: manual
    manual_instructions: "Replace with class constants or myclabs/php-enum"
    backport:
      package: "myclabs/php-enum"

# PHP 8.1 — Fibers
- id: php.8_1.fibers
  feature_name: "Fiber class"
  introduced: "8.1"
  detection:
    primary:
      ast_type: object_creation_expression
      match:
        class: Fiber
  fix:
    strategy: manual
    manual_instructions: "Use callbacks, generators, or ReactPHP for async"

# PHP 8.1 — Readonly properties
- id: php.8_1.readonly_property
  feature_name: "readonly properties"
  introduced: "8.1"
  detection:
    primary:
      ast_type: property_declaration
      match:
        modifiers_contains: readonly
  fix:
    strategy: rewrite_expression
    transforms:
      - type: remove_readonly_add_getter

# PHP 8.1 — Intersection types
- id: php.8_1.intersection_types
  feature_name: "intersection types (A&B)"
  introduced: "8.1"
  detection:
    primary:
      ast_type: intersection_type
  fix:
    strategy: manual
    manual_instructions: "Remove type declaration or use PHPDoc"

# PHP 8.2 — Readonly classes
- id: php.8_2.readonly_class
  feature_name: "readonly class"
  introduced: "8.2"
  detection:
    primary:
      ast_type: class_declaration
      match:
        modifiers_contains: readonly
  fix:
    strategy: rewrite_expression
    transforms:
      - type: remove_class_readonly_add_property_readonly

# PHP 8.2 — DNF types
- id: php.8_2.dnf_types
  feature_name: "DNF types ((A&B)|C)"
  introduced: "8.2"
  detection:
    primary:
      ast_type: disjunctive_normal_form_type
  fix:
    strategy: manual

# PHP 8.3 — Typed class constants
- id: php.8_3.typed_constants
  feature_name: "typed class constants"
  introduced: "8.3"
  detection:
    primary:
      ast_type: const_declaration
      match:
        has_type: true
  fix:
    strategy: rewrite_expression
    transforms:
      - type: remove_constant_type

# PHP 8.3 — Override attribute
- id: php.8_3.override_attribute
  feature_name: "#[Override] attribute"
  introduced: "8.3"
  detection:
    primary:
      ast_type: attribute
      match:
        name: Override
  fix:
    strategy: rewrite_expression
    transforms:
      - type: remove_attribute
```

---

## 3. PHP-Specific Edge Cases

### 3.1 PSR-4 autoloading
PHP resolves classes via PSR-4 namespace-to-directory mapping defined in `composer.json`. The import resolver must parse `composer.json`'s `autoload` section.

### 3.2 Composer platform requirements
`composer.json` has `require.php` field declaring the minimum PHP version. This is the version floor.

### 3.3 Extensions
PHP features may depend on extensions (e.g., Fibers need no extension, but some stdlib functions need specific extensions). Track extension requirements separately.

### 3.4 Polyfills via Symfony
Symfony provides polyfill packages for many PHP features:
- `symfony/polyfill-php80` — `str_contains`, `str_starts_with`, `str_ends_with`
- `symfony/polyfill-php81` — Various 8.1 functions

These should be recognized as backport packages.

---

## 4. Integration Points

Standard LanguageBackend. PHP-specific:
- `composer.json` parsing for autoload + version floor
- `php -l` for syntax verification
- Packagist API for dependency analysis
- PSR-4 namespace resolution for import chains
- Symfony polyfill awareness
