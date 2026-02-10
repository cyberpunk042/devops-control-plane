# Stacks Guide

> How to create and customize stack definitions.

---

## What is a Stack?

A **stack** defines how to detect and interact with a particular technology. For example, a `python` stack knows to look for `pyproject.toml` and can run `pytest` for testing and `ruff` for linting.

Stacks live in the `stacks/` directory, each in its own subdirectory:

```
stacks/
├── python/
│   └── stack.yml
├── node/
│   └── stack.yml
└── docker-compose/
    └── stack.yml
```

---

## Stack Definition

### `stack.yml` Format

```yaml
name: python                    # Unique identifier
description: "Python project"   # Human-readable description
domain: service                 # Default domain (service, library, docs, etc.)

detection:
  files_any_of:                 # Module detected if ANY of these files exist
    - pyproject.toml
    - setup.py
    - requirements.txt

requires:                       # Optional: external tool requirements
  - adapter: python
    min_version: "3.8"

capabilities:                   # What can be done with this stack
  - name: test
    adapter: shell              # 'shell' is the default
    command: "pytest"
    description: "Run tests"

  - name: lint
    command: "ruff check ."
    description: "Run linter"

  - name: build
    command: "python -m build"
    description: "Build package"
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
| `files_any_of` | List of filenames — module detected if ANY exist |

The detection engine scans each configured module's path for these marker files. If at least one is found, the module is matched to this stack.

### Capabilities

| Field | Required | Description |
|---|---|---|
| `name` | ✓ | Capability name (e.g., `test`, `lint`, `build`) |
| `command` | ✓ | Shell command to execute |
| `adapter` | | Adapter to use (default: `shell`) |
| `description` | | What this capability does |

---

## Creating a Custom Stack

### Example: Ruby Stack

```yaml
name: ruby
description: "Ruby/Rails project"
domain: service

detection:
  files_any_of:
    - Gemfile
    - Rakefile

capabilities:
  - name: install
    command: "bundle install"
    description: "Install dependencies"

  - name: test
    command: "bundle exec rspec"
    description: "Run RSpec tests"

  - name: lint
    command: "bundle exec rubocop"
    description: "Run RuboCop"

  - name: build
    command: "bundle exec rake build"
    description: "Build gem"
```

Save as `stacks/ruby/stack.yml`, then run `./manage.sh detect` to pick up modules using this stack.

### Example: Go Stack

```yaml
name: go
description: "Go project"
domain: service

detection:
  files_any_of:
    - go.mod
    - go.sum

capabilities:
  - name: test
    command: "go test ./..."
  - name: lint
    command: "golangci-lint run"
  - name: build
    command: "go build ./..."
```

---

## Stack Variants

You can create specialized variants by adding a suffix:

```
stacks/
├── python/          # Base Python stack
│   └── stack.yml
├── python-lib/      # Python library (different test/build)
│   └── stack.yml
├── python-flask/    # Flask web app
│   └── stack.yml
└── python-cli/      # CLI tool
    └── stack.yml
```

In `project.yml`, reference the specific variant:

```yaml
modules:
  - name: api
    stack: python-flask   # Uses the Flask variant
  - name: utils
    stack: python-lib     # Uses the library variant
```

The engine resolves variants by trying exact match first, then falling back to the base name (e.g., `python-flask` → `python`).

---

## Tips

1. **Keep capabilities consistent** — Use the same names (`test`, `lint`, `build`, `deploy`) across stacks so you can run `./manage.sh run test` against any module
2. **Use adapter: shell** — The shell adapter handles command execution, environment variables, and working directory setup
3. **Detection is non-destructive** — Running `detect` just scans; it never modifies your project files
4. **Stack discovery is automatic** — Any `stack.yml` in `stacks/*/` is loaded automatically
