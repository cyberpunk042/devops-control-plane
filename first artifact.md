# Project Root Architecture — Scalable Foundation

This document defines the **canonical root structure** for the project.  
It is designed to scale by **peeling branches**, not by accumulating clutter.

The structure enforces:
- clear separation of intent vs tooling
- predictable growth paths
- shared logic across CLI, Web, and Console
- long-term maintainability

---

## Core Principle

**Everything is a domain object first.**

Scripts, templates, CI, infrastructure, and tools are *expressions* of intent — never the source of truth.

If something cannot be expressed as a domain concept, it does not belong in the system.

---

## Root Directory Layout (Invariant)

Nothing outside this list is allowed at the root.

```
project-root/
├─ project.yml
├─ state/
├─ core/
├─ adapters/
├─ ui/
├─ modules/
├─ stacks/
├─ templates/
├─ automations/
├─ docs/
├─ scripts/
└─ .proj/
```

Each directory has a **single responsibility**.

---

## project.yml — Canonical Truth

This file defines *what the project is*, not how tools implement it.

Responsibilities:
- project identity
- domains and environments
- declared modules and stacks
- external system links

Discovery may enrich this model but must never contradict it.

---

## state/ — Observed Reality (Generated)

Contains cached, generated, or discovered data:
- detected stacks and versions
- environment checks
- last-known tool availability
- graph snapshots

This directory is disposable and reproducible.

---

## core/ — Domain & Use-Cases (Tool-Free)

The heart of the system.

Rules:
- no shell execution
- no direct tool imports
- pure domain logic only

Contains:
- domain models (Project, Module, Stack, Action, Environment)
- services (detection, planning, validation, graph building)
- use-cases (detect, scaffold, run automation, generate graphs)

All UIs and automations call into this layer.

---

## adapters/ — Tool Bindings

Adapters translate domain intent into real-world effects.

Examples:
- git, github
- docker, compose
- kubectl, helm
- python, node
- shell, filesystem

Adapters:
- declare capabilities and versions
- report side effects
- can be mocked or replaced

---

## ui/ — Interfaces (Thin Only)

Multiple interfaces, one engine.

```
ui/
├─ cli/
├─ web/
└─ tui/
```


Rules:
- no business logic
- no direct tool calls
- all actions route through core use-cases

CLI, Web, and Console must remain functionally equivalent.

---

## modules/ — Project Components

Represents the user’s actual project structure.

Each module contains:
- a module descriptor
- its own source and config
- no global assumptions

Modules are classified by domain:
- service
- library
- infra
- ops
- docs

---

## stacks/ — Technology Knowledge

Stacks define *how a kind of module behaves*.

A stack may include:
- detection logic
- default configurations
- compatible automations
- version constraints

Stacks are reusable across modules and projects.

---

## templates/ — File Shape Only

Templates are **dumb**.

They:
- render files
- contain no detection
- contain no logic
- never call tools

Logic belongs in stacks or core use-cases.

---

## automations/ — Named Capabilities

Automations represent **what can be done**, not scripts.

Each automation:
- declares prerequisites
- defines ordered steps
- resolves to adapters at runtime

This enables:
- dry-runs
- dependency graphs
- reuse across CLI, Web, and CI

---

## docs/ — Living Documentation

Documentation is part of the system, not an afterthought.

Includes:
- architecture explanations
- domain definitions
- generated diagrams
- operational guidance

---

## scripts/ — Thin Wrappers

Scripts are allowed only as:
- entrypoints
- convenience shims
- backward-compat helpers

No logic is allowed here.

---

## .proj/ — Internal Metadata

Private system metadata:
- internal indexes
- caches
- version markers

Ignored by users and tooling.

---

## Growth Rules (Non-Negotiable)

If a change requires touching:
- core + adapters → acceptable
- core + ui → acceptable
- adapters + ui → acceptable
- **three or more layers → design error**

New capabilities must emerge as **branches**, never as root mutations.

---

## Outcome

This structure ensures:
- natural scalability
- explicit boundaries
- consistent automation
- shared intelligence across interfaces
- long-term clarity

This is the foundation. Everything else grows from here.
