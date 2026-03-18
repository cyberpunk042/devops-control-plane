# E9 Chunk 3 — Automation Engine (All Languages)

> Extend recipes and automation handlers to all supported languages.
> Depends on: Chunk 2 (Python automation) complete and validated.
> Architecture: `.agent/docs/E9-checklist-automation-architecture.md`
> Status: SCAFFOLD — future work

---

## What This Chunk Delivers

Every language in module_lifecycle.json gets:
1. A recipe JSON file (checklist generation — extends Chunk 1)
2. Automation handlers where applicable (extends Chunk 2)

---

## Languages to Cover

From `module_lifecycle.json` (8 languages):

| Language | Config File(s) | Package Manager | Lifecycle Key |
|----------|----------------|-----------------|---------------|
| Python | pyproject.toml, setup.py, setup.cfg | pip/PyPI | python |
| Node.js | package.json | npm/npmjs | node |
| Go | go.mod | go modules | go |
| Rust | Cargo.toml | cargo/crates.io | rust |
| Ruby | Gemfile, .ruby-version | gem/RubyGems | ruby |
| Java | pom.xml, build.gradle | maven/gradle | java |
| C# | *.csproj | NuGet | dotnet |
| PHP | composer.json | composer/Packagist | php |
| Elixir | mix.exs | hex | elixir |

---

## Per-Language Work

### Recipe JSON Files to Create

| File | Key Steps |
|------|-----------|
| `data/recipes/node.json` | Edit package.json engines.node, check npm dep compat, audit for ESM/CJS issues |
| `data/recipes/go.json` | Edit go.mod go directive, check go.sum deps, scan for deprecated API usage |
| `data/recipes/rust.json` | Edit Cargo.toml rust-version, check crate MSRV, scan for edition-gated features |
| `data/recipes/ruby.json` | Edit Gemfile ruby version, edit .ruby-version, check gem compatibility |
| `data/recipes/java.json` | Edit pom.xml/build.gradle source/target, check dependency Java version support |
| `data/recipes/dotnet.json` | Edit .csproj TargetFramework, check NuGet package compat |
| `data/recipes/php.json` | Edit composer.json require.php, check Packagist compat |
| `data/recipes/elixir.json` | Edit mix.exs elixir version, check hex package compat |

### Automation Handlers to Add

| Handler | Languages | What it does |
|---------|-----------|-------------|
| `edit_package_json_engines` | node | Edit engines.node in package.json |
| `edit_go_mod_directive` | go | Edit go directive in go.mod |
| `edit_cargo_toml_rust_version` | rust | Edit rust-version in Cargo.toml |
| `edit_gemfile_ruby_version` | ruby | Edit ruby version in Gemfile + .ruby-version |
| `edit_pom_java_version` | java | Edit source/target in pom.xml |
| `edit_csproj_target` | dotnet | Edit TargetFramework in .csproj |
| `edit_composer_php_version` | php | Edit require.php in composer.json |
| `edit_mix_elixir_version` | elixir | Edit elixir version in mix.exs |
| `check_dep_compat_npm` | node | Query npmjs for engine requirements |
| `check_dep_compat_crates` | rust | Query crates.io for MSRV |
| `check_dep_compat_rubygems` | ruby | Query RubyGems for ruby version |
| `check_dep_compat_maven` | java | Check Maven Central metadata |
| `check_dep_compat_nuget` | dotnet | Check NuGet package metadata |
| `check_dep_compat_packagist` | php | Query Packagist for PHP version |
| `check_dep_compat_hex` | elixir | Query Hex for elixir version |

### Condition Operators to Potentially Add

Depending on language-specific needs, new condition operators may be required:
- `has_file_in_root` — file exists in project root (not module dir)
- `stack_is` — exact stack match (e.g., "python-django" vs "python")
- `has_lockfile` — package-lock.json, go.sum, Cargo.lock, etc.

These are additive — one elif branch in evaluator.py per operator.

---

## Execution Strategy

1. Start with languages that have the most overlap with Python patterns (Node, Go, Rust)
2. Each language is independent — can be added one at a time
3. Each language = 1 recipe JSON + 1-2 automation handler functions
4. Test each language's recipe by creating a plan for a module with that stack
5. No changes to generator.py, evaluator.py, or context.py needed (by design)

---

## Files Summary

| Action | File | Per Language |
|--------|------|-------------|
| CREATE | `data/recipes/{language}.json` | ~120-160 lines each |
| EDIT | `automation/config_editor.py` | +1 handler function (~30 lines) |
| EDIT | `automation/dep_checker.py` | +1 handler function (~40 lines) |

**Total per language:** ~200 lines recipe + ~70 lines automation
**Total for all 8 remaining:** ~2,160 lines

---

## Design Constraint

Zero changes to the generator, evaluator, or context builder.
Adding a language = adding data (JSON) + adding handlers (Python functions).
If this constraint is violated, the architecture is wrong and needs fixing before proceeding.
