# Evolution Milestones — Index
> Scaffolded March 14, 2026. Each milestone has its own document for deep discussion.

---

## Overview

| Milestone | Name | Evolutions | Depends On |
|-----------|------|------------|------------|
| [M1](milestone-1-observability-foundation.md) | Observability Foundation | #6, #7 | — |
| [M2](milestone-2-dependency-intelligence.md) | Dependency Intelligence | #1, #10 | M1 |
| [M3](milestone-3-lifecycle-stack-health.md) | Lifecycle & Stack Health | #3, #8, #2 | M1, M2 |
| [M4](milestone-4-release-environment-flow.md) | Release & Environment Flow | #9, #5, #4 | M1, M2, M3 |
| [M5](milestone-5-proactive-intelligence.md) | Proactive Intelligence | #11 | M1–M4 |

---

## Rationale for ordering

- **M1 first** — builds read surfaces (timeline, security view) that all other milestones depend on for data and UX patterns
- **M2 second** — project dependencies become first-class; dependency graph informs M3 (lifecycle) and M4 (readiness)
- **M3 third** — tool and stack lifecycle ownership; produces the state signals M4's readiness score needs
- **M4 fourth** — promotion and release flow; requires readiness signals from M1-M3 to be meaningful
- **M5 last** — notifications are only valuable once M1-M4 have produced real signals to route

---

## Source document
Full evolution ideas: `.agent/docs/product-evolutions.md`
