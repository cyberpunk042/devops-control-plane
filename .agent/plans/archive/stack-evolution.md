# Stack Architecture Evolution

> Single source of truth for the stack evolution. Supersedes all prior notes.

---

## Design Principle

A **stack** is a technology definition: `{language}-{flavor}`.

- **Language** = the programming language or platform. Determines linting, formatting, type-checking tools.
- **Flavor** = the framework, SDK, or purpose pattern. Determines serve commands, Dockerfile shape, health checks, domain.

Not every stack has a flavor. `go` is a valid stack (generic Go project).  
Not every flavor implies a framework. `python-lib` is a purpose pattern (library, no entry point).

Infrastructure stacks (`docker-compose`, `kubernetes`, `helm`, `terraform`) and content stacks (`markdown`, `static-site`) don't follow the language-flavor pattern. They're standalone — no parent, no inheritance.

---

## The Java Problem (and its resolution)

Java has TWO orthogonal axes: **build system** (Maven / Gradle) and **framework** (Spring / Quarkus / plain).

These are fundamentally different dimensions:
- Maven and Gradle share **zero commands** (`mvn test` vs `./gradlew test`)
- Spring and Quarkus share **the same build commands** but add different runtime capabilities

Resolution: **the build system IS the base stack**, not the language.

```
java-maven (base)  →  java-maven-spring (flavor)
java-gradle (base) →  java-gradle-spring (flavor)
```

There is no abstract `java` base stack because Maven and Gradle share nothing worth inheriting. The language is Java in both cases, but `language` is a derived property, not an inheritance axis.

The redundancy between `java-maven-spring` and `java-gradle-spring` (both add Spring-specific capabilities) is small and acceptable. It's 3-4 extra capability entries duplicated. The alternative (mixins, multiple inheritance) is over-engineered for this scale.

This pattern applies nowhere else. Every other language has exactly one canonical build system:
- Python → pip/setuptools
- Node → npm
- Go → go mod
- Rust → cargo
- Ruby → bundler
- Elixir → mix

---

## Stack Model (implemented)

```python
class Stack(BaseModel):
    name: str
    description: str = ""
    domain: str = "service"
    icon: str = ""              # Emoji for UI rendering
    parent: str = ""            # Inherits from this stack (empty = base stack)
    detail: str = ""            # Rich description for assistant panel:
                                #   paragraph 1 = human-friendly description
                                #   paragraph 2 = technical detection/capability note
                                #   Inherited from parent if empty.

    requires: list[AdapterRequirement] = Field(default_factory=list)
    detection: DetectionRule = Field(default_factory=DetectionRule)
    capabilities: list[StackCapability] = Field(default_factory=list)
```

Fields added beyond the original 20-stack model: `icon`, `parent`, `detail`.
All optional with empty-string defaults. Fully backward compatible.

### `icon`

Single source of truth for the emoji used in dashboard cards, wizard rows, and assistant.
Eliminates 4 hardcoded `stackIcons` maps across the frontend.

### `parent`

Names the base stack this flavor inherits from. Resolved at load time by the stack loader.
Consumers receive fully-flattened stacks — they never chase parent references.

---

## Inheritance: Merge Rules

When a stack declares `parent: python`, the loader produces a resolved stack by merging:

| Field | Rule |
|-------|------|
| `name` | Child's name (never inherited) |
| `description` | Child's description (never inherited) |
| `domain` | Child's value if set, else parent's |
| `icon` | Child's value if set, else parent's |
| `detail` | Child's value if set, else parent's |
| `requires` | Parent + child, deduped by adapter name (child version wins) |
| `detection` | **Both must match**. Parent rules + child rules. Child adds additional specificity. See "Detection" below. |
| `capabilities` | Parent's list, with child entries overriding by `name`. Child can add new capabilities. |

### Capability merge example

Parent `python`:
```yaml
capabilities:
  - name: install
    command: "pip install -e ."
  - name: lint
    command: "ruff check ."
  - name: test
    command: "pytest"
```

Child `python-flask`:
```yaml
capabilities:
  - name: install           # OVERRIDES parent's install
    command: "pip install -e '.[dev]'"
  - name: serve             # NEW — added to parent's list
    command: "flask run --debug"
```

Resolved `python-flask`:
```yaml
capabilities:
  - name: install → "pip install -e '.[dev]'"    # child's version
  - name: lint → "ruff check ."                   # inherited
  - name: test → "pytest"                          # inherited
  - name: serve → "flask run --debug"              # added
```

---

## Detection: Specificity & Ordering

### Rule: more-specific stacks are checked first

The loader returns stacks ordered by specificity:
1. Stacks with `parent` (flavored) — most specific, checked first
2. Stacks without `parent` (base) — generic, checked last

Within each group, stacks with more detection rules are checked first.

### Rule: child detection inherits parent detection

When detecting, a flavored stack's detection rules are **additive** to its parent's:
- Parent `python`: `files_any_of: [pyproject.toml, setup.py, requirements.txt, Pipfile]`
- Child `python-flask`: `content_contains: {requirements.txt: "flask", pyproject.toml: "flask"}`

To match `python-flask`, BOTH must pass:
1. One of the parent's files must exist (pyproject.toml, setup.py, etc.)
2. AND one of the child's content patterns must match ("flask" found in deps)

This naturally means flavors are always subsets of their parent's matches.

### Detection for non-detectable flavors

Some flavors can't be auto-detected:
- `python-lib`: There's no reliable file signature for "this is a library, not an app". Absence of `[project.scripts]` is a weak signal (many apps lack it too).
- `go-lib`: No `main.go` is suggestive but not definitive.

These flavors have **empty child detection rules**. They can't be auto-detected — the user picks them manually in the wizard. The auto-detector would match the parent (`python`, `go`), and the user refines.

This is correct behavior. Not a gap.

---

## Target Directory Tree

```
stacks/
  # ═══════════════════════════════════════════
  # BASE LANGUAGE STACKS (no parent)
  # ═══════════════════════════════════════════

  python/stack.yml          🐍  Python project (generic)
  node/stack.yml            📦  Node.js project
  typescript/stack.yml      📘  TypeScript project
  go/stack.yml              🐹  Go project
  rust/stack.yml            🦀  Rust project
  c/stack.yml               ⚙️  C project
  cpp/stack.yml             ⚙️  C++ project
  zig/stack.yml             ⚡  Zig project
  swift/stack.yml           🍎  Swift project (SPM)
  ruby/stack.yml            💎  Ruby project
  elixir/stack.yml          💧  Elixir project (Mix)
  dotnet/stack.yml          🔷  .NET project
  java-maven/stack.yml      ☕  Java project (Maven)
  java-gradle/stack.yml     ☕  Java project (Gradle)
  protobuf/stack.yml        📡  Protocol Buffers / gRPC
  php/stack.yml             🐘  PHP project             ← NEW (Dockerfile exists, YAML missing)

  # ═══════════════════════════════════════════
  # PYTHON FLAVORS (parent: python)
  # ═══════════════════════════════════════════

  python-lib/stack.yml      🐍  Python library (no entry point)
                                domain: library
                                detection: none (user-declared)
                                capabilities: inherits all

  python-cli/stack.yml      🐍  Python CLI tool (Click/argparse)
                                domain: service
                                detection: content_contains pyproject.toml: "[project.scripts]"
                                added: run capability

  python-flask/stack.yml    🐍  Flask web application
                                domain: service
                                detection: "flask" in requirements or pyproject.toml
                                added: serve (flask run), overrides install

  python-fastapi/stack.yml  🐍  FastAPI application
                                domain: service
                                detection: "fastapi" in requirements or pyproject.toml
                                added: serve (uvicorn)

  python-django/stack.yml   🐍  Django application
                                domain: service
                                detection: manage.py exists
                                added: serve (manage.py runserver), migrate, shell

  # ═══════════════════════════════════════════
  # NODE FLAVORS (parent: node)
  # ═══════════════════════════════════════════

  node-express/stack.yml    📦  Express.js server
                                detection: "express" in package.json
                                added: serve (node index.js)

  node-nextjs/stack.yml     📦  Next.js application
                                detection: next.config.* exists
                                added: dev (next dev), overrides build

  node-react/stack.yml      📦  React SPA (CRA/Vite)
                                detection: "react" in package.json deps (no "next")
                                added: dev (npm start / vite)

  node-lib/stack.yml        📦  npm library
                                domain: library
                                detection: none (user-declared)

  # ═══════════════════════════════════════════
  # GO FLAVORS (parent: go)
  # ═══════════════════════════════════════════

  go-gin/stack.yml          🐹  Gin web framework
                                detection: "gin-gonic" in go.mod
                                added: serve

  go-fiber/stack.yml        🐹  Fiber web framework
                                detection: "gofiber" in go.mod
                                added: serve

  go-cli/stack.yml          🐹  Go CLI tool (Cobra/urfave)
                                detection: "spf13/cobra" or "urfave/cli" in go.mod

  go-lib/stack.yml          🐹  Go library
                                domain: library
                                detection: none (user-declared)

  # ═══════════════════════════════════════════
  # RUST FLAVORS (parent: rust)
  # ═══════════════════════════════════════════

  rust-actix/stack.yml      🦀  Actix-web service
                                detection: "actix-web" in Cargo.toml

  rust-axum/stack.yml       🦀  Axum web service
                                detection: "axum" in Cargo.toml

  rust-lib/stack.yml        🦀  Rust library
                                domain: library
                                detection: [lib] section in Cargo.toml

  rust-cli/stack.yml        🦀  Rust CLI tool (clap)
                                detection: "clap" in Cargo.toml

  # ═══════════════════════════════════════════
  # RUBY FLAVORS (parent: ruby)
  # ═══════════════════════════════════════════

  ruby-rails/stack.yml      💎  Ruby on Rails application
                                detection: "rails" in Gemfile, Rakefile exists
                                added: serve (rails server), migrate, console override

  ruby-sinatra/stack.yml    💎  Sinatra application
                                detection: "sinatra" in Gemfile
                                added: serve

  # ═══════════════════════════════════════════
  # ELIXIR FLAVORS (parent: elixir)
  # ═══════════════════════════════════════════

  elixir-phoenix/stack.yml  💧  Phoenix web framework
                                detection: "phoenix" in mix.exs
                                added: server (mix phx.server), routes, migrate

  # ═══════════════════════════════════════════
  # JAVA FLAVORS
  # ═══════════════════════════════════════════

  java-maven-spring/stack.yml  ☕  Spring Boot (Maven)
                                   parent: java-maven
                                   detection: "spring-boot" in pom.xml
                                   added: serve (spring-boot:run), actuator

  java-gradle-spring/stack.yml ☕  Spring Boot (Gradle)
                                   parent: java-gradle
                                   detection: "spring-boot" in build.gradle
                                   added: serve (bootRun), actuator

  # ═══════════════════════════════════════════
  # .NET FLAVORS (parent: dotnet)
  # ═══════════════════════════════════════════

  dotnet-aspnet/stack.yml   🔷  ASP.NET web application
                                detection: "Microsoft.AspNetCore" in .csproj
                                added: serve (dotnet watch)

  dotnet-blazor/stack.yml   🔷  Blazor application
                                detection: "Microsoft.AspNetCore.Components" in .csproj

  # ═══════════════════════════════════════════
  # TYPESCRIPT FLAVORS (parent: typescript)
  # ═══════════════════════════════════════════

  typescript-lib/stack.yml  📘  TypeScript library (npm package)
                                domain: library
                                detection: none (user-declared)

  # ═══════════════════════════════════════════
  # INFRASTRUCTURE STACKS (standalone)
  # ═══════════════════════════════════════════

  docker-compose/stack.yml  🐳  Docker Compose orchestration     domain: ops
  kubernetes/stack.yml      ☸️  Kubernetes manifests              domain: ops
  helm/stack.yml            ⎈  Helm charts                       domain: ops
  terraform/stack.yml       🏗️  Terraform infrastructure          domain: ops

  # ═══════════════════════════════════════════
  # CONTENT STACKS (standalone)
  # ═══════════════════════════════════════════

  static-site/stack.yml     🌐  Static site (HTML/CSS/JS)        domain: docs
  markdown/stack.yml        📝  Documentation (Markdown/Docs)    domain: docs  ← NEW
```

**Total: 16 bases + 31 flavors = 47 stacks (all implemented)**

All 47 stacks have YAML definitions with full detail fields (human-friendly description + technical note). The structure supports adding new flavors at any time by dropping a YAML file.

---

## Loader Changes (`stack_loader.py`)

### Current behavior

`discover_stacks()` → walks `stacks/*/stack.yml` → returns `dict[str, Stack]`.

### Target behavior

```python
def discover_stacks(stacks_dir: Path) -> dict[str, Stack]:
    """Discover, load, and resolve all stack definitions.

    Resolution:
    1. Load all raw stack.yml files
    2. Resolve parent references (merge capabilities, detection, etc.)
    3. Sort by specificity (flavored stacks before base stacks)

    Returns pre-resolved, flat stacks. Consumers never see parent refs.
    """
    raw = _load_all(stacks_dir)       # dict[name, Stack]
    resolved = _resolve_parents(raw)  # merge inheritance
    return resolved                   # ordered: flavors first
```

### `_resolve_parents()` logic

```
For each stack with parent != "":
  1. Find parent in raw dict (error if missing)
  2. Guard against circular references
  3. Merge:
     - domain: child's if non-default, else parent's
     - icon: child's if set, else parent's
     - requires: parent list + child list (dedup by adapter, child wins)
     - detection: UNION of rules:
         files_any_of: parent's list + child's list  (any match counts)
         files_all_of: parent's list + child's list  (all must match)
         content_contains: parent's dict merged with child's dict (child wins on conflict)
     - capabilities: parent list, child entries override by name, child extras appended
  4. Clear parent field (it's resolved, consumers see flat stacks)
```

### `detail` field content

Every stack YAML has a `detail` field with two paragraphs:
1. **Human-friendly description** — what the technology IS and when/why to use it
2. **Technical note** — prefixed with "Technical:" — detection mechanism, inherited capabilities, specific commands

The `detail` is inherited from parent if a child doesn't define its own (resolved in `_resolve_parents()`).

---

## Consumers: What Changes

### `executor.py` — `_resolve_stack()`

Before: Tries exact match, then strips suffix (`python-flask` → `python`).
After: Exact match only. Variants ARE real stacks.

The fallback to prefix-strip is kept temporarily during migration (if a variant YAML doesn't exist yet, fall back to base). Once all flavors have YAMLs, remove it.

### `detection.py` — `match_stack()`

Before: Iterates stacks in arbitrary order, returns first match.
After: Iterates in specificity order (flavored first). More-specific detection wins.

`detect_language()` stays as-is — it already does prefix matching which works correctly. The resolved stack name `python-flask` still starts with `python`, so `detect_language("python-flask")` → `"python"`.

### `detection.py` — `match_stack()` with inheritance

When checking a flavored stack:
1. Check the parent's detection rules (inherited into resolved stack)
2. Check the child's additional detection rules
3. Both must pass

Since the loader merges detection rules into one flat `DetectionRule`, this happens automatically.

### `dockerfile.py` — `_resolve_template()`

The prefix matching in `_resolve_template()` is actually CORRECT here and should stay.
Dockerfile templates are keyed by language, not framework — `python-flask` uses the Python Dockerfile.
The prefix match `python-flask → python` is the right behavior for template selection.

The one fix: add `"php"` as a base stack (already has template, missing YAML).

### UI: Icon maps

Before: Hardcoded `stackIcons` dict in `_dashboard.html` and `_wizard_helpers.html`.
After: Read from `window._dcp.stacks`:

```javascript
function stackIcon(stackName) {
    const s = (window._dcp.stacks || []).find(s => s.name === stackName);
    return s ? s.icon : '📁';
}
```

### UI: Assistant enrichment — Stack selection

The stack select dropdown in the wizard triggers `_highlightSelectedStack()` which:
1. Identifies the selected stack's language family section in the expanded content
2. Wraps the section in `<span class="assistant-stack-section">` for visual grouping
3. Marks the selected entry with `.assistant-stack-selected` and parent with `.assistant-stack-parent`
4. Inserts a styled **detail card** (`<div class="assistant-stack-detail">`) AFTER the section:
   - For **flavored stacks**: language name + description first, then `↳ framework` + description
   - For **base stacks**: stack name + description
   - Capabilities listed at the bottom
5. Scrolls the panel to center on the selected entry using `getBoundingClientRect()`

### UI: Assistant enrichment — Module list

When hovering a module in the module list, `_resolveDynamic()` builds a styled detail card
(same CSS classes as above) showing the module's stack information:
- Language + language description (from parent stack's `detail` field)
- Framework + framework description (from the stack's own `detail` field)
- Capabilities

This is rendered as HTML within the `nodeExpanded` content, not raw text.

### Server injection (`server.py`)

Full stack data injected into `window._dcp.stacks`:

```python
dcp["stacks"] = [
    {
        "name": s.name,
        "description": s.description,
        "detail": s.detail,              # Human-friendly + technical description
        "icon": s.icon,
        "domain": s.domain,
        "parent": s.parent,
        "capabilities": [c.name for c in s.capabilities],
        "capabilityDetails": [
            {"name": c.name, "command": c.command, "description": c.description, "adapter": c.adapter}
            for c in s.capabilities
        ],
        "requires": [
            {"adapter": r.adapter, "minVersion": r.min_version}
            for r in s.requires
        ],
        "detection": {
            "filesAnyOf": s.detection.files_any_of,
            "filesAllOf": s.detection.files_all_of,
            "contentContains": s.detection.content_contains,
        },
    }
    for s in sorted(stacks.values(), key=lambda s: s.name)
]
```

---

## Icons: Full Map

| Stack | Icon | Reasoning |
|-------|------|-----------|
| python (all flavors) | 🐍 | Python logo |
| node (all flavors) | 📦 | npm packages |
| typescript (all) | 📘 | Blue book (TS blue) |
| go (all) | 🐹 | Go gopher |
| rust (all) | 🦀 | Ferris the crab |
| c | ⚙️ | Systems gear |
| cpp | ⚙️ | Systems gear |
| zig | ⚡ | Fast, low-level |
| swift | 🍎 | Apple ecosystem |
| ruby (all) | 💎 | Ruby gem |
| elixir (all) | 💧 | Elixir drop |
| dotnet (all) | 🔷 | .NET blue |
| java-maven (all) | ☕ | Java coffee |
| java-gradle (all) | ☕ | Java coffee |
| protobuf | 📡 | Wire protocol |
| php | 🐘 | PHP elephant |
| docker-compose | 🐳 | Docker whale |
| kubernetes | ☸️ | K8s helm wheel |
| helm | ⎈ | Helm wheel |
| terraform | 🏗️ | Infrastructure |
| static-site | 🌐 | Web globe |
| markdown | 📝 | Writing |

Flavors inherit their parent's icon by default. The icon field in a flavor YAML can be left empty.

---

## Implementation Phases (all complete)

### Phase 1: Model & Loader ✅

- Added `icon`, `parent`, `detail` fields to `Stack` model
- Added `_resolve_parents()` to `stack_loader.py` with full merge logic
- Added icon, detail fields to all stack YAMLs
- Server injection includes all fields

### Phase 2: All 47 stacks created ✅

All base and flavored stacks have YAML definitions with:
- Detection rules, capabilities, requires
- Human-friendly descriptions + technical notes in `detail`
- Proper parent inheritance

### Phase 3: UI consolidation ✅

- Hardcoded `stackIcons` replaced with `window._dcp.stacks` lookup
- Hardcoded `stackNotes` replaced with data-driven detail cards
- Assistant catalogue references data layer for stack enrichment
- Module hover shows styled detail cards (language + framework)
- Stack select shows highlighted sections with detail block

### Phase 4: Detection ordering ✅

- Flavored stacks checked before base stacks
- Auto-detect distinguishes framework-specific stacks

### Phase 5: Executor cleanup ✅

- Prefix-strip fallback removed
- `detect_language()` prefix matching preserved (correct behavior)

### Phase 6: All flavors implemented ✅

All 47 stacks have YAML files. No remaining gaps.
