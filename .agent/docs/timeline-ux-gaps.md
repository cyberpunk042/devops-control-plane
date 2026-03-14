# UX Gap Analysis — History / Timeline View

> Date: 2026-03-14
> Scope: The History/Timeline page of the DevOps control plane admin panel (port 8000).
> Purpose: Capture every observed UX failure with concrete scenario walkthroughs, expected behavior, and fix direction.

---

## Gap 1 — Locality toggle is buried as a filter instead of positioned as a view mode

### The gap

The "All / Local / Shared" selector is placed inside the filter bar, sandwiched between dropdowns for source, status, and severity. But locality is not a filter. It is a **perspective lens** — a fundamental choice about which data universe you are looking at.

- **Local** = events recorded only on this machine, not committed to the team ledger.
- **Shared** = events that have been committed to the team ledger and are visible to all members.
- **All** = both Local and Shared combined.

Treating this as a filter implies it narrows down an already-loaded dataset. But it actually controls *which dataset is fetched at all*. The data behind "Local" and "Shared" are categorically different populations with different trust levels, different ownership, and different permanence. A developer looking at their own machine's draft events versus auditing the team's committed ledger are two completely different jobs-to-be-done.

### Scenario walkthrough

A developer finishes a deployment. They want to review the team's shared audit trail to confirm the deployment event was committed. They land on the History page. They see the timeline. The events shown are Local — their own uncommitted machine events — but they don't know that, because the "All / Local / Shared" control is tucked between two dropdowns and defaults to "All" without any prominent indication.

They add a filter for `source: CI` to find the deployment. The timeline reflows (see Gap 2). They still don't see the deployment event. They assume it wasn't recorded. They spend minutes second-guessing whether their CI integration works. Eventually, by accident, they click the locality dropdown and realize they were looking at "All" but their machine has no Local CI events — the Shared events simply weren't prominent in the mixed view. They switch to "Shared" and find the event immediately.

The user wasted time debugging an integration that was working perfectly, because the viewing lens had no visual weight relative to the filters.

### Expected behavior

The All / Local / Shared control should sit above or visually separate from the filter bar, styled as a **segmented tab selector** or **view mode switcher** — the same visual weight as a tab group at the top of the page. It should be the first thing a user sees when they land. The current active mode should be legible without reading fine print. Switching it should feel like switching pages, not adjusting a dropdown.

### Fix direction

Promote the locality selector to a view-mode selector. Separate it from the filter bar visually. Give it the same prominence as a top-level navigation tab. It is not a predicate on a list — it is the identity of the list itself.

---

## Gap 2 — Applying a filter causes layout instability and displaces active controls

### The gap

When a filter is applied (e.g., selecting a source from the dropdown), an active filter pill is inserted into the toolbar row. This causes the toolbar to reflow: the sort control, the locality selector, the search input — all shift position. The user's cursor is no longer near the control they just used. The spatial map of the page has changed beneath them.

### Scenario walkthrough

A user wants to narrow the timeline to SECURITY events, then sort by severity descending. The workflow:

1. They click the source dropdown and select "SECURITY". A filter pill appears inline. The toolbar row is now taller or wider, and the sort dropdown has moved to a different x/y position on screen.
2. They move to click the sort dropdown — but their muscle memory is wrong. The sort control has shifted. They either click the wrong element or miss it entirely.
3. They add a second filter, `status: ERROR`. Another pill appears. The row reflows again. The sort dropdown has moved again.
4. By the time they have three active filters, the sort control is in a completely different position than when they started.

This creates a classic layout instability problem: every action changes the canvas, so the user must re-orient after every step. The interaction becomes cognitively expensive. Users working quickly — which is the norm in an incident response scenario where this view is most critical — will make mistakes.

### Expected behavior

The toolbar should be **spatially stable**. Applying filters should not move any other control. Filter pills should appear in a dedicated zone (below the toolbar row, or in a collapsible chip strip) that does not displace the core toolbar controls. The sort control, the search input, and the locality selector should be at fixed positions regardless of how many filters are active.

### Fix direction

Separate filter state (the active pills) from filter affordances (the dropdowns). The dropdowns stay in their fixed positions. The resulting active filter pills render in a dedicated strip below the toolbar, which expands/contracts without pushing any toolbar element. The toolbar row has a fixed height and fixed control positions.

---

## Gap 3 — Sort control is positioned in the middle of the toolbar, not at the trailing edge

### The gap

Sort is mixed into the middle of the filter controls. Sort is not a filter — it does not change what events are shown, only the order in which they appear. It is a meta-control on the full result set. Convention across every mature list/table UI (GitHub Issues, Linear, Jira, Notion) places sort at the trailing (rightmost) edge of the toolbar, visually and semantically separated from the filtering controls on the left.

### Scenario walkthrough

A user has just landed on the History page and wants to get the most recent events first. They scan the toolbar left-to-right expecting sort to be on the right. They find it in the middle between two dropdowns. They are momentarily confused, thinking perhaps the sort is a filter variant. The label "Sort" is there, but it's lost in the visual sequence of dropdowns. They either miss it, interact with the wrong control, or take extra seconds to re-orient.

In a more advanced case: the user has added filters and the toolbar has reflowed (Gap 2). Now sort is not just in the wrong position conceptually — it has also physically moved. They cannot form a reliable mental model of where sort lives.

### Expected behavior

Sort appears at the rightmost position in the toolbar, after all filter controls, optionally separated by a thin visual divider. It is always reachable by scanning to the right edge. Its position never changes.

### Fix direction

Pin the sort control to the trailing edge of the toolbar. Apply a visual separator (divider line or spacing increase) between filter dropdowns and the sort control to reinforce the conceptual distinction between "narrow the set" and "order the set."

---

## Gap 4 — Filter dropdowns list all possible option values, including those with zero matching events

### The gap

The source filter dropdown lists all 17 defined sources:

> GIT, AUDIT, PKG, VAULT, ENV, TOOLS, STACK, CI, TESTS, BACKUP, CHAT, PLAN, PLATFORM, POSTURE, SECURITY, WIZARD, CONFIG

In most projects, only 4–6 of these sources will have any events in the current dataset. The remaining 11–13 options are dead options — selecting them returns an empty timeline. They add noise, inflate the dropdown height, slow the user's scan, and create false affordance (the user thinks clicking them will show something).

### Scenario walkthrough

A user wants to find all vault-rotation events. They open the source dropdown and see 17 entries in alphabetical order. They find "VAULT" and click it. The timeline goes empty. They wonder whether vault events exist at all, or whether "VAULT" is the right label, or whether they need to change the locality mode first. In reality, this project simply never had vault events — the source was always empty. But the dropdown made it appear as a valid, live option.

In a different scenario: the user is under incident pressure, scanning quickly for the right source. They have to visually parse 17 items to find the 4 that are active. This is four times more cognitive work than necessary. The "fog of dead options" slows down the identification of live data.

### Expected behavior

The source dropdown (and status, severity dropdowns) should only show options that have at least one matching event in the current dataset (accounting for the current locality mode and any other active filters). Dead options are either hidden or shown in a visually dimmed/disabled state with a zero count badge. The active options are shown first, above a divider, with event counts.

### Fix direction

Compute option availability server-side or client-side as part of the query. Show counts alongside option labels ("CI (12)", "GIT (47)"). Hide or deprioritize zero-count options. This pattern is standard in faceted search (e-commerce filters, Elasticsearch facets) and should be applied here.

---

## Gap 5 — Chain navigator renders as a flat list instead of a tree

### The gap

A chain in this system is a causal sequence: ORIGIN → STEP → STEP → TERMINAL. This is explicitly hierarchical data. The chain navigator currently renders chains as flat list items with a count badge. There is no indentation, no parent-child visual relationship, no connector lines. It looks like a glossary or a tag cloud. The word "tree" in "outline tree" implies visual hierarchy — depth, branching, parent-child connectors. The current render is a list.

### Scenario walkthrough

A user is investigating a failed deployment. They know it was part of a chain of events: a PLAN event triggered a CI event which triggered a STACK event which failed. They open the chain navigator expecting to see this causal sequence laid out visually — so they can identify at which step the failure occurred.

Instead they see:

```
● chain-a8f3   (7)
● chain-b2c9   (3)
● chain-d1e4   (12)
```

These are flat items with a count badge. There is no indication of structure. "chain-a8f3 has 7 events" tells the user nothing about *which* of those 7 events is the ORIGIN, which is a STEP, and which is the TERMINAL where the failure occurred. The user has to click into the chain and mentally reconstruct the sequence from the event list — which defeats the purpose of a chain navigator.

The chain navigator fails at its core job: showing causal structure. It shows a directory listing instead of a chain.

### Expected behavior

Each chain in the navigator renders as an indented tree:

```
▼ chain-a8f3
    ○ PLAN:plan-create           [ORIGIN]
        ○ CI:pipeline-run        [STEP]
            ○ STACK:deploy       [STEP]
                ● STACK:rollback [TERMINAL — ERROR]
```

Parent nodes are expandable/collapsible. The failure node is visually marked (color, icon). The depth of the tree is visible at a glance. The user can identify the failure point without clicking into anything.

### Fix direction

Render the chain navigator as a recursive tree component. Use indentation + connector lines (or an outline-style disclosure triangle) to show depth. Display event type, step role (ORIGIN/STEP/TERMINAL), and status at each node. The chain is a first-class data structure — render it as one.

---

## Gap 6 — The page provides no orientation for a first-time user

### The gap

When a user lands on the History/Timeline page for the first time, there is no contextual guidance. The page presents two panels, a toolbar with labeled dropdowns, icons (🔗), and technical terms (PLATFORM, POSTURE, chain, source, severity) without any definition or explanation. The user has no way to know:

- What the left panel vs right panel represents.
- What a "source" is and how it differs from a "type" or "category."
- What a "chain" is and why it matters.
- What the 🔗 icon means on an event row.
- What "POSTURE" or "WIZARD" means in the context of this system.
- Why there is a Local vs Shared distinction and what the practical difference is.
- What actions they can take from this page and what those actions accomplish.

### Scenario walkthrough

A new developer has been added to a team. Their team lead says "go check the History page to see what happened with last night's deployment." The developer opens the History page. They see:

- A toolbar with dropdowns labeled "Source", "Status", "Severity", "Sort"
- A toggle labeled "All / Local / Shared" (buried — they may not even notice it)
- A list of events with type codes like `PLATFORM:config-drift`, `POSTURE:check-fail`, `STACK:deploy`
- Some events have a 🔗 icon
- A side panel labeled "Chains" showing a list of chain IDs

None of this is self-explanatory. The developer does not know what PLATFORM or POSTURE means. They do not know whether "Local" events are from their own machine or the local network. They do not know what a chain is or whether the 🔗 icon means "linked" or "chained" or something else entirely. They do not know if clicking a chain ID does anything.

They either give up and ask their team lead (interruption), or they start clicking randomly to reverse-engineer the interface (wasted time, risk of accidental state changes), or they form wrong mental models that cause systematic misreads of the data.

### Expected behavior

The page should provide orientation through:
1. An empty state with a brief explanation when there are no events.
2. Tooltip definitions on first-seen technical terms (source, chain, locality).
3. A brief one-line description in the panel headers explaining what each panel shows.
4. Icon labels or tooltips so that 🔗 is never a mystery.
5. Possibly a one-time onboarding callout that can be dismissed.

The goal is not a help page. The goal is enough inline context that a technical user with no prior knowledge of this system can form a correct mental model within 30 seconds of landing.

### Fix direction

Apply progressive disclosure. Add short, precise inline labels and tooltips to technical terms. Write panel header descriptions. Give every icon a tooltip. Write a one-sentence description of the page's purpose at the top. Make the empty state informative rather than blank.

---

## Underlying Principle Violations

### 1. Mental model mismatch (Norman — conceptual model)
The system's internal conceptual model (locality as a view mode, chains as trees, sources as active datasets) does not match what the UI presents (locality as a filter, chains as flat lists, sources as static enumerations). Every gap above is, at root, a failure to make the system's true model legible. Users form wrong mental models and then make wrong decisions.

### 2. Spatial consistency / stability (Nielsen Heuristic #4 — Consistency and Standards; Fitts' Law)
Gap 2 directly violates spatial consistency. When controls move after user interaction, the user's learned motor patterns break. In high-stakes, fast-moving contexts (incident response), this imposes a disproportionate cognitive and physical cost.

### 3. Progressive disclosure (Nielsen Heuristic #6 — Recognition over Recall; Information Architecture principle)
Gap 4 (showing all 17 sources including dead ones) and Gap 6 (no orientation for new users) both violate progressive disclosure. Users should see only what is relevant now, with full detail available on demand. Flooding the UI with all possible values at all times forces users to filter noise mentally before they can begin their task.

### 4. Hierarchy of information (Gestalt — figure/ground, proximity, hierarchy)
Gap 1 (locality buried as a filter) and Gap 3 (sort in the middle of filters) violate the principle that controls of different conceptual weight should have different visual weight. A view-mode selector and a filter dropdown should not look identical. A meta-control (sort) and a predicate control (filter) should not be intermixed without visual distinction.

### 5. Recognition over recall (Nielsen Heuristic #6)
Gap 5 (chain navigator as flat list) forces the user to recall the chain's structure rather than recognizing it. A tree visualization makes the structure recognizable without any prior knowledge. A flat list requires the user to have already loaded the chain's topology into working memory. This is a textbook recall-over-recognition failure.

### 6. Affordance clarity (Gibson — affordances; Norman — signifiers)
Gap 4 (dead filter options with no count) and Gap 6 (unexplained icons and terms) both present affordances that do not signal their true behavior or meaning. A filter option that returns no results looks identical to one that returns 50. An icon without a label provides no affordance about what clicking it will do. Users cannot form correct predictions about the outcome of their actions.

### 7. Learnability and first-use experience (Nielsen Heuristic #10 — Help and Documentation)
Gap 6 is a complete failure of learnability. A page in a complex technical system, used infrequently or by new team members, must provide enough inline orientation that the user can begin working without external help. This is not about writing documentation — it is about making the interface self-describing.

---

## Gap 7 — Entry detail is a raw key-value dump, not a source-aware view

### The gap

When a user clicks a timeline entry to expand its detail, they see a generic key-value list — every field in `entry.detail` rendered as `key: value` in the same monotone format, regardless of what the entry actually is. A GIT commit, a CHAT message, a CI build failure, and a vault rotation all produce the same-looking wall of keys and values.

This is not a detail view. It is a raw JSON inspection pane wearing a stylesheet. It has no awareness of what the entry represents, what fields matter for that source, or how to present them usefully.

Compare to what the Audit Log in the same Debugging tab does when you expand an entry:
- **Target** → rendered as a clickable file path
- **Before / After** → side-by-side red/green panels showing exactly what changed
- **Diff** → syntax-highlighted code block with `+` green, `-` red, `@@` purple
- **File list** → categorized into new / overridden / existing, each file clickable
- **Action badge** → colored label for the action type (created, modified, deleted, rotated…)
- **URLs and SSH git remotes** → rendered as clickable links

The Timeline has none of this. It has `key: value · key: value · key: value`.

### Scenario walkthrough

A developer sees a `CI — Build failed — lint error` entry in the Timeline. They click it to find out which file had the lint error. They see:

```
duration_ms   12340
ended_at      1741975200.0
code_ref      a8f3d1b
environment   dev
modules       ["api"]
errors        [{"file": "src/core/services/scanner.py", "rule": "E501", "line": 147}]
```

The errors field is there — but it's rendered as a stringified JSON array in a mono span. The user has to mentally parse JSON to find the file and line. There is no file link. There is no "1 error" summary. There is no clear affordance that the error is actionable.

Now the same user clicks a `GIT — fix: bugs — 5 ins, 1 del` entry. They want to see which files changed:

```
author        Jean Fortin
email         jean@example.com
insertions    5
deletions     1
files         ["src/core/services/scanner.py", "tests/test_scanner.py"]
```

The files are there as a plain comma-separated list in a span. No diff. No +5/-1 per file. No file links. Compare to any git log UI — GitHub, GitLab, even `git log --stat`. Every one of them shows files with per-file change counts.

Now the user clicks a `CHAT — wsl transport` message entry. They want to read the message. They see:

```
user    jfortin
text    Hey the WSL transport issue should be fixed in build 4...
```

The text is truncated at 120 chars (the `summary` truncation) and the `detail.text` field is rendered inline as a flat value. There is no readable message body. There is no thread context. There is no indication that the full text is available.

Every source has a specific shape of data that requires a specific rendering strategy. The current renderer ignores the shape entirely.

### Expected behavior

Each source gets its own rendering template for the expanded detail view:

| Source | Key information to surface | Format |
|--------|---------------------------|--------|
| GIT | Commit hash (short), author, insertions/deletions summary, file list with ±counts | Hash as mono, files as clickable list |
| AUDIT | Before/After state panels, action badge, diff if present, target path | Same pattern as audit log in Debugging tab |
| CHAT | Full message text, author, thread title, refs | Readable prose block |
| CI / TESTS | Run ID, duration, environment, modules, error list (file + line) | Error list as structured rows with file links |
| PKG | Package name, old version → new version (or CVE IDs found), ecosystem | Version transition row, CVE badges |
| VAULT | Action (rotated/added/deleted), target key name, timestamp | Action badge + key name |
| ENV | Variable name, before/after value, environment, promotion path | Before/After panels |
| SECURITY | CVE IDs, secret types found, finding count by severity | Severity-colored finding rows |
| POSTURE | Finding name, node/item, recommendation | Finding rows with severity badge |
| STACK | Stack name, detected version, EOL date if outdated | Version + EOL callout |
| TOOLS | Tool name, version installed/removed, ecosystem | Version row |
| BACKUP | Snapshot ID, size, target path | kv rows |
| PLATFORM | Detection result, relevant fields (docker, wsl, k8s) | kv rows |
| WIZARD / CONFIG | What was configured/changed, which file, diff if available | Target + diff block |
| PLAN | Files changed in `.agent/`, commit subject | File list |

All sources fall back gracefully: if a specific field is missing, skip it. If none of the source-specific fields are present, show the generic kv fallback.

### Fix direction

Replace `_tlRenderDetail(entry)` with a dispatch function:

```js
function _tlRenderDetail(entry) {
  switch (entry.source) {
    case 'GIT':      return _tlDetailGit(entry);
    case 'AUDIT':    return _tlDetailAudit(entry);
    case 'CHAT':     return _tlDetailChat(entry);
    case 'CI':
    case 'TESTS':    return _tlDetailRun(entry);
    case 'PKG':      return _tlDetailPkg(entry);
    case 'VAULT':    return _tlDetailVault(entry);
    case 'ENV':      return _tlDetailEnv(entry);
    case 'SECURITY': return _tlDetailSecurity(entry);
    case 'POSTURE':  return _tlDetailPosture(entry);
    // … etc.
    default:         return _tlDetailGeneric(entry);
  }
}
```

The audit log renderer in the Debugging tab (`_debugging.html` lines 427–529) is the direct reference implementation for the detail rendering patterns (before/after panels, diff block, file list with badges, action badge). The timeline renderers should follow the same visual language — same colors, same panel structure — so the two views feel like siblings, not strangers.

---

## Underlying Principle Violations (updated)

### 8. Source-specific representation (Information Architecture — content type determines form)
Gap 7 is a violation of the principle that **the form of information presentation must match the type of information**. A commit is not a key-value store. A message is not a key-value store. A build failure is not a key-value store. Rendering all of them as identical key-value lists destroys the cognitive affordance that each type carries. The user cannot recognize what they're looking at without reading the raw data — and even then, they have to parse it mentally rather than read it.

---

## Summary table

| # | Gap | Principle violated | Severity |
|---|-----|--------------------|----------|
| 1 | Locality is a filter, not a view mode | Mental model mismatch | High |
| 2 | Filter pills cause layout reflow and displace controls | Spatial consistency | High |
| 3 | Sort is in the middle instead of the trailing edge | Information hierarchy | Medium |
| 4 | Dead filter options shown with no count | Progressive disclosure / affordance | Medium |
| 5 | Chain navigator is a flat list, not a tree | Mental model mismatch / recognition over recall | High |
| 6 | Page provides no orientation on first load | Learnability / progressive disclosure | High |
| 7 | Entry detail is a source-blind key-value dump | Source-specific representation / affordance clarity | High |
