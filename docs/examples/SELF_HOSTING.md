# Example: Self-Hosting

> This repository uses the Control Plane to manage itself.

---

## How It Works

The `project.yml` at the project root defines the control plane itself as a project:

```yaml
name: devops-control-plane
description: A general-purpose project control plane for DevOps automation
repository: github.com/cyberpunk042/devops-control-plane

modules:
  - name: core
    path: src/core
    stack: python-lib
    domain: library
  - name: adapters
    path: src/adapters
    stack: python-lib
    domain: library
  - name: cli
    path: src/ui/cli
    stack: python-cli
    domain: ops
  - name: web
    path: src/ui/web
    stack: python-flask
    domain: ops
  - name: docs
    path: docs
    stack: markdown
    domain: docs

environments:
  - name: dev
    default: true
  - name: test
  - name: production
```

## Running Against Itself

```bash
# Detect its own modules
./manage.sh detect

# Run tests on itself
./manage.sh run test

# Lint itself
./manage.sh run lint

# Check its own health
./manage.sh health
```

## What This Demonstrates

1. **Multi-module projects** — 5 modules across different domains
2. **Stack variants** — `python-lib`, `python-cli`, `python-flask`, `markdown`
3. **Environment support** — dev, test, production
4. **Self-description** — the tool describes and manages itself
