# 20 — JavaScript/TypeScript Language Module

> **Document**: 20 of 37
> **Milestone**: M9 — Language modules & edge cases
> **Status**: Draft

---

## 1. Overview

JavaScript and TypeScript share a module because:
- TypeScript is a superset of JavaScript
- They share the same runtime (Node.js / browser)
- ES version features apply to both
- TypeScript adds its own version-specific features on top

**JS versions covered**: ES2015 (ES6) through ES2024
**TS versions covered**: TypeScript 4.0 through 5.5+
**Node.js versions covered**: 14, 16, 18, 20, 22
**Feature entries target**: 250+
**Parser**: tree-sitter-javascript / tree-sitter-typescript
**Import resolver**: Follow `import`/`require`/`export from`
**Package registry**: npm
**Formatter**: prettier (optional post-transform)

---

## 2. AST Backend

### 2.1 Parser

Uses tree-sitter for both JS and TS. Tree-sitter produces a concrete syntax tree that preserves all tokens including comments and whitespace.

```python
class JavaScriptBackend(LanguageBackend):
    def __init__(self):
        self._parser = tree_sitter.Parser()
        self._parser.set_language(tree_sitter_javascript.language())

class TypeScriptBackend(JavaScriptBackend):
    def __init__(self):
        self._parser = tree_sitter.Parser()
        self._parser.set_language(tree_sitter_typescript.language())
```

### 2.2 Version spaces

JavaScript has TWO version spaces:
1. **ECMAScript version** (ES2015–ES2024): Language syntax and builtins
2. **Node.js version** (14, 16, 18, 20, 22): Runtime APIs and behavior

A feature might be ES2020 (syntax) but only available in Node.js 14+ (runtime).

TypeScript adds a third:
3. **TypeScript version** (4.0–5.5): TS-specific syntax and type system features

---

## 3. Feature Database — ES2015 (ES6)

The big one. ES6 introduced most of modern JavaScript:

```yaml
- id: js.es2015.arrow_function
  feature_name: "arrow function (=>)"
  introduced: "ES2015"
  category: es2015
  detection:
    primary:
      ast_type: arrow_function
  fix:
    strategy: rewrite_expression
    transforms:
      - type: rewrite_arrow_to_function
  severity: error

- id: js.es2015.template_literal
  feature_name: "template literal (`${}`)"
  introduced: "ES2015"
  detection:
    primary:
      ast_type: template_string
  fix:
    strategy: rewrite_expression
    transforms:
      - type: rewrite_template_to_concat

- id: js.es2015.destructuring
  feature_name: "destructuring assignment"
  introduced: "ES2015"
  detection:
    primary:
      ast_type: object_pattern
    alternatives:
      - ast_type: array_pattern
  fix:
    strategy: manual
    manual_instructions: "Replace with individual property access"

- id: js.es2015.class_declaration
  feature_name: "class declaration"
  introduced: "ES2015"
  detection:
    primary:
      ast_type: class_declaration
  fix:
    strategy: manual
    manual_instructions: "Rewrite as constructor function with prototype"

- id: js.es2015.let_const
  feature_name: "let/const declarations"
  introduced: "ES2015"
  detection:
    primary:
      ast_type: lexical_declaration
  fix:
    strategy: rewrite_expression
    transforms:
      - type: replace_let_const_with_var

- id: js.es2015.promise
  feature_name: "Promise"
  introduced: "ES2015"
  detection:
    primary:
      ast_type: new_expression
      match:
        constructor: Promise
  fix:
    strategy: add_backport_import
    backport:
      package: es6-promise

- id: js.es2015.spread
  feature_name: "spread operator (...)"
  introduced: "ES2015"
  detection:
    primary:
      ast_type: spread_element
  fix:
    strategy: rewrite_expression
    transforms:
      - type: rewrite_spread
        replace:
          array_spread: "Array.prototype.concat.apply([], {args})"
          object_spread: "Object.assign({}, {args})"

- id: js.es2015.for_of
  feature_name: "for...of loop"
  introduced: "ES2015"
  detection:
    primary:
      ast_type: for_in_statement
      match:
        kind: of
  fix:
    strategy: rewrite_expression
    transforms:
      - type: rewrite_for_of_to_for_i

- id: js.es2015.default_params
  feature_name: "default parameter values"
  introduced: "ES2015"
  detection:
    primary:
      ast_type: assignment_pattern
      context: function_params
  fix:
    strategy: rewrite_expression
    transforms:
      - type: add_default_check_in_body
```

---

## 4. Feature Database — ES2016–ES2024

```yaml
# ES2016
- id: js.es2016.array_includes
  feature_name: "Array.prototype.includes()"
  introduced: "ES2016"
  detection:
    primary:
      ast_type: call_expression
      match:
        method: includes
        receiver_type: array
  fix:
    strategy: rewrite_expression
    transforms:
      - type: rewrite_method_call
        replace:
          template: "{receiver}.indexOf({arg}) !== -1"

- id: js.es2016.exponentiation
  feature_name: "exponentiation operator (**)"
  introduced: "ES2016"
  detection:
    primary:
      ast_type: binary_expression
      match:
        operator: "**"
  fix:
    strategy: rewrite_expression
    transforms:
      - type: rewrite_binary_op
        replace:
          template: "Math.pow({left}, {right})"

# ES2017
- id: js.es2017.async_await
  feature_name: "async/await"
  introduced: "ES2017"
  detection:
    primary:
      ast_type: async_function
    alternatives:
      - ast_type: await_expression
  fix:
    strategy: manual
    manual_instructions: "Rewrite as Promise.then() chains"

- id: js.es2017.object_entries
  feature_name: "Object.entries()"
  introduced: "ES2017"
  detection:
    primary:
      ast_type: call_expression
      match:
        object: Object
        method: entries

# ES2018
- id: js.es2018.rest_spread_object
  feature_name: "object rest/spread ({...obj})"
  introduced: "ES2018"
  detection:
    primary:
      ast_type: spread_element
      context: object

- id: js.es2018.async_iteration
  feature_name: "for await...of"
  introduced: "ES2018"
  detection:
    primary:
      ast_type: for_in_statement
      match:
        await: true

# ES2019
- id: js.es2019.optional_catch_binding
  feature_name: "optional catch binding"
  introduced: "ES2019"
  detection:
    primary:
      ast_type: catch_clause
      match:
        parameter: null

- id: js.es2019.flat_flatmap
  feature_name: "Array.prototype.flat/flatMap"
  introduced: "ES2019"
  detection:
    primary:
      ast_type: call_expression
      match:
        method_in: [flat, flatMap]

# ES2020
- id: js.es2020.optional_chaining
  feature_name: "optional chaining (?.)"
  introduced: "ES2020"
  detection:
    primary:
      ast_type: optional_chain_expression
    alternatives:
      - ast_type: member_expression
        match:
          optional: true
  fix:
    strategy: rewrite_expression
    transforms:
      - type: rewrite_optional_chain
        replace:
          template: "{base} && {base}.{property}"
  edge_cases:
    - id: deep_chain
      description: "a?.b?.c?.d requires nested && checks"
    - id: method_call
      description: "a?.b() requires typeof check"

- id: js.es2020.nullish_coalescing
  feature_name: "nullish coalescing (??)"
  introduced: "ES2020"
  detection:
    primary:
      ast_type: binary_expression
      match:
        operator: "??"
  fix:
    strategy: rewrite_expression
    transforms:
      - type: rewrite_binary_op
        replace:
          template: "({left} !== null && {left} !== undefined) ? {left} : {right}"

- id: js.es2020.bigint
  feature_name: "BigInt"
  introduced: "ES2020"
  detection:
    primary:
      ast_type: bigint
  fix:
    strategy: manual
    manual_instructions: "No polyfill for BigInt literal syntax. Use a BigInt library."

- id: js.es2020.globalthis
  feature_name: "globalThis"
  introduced: "ES2020"
  detection:
    primary:
      ast_type: identifier
      match:
        name: globalThis
  fix:
    strategy: rewrite_expression
    transforms:
      - type: replace_identifier
        replace:
          expression: "(typeof globalThis !== 'undefined' ? globalThis : typeof window !== 'undefined' ? window : global)"

# ES2021
- id: js.es2021.logical_assignment
  feature_name: "logical assignment (&&=, ||=, ??=)"
  introduced: "ES2021"
  detection:
    primary:
      ast_type: assignment_expression
      match:
        operator_in: ["&&=", "||=", "??="]
  fix:
    strategy: rewrite_expression
    transforms:
      - type: rewrite_logical_assignment

- id: js.es2021.replaceall
  feature_name: "String.prototype.replaceAll()"
  introduced: "ES2021"
  detection:
    primary:
      ast_type: call_expression
      match:
        method: replaceAll
  fix:
    strategy: rewrite_expression
    transforms:
      - type: rewrite_method_call
        replace:
          template: "{receiver}.replace(new RegExp({arg}, 'g'), {arg2})"

# ES2022
- id: js.es2022.top_level_await
  feature_name: "top-level await"
  introduced: "ES2022"
  detection:
    primary:
      ast_type: await_expression
      context: module_level
  fix:
    strategy: manual
    manual_instructions: "Wrap in async IIFE: (async () => { await ... })()"

- id: js.es2022.array_at
  feature_name: "Array.prototype.at()"
  introduced: "ES2022"
  detection:
    primary:
      ast_type: call_expression
      match:
        method: at
  fix:
    strategy: rewrite_expression
    transforms:
      - type: rewrite_method_call
        replace:
          template: "{receiver}[{arg} < 0 ? {receiver}.length + {arg} : {arg}]"

- id: js.es2022.class_fields
  feature_name: "class public/private fields"
  introduced: "ES2022"
  detection:
    primary:
      ast_type: field_definition
    alternatives:
      - ast_type: private_property_identifier
  fix:
    strategy: manual
    manual_instructions: "Move field declarations into constructor"

- id: js.es2022.error_cause
  feature_name: "Error cause (new Error('msg', {cause}))"
  introduced: "ES2022"
  detection:
    primary:
      ast_type: new_expression
      match:
        constructor: Error
        has_options_arg: true

# ES2023
- id: js.es2023.findlast
  feature_name: "Array.prototype.findLast/findLastIndex"
  introduced: "ES2023"
  detection:
    primary:
      ast_type: call_expression
      match:
        method_in: [findLast, findLastIndex]
  fix:
    strategy: rewrite_expression
    manual_instructions: "Use reverse + find, or a loop"

# ES2024
- id: js.es2024.object_groupby
  feature_name: "Object.groupBy()"
  introduced: "ES2024"
  detection:
    primary:
      ast_type: call_expression
      match:
        object: Object
        method: groupBy
  fix:
    strategy: rewrite_expression
    manual_instructions: "Use reduce() to group manually"

- id: js.es2024.promise_withresolvers
  feature_name: "Promise.withResolvers()"
  introduced: "ES2024"
  detection:
    primary:
      ast_type: call_expression
      match:
        object: Promise
        method: withResolvers
  fix:
    strategy: rewrite_expression
    transforms:
      - type: rewrite_promise_withresolvers
```

---

## 5. TypeScript-Specific Features

```yaml
# TS 4.9 — satisfies operator
- id: ts.4_9.satisfies
  language: typescript
  feature_name: "satisfies operator"
  introduced: "4.9"
  category: ts4
  detection:
    primary:
      ast_type: satisfies_expression
  fix:
    strategy: rewrite_expression
    transforms:
      - type: remove_satisfies
        replace:
          template: "{expression} as {type}"

# TS 5.0 — const type parameters
- id: ts.5_0.const_type_param
  language: typescript
  feature_name: "const type parameters"
  introduced: "5.0"
  detection:
    primary:
      ast_type: type_parameter
      match:
        const: true
  fix:
    strategy: manual
    manual_instructions: "Remove const modifier, use 'as const' at call site"

# TS 5.0 — decorators (stage 3)
- id: ts.5_0.decorators_stage3
  language: typescript
  feature_name: "Stage 3 decorators"
  introduced: "5.0"
  detection:
    primary:
      ast_type: decorator
  fix:
    strategy: manual
    manual_instructions: "Use experimental decorators (enable experimentalDecorators in tsconfig)"
```

---

## 6. Node.js Runtime Features

```yaml
# Node.js 18+ — fetch API
- id: node.18.fetch
  language: javascript
  feature_name: "global fetch()"
  introduced: "18"
  category: node_api
  detection:
    primary:
      ast_type: call_expression
      match:
        function: fetch
      context: not_imported  # Only match if fetch is used as a global, not imported
  fix:
    strategy: add_backport_import
    backport:
      package: node-fetch
      import_statement: "const fetch = require('node-fetch')"

# Node.js 20+ — import.meta.resolve
- id: node.20.import_meta_resolve
  language: javascript
  feature_name: "import.meta.resolve()"
  introduced: "20"
  detection:
    primary:
      ast_type: call_expression
      match:
        object: "import.meta"
        method: resolve
  fix:
    strategy: manual
    manual_instructions: "Use require.resolve() or a custom resolver"
```

---

## 7. JS/TS-Specific Edge Cases

### 7.1 Transpiler configuration

Many JS/TS projects use Babel or TypeScript compiler to downlevel syntax. The compat system should detect if a transpiler is configured:

```
If babel.config.js or .babelrc exists:
  Check which presets/plugins are configured
  If @babel/preset-env with targets → features may already be transpiled
  Adjust findings accordingly
```

### 7.2 Polyfill bundles

Projects using `core-js` or `@babel/polyfill` may have runtime polyfills that make API features available even on older engines. Detect:
```
If package.json includes core-js → runtime APIs may be polyfilled
Flag findings as "possibly polyfilled" rather than "error"
```

### 7.3 Browser vs Node.js

Features may be available in browsers but not Node.js or vice versa:
- `fetch`: Available in browsers since forever, Node.js 18+
- `require()`: Node.js only, not browsers
- `import.meta`: Different behavior in browsers vs Node.js

The target version must specify the RUNTIME, not just the language version.

### 7.4 ESM vs CommonJS

Import style affects what features are available:
- `import/export`: ESM (modern)
- `require/module.exports`: CommonJS (legacy)
- Top-level `await` only works in ESM

The import resolver must handle both styles.

### 7.5 tsconfig.json target

TypeScript's `compilerOptions.target` already handles downleveling. If set to `ES2018`, TS will transpile ES2020+ features. The compat system should read tsconfig and adjust:
- If TS target handles the downlevel → don't flag those features
- If TS target is higher than the deployment target → flag the gap

---

## 8. Integration Points

Same as Python module — implements LanguageBackend interface, provides entries to the feature database, integrates with import resolver and fix engine.

Key differences from Python:
- Two parsers (JS + TS)
- Three version spaces (ES, Node.js, TS)
- Transpiler awareness (Babel, TS compiler)
- Polyfill awareness (core-js)
- ESM/CommonJS duality
