# Milestone 1 — Observability Foundation
> Status: DESIGNED (E6) / PENDING (E7) — E6 foundation requirements complete; E7 design deferred

---

## Goal
Make what already exists in the platform *visible* in unified ways.
No new operations. Pure read surfaces. Low risk, high value.
Everything downstream depends on these surfaces.

---

## Evolutions included

### E6 — Project Timeline & Activity Intelligence
A unified chronological view of all events across all domains.
The Timeline is a **new dedicated tab** — not a replacement of the existing Audit Log. The Audit Log tab continues to exist. The Timeline aggregates audit log data alongside 16 other sources into one unified, filterable, chain-aware surface.

**What already exists (investigated):**

| Source | Location | Shape | Limit |
|--------|----------|-------|-------|
| Scan activity | `.state/audit_activity.json` | `{ts, iso, card, label, status, duration_s, summary, bust, action?, target?, before?, after?, detail?}` | 200 entries, rotated |
| CLI operations | `.state/audit.ndjson` | `{timestamp, operation_id, operation_type, automation, environment, modules_affected, status, actions_total/succeeded/failed, duration_ms, errors, context}` | append-only NDJSON |
| Ledger runs | `.ledger/` git branch | `Run {run_id, type, subtype, status, user, code_ref, started_at, ended_at, environment, modules_affected, summary}` + JSONL events | git tags `scp/run/*` |
| Ledger audits | `.ledger/` git branch | `audits/<id>.json` | git tags `scp/audit/*` |
| Chat threads | `.ledger/chat/` | `Thread + Message` with `publish` flag | git branch |
| Event bus | runtime only | typed events (`cache:done`, `stream:*`, `error:new`, `ledger:conflict`, `chat:*`, etc.) | ephemeral, not persisted |

**What the current Audit Log shows:**
- Two separate views: Scan Activity (card-level scans) + CLI Operations (operation records)
- Each view is siloed — no unified sort, no date-range filter, no domain filter
- Scan activity capped at 200 entries; no history beyond that

**What the Timeline needs that doesn't exist yet:**
- Git commit reader (local git log, not in any current UI source)
- CI run reader (not yet surfaced — ledger or external CI)
- A unified aggregator service that merges all sources into a single time-ordered feed
- Date-range query beyond the 200-entry cap (requires reading ledger branch)
- The local/shared (⬡/⇡) flag per entry — derivable from git state, but not currently computed

**Integration point:** The Timeline lives in its own dedicated tab. The existing Audit Log tab is untouched. Timeline consumes audit data as one of its 17 sources.

### E7 — Security Posture as a First-Class Citizen
Consolidate fragmented security signals into one view.
- Sources: audit (L0/L1/L2), security scanning, vault status, secrets detection
- Single aggregated security score
- Priority-ranked list of open issues
- Direct link to remediation for each finding

---

## What this milestone does NOT include
- No new operations
- No new data collection (reads existing ledger/signals only)
- No notification routing (that's M5)

---

## Dependencies
- None — M1 is the foundation

## Unlocks
- M2: dependency operations will emit timeline events
- M3: tool lifecycle state will appear in the security view
- M4: security score feeds the readiness score
- M5: security signals become notification sources

---

## Timeline — Target UI Design

```
┌─────────────────────┬──────────────────────────────────────────────────────────────┐
│ NAVIGATOR           │ TIMELINE — my-project                            ⟳ Live      │
│ ─────────────────── │ ─────────────────────────────────────────────────────────── │
│ 📎 Chains           │ [GIT▾][AUDIT▾][+3▾]  [⚠▾]  [desc▾]   🔍 search...          │
│ 🌐 Domains          │ [⬡ Local]  [⇡ Shared]  [● All]                              │
│ 📅 Calendar         ├── TODAY — March 14, 2026 ──────────────────────────────────┤
│ ─────────────────── │                                                              │
│ 🔍 filter...        │  ● ⇡  [GIT]   fix: bugs — 5 ins, 1 del          10:33      │
│                     │                                                              │
│ ── Active chains ── │  ● ⬡  [PKG]   cryptography → 42.0.5             10:24      │
│                     │                                                              │
│ 📎 Audit L2 (2)     │  ◑ ⬡  [AUDIT] L2 scan — 3 findings  🔗         08:51 ─┐   │
│  ○ ⬡ L2 ran  08:51  │                                                        │   │
│→ ● ⇡ committed 10:30│  ● ⇡  [CHAT]  "wsl transport" — 4 msgs          08:30  │   │
│                     ├── YESTERDAY — March 13, 2026 ──────────────────────────┤   │
│ 📎 feat:posture (2) │                                                        │   │
│  ○ ⇡ commit  14:55  │  ● ⇡  [CI]    Build passed — main ✓ (2m 14s)   17:44  │   │
│→ ● ✕ CI fail 15:20  │                                                        │   │
│                     │  ◑ ⬡  [PKG]   npm audit — 2 moderate CVEs       17:40  │   │
│ 📎 wsl thread (5)   │                                                        │   │
│  ○ ⇡ created 08:30  │  ● ⇡  [TESTS] Test suite — 94/94 passed         16:10  │   │
│  · ⇡ msg     09:15  │                                                        │   │
│  · ⇡ msg     10:45  │  ● ⬡  [BACKUP] Snapshot #47 created — dev       14:22  │   │
│  · ⇡ msg     11:30  │                                                        │   │
│→ ● ⇡ msg     12:10  │  ● ⇡  [PLAN]  Exec plan committed — wsl-refactor 13:45 │   │
│                     │                                                        │   │
│ ── Domains ──────── │  ⚠ ⬡  [POSTURE] Node 18 → OUTDATED (EOL 11mo)  11:05  │   │
│ ⚡ GIT    (3)       │                                                        │   │
│ ⚡ AUDIT  (2)       │  ● ⇡  [AUDIT] L2 committed — 7 findings  🔗     10:30 ─┘   │
│ ⚡ PKG    (2) ▸     │       ↳ chain: Audit L2 Lifecycle   [view chain]            │
│ ⚡ CI     (2)       │                                                              │
│ ⚡ CHAT   (5)       ├── March 12, 2026 ─────────────────────────────────────────┤
│ ⚡ BACKUP (1)       │                                                              │
│ ⚡ PLAN   (1)       │  ✕ ⇡  [CI]    Build failed — lint error  🔗      15:20 ─┐  │
│ ⚡ POSTURE(1)       │       ↳ chain: feat: posture scan   [view chain]       │  │
│ ⚡ TESTS  (1)       │                                                        │  │
│                     │  ● ⇡  [GIT]   feat: posture scan and observability 14:55─┘  │
│                     │                                                              │
│                     │  ● ⬡  [TOOLS] Node 18.20.0 installed             12:00      │
│                     │                                                              │
│                     │  ↓  Loading older entries...                                │
└─────────────────────┴──────────────────────────────────────────────────────────────┘

Legend:  ⬡ local only   ⇡ in git (shared)
         ○ chain origin   · chain step   ● chain terminal
         ● ok   ◑ warning   ⚠ attention   ✕ failed
         🔗 belongs to a chain — click to navigate in left panel
```

**Key design decisions:**
- **⇡ in git** = committed and pushed to origin — visible to anyone with repo access
- **⬡ local only** = on this machine only — backups, detection runs, posture changes, local package ops
- Session noise (vault autolock, server start/stop) is **filtered out entirely** — not a project event
- "Shared" is not a separate action — it's a consequence of committing to git (chat, audit, plans, tests)
- The distinction is read from the git state — not a user-configured flag per event

---

## Open questions

**E6 — resolved:**
- [x] Where does the timeline live in the UI? → **own dedicated tab**
- [x] What events from the ledger are timeline-worthy vs. too noisy? → **noise contract defined in `m1-foundation-requirements.md` §3**

**E7 — pending design (E7 not yet designed):**
- [ ] What is the security score formula? Which signals have which weight?
- [ ] Does the security view replace existing security domain pages or sit alongside them?

---

## Rough scope estimate
- E6:
  - Backend: `TimelineService` — 17 source adapters, 23 mediator nodes (6 source + 10 view + 7 feed), work queue tiers T1-T7, bus transformer subscriber, single `/api/timeline` endpoint with cursor pagination, `/api/timeline/chains` and `/api/timeline/domains` endpoints
  - Frontend: new dedicated Timeline tab — split-panel layout (left navigator: Chains/Domains/Calendar modes; right: chronological lazy-loading list with chain threading), SSE live integration, IntersectionObserver scroll loading
  - Full design contract: `m1-foundation-requirements.md`
- E7: Not yet designed — pending foundation requirements discussion
