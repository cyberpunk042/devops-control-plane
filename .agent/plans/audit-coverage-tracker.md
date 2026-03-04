# Audit Coverage Tracker

> **Purpose**: Living document tracking what the audit system can analyze today
> vs. what it needs to analyze. Updated as each phase of the
> [audit-system-overhaul.md](./audit-system-overhaul.md) progresses.
>
> **Last Updated**: 2026-03-04 (initial creation — baseline)
>
> **Quick Summary**:  
> - **Stacks covered**: 1 of 47 (2%)  
> - **Languages parsed**: 1 of 21 source languages (5%)  
> - **Template engines**: 0 of 16 (0%)  
> - **Config formats**: 0 of 17 (0%)  
> - **This project's files**: 681 of 1,615 (42%)

---

## Coverage Legend

| Symbol | Meaning |
|--------|---------|
| ✅ | **Fully covered** — parser exists, quality rubric defined, structure analysis works |
| 🔧 | **Parser exists** — file is parsed but quality scoring or structure analysis incomplete |
| 📐 | **Basic metrics only** — line counting, comment detection via generic fallback parser |
| ❌ | **Not covered** — file type is completely invisible to the audit system |
| 🚫 | **Intentionally excluded** — not a parseable file type (binary, cache, etc.) |

---

## Phase Progression

| Phase | Name | Status | Started | Completed | Notes |
|-------|------|--------|---------|-----------|-------|
| **1** | Foundation: Parser Infrastructure & Universal Model | ❌ Not Started | — | — | — |
| **2** | Tier 1 Parsers: JS/TS + Templates + CSS | ❌ Not Started | — | — | — |
| **3** | Tier 2 Parsers: Go, Rust, JVM, Systems | ❌ Not Started | — | — | — |
| **4** | Quality Scoring: Per-Language Rubrics | ❌ Not Started | — | — | — |
| **5** | Structure: Cross-Language Dependency Graphs | ❌ Not Started | — | — | — |
| **6** | Directive: Multi-Language Cards + Code Navigation | ❌ Not Started | — | — | — |
| **7** | Async Audit + SSE Streaming | ❌ Not Started | — | — | — |
| **8** | Intelligence: Smart Deduction + Insights | ❌ Not Started | — | — | — |

### Sub-Phase Detail

| Sub-Phase | Name | Status | Depends On | Unlocks |
|-----------|------|--------|-----------|---------|
| 1.1 | Universal FileAnalysis Model | ❌ | — | 1.2, 1.3, 1.4 |
| 1.2 | Parser Registry | ❌ | 1.1 | 1.3, 1.4, 2.x |
| 1.3 | Refactor Python Parser | ❌ | 1.1, 1.2 | 2.4 |
| 1.4 | Generic/Fallback Parser | ❌ | 1.2 | 2.4 |
| 2.1 | JavaScript/TypeScript Parser | ❌ | 1.2 | 4.1, 5.1 |
| 2.2 | Template Parser (Jinja2/ERB/etc.) | ❌ | 1.2 | 4.1, 6.3, 8.1 |
| 2.3 | CSS/SCSS Parser | ❌ | 1.2 | 4.1 |
| 2.4 | Integration: parse_tree() Multi-Language | ❌ | 1.3, 1.4 | 4.x, 5.x |
| 3.1 | Go Parser | ❌ | 1.2 | 4.1, 5.1 |
| 3.2 | Rust Parser | ❌ | 1.2 | 4.1, 5.1 |
| 3.3 | JVM Parser (Java/Kotlin/Scala) | ❌ | 1.2 | 4.1, 5.1 |
| 3.4 | C Family Parser (C/C++) | ❌ | 1.2 | 4.1, 5.1 |
| 3.5 | Other Parsers (Ruby/PHP/C#/Elixir/Swift/Zig) | ❌ | 1.2 | 4.1, 5.1 |
| 3.6 | Config/Infra Parser (YAML/JSON/HCL/Dockerfile) | ❌ | 1.2 | 4.1, 6.3 |
| 4.1 | Rubric Registry | ❌ | 2.x or 3.x | 4.2, 4.3 |
| 4.2 | Dimension Scorers | ❌ | 4.1 | 4.3 |
| 4.3 | Composite Scoring | ❌ | 4.2 | 4.4 |
| 4.4 | l2_quality Integration | ❌ | 4.3 | 6.1 |
| 5.1 | Universal Import Graph | ❌ | 2.x or 3.x | 5.2 |
| 5.2 | Cross-Module Dependencies Multi-Language | ❌ | 5.1 | 5.3, 5.4 |
| 5.3 | Library Usage Multi-Language | ❌ | 5.2 | 6.4 |
| 5.4 | Module Metadata Multi-Language | ❌ | 5.2 | 6.1, 6.3 |
| 6.1 | Multi-Language Health Card | ❌ | 4.4, 5.4 | — |
| 6.2 | Code Peeking | ❌ | 1.1 (SymbolLocation) | — |
| 6.3 | Smart File Type Composition Display | ❌ | 2.2, 3.6, 5.4 | — |
| 6.4 | Dependency Graph Multi-Language | ❌ | 5.3 | — |
| 6.5 | Navigation Links | ❌ | 6.2 | — |
| 7.1 | Async Audit Task Architecture | ❌ | 1.x | 7.2 |
| 7.2 | SSE Progress Streaming | ❌ | 7.1 | 7.4 |
| 7.3 | Incremental Cache Updates | ❌ | 2.4 | 7.4 |
| 7.4 | Frontend Timeout Elimination | ❌ | 7.2, 7.3 | — |
| 8.1 | Template Engine Detection Intelligence | ❌ | 2.2 | 8.2 |
| 8.2 | Stack Deduction from Module Context | ❌ | 8.1 | 8.3 |
| 8.3 | Narrative Report Generation | ❌ | 4.4, 5.4 | — |
| 8.4 | Comparison & Trend Context | ❌ | 8.3 | — |
| 8.5 | Actionable Recommendations | ❌ | 8.3 | — |

---

## Source Language Coverage

### Tier 1 — Languages with stack definitions AND recipe tooling

| # | Language | Stack(s) | Recipes | Parser | Quality Rubric | Structure/Imports | Extensions |
|---|----------|----------|---------|--------|---------------|-------------------|------------|
| 1 | **Python** | `python`, `python-lib`, `python-cli`, `python-flask`, `python-django`, `python-fastapi` | ✅ `python.py` (14.8KB) | ✅ `python_parser.py` (AST) | ✅ 5 dimensions | ✅ `import`/`from` | `.py`, `.pyw`, `.pyi` |
| 2 | **JavaScript** | `node`, `node-lib`, `node-express`, `node-nextjs`, `node-react` | ✅ `node.py` (13.6KB) | ❌ None | ❌ None | ❌ None | `.js`, `.mjs`, `.cjs`, `.jsx` |
| 3 | **TypeScript** | `typescript`, `typescript-lib` | ✅ (shares `node.py`) | ❌ None | ❌ None | ❌ None | `.ts`, `.tsx`, `.mts`, `.cts` |
| 4 | **Go** | `go`, `go-lib`, `go-cli`, `go-gin`, `go-fiber` | ✅ `go.py` (5.5KB) | ❌ None | ❌ None | ❌ None | `.go` |
| 5 | **Rust** | `rust`, `rust-lib`, `rust-cli`, `rust-axum`, `rust-actix` | ✅ `rust.py` (20.3KB) | ❌ None | ❌ None | ❌ None | `.rs` |
| 6 | **Java** | `java-maven`, `java-maven-spring`, `java-gradle`, `java-gradle-spring` | ✅ `jvm.py` (5.1KB) | ❌ None | ❌ None | ❌ None | `.java` |
| 7 | **Ruby** | `ruby`, `ruby-rails`, `ruby-sinatra` | ✅ `ruby.py` (3.5KB) | ❌ None | ❌ None | ❌ None | `.rb`, `.rake` |
| 8 | **C#/.NET** | `dotnet`, `dotnet-aspnet`, `dotnet-blazor` | ✅ `dotnet.py` (2.2KB) | ❌ None | ❌ None | ❌ None | `.cs` |
| 9 | **PHP** | `php` | ✅ `php.py` (4.9KB) | ❌ None | ❌ None | ❌ None | `.php` |
| 10 | **Elixir** | `elixir`, `elixir-phoenix` | ✅ `elixir.py` (1.9KB) | ❌ None | ❌ None | ❌ None | `.ex`, `.exs` |
| 11 | **Swift** | `swift` | ✅ (none — stack only) | ❌ None | ❌ None | ❌ None | `.swift` |
| 12 | **C** | `c` | ✅ (none — stack only) | ❌ None | ❌ None | ❌ None | `.c`, `.h` |
| 13 | **C++** | `cpp` | ✅ (none — stack only) | ❌ None | ❌ None | ❌ None | `.cpp`, `.hpp`, `.cc`, `.hh`, `.cxx`, `.hxx` |
| 14 | **Zig** | `zig` | ✅ `zig.py` (1.4KB) | ❌ None | ❌ None | ❌ None | `.zig` |
| 15 | **Protobuf** | `protobuf` | ✅ (none — stack only) | ❌ None | ❌ None | ❌ None | `.proto` |

### Tier 2 — Languages with recipe tooling but NO stack definition

| # | Language | Recipes | Parser | Quality Rubric | Extensions |
|---|----------|---------|--------|---------------|------------|
| 16 | **Kotlin** | ✅ `jvm.py` (kotlinc, ktlint) | ❌ None | ❌ None | `.kt`, `.kts` |
| 17 | **Scala** | ✅ `jvm.py` (scala, sbt, ammonite) | ❌ None | ❌ None | `.scala`, `.sc` |
| 18 | **Lua** | ✅ `lua.py` (lua, luarocks, stylua) | ❌ None | ❌ None | `.lua` |
| 19 | **Haskell** | ✅ `haskell.py` (ghc, cabal, stack) | ❌ None | ❌ None | `.hs`, `.lhs` |
| 20 | **OCaml** | ✅ `ocaml.py` (ocaml, opam, dune) | ❌ None | ❌ None | `.ml`, `.mli` |
| 21 | **R** | ✅ `rlang.py` (R, Rscript) | ❌ None | ❌ None | `.R`, `.r`, `.Rmd` |

### Tier 3 — Compilation targets (not source languages)

| # | Type | Recipes | Parser | Extensions |
|---|------|---------|--------|------------|
| 22 | **WebAssembly** | ✅ `wasm.py` (wasmtime, wasmer, wasm-pack) | ❌ None | `.wasm` (binary), `.wat` (text) |

---

## Template Engine Coverage

| # | Engine | Associated Stack(s) | Parser | Quality Rubric | Extensions |
|---|--------|-------------------|--------|---------------|------------|
| 1 | **Jinja2** | `python-flask`, `python-django` | ❌ None | ❌ None | `.html`, `.j2`, `.jinja`, `.jinja2` |
| 2 | **ERB** | `ruby-rails`, `ruby-sinatra` | ❌ None | ❌ None | `.erb`, `.html.erb` |
| 3 | **HEEx/EEx** | `elixir-phoenix` | ❌ None | ❌ None | `.heex`, `.eex`, `.leex` |
| 4 | **Go Templates** | `go-gin`, `go-fiber`, `helm` | ❌ None | ❌ None | `.tmpl`, `.gohtml` |
| 5 | **Blade** | `php` (Laravel) | ❌ None | ❌ None | `.blade.php` |
| 6 | **Razor** | `dotnet-aspnet`, `dotnet-blazor` | ❌ None | ❌ None | `.cshtml`, `.razor` |
| 7 | **JSX** | `node-react`, `node-nextjs` | ❌ None | ❌ None | `.jsx` (handled by JS parser) |
| 8 | **TSX** | `node-react`, `node-nextjs` | ❌ None | ❌ None | `.tsx` (handled by TS parser) |
| 9 | **Pug/Jade** | `node-express` | ❌ None | ❌ None | `.pug`, `.jade` |
| 10 | **Handlebars/Mustache** | `node-express` | ❌ None | ❌ None | `.hbs`, `.handlebars`, `.mustache` |
| 11 | **EJS** | `node-express` | ❌ None | ❌ None | `.ejs` |
| 12 | **Twig** | `php` (Symfony) | ❌ None | ❌ None | `.twig` |
| 13 | **Slim** | `ruby-rails` | ❌ None | ❌ None | `.slim` |
| 14 | **HAML** | `ruby-rails` | ❌ None | ❌ None | `.haml` |
| 15 | **Svelte** | standalone | ❌ None | ❌ None | `.svelte` |
| 16 | **Vue SFC** | standalone | ❌ None | ❌ None | `.vue` |
| 17 | **MDX** | Docusaurus, Next.js MDX | ❌ None | ❌ None | `.mdx` |
| 18 | **Thymeleaf** | `java-*-spring` | ❌ None | ❌ None | `.html` (with `th:` attributes) |

---

## Configuration & Infrastructure Format Coverage

| # | Format | Associated Stack(s) | Parser | Quality Rubric | Extensions |
|---|--------|-------------------|--------|---------------|------------|
| 1 | **YAML** | `kubernetes`, `helm`, `docker-compose`, all CI/CD | ❌ None | ❌ None | `.yml`, `.yaml` |
| 2 | **JSON** | `node` (package.json), configs | ❌ None | ❌ None | `.json` |
| 3 | **TOML** | `python` (pyproject.toml), `rust` (Cargo.toml) | ❌ None | ❌ None | `.toml` |
| 4 | **HCL** | `terraform` | ❌ None | ❌ None | `.tf`, `.tfvars` |
| 5 | **Dockerfile** | all containerized stacks | ❌ None | ❌ None | `Dockerfile`, `Dockerfile.*` |
| 6 | **Docker Compose** | `docker-compose` | ❌ None | ❌ None | `docker-compose.yml`, `compose.yml` |
| 7 | **K8s Manifests** | `kubernetes` | ❌ None | ❌ None | `.yaml` (with `apiVersion:`) |
| 8 | **Helm Templates** | `helm` | ❌ None | ❌ None | `.yaml` in `templates/` |
| 9 | **GitHub Actions** | all projects with CI | ❌ None | ❌ None | `.yml` in `.github/workflows/` |
| 10 | **Makefile** | `c`, `cpp`, general | ❌ None | ❌ None | `Makefile`, `*.mk` |
| 11 | **Shell Scripts** | all projects | ❌ None | ❌ None | `.sh`, `.bash`, `.zsh` |
| 12 | **SQL** | database-backed stacks | ❌ None | ❌ None | `.sql` |
| 13 | **GraphQL** | API stacks | ❌ None | ❌ None | `.graphql`, `.gql` |
| 14 | **CSS** | `static-site`, web stacks | ❌ None | ❌ None | `.css` |
| 15 | **SCSS/SASS** | web stacks | ❌ None | ❌ None | `.scss`, `.sass` |
| 16 | **Less** | web stacks | ❌ None | ❌ None | `.less` |
| 17 | **Markdown** | `markdown`, all READMEs | ❌ None | ❌ None | `.md` |

---

## Dependency Manifest Parser Coverage (l1_parsers.py)

These already exist and work today — they parse dependency files for dependency
classification, NOT source code analysis. They are NOT affected by the audit overhaul
but are listed for completeness.

| # | Manifest | Ecosystem | Parser Status | File |
|---|----------|-----------|--------------|------|
| 1 | `requirements.txt` | Python | ✅ Working | `l1_parsers.py` |
| 2 | `pyproject.toml` | Python | ✅ Working | `l1_parsers.py` |
| 3 | `package.json` | Node.js | ✅ Working | `l1_parsers.py` |
| 4 | `go.mod` | Go | ✅ Working | `l1_parsers.py` |
| 5 | `Cargo.toml` | Rust | ✅ Working | `l1_parsers.py` |
| 6 | `Gemfile` | Ruby | ✅ Working | `l1_parsers.py` |
| 7 | `mix.exs` | Elixir | ✅ Working | `l1_parsers.py` |
| 8 | `pom.xml` | Java (Maven) | ❌ Not yet | — |
| 9 | `build.gradle` | Java/Kotlin (Gradle) | ❌ Not yet | — |
| 10 | `composer.json` | PHP | ❌ Not yet | — |
| 11 | `*.csproj` / `*.sln` | .NET | ❌ Not yet | — |
| 12 | `Package.swift` | Swift | ❌ Not yet | — |
| 13 | `*.cabal` / `stack.yaml` | Haskell | ❌ Not yet | — |

---

## This Project Coverage (devops-control-plane)

Concrete tracking of what happens when we audit ourselves:

| File Type | Count | Currently Parsed | After Phase 1 | After Phase 2 | After Phase 3 | Full Coverage |
|-----------|-------|-----------------|---------------|---------------|---------------|---------------|
| `.py` | 681 | ✅ (AST) | ✅ (refactored) | ✅ | ✅ | ✅ |
| `.md` | 383 | ❌ | 📐 (fallback) | 📐 | 📐 or 🔧 | ✅ |
| `.json` | 154 | ❌ | 📐 (fallback) | 📐 | 🔧 (3.6) | ✅ |
| `.html` | 146 | ❌ | 📐 (fallback) | 🔧 (2.2 templates) | 🔧 | ✅ |
| `.mdx` | 97 | ❌ | 📐 (fallback) | 📐 | 📐 | ✅ |
| `.js` | 66 | ❌ | 📐 (fallback) | 🔧 (2.1 JS parser) | 🔧 | ✅ |
| `.yml` | 53 | ❌ | 📐 (fallback) | 📐 | 🔧 (3.6) | ✅ |
| `.ts` | 8 | ❌ | 📐 (fallback) | 🔧 (2.1 TS parser) | 🔧 | ✅ |
| `.tmpl` | 5 | ❌ | 📐 (fallback) | 🔧 (2.2 Go tmpl) | 🔧 | ✅ |
| `Dockerfile` | 5 | ❌ | ❌ | ❌ | 🔧 (3.6) | ✅ |
| `.tsx` | 3 | ❌ | 📐 (fallback) | 🔧 (2.1 TSX) | 🔧 | ✅ |
| `.css` | 3 | ❌ | 📐 (fallback) | 🔧 (2.3 CSS) | 🔧 | ✅ |
| `.toml` | 2 | ❌ | 📐 (fallback) | 📐 | 🔧 (3.6) | ✅ |
| `Makefile` | 1 | ❌ | ❌ | ❌ | 🔧 (3.6) | ✅ |
| `.sh` | 1 | ❌ | ❌ | ❌ | 🔧 (3.6) | ✅ |
| **TOTAL** | **1,615** | **681 (42%)** | **~1,600 (99%)** | **~1,600** | **~1,615** | **1,615 (100%)** |

---

## Quality Rubric Coverage

| Language / Type | Rubric Defined | Dimensions | Scoring Active |
|----------------|---------------|------------|---------------|
| Python | ✅ (existing) | docstrings, type_hints, nesting, function_length, comments | ✅ Working |
| JavaScript | ❌ | — | ❌ |
| TypeScript | ❌ | — | ❌ |
| Go | ❌ | — | ❌ |
| Rust | ❌ | — | ❌ |
| Java | ❌ | — | ❌ |
| Ruby | ❌ | — | ❌ |
| C# | ❌ | — | ❌ |
| PHP | ❌ | — | ❌ |
| Template (Jinja2/ERB/etc.) | ❌ | — | ❌ |
| Config (YAML/JSON/HCL) | ❌ | — | ❌ |
| `_generic` fallback | ❌ | — | ❌ |

---

## Audit Directive Capabilities

| Capability | Status | Phase |
|-----------|--------|-------|
| Module Health (single language — Python) | ✅ Working | — |
| Module Health (multi-language breakdown) | ❌ | 6.1 |
| Hotspot file references (text only) | ✅ Working | — |
| Hotspot code peeking (clickable, preview) | ❌ | 6.2 |
| File composition tree (multi-language) | ❌ | 6.3 |
| Dependency graph (Python-only) | ✅ Working | — |
| Dependency graph (multi-language) | ❌ | 6.4 |
| File navigation links | ❌ | 6.5 |
| SSE progress streaming | ❌ | 7.2 |
| Async audit (no timeout) | ❌ | 7.4 |
| Narrative insights | ❌ | 8.3 |
| Actionable recommendations | ❌ | 8.5 |

---

## Update Log

| Date | Changes | Phase Affected |
|------|---------|---------------|
| 2026-03-04 | Initial creation — baseline coverage documented | All (planning) |

<!-- 
UPDATE INSTRUCTIONS FOR FUTURE AI:

When you complete a sub-phase, update this document:
1. Change the sub-phase's Status in the "Sub-Phase Detail" table
2. Update the Phase status in the "Phase Progression" table if all sub-phases done
3. Update the relevant coverage table cells (❌ → 🔧 → ✅)
4. Update the "Quick Summary" percentages at the top
5. Update the "This Project Coverage" table for the affected columns
6. Add an entry to the "Update Log" at the bottom
7. Recalculate the "Full Coverage" percentages

NEVER change this document without also reflecting the change in the
audit-system-overhaul.md plan. The two documents must be in sync.
-->
