# Timeline Navigator v2 — Spec

> Scope: Left side-panel of the Timeline/History view.
> Three modes: Calendar, Domains, Chains.
> Each mode is a tree with real depth, not a flat list.
> Toggle principle on source filters: clicking an already-active source
> deactivates it (same as clicking X on the pill).

---

## Calendar mode — tree with year → month → day

### Current
Flat list of days grouped under month labels. Month labels are not clickable.
No year grouping. Clicking a day filters to that single day. No way to select
a whole month or year.

### Target
```
▼ 2026                              (154)
  ▼ March                           (47)
      14  ●                          (12)
      13  ●                          (8)
      12  ◑                          (3)
      …
  ▸ February                        (62)
  ▸ January                         (45)
▸ 2025                              (38)
```

- **Year row**: clickable → sets dateFrom/dateTo to span the full year.
  Count = sum of all entries in that year.
- **Month row**: clickable → sets dateFrom/dateTo to span the full month.
  Collapsible (▸/▼). Count = sum of all entries in that month.
- **Day row**: clickable → sets dateFrom/dateTo to that single day (existing).
  Status dot: ● (all ok) or ◑ (has failures).
- **Toggle**: clicking an already-selected year/month/day clears the date filter.

### Data needed
Current `calendar` array has `{date, count, has_failure}` per day.
Year and month counts/failure flags are derived client-side by summing days.
No backend change needed.

---

## Domains mode — tree with adapter → source → subtype

### Current
Flat list of 17 source enum values with total count — the same list as the
top filter dropdown. No depth. No insight into which adapters/features
produce the data. No subtypes visible.

### Target

The Domains tree shows the timeline's internal structure: the 6 source
adapters (features), each expanding to show the sources they produce,
each expanding to show subtypes as leaves. This gives 50+ nodes of depth
within the timeline domain alone.

```
▼ scan_activity                     (32)
  ▼ AUDIT                           (12)
      L0                             (3)
      L1                             (5)
      L2                             (2)
      run                            (2)
  ▸ PKG                              (5)
  ▸ PLATFORM                         (8)
  ▸ POSTURE                          (3)
  ▸ SECURITY                         (2)
  ▸ STACK                            (1)
  ▸ WIZARD                           (1)
▼ cli_ops                           (10)
  ▸ TOOLS                            (5)
  ▸ BACKUP                           (3)
  ▸ VAULT                            (2)
▼ git_log                           (47)
  ▼ GIT                              (40)
      commit                         (40)
  ▼ PLAN                             (4)
      commit                         (3)
      rules                          (1)
  ▸ CONFIG                           (3)
▸ ledger_runs                        (6)
▸ ledger_audits                      (4)
▸ chat                               (3)
```

- **Adapter row (level 0)**: collapsible. Count = total entries from this
  adapter. Not directly filterable (it's structural).
- **Source row (level 1)**: clickable → toggles source filter. If already
  in `_tlState.sources`, remove it (toggle off). Collapsible to show subtypes.
  Count = entries for this source from this adapter.
- **Subtype row (level 2, leaf)**: clickable → filters to source + subtype.
  Count = entries with this source and subtype.
- **Active state**: source rows that are in the active filter get highlighted.

### Data needed

The aggregate node needs to track which adapter produced each entry so the
tree can group by adapter → source → subtype.

Option A (minimal): Tag each entry with its adapter name during `_resolve_data`.
The adapters are already called per-source-node, so we know which adapter
produced which entries. Add an `adapter` field to the serialized entry dict
(or derive it from the source node path).

Option B (facet-based): Add a nested facet
`by_adapter: {scan_activity: {audit: {L0: 3, L1: 5}, pkg: {install: 2}}, ...}`
to `_build_facets()`.

Either way, the tree needs three levels of counts:
`adapter → source → subtype`.

---

## Chains mode — linked causal tree

### Current
Flat chain summaries. Members listed chronologically when expanded.
No parent-child visual. `chain_parent_ref` exists in member data but
is not used in rendering.

### Target
```
▼ 📎 op-20260314-audit-L2           (4)
    ○ AUDIT:L2 scan started          08:51  [ORIGIN]
      ├─ ○ AUDIT committed            10:30  [STEP]
      └─ ● AUDIT:L2 result            10:31  [TERMINAL]

▼ 📎 abc123 — fix: bugs             (2)
    ○ GIT commit                     10:33  [ORIGIN]
      └─ ○ CI pipeline-run           10:35  [STEP]
```

- **Chain header**: clickable → toggles chain filter.
  Shows summary from ORIGIN entry + entry count.
- **Members**: rendered as a tree using `chain_parent_ref`.
  - Entry with `chain_role == ORIGIN` or no `chain_parent_ref` → root.
  - Entry with `chain_parent_ref` → child of the entry whose `ref` matches.
  - Indentation + connector lines (├─ / └─) show the hierarchy.
- **Status per member**: colored dot (● ok, ◑ warning, ✕ failed).
- **Clicking a member**: scrolls to / highlights that entry in the right panel.

### Note
The chain system may need deeper work. The current adapters set `chain_id`
and `chain_parent_ref` in some cases but the linking may not be fully
implemented across all adapters. This spec covers the rendering side —
if the data linkage is incomplete, that's a separate issue to address
in the adapter layer.

### Data needed
`chain_parent_ref` is already in the member data from `_build_chains()`.
No backend change needed for rendering — just use it.

---

## Toggle principle — on source filters

When clicking a source from the Domains side panel:
- If that source is NOT in `_tlState.sources`: add it (activate).
- If that source IS already in `_tlState.sources`: remove it (deactivate).
- Same behavior as clicking the X on the filter pill.

### Affected function
- `_tlFilterBySource(src)` — currently only adds. Change to toggle.

---

## Execution order

### Step 1 — Backend: adapter-level facets
Track which adapter produced each entry. Add `by_adapter` nested facet to
`_build_facets()` with shape:
`{adapter_name: {source_value: {subtype_value: count}}}`.

### Step 2 — Domains tree rendering
Replace `_tlNavRenderDomains()` with 3-level expandable tree:
adapter → source → subtype. Counts from `by_adapter` facet.
Source rows toggle source filter. Active state highlighted.

### Step 3 — Calendar tree rendering
Replace `_tlNavRenderCalendar()` with year → month → day tree.
Month/year rows clickable with date range filters. Collapsible.

### Step 4 — Toggle on source filter
Update `_tlFilterBySource(src)` to toggle: add if absent, remove if present.

### Step 5 — Chain tree rendering
Replace flat member list in `_tlNavRenderChains()` with parent-child
tree built from `chain_parent_ref`. Indentation + connectors.
(Scope: rendering only. Adapter-level chain linking is a separate task.)

### Step 6 — URL state
Ensure new selections (month, year, adapter, subtype) are reflected in URL hash.
