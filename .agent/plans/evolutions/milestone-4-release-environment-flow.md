# Milestone 4 — Release & Environment Flow
> Status: SCAFFOLDED — not yet discussed in detail

---

## Goal
Give the project a deliberate, audited flow from development to production.
Readiness before promotion. Filtered, safe promotion. Intelligent release artifacts.

---

## Evolutions included

### E9 — Project Readiness Score (prerequisite — implement first)
Aggregate all signals from M1-M3 into a single readiness score per environment:
- Security posture (E7)
- Dependency health (E1, E10)
- Tool/stack lifecycle state (E3, E8)
- CI status, test coverage, backup policy, env completeness
- "Your staging is 84% ready for production promotion"
- Each gap is actionable — links directly to the thing that fixes it

### E5 — Multi-Environment Promotion Pipeline (depends on E9)
Structured, audited flow from dev → staging → production:
- Filtered promotion: strips dev-only keys, local overrides, mock flags
- Diff view before push: what travels, what gets dropped
- Approval gate before anything moves
- Optional health/test gate
- Full rollback via backup snapshots
- Every promotion is a ledger entry

### E4 — Changelog & Release Intelligence (benefits from E9 + E5)
Generate changelogs from real signals across the full project surface:
- Packages bumped (E1/E2 data)
- Config modified (vault/env diff)
- Infra updated (Dockerfile, K8s, Terraform)
- Secrets rotated (vault audit)
- Tools upgraded (E3 lifecycle history)
- Stack annotations added (E8)
- Release workflow: changelog → version bump → tag → publish

---

## What this milestone does NOT include
- Notification routing (M5 — but this milestone produces the events M5 needs)

---

## Dependencies
- M1: security score feeds readiness; timeline records promotions
- M2: dependency health feeds readiness; package changes feed changelog
- M3: tool/stack state feeds readiness; lifecycle events feed changelog

## Unlocks
- M5: promotion events, readiness drops, and release completions become notification triggers

---

## Open questions
- [ ] What is the readiness score formula? Which signals, which weights?
- [ ] How are "dev-only keys" identified? (existing tier metadata? manual tagging?)
- [ ] Does the promotion gate block or warn? (configurable per environment?)
- [ ] What does the changelog UI look like? (diff view? grouped by domain?)
- [ ] How does version bump work — semver only? manual override?
- [ ] What does rollback cover exactly? (env vars only? or full state snapshot?)

---

## Rough scope estimate
- E9: Backend (score aggregator) + Frontend (readiness dashboard per environment)
- E5: Backend (promotion engine, diff generator) + Frontend (promotion wizard, diff view)
- E4: Backend (multi-signal changelog generator) + Frontend (changelog editor + release action)
- Strict implementation order: E9 → E5 → E4
