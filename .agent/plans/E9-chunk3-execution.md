# E9 Chunk 3 — Execution Plan: All Languages

> Extend recipes + automation handlers to all 8 remaining languages.
> Depends on: Chunk 1 + 2 complete.
> Design constraint: ZERO changes to generator.py, evaluator.py, context.py.

---

## Execution Order

Node → Go → Rust → Ruby → Java → C#/dotnet → PHP → Elixir

Node/Go/Rust first (most overlap with Python patterns), then the rest.

## Per Language: What Gets Created

Each language needs:
1. **Recipe JSON** — `data/recipes/{lang}.json` with upgrade + downgrade steps
2. **Config editor handler** — edit the language's version config file
3. **Registry entry** — add handler to `automation/__init__.py`

Dep compatibility checking and CI matrix scanning are language-agnostic
(already implemented). Code scanning is Python-only for now — other languages
get manual code audit steps.

## Steps

### Step 1: Node.js recipe + handler
- Recipe: `node.json` — edit package.json engines.node, check deps, CI, test, verify
- Handler: `edit_package_json_engines` in config_editor.py
- Condition operators needed: `has_file: "package.json"` (already exists)

### Step 2: Go recipe + handler
- Recipe: `go.json` — edit go.mod go directive, check deps, CI, test, verify
- Handler: `edit_go_mod_directive` in config_editor.py

### Step 3: Rust recipe + handler
- Recipe: `rust.json` — edit Cargo.toml rust-version, check deps, CI, test, verify
- Handler: `edit_cargo_toml_rust_version` in config_editor.py

### Step 4: Ruby recipe + handler
- Recipe: `ruby.json` — edit Gemfile ruby version + .ruby-version, CI, test, verify
- Handler: `edit_gemfile_ruby_version` in config_editor.py

### Step 5: Java recipe + handler
- Recipe: `java.json` — edit pom.xml/build.gradle source/target, CI, test, verify
- Handler: `edit_pom_java_version` in config_editor.py

### Step 6: C# recipe + handler
- Recipe: `dotnet.json` — edit .csproj TargetFramework, CI, test, verify
- Handler: `edit_csproj_target` in config_editor.py

### Step 7: PHP recipe + handler
- Recipe: `php.json` — edit composer.json require.php, CI, test, verify
- Handler: `edit_composer_php_version` in config_editor.py

### Step 8: Elixir recipe + handler
- Recipe: `elixir.json` — edit mix.exs elixir version, CI, test, verify
- Handler: `edit_mix_elixir_version` in config_editor.py

### Step 9: Update registry
- Add all 8 new handlers to `automation/__init__.py`

### Step 10: Validate
- Verify all recipe JSON files parse correctly
- Verify all handlers import and register
- Verify generator constraint: zero changes to generator/evaluator/context
