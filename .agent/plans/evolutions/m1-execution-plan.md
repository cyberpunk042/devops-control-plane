# M1 — Execution Plan
> Status: LAYERS 1–8 DONE (E6) / BLOCKED (Layer 9 — E7 design pending)
>
> This document defines the ordered implementation sequence for Milestone 1.
> It references — it does not duplicate — the two source-of-truth documents:
>   - Foundation contracts: `m1-foundation-requirements.md`
>   - Milestone overview:   `milestone-1-observability-foundation.md`

---

## Execution order

Each layer must be complete and verified before the next begins.
No layer may be started if its predecessor has an unresolved blocker.

---

### Layer 0 — Foundation contracts ✅ DONE
> Reference: `m1-foundation-requirements.md` §1–§7

Defines the contracts everything is built on. Frozen for E6 execution.

| Deliverable | Section | Status |
|---|---|---|
| Unified `TimelineEntry` model | §1 | ✅ |
| Source taxonomy (17 sources) | §2 | ✅ |
| Noise contract | §3 | ✅ |
| Locality contract | §4 | ✅ |
| Query contract (filters, sort, pagination, endpoints) | §5 | ✅ |
| Live bus contract (`timeline:entry` SSE event) | §6 | ✅ |
| Panel UX contract (left navigator + right list, chains) | §7 | ✅ |

---

### Layer 1 — Models and protocol
> Reference: `m1-foundation-requirements.md` §1, §2

Define the Python dataclass and enums that enforce the entry model in code.
No business logic. No file I/O. Just the data contract as code.

| Task | File |
|---|---|
| `TimelineEntry` dataclass (all fields, typed) | `src/core/services/timeline/models.py` |
| `Source` enum (17 values) | same |
| `Status`, `Severity`, `Locality`, `Actor`, `ChainRole` enums | same |
| `TimelineQuery` dataclass (all 13 filter axes + pagination fields) | same |
| `TimelinePage` dataclass (entries, has_more, next_cursor, prev_cursor, total_hint) | same |

**Done when:** models importable with no side effects, all fields present, all enums match §1 exactly.

---

### Layer 2 — Source adapters
> Reference: `m1-foundation-requirements.md` §9

One adapter per source group. Each adapter reads its raw source and returns `list[TimelineEntry]`.
Adapters do not call mediator directly — they are called by the mediator resolver.
Noise filters defined in §3 are applied inside each adapter.

| Adapter | Sources covered | Raw input |
|---|---|---|
| `ScanActivityAdapter` | AUDIT(local), PKG, VAULT, ENV, STACK, PLATFORM, POSTURE, SECURITY, WIZARD, CONFIG(local) | `.state/audit_activity.json` |
| `CliOpsAdapter` | TOOLS, BACKUP, CONFIG(local ops) | `.state/audit.ndjson` |
| `GitLogAdapter` | GIT, PLAN, CONFIG(commits) | `git log` subprocess |
| `LedgerRunsAdapter` | CI, TESTS | `.ledger/` git branch — `scp/run/*` tags |
| `LedgerAuditsAdapter` | AUDIT(shared) | `.ledger/` git branch — `scp/audit/*` tags |
| `ChatAdapter` | CHAT | `.ledger/chat/` — per-message granularity |

**Done when:** each adapter returns valid `list[TimelineEntry]`, passes noise filter, maps all fields per §9 normalization tables.

---

### Layer 3 — Mediator registration
> Reference: `m1-foundation-requirements.md` §8 (Infrastructure — mediator registry)

Register all 23 nodes in the mediator. Adapters become resolvers.
Work queue priorities assigned per §8.

**23 nodes in registration order (dependencies first):**

**Source nodes (6) — raw data, mtime-watched or git-polled:**

| Node key | Resolver | TTL | Priority | Depends on |
|---|---|---|---|---|
| `timeline.source.scan_activity` | `ScanActivityAdapter` | mtime watch | T2 | — |
| `timeline.source.cli_ops` | `CliOpsAdapter` | mtime watch | T2 | — |
| `timeline.source.git_log` | `GitLogAdapter` | 60s | T3 | — |
| `timeline.source.ledger_runs` | `LedgerRunsAdapter` | 120s | T3 | — |
| `timeline.source.ledger_audits` | `LedgerAuditsAdapter` | 120s | T3 | — |
| `timeline.source.chat` | `ChatAdapter` | 120s | T3 | — |

**View nodes (10) — pre-aggregated slices:**

| Node key | TTL | Priority | Depends on |
|---|---|---|---|
| `timeline.view.recent` | 30s | T2 | all 6 source nodes |
| `timeline.view.today` | 30s | T2 | all 6 source nodes |
| `timeline.view.week` | 60s | T3 | all 6 source nodes |
| `timeline.view.month` | 300s | T4 | all 6 source nodes |
| `timeline.view.local` | 30s | T2 | scan_activity, cli_ops |
| `timeline.view.shared` | 60s | T3 | git_log, ledger_runs, ledger_audits, chat |
| `timeline.view.failures` | 30s | T2 | all 6 source nodes |
| `timeline.view.security` | 60s | T3 | scan_activity |
| `timeline.view.chains` | 60s | T3 | all 6 source nodes |
| `timeline.view.stats` | 300s | T5 | all 6 source nodes |

**Feed nodes (7) — cross-domain pre-computed feeds:**

| Node key | TTL | Priority | Depends on |
|---|---|---|---|
| `timeline.feed.security_posture` | 300s | T4 | scan_activity |
| `timeline.feed.pkg_health` | 300s | T4 | scan_activity |
| `timeline.feed.tool_lifecycle` | 300s | T4 | scan_activity, cli_ops |
| `timeline.feed.stack_health` | 300s | T4 | scan_activity |
| `timeline.feed.readiness` | 300s | T4 | all view nodes |
| `timeline.feed.changelog` | 600s | T5 | git_log |
| `timeline.feed.notifications` | 60s | T3 | failures, security_posture |

**Done when:** `mediator.get("timeline.source.scan_activity")` returns valid entries, cascade invalidation works (touch `.state/audit_activity.json` → view nodes invalidate).

---

### Layer 4 — TimelineService + API route
> Reference: `m1-foundation-requirements.md` §8 (TimelineService, thin route)

`TimelineService` accepts a `TimelineQuery`, calls `mediator.get()` on the appropriate view nodes, merges, sorts, applies remaining filter axes, paginates with cursor.

Thin API route at `/api/timeline` receives query params, constructs `TimelineQuery`, calls service, returns JSON page.

| Task | File |
|---|---|
| `TimelineService.query(q: TimelineQuery) -> TimelinePage` | `src/core/services/timeline/service.py` |
| `/api/timeline` GET route | `src/ui/web/routes/timeline/routes.py` |
| `/api/timeline/chains` GET route | same |
| `/api/timeline/domains` GET route | same |

**Done when:** `GET /api/timeline?sources=GIT,AUDIT&limit=50` returns a valid `TimelinePage` JSON with correct entries.

---

### Layer 5 — Bus transformer subscriber
> Reference: `m1-foundation-requirements.md` §6, §8 (bus transformer pattern)

Subscribe to `"computed"` events on the mediator for `timeline.source.*` nodes.
Normalize to `TimelineEntry`. Publish `timeline:entry` to the event bus.
Follows existing pattern: `subscribers/eventbus_bridge.py` + `subscribers/activity.py`.

| Task | File |
|---|---|
| `TimelineSubscriber` — mediator computed → bus `timeline:entry` | `src/core/subscribers/timeline.py` |
| Register subscriber at app startup | `src/core/startup.py` (or equivalent) |

**Done when:** writing a new entry to `.state/audit_activity.json` causes `timeline:entry` to appear on the event bus within TTL window.

---

### Layer 6 — Frontend basic (tab shell + flat list)
> Reference: `m1-foundation-requirements.md` §10

New Timeline tab. Right panel only (no navigator yet). Flat chronological list.
SSE integration (`timeline:entry` → prepend). IntersectionObserver scroll loading.

| Task | File |
|---|---|
| Tab shell — two-panel layout skeleton | `src/ui/web/templates/timeline/_timeline.html` |
| Flat list rendering (entries, day separators, status icons, locality badge) | `src/ui/web/templates/timeline/_timeline_list.html` |
| JS state model `_tlState` | `src/ui/web/static/js/timeline.js` |
| REST fetch + cursor pagination (IntersectionObserver sentinel) | same |
| SSE handler (`timeline:entry` → 800ms batch buffer → prepend) | same |
| CSS — list layout, status colors, locality badge, day separator | `src/ui/web/static/css/timeline.css` |

**Done when:** Timeline tab loads, shows entries from all sources in date order, new entries appear live, scroll loads older entries.

---

### Layer 7 — Chain system
> Reference: `m1-foundation-requirements.md` §7 (chain threading), §10 (chain badges, CSS pseudo-elements)

Add `chain_id` / `chain_role` / `chain_parent_ref` to the rendered list.
Thread lines connecting chain members via CSS pseudo-elements.
Chain badge 🔗 on entries that belong to a chain.
Chain footer `↳ chain: <name>  [view chain]` at chain terminal entries.

| Task | File |
|---|---|
| Chain badge rendering (🔗 on entries with chain_id) | `_timeline_list.html` |
| Thread line CSS pseudo-elements (─┐ / ─┘ connectors) | `timeline.css` |
| Chain footer at terminal entries | `_timeline_list.html` |
| JS: group entries by chain_id for thread rendering | `timeline.js` |

**Done when:** a chain (e.g., local audit ran → committed to ledger) renders with thread connectors and a navigable footer.

---

### Layer 8 — Left navigator panel
> Reference: `m1-foundation-requirements.md` §7 (panel UX contract), §10 (left navigator)

Three modes: Chains / Domains / Calendar.
Scroll sync: right list scroll → left panel highlights active chain.
Click chain in left panel → filters right list.
Hover chain → soft-highlights all chain members in right list.

| Task | File |
|---|---|
| Left navigator panel shell (mode tabs: Chains/Domains/Calendar) | `src/ui/web/templates/timeline/_timeline_nav.html` |
| Chains mode — collapsible chain trees with chain member rows | same |
| Domains mode — per-source counts, expandable | same |
| Calendar mode — date navigation | same |
| JS: scroll sync, hover highlight, click-to-filter | `timeline.js` |
| CSS: navigator panel, active/hover states, chain node indentation | `timeline.css` |

**Done when:** all three navigator modes function; scroll in right list highlights chain in left panel; click chain in left panel filters right list to that chain.

---

### Layer 9 — E7 Security Posture ⛔ BLOCKED
> Foundation requirements not yet designed.
> `timeline.feed.security_posture` node is registered (Layer 3) and available as input.
> E7 design must happen before this layer can be scoped.

---

## Blockers and dependencies

| Layer | Blocked by | Notes |
|---|---|---|
| 1–8 | Nothing | E6 foundation complete |
| 9 | E7 foundation design | Must be designed before Layer 9 begins |

---

## Tracking

| Layer | Status | Notes |
|---|---|---|
| 0 — Foundation contracts | ✅ DONE | `m1-foundation-requirements.md` |
| 1 — Models and protocol | ✅ DONE | `src/core/services/timeline/models.py` + `__init__.py` |
| 2 — Source adapters | ✅ DONE | `src/core/services/timeline/adapters/` (6 adapters) |
| 3 — Mediator registration | ✅ DONE | `src/core/services/mediator/registrations/timeline.py` + `__init__.py` |
| 4 — TimelineService + API | ✅ DONE | `src/core/services/timeline/service.py` + `src/ui/web/routes/timeline/` |
| 5 — Bus transformer | ✅ DONE | `src/core/services/mediator/subscribers/timeline.py` |
| 6 — Frontend basic | ✅ DONE | `_tab_timeline.html`, `_timeline.html` (JS), `admin.css` (timeline classes), `_event_stream.html` (timeline:entry), nav + dashboard wired |
| 7 — Chain system | ✅ DONE | badges, thread lines, chain footer + view-chain button all in Layer 6 JS/CSS |
| 8 — Left navigator | ✅ DONE | Chains (collapsible members) + Domains + Calendar modes; scroll sync, hover highlight, click-to-filter |
| 9 — E7 Security Posture | ⛔ BLOCKED | Design pending |
