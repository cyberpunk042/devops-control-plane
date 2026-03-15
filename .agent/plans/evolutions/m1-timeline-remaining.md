# M1 Timeline — Remaining Work

> Status: PLAN — captures all outstanding issues and next steps.
> Ordered by dependency, not priority.

---

## A. Chain linking — missing chain types

### What exists now
- Index cycle chains (scan, delta, files, dirs, paths, classify) — works for synchronous phase, background tiers now wired
- Chat thread chains — works
- Solo chain filter — hides single-entry chains

### What's missing

#### A1. Git commit chains
Git commits have parent hashes (chain_parent_ref is set) but each commit
has its own chain_id (= commit hash). They don't form multi-member chains
because no other entry shares their chain_id.

**Real chains that should exist:**
- Commits on the same branch within a session/time window
- Commit → CI run (when ledger_runs have code_ref matching the commit)
- Commit → config change (when wizard/config events precede a commit)

**Options:**
- Group commits by time proximity (e.g., commits within 1 hour = same chain)
- Group commits by branch (requires branch detection from git log)
- Only chain commits when they have linked runs/events (conservative)

#### A2. Audit lifecycle chains
L0 scan → L1 scan → L2 scan for the same domain. These are progressive
levels. Currently they fire as separate scan_activity entries with no link.

**Linking key:** card_key prefix (e.g., `audit:scores` → `audit:scores:enriched`)
or time proximity within the same index cycle.

#### A3. CLI operation → scan_activity → ledger
The infrastructure is built (operation_context, record_scan_activity writes
operation_id). But CLI operations and mediator scans run on different
timelines. A CLI `test` command triggers scans via the executor, but the
mediator card scans (devops.testing, etc.) run in the index watcher cycle,
not during the executor's operation.

**Gap:** The executor's operation_id is only active during `execute_plan()`.
Card scans triggered by the index watcher happen later, outside that window.
The link between "user ran test" and "testing card recomputed" doesn't exist
unless the card scan happens during the operation.

#### A4. Integration-specific chains
Each integration (Docker, K8s, Terraform, GitHub, etc.) produces scan
entries. Related scans should chain:
- docker detection → docker status update
- github pulls refresh → github runs refresh → github workflows refresh
- terraform detection → terraform plan
- package scan → CVE detection → package update

#### A5. Script/command chains
CLI commands that are part of a workflow:
- lint → format → test (quality pipeline)
- scan → audit → commit (audit pipeline)
- backup → verify → rotate (backup pipeline)

These run as separate CLI operations. Currently no link between them.
Could chain by time proximity or by explicit workflow_id.

---

## B. Chain UX issues

### B1. Chain click behavior
**Current:** Clicking a chain header toggles the filter (shows only that
chain's entries in the right panel) AND expands to show members.
**Problem:** This is confusing — the user expects clicking to open/explore
the chain, not to filter the entire timeline to just those entries.

**Target behavior:**
- Click chain header → expand/collapse members (like a tree node)
- Click a member → scroll to that entry in the right panel
- Filter pill appears only when explicitly requested (e.g., right-click
  "filter to this chain" or a filter icon button)

### B2. Hover behavior
**Current:** Hover highlights chain entries in the right panel.
**Problem:** Glitchy — the highlight flickers and doesn't always clear.

### B3. Empty chains panel
When no multi-member chains exist, the panel shows "No chains found".
Should show a helpful message explaining what chains are.

### B4. Chain tree rendering
The `_tlRenderChainTree` function builds a tree from `chain_parent_ref`.
But for index cycles, all members have `chain_parent_ref = cycle_id`
(flat, all children of the root). The tree should show them as siblings
under the origin, not as a nested tree.

---

## C. UX pass — full review

### C1. Click targets and affordances
- Every clickable element needs clear hover state
- Click targets need to be large enough (min 32px height)
- Distinguish between "navigate to" and "filter by" clicks
- Remove ambiguity: expanding a tree node vs selecting/filtering

### C2. Glitchy interactions
- Hover highlight on chains flickers
- Scroll-to-entry sometimes doesn't find the target
- Filter pills row can get very wide with many filters
- Calendar/domain tree expand/collapse can feel laggy with many entries

### C3. Empty states
- Each navigator mode needs a useful empty state message
- First-time user orientation (Gap 6 from timeline-ux-gaps.md)

### C4. Visual hierarchy
- Adapter names in domain tree are cryptic (scan_activity, cli_ops, git_log)
  — should have human-readable labels
- Chain summaries truncated — need tooltip with full text
- Status dots too small to distinguish colors
- Severity badge colors not consistent across views

### C5. Gaps from timeline-ux-gaps.md still open
- Gap 1: Locality toggle positioning (view mode vs filter)
- Gap 2: Filter pills causing layout reflow
- Gap 3: Sort control positioning
- Gap 5: Chain navigator as tree (partially done)
- Gap 6: No orientation for first-time users
- Gap 7: Entry detail is source-blind key-value dump

---

## D. Execution priority (suggested)

1. **A1 — Git commit chains** — highest value, most visible data
2. **B1 — Chain click UX** — fundamental interaction is broken
3. **A2 — Audit lifecycle chains** — connects existing data
4. **C4 — Human-readable adapter labels** — quick win for domains tree
5. **C1-C3 — UX cleanup pass** — interaction quality
6. **A3-A5 — Deeper chain types** — requires infrastructure work
7. **C5 — Remaining UX gaps** — from original gap analysis

---

## Open questions

1. For git commit chains: group by time proximity, by branch, or only
   when linked to other events (runs, configs)?
2. Should chain click expand the chain or filter the timeline? What's
   the expected primary action?
3. Should adapter names in the domains tree be human-readable
   (e.g., "Scan Activity" instead of "scan_activity")?
4. Which of the remaining UX gaps (Gap 1, 2, 3, 6, 7) should be
   tackled in this iteration vs deferred?
