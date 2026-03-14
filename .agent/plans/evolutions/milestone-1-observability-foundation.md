# Milestone 1 — Observability Foundation
> Status: INVESTIGATED — infrastructure mapped, ready for deep design discussion

---

## Goal
Make what already exists in the platform *visible* in unified ways.
No new operations. Pure read surfaces. Low risk, high value.
Everything downstream depends on these surfaces.

---

## Evolutions included

### E6 — Project Timeline & Activity Intelligence
A unified chronological view of all events across all domains.
This is the **evolution of the existing Audit Log view** (Debugging tab) — not a replacement, an upgrade.

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

**Integration point:** The Timeline replaces/supersedes the Audit Log inside the Debugging tab as a first step, then optionally gets promoted to its own tab once mature.

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
┌──────────────────────────────────────────────────────────────────────────────┐
│  TIMELINE — my-project                        [All] [Local] [Shared]        │
│  All domains ▾   All environments ▾   Last 7 days ▾                         │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Legend:  ⬡ local only    ⇡ in git (shared)                                 │
│           ● ok   ◑ warning   ⚠ needs attention   ✕ failed                  │
│                                                                              │
├── TODAY — March 14, 2026 ────────────────────────────────────────────────────┤
│                                                                              │
│  10:33  ● ⇡  [GIT]      fix: bugs — 5 insertions, 1 deletion               │
│  10:24  ● ⬡  [PKG]      cryptography → 42.0.5, flask → 3.1.0               │
│  09:12  ● ⇡  [GIT]      mediator — work_queue patched                       │
│  08:51  ◑ ⬡  [AUDIT]    Security scan — 3 findings (not yet committed)      │
│  08:30  ● ⇡  [CHAT]     Thread: "wsl transport approach" — 4 msgs           │
│                                                                              │
├── YESTERDAY — March 13, 2026 ────────────────────────────────────────────────┤
│                                                                              │
│  17:44  ● ⇡  [CI]       Build passed — main ✓  (2m 14s)                    │
│  17:40  ◑ ⬡  [PKG]      npm audit — 2 moderate CVEs                        │
│  16:10  ● ⇡  [TESTS]    Test suite — 94/94 passed                          │
│  14:22  ● ⬡  [BACKUP]   Snapshot #47 created — dev                         │
│  13:45  ● ⇡  [PLAN]     Execution plan committed — wsl-refactor             │
│  11:05  ⚠ ⬡  [POSTURE]  Node 18 → OUTDATED (EOL 11mo ago)                 │
│  09:30  ● ⬡  [PLATFORM] Detection — 6 modules, all healthy                 │
│                                                                              │
├── March 12, 2026 ────────────────────────────────────────────────────────────┤
│                                                                              │
│  15:20  ✕ ⇡  [CI]       Build failed — lint error                          │
│  14:55  ● ⇡  [GIT]      feat: posture scan and observability                │
│  12:00  ● ⬡  [TOOLS]    Node 18.20.0 installed                             │
│  10:30  ● ⇡  [AUDIT]    L2 audit committed — 7 findings, 2 open            │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Key design decisions:**
- **⇡ in git** = committed and pushed to origin — visible to anyone with repo access
- **⬡ local only** = on this machine only — backups, detection runs, posture changes, local package ops
- Session noise (vault autolock, server start/stop) is **filtered out entirely** — not a project event
- "Shared" is not a separate action — it's a consequence of committing to git (chat, audit, plans, tests)
- The distinction is read from the git state — not a user-configured flag per event

---

## Open questions
- [ ] Where does the timeline live in the UI? (tab? side panel? dedicated page?)
- [ ] What is the security score formula? Which signals have which weight?
- [ ] Does the security view replace existing security domain pages or sit alongside them?
- [ ] What events from the ledger are timeline-worthy vs. too noisy?

---

## Rough scope estimate
- E6:
  - Backend: `TimelineAggregator` service — merges scan_activity + audit_ops + ledger runs/audits + git log into unified sorted feed; computes local/shared flag per entry; supports date-range + domain + environment filters; single `/api/timeline` endpoint
  - Frontend: Replace/evolve the Debugging tab Audit Log with the new timeline view — same tab, promoted UI
- E7: Frontend + light aggregation layer — reads existing signals (audit cards, vault, security scanning), computes score
