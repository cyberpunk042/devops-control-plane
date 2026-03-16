# Audit-to-Git & Run Operations — Master Plan

> **Created**: 2026-02-18  
> **Status**: Planning  
> **Goal**: Make every DevOps card scan a saveable audit, every integration action a trackable Run, and both referenceable in chat.

---

## Problem Statement

Today, card scan results vanish into the cache. The user has no way to:
1. **Persist** a scan snapshot to git for cross-machine sharing
2. **Reference** a specific scan result in a chat message (`@audit:xxx`)
3. **Track** operational actions (install, build, deploy) as discrete Run entities
4. **Preview** what a `@run:` or `@audit:` reference resolves to before sending a message

## Three Concepts

| # | Concept | Summary |
|---|---------|---------|
| **C1** | **Audit-to-Git** | Every cache computation = audit scan. Offer save-to-git or discard. Badge on card → Audit Manager Modal for batch ops. Saved = referenceable as `@audit:` in chat. |
| **C2** | **Run Operations** | Every integration action (install, build, deploy, setup) = Run. Uses existing `Run` model + `record_run()`. Wire into CI/CD, Docker, K8s, Terraform, Pages, and setup flows. Referenceable as `@run:` in chat. |
| **C3** | **Pre-embed Preview** | When composing a chat message, resolving `@audit:` or `@run:` shows an inline preview card before submit. |

## Architecture Overview

```
                        ┌──────────────────────────────────┐
                        │      devops_cache.get_cached()   │
                        │   (every card scan = audit scan)  │
                        └──────────┬───────────────────────┘
                                   │ cache:done SSE
                    ┌──────────────┼──────────────────────┐
                    ▼              ▼                      ▼
            ┌──────────┐  ┌────────────────┐   ┌───────────────┐
            │  Cache    │  │ Pending Audit  │   │   SSE Event   │
            │ (as-is)  │  │ Staging Area   │   │ audit:pending │
            └──────────┘  │ .state/pending │   └───────┬───────┘
                          │ _audits.json   │           │
                          └───────┬────────┘           ▼
                                  │            ┌───────────────┐
                        ┌────────▼─────────┐   │  Card Badge   │
                        │ POST /api/audits │   │  (click →     │
                        │ /save or /discard│   │   modal)      │
                        └────────┬─────────┘   └───────────────┘
                                 │ save
                                 ▼
                        ┌──────────────────┐
                        │ .scp-ledger/     │
                        │ audits/<id>.json │
                        │ + git tag        │
                        └────────┬─────────┘
                                 │ referenceable
                                 ▼
                        ┌──────────────────┐
                        │ @audit:<id>      │
                        │ in chat messages │
                        └──────────────────┘

         ┌────────────────────────────────────────────┐
         │  Integration action (build/install/deploy)  │
         └──────────────┬─────────────────────────────┘
                        │ record_run()
                        ▼
         ┌──────────────────────────┐
         │ Run model (git tag)      │─────► @run:<id> in chat
         │ .scp-ledger/ledger/runs/ │
         │ SSE: run:started/done    │
         └──────────────────────────┘
```

## Existing Infrastructure (leveraged, not rebuilt)

| Component | Location | Role |
|-----------|----------|------|
| `devops_cache.get_cached()` | `src/core/services/devops_cache.py` | Cache + SSE publish on compute |
| `_record_activity()` | `src/core/services/devops_activity.py` | Local activity log per scan |
| `_publish_event()` | `src/core/services/devops_cache.py` | SSE bus publish (fail-safe) |
| `AuditEntry` + `AuditWriter` | `src/core/persistence/audit.py` | Append-only NDJSON execution log |
| `audit_helpers.make_auditor()` | `src/core/services/audit_helpers.py` | Per-card audit event helper |
| `Run` + `RunEvent` models | `src/core/services/ledger/models.py` | Run tracking model (git tags + JSONL) |
| `record_run()` | `src/core/services/ledger/ledger_ops.py` | Write Run to ledger + tag |
| `get_run()` / `get_run_events()` | `src/core/services/ledger/ledger_ops.py` | Read Runs from tags/worktree |
| `_resolve_audit()` / `_resolve_run()` | `src/core/services/chat/chat_refs.py` | Chat ref resolvers |
| SSE `_event_stream.html` | `src/ui/web/templates/scripts/` | Frontend SSE client + state store |
| Card HTML (9 DevOps + 7 Integrations) | `templates/partials/_tab_devops.html`, `_tab_integrations.html` | Card layout with badge + detail |

## Phase Index

| Phase | Document | Scope | Dependencies |
|-------|----------|-------|--------------|
| **Phase 1** | [01-audit-pending-backend.md](./01-audit-pending-backend.md) | Pending audit staging area, save/discard API, ledger persistence | None |
| **Phase 2** | [02-audit-ui-badge-modal.md](./02-audit-ui-badge-modal.md) | Card badge, SSE listener, Audit Manager Modal | Phase 1 |
| **Phase 3** | [03-audit-chat-ref.md](./03-audit-chat-ref.md) | Upgrade `@audit:` resolver to read from ledger, autocomplete saved audits | Phase 1 |
| **Phase 4** | [04-run-ops-backend.md](./04-run-ops-backend.md) | Wire `record_run()` into integration actions, SSE events, Run sub-types | None (parallel with P1-P3) |
| **Phase 5** | [05-run-ops-ui.md](./05-run-ops-ui.md) | Run badges on integration cards, run details in chat `@run:` refs | Phase 4 |
| **Phase 6** | [06-pre-embed-preview.md](./06-pre-embed-preview.md) | Inline ref preview in chat compose area before submit | Phase 3, Phase 5 |

## Resolved Questions

| # | Question | **Answer** |
|---|----------|-----------|
| **Q1** | Audit snapshot = full card data dict or summary only? | ✅ **Full card data blob** — the entire compute result is stored. |
| **Q2** | Pending audits survive server restart? | ✅ **Yes** — persisted to `.state/pending_audits.json`, same pattern as the cache. |
| **Q3** | Which integration actions are RUN-trackable today? | ✅ **~70 POST action routes** across 36 route files. Full inventory in Phase 4. Solved with `@run_tracked` decorator pattern for scalability. |
| **Q4** | Should the Audit Manager Modal be a dedicated overlay or use `modalOpen()`? | ✅ **Dedicated overlay** — list/batch semantics don't fit the single-modal pattern. |

## Design Principles

1. **Cache is untouched** — saving/discarding an audit never invalidates the cache
2. **SSE is the notification bus** — no polling for pending audits
3. **Ledger branch is the persistence layer** — `.scp-ledger/audits/` for audits, `.scp-ledger/ledger/runs/` for runs (runs already use this)
4. **Badge is the entry point** — user clicks badge → modal. Never auto-open.
5. **Every action = a Run** — if it changes state (install, build, deploy, setup), it's a Run
6. **Every scan = an audit** — if `get_cached()` computes, it's an audit snapshot candidate
7. **Decorator pattern for scalability** — `@run_tracked` decorator makes wiring new routes trivial (1 line per route)

## File Impact Summary

### Backend (new or modified)
- `src/core/services/audit_staging.py` — **NEW** — pending audit staging area
- `src/core/services/run_tracker.py` — **NEW** — `@run_tracked` decorator + `tracked_run()` context manager
- `src/core/services/devops_cache.py` — **MODIFIED** — emit `audit:pending` on compute (~6 lines)
- `src/core/services/ledger/ledger_ops.py` — **MODIFIED** — `save_audit_snapshot()`
- `src/core/services/chat/chat_refs.py` — **MODIFIED** — upgraded `_resolve_audit()`, `_resolve_run()`
- `src/ui/web/routes_audit.py` — **MODIFIED** — pending/save/discard endpoints
- **~15 integration route files** — **MODIFIED** — add `@run_tracked` decorator to ~70 POST routes (1 line each)

### Frontend (new or modified)
- `_event_stream.html` — **MODIFIED** — handle `audit:pending`, `run:started`, `run:completed`
- `_tab_devops.html` — **MODIFIED** — add audit badge placeholder to each card
- `_tab_integrations.html` — **MODIFIED** — add audit/run badge placeholders
- `_audit_manager_modal.html` — **NEW** — dedicated Audit Manager overlay
- `_content_chat.html` — **MODIFIED** — pre-embed preview area in compose
- `_content_chat_refs.html` — **MODIFIED** — pre-embed resolve + render
- `admin.css` — **MODIFIED** — badge styles, modal styles, pre-embed styles
