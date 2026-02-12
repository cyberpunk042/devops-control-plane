# Stacks Guide

> How to use and create stack definitions.

---

## What is a Stack?

A **stack** defines how to detect and interact with a particular technology. For example, a `python` stack knows to look for `pyproject.toml` and can run `pytest` for testing and `ruff` for linting.

Stacks live in the `stacks/` directory, each in its own subdirectory:

```
stacks/
├── c/                  ├── kubernetes/
├── cpp/                ├── node/
├── docker-compose/     ├── protobuf/
├── dotnet/             ├── python/
├── elixir/             ├── ruby/
├── go/                 ├── rust/
├── helm/               ├── static-site/
├── java-gradle/        ├── swift/
├── java-maven/         ├── terraform/
│                       ├── typescript/
│                       └── zig/
```

---

## Built-in Stacks (20)

### Service Stacks — Languages

| Stack | Language | Detects | Capabilities |
|---|---|---|---|
| `python` | Python | `pyproject.toml`, `setup.py`, `setup.cfg`, `requirements.txt`, `Pipfile` | install, lint, format, test, types |
| `node` | JavaScript | `package.json` | install, lint, format, test, build |
| `typescript` | TypeScript | `tsconfig.json` + `package.json` (both required) | install, lint, format, test, build, compile, types |
| `go` | Go | `go.mod` | install, lint, format, test, build, vet |
| `rust` | Rust | `Cargo.toml` | install, lint, format, test, build, check |
| `ruby` | Ruby | `Gemfile`, `Rakefile` | install, lint, format, test, console |
| `java-maven` | Java | `pom.xml` | install, lint, test, build, clean, verify |
| `java-gradle` | Java/Kotlin | `build.gradle`, `build.gradle.kts` | install, lint, test, build, clean |
| `dotnet` | C# | `Directory.Build.props`, `global.json`, `nuget.config` | install, lint, format, test, build, clean |
| `swift` | Swift | `Package.swift` | install, build, test, clean, format, lint |
| `elixir` | Elixir | `mix.exs` | install, lint, format, test, build, types |
| `zig` | Zig | `build.zig`, `build.zig.zon` | build, test, format, clean |

### Service Stacks — Low-Level

| Stack | Language | Detects | Capabilities |
|---|---|---|---|
| `c` | C | `CMakeLists.txt`, `Makefile`, `configure.ac`, `meson.build` | install (configure), build, test, clean, lint (cppcheck), format (clang-format) |
| `cpp` | C++ | `CMakeLists.txt` containing `CXX` | install (cmake), build (parallel), test, clean, lint, format |

> **Note:** `cpp` is distinguished from `c` via `content_contains` — it requires `CMakeLists.txt` to contain the string `CXX`.

### Ops / Infrastructure Stacks

| Stack | Language | Detects | Capabilities |
|---|---|---|---|
| `docker-compose` | — | `docker-compose.yml`, `compose.yml` (+ `.yaml` variants) | up, down, build, logs, status |
| `kubernetes` | YAML | `kustomization.yaml`, `kustomization.yml`, `skaffold.yaml` | lint (dry-run), apply, diff, status, build (kustomize), delete |
| `terraform` | HCL | `main.tf`, `terraform.tf`, `versions.tf` | install (init), lint (validate), format, plan, apply, status |
| `helm` | YAML | `Chart.yaml` | install (dep update), lint, test (dry-run), build (package), status |

### Docs / Frontend Stacks

| Stack | Language | Detects | Capabilities |
|---|---|---|---|
| `static-site` | HTML | `index.html` | lint (htmlhint), format (prettier), test (lighthouse), serve |
| `protobuf` | Protobuf | `buf.yaml`, `buf.gen.yaml`, `buf.work.yaml` | lint, format, build (generate), test (breaking) |

---

## Stack Definition

### `stack.yml` Format

```yaml
name: python                    # Unique identifier
description: "Python project"   # Human-readable description
domain: service                 # Default domain (service, library, ops, docs)

detection:
  files_any_of:                 # Module detected if ANY of these files exist
    - pyproject.toml
    - setup.py
    - requirements.txt
  files_all_of: []              # All must exist (optional — strict matching)
  content_contains: {}          # file: string — file must contain string

requires:                       # Optional: external tool requirements
  - adapter: python
    min_version: "3.8"

capabilities:                   # What can be done with this stack
  - name: test
    adapter: shell              # Which adapter executes this
    command: "pytest"            # Command string
    description: "Run tests"
```

---

## Fields Reference

### Top-Level

| Field | Required | Description |
|---|---|---|
| `name` | ✓ | Unique stack identifier |
| `description` | | Human-readable description |
| `domain` | | Default domain for modules using this stack |

### Detection

| Field | Description |
|---|---|
| `files_any_of` | Module detected if ANY of these files exist in its directory |
| `files_all_of` | Module detected only if ALL of these files exist |
| `content_contains` | Map of `filename: string` — file must contain the string |

The detection engine scans each configured module's path for these markers.
Multiple detection rules are AND-ed together: if both `files_any_of` *and*
`content_contains` are specified, both must match.

### Capabilities

| Field | Required | Description |
|---|---|---|
| `name` | ✓ | Capability name (e.g., `test`, `lint`, `build`) |
| `command` | ✓ | Command to execute |
| `adapter` | | Adapter to use (default: `shell`). See [ADAPTERS.md](ADAPTERS.md) |
| `description` | | What this capability does |

---

## Stack Variants

You can create specialised variants by adding a suffix:

```
stacks/
├── python/          # Base Python stack
│   └── stack.yml
├── python-strict/   # Strict mode (mypy --strict, ruff --select ALL)
│   └── stack.yml
├── python-flask/    # Flask web app (gunicorn serve, flask routes)
│   └── stack.yml
├── python-cli/      # CLI tool (pyinstaller build)
│   └── stack.yml
└── node-esm/        # Node.js ESM-only (type: module)
    └── stack.yml
```

In `project.yml`, reference the specific variant:

```yaml
modules:
  - name: api
    stack: python-flask   # Uses the Flask variant
  - name: utils
    stack: python-strict  # Uses strict type checking
  - name: frontend
    stack: node-esm       # ESM-only Node project
```

The engine resolves variants by exact name, then falls back to the longest
matching prefix (e.g., `python-flask` → `python` for language detection).

### Example Variants to Consider

| Variant | Differences from Base |
|---|---|
| `python-strict` | `mypy --strict`, stricter ruff rules, requires 3.11+ |
| `python-flask` | Adds `serve` capability (`gunicorn`), `routes` capability |
| `node-esm` | ESM module tests, `"type": "module"` detection |
| `typescript-strict` | `tsc --strict --noUncheckedIndexedAccess` |
| `rust-wasm` | Adds `wasm-pack build` capability |
| `java-spring` | Adds `bootRun` capability for Spring Boot |

---

## Version Detection

The detection engine automatically extracts version information from:

| Stack | Source |
|---|---|
| Python | `pyproject.toml` → `version = "x.y.z"` |
| Node / TypeScript | `package.json` → `"version": "x.y.z"` |
| Go | `go.mod` → `go 1.22` directive |
| Rust | `Cargo.toml` → `version = "x.y.z"` |
| Elixir | `mix.exs` → `version: "x.y.z"` |
| Helm | `Chart.yaml` → `version: x.y.z` |

---

## Conventions

1. **Consistent capability names** — Use the same names (`install`, `test`, `lint`, `format`, `build`) across stacks so you can run `./manage.sh run test` against any module regardless of technology
2. **Detection is non-destructive** — Running `detect` just scans; it never modifies your project files
3. **Stack discovery is automatic** — Any `stack.yml` in `stacks/*/` is loaded at startup
4. **Adapter flexibility** — Capabilities default to `shell` but can reference any registered adapter (`git`, `docker`, `python`, `node`, or custom). See [ADAPTERS.md](ADAPTERS.md)
5. **Graceful degradation** — Stacks for optional tools (htmlhint, lighthouse, cppcheck) use `2>/dev/null || echo 'not available'` fallbacks
