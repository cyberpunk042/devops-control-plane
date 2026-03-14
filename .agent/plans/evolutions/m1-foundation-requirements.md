# M1 — Foundation Requirements
> Status: IN DISCUSSION
> This document defines the contracts the infrastructure and features will be built on.
> It is not frozen — the model is expansive by design.

---

## 1. Unified Timeline Entry Model

The single normalized data contract that every source maps into.
The aggregator speaks this model. The API returns this model. The frontend consumes this model.

```
TimelineEntry {

  -- Identity
  id          string      stable unique ID per entry (source:subtype:ref or hash)
  ts          float       unix epoch — the single sort key across all sources
  ref         string?     back-link to the original record (run_id, commit hash, thread_id, ...)

  -- Classification
  source      enum        domain of origin — see Source Taxonomy below
  subtype     string?     source-specific subdivision (L2, npm, pip, staging→prod, ...)
  actor       enum        what triggered this: user | scheduler | platform | automation

  -- Outcome
  status      enum        ok | warning | attention | failed
  severity    enum?       low | medium | high | critical
                          null for neutral/informational events

  -- Locality
  locality    enum        local | shared
                          local  = exists only in .state/ on this machine
                          shared = committed to git (ledger branch or project repo)

  -- Scope
  env         string[]    environments involved — [] if not applicable
                          single: ["dev"]
                          transition: ["dev", "staging"]
  modules     string[]    affected modules/domains — [] if project-wide

  -- Content
  summary     string      one-line human-readable — always present, never empty

  detail      dict?       source-specific payload — opaque to aggregator, rendered by frontend
                          structure is defined per source in the Source Taxonomy

  -- Lifecycle chain
  chain_id        string?   groups related entries across sources and localities — first-class concept
                            examples:
                              operation_id  chains a local CLI op → its ledger commit
                              git hash      chains a commit → all CI runs triggered by it
                              thread_id     chains thread creation → messages → deletion
                            chain members share chain_id, sorted by ts — full lifecycle traversable

  chain_role      enum?     position of this entry within its chain
                              origin       — the first event that started the chain (local audit ran)
                              step         — intermediate event (CI started, scan staged)
                              terminal     — final event in the chain (committed, passed, resolved)
                            null if this entry is not part of any chain

  chain_parent_ref string?  ref of the entry that directly caused/triggered this one
                            enables tree-shaped chains (one commit → multiple CI runs)
                            null if origin or if parent is unknown

  -- Origin metadata
  hostname    string?     machine where the event was produced
  os          string?     OS identifier (linux, darwin, win32)
  platform    string?     platform context if relevant (wsl2, docker, native, ...)
}
```

---

## 2. Source Taxonomy

Each source maps to one or more `source` enum values.
Each entry defines: what data it reads, what it produces, and what it never contributes.

| source    | subtypes                        | reads from                          | locality  | actor                |
|-----------|---------------------------------|-------------------------------------|-----------|----------------------|
| GIT       | commit, push, pull, merge, tag  | git log (project repo)                         | shared       | user / automation    |
| AUDIT     | L0, L1, L2                      | ledger audits + scan_activity                  | local→shared | scheduler / user     |
| PKG       | pip, npm, go, cargo, ...        | scan_activity (card: pkg/*)                    | local        | user / automation    |
| VAULT     | rotate, lock, unlock, add, del  | scan_activity (card: vault/*)                  | local        | user / automation    |
| ENV       | add, modify, delete, promote    | scan_activity (card: env/*)                    | local        | user                 |
| TOOLS     | install, upgrade, remove        | CLI ops (operation_type: tool_*)               | local        | user                 |
| STACK     | detected, outdated, eol, annot  | scan_activity (card: stack/*)                  | local        | scheduler / user     |
| CI        | build, test, deploy             | ledger runs (type: ci)                         | shared       | automation           |
| TESTS     | run, coverage                   | ledger runs (type: test)                       | shared       | user / automation    |
| BACKUP    | snapshot, restore               | CLI ops (operation_type: backup_*)             | local        | scheduler / user     |
| CHAT      | thread, message, delete         | ledger chat threads (per-message granularity)  | shared       | user                 |
| PLAN      | commit, update                  | git log (commits touching .agent/)             | shared       | user                 |
| PLATFORM  | detection, health               | scan_activity (card: platform/*)               | local        | scheduler            |
| POSTURE   | scan, finding, rank             | scan_activity (card: posture/*)                | local        | scheduler            |
| SECURITY  | cve, secret, finding            | scan_activity (card: security/*)               | local        | scheduler            |
| WIZARD    | configured, created, deleted    | scan_activity (card: wizard) — already recorded via record_event() | local | user |
| CONFIG    | saved, promoted                 | scan_activity (card: wizard, target: project.yml) + git log (commits touching project.yml, Dockerfile, k8s/, .github/workflows/, terraform/) | local→shared | user / wizard |

**Note on WIZARD + CONFIG storage:** Wizard setup actions and project.yml saves already write to
`.state/audit_activity.json` via `record_event()`. No new persistence needed. The `scan_activity`
adapter covers these — the normalizer maps `card: "wizard"` → source WIZARD or CONFIG based on target.

**Note on CHAT granularity:** One timeline entry per message, plus thread creation and deletion events.
Thread-level aggregation is a UI concern (chain grouping), not a data concern.

---

## 3. Noise Contract — What Is Never a Timeline Event

These are explicitly excluded. They are session-level noise, not project events.

| Excluded | Reason |
|----------|--------|
| Vault autolock / autounlock | Session lifecycle, not a project state change |
| Server start / stop / restart | Platform plumbing, not observable project work |
| SSE connection established / dropped | Transport noise |
| Cache bust (internal) | Implementation detail of the caching layer |
| Heartbeats | Protocol noise |
| Auth prompts (git/gh) | Session mechanics |

**Rule:** if the event says nothing about the *state of the project*, it is noise.

---

## 4. Locality Contract — How local vs shared Is Determined

Every entry gets a `locality` value. This is **computed**, not user-configured.

```
local   The data exists only in .state/ files on this machine.
        It has never been committed to git.
        Examples: scan activity, CLI ops, vault events, backup snapshots.

shared  The data is in a git commit — either:
        - The project repository (git log: commits, plan files, .agent/ changes)
        - The ledger branch (.ledger/: audit snapshots, chat threads, CI runs)
        Anyone with repo access can see it.
        Examples: GIT commits, committed audits, chat threads, CI runs.
```

**How to compute it:**
- Sources that are always local: scan_activity entries, audit.ndjson ops, backup events
- Sources that are always shared: git log entries, ledger run records, ledger audit records, chat threads
- AUDIT entries: local until `save_audit_snapshot()` is called → then shared (the ledger tag is the signal)

---

---

## 5. Query Contract

The API contract for retrieving timeline entries. The aggregator must honor all of these.

### Filter axes — all are legal, all are optional, all combinable

| Parameter     | Type       | Values                                          | Notes |
|---------------|------------|-------------------------------------------------|-------|
| `source`      | string[]   | Any value from Source Taxonomy                  | Multi-select |
| `subtype`     | string[]   | Source-specific (L0, L1, npm, pip, ...)         | Multi-select |
| `status`      | string[]   | ok, warning, attention, failed                  | Multi-select |
| `severity`    | string[]   | low, medium, high, critical                     | Multi-select |
| `locality`    | string     | local, shared                                   | Single |
| `env`         | string[]   | dev, staging, prod, or any env name             | Multi-select |
| `module`      | string[]   | Module name as known to the platform            | Multi-select |
| `actor`       | string[]   | user, scheduler, platform, automation           | Multi-select |
| `date_from`   | float      | Unix epoch — lower bound (inclusive)            | |
| `date_to`     | float      | Unix epoch — upper bound (inclusive)            | |
| `chain_id`    | string     | Return all entries belonging to this chain      | Powers left panel navigation |
| `chain_role`  | string[]   | origin, step, terminal                          | |
| `q`           | string     | Free-text search against `summary` + `detail`   | |

### Sort

The user can shape their view. Foundation must support:

| `sort_by`   | `sort_dir` | Description |
|-------------|------------|-------------|
| `ts`        | desc / asc | Chronological (default: desc = newest first) |
| `severity`  | desc / asc | Most critical first |
| `source`    | asc        | Group by domain |
| `status`    | desc       | Failures first |

Default: `sort_by=ts&sort_dir=desc`

### Pagination — cursor-based, scroll-triggered

The timeline is time-unbounded. Offset pagination breaks on live data. The foundation uses **timestamp cursors**.

```
Request:
  GET /api/timeline
    ?before_ts=<float>     load entries older than this timestamp (scroll deeper into past)
    ?after_ts=<float>      load entries newer than this timestamp (live refresh from top)
    &limit=<int>           entries per page (default: 50, max: 200)
    &[...filter params]

Response:
  {
    "entries":    TimelineEntry[],
    "has_more":   bool,           -- true if more entries exist beyond this page
    "next_cursor": float | null,  -- ts of the oldest entry in this page (use as next before_ts)
    "prev_cursor": float | null,  -- ts of the newest entry (use as after_ts for live refresh)
    "total_hint": int | null      -- approximate total matching entries (best-effort, not guaranteed)
  }
```

**Scroll mechanic (UX contract):**
- Initial load: no `before_ts` — returns the N most recent entries
- Scroll to bottom: fires request with `before_ts = next_cursor` — appends older entries
- Live refresh (top): fires request with `after_ts = prev_cursor` every N seconds — prepends new entries
- Filters change: full reset — discard loaded entries, reload from scratch
- Chain filter: `chain_id=X` returns all entries in that chain regardless of date/cursor — full chain always loaded

### Additional endpoints

```
GET /api/timeline/chains
  ?date_from=<float>
  ?date_to=<float>
  ?source[]=<str>
  Returns: list of chains visible in the current view window
  {
    "chains": [
      {
        "chain_id":   string,
        "label":      string,          -- human name for the chain (derived from origin entry summary)
        "source":     string,          -- source of the origin entry
        "ts_start":   float,           -- ts of the origin entry
        "ts_end":     float | null,    -- ts of the terminal entry (null if chain still open)
        "status":     string,          -- worst status across all chain members
        "severity":   string | null,
        "locality":   string,          -- "mixed" if chain spans local + shared
        "members":    [                -- all entries in the chain, ordered by ts
          { "id", "ts", "source", "subtype", "status", "locality", "summary",
            "chain_role", "chain_parent_ref" }
        ]
      }
    ]
  }

GET /api/timeline/domains
  ?date_from=<float>
  ?date_to=<float>
  Returns: source domain tree with entry counts
  {
    "domains": [
      { "source": "GIT", "count": 12, "subtypes": [{"subtype":"commit","count":10}, ...] },
      ...
    ]
  }
```

---

## 6. Live Extension — Event Bus Contract

The foundation defines the live channel. This is not infrastructure detail — it is a first-class contract.

New entries are broadcast on the event bus as they are produced, so the timeline panel can prepend them without polling.

```
Event type:  timeline:entry
Key:         entry.id
Data:        TimelineEntry (full normalized entry — same model as the REST API)
```

The frontend subscribes to `timeline:entry` on the SSE channel.
When an entry arrives: prepend to the visible list if it passes the current filter state.
The user sees new events appear at the top in real time — no page refresh, no manual reload.

**Why this is foundation and not infrastructure:**
Every source adapter that produces a TimelineEntry must also publish `timeline:entry` to the bus.
This is a contract on the aggregator, not an optional add-on. The API and the bus emit the same model.

---

## 7. Panel UX Contract (reference for frontend design)

The timeline is a **full tab** with a two-panel layout — left navigator + right chronological list.
Same pattern as the content vault: left = structure, right = content.

```
┌──────────────────────┬────────────────────────────────────────────────────────┐
│  NAVIGATOR           │  TIMELINE — my-project                      ⟳ Live    │
│  ─────────────────── │  ──────────────────────────────────────────────────── │
│  📎 Chains           │  [GIT▾][AUDIT▾][+3▾]  [⚠▾]  [desc▾]   🔍 search...  │
│  🌐 Domains          │  [⬡ Local] [⇡ Shared] [● All]                         │
│  📅 Calendar         ├── TODAY — March 14, 2026 ─────────────────────────────┤
│  ─────────────────── │                                                        │
│  🔍 filter chains... │  ● ⇡  [GIT]    fix: bugs — 5 ins, 1 del     10:33    │
│                      │                                                        │
│  ── Active chains ── │  ● ⬡  [PKG]    cryptography → 42.0.5        10:24    │
│                      │                                                        │
│  📎 Audit L2 (2)     │  ◑ ⬡  [AUDIT]  L2 scan — 3 findings  🔗    08:51 ─┐ │
│    ⬡ L2 ran   08:51  │                                                    │ │
│  → ⇡ committed 10:30 │  ● ⇡  [CHAT]   "wsl transport" — 4 msgs    08:30  │ │
│                      ├── YESTERDAY — March 13, 2026 ──────────────────────┤ │
│  📎 feat: posture (2)│                                                    │ │
│    ⇡ commit   14:55  │  ● ⇡  [CI]     Build passed (2m 14s)        17:44  │ │
│  → ✕ CI fail  15:20  │                                                    │ │
│                      │  ◑ ⬡  [PKG]    npm audit — 2 CVEs           17:40  │ │
│  📎 wsl thread (3)   │                                                    │ │
│    ⇡ created  08:30  │  ⇡ [AUDIT]  L2 committed — 7 findings  🔗   10:30 ─┘ │
│    ⇡ msg      09:15  │       ↳ chain: Audit L2 Lifecycle  [view chain]       │
│  → ⇡ msg      10:45  │                                                        │
│                      │  ● ⇡  [GIT]    feat: posture scan           14:55 ─┐  │
│  ── Domains ──────── │                                                    │  │
│  ⚡ GIT    (3) ────── │  ✕ ⇡  [CI]     Build failed — lint error    15:20 ─┘ │
│  ⚡ AUDIT  (2)       │       ↳ chain: feat: posture scan  [view chain]        │
│  ⚡ PKG    (2) ▸     │                                                        │
│  ⚡ CI     (2)       │  ↓  Loading older entries...                           │
│  ⚡ CHAT   (3)       │                                                        │
└──────────────────────┴────────────────────────────────────────────────────────┘
```

**Left navigator — 3 modes (like the glossary panel):**

| Mode | Content | Analogy |
|------|---------|---------|
| 📎 Chains | All chains in view — collapsible tree per chain showing member entries | Outline mode |
| 🌐 Domains | All sources with entry counts — collapsible by source/subtype | Glossary/folder mode |
| 📅 Calendar | Mini calendar — dots on days with events, click to jump | Navigation aid |

**Left ↔ Right synchronization (mirrors the glossary ↔ preview sync):**
- Scrolling the right list → left panel highlights the chains/domains currently in view
- Clicking a chain in the left panel → right list highlights all entries in that chain + scrolls to earliest
- Clicking a domain in the left panel → applies source filter to right list
- Hovering a chain node → soft highlight of all chain members in the right list
- Live new entry arrives → left panel chain count updates; right list prepends with animation

**Chain visualization in the right list:**
- Entries belonging to a chain show `🔗` indicator
- Connected chain members show a vertical thread line (CSS `border-left` on a connector div)
- Below the terminal entry: `↳ chain: <label>  [view chain]` — click to filter to full chain
- `[view chain]` sets `chain_id=X` filter → right list shows only that chain's entries in full detail

**Key UX rules:**
- Date group headers are sticky — always visible as you scroll past
- Status + locality icons always visible on row (no hover required)
- Filter pills show active filters only — collapsed by default, expandable
- Live entries prepend at top with 1.5s blue fade animation
- IntersectionObserver sentinel at bottom triggers next cursor fetch (200px threshold)
- Clicking a row expands inline detail — no navigation away
- Left panel width is resizable (drag handle) and persists to localStorage

---

---

## 8. Infrastructure Design

Built on top of the foundation contracts. Uses existing platform systems — does not reinvent them.

### 8.1 — Where timeline fits in the existing architecture

```
Index → Detect → Devops → Posture → Audit
                                        ↓
                              timeline.* (new, depends on all upstream)
```

The timeline is a **consumer** of all other domains. It depends on everything but nothing depends on it.
This places it at **T5:aggregate** in the mediator tier system — same as `devops.status`, `posture.*`, `audit.*`.

---

### 8.2 — Three new components, all following existing patterns

```
src/core/services/mediator/
  registrations/
    timeline.py          ← NEW: registers timeline.* mediator nodes
  subscribers/
    timeline.py          ← NEW: bus transformer — listens, normalizes, publishes timeline:entry
                              (same pattern as eventbus_bridge.py and activity.py)

src/core/services/timeline/
  __init__.py
  models.py              ← TimelineEntry, TimelineQuery, TimelineResult
  adapters/
    __init__.py          ← TimelineAdapter protocol
    scan_activity.py     ← reads .state/audit_activity.json
    cli_ops.py           ← reads .state/audit.ndjson
    ledger_runs.py       ← reads .ledger/ runs (git tags scp/run/*)
    ledger_audits.py     ← reads .ledger/ audits (git tags scp/audit/*)
    git_log.py           ← reads project git log
    chat.py              ← reads .ledger/chat/ threads
  locality.py            ← LocalityResolver (shared, computes local|shared per entry)
  service.py             ← TimelineService (aggregator — fan-out, merge, sort, paginate)
  noise.py               ← NoiseFilter (applies noise contract)
```

---

### 8.3 — Mediator registration (`registrations/timeline.py`)

Full node registry. Three categories, all in one registration file.

#### Category 1 — Source nodes (one per raw data source)

Each source node loads its full data into cache. Adapters call `mediator.get()` — no raw file I/O at query time.

```
timeline.source.scan_activity    mtime: .state/audit_activity.json        TTL: None   size: 1   persist: False
timeline.source.cli_ops          mtime: .state/audit.ndjson               TTL: None   size: 1   persist: False
timeline.source.git_log          mtime: .git/refs/heads/                  TTL: 60     size: 2   persist: False
timeline.source.ledger_runs      mtime: .ledger/ (refs)                   TTL: 60     size: 2   persist: False
timeline.source.ledger_audits    mtime: .ledger/audits/                   TTL: 60     size: 2   persist: False
timeline.source.chat             mtime: .ledger/chat/                     TTL: 60     size: 1   persist: False
```

All source nodes: `depends_on = []` (they are the leaves — nothing upstream in timeline domain).

#### Category 2 — Pre-computed view nodes

Fast-path for common queries. All depend on `timeline.source.*`.

```
timeline.recent        newest 50, no filters          TTL: 30     size: 2   persist: False
timeline.today         today's entries                TTL: 30     size: 2   persist: False
timeline.week          last 7 days                    TTL: 60     size: 2   persist: False
timeline.month         last 30 days                   TTL: 120    size: 3   persist: False
timeline.local         local-only entries             TTL: 30     size: 1   persist: False
timeline.shared        shared-only entries            TTL: 60     size: 1   persist: False
timeline.failures      failed + attention entries     TTL: 30     size: 1   persist: False
timeline.security      AUDIT+SECURITY+VAULT+POSTURE   TTL: 30     size: 2   persist: True
timeline.chains        entries grouped by chain_id    TTL: 60     size: 2   persist: False
timeline.stats         counts/source/status/day       TTL: 60     size: 1   persist: True
```

All view nodes: `depends_on = ["timeline.source.*"]`
Cascade: any source node invalidates → all view nodes invalidate automatically.

#### Category 3 — Downstream feed nodes (curated outputs for M2-M5)

These are the outputs the timeline produces for other milestones to consume.
Each feed is a curated, pre-filtered subset of the timeline for a specific domain.

```
timeline.feed.security_posture   AUDIT+SECURITY+VAULT+POSTURE entries     → feeds E7 (M1)
timeline.feed.pkg_health         PKG entries with CVE/warning status       → feeds E1, E10 (M2)
timeline.feed.tool_lifecycle     TOOLS+STACK entries                       → feeds E3, E8 (M3)
timeline.feed.stack_health       STACK entries (outdated, eol, annotated)  → feeds E8 (M3)
timeline.feed.readiness          all entries affecting readiness score      → feeds E9 (M4)
timeline.feed.changelog          GIT+PKG+VAULT+TOOLS+STACK+CONFIG diffs    → feeds E4 (M4)
timeline.feed.notifications      high+critical severity entries            → feeds E11 (M5)
```

All feed nodes: `depends_on = ["timeline.security" | "timeline.week" | ...]` (relevant view node)
`persist: True` for all feed nodes — downstream domains read them on startup.

**Cascade behavior:** change in `devops.git` → `timeline.source.git_log` invalidates → `timeline.recent`, `timeline.week`, `timeline.shared`, `timeline.chains` invalidate → `timeline.feed.changelog`, `timeline.feed.readiness` invalidate → M4 readiness score invalidates. Fully automatic.

---

### 8.4 — Work queue priority assignment

| Operation | Priority | Reason |
|-----------|----------|--------|
| Initial timeline load (user opens panel) | `HIGH (1)` | User-initiated, visible |
| Cursor fetch (scroll, load more) | `HIGH (1)` | User-initiated, visible |
| Git log adapter read | `NORMAL (2)` | Moderate cost, triggered by request |
| Ledger branch read (runs, audits, chat) | `NORMAL (2)` | Moderate cost, triggered by request |
| Background adapter warm-up (cold start) | `LOW (3)` | Background pre-fill |
| Stats recompute | `IDLE (4)` | Not user-facing, passive |

Live entry publishing (the bus subscriber) does **not** go through the work queue.
It is a synchronous callback — lightweight normalization only, no I/O.

---

### 8.5 — Bus transformer subscriber (`subscribers/timeline.py`)

Follows the exact same pattern as `eventbus_bridge.py` and `activity.py`.

```python
# subscribes to mediator "computed" events → publishes timeline:entry
# subscribes to ledger:* events (audit:saved, etc.) → publishes timeline:entry
# subscribes to chat:* events → publishes timeline:entry

def _on_computed(event: dict) -> None:
    if event.get("type") != "computed":
        return
    path = event["paths"][0]
    if not _is_timeline_relevant(path):     # filter: only devops.*, audit.*, posture.*
        return
    entry = _normalize_computed(path, event["compute_meta"])
    if entry is None:                       # noise filter applied here
        return
    bus.publish("timeline:entry", key=entry.id, data=entry.to_dict())

def _on_ledger(event: dict) -> None:
    if event.get("type") not in ("audit:saved",):
        return
    entry = _normalize_ledger(event)
    if entry:
        bus.publish("timeline:entry", key=entry.id, data=entry.to_dict())

def register(mediator, bus):
    mediator.subscribe("*", _on_computed)
    bus.subscribe("audit:saved", _on_ledger)
    bus.subscribe("chat:*", _on_chat)
```

---

### 8.6 — TimelineService (aggregator)

```python
class TimelineService:
    adapters: list[TimelineAdapter]
    locality: LocalityResolver
    noise: NoiseFilter
    work_queue: WorkQueue

    def query(self, q: TimelineQuery) -> TimelineResult:
        # 1. Fan out to all adapters in parallel via work queue (Priority.HIGH)
        # 2. Each adapter returns list[TimelineEntry] filtered by q.date_from/date_to
        # 3. Merge all results into one list
        # 4. Apply noise filter
        # 5. Resolve locality for each entry
        # 6. Apply remaining filters (source, status, severity, env, module, actor, q)
        # 7. Sort by q.sort_by / q.sort_dir
        # 8. Apply cursor bounds (before_ts / after_ts)
        # 9. Paginate (limit + has_more)
        # 10. Return TimelineResult

    def stats(self) -> dict:
        # Entry counts per source per day — lightweight, uses cached adapter reads
```

---

### 8.7 — API route

```
GET /api/timeline
    ?before_ts=<float>
    ?after_ts=<float>
    ?limit=<int>           default 50, max 200
    &source[]=<str>        multi-value
    &status[]=<str>
    &severity[]=<str>
    &locality=<str>
    &env[]=<str>
    &module[]=<str>
    &actor[]=<str>
    &date_from=<float>
    &date_to=<float>
    &sort_by=<str>         ts | severity | source | status
    &sort_dir=<str>        asc | desc
    &q=<str>               free text
```

Thin route — delegates entirely to `TimelineService.query()`.
Serializes `TimelineResult` to JSON. No logic in the route.

---

## 9. Adapter Specifications

Each adapter populates one `timeline.source.*` mediator node.
The mediator handles caching, invalidation, and work queue dispatch.
Adapters do not do raw I/O at query time — they read from mediator cache.

---

### Adapter 1 — `scan_activity`
**Mediator node:** `timeline.source.scan_activity`
**Reads:** `.state/audit_activity.json` (JSON array, max 200 entries)
**mtime watch:** `.state/audit_activity.json`

This is the widest adapter — it covers all card scans and all user-initiated events recorded
via `record_scan_activity()` and `record_event()`. This includes wizard completions,
project.yml saves, package scans, security scans, posture checks, and platform detection.

#### Card → source/subtype mapping

| card key            | action present? | source   | subtype               | notes |
|---------------------|-----------------|----------|-----------------------|-------|
| `wizard`            | yes             | WIZARD   | target value          | always signal — user action |
| `wizard`            | `saved` + target `project.yml` | CONFIG | saved | project.yml written locally |
| `packages`          | any             | PKG      | (ecosystem from detail) | |
| `security`          | any             | SECURITY | cve / secret / finding | |
| `vault`             | any             | VAULT    | action value          | |
| `env`               | any             | ENV      | action value          | |
| `audit:*`           | any             | AUDIT    | L0 / L1 / L2          | local side — pre-ledger commit |
| `posture:*`         | any             | POSTURE  | summary / full / toolchain | |
| `stack`             | any             | STACK    | detected / outdated / eol / annotated | |
| `platform`          | any             | PLATFORM | detection / health    | |
| `docker`            | any             | PLATFORM | docker                | detection scan |
| `k8s`               | any             | PLATFORM | k8s                   | detection scan |
| `terraform`         | any             | PLATFORM | terraform             | detection scan |
| `git`               | any             | PLATFORM | git                   | git status scan — NOT a commit |
| `ci`                | any             | CI       | scan                  | CI status scan |
| `testing`           | any             | TESTS    | scan                  | test result scan |
| `tools`             | any             | TOOLS    | (tool name from detail) | |

#### Normalization

| source field   | → TimelineEntry field | notes |
|----------------|-----------------------|-------|
| `ts`           | `ts`                  | unix epoch float |
| `card`         | `source` + `subtype`  | via mapping table above |
| `label`        | part of `summary`     | combined with `summary` field |
| `summary`      | `summary`             | use as-is; prefix with label if needed |
| `status`       | `status`              | ok → ok; failed → failed; warn → warning |
| `action`       | part of `subtype`     | refines subtype when present |
| `target`       | `detail.target`       | what was acted on |
| `before`       | `detail.before`       | state before |
| `after`        | `detail.after`        | state after |
| `detail`       | `detail`              | merged with target/before/after |
| `duration_s`   | `detail.duration_s`   | |
| `bust`         | dropped               | internal cache mechanic — noise |
| —              | `locality`            | always `local` (scan_activity never committed) |
| —              | `actor`               | `user` if action present; `scheduler` otherwise |
| —              | `chain_id`            | see chain_id rules below |
| —              | `severity`            | derived: failed+security/audit → high; warning → medium; else null |

#### chain_id assignment

```
WIZARD events:      chain_id = "wizard:{target}:{iso_date}"
                    links wizard action (local) to the git commit that follows it (CONFIG shared)
                    the git_log adapter matches by touching project.yml or infra files on same date

AUDIT entries:      chain_id = operation_id (from detail if present)
                    links local scan entry to ledger_audits entry for the same operation

PKG entries:        chain_id = null (no downstream ledger record today)

All others:         chain_id = null unless operation_id available in detail
```

#### Noise filter

```
DROP if: card in ("docker", "k8s", "terraform", "git", "ci", "testing", "platform")
         AND status == "ok"
         AND action is None
         → pure refresh scan with no findings — not a project event

KEEP if: status != "ok"
         OR action is not None
         OR card in ("wizard", "audit:*", "posture:*", "security", "vault", "env", "packages")
```

---

### Adapter 2 — `cli_ops`
**Mediator node:** `timeline.source.cli_ops`
**Reads:** `.state/audit.ndjson` (append-only NDJSON, unbounded)
**mtime watch:** `.state/audit.ndjson`

Records CLI-level operations: tool installs, backups, vault operations, package operations.
This file grows indefinitely — the mediator caches the full parsed list; the adapter
reads from cache and indexes by ts for cursor-based queries.

#### operation_type → source/subtype mapping

| operation_type prefix | source  | subtype           |
|-----------------------|---------|-------------------|
| `tool_install`        | TOOLS   | install           |
| `tool_upgrade`        | TOOLS   | upgrade           |
| `tool_remove`         | TOOLS   | remove            |
| `backup_snapshot`     | BACKUP  | snapshot          |
| `backup_restore`      | BACKUP  | restore           |
| `vault_rotate`        | VAULT   | rotate            |
| `vault_add`           | VAULT   | add               |
| `vault_delete`        | VAULT   | delete            |
| `env_promote`         | ENV     | promote           |
| `env_modify`          | ENV     | modify            |
| `package_install`     | PKG     | (from context)    |
| `audit_run`           | AUDIT   | (from context)    |
| *(unrecognized)*      | PLATFORM| operation_type    |

#### Normalization

| source field          | → TimelineEntry field | notes |
|-----------------------|-----------------------|-------|
| `timestamp`           | `ts`                  | |
| `operation_id`        | `ref` + `chain_id`    | operation_id is the chain anchor |
| `operation_type`      | `source` + `subtype`  | via mapping table above |
| `automation`          | `summary` prefix + `actor` | if automation = "user" → actor: user; else automation |
| `environment`         | `env`                 | wrapped in list: [environment] |
| `modules_affected`    | `modules`             | |
| `status`              | `status`              | |
| `actions_succeeded` / `actions_total` | `detail.actions` | "X/Y succeeded" |
| `duration_ms`         | `detail.duration_ms`  | |
| `errors`              | `detail.errors` + `severity` | non-empty errors → severity: high |
| `context`             | `detail.context`      | opaque passthrough |
| —                     | `locality`            | always `local` |
| —                     | `actor`               | derived from `automation` field |

#### chain_id assignment

```
chain_id = operation_id

The ledger_audits adapter finds matching entries by the same operation_id
and assigns the same chain_id — forming the local→shared chain automatically.
```

#### Noise filter

None. All CLI ops are signal — they represent deliberate platform actions.

---

### Adapter 3 — `git_log`
**Mediator node:** `timeline.source.git_log`
**Reads:** `git log` subprocess — project repository
**mtime watch:** `.git/refs/heads/` (any branch head changes)

Covers all committed project history. Path analysis determines source and subtype.
This is the primary source for the PLAN, CONFIG (shared), and GIT entries.

#### git log command

```bash
git log --format="%H|%ae|%an|%at|%s" --numstat
```
Produces: hash, author_email, author_name, unix_ts, subject, then per-file stats (insertions, deletions, path).

#### Path → source/subtype detection (evaluated in order, first match wins)

| paths touched                                  | source | subtype    |
|------------------------------------------------|--------|------------|
| `.agent/plans/` or `.agent/workflows/`         | PLAN   | commit     |
| `.agent/rules/`                                | PLAN   | rules      |
| `project.yml`                                  | CONFIG | promoted   |
| `Dockerfile` or `docker-compose*`              | CONFIG | docker     |
| `.github/workflows/`                           | CONFIG | ci         |
| `k8s/` or `kubernetes/`                        | CONFIG | k8s        |
| `terraform/` or `*.tf`                         | CONFIG | terraform  |
| `dns/` or `cdn/` or `CNAME`                    | CONFIG | dns        |
| *(any other files)*                            | GIT    | commit     |

A single commit touching both code and `.agent/plans/` → source: PLAN (plan takes precedence).
A commit touching multiple config types → source: CONFIG, subtype: first matched.

#### Normalization

| source field       | → TimelineEntry field | notes |
|--------------------|-----------------------|-------|
| unix_ts (author)   | `ts`                  | author date, not commit date |
| hash               | `ref` + `chain_id`    | commit hash is the chain anchor |
| subject            | `summary`             | commit message first line |
| author_name        | `detail.author`       | |
| author_email       | `detail.email`        | |
| insertions         | `detail.insertions`   | |
| deletions          | `detail.deletions`    | |
| files list         | `detail.files`        | list of touched paths |
| paths touched      | `source` + `subtype`  | via detection table above |
| —                  | `locality`            | always `shared` |
| —                  | `actor`               | `user` (all commits are user-initiated) |
| —                  | `severity`            | null (commits are informational) |

#### chain_id assignment

```
chain_id = commit_hash

The ledger_runs adapter matches CI runs to their triggering commit via
Run.code_ref == commit_hash — completing the commit→CI chain automatically.

CONFIG commits (touching project.yml / infra files) share chain_id with
the WIZARD/CONFIG scan_activity entry that preceded them, matched by
date proximity and target. Best-effort — not guaranteed.
```

#### Noise filter

```
DROP merge commits with no file changes (automated merge noise)
DROP commits where subject matches: "^Merge (branch|pull request)"
     AND insertions == 0 AND deletions == 0

KEEP everything else — all commits are signal
```

---

### Adapter 4 — `ledger_runs`
**Mediator node:** `timeline.source.ledger_runs`
**Reads:** `.ledger/` git branch — annotated tags `scp/run/<run_id>`
**mtime watch:** `.ledger/` refs directory

Each tag's annotation contains the Run JSON (run_id, type, subtype, status, user,
code_ref, started_at, ended_at, duration_ms, environment, modules_affected, summary).
Also reads `events.jsonl` per run for RunEvent granularity when needed.

#### Run.type → source mapping

| Run.type   | source | notes |
|------------|--------|-------|
| `ci`       | CI     | |
| `test`     | TESTS  | |
| `deploy`   | CI     | subtype: deploy |
| *(other)*  | PLATFORM | subtype: Run.type |

#### Normalization

| source field       | → TimelineEntry field | notes |
|--------------------|-----------------------|-------|
| `started_at`       | `ts`                  | when the run began |
| `run_id`           | `ref`                 | |
| `type`             | `source`              | via mapping above |
| `subtype`          | `subtype`             | passthrough |
| `status`           | `status`              | |
| `summary`          | `summary`             | |
| `user`             | `actor`               | user → user; else automation |
| `environment`      | `env`                 | wrapped in list |
| `modules_affected` | `modules`             | |
| `duration_ms`      | `detail.duration_ms`  | |
| `ended_at`         | `detail.ended_at`     | |
| `code_ref`         | `chain_id`            | links run → triggering git commit |
| —                  | `locality`            | always `shared` (on ledger branch) |
| —                  | `severity`            | failed + CI → high; failed + TESTS → medium |

#### chain_id assignment

```
chain_id = Run.code_ref  (the git commit hash that triggered this run)

This links the run back to its commit in git_log — completing the
commit → CI run chain. If code_ref is null, chain_id = run_id.
```

#### Noise filter

None. All ledger runs are signal — they were deliberately committed to the ledger.

---

### Adapter 5 — `ledger_audits`
**Mediator node:** `timeline.source.ledger_audits`
**Reads:** `.ledger/audits/<id>.json` — audit snapshots on the ledger branch
**mtime watch:** `.ledger/` refs directory (same as ledger_runs)

These are the **shared** side of audit entries. The same audit operation appears in
`cli_ops` (local, when it ran) and here (shared, when it was committed to the ledger).
Both entries are kept — they are two distinct historical facts linked by chain_id.

#### Normalization

| source field        | → TimelineEntry field | notes |
|---------------------|-----------------------|-------|
| ledger commit ts    | `ts`                  | when committed to ledger — NOT when op ran |
| audit `id`          | `ref`                 | |
| audit `operation_id`| `chain_id`            | links to cli_ops entry for the same operation |
| audit level (L0/L1/L2) | `subtype`          | |
| audit `status`      | `status`              | |
| audit `summary`     | `summary`             | |
| findings count      | `severity`            | 0 findings → null; 1-3 → low; 4-10 → medium; 10+ → high |
| audit `environment` | `env`                 | |
| audit `modules`     | `modules`             | |
| audit data          | `detail`              | full snapshot passthrough |
| —                   | `source`              | always AUDIT |
| —                   | `locality`            | always `shared` |
| —                   | `actor`               | `user` (audit commits are user-initiated) |

#### chain_id assignment

```
chain_id = audit.operation_id

This is the same operation_id present in the cli_ops entry for the
same audit run. The two entries form a chain:

  ts=T1  ⬡  AUDIT L2 scan ran — 7 findings       (cli_ops, local)
  ts=T2  ⇡  AUDIT L2 committed to ledger           (ledger_audits, shared)

Both carry chain_id = operation_id. The UI can show them flat or collapsed.
```

#### Noise filter

None. All ledger audit entries are signal — committed to the ledger intentionally.

---

### Adapter 6 — `chat`
**Mediator node:** `timeline.source.chat`
**Reads:** `.ledger/chat/threads/<thread_id>/messages.jsonl` + thread metadata
**mtime watch:** `.ledger/chat/` directory

One timeline entry per event: thread creation, each message, thread deletion.
All events in a thread share chain_id = thread_id — the full conversation is traversable.

#### Event types → subtype mapping

| event              | subtype          | ts source          |
|--------------------|------------------|--------------------|
| Thread created     | `thread_created` | Thread.created_at  |
| Message sent       | `message`        | Message.ts         |
| Thread deleted     | `thread_deleted` | deletion ts        |

#### Normalization — Message entry

| source field       | → TimelineEntry field | notes |
|--------------------|-----------------------|-------|
| `ts`               | `ts`                  | |
| `id`               | `ref`                 | |
| `thread_id`        | `chain_id`            | all thread events share this |
| `user`             | `detail.user`         | |
| `hostname`         | `hostname`            | |
| `text` (truncated) | `summary`             | first 120 chars + "…" if longer |
| `text` (full)      | `detail.text`         | |
| `source`           | `detail.source`       | manual / trace / system |
| `refs`             | `detail.refs`         | linked resources |
| `run_id`           | `detail.run_id`       | if message is linked to a run |
| `trace_id`         | `detail.trace_id`     | if message is linked to a trace |
| —                  | `source`              | always CHAT |
| —                  | `subtype`             | message |
| —                  | `locality`            | always `shared` |
| —                  | `actor`               | `user` |
| —                  | `severity`            | null |

#### Normalization — Thread creation entry

| source field       | → TimelineEntry field |
|--------------------|-----------------------|
| `created_at`       | `ts`                  |
| `thread_id`        | `ref` + `chain_id`    |
| `title`            | `summary`             |
| `created_by`       | `detail.created_by`   |
| `anchor_run`       | `detail.anchor_run`   |
| `tags`             | `detail.tags`         |

#### chain_id assignment

```
chain_id = thread_id for ALL events in a thread (creation, messages, deletion)

If a message has run_id set, it is also a member of the run's chain.
In that case the entry carries two chain memberships:
  - chain_id = thread_id  (the conversation chain)
  - detail.run_chain = run_id  (secondary link — UI can cross-navigate)
```

#### Noise filter

```
DROP system messages where source == "system" AND text contains internal
     platform noise (heartbeat confirmations, sync acks)

KEEP all user messages, trace-linked messages, thread creation, thread deletion
```

---

---

## 10. Frontend Design

### 10.1 — Placement decision

The timeline starts as **its own tab** — not inside Debugging.
The Debugging Audit Log stays as-is. The timeline is a promotion, not a rename.
When the timeline is mature and trusted, the Audit Log inside Debugging can be deprecated.

---

### 10.2 — File structure

```
src/ui/web/templates/
  partials/
    _tab_timeline.html       ← NEW: tab shell (header + container divs)
  scripts/
    _timeline.html           ← NEW: all timeline JS (state, rendering, SSE, scroll)

src/ui/web/static/css/
  admin.css                  ← EDIT: add .timeline-* classes

src/ui/web/templates/partials/
  _nav.html                  ← EDIT: add Timeline tab button

src/ui/web/templates/scripts/
  _tabs.html                 ← EDIT: add case in switchTab()
  _event_stream.html         ← EDIT: add handler for timeline:entry event type

src/ui/web/templates/
  dashboard.html             ← EDIT: include _tab_timeline.html + _timeline.html
```

---

### 10.2b — Left navigator panel (`_timeline_nav.html`)

Separate partial following the exact same structure as `_glossary.html`.

```html
<div id="timeline-nav-panel" class="timeline-nav-panel">

  <!-- Mode tabs — mirrors glossary mode tabs -->
  <div class="timeline-nav-modes">
    <button data-tl-nav-mode="chains"   onclick="_tlNavMode('chains')"   class="active">📎 Chains</button>
    <button data-tl-nav-mode="domains"  onclick="_tlNavMode('domains')">🌐 Domains</button>
    <button data-tl-nav-mode="calendar" onclick="_tlNavMode('calendar')">📅 Calendar</button>
  </div>

  <!-- Filter (chains mode only) -->
  <div id="tl-nav-search-wrap">
    <input id="tl-nav-search" type="text" placeholder="🔍 Filter chains..."
           oninput="_tlNavFilterDebounce()">
  </div>

  <!-- Chains mode tree -->
  <div id="tl-nav-chains" class="tl-nav-tree">
    <!-- Populated by _tlNavRenderChains() -->
    <!-- Each chain node: collapsible, shows member entries -->
  </div>

  <!-- Domains mode tree -->
  <div id="tl-nav-domains" class="tl-nav-tree" style="display:none">
    <!-- Populated by _tlNavRenderDomains() -->
    <!-- Each domain: collapsible, shows subtypes with counts -->
  </div>

  <!-- Calendar mode -->
  <div id="tl-nav-calendar" class="tl-nav-calendar" style="display:none">
    <!-- Mini calendar: month grid, dots on active days -->
    <!-- Click a day → sets date_from/date_to filter -->
  </div>

  <!-- Resize handle -->
  <div id="tl-nav-resize" class="tl-nav-resize-handle"></div>
</div>
```

#### Chain node rendering

```javascript
function _tlNavRenderChainNode(chain) {
  const statusIcon  = { ok:'●', warning:'◑', attention:'⚠', failed:'✕' }[chain.status] ?? '●';
  const isActive    = _tlNavActiveChain === chain.chain_id;
  const isExpanded  = _tlNavExpanded[chain.chain_id] ?? false;

  const membersHtml = chain.members.map(m => `
    <div class="tl-nav-member ${_tlNavActiveChain === chain.chain_id ? 'active' : ''}"
         data-entry-id="${esc(m.id)}"
         onclick="_tlNavJumpToEntry('${esc(m.id)}')"
         onmouseenter="_tlNavHoverChain('${esc(chain.chain_id)}')"
         onmouseleave="_tlNavUnhover()">
      <span class="tl-nav-member-role">${m.chain_role === 'origin' ? '○' : m.chain_role === 'terminal' ? '●' : '·'}</span>
      <span class="tl-nav-member-locality">${m.locality === 'shared' ? '⇡' : '⬡'}</span>
      <span class="tl-nav-member-summary">${esc(_tlTruncate(m.summary, 28))}</span>
      <span class="tl-nav-member-time">${_tlFormatTimeShort(m.ts)}</span>
    </div>
  `).join('');

  return `
  <div class="tl-nav-chain ${isActive ? 'tl-nav-chain--active' : ''}"
       data-chain-id="${esc(chain.chain_id)}">
    <div class="tl-nav-chain-header"
         onclick="_tlNavSelectChain('${esc(chain.chain_id)}')"
         onmouseenter="_tlNavHoverChain('${esc(chain.chain_id)}')"
         onmouseleave="_tlNavUnhover()">
      <span class="tl-nav-chain-toggle" onclick="event.stopPropagation();_tlNavToggleChain('${esc(chain.chain_id)}')">
        ${isExpanded ? '▾' : '▸'}
      </span>
      <span class="tl-nav-chain-icon">📎</span>
      <span class="tl-nav-chain-label">${esc(_tlTruncate(chain.label, 22))}</span>
      <span class="tl-nav-chain-count">(${chain.members.length})</span>
      <span class="tl-nav-chain-status" style="color:${_tlStatusColor(chain.status)}">${statusIcon}</span>
    </div>
    <div class="tl-nav-chain-members ${isExpanded ? '' : 'tl-nav-collapsed'}">
      ${membersHtml}
    </div>
  </div>`;
}
```

#### Hover + active sync (mirrors `_glossaryUpdateActive`)

```javascript
// Hover: soft highlight all chain members in the right list
function _tlNavHoverChain(chainId) {
  document.querySelectorAll('.timeline-entry').forEach(el => {
    el.classList.toggle('tl-chain-hover', el.dataset.chain === chainId);
  });
}

// Click chain: select + filter right list to that chain
function _tlNavSelectChain(chainId) {
  _tlNavActiveChain = chainId;
  _tlState.chainFilter = chainId;
  _tlLoadPage(false);  // full reset with chain_id filter
  _tlNavRenderChains(); // re-render to update active state
}

// Scroll sync: as right list scrolls, highlight chains in view
function _tlSyncNavFromScroll() {
  const entries = document.querySelectorAll('.timeline-entry[data-chain]');
  const viewportMid = window.scrollY + window.innerHeight / 2;
  let closest = null, closestDist = Infinity;
  entries.forEach(el => {
    const dist = Math.abs(el.getBoundingClientRect().top - viewportMid);
    if (dist < closestDist) { closest = el; closestDist = dist; }
  });
  if (closest) _tlNavScrollTo(closest.dataset.chain);
}
```

---

### 10.3 — Tab shell (`_tab_timeline.html`)

```html
<div id="tab-timeline" class="tab-content">
<div id="timeline-layout">  <!-- flex row: nav panel + main panel -->

  <!-- LEFT: Navigator panel (included from _timeline_nav.html) -->
  <!-- ... -->

  <!-- RIGHT: Main panel -->
  <div id="timeline-main">

  <!-- Toolbar: filters + search + sort + locality toggle -->
  <div id="timeline-toolbar">

    <div id="timeline-filter-bar">
      <!-- Active filter pills — each pill is removable -->
      <div id="timeline-active-filters"></div>

      <!-- Source multi-select pill -->
      <button id="timeline-source-btn" onclick="_tlToggleSourceMenu()">
        Sources ▾
      </button>
      <div id="timeline-source-menu" class="timeline-dropdown" style="display:none">
        <!-- one checkbox per source, dynamically populated -->
      </div>

      <!-- Status filter pill -->
      <button id="timeline-status-btn" onclick="_tlToggleStatusMenu()">Status ▾</button>
      <div id="timeline-status-menu" class="timeline-dropdown" style="display:none">
        <label><input type="checkbox" value="ok"> ● ok</label>
        <label><input type="checkbox" value="warning"> ◑ warning</label>
        <label><input type="checkbox" value="attention"> ⚠ attention</label>
        <label><input type="checkbox" value="failed"> ✕ failed</label>
      </div>

      <!-- Severity filter -->
      <button id="timeline-severity-btn" onclick="_tlToggleSeverityMenu()">Severity ▾</button>

      <!-- Locality toggle: All / Local only / Shared only -->
      <div id="timeline-locality-toggle">
        <button onclick="_tlSetLocality(null)" class="active">All</button>
        <button onclick="_tlSetLocality('local')">⬡ Local</button>
        <button onclick="_tlSetLocality('shared')">⇡ Shared</button>
      </div>

      <!-- Sort -->
      <select id="timeline-sort" onchange="_tlApplySort()">
        <option value="ts:desc">Newest first</option>
        <option value="ts:asc">Oldest first</option>
        <option value="severity:desc">Most critical</option>
        <option value="status:desc">Failures first</option>
        <option value="source:asc">By domain</option>
      </select>
    </div>

    <!-- Search -->
    <div id="timeline-search-wrap">
      <span>🔍</span>
      <input id="timeline-search" type="text"
        placeholder="Search summary, target, module…"
        oninput="_tlSearchDebounce()">
    </div>

    <!-- Live indicator -->
    <div id="timeline-live-indicator" title="Live — new entries appear automatically">⟳ Live</div>

  </div>

  <!-- Entry list -->
  <div id="timeline-list">
    <!-- Date group headers + entry rows rendered here -->
  </div>

  <!-- Scroll sentinel — IntersectionObserver watches this to trigger next page load -->
  <div id="timeline-sentinel" style="height:1px"></div>

  <!-- Loading indicator -->
  <div id="timeline-loading" style="display:none">Loading…</div>

</div>
```

---

### 10.4 — JS state model

Single state object — single source of truth for the timeline panel.

```javascript
const _tlState = {
  // Pagination
  nextCursor:   null,     // before_ts for next page (null = not yet loaded)
  prevCursor:   null,     // after_ts for live refresh
  hasMore:      true,     // false = all history loaded
  loading:      false,    // guard against concurrent fetches

  // Filters — each maps directly to an API param
  sources:      [],       // string[] — empty = all
  statuses:     [],       // string[]
  severities:   [],       // string[]
  locality:     null,     // null | "local" | "shared"
  envs:         [],       // string[]
  modules:      [],       // string[]
  sortBy:       "ts",
  sortDir:      "desc",
  q:            "",       // free text

  // Live
  liveEntries:  [],       // entries received via SSE not yet rendered
  liveTimer:    null,     // debounce timer for batch prepend

  // Rendered state
  lastDate:     null,     // last date group header rendered (for grouping logic)
};
```

---

### 10.5 — Rendering pipeline

#### Entry row structure

Follows the same expandable pattern as `_renderAuditEntry()` — inline onclick, hidden detail div.

```javascript
function _tlRenderEntry(entry, idx) {
  const statusIcon  = { ok:'●', warning:'◑', attention:'⚠', failed:'✕' }[entry.status] ?? '●';
  const statusColor = { ok:'var(--success)', warning:'var(--warning)',
                        attention:'var(--warning)', failed:'var(--error)' }[entry.status];
  const localityIcon = entry.locality === 'shared' ? '⇡' : '⬡';
  const localityColor = entry.locality === 'shared' ? 'var(--accent)' : 'var(--text-muted)';

  // Chain indicator — shown on entries belonging to a chain
  const chainBadge = entry.chain_id
    ? `<span class="tl-chain-badge" title="Part of a chain"
             onclick="event.stopPropagation();_tlNavSelectChain('${esc(entry.chain_id)}')">🔗</span>`
    : '';

  // Chain thread connector — vertical line on terminal entries pointing back to origin
  // The CSS connector is drawn by marking entries with data-chain-role and letting
  // CSS ::before pseudo-elements draw the thread between consecutive chain members
  const isChainMember = !!entry.chain_id;
  const chainRoleClass = entry.chain_role ? `tl-chain-${entry.chain_role}` : '';

  // Chain footer — shown below terminal entries with link to full chain view
  const chainFooter = entry.chain_role === 'terminal' && entry.chain_id ? `
    <div class="tl-chain-footer">
      ↳ chain: <em>${esc(_tlChainLabel(entry.chain_id))}</em>
      <button onclick="event.stopPropagation();_tlNavSelectChain('${esc(entry.chain_id)}')"
              class="tl-chain-view-btn">view chain</button>
    </div>` : '';

  return `
  <div class="timeline-entry ${chainRoleClass} ${isChainMember ? 'tl-in-chain' : ''}"
       id="tl-entry-${idx}"
       data-chain="${esc(entry.chain_id ?? '')}"
       data-chain-role="${esc(entry.chain_role ?? '')}"
       style="border-left:3px solid ${statusColor}">

    <!-- Header row — always visible -->
    <div class="timeline-entry-header" onclick="_tlToggleDetail(${idx})">
      <span class="tl-status" style="color:${statusColor}">${statusIcon}</span>
      <span class="tl-locality" style="color:${localityColor}">${localityIcon}</span>
      <span class="tl-source-badge tl-source-${entry.source.toLowerCase()}">${entry.source}</span>
      ${entry.subtype ? `<span class="tl-subtype">${esc(entry.subtype)}</span>` : ''}
      <span class="tl-summary">${esc(entry.summary)}</span>
      ${entry.severity ? `<span class="tl-severity tl-sev-${entry.severity}">${entry.severity}</span>` : ''}
      ${chainBadge}
      <span class="tl-time" title="${esc(entry.ts)}">${_tlFormatTime(entry.ts)}</span>
      <span class="tl-env">${(entry.env ?? []).join(' → ')}</span>
      <button class="tl-raw-btn" onclick="event.stopPropagation();_tlToggleRaw(${idx})"
              title="Raw JSON">{ }</button>
    </div>

    <!-- Expandable detail -->
    <div id="tl-detail-${idx}" class="timeline-entry-detail" style="display:none">
      ${_tlRenderDetail(entry)}
    </div>

    <!-- Raw JSON -->
    <div id="tl-raw-${idx}" class="timeline-entry-raw" style="display:none">
      <pre>${esc(JSON.stringify(entry, null, 2))}</pre>
    </div>

    <!-- Chain footer (terminal entries only) -->
    ${chainFooter}

  </div>`;
}
```

#### Date group header

Injected between entries when the date changes.

```javascript
function _tlMaybeDateHeader(entry) {
  const d = new Date(entry.ts * 1000);
  const key = d.toDateString();
  if (key === _tlState.lastDate) return '';
  _tlState.lastDate = key;
  const label = _tlDateLabel(d);  // "TODAY — March 14, 2026" / "YESTERDAY — ..." / "March 12, 2026"
  return `<div class="timeline-date-header">${label}</div>`;
}
```

---

### 10.6 — SSE integration

Register a handler for `timeline:entry` in `_event_stream.html`:

```javascript
// In _event_stream.html — add to the event type → handler map:
'timeline:entry': (event) => {
  if (typeof _tlOnLiveEntry === 'function') _tlOnLiveEntry(event.data);
},
```

In `_timeline.html`:

```javascript
function _tlOnLiveEntry(entry) {
  // Buffer live entries — don't render every single one immediately
  _tlState.liveEntries.push(entry);
  clearTimeout(_tlState.liveTimer);
  _tlState.liveTimer = setTimeout(_tlFlushLiveEntries, 800);  // batch 800ms
}

function _tlFlushLiveEntries() {
  if (!_tlState.liveEntries.length) return;
  const entries = [..._tlState.liveEntries];
  _tlState.liveEntries = [];

  // Filter against current active filters before rendering
  const filtered = entries.filter(_tlPassesFilter);
  if (!filtered.length) return;

  // Prepend to list with highlight animation
  const html = filtered.map((e, i) => _tlMaybeDateHeader(e) + _tlRenderEntry(e, 'live-' + Date.now() + i)).join('');
  const list = document.getElementById('timeline-list');
  list.insertAdjacentHTML('afterbegin', html);

  // Update prevCursor to newest entry
  _tlState.prevCursor = Math.max(...filtered.map(e => e.ts));
}
```

---

### 10.7 — Scroll-triggered loading (IntersectionObserver)

```javascript
function _tlInitScrollObserver() {
  const sentinel = document.getElementById('timeline-sentinel');
  const observer = new IntersectionObserver((entries) => {
    if (entries[0].isIntersecting && _tlState.hasMore && !_tlState.loading) {
      _tlLoadPage(true);  // append = true
    }
  }, { rootMargin: '200px' });  // trigger 200px before sentinel is visible
  observer.observe(sentinel);
}
```

---

### 10.8 — API call + filter application

```javascript
async function _tlLoadPage(append = false) {
  if (_tlState.loading) return;
  if (!append) {
    // Full reset — clear list, reset cursors
    _tlState.nextCursor = null;
    _tlState.prevCursor = null;
    _tlState.hasMore = true;
    _tlState.lastDate = null;
    document.getElementById('timeline-list').innerHTML = '';
  }

  _tlState.loading = true;
  document.getElementById('timeline-loading').style.display = '';

  try {
    const params = new URLSearchParams({ limit: 50 });
    if (_tlState.nextCursor)         params.set('before_ts',  _tlState.nextCursor);
    if (_tlState.sources.length)     _tlState.sources.forEach(s  => params.append('source[]', s));
    if (_tlState.statuses.length)    _tlState.statuses.forEach(s => params.append('status[]', s));
    if (_tlState.severities.length)  _tlState.severities.forEach(s => params.append('severity[]', s));
    if (_tlState.locality)           params.set('locality', _tlState.locality);
    if (_tlState.envs.length)        _tlState.envs.forEach(e => params.append('env[]', e));
    if (_tlState.q)                  params.set('q', _tlState.q);
    params.set('sort_by', _tlState.sortBy);
    params.set('sort_dir', _tlState.sortDir);

    const data = await api('/timeline?' + params.toString());

    const list = document.getElementById('timeline-list');
    const html = data.entries.map((e, i) =>
      _tlMaybeDateHeader(e) + _tlRenderEntry(e, (append ? 'p' : '') + i)
    ).join('');

    list.insertAdjacentHTML('beforeend', html);

    _tlState.hasMore    = data.has_more;
    _tlState.nextCursor = data.next_cursor;
    if (!append) _tlState.prevCursor = data.prev_cursor;

  } finally {
    _tlState.loading = false;
    document.getElementById('timeline-loading').style.display = 'none';
  }
}
```

---

### 10.9 — CSS additions (admin.css)

New classes follow existing conventions — CSS variables only, no hardcoded colors.

```css
/* Timeline tab layout */
.timeline-entry           { display:flex; flex-direction:column; gap:3px; padding:10px 14px;
                            margin-bottom:4px; border-radius:var(--radius-sm);
                            background:var(--bg-secondary); }
.timeline-entry-header    { display:flex; align-items:center; gap:8px; flex-wrap:wrap;
                            cursor:pointer; font-size:0.8rem; }
.timeline-entry-header:hover { background:var(--bg-card-hover); border-radius:var(--radius-sm); }
.timeline-entry-detail    { padding:6px 10px; margin-top:4px; border-radius:var(--radius-sm);
                            background:var(--bg-primary); border:1px solid var(--border-subtle);
                            font-size:0.72rem; }
.timeline-entry-raw       { padding:8px 10px; margin-top:4px; border-radius:var(--radius-sm);
                            background:var(--bg-inset); font-family:var(--font-mono);
                            font-size:0.66rem; max-height:280px; overflow-y:auto; }
.timeline-date-header     { font-size:0.68rem; font-weight:600; color:var(--text-muted);
                            text-transform:uppercase; letter-spacing:0.6px;
                            padding:12px 4px 4px; border-bottom:1px solid var(--border-subtle);
                            position:sticky; top:0; background:var(--bg-primary); z-index:1; }
/* Source badges — one color per domain */
.tl-source-badge          { font-size:0.6rem; font-weight:700; letter-spacing:0.5px;
                            text-transform:uppercase; padding:2px 6px;
                            border-radius:var(--radius-sm); flex-shrink:0; }
.tl-source-git            { background:rgba(59,130,246,0.12); color:#60a5fa; }
.tl-source-audit          { background:rgba(139,92,246,0.12); color:#a78bfa; }
.tl-source-security       { background:rgba(239,68,68,0.12); color:#f87171; }
.tl-source-pkg            { background:rgba(52,211,153,0.12); color:#34d399; }
.tl-source-vault          { background:rgba(245,158,11,0.12); color:#fbbf24; }
.tl-source-ci             { background:rgba(99,102,241,0.12); color:#818cf8; }
.tl-source-chat           { background:rgba(20,184,166,0.12); color:#2dd4bf; }
.tl-source-wizard         { background:rgba(244,114,182,0.12); color:#f472b6; }
.tl-source-config         { background:rgba(251,146,60,0.12); color:#fb923c; }
/* Severity */
.tl-severity              { font-size:0.6rem; font-weight:600; padding:1px 5px;
                            border-radius:var(--radius-sm); flex-shrink:0; }
.tl-sev-critical          { background:rgba(239,68,68,0.15); color:#f87171; }
.tl-sev-high              { background:rgba(245,158,11,0.15); color:#fbbf24; }
.tl-sev-medium            { background:rgba(59,130,246,0.12); color:#60a5fa; }
.tl-sev-low               { background:rgba(148,163,184,0.1); color:var(--text-muted); }
/* New entry highlight animation */
@keyframes tl-new-entry   { from { background:rgba(59,130,246,0.15); } to { background:var(--bg-secondary); } }
.timeline-entry.tl-new    { animation:tl-new-entry 1.5s ease-out; }

/* Two-panel layout */
#timeline-layout          { display:flex; height:100%; gap:0; overflow:hidden; }
#timeline-main            { flex:1; overflow-y:auto; min-width:0; padding:0 var(--space-md); }

/* Left navigator panel — mirrors .glossary-panel */
.timeline-nav-panel       { width:220px; min-width:160px; max-width:340px; flex-shrink:0;
                            border-right:1px solid var(--border); overflow-y:auto;
                            display:flex; flex-direction:column; background:var(--bg-secondary); }
.timeline-nav-modes       { display:flex; gap:2px; padding:var(--space-sm); flex-shrink:0; }
.timeline-nav-modes button { flex:1; padding:4px 6px; font-size:0.68rem; border-radius:var(--radius-sm);
                             border:1px solid transparent; background:transparent;
                             color:var(--text-muted); cursor:pointer; }
.timeline-nav-modes button.active { background:var(--bg-inset); color:var(--text-primary);
                                    border-color:var(--border); }
.tl-nav-tree              { flex:1; overflow-y:auto; padding:var(--space-xs) 0; }

/* Chain nodes in navigator */
.tl-nav-chain             { border-radius:var(--radius-sm); margin:1px var(--space-xs); }
.tl-nav-chain:hover       { background:var(--bg-card); }
.tl-nav-chain--active     { background:var(--accent-glow); }
.tl-nav-chain-header      { display:flex; align-items:center; gap:4px; padding:4px 8px;
                            font-size:0.72rem; cursor:pointer; }
.tl-nav-chain-label       { flex:1; min-width:0; overflow:hidden; text-overflow:ellipsis;
                            white-space:nowrap; color:var(--text-primary); }
.tl-nav-chain-count       { font-size:0.62rem; color:var(--text-muted); }
.tl-nav-chain-members     { padding-left:16px; }
.tl-nav-collapsed         { display:none; }
.tl-nav-member            { display:flex; align-items:center; gap:4px; padding:2px 6px;
                            font-size:0.66rem; cursor:pointer; border-radius:var(--radius-sm); }
.tl-nav-member:hover      { background:var(--bg-inset); }
.tl-nav-member.active     { color:var(--accent); }
.tl-nav-member-summary    { flex:1; min-width:0; overflow:hidden; text-overflow:ellipsis;
                            white-space:nowrap; color:var(--text-secondary); }
.tl-nav-member-time       { font-size:0.6rem; color:var(--text-muted); flex-shrink:0; }

/* Chain threading in main list */
.tl-in-chain              { position:relative; }
.tl-chain-origin::after   { content:''; position:absolute; left:-2px; top:100%; width:2px;
                            height:8px; background:var(--border); }
.tl-chain-step::before    { content:''; position:absolute; left:-2px; bottom:100%; width:2px;
                            height:8px; background:var(--border); }
.tl-chain-step::after     { content:''; position:absolute; left:-2px; top:100%; width:2px;
                            height:8px; background:var(--border); }
.tl-chain-terminal::before { content:''; position:absolute; left:-2px; bottom:100%; width:2px;
                             height:8px; background:var(--border); }
.tl-chain-footer          { font-size:0.66rem; color:var(--text-muted); padding:2px 4px 4px 24px; }
.tl-chain-view-btn        { font-size:0.62rem; padding:1px 6px; border-radius:var(--radius-sm);
                            border:1px solid var(--border-subtle); background:transparent;
                            color:var(--accent); cursor:pointer; margin-left:4px; }
.tl-chain-badge           { font-size:0.72rem; cursor:pointer; opacity:0.7; }
.tl-chain-badge:hover     { opacity:1; }

/* Chain hover highlight from navigator */
.timeline-entry.tl-chain-hover { background:var(--accent-glow); }

/* Resize handle */
.tl-nav-resize-handle     { width:4px; cursor:col-resize; position:absolute; right:0; top:0;
                            height:100%; background:transparent; }
.tl-nav-resize-handle:hover { background:var(--accent); opacity:0.3; }
```

---

## Open questions (foundation level)

- [ ] Does `severity` need to be in the foundation model, or is it source-specific detail?
- [ ] Should `hostname` + `os` + `platform` be a nested `origin` object for cleanliness?
- [ ] How do we handle multi-machine scenarios — same event produced on two machines?
- [ ] Is `PLAN` a real source or a subtype of GIT (commits that touch `.agent/` paths)?
