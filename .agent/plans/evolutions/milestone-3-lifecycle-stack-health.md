# Milestone 3 — Lifecycle & Stack Health
> Status: SCAFFOLDED — not yet discussed in detail

---

## Goal
Own what the project has over time — system tools, stack versions, nested projects.
Connect posture rankings to actionable upgrade/migration paths.
Let users document their decisions, not just receive warnings.

---

## Evolutions included

### E3 — Environment & Tool Lifecycle Ownership
Connect the posture system (which ranks tools) to the tool installer (which manages them):
- OUTDATED tool → platform offers upgrade plan
- DEPRECATED tool → platform surfaces migration path
- Configuration drift → platform detects and proposes fix
- All lifecycle actions reversible with audit trail

### E8 — Stack Version Advisor & Annotated Decisions
Connect stack detection + posture rankings into actionable upgrade guidance:
- Layer 1: When a stack is OUTDATED/DEPRECATED, show the upgrade path at module level
  - What the upgrade touches (deps, configs, Dockerfile, CI)
  - Scoped, guided migration
- Layer 2: User annotates version decisions
  - "Staying on Node 18 — vendor SDK doesn't support 20 yet"
  - Annotation is audited, visible in timeline, stops platform from re-flagging
  - Decision is a first-class traceable record

### E2 — Nested Project Support
Extend multi-module detection to handle project-in-project:
- Detect sub-projects as independent units (nested git, separate dep trees)
- Offer independent or parent-scoped management
- Relatively targeted — multi-module foundation is already solid

---

## What this milestone does NOT include
- Project-level package management (M2)
- Release/promotion flow (M4)

---

## Dependencies
- M1: security view surfaces tool/stack posture issues; timeline records lifecycle actions
- M2: dependency graph informs stack upgrade impact (what does upgrading this stack touch?)

## Unlocks
- M4: tool and stack state feeds the readiness score; lifecycle events feed the changelog

---

## Open questions
- [ ] Where do annotated decisions live in the UI? (inline on the stack card? dedicated view?)
- [ ] What is the upgrade recipe format? (extension of existing tool recipes?)
- [ ] How does configuration drift detection work per tool?
- [ ] For nested projects — does the platform create a separate project.yml per sub-project?
- [ ] How does E2 interact with the existing module detection system?

---

## Rough scope estimate
- E3: Backend (connect posture → tool_install, upgrade/migrate recipes) + Frontend (lifecycle action surface)
- E8: Backend (upgrade path generator, annotation storage) + Frontend (annotated stack card, decision history)
- E2: Backend (nested detection logic) — relatively small, targeted extension
