# Module Upgrade Service

Intelligent checklist generation + automation engine for module version upgrades and downgrades.

**Coverage:** 37 automation handlers, 74/113 steps automatable (65%), 9 languages.

## Architecture

```
module_upgrade/
├── __init__.py              ← public API: generate_checklist()
├── context.py               ← UpgradeContext builder
├── evaluator.py             ← JSON condition evaluator
├── generator.py             ← recipe loader + step materializer
├── data/
│   └── recipes/
│       ├── python.json      ← 13 upgrade + 9 downgrade steps
│       ├── node.json        ← 7 + 5
│       ├── go.json          ← 7 + 5
│       ├── rust.json        ← 7 + 5
│       ├── ruby.json        ← 6 + 5
│       ├── java.json        ← 6 + 5
│       ├── dotnet.json      ← 6 + 5
│       ├── php.json         ← 6 + 5
│       ├── elixir.json      ← 6 + 5
│       └── _common.json     ← shared tail steps
├── automation/
│   ├── __init__.py          ← handler registry (37 handlers)
│   ├── executor.py          ← step dispatcher + rescan handler
│   ├── config_editor.py     ← version config file editors (all 9 languages)
│   ├── dep_checker.py       ← dependency compatibility checkers (6 registries)
│   ├── dep_scanner.py       ← per-language dependency file parsers
│   ├── registry_clients.py  ← package registry API clients (5 registries + cache)
│   ├── code_scanner.py      ← code feature analysis + __future__ handling
│   ├── subprocess_ops.py    ← package manager command runners (7 commands)
│   └── wizard.py            ← wizard flow orchestrator (SSE streaming)
└── README.md
```

## How It Works

### Checklist Generation (Chunk 1)

1. **Context building** (`context.py`): Gathers module intelligence — floors, verdict, strategy, file presence, direction.
2. **Recipe loading** (`generator.py`): Loads JSON recipe for the module's language.
3. **Condition evaluation** (`evaluator.py`): Filters steps by structured conditions.
4. **Step materialization**: Interpolates labels (`{target}`, `{current}`, `{language}`), generates IDs.
5. **Common tail**: Test + verify steps appended if not already present.

### Automation Engine (Chunk 2)

Each step with an `automation_id` can be automated:

- **Inline preview**: Config edits, code scans, rescan — preview in plan modal, apply on confirm.
- **Wizard modal**: Dep checks, subprocess ops — opens a streaming modal with live progress.

### Three UI Paths

| Handler prefix | UI | Experience |
|----------------|-----|-----------|
| `edit_*`, `scan_*`, `remove_*`, `add_*`, `modernize_*`, `rescan_*`, `update_ci_*` | Inline preview | Show diff/findings in plan modal → Apply button |
| `check_dep_compat_*`, `update_deps_*` | Wizard (dep scan) | Stream: scan deps → query registry → show compatible/incompatible → alternatives |
| `run_*` | Wizard (subprocess) | Stream: show command → confirm → live output → success/failure |

## Automation Handlers (37 total)

### Config Editors (11 handlers)
| Handler | Language | Edits |
|---------|----------|-------|
| `edit_pyproject_requires_python` | Python | pyproject.toml requires-python |
| `edit_setup_py_python_requires` | Python | setup.py python_requires |
| `edit_setup_cfg_python_requires` | Python | setup.cfg python_requires |
| `edit_package_json_engines` | Node.js | package.json engines.node |
| `edit_go_mod_directive` | Go | go.mod go directive |
| `edit_cargo_toml_rust_version` | Rust | Cargo.toml rust-version |
| `edit_gemfile_ruby_version` | Ruby | Gemfile + .ruby-version |
| `edit_pom_java_version` | Java | pom.xml / build.gradle |
| `edit_csproj_target` | C# | .csproj TargetFramework |
| `edit_composer_php_version` | PHP | composer.json require.php |
| `edit_mix_elixir_version` | Elixir | mix.exs elixir version |

### Dep Checkers (12 handlers)
| Handler | Registry | Checks |
|---------|----------|--------|
| `check_dep_compat_pypi` | PyPI | Requires-Python |
| `check_dep_compat_npm` | npm | engines.node |
| `check_dep_compat_crates` | crates.io | rust_version (MSRV) |
| `check_dep_compat_rubygems` | RubyGems | required_ruby_version |
| `check_dep_compat_packagist` | Packagist | require.php |
| `check_dep_compat_hex` | Hex.pm | elixir requirement |
| `update_deps_interactive` | PyPI | Find compatible older versions |
| `update_deps_npm` | npm | Find compatible older versions |
| `update_deps_crates` | crates.io | Find compatible older versions |
| `update_deps_rubygems` | RubyGems | Find compatible older versions |
| `update_deps_packagist` | Packagist | Find compatible older versions |
| `update_deps_hex` | Hex.pm | Find compatible older versions |

### Code Scanners (6 handlers)
| Handler | What |
|---------|------|
| `scan_breaking_changes` | Version-specific code features (upgrade) |
| `scan_incompatible_features` | Features above target (downgrade) |
| `remove_future_annotations` | Remove __future__ imports |
| `add_future_annotations` | Add __future__ imports |
| `modernize_type_hints` | Replace typing.X with builtins |
| `update_ci_matrix` | Detect CI files + Python version refs |

### Subprocess Ops (7 handlers)
| Handler | Command |
|---------|---------|
| `run_go_mod_tidy` | `go mod tidy` |
| `run_bundle_update` | `bundle update` |
| `run_composer_update` | `composer update` |
| `run_dotnet_restore` | `dotnet restore` |
| `run_mix_deps_get` | `mix deps.get` |
| `run_cargo_check` | `cargo check` |
| `run_npm_install` | `npm install` |

### Other (1 handler)
| Handler | What |
|---------|------|
| `rescan_module` | Invalidate + recompute posture |

## Registry Clients

Cached HTTP queries (1-hour TTL in `.state/registry_cache/`):

| Function | Registry | Returns |
|----------|----------|---------|
| `query_npm(pkg)` | npmjs.org | name, version, engines_node |
| `query_crates(crate)` | crates.io | name, version, rust_version |
| `query_rubygems(gem)` | rubygems.org | name, version, required_ruby_version |
| `query_packagist(pkg)` | packagist.org | name, version, require_php |
| `query_hex(pkg)` | hex.pm | name, version, elixir_requirement |

## Dep Scanners

Per-language dependency file parsers:

| Function | Parses | Returns |
|----------|--------|---------|
| `scan_npm_deps(dir)` | package.json | Package names |
| `scan_go_deps(dir)` | go.mod | Module paths |
| `scan_rust_deps(dir)` | Cargo.toml | Crate names |
| `scan_ruby_deps(dir)` | Gemfile | Gem names |
| `scan_php_deps(dir)` | composer.json | vendor/package names |
| `scan_elixir_deps(dir)` | mix.exs | Dep atom names |

## JSON Recipe Schema

See `data/recipes/python.json` for the reference implementation.

### Condition Operators (15)

| Operator | Type | Description |
|----------|------|-------------|
| `always` | bool | Unconditional |
| `has_file` | string | File exists in module dir |
| `not_has_file` | string | File absent |
| `not_has_files` | list | ALL listed files absent |
| `floor_source_in` | list | Floor source is one of |
| `floor_source_is` | string | Floor source matches exactly |
| `has_deps_floor` | bool | Has dependency floor |
| `has_code_floor` | bool | Has code floor |
| `has_future_import` | bool | Uses __future__ annotations |
| `strategy_is` | string | Version strategy matches |
| `verdict_is` | string | Verdict matches |
| `target_gte` | string | Target >= value |
| `target_lt` | string | Target < value |
| `current_gte` | string | Current >= value |
| `current_lt` | string | Current < value |

## Adding a New Language

1. Create `data/recipes/{language}.json`
2. Map in `generator.py` `_LANGUAGE_TO_RECIPE`
3. Add config editor handler in `config_editor.py`
4. Add dep scanner in `dep_scanner.py` (if parseable dep file exists)
5. Add registry client in `registry_clients.py` (if public API exists)
6. Add dep checker handlers in `dep_checker.py`
7. Add subprocess handler in `subprocess_ops.py` (if package manager exists)
8. Register all in `automation/__init__.py`
