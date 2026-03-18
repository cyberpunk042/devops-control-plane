# Modules Posture V3 — Remediation & Deep Intelligence
> Status: ENVISIONING — 2026-03-17
> Builds on: V2 (interactive peek panels with conversational tooltips)
> This is the complete vision. Everything here is in scope.

---

## What V2 Achieved

V2 gave us the 9-column matrix table with per-module differentiated data,
clickable peek panels with conversational explanations, and basic action
buttons (acknowledge, full report). The data is real — declared floor from
3-tier detection, dependency floor from import analysis, code floor from
static analysis, effective floor, consistency verdict.

## What V3 Must Be

V2 tells you WHAT's happening. V3 tells you what to DO about it, helps you
INVESTIGATE deeper, lets you DECIDE and TRACK decisions, and ACTS on your
behalf when you choose.

Every finding becomes a workflow, not just a data point.

---

## The Remediation Model

Every situation the module posture detects has a remediation tree.
Not one action — a tree of options, each with its own depth.

```
SITUATION DETECTED
  │
  ├── 🔍 Understand (investigate deeper)
  │     ├── Why is this the case?
  │     ├── What exactly causes it?
  │     ├── What would happen if we don't act?
  │     └── Show me the evidence (files, packages, versions)
  │
  ├── 🔧 Fix (change something)
  │     ├── Quick fix (platform does it for you)
  │     ├── Guided fix (platform shows you what to change)
  │     ├── Manual fix (platform explains how, you do it)
  │     └── Alternative approaches (different ways to solve it)
  │
  ├── 📝 Decide (record a decision)
  │     ├── Accept with reason (acknowledge + note)
  │     ├── Defer with timeline ("review in Q3")
  │     ├── Set strategy explicitly
  │     └── Dismiss permanently
  │
  └── 📋 Track (plan for the future)
        ├── Add to version plan
        ├── Set a review date
        ├── Watch for changes (dep updates, EOL dates)
        └── Link to external tracking (issue, ticket)
```

---

## Situation 1: GAP (declared < effective)

The module claims wider compatibility than it actually has.
Example: declares ≥3.8 but deps need 3.10 and code uses 3.9 features.

### 🔍 Understand

**"Why does this gap exist?"**

Panel shows the full chain:
```
Your declared floor is 3.8 (from the python-lib stack baseline).
But your module can't actually run on 3.8 because:

  Dependencies:
  • click 8.3.1 requires Python ≥3.10
  • pydantic 2.12 requires Python ≥3.9
  → Highest dep constraint: 3.10

  Code features:
  • runtime list[] generics in builders/__init__.py:24
  → This syntax requires Python 3.9+
  • walrus operator := in helm_generate.py:369
  → This syntax requires Python 3.8+

  Effective floor: 3.10 (driven by click)

If someone installs this module on Python 3.8 or 3.9,
click will fail to import.
```

**"Is this actually a problem?"**

Context-aware guidance:
```
This depends on where you deploy:

• If you only deploy on Python 3.12+ → this gap is cosmetic.
  The declared floor is technically wrong but nothing breaks.

• If you publish this as a library → the gap is a real bug.
  Users on 3.8/3.9 will install it and it will break.

• If you have CI testing on 3.8 → your CI is testing a
  configuration that can't actually work.
```

**"What would happen if I don't fix it?"**

```
Nothing breaks in your current setup. The gap means the
declared compatibility is broader than reality, which could
mislead someone who tries to use this module on an older
Python. The risk depends on your deployment targets.
```

### 🔧 Fix

**Option A: Raise the declared floor (recommended)**
```
Add requires-python to this module's config to match reality.

What the platform will do:
  Create src/core/pyproject.toml with:
    [project]
    requires-python = ">=3.10"

This makes the module honest about its requirements.
The gap disappears because declared matches effective.

[Preview changes] [Apply]
```

**Option B: Update the project root config**
```
Your project root already declares requires-python = ">=3.11",
which is stricter than what's needed. But the module uses the
stack baseline (3.8) because it doesn't have its own config.

Adding a module-level config (Option A) is cleaner than
changing the project root, because different modules might
have different requirements.
```

**Option C: Lower the effective floor (advanced)**
```
To actually support Python 3.8, you would need to:

Dependencies:
  • Pin click to ≤8.0 (last version supporting 3.7)
    ⚠️ This is 2 major versions behind — missing features and fixes
  • Pin pydantic to ≤1.x (last version supporting 3.7)
    ⚠️ This is a major API rewrite — significant code changes needed

Code:
  • Replace list[] with List[] from typing (7 files)
  • Replace walrus := with if/else (1 file)
  • Both changes are backwards-compatible

Verdict: lowering the floor is expensive for this module.
The dependency cost is high (old click + pydantic 1.x rewrite).
Raising the declared floor is much simpler.

[Show affected files] [Show dep version history]
```

**Option D: Split the difference**
```
You could target Python 3.9 instead of 3.8 or 3.10:
  • 3.9 satisfies pydantic (≥3.9) and your code (3.9 features)
  • But not click (≥3.10)

To make 3.9 work, you'd only need to pin click to 8.1.x
(last version supporting 3.9). This is a minor pin, not a
major downgrade.

[Show what changes with click 8.1.x]
```

### 📝 Decide

**Accept with reason:**
```
Record why this gap is acceptable.

[textarea: "We only deploy on 3.12+, gap doesn't affect us"]

This note will:
  • Show on the module's posture card
  • Suppress the warning (but keep the data visible)
  • Be tracked in project.yml (version-controlled)

[Save note]
```

**Defer with timeline:**
```
Plan to address this later.

When should this be reviewed? [date picker / text: "Q3 2026"]
Reason: [textarea: "Waiting for vendor SDK 3.10 support"]

The platform will:
  • Record the deferral date
  • Re-surface the warning after the date
  • Show "deferred until Q3" on the posture card

[Save deferral]
```

**Set strategy explicitly:**
```
Tell the platform how to evaluate this module.

[dropdown: Latest / Compatibility / Let platform decide]

Latest: "I track the current Python version. Warn me when
  I fall behind."

Compatibility: "I deliberately support a wide range. Don't
  treat a low floor as a problem — only warn about EOL/CVEs
  at the floor."

[Save strategy]
```

### 📋 Track

**Version plan:**
```
Create a plan for upgrading this module's Python floor.

Target floor: [3.10 / 3.11 / 3.12]
Target date: [text]
Blocking items:
  • [ ] Verify click 8.3+ works on target
  • [ ] Update CI matrix
  • [ ] Update deployment configs
  • [ ] Test all module functionality

[Create plan]
```

---

## Situation 2: FLOOR EOL APPROACHING

Python 3.9 EOL October 2025. The effective floor is 3.9.

### 🔍 Understand

**"What does EOL mean for this module?"**
```
Python 3.9 reaches end-of-life in October 2025.

After that date:
  • No more security patches from python.org
  • New CVEs discovered won't be fixed for 3.9
  • Package maintainers may drop 3.9 support in new releases
  • Your module will still WORK — nothing stops running on 3.9
  • But deployments on 3.9 become increasingly risky over time

Timeline:
  Today ────────── EOL Oct 2025 ──────── Risk increases ──►
  ✅ Patches       ⚠️ No patches         🔴 Unpatched CVEs
```

**"Which of my modules are affected?"**
```
Modules with effective floor = 3.9:
  • adapters (effective ≥3.9, driven by pydantic)
  • web (effective ≥3.9, driven by flask)

Modules NOT affected:
  • core (effective ≥3.10)
  • cli (effective ≥3.10)
```

**"When will my dependencies drop 3.9?"**
```
When package maintainers release new versions that require
3.10+, your deps floor will naturally rise and 3.9 will
fall out of your effective range.

This is already happening:
  • click 8.3+ already requires ≥3.10
  • pydantic is likely to drop 3.9 in a future release
  • flask typically follows Python's EOL schedule

You may not need to do anything — the ecosystem will
move you forward naturally.
```

### 🔧 Fix

**Option A: Raise the floor preemptively**
```
Move your effective floor to 3.10 now, before 3.9 EOL.

For adapters: pydantic drives the 3.9 floor.
  → If you update pydantic to a version requiring 3.10+,
    the floor rises automatically.
  → Or add requires-python = ">=3.10" to the module config.

For web: flask drives the 3.9 floor.
  → Flask 3.1 still supports 3.9.
  → Flask 4.0 (when released) will likely require 3.10+.
  → Or add requires-python = ">=3.10" to the module config.

[Preview: what changes if we set floor to 3.10]
```

**Option B: Wait for the ecosystem**
```
Your dependencies will naturally raise their floors as 3.9
approaches and passes EOL. You can wait for:
  • Next pydantic release (likely drops 3.9 in 2025)
  • Next flask release (follows Python EOL schedule)

This is a valid approach if you're not deploying on 3.9
and don't need to make changes right now.
```

**Option C: Test on newer versions**
```
Verify your module works on Python 3.10+ before raising
the floor. The platform can help:

  • Run tests on 3.10, 3.11, 3.12 → show results
  • Check if all deps have compatible versions
  • Verify no code relies on 3.9-specific behavior

[Run compatibility check]
```

### 📝 Decide

Same options as Gap: accept, defer, set strategy.

### 📋 Track

**Watch for EOL:**
```
The platform tracks Python version lifecycle automatically.
When 3.9 reaches EOL, the floor health changes from 🟡 to 🟡/🔴.

You can set a reminder:
  • [Remind me 3 months before EOL (July 2025)]
  • [Remind me at EOL (October 2025)]
  • [Remind me when pydantic drops 3.9 support]
```

---

## Situation 3: CVEs ON THE FLOOR

Python 3.8 has CVE-2024-6232. The declared floor includes 3.8.

### 🔍 Understand

**"Am I actually at risk?"**

Context-aware analysis:
```
Your DECLARED floor is 3.8 (from the stack baseline).
Your EFFECTIVE floor is 3.10 (from click dependency).

Since click requires Python 3.10+, nobody can actually
install this module on 3.8 — pip would refuse because
click wouldn't install.

Risk assessment:
  Theoretical risk: yes (declared says 3.8 is supported)
  Practical risk: NO (effective floor prevents 3.8 deployment)

The CVE exists on a version you can't actually deploy on.
The floor health indicator shows the effective floor's health,
not the declared floor's.
```

If effective = declared and has CVEs:
```
⚠️ REAL RISK: Your effective floor IS 3.8, which has
known vulnerabilities.

CVE-2024-6232: [description of the vulnerability]
  Severity: [high/medium/low]
  Affected: Python 3.8.x (all patch versions)
  Fixed in: Python 3.9+

Deployments running Python 3.8 are exposed to this
vulnerability. There is no patch for 3.8 — the only
fix is upgrading to 3.9+.

[View CVE details] [Show affected deployments]
```

### 🔧 Fix

**Raise the floor above the vulnerable version:**
```
The only way to eliminate this CVE is to ensure your
module requires Python 3.9+.

What needs to change:
  • Add requires-python = ">=3.9" to module config
  • Verify all deps support 3.9+ (they do — see deps analysis)
  • Verify code doesn't use 3.8-only patterns (unlikely)

[Preview changes] [Apply]
```

### 📝 Decide + 📋 Track

Same patterns as above, but with urgency indicators for CVEs.

---

## Situation 4: COULD LOWER (wider compatibility possible)

The module declares ≥3.8 but only needs ≥3.6.

### 🔍 Understand

**"What would wider compatibility give me?"**
```
Your module currently declares support for Python 3.8+.
But your code only uses f-strings (3.6+) and your deps
don't have constraints.

If you lowered the floor to 3.6:
  • 2 more Python versions supported (3.6, 3.7)
  • Both are past EOL — limited practical value
  • But it signals that your code is simple and portable

If you lowered to 3.7:
  • 1 more version supported (3.7)
  • Also past EOL

Recommendation: the current floor (3.8 from stack) is
reasonable. Lowering it would only add EOL versions.
Unless you have users on 3.6/3.7, this isn't actionable.
```

**For libraries (domain: library):**
```
As a library, wider compatibility means more potential users.
However, Python 3.6 and 3.7 are both past EOL with declining
usage. The practical benefit is small.

PyPI download stats show <2% of downloads come from 3.7-.
```

### 🔧 Fix

**Lower the floor (if desired):**
```
To support Python 3.6+:
  • Create module config with requires-python = ">=3.6"
  • Add 3.6 and 3.7 to CI test matrix
  • Ensure no deps are pulled that need 3.7+

To support Python 3.7+:
  • Create module config with requires-python = ">=3.7"
  • 3.7 is past EOL but still commonly installed

[Preview] [Apply]
```

**Accept current floor:**
```
The stack baseline (3.8) is a reasonable floor for this module.
No action needed.

[Acknowledge: "stack baseline is appropriate"]
```

---

## UI Architecture for Remediation

### The Remediation Panel

When the user clicks on a status icon (⚠️, 🟡, 🔴, ℹ️) or clicks
"What can I do?" in any peek panel, a remediation modal opens.

```
┌─────────────────────────────────────────────────────────────┐
│ ⚠️ core — Compatibility Gap                          [X]   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Your module declares Python ≥3.8 support, but actually    │
│  needs ≥3.10 to run.                                       │
│                                                             │
│  ┌─ 🔍 Understand ────────────────────────────────────────┐ │
│  │ Why does this gap exist?                                │ │
│  │ Is this actually a problem?                             │ │
│  │ What happens if I don't fix it?                         │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                             │
│  ┌─ 🔧 Fix ───────────────────────────────────────────────┐ │
│  │ A. Raise the declared floor to ≥3.10 (recommended)     │ │
│  │ B. Update project root config                           │ │
│  │ C. Lower the effective floor (advanced)                 │ │
│  │ D. Split the difference — target 3.9                   │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                             │
│  ┌─ 📝 Decide ────────────────────────────────────────────┐ │
│  │ Accept with reason                                      │ │
│  │ Defer until [date]                                      │ │
│  │ Set version strategy explicitly                         │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                             │
│  ┌─ 📋 Track ─────────────────────────────────────────────┐ │
│  │ Create version upgrade plan                             │ │
│  │ Set review reminder                                     │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│                                              [Close]        │
└─────────────────────────────────────────────────────────────┘
```

Each section is expandable. Clicking an option expands it inline
with the full explanation and action controls.

### Expanded Option Example

```
┌─ 🔧 Fix ───────────────────────────────────────────────────┐
│                                                             │
│  ▸ A. Raise the declared floor to ≥3.10 (recommended)     │
│                                                             │
│  ▾ B. Update project root config                           │
│    ┌─────────────────────────────────────────────────────┐  │
│    │ Your project root declares requires-python = ≥3.11. │  │
│    │ This is stricter than what's needed, but the module  │  │
│    │ uses the stack baseline (3.8) because it doesn't     │  │
│    │ have its own config.                                 │  │
│    │                                                       │  │
│    │ Adding a module-level config (Option A) is cleaner   │  │
│    │ because different modules might have different        │  │
│    │ requirements.                                        │  │
│    │                                                       │  │
│    │ [Go to Option A instead]                             │  │
│    └─────────────────────────────────────────────────────┘  │
│                                                             │
│  ▸ C. Lower the effective floor (advanced)                 │
│  ▸ D. Split the difference — target 3.9                   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Actions That Modify Files

When the user chooses an action that changes files (like "raise the
declared floor"), the platform shows a preview:

```
┌─ Preview changes ──────────────────────────────────────────┐
│                                                             │
│  This will create a new file:                               │
│                                                             │
│  📄 src/core/pyproject.toml (NEW)                          │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ [project]                                           │    │
│  │ name = "core"                                       │    │
│  │ requires-python = ">=3.10"                          │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
│  After applying:                                            │
│  • Declared floor changes: ≥3.8 (stack) → ≥3.10 (module)  │
│  • Gap status changes: ⚠️ → ✅                            │
│  • Floor source changes: stack → module                    │
│                                                             │
│  [Apply changes] [Cancel]                                   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Actions That Write to project.yml

When the user sets a strategy or writes a note:

```
┌─ Save to project.yml ─────────────────────────────────────┐
│                                                             │
│  This will update project.yml:                              │
│                                                             │
│  modules:                                                   │
│    - name: core                                             │
│      path: src/core                                         │
│  +   version_strategy: compatibility                        │
│  +   version_note: "We only deploy on 3.12+, gap is OK"   │
│                                                             │
│  [Apply] [Cancel]                                           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Data & API Needs

### New API Endpoints

```
POST /api/posture/module-remediate
  Body: {
    module: "core",
    action: "raise_floor",
    target_floor: "3.10"
  }
  → Creates pyproject.toml, returns diff preview or applies

POST /api/posture/module-note
  Body: {
    module: "core",
    version_note: "...",
    version_strategy: "compatibility"
  }
  → Already exists (V2)

POST /api/posture/module-defer
  Body: {
    module: "core",
    defer_until: "2026-09-01",
    reason: "Waiting for vendor SDK"
  }
  → Saves deferral to project.yml, suppresses warning until date

GET /api/posture/module-impact?module=core&target_floor=3.10
  → Returns: what changes if we raise the floor
    - Which deps would need updating
    - Which code changes needed
    - Which CI configs affected
    - Blast radius analysis
```

### New Data on Module Items

```
For remediation panels to work, each module item needs:

  remediation_options: [
    {
      id: "raise_floor",
      label: "Raise declared floor to ≥3.10",
      type: "fix",
      recommended: true,
      description: "Makes the module honest about its requirements",
      preview_available: true,
    },
    {
      id: "accept_gap",
      label: "Accept with reason",
      type: "decide",
      description: "Record why this gap is acceptable",
    },
    ...
  ]

  dep_alternatives: {
    // For "lower effective" option — what older dep versions exist
    "click": {
      current: "8.3.1",
      last_supporting_38: "8.0.4",
      cost: "2 major versions behind, missing features X Y Z"
    }
  }

  deployment_context: {
    // Inferred from project config, CI, env settings
    deploy_targets: ["3.12"],  // from CI matrix or env
    is_library: false,         // from domain
    has_ci_matrix: true,
  }
```

### Persistence for Decisions

Deferrals and version plans need persistence beyond project.yml:

```
.state/module_decisions.json
{
  "core": {
    "deferred_until": "2026-09-01",
    "deferred_reason": "Waiting for vendor SDK",
    "deferred_at": "2026-03-17",
    "version_plan": {
      "target_floor": "3.12",
      "target_date": "2026-09",
      "checklist": [
        {"label": "Verify click 8.3+ on 3.12", "done": false},
        {"label": "Update CI matrix", "done": false}
      ]
    }
  }
}
```

---

## Existing Infrastructure to Leverage

### File operations
- project.yml reader/writer (exists in loader.py + new module-note endpoint)
- Need: pyproject.toml generator for individual modules

### Dependency intelligence
- dependency_mgr already knows package versions, alternatives
- subdeps.py can check what older versions of a dep require
- graph.py does impact analysis for upgrades

### Event tracking
- Event store can log remediation actions
- Timeline projection shows the history

### Modal system
- modalOpen with replace:false for stacking
- modalFormField for inputs
- modalSteps for multi-step flows
- modalPreview for showing diffs

---

## Implementation Phases

### Phase 1: Remediation Modal Framework
Build the expandable option panel UI pattern.
Wire to existing peek panels (⚠️ click → remediation modal).
Populate with static content for all 4 situations.

### Phase 2: File Operations
Create pyproject.toml generator for modules.
Preview diffs before applying.
Apply changes and re-scan posture.

### Phase 3: Decision Persistence
Deferral system (defer until date, re-surface after).
Version plan creation and tracking.
Integration with project.yml for notes/strategy.

### Phase 4: Deep Investigation
"Lower the effective floor" option with dep version analysis.
"What would break" impact analysis.
Code feature replacement suggestions.
Blast radius analysis for floor changes.

### Phase 5: Tracking & Reminders
Watch for dependency version changes.
EOL countdown and reminders.
Version plan progress tracking.
Link to external issue trackers.
