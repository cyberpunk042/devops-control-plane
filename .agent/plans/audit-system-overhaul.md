# Audit System Overhaul — Master Plan

> **Status**: Planning  
> **Created**: 2026-03-04  
> **Scope**: Mastodon — 8 phases, each with sub-phases  
> **Goal**: Transform the audit system from a Python-only code scanner into a
> universal, multi-language, multi-stack intelligent code analysis engine that
> supports every stack and language the DevOps control plane manages.

---

## The Problem

The current audit system is **hardcoded to Python**:

- `parsers/python_parser.py` is the **only** file parser — uses Python `ast.parse()`
- `parse_tree()` does `rglob("*.py")` — only Python files are ever seen
- Quality scoring uses 5 Python-specific dimensions: `docstrings`, `function_length`,
  `nesting`, `comments`, `type_hints`
- Structure analysis only builds import graphs from Python `import` statements
- Hotspot detection assumes Python function metrics
- The `FileAnalysis` model is shaped around Python AST concepts

This means:
- **HTML templates** (130 Jinja2 files in `src/ui/web/templates/`) — invisible
- **JavaScript** (25,000+ `.js` files in docs/node_modules but also real app JS) — invisible
- **TypeScript** (6,800+ `.ts` files) — invisible
- **CSS** (240 `.css` files) — invisible
- **YAML/HCL/Dockerfile** config — invisible
- **Go, Rust, Ruby, Java, C#, PHP, Elixir, Swift, C, C++, Zig, Lua, Haskell, OCaml, R** — all invisible

And this program **manages projects in ALL of these stacks**. It has 47 stack
definitions across 22 root stacks and 25 child stacks, plus 15 language recipe
families (7 of which have recipes but no corresponding stack definition yet).

---

## Complete Language & File Type Inventory

### Source Languages (the program manages projects in ALL of these)

| # | Language | Extensions | Import System | Quality Concerns |
|---|----------|-----------|---------------|-----------------|
| 1 | **Python** | `.py`, `.pyw`, `.pyi` | `import X`, `from X import Y` | docstrings, type hints, nesting, function length, naming |
| 2 | **JavaScript** | `.js`, `.mjs`, `.cjs`, `.jsx` | `import`, `require()` | function complexity, callback depth, var/let/const, JSDoc |
| 3 | **TypeScript** | `.ts`, `.tsx`, `.mts`, `.cts` | `import`, `require()` | type coverage, interface design, generics complexity |
| 4 | **Go** | `.go` | `import "pkg"` | exported vs unexported, error handling, goroutine patterns |
| 5 | **Rust** | `.rs` | `use crate::`, `use std::`, `mod` | unsafe blocks, lifetime complexity, ownership patterns |
| 6 | **Java** | `.java` | `import pkg.Class` | visibility, exception handling, class hierarchy depth |
| 7 | **Kotlin** | `.kt`, `.kts` | `import pkg.Class` | null safety, coroutine usage, data class appropriateness |
| 8 | **Scala** | `.scala`, `.sc` | `import pkg._` | implicit complexity, monad usage, pattern matching |
| 9 | **C#** | `.cs` | `using Namespace` | async/await, LINQ complexity, dependency injection |
| 10 | **Ruby** | `.rb`, `.rake` | `require`, `require_relative` | method length, module mixing, metaprogramming |
| 11 | **PHP** | `.php` | `use`, `require_once`, `include` | type declarations, namespace usage, SQL injection vectors |
| 12 | **Elixir** | `.ex`, `.exs` | `import`, `alias`, `use` | pattern match complexity, process supervision, macro usage |
| 13 | **Swift** | `.swift` | `import Module` | optional handling, protocol conformance, access control |
| 14 | **C** | `.c`, `.h` | `#include` | memory management, buffer safety, preprocessor complexity |
| 15 | **C++** | `.cpp`, `.hpp`, `.cc`, `.hh`, `.cxx`, `.hxx` | `#include`, `using namespace` | RAII, template complexity, smart pointer usage |
| 16 | **Zig** | `.zig` | `@import()` | comptime usage, error handling, allocator patterns |
| 17 | **Lua** | `.lua` | `require()` | table structure, metatable patterns, global pollution |
| 18 | **Haskell** | `.hs`, `.lhs` | `import` | monad stacking, type class instances, partial functions |
| 19 | **OCaml** | `.ml`, `.mli` | `open Module` | functor complexity, pattern exhaustiveness |
| 20 | **R** | `.R`, `.r`, `.Rmd` | `library()`, `require()` | vectorization, for-loop antipatterns |
| 21 | **Protobuf** | `.proto` | `import` | field numbering, backward compat, service definitions |

### Template Engines & Pseudo-Languages

| # | Type | Extensions | Host Stack | What's Inside | Audit Challenge |
|---|------|-----------|-----------|--------------|-----------------|
| 22 | **Jinja2** | `.html`, `.j2`, `.jinja`, `.jinja2` | Python (Flask/Django) | HTML + `{{ }}` + `{% %}` + embedded raw JS + CSS | Mixed content: template logic + HTML structure + JS behavior |
| 23 | **ERB** | `.erb`, `.html.erb` | Ruby (Rails) | HTML + `<%= %>` + `<% %>` | Ruby expressions inside HTML |
| 24 | **EEx/HEEx** | `.eex`, `.heex`, `.leex` | Elixir (Phoenix) | HTML + `<%= %>` + `~H""" """` | Elixir + HTML LiveView components |
| 25 | **Go Templates** | `.tmpl`, `.gohtml` | Go, Helm | `{{ .Values.x }}`, `{{ range }}` | Logic in YAML (Helm) or HTML (Go web) |
| 26 | **Blade** | `.blade.php` | PHP (Laravel) | `@section`, `@yield`, `@foreach` | PHP directive syntax in HTML |
| 27 | **Razor** | `.cshtml`, `.razor` | C# (ASP.NET, Blazor) | `@model`, `@foreach`, `@code {}` | C# expressions in HTML |
| 28 | **JSX** | `.jsx` | React | HTML-in-JS | Component structure, prop patterns |
| 29 | **TSX** | `.tsx` | React + TypeScript | HTML-in-TS | Type-safe component patterns |
| 30 | **Pug/Jade** | `.pug`, `.jade` | Node.js | Indentation-based HTML | Nesting depth, mixin reuse |
| 31 | **Handlebars/Mustache** | `.hbs`, `.handlebars`, `.mustache` | Node.js/Ruby | `{{variable}}`, `{{#each}}` | Logic-less template evaluation |
| 32 | **EJS** | `.ejs` | Node.js | `<%= %>`, `<% %>` | JS inside HTML |
| 33 | **Twig** | `.twig` | PHP (Symfony) | `{{ }}`, `{% %}` (Jinja-like) | Similar to Jinja2 patterns |
| 34 | **Slim** | `.slim` | Ruby | Indentation-based HTML | Like Pug but Ruby |
| 35 | **HAML** | `.haml` | Ruby | `%tag`, `= expression` | Ruby-in-HTML shorthand |
| 36 | **Svelte** | `.svelte` | JavaScript | HTML + `<script>` + `<style>` | Component structure, reactivity patterns |
| 37 | **Vue SFC** | `.vue` | JavaScript/TypeScript | `<template>` + `<script>` + `<style>` | Three-section component files |
| 38 | **MDX** | `.mdx` | React | Markdown + JSX components | Documentation + interactive components |

### Configuration & Infrastructure Languages

| # | Type | Extensions | Audit Concern |
|---|------|-----------|--------------|
| 39 | **YAML** | `.yml`, `.yaml` | Structure validity, nesting depth, anchor/alias usage |
| 40 | **JSON** | `.json` | Schema conformance, nesting depth, size |
| 41 | **TOML** | `.toml` | Section organization, key naming |
| 42 | **HCL (Terraform)** | `.tf`, `.tfvars` | Resource structure, variable usage, module composition |
| 43 | **Dockerfile** | `Dockerfile`, `Dockerfile.*` | Layer optimization, base image, security (no root) |
| 44 | **Docker Compose** | `docker-compose.yml`, `compose.yml` | Service structure, volume mounts, network config |
| 45 | **Kubernetes manifests** | `.yaml` (with `apiVersion:`) | Resource limits, labels, security context |
| 46 | **Helm templates** | `.yaml` inside `templates/` | Value references, helper usage, notes.txt |
| 47 | **GitHub Actions** | `.yml` inside `.github/workflows/` | Step structure, secret usage, action versions |
| 48 | **Makefile** | `Makefile`, `*.mk` | Target structure, phony declarations |
| 49 | **Shell scripts** | `.sh`, `.bash`, `.zsh` | Error handling (set -e), quoting, portability |
| 50 | **SQL** | `.sql` | Injection patterns, migration structure |
| 51 | **GraphQL** | `.graphql`, `.gql` | Schema design, complexity |
| 52 | **CSS** | `.css` | Specificity, unused selectors, responsive patterns |
| 53 | **SCSS/SASS** | `.scss`, `.sass` | Nesting depth, mixin reuse, variable naming |
| 54 | **Less** | `.less` | Similar to SCSS |
| 55 | **Markdown** | `.md` | Heading hierarchy, link validity, code block language tags |

### Project-Specific Template Reality (THIS project)

The `src/ui/web/templates/` directory uses a specific pattern that the audit MUST understand:

- `scripts/*.html` files are **NOT HTML** — they are **raw JavaScript** inside a shared
  `<script>` block (opened by `_globals.html`, closed by `_boot.html`). Adding `<script>`
  tags inside them would cause a syntax error.
- `partials/*.html` files are **Jinja2 HTML fragments** — actual HTML with template directives.
- `*.html` at root are **Jinja2 full pages** — extend base templates, use blocks.
- This distinction between "HTML file that contains JS" vs "HTML file that contains HTML"
  is exactly the kind of intelligence the audit needs.

---

## Complete Stack Taxonomy (from `stacks/*/stack.yml`)

This is the authoritative list of every stack the control plane knows about.
Every one of these must be auditable.

### Root Stacks (22 — no parent)

| Stack | Domain | Language | Detection Files | Description |
|-------|--------|----------|----------------|-------------|
| `python` | service | python | `pyproject.toml`, `setup.py`, `setup.cfg`, `requirements.txt`, `Pipfile` | Python project (generic) |
| `node` | service | javascript | `package.json` | Node.js project |
| `typescript` | service | typescript | `tsconfig.json` + `package.json` (both required) | TypeScript project |
| `go` | service | go | `go.mod` | Go project |
| `rust` | service | rust | `Cargo.toml` | Rust project |
| `ruby` | service | ruby | `Gemfile`, `Rakefile` | Ruby project |
| `java-maven` | service | java | `pom.xml` (required) | Java project (Maven) |
| `java-gradle` | service | java | `build.gradle`, `build.gradle.kts` | Java/Kotlin project (Gradle) |
| `dotnet` | service | csharp | `Directory.Build.props`, `global.json`, `nuget.config` | .NET / C# project |
| `php` | service | php | `composer.json` | PHP project (Composer) |
| `elixir` | service | elixir | `mix.exs` | Elixir project (Mix) |
| `swift` | service | swift | `Package.swift` | Swift project (SPM) |
| `c` | service | c | `CMakeLists.txt`, `Makefile`, `configure.ac`, `meson.build` | C project (Make/CMake) |
| `cpp` | service | cpp | `CMakeLists.txt`, `Makefile`, `meson.build` + content `CXX` in CMakeLists.txt | C++ project (CMake/Make) |
| `zig` | service | zig | `build.zig`, `build.zig.zon` | Zig project |
| `protobuf` | service | protobuf | `buf.yaml`, `buf.gen.yaml`, `buf.work.yaml` | Protocol Buffers / gRPC |
| `terraform` | ops | hcl | `main.tf`, `terraform.tf`, `versions.tf` | Terraform infrastructure |
| `kubernetes` | ops | yaml | `kustomization.yaml`, `kustomization.yml`, `skaffold.yaml` | Kubernetes manifests |
| `helm` | ops | yaml | `Chart.yaml` (required) | Helm chart |
| `docker-compose` | ops | — | `docker-compose.yml`, `docker-compose.yaml`, `compose.yml`, `compose.yaml` | Docker Compose project |
| `static-site` | docs | html | `index.html` (required) | Static site (HTML/CSS/JS) |
| `markdown` | docs | — | `mkdocs.yml`, `docusaurus.config.js`, `docusaurus.config.ts` | Documentation (Markdown) |

### Child Stacks (25 — inherit from parent)

| Stack | Parent | Domain | Framework | Template Engine | Extra Detection |
|-------|--------|--------|-----------|----------------|----------------|
| `python-lib` | python | library | — | — | no entry point |
| `python-cli` | python | service | Click/argparse | — | content detection |
| `python-flask` | python | service | Flask | **Jinja2** | `flask` in pyproject.toml |
| `python-django` | python | service | Django | **Django Templates** (Jinja2-like) | `manage.py` |
| `python-fastapi` | python | service | FastAPI | — | `fastapi` in pyproject.toml |
| `node-lib` | node | library | — | — | `prepublish` script |
| `node-express` | node | service | Express.js | **EJS**, **Pug**, **Handlebars** (varies) | `express` in package.json |
| `node-nextjs` | node | service | Next.js | **JSX/TSX** | `next.config.*` |
| `node-react` | node | service | React | **JSX/TSX** | content detection |
| `typescript-lib` | typescript | library | — | — | `prepublish` script |
| `go-lib` | go | library | — | — | no main package |
| `go-cli` | go | service | Cobra/urfave | — | content detection |
| `go-gin` | go | service | Gin | **Go Templates** | `gin-gonic` in go.mod |
| `go-fiber` | go | service | Fiber | **Go Templates** | content detection |
| `rust-lib` | rust | library | — | — | lib.rs |
| `rust-cli` | rust | service | clap | — | content detection |
| `rust-axum` | rust | service | Axum | — | `axum` in Cargo.toml |
| `rust-actix` | rust | service | Actix-web | — | `actix` in Cargo.toml |
| `ruby-rails` | ruby | service | Rails | **ERB**, **HAML**, **Slim** | `config/routes.rb` |
| `ruby-sinatra` | ruby | service | Sinatra | **ERB** | `sinatra` in Gemfile |
| `java-maven-spring` | java-maven | service | Spring Boot | **Thymeleaf**, **JSP** | `spring-boot` in pom.xml |
| `java-gradle-spring` | java-gradle | service | Spring Boot | **Thymeleaf**, **JSP** | `spring-boot` in build.gradle |
| `dotnet-aspnet` | dotnet | service | ASP.NET | **Razor** (`.cshtml`) | dotnet watch |
| `dotnet-blazor` | dotnet | service | Blazor | **Razor** (`.razor`) | Blazor serve |
| `elixir-phoenix` | elixir | service | Phoenix | **HEEx** (`.heex`) | `phoenix` in mix.exs |

### Stack → Template Engine Map (for audit intelligence)

When auditing a module with a known stack, the audit can predict what template
engines are in use and apply the correct parser:

| Stack | Expected Template Engine | Expected Template Dirs | Template Extensions |
|-------|-------------------------|----------------------|--------------------|
| `python-flask` | Jinja2 | `templates/` | `.html`, `.j2`, `.jinja2` |
| `python-django` | Django Templates | `templates/` | `.html` |
| `node-express` | EJS/Pug/Handlebars | `views/` | `.ejs`, `.pug`, `.hbs` |
| `node-nextjs` | JSX/TSX | `pages/`, `app/` | `.jsx`, `.tsx` |
| `node-react` | JSX/TSX | `src/` | `.jsx`, `.tsx` |
| `go-gin` / `go-fiber` | Go Templates | `templates/`, `views/` | `.tmpl`, `.gohtml`, `.html` |
| `ruby-rails` | ERB | `app/views/` | `.html.erb`, `.erb` |
| `ruby-sinatra` | ERB | `views/` | `.erb` |
| `java-*-spring` | Thymeleaf/JSP | `src/main/resources/templates/` | `.html`, `.jsp` |
| `dotnet-aspnet` | Razor | `Views/`, `Pages/` | `.cshtml` |
| `dotnet-blazor` | Razor | `Components/`, `Pages/` | `.razor` |
| `elixir-phoenix` | HEEx | `lib/*/controllers/`, `lib/*/live/` | `.heex` |
| `helm` | Go Templates | `templates/` | `.yaml`, `.tpl` |
| `php` + Laravel | Blade | `resources/views/` | `.blade.php` |
| `php` + Symfony | Twig | `templates/` | `.twig` |

---

## Recipe Ecosystems Without Stack Definitions

The tool install recipe system (`src/core/services/tool_install/data/recipes/languages/`)
knows about **7 language ecosystems** that have NO corresponding `stacks/*/stack.yml`.
These are languages the system can install and manage tools for but cannot yet
detect, audit, or scaffold as projects:

| Recipe File | Languages/Tools | Source Extensions | Why No Stack (Yet) |
|-------------|----------------|------------------|-------------------|
| `haskell.py` | GHC, Cabal, Stack | `.hs`, `.lhs` | Less common in DevOps targets |
| `jvm.py` (Scala subset) | Scala, sbt, Ammonite | `.scala`, `.sc` | Shares JVM but distinct syntax from Java |
| `jvm.py` (Kotlin subset) | Kotlin, ktlint | `.kt`, `.kts` | `java-gradle` detects `.kts` but no dedicated Kotlin stack |
| `lua.py` | Lua, LuaRocks, StyLua | `.lua` | Often embedded (Neovim configs, game scripts) |
| `ocaml.py` | OCaml, opam, Dune | `.ml`, `.mli` | Functional niche language |
| `rlang.py` | R, Rscript | `.R`, `.r`, `.Rmd` | Data science / stats focus |
| `wasm.py` | Wasmtime, Wasmer, wasm-pack | `.wasm`, `.wat` | Runtime target, not a source language |

**Audit implication**: Even without stack definitions, these languages may appear
as files inside projects the audit is scanning. A Go project might have Lua scripts.
A Rust project might produce WASM output. The parsers need to handle these files
when encountered, using the `_generic` rubric until/unless dedicated stacks are created.

---

## Known Gaps & Bugs (Pre-Existing)

| Issue | Location | Severity | Notes |
|-------|----------|----------|-------|
| `php` missing from `detect_language()` lang_map | `src/core/services/detection.py:187-222` | BUG | PHP stack exists, recipes exist, but `detect_language("php")` returns `None` — it's not in the `lang_map` dict |
| `docker-compose` returns `None` for language | `detect_language()` | BY DESIGN | But audit should still analyze compose files as YAML |
| `markdown` returns `None` for language | `detect_language()` | BY DESIGN | But audit should still analyze `.md` files |
| Kotlin/Scala share `java-gradle` stack | stacks directory | GAP | `java-gradle` detects `.kts` files (Kotlin build scripts) but there's no separate `kotlin` or `scala` stack |
| No `php-laravel` or `php-symfony` child stacks | stacks directory | GAP | PHP has one base stack; framework-specific detection (Blade vs Twig templates) not yet possible via stack system |
| `.tmpl` files in this project (5 files) | various | INFO | These are Go-template-style files used by the Docusaurus builder — audit needs to detect them as Go templates |

---

## This Project's Actual File Distribution

The audit system will first be tested on THIS project. Here's what it contains
(excluding `node_modules/`, `.git/`, `__pycache__/`, `build/`, `dist/`, `.venv/`):

| Extension | Count | What They Are | Current Audit Coverage |
|-----------|-------|--------------|----------------------|
| `.py` | 681 | Python source (core, web, CLI, audit, adapters) | ✅ Fully parsed (only language covered) |
| `.md` | 383 | Markdown docs, READMEs, plans, workflows | ❌ Not parsed |
| `.json` | 154 | Config, package.json, assistant catalogue, test fixtures | ❌ Not parsed |
| `.html` | 146 | Jinja2 templates (pages, partials, scripts with embedded JS) | ❌ Not parsed |
| `.mdx` | 97 | Docusaurus MDX pages (Markdown + JSX components) | ❌ Not parsed |
| `.js` | 66 | Docusaurus plugins, Remark plugins, standalone scripts | ❌ Not parsed |
| `.yml` | 53 | Stack definitions, GitHub Actions, Docker Compose, project.yml | ❌ Not parsed |
| `.ts` | 8 | TypeScript source (Docusaurus config, types) | ❌ Not parsed |
| `.jsonl` | 8 | Chat history, NDJSON data files | ❌ Not parsed |
| `.tmpl` | 5 | Go template files (Docusaurus builder) | ❌ Not parsed |
| `.tsx` | 3 | React components (Docusaurus custom) | ❌ Not parsed |
| `.css` | 3 | Stylesheets (Docusaurus custom, web admin) | ❌ Not parsed |
| `.toml` | 2 | `pyproject.toml`, config | ❌ Not parsed |
| `Dockerfile` | 5 | Container build definitions | ❌ Not parsed |
| `Makefile` | 1 | Build automation | ❌ Not parsed |
| `.sh` | 1 | Shell script (`manage.sh`) | ❌ Not parsed |

**Summary**: Of 1,615 auditable files in this project, the current system parses
**681 (42%)**. After the overhaul, it should parse **1,615 (100%)**.

---

## Architecture Design

### Parser Registry Architecture

```
src/core/services/audit/parsers/
├── __init__.py              # ParserRegistry — routes files to parsers
├── _base.py                 # BaseParser ABC, FileAnalysis model
├── python_parser.py         # Python AST parser (existing, refactored)
├── javascript_parser.py     # JS/TS regex + heuristic parser
├── go_parser.py             # Go parser
├── rust_parser.py           # Rust parser
├── c_family_parser.py       # C/C++ parser
├── jvm_parser.py            # Java/Kotlin/Scala parser
├── ruby_parser.py           # Ruby parser
├── php_parser.py            # PHP parser
├── dotnet_parser.py         # C#/F# parser
├── elixir_parser.py         # Elixir parser
├── swift_parser.py          # Swift parser
├── systems_parser.py        # Zig/Haskell/OCaml/Lua/R (lighter analysis)
├── template_parser.py       # Jinja2/ERB/EEx/Blade/Razor/Go-tmpl
├── config_parser.py         # YAML/JSON/TOML/HCL/Dockerfile
├── css_parser.py            # CSS/SCSS/SASS/Less
├── markup_parser.py         # HTML/Markdown/MDX/GraphQL/SQL/Protobuf
└── shell_parser.py          # Shell/Bash scripts
```

### Language-Agnostic FileAnalysis Model

```python
@dataclass
class FileAnalysis:
    """Universal file analysis result — works for any language."""
    
    # ── Identity ──
    file_path: str                    # Relative path from project root
    language: str                     # "python", "javascript", "go", etc.
    file_type: str                    # "source", "template", "config", "markup", "style", "script"
    template_engine: str | None       # "jinja2", "erb", "heex", None
    
    # ── Metrics (language-agnostic) ──
    total_lines: int                  # Total line count
    code_lines: int                   # Non-blank, non-comment lines
    comment_lines: int                # Comment-only lines
    blank_lines: int                  # Empty lines
    
    # ── Symbols (language-agnostic) ──
    functions: list[SymbolInfo]       # Functions/methods/procedures
    classes: list[SymbolInfo]         # Classes/structs/modules/traits
    exports: list[str]               # Publicly exported symbols
    
    # ── Imports (language-agnostic) ──
    imports: list[ImportInfo]         # All import/require/use statements
    
    # ── Complexity (language-agnostic) ──
    max_nesting_depth: int            # Deepest nesting in the file
    max_function_length: int          # Longest function in lines
    avg_function_length: float        # Average function length
    cyclomatic_complexity: int | None # If computable for this language
    
    # ── Language-Specific Extensions ──
    language_metrics: dict            # Per-language extra data
    # Python: {docstring_coverage, type_hint_coverage, ...}
    # Go: {exported_ratio, error_handling_ratio, ...}
    # Rust: {unsafe_block_count, lifetime_count, ...}
    # JS: {callback_depth, es_module, ...}
    # HTML/Template: {directive_count, block_count, macro_count, ...}
    
    # ── Code Navigation ──
    symbol_locations: list[SymbolLocation]  # For code peeking


@dataclass
class SymbolInfo:
    name: str
    kind: str              # "function", "class", "struct", "trait", "module", "interface"
    line_start: int
    line_end: int
    length: int            # line_end - line_start + 1
    visibility: str        # "public", "private", "protected", "internal", "default"
    docstring: bool        # Has documentation
    nesting_depth: int     # How deep in the nesting tree


@dataclass
class ImportInfo:
    raw: str               # The original import statement
    module: str            # The resolved module path
    names: list[str]       # Specific names imported (if any)
    is_relative: bool      # Relative import
    is_stdlib: bool        # Standard library import (if detectable)
    line: int              # Line number


@dataclass
class SymbolLocation:
    """For code peeking — links symbols to source positions."""
    symbol: str
    kind: str
    file: str
    line_start: int
    line_end: int
    preview: str           # First 3-5 lines of the symbol's body (for inline peek)
```

### Quality Rubric System

Instead of one hardcoded Python rubric, each language family gets its own rubric
that measures what matters FOR THAT LANGUAGE:

```python
QUALITY_RUBRICS: dict[str, list[QualityDimension]] = {
    "python": [
        QualityDimension("docstrings", weight=0.2, description="Docstring coverage"),
        QualityDimension("type_hints", weight=0.15, description="Type annotation coverage"),
        QualityDimension("nesting", weight=0.2, description="Nesting depth control"),
        QualityDimension("function_length", weight=0.25, description="Function size discipline"),
        QualityDimension("comments", weight=0.2, description="Comment quality"),
    ],
    "go": [
        QualityDimension("documentation", weight=0.2, description="Godoc coverage"),
        QualityDimension("error_handling", weight=0.25, description="Error return checking"),
        QualityDimension("exported_ratio", weight=0.15, description="API surface control"),
        QualityDimension("function_length", weight=0.2, description="Function size discipline"),
        QualityDimension("nesting", weight=0.2, description="Nesting depth control"),
    ],
    "rust": [
        QualityDimension("documentation", weight=0.2, description="Doc comment coverage"),
        QualityDimension("unsafe_usage", weight=0.25, description="Unsafe block discipline"),
        QualityDimension("nesting", weight=0.2, description="Nesting depth control"),
        QualityDimension("function_length", weight=0.2, description="Function size discipline"),
        QualityDimension("error_handling", weight=0.15, description="Result/Option usage"),
    ],
    "javascript": [
        QualityDimension("jsdoc", weight=0.15, description="JSDoc coverage"),
        QualityDimension("function_length", weight=0.25, description="Function size discipline"),
        QualityDimension("nesting", weight=0.2, description="Callback/nesting depth"),
        QualityDimension("modern_syntax", weight=0.2, description="ES6+ patterns (const/let, arrow, destructuring)"),
        QualityDimension("comments", weight=0.2, description="Comment quality"),
    ],
    "typescript": [
        QualityDimension("type_coverage", weight=0.2, description="Type annotation completeness"),
        QualityDimension("function_length", weight=0.2, description="Function size discipline"),
        QualityDimension("nesting", weight=0.2, description="Nesting depth control"),
        QualityDimension("interface_design", weight=0.2, description="Interface/type design quality"),
        QualityDimension("jsdoc", weight=0.1, description="Documentation comments"),
        QualityDimension("any_usage", weight=0.1, description="Avoidance of 'any' type"),
    ],
    "java": [
        QualityDimension("javadoc", weight=0.2, description="Javadoc coverage"),
        QualityDimension("class_length", weight=0.2, description="Class size discipline"),
        QualityDimension("method_length", weight=0.2, description="Method size discipline"),
        QualityDimension("nesting", weight=0.2, description="Nesting depth control"),
        QualityDimension("visibility", weight=0.2, description="Access modifier appropriateness"),
    ],
    "template": [
        QualityDimension("logic_complexity", weight=0.3, description="Template logic complexity (loops, conditionals)"),
        QualityDimension("reuse", weight=0.25, description="Block/macro/partial reuse"),
        QualityDimension("nesting", weight=0.25, description="Template nesting depth"),
        QualityDimension("comments", weight=0.2, description="Template documentation"),
    ],
    "config": [
        QualityDimension("structure", weight=0.3, description="Logical organization"),
        QualityDimension("nesting", weight=0.3, description="Nesting depth"),
        QualityDimension("comments", weight=0.2, description="Documentation/comments"),
        QualityDimension("size", weight=0.2, description="File size appropriateness"),
    ],
    # Generic fallback for languages without a specific rubric
    "_generic": [
        QualityDimension("documentation", weight=0.2, description="Documentation coverage"),
        QualityDimension("function_length", weight=0.3, description="Function size discipline"),
        QualityDimension("nesting", weight=0.3, description="Nesting depth control"),
        QualityDimension("comments", weight=0.2, description="Comment quality"),
    ],
}
```

---

## Phase Plan

### Phase 1 — Foundation: Parser Infrastructure & Universal Model
**Goal**: Build the parser registry and language-agnostic file analysis model.
**Estimated**: 3-4 sessions

#### 1.1 — Universal FileAnalysis Model
- Design and implement `_base.py` with `FileAnalysis`, `SymbolInfo`, `ImportInfo`, `SymbolLocation`
- These are language-agnostic data structures used by ALL parsers
- Must NOT break existing Python parser yet — the refactored models must be compatible

#### 1.2 — Parser Registry
- Create `ParserRegistry` class in `parsers/__init__.py`
- Routes file extensions → parser implementations
- Supports multi-extension mapping (`.js`, `.mjs`, `.cjs` → all go to JS parser)
- Supports override/priority (`.cshtml` → Razor parser, not generic HTML)
- Exposes `parse_file(path) → FileAnalysis` and `parse_tree(root) → dict[str, FileAnalysis]`

#### 1.3 — Refactor Existing Python Parser
- Adapt `python_parser.py` to implement the `BaseParser` interface
- Output the universal `FileAnalysis` model instead of the current Python-specific one
- Python-specific metrics go into `language_metrics` dict
- All existing consumers of `parse_tree()` must still work (backward compat shim)

#### 1.4 — Generic/Fallback Parser
- For ANY file the registry encounters that doesn't have a specialized parser
- Line counting, comment detection (using `#`, `//`, `/* */` heuristics), blank lines
- No symbol extraction, no import parsing — just basic metrics
- This ensures EVERY file gets something even if we haven't built the specific parser yet

---

### Phase 2 — Tier 1 Parsers: JavaScript/TypeScript + Templates
**Goal**: Build parsers for the TWO most impactful file types beyond Python.
**Estimated**: 3-4 sessions

#### 2.1 — JavaScript/TypeScript Parser
- Regex + heuristic based (not full AST — we're in Python, parsing JS AST would need Node)
- Detect: `function`, `const X = () =>`, `class X`, `export`, `import`/`require`
- Count: functions, classes, exports, imports
- Metrics: nesting depth (brace counting), function length, JSDoc presence
- Handle: `.js`, `.mjs`, `.cjs`, `.jsx`, `.ts`, `.tsx`, `.mts`, `.cts`
- Distinguish ES modules vs CommonJS
- Detect `var` vs `let`/`const` (modern syntax indicator)

#### 2.2 — Template Parser (Jinja2/ERB/EEx/Blade/Go-tmpl)
- Detect template engine from file content + host stack context
- Jinja2: count `{{ }}` expressions, `{% %}` blocks, `{% macro %}` definitions,
  `{% block %}` definitions, `{% extends %}` inheritance
- ERB: count `<%= %>` and `<% %>` blocks
- Go templates: count `{{ }}` directives
- For Jinja2 specifically: detect embedded raw JS (the `scripts/*.html` pattern)
  by looking for function declarations, event handlers, DOM manipulation outside
  template directives
- Template reuse analysis: macro/block/partial reuse patterns

#### 2.3 — CSS/SCSS Parser
- Selector count, nesting depth, media query count
- Variable/custom property usage
- Import/use statements
- File size and rule count metrics

#### 2.4 — Integration: parse_tree() Goes Multi-Language
- Update `parse_tree()` to iterate ALL supported extensions, not just `*.py`
- Each file gets routed through the parser registry
- The result dict is keyed by relative file path, values are `FileAnalysis`
- All downstream consumers (l2_quality, l2_structure) use the new model

---

### Phase 3 — Tier 2 Parsers: Go, Rust, JVM, Systems Languages
**Goal**: Cover the second ring of languages with real parsers.
**Estimated**: 3-4 sessions

#### 3.1 — Go Parser
- Regex-based: detect `func`, `type X struct`, `type X interface`
- Import parsing: `import "pkg"` and `import (...)` blocks
- Exported vs unexported (uppercase first letter)
- Error return detection: functions returning `error`
- Comment/doc detection: `//` comments preceding exports

#### 3.2 — Rust Parser
- Detect `fn`, `struct`, `enum`, `trait`, `impl`, `mod`
- Import parsing: `use crate::`, `use std::`, `use super::`
- `pub` vs private visibility
- `unsafe` block counting
- Doc comment detection: `///` and `//!`

#### 3.3 — JVM Parser (Java/Kotlin/Scala)
- Java: `public class`, `private void`, `import`, package structure
- Kotlin: `fun`, `class`, `data class`, `object`, `import`
- Scala: `def`, `class`, `object`, `trait`, `import`
- Shared: visibility modifiers, annotation counting, Javadoc/KDoc

#### 3.4 — C Family Parser (C/C++)
- Detect functions (via `type name(args) {` pattern)
- `#include` parsing
- Header guard detection
- `#define` macro counting
- C++: class/struct/namespace detection, template usage

#### 3.5 — Other Language Parsers (Ruby, PHP, C#, Elixir, Swift, Zig)
- Ruby: `def`, `class`, `module`, `require`, `require_relative`
- PHP: `function`, `class`, `namespace`, `use`, `require_once`
- C#: `class`, `interface`, `namespace`, `using`, `public`/`private`
- Elixir: `def`, `defmodule`, `defp`, `import`, `alias`, `use`
- Swift: `func`, `class`, `struct`, `protocol`, `import`
- Zig: `fn`, `pub fn`, `@import`, `const`, `struct`
- Each produces a valid `FileAnalysis` with appropriate `language_metrics`

#### 3.6 — Config/Infra Parser
- YAML: key count, nesting depth, anchor/alias usage, file purpose heuristic
- JSON: key count, nesting depth, array size
- TOML: section count, key count
- HCL/Terraform: resource/variable/output/module block counting
- Dockerfile: instruction count, FROM count, layer optimization heuristics
- Makefile: target count, phony declarations
- Shell scripts: function count, error handling (`set -e`/`set -o pipefail`)
- GitHub Actions YAML: step count, action version analysis

---

### Phase 4 — Quality Scoring: Per-Language Rubrics
**Goal**: Replace the Python-only quality scoring with language-appropriate rubrics.
**Estimated**: 2-3 sessions

#### 4.1 — Rubric Registry
- Define `QualityDimension` dataclass
- Define `QUALITY_RUBRICS` dict mapping language → dimensions with weights
- Include rubrics for: Python, Go, Rust, JavaScript, TypeScript, Java, template, config, generic
- Each dimension has: name, weight, description, scorer function

#### 4.2 — Dimension Scorers
- Each quality dimension needs a scorer function: `score(FileAnalysis) → float (0-10)`
- Reuse existing Python scorers where possible (docstrings, nesting, function_length)
- New scorers for: JSDoc, type_coverage, exported_ratio, error_handling, unsafe_usage
- Template scorers: logic_complexity, block_reuse
- Config scorers: structure, nesting_depth

#### 4.3 — Composite Scoring
- `l2_quality.py` refactored to use rubric registry
- For each file: look up language → get rubric → score each dimension → weighted average
- Hotspot detection becomes language-aware (long Go function threshold ≠ long Python function threshold)
- Sub-category averages computed per-language within a scope

#### 4.4 — l2_quality Integration
- Refactor `l2_quality.py` to accept multi-language `parse_tree()` output
- `file_scores[]` now includes `language` field per entry
- `hotspots[]` include `language` field
- Quality breakdown shows per-language dimensions, not just Python dimensions
- The summary can group by language: "Python: 8.3/10 (22 files), JS: 7.1/10 (12 files)"

---

### Phase 5 — Structure Analysis: Cross-Language Dependency Graphs
**Goal**: Build import/dependency graphs for all supported languages.
**Estimated**: 2-3 sessions

#### 5.1 — Universal Import Graph
- `l2_structure.py` refactored: `_build_import_graph()` uses `imports` from `FileAnalysis`
  instead of Python-specific AST data
- Each `ImportInfo` already has `module`, `names`, `is_relative` — language-agnostic
- Cross-language boundaries detected: a Python file importing a generated protobuf module,
  or a JS file importing a WASM module compiled from Rust

#### 5.2 — Cross-Module Dependencies Multi-Language
- `_cross_module_deps()` already works with module paths — but needs to handle
  non-Python import resolution (Go packages, Rust crate paths, Node module resolution)
- Each language parser resolves imports to dotted module paths in the `ImportInfo`

#### 5.3 — Library Usage Multi-Language
- `library_usage` filtering now covers all language imports, not just Python
- JS: detect npm package imports (`import X from 'lodash'`)
- Go: detect external packages vs stdlib
- Rust: detect crate dependencies vs std

#### 5.4 — Module Metadata Multi-Language
- `modules[]` in structure data now includes file breakdown by language
- Total functions/classes aggregated across languages
- `exposure_ratio` computed per-language where applicable (Go, Rust, Python)

---

### Phase 6 — Audit-Data Directive: Multi-Language Rendering & Code Navigation
**Goal**: The `:::audit-data` directive shows complete multi-language health cards
with code navigation.
**Estimated**: 3-4 sessions

#### 6.1 — Multi-Language Health Card
- Module Health section shows per-language breakdown:
  ```
  Module Health                         22 Python · 12 Jinja2 · 3 JS · 2 CSS
  Python:   ██████████████████░░  8.3/10
  Jinja2:   ████████████████████  9.1/10
  JS:       ██████████████░░░░░░  7.2/10
  CSS:      █████████████████░░░  8.8/10
  ```
- Quality breakdown shows language-appropriate dimensions per language
- Weakest files across ALL languages, noting which language each is

#### 6.2 — Code Peeking
- Hotspot references become clickable
- On click: show `SymbolLocation.preview` (first 3-5 lines) inline in the audit card
- On double-click or "open": navigate to the file in the preview panel, scrolled to the line
- Implementation: hotspot entries include `data-file` and `data-line` attributes
- Frontend JS handler opens the preview panel with the file and line number

#### 6.3 — Smart File Type Composition Display
- Instead of just "22 files", show:
  ```
  File Composition
  ├── Python sources     22 files   4,800 lines
  ├── Jinja2 templates   12 files   1,200 lines
  │   ├── pages           4 files     380 lines
  │   ├── partials        5 files     520 lines
  │   └── scripts (JS)    3 files     300 lines  ← detected as embedded JS
  ├── JavaScript          3 files     450 lines
  ├── CSS                 2 files     180 lines
  └── Config (YAML)       1 file       45 lines
  ```
- This requires the template parser to distinguish subtypes within HTML files

#### 6.4 — Dependency Graph Multi-Language
- Dependencies section shows cross-language deps
  ```
  Dependencies
  Outbound (this code imports from)
    → config (Python · strong · 12 imports)
    → lodash (npm · moderate · 5 imports)
  Inbound (other code imports this)
    ← cli (Python · strong · 18 imports)
    ← tests (Python · weak · 3 imports)
  ```
- Each dep pill includes the language/ecosystem

#### 6.5 — Navigation Links
- All file references in the audit card are hyperlinks
- Clicking a file name opens it in the content preview panel
- Links include line numbers for symbol-level navigation: `_preview.html?path=...&line=42`

---

### Phase 7 — Async Audit & Streaming
**Goal**: Eliminate frontend timeouts for long-running audits. Enable real-time progress.
**Estimated**: 2-3 sessions

#### 7.1 — Async Audit Task Architecture
- Audit computation moves to a background task
- New endpoint: `POST /api/audit/scan` → returns `{task_id, status: "started"}`
- New endpoint: `GET /api/audit/status/{task_id}` → returns `{status, progress, result}`
- Frontend polls status or subscribes to SSE

#### 7.2 — SSE Progress Streaming
- Leverage existing `_event_stream.html` SSE infrastructure
- During scan: emit progress events
  ```
  event: audit_progress
  data: {"phase": "parsing", "language": "python", "files_done": 150, "files_total": 681}
  
  event: audit_progress
  data: {"phase": "parsing", "language": "javascript", "files_done": 30, "files_total": 45}
  
  event: audit_progress
  data: {"phase": "scoring", "progress": 0.75}
  
  event: audit_complete
  data: {"task_id": "abc123", "duration_ms": 42000}
  ```
- Audit card shows progress indicator while scan is running

#### 7.3 — Incremental Cache Updates
- When a full scan completes, cache ALL results
- When individual files change, do INCREMENTAL re-parse of just those files
- Cache key per file: `audit:file:{path}:{mtime}` — if the mtime hasn't changed, reuse
- Full structure analysis still needs all files, but quality scores can be incrementally updated

#### 7.4 — Frontend Timeout Elimination
- `audit_directive.py` no longer blocks the preview endpoint on scan computation
- If cache is warm: return cached data immediately
- If cache is cold: return placeholder "⏳ Audit scan in progress..." with SSE subscription
- When scan completes, SSE event triggers frontend to re-fetch the audit card

---

### Phase 8 — Intelligence: Smart Deduction & Insights
**Goal**: The audit doesn't just dump metrics — it makes intelligent observations.
**Estimated**: 2-3 sessions

#### 8.1 — Template Engine Detection Intelligence
- Don't just check file extension — examine file CONTENT
- Detect Jinja2 by `{{ }}` + `{% %}` pattern presence, NOT by `.html` extension
- Detect embedded JS in HTML by: function declarations, `addEventListener`, DOM API usage
  OUTSIDE `{{ }}` blocks
- Classify: "This is a Jinja2 template that primarily contains JavaScript" vs
  "This is a Jinja2 template that primarily contains HTML"
- For `src/ui/web/templates/scripts/*.html`: detect that the entire content is JS
  and audit it as JS, not HTML

#### 8.2 — Stack Deduction from Module Context
- Use `project.yml` module stack declarations to inform parsing intelligence
- If module is `python-flask`, expect Jinja2 templates in `templates/` subdirectory
- If module is `node-nextjs`, expect TSX pages in `pages/` or `app/` directory
- If module is `helm`, expect Go templates in `templates/` directory
- This context helps disambiguate: `.yaml` in a Helm chart means Go template YAML,
  `.yaml` in `.github/workflows/` means GitHub Actions YAML

#### 8.3 — Narrative Report Generation
- Instead of raw metric dump, generate natural language observations:
  ```
  📊 This module scores 8.3/10 overall. Its Python code is well-documented
  (docstrings: 9.2) but has nesting concerns in l1_classification.py (depth 8).
  The 12 Jinja2 templates could benefit from more macro reuse — only 2 of 12
  templates use {% macro %} directives. The 3 JavaScript files in templates/scripts/
  average 450 lines, suggesting they could be split into smaller modules.
  ```
- Observations are computed, not templated strings — they react to actual data patterns

#### 8.4 — Comparison & Trend Context
- Cross-module comparison: "This module's Python quality (8.3) is above the project average (8.0)"
- Trend detection: "Quality improved +0.4 since last scan (new docstrings in 3 files)"
- Cross-language insight: "Python code is well-maintained (8.3), but JS code lags (6.8)"

#### 8.5 — Actionable Recommendations
- Based on detected patterns, suggest specific improvements:
  ```
  Recommendations
  1. ⚠ l1_classification.py:_extract_all_deps — depth 8 nesting. Consider extracting
     the inner loop into a helper function.
  2. ⚠ templates/scripts/ — 3 HTML files contain only JavaScript (no HTML/template 
     content). Consider renaming to .js or adding a clear comment about the convention.
  3. ✓ All 22 Python files have docstrings — good documentation coverage.
  ```

---

## Dependency Map Between Phases

```
Phase 1 (Foundation) ──────────────────────────────────────────────────┐
   ↓                                                                    │
Phase 2 (JS/TS + Templates) ──────┐                                    │
   ↓                               │                                    │
Phase 3 (All Other Parsers) ──────┤                                    │
   ↓                               ↓                                    │
Phase 4 (Quality Rubrics) ←── uses parser output from 1-3              │
   ↓                                                                    │
Phase 5 (Structure Multi-Lang) ←── uses ImportInfo from 1-3            │
   ↓                               ↓                                    │
Phase 6 (Directive Enhancement) ←── needs quality + structure data  ←──┘
   ↓                                                                    
Phase 7 (Async/Streaming) ←── independent of 4-6, depends on 1        
   ↓                                                                    
Phase 8 (Intelligence) ←── needs all prior phases for full data        
```

**Critical path**: Phase 1 → Phase 2 → Phase 4 → Phase 6 (parser → scoring → rendering)

**Parallelizable**: Phase 7 (streaming) can start after Phase 1 independently.
Phase 3 (more parsers) can overlap with Phase 4 (scoring for languages already parsed).

---

## Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| Python parser regression during refactor | HIGH | Phase 1.3: backward compat shim, verify all existing audit pages still work |
| JS regex parser produces garbage on edge cases | MEDIUM | Accept 80% accuracy for v1, improve iteratively |
| Performance: parsing 25K JS files crashes | HIGH | Exclude `node_modules/`, `dist/`, `build/` dirs; keep per-file cap on parse time |
| Cache format breaking change | HIGH | Version the cache format; clear on upgrade |
| Template engine misdetection | MEDIUM | Default to generic HTML parser when uncertain; allow manual override |
| Quality scores not comparable across languages | MEDIUM | Display per-language, never average Python + JS scores together |

---

## What This Does NOT Include

- **External tool integration** (running ruff, eslint, clippy on the project) — the
  audit system is a built-in analyzer, not a wrapper around external linters
- **Security scanning** (that's `l2_risk.py` — separate concern, already exists)
- **Test execution** — audit observes test files, doesn't run them
- **AST parsing via external tools** — we don't shell out to `node` to parse JS or
  `go` to parse Go. We use regex + heuristic analysis that runs in Python.

---

## Open Questions for Discussion

1. **Parser depth vs. breadth tradeoff**: For Phase 2, do we want the JS parser to
   be production-quality (handling all edge cases of arrow functions, destructuring,
   async generators) or 80%-accurate heuristic that we improve later?

2. **Template engine detection confidence**: When we see a `.html` file, how much
   analysis should we do before deciding if it's Jinja2, raw HTML, or embedded JS?
   Should we examine the first N lines? The whole file? Check the parent module's stack?

3. **Cross-language scoring**: Should the audit card EVER show a single "Module Health"
   score that averages across Python + JS + templates, or should each language always
   get its own independent score?

4. **File exclusion lists**: Should each language parser have its own exclusion patterns
   (e.g., `node_modules` for JS, `vendor/` for Go/Ruby/PHP, `target/` for Rust,
   `bin/obj` for .NET) or is there one global exclusion list?

5. **Phase 1 scope**: Should Phase 1.4 (generic fallback parser) cover CSS/HTML/YAML
   immediately (just line counting + comment detection), or leave those entirely
   for Phase 2-3?

---

## Related Documents

| Document | Purpose |
|----------|---------|
| [audit-coverage-tracker.md](./audit-coverage-tracker.md) | **Living progress dashboard** — tracks what's covered vs. what's not, updated as each sub-phase completes |
| [audit-directive.md](./audit-directive.md) | Original audit-data directive spec — HTML rendering, data structures, scope resolution |

### Update Discipline

When completing any sub-phase of this plan:

1. **Update this plan**: Mark the sub-phase as complete in the Phase Plan section
2. **Update the coverage tracker**: Change the relevant ❌ → 🔧 → ✅ cells,
   update percentages, add an entry to the Update Log
3. **Both documents must stay in sync** — never update one without the other
