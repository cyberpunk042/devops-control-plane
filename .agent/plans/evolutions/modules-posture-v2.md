# Modules Posture V2 — Complete Experience
> Status: PLANNING — 2026-03-17
> What exists: raw data in a 9-column table with no context, no interaction, no guidance
> What this milestone delivers: a complete, interactive, explainable module health experience

---

## The Problem with V1

V1 dumps data on screen. Numbers with no explanation. Warnings with no guidance.
Icons with no context. The user sees ⚠️ and has no way to:
- Understand WHY it's flagged
- Verify if the data is correct
- Dismiss it with a reason
- Get guidance on what to do
- Drill deeper into any cell

It's a debug log pretending to be a feature.

---

## What V2 Must Be

Every piece of data in the table must be:

1. **Explainable** — hover on any cell and get a tooltip/panel that explains
   what this value means, where it came from, and why it matters

2. **Verifiable** — the user can see the evidence behind each value
   (which files, which imports, which packages, which features)

3. **Actionable** — when something is flagged, the user gets options:
   remediate, dismiss with a note, get more detail, or understand more

4. **Interactive** — clicking/hovering on cells opens contextual information,
   not just static text

---

## Cell-by-Cell Design

### Module Column
**Hover tooltip:**
```
Module: core
Path: src/core
Domain: library
Stack: python-lib (detected)
Files: 582 .py files
```

### Stack Column
**Hover tooltip:**
```
Stack: python-lib
Parent: python
Requires: python ≥ 3.8
Capabilities: install, lint, format, test, types
Detection: matched via pyproject.toml
```

### Declared Column
**Hover tooltip shows the 3-tier source:**
```
Declared floor: ≥3.8
Source: stack definition (tier 2)

Tier 1 (module config): no pyproject.toml in src/core/
Tier 2 (stack requires): python-lib inherits python ≥ 3.8 ← USED
Tier 3 (project root): requires-python = ">=3.11"

The stack's baseline requirement determines the declared floor
because this module doesn't have its own config file.
```

### Deps Column
**Hover tooltip shows which packages drive the floor:**
```
Dependency floor: ≥3.10

Highest constraint from:
  click 8.3.1        Requires-Python ≥3.10  ← drives floor
  pydantic 2.12.5    Requires-Python ≥3.9
  pyyaml 6.0.3       Requires-Python ≥3.8

12 packages scanned, 3 with Python constraints.
The highest minimum (click ≥3.10) determines the dep floor.
```
**Click action:** expand to show full package list with constraints

### Code Column
**Hover tooltip shows which features were detected:**
```
Code floor: 3.9

Highest feature detected:
  3.9  builtin generics (runtime list[X])
       in src/core/services/artifacts/builders/__init__.py:24
  3.8  walrus operator :=
       in src/core/services/k8s/helm_generate.py:369
  3.6  f-strings
       in src/core/services/peek.py:47

582 files scanned. 7 files use runtime generics without
__future__ annotations, requiring Python 3.9+.
480 files use __future__ annotations (type hints work on 3.7+).
```

### Effective Column
**Hover tooltip explains the calculation:**
```
Effective floor: ≥3.10

Calculated as highest of:
  Declared: 3.8  (from stack)
  Deps:     3.10 (from click 8.3.1)  ← highest
  Code:     3.9  (from runtime generics)

This module cannot run on anything below Python 3.10
regardless of what the stack declares, because click
requires 3.10+.
```

### Compat Column
**Hover tooltip explains the range:**
```
Compatibility: 4 versions
Range: 3.10 — 3.13

Supported versions:
  3.10  ✓ supported (EOL Oct 2026)
  3.11  ✓ supported (EOL Oct 2027)
  3.12  ✓ supported (EOL Oct 2028)
  3.13  ✓ current

All versions in range are actively maintained.
```

### Floor Column
**Hover tooltip explains the health:**
```
Floor health: 🟢 supported

The effective floor (3.10) is still receiving
security patches until October 2026.

No known CVEs for Python 3.10.
```

For 🔴:
```
Floor health: 🔴 CVE exposure

The effective floor (3.8) has known vulnerabilities:
  CVE-2024-6232 (EOL October 2024)

Python 3.8 no longer receives security patches.
Deployments on 3.8 are exposed.
```

### Status Column
**Hover tooltip explains the verdict:**
```
Status: ⚠️ Gap detected

Declared floor (3.8) is lower than what the module
actually needs:
  • Dependencies require ≥3.10 (click)
  • Code uses 3.9+ features (runtime generics)

The declared floor is inaccurate — this module
cannot actually run on Python 3.8.
```

**Click action: remediation panel**
```
┌─────────────────────────────────────────────────┐
│ ⚠️ Gap: core declares ≥3.8 but needs ≥3.10    │
│                                                  │
│ Options:                                         │
│                                                  │
│ [📝 Acknowledge]                                │
│   Add a note explaining why the declared floor   │
│   differs from the effective floor.              │
│   Opens: version_note editor for project.yml     │
│                                                  │
│ [🔧 Update Declaration]                         │
│   Update requires-python to ≥3.10 to match       │
│   what the module actually needs.                │
│   Shows: what would change in pyproject.toml     │
│                                                  │
│ [📋 View Full Report]                           │
│   See all dependencies, code features, and       │
│   version constraints in detail.                 │
│                                                  │
│ [✕ Dismiss]                                     │
│   Dismiss this warning for this module.          │
│   Adds version_note: "Reviewed — accepted gap"  │
│                                                  │
└─────────────────────────────────────────────────┘
```

---

## Below-Table Sections

### Status Section
Each verdict line is expandable:
```
⚠️ core: declared 3.8 but deps need 3.10
   └─ click 8.3.1 requires Python ≥3.10
   └─ Code uses runtime generics (3.9+) in 7 files
   └─ [📝 Acknowledge] [🔧 Fix] [📋 Details]
```

### Strategy Section
Each strategy badge is hoverable:
```
core: compat.✱
  ↳ Deduced as compatibility strategy (floor gap ≥ 4 from current)
  ↳ Set explicitly in project.yml: version_strategy: compatibility
  ↳ [Set to 'latest'] [Set to 'compatibility'] [Add note]
```

### Floor Advisories
Each advisory is expandable with remediation:
```
⚠️ adapters: Python 3.8 has known CVEs
   └─ CVE-2024-6232: security vulnerability in 3.8
   └─ Python 3.8 EOL: October 2024 (no more patches)
   └─ Effective floor is 3.9 (from pydantic) — above the CVE
   └─ The declared floor (3.8 from stack) includes the CVE range
   └─ [📝 Acknowledge] [🔧 Raise floor to ≥3.9]
```

---

## Data Accuracy Fixes Needed

### The "stack" source is misleading
The declared floor says `≥3.8 stack` for all modules because they all inherit
from the python parent stack. But:
- The PROJECT says `requires-python = ">=3.11"` in its pyproject.toml
- That's tier 3 — it should show when tier 2 (stack) is used
- The tooltip should explain: "Stack says 3.8, but project declares 3.11.
  The module inherits the stack baseline because it has no own config."

### Floor health evaluation needs to use EFFECTIVE floor
Currently some modules show 🔴 because the DECLARED floor (3.8) has CVEs.
But the EFFECTIVE floor (3.9 or 3.10) doesn't have CVEs.
The floor health emoji should evaluate the EFFECTIVE floor, not the declared.
The tooltip can explain: "Declared floor 3.8 has CVEs, but your effective
floor is 3.10 which is supported."

### Verdict "could_lower" needs better explanation
"declared 3.8 but nothing needs more than 3.6" is confusing when the
declared comes from a stack baseline. The verdict should say:
"Stack baseline is 3.8. Your code only uses 3.6 features and your deps
only need 3.6. The module is compatible below the stack baseline."

---

## Interaction Model

### Hover → Tooltip
Every cell in the table gets a rich CSS tooltip on hover.
Not a browser title attribute — a styled tooltip panel with:
- Explanation text
- Evidence (files, packages, versions)
- Context (where the value came from)

### Click → Action Panel
Cells that have actions (Status, Strategy badges) open a modal or
inline panel with options:
- Acknowledge / dismiss with note
- Fix the issue (update config)
- View full report
- Set strategy explicitly

### Inline Editing
- version_note: editable from the UI → writes to project.yml
- version_strategy: selectable from dropdown → writes to project.yml
- Dismiss: adds a version_note marking the issue as reviewed

---

## Technical Implementation

### Tooltip System
- CSS-based tooltips (not browser title)
- Position: below the cell, aligned left
- Max width: 400px
- Style: dark surface, border, monospace for technical values
- Delay: 300ms before showing (avoid flicker)
- Each tooltip content is computed from the item's structured data
  (already available in the JSON response)

### Action Panels
- Use existing modalOpen() for complex actions
- Inline expand for simple details (accordion style)
- API endpoints needed:
  - POST /api/modules/{name}/note — update version_note in project.yml
  - POST /api/modules/{name}/strategy — update version_strategy in project.yml
  - POST /api/modules/{name}/dismiss — add dismissal note

### Data Completeness
- deps_floor details: expose the per-package breakdown in the JSON
- code_floor details: expose the per-feature list in the JSON
- Both already computed in module_intel.py, just need to pass through
  enrichment to the frontend

---

## Implementation Order

```
1. Fix data accuracy (floor health uses effective, not declared)
2. Add rich tooltip system (CSS + JS)
3. Implement tooltips for all 9 columns
4. Add action panel for Status column
5. Add strategy interaction (set explicitly)
6. Add version_note editing
7. Add dismiss/acknowledge flow
8. Pass deps details + code features to frontend
9. Polish: styling, animations, responsive
```
