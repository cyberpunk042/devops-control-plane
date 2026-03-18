# Modules Posture V3 — UX Design: Admonitions, Confirmations, Completeness
> Status: DESIGN — 2026-03-17
> This document defines the exact content and interaction for every element
> of the remediation modal. Everything here must be built.

---

## 1. Admonition System

Reusable visual callouts that communicate severity and intent at a glance.
Used throughout the remediation modal and peek panels.

### Types

```
info     — 💡 blue   — educational, helpful context
tip      — 💚 green  — suggested action, best practice
warning  — ⚠️ amber  — something to be aware of, potential risk
danger   — 🔴 red    — security risk, data loss, breaking change
note     — 📝 purple — recorded decision, annotation
success  — ✅ green  — action completed, good state
```

### HTML structure

```html
<div class="adm adm-warning">
    <div class="adm-icon">⚠️</div>
    <div class="adm-content">
        <div class="adm-title">This gap means deployment risk</div>
        <div class="adm-body">If someone installs this module on Python 3.8,
        the click package will fail to import because click 8.3 requires 3.10+.</div>
    </div>
</div>
```

### CSS

```css
.adm { display: flex; gap: 0.6rem; padding: 0.65rem 0.75rem;
       border-radius: var(--radius-md); margin: 0.5rem 0;
       font-size: 0.82rem; line-height: 1.55; }
.adm-icon { flex-shrink: 0; font-size: 1rem; }
.adm-title { font-weight: 600; margin-bottom: 0.15rem; }
.adm-body { color: var(--text-secondary); }

.adm-info    { background: hsla(210,80%,55%,0.08); border: 1px solid hsla(210,80%,55%,0.2); }
.adm-tip     { background: hsla(150,60%,45%,0.08); border: 1px solid hsla(150,60%,45%,0.2); }
.adm-warning { background: hsla(38,92%,55%,0.08);  border: 1px solid hsla(38,92%,55%,0.2); }
.adm-danger  { background: hsla(0,75%,55%,0.08);   border: 1px solid hsla(0,75%,55%,0.2); }
.adm-note    { background: hsla(270,60%,55%,0.08);  border: 1px solid hsla(270,60%,55%,0.2); }
.adm-success { background: hsla(150,60%,45%,0.08);  border: 1px solid hsla(150,60%,45%,0.2); }
```

### JS helper

```javascript
function _adm(type, title, body) {
    const icons = { info:'💡', tip:'✅', warning:'⚠️', danger:'🔴', note:'📝', success:'✅' };
    return `<div class="adm adm-${type}">
        <div class="adm-icon">${icons[type] || '💡'}</div>
        <div class="adm-content">
            ${title ? `<div class="adm-title">${title}</div>` : ''}
            <div class="adm-body">${body}</div>
        </div>
    </div>`;
}
```

---

## 2. Where Admonitions Go

### In the Summary

The summary already has a colored left border. Add an admonition inside for critical situations:

**GAP:**
```
[rem-summary with warning border]
core declares Python ≥3.8 but needs ≥3.10...

[adm-warning] Deployment risk
If someone runs this module on Python 3.8 or 3.9, it will crash
at import time. The click package requires 3.10+.

[adm-info] Why this happens
The declared floor (≥3.8) comes from the python-lib stack baseline.
Your module's actual dependencies need more than what the stack promises.
```

**CVE:**
```
[rem-summary with danger border]
core's floor has known vulnerabilities...

[adm-danger] Security exposure
CVE-2024-6232 affects Python 3.8. Deployments on this version are
running unpatched software with a known vulnerability.
```

**EOL:**
```
[rem-summary with warning border]
adapters' floor reaches end-of-life...

[adm-warning] Upcoming deadline
Python 3.9 stops receiving security patches in October 2025.
After that date, new vulnerabilities won't be fixed.

[adm-info] What this means for you
Your module will continue to work. Nothing breaks at the EOL date.
But over time, deployments on 3.9 become increasingly risky.
```

**COULD LOWER:**
```
[rem-summary with info border]
core declares ≥3.8 but only needs ≥3.6...

[adm-tip] Opportunity
This module could support a wider range of Python versions.
Whether this matters depends on your audience.
```

### In the Understand section

Each question gets admonitions for key insights:

```
Why does this gap exist?
[explanation text]

[adm-info] How we detected this
We scanned 582 .py files in src/core/ for version-specific syntax.
We checked 5 installed packages for Requires-Python metadata.
The python-lib stack declares a baseline of Python ≥3.8.

Is this actually a problem?
[adm-tip] If you only deploy on 3.12+
The gap is cosmetic. Nothing breaks in your actual deployment.
You can acknowledge it with a note and move on.

[adm-warning] If this is a published library
Users on Python 3.8/3.9 will install it and get import errors.
The declared floor is misleading — you should fix it.
```

### In the Fix options

Each option gets:
1. An admonition explaining what it does
2. An admonition about consequences
3. An admonition about what happens next

```
Option A: Raise the declared floor to ≥3.10

[explanation + preview]

[adm-tip] What this does
Creates a pyproject.toml in src/core/ that declares requires-python = ">=3.10".
This makes the module honest about what it actually needs.

[adm-warning] Consequence
Anyone trying to install this module on Python 3.8 or 3.9 will get
an error from pip: "requires Python >=3.10 but Python 3.9 is installed."
If nobody deploys on 3.8/3.9, this has no practical impact.

[adm-info] What happens after
The posture table will update: Declared changes from ≥3.8 (stack) to ≥3.10 (module).
The gap status changes from ⚠️ to ✅. The floor source changes from "stack" to "module".

[Apply] [Preview]
```

```
Option B: Lower the effective floor (advanced)

[adm-danger] This is complex
Lowering the effective floor means downgrading dependencies or
rewriting code. Both carry risk. Only do this if you have a
strong reason to support Python 3.8.

[dep list + find alternatives buttons]

[adm-warning] Downgrade risks
Older package versions may have:
• Known security vulnerabilities (unpatched CVEs)
• Missing features your code depends on
• Incompatibilities with other packages
```

### In the Decide options

```
📝 Accept with a note

[adm-info] What this does
Your note is saved to project.yml in the module's version_note field.
It's version-controlled and visible to anyone reading the project config.
The warning remains visible in the posture table but shows your note
alongside it, so others know it's been reviewed.

[textarea]

[adm-note] After saving
The posture card will show 📝 next to the module. Anyone hovering
over it will see your explanation. The warning is NOT suppressed —
the data stays visible, but marked as acknowledged.

[Save]
```

```
📅 Defer until a date

[adm-info] What this does
The warning is suppressed until your chosen date. After that date,
it re-surfaces automatically. The deferral is recorded in
.state/module_decisions.json (not version-controlled).

[date + reason inputs]

[adm-warning] When the deferral expires
The platform will re-surface this warning with a note:
"Deferral expired — originally deferred on [date] because: [reason]"
You'll need to address it or defer again.

[Defer]
```

```
🎯 Set version strategy

Each strategy button gets a full explanation panel:

[Latest button]
[adm-info] Latest strategy
Track the current Python version. The platform will:
• Warn you when your floor falls behind the current release
• Treat the compatibility range as "how far behind are you"
• Recommend updating when new Python versions release
Best for: application modules that you control the deployment for.

[Compatibility button]
[adm-info] Compatibility strategy
Wide range is intentional. The platform will:
• NOT warn about being "behind" — wide range is the goal
• Only warn about EOL versions and CVEs at the floor
• Show compatibility breadth as a strength
Best for: libraries, SDKs, packages consumed by others.

[Auto button]
[adm-info] Auto-detect strategy
The platform deduces your strategy from the constraint gap:
• Gap ≤ 2 versions → treated as "latest"
• Gap ≥ 4 versions → treated as "compatibility"
• Gap = 3 → ambiguous, shown with ✱ marker
This is the default. Set explicitly to remove the ✱.
```

### In the Track options

```
📋 Create version upgrade plan

[adm-info] What this creates
A tracked plan with a target floor, target date, and checklist.
The platform will show your progress and remind you of the target date.

[target floor + date inputs]

Auto-generated checklist:
☐ Verify all dependencies support target floor
☐ Update requires-python in module config
☐ Update CI test matrix
☐ Run full test suite on target version
☐ Remove compatibility shims if any

[adm-tip] You can customize this
After creating the plan, you can add or remove checklist items,
update the target date, and mark items as done. The plan is
saved to .state/module_decisions.json.

[Create plan]
```

---

## 3. Confirmation Modals

Every action that modifies files must go through a confirmation modal
stacked on top (`replace: false`).

### Pattern

```javascript
function _remConfirm(title, body, onConfirm) {
    modalOpen({
        title: title,
        replace: false,
        body: body,
        size: 'md',
        footerButtons: [
            { label: 'Cancel', cls: 'btn-ghost', onclick: 'modalClose()' },
            { label: 'Confirm & Apply', cls: 'btn-primary',
              onclick: `modalClose(); (${onConfirm.toString()})()` },
        ],
    });
}
```

### For "Apply floor fix"

```
┌─ Confirm: Create pyproject.toml ──────────────────────────┐
│                                                            │
│  [adm-warning] This will create a new file                │
│  src/core/pyproject.toml will be created with:             │
│                                                            │
│  [rem-preview]                                             │
│  [project]                                                 │
│  name = "core"                                             │
│  requires-python = ">=3.10"                                │
│                                                            │
│  [adm-info] What changes after this                       │
│  • Declared floor: ≥3.8 (stack) → ≥3.10 (module)         │
│  • Status: ⚠️ gap → ✅ consistent                        │
│  • Floor source: stack → module                           │
│  • Anyone on Python 3.8/3.9 can no longer install         │
│                                                            │
│  [Cancel]  [Confirm & Apply]                              │
└────────────────────────────────────────────────────────────┘
```

### For "Save note"

```
┌─ Confirm: Save version note ──────────────────────────────┐
│                                                            │
│  [adm-info] This will modify project.yml                  │
│                                                            │
│  modules:                                                  │
│    - name: core                                            │
│      path: src/core                                        │
│  +   version_note: "We only deploy on 3.12+..."           │
│                                                            │
│  [adm-note] This is version-controlled                    │
│  The change will appear in your next git diff.             │
│  Anyone reading project.yml will see your note.            │
│                                                            │
│  [Cancel]  [Save to project.yml]                          │
└────────────────────────────────────────────────────────────┘
```

### For "Defer"

```
┌─ Confirm: Defer warning ──────────────────────────────────┐
│                                                            │
│  [adm-info] Deferring until Q3 2026                       │
│  This warning will be suppressed until the specified date. │
│                                                            │
│  [adm-warning] When the deferral expires                  │
│  The warning will re-surface with a note saying:           │
│  "Deferral expired — was deferred because: [reason]"      │
│  You'll need to address it or defer again.                 │
│                                                            │
│  [Cancel]  [Defer]                                        │
└────────────────────────────────────────────────────────────┘
```

### For "Set strategy"

```
┌─ Confirm: Set strategy to Compatibility ──────────────────┐
│                                                            │
│  [adm-info] What changes                                  │
│  The platform will evaluate this module differently:       │
│  • Wide compatibility range is treated as a strength       │
│  • No warnings for being "behind" current Python           │
│  • Only warns about EOL versions and CVEs at the floor    │
│                                                            │
│  This modifies project.yml:                                │
│    - name: core                                            │
│  +   version_strategy: compatibility                       │
│                                                            │
│  [Cancel]  [Set strategy]                                 │
└────────────────────────────────────────────────────────────┘
```

---

## 4. Missing Sections Identified

### "Do nothing" option in every Fix section

Every situation needs an explicit "Do nothing" card that explains
what happens if the user takes no action:

```
Option: Do nothing

[adm-info] What happens if you don't act
The gap will continue to show in the posture table. The module
will work fine in your current deployment (Python 3.12+).

If someone tries to install this module on Python 3.8, it will
fail — but if nobody does that, nothing breaks.

The warning will appear on every posture scan until you either
fix the gap or acknowledge it with a note.
```

### "How we detected this" transparency section

Inside Understand, after the analysis:

```
[adm-info] How this was analyzed
• Declared floor: from python-lib stack definition (tier 2 of 3-tier detection)
• Dependency floor: scanned imports in src/core/ → found 5 third-party packages
  → read Requires-Python from each package's dist-info metadata
  → highest constraint: click ≥3.10
• Code floor: scanned 582 .py files for version-specific syntax
  → 480 files have __future__ annotations (type hints don't count)
  → 7 files use runtime generics without __future__ (needs 3.9+)
  → 1 file uses walrus operator (needs 3.8+)
• Effective floor: max(declared=3.8, deps=3.10, code=3.9) = 3.10
```

### Cross-module impact in Fix section

When raising a floor:

```
[adm-info] Impact on other modules
This change only affects the core module. Other modules (adapters,
cli, web) have their own floors and are not affected.

If core exports public APIs used by other modules, those modules
may need to update their own floors to match. Currently detected
cross-module imports: [list or "none detected"].
```

### "What happens next" after every action

After applying any fix, the confirmation modal shows:

```
[adm-success] Applied successfully

What the platform will do now:
1. Rescan the module posture (takes ~2 seconds)
2. Update the table with the new declared floor
3. Recalculate the effective floor and verdict
4. Recalculate floor health against the new effective
5. Update the posture badge in the nav bar

You'll see the changes reflected in the table immediately.
```

---

## 5. Strategy Section Needs Full Expansion

The strategy buttons are too compact. Each needs its own full panel
with admonitions, not just buttons with a footnote.

```
🎯 Set version strategy

Choose how the platform evaluates this module's version health.
This is saved to project.yml and affects how warnings and
recommendations are generated.

[Option card: Latest]
  [adm-tip] Best for application modules
  Your module tracks the current Python version. The platform will warn
  you when your floor falls behind, recommend updates when new versions
  release, and treat narrow compatibility as normal.

  After setting:
  • compat.✱ badge → latest badge
  • No more "deduced" marker
  • Warnings shift from floor health to version currency

  [Set to Latest]

[Option card: Compatibility]
  [adm-tip] Best for libraries and shared packages
  Your module deliberately supports a wide range. The platform will
  treat breadth as a strength, not warn about being behind, and only
  alert you about EOL versions and CVEs at the floor.

  After setting:
  • compat.✱ badge → compat. badge
  • No more "deduced" marker
  • Warnings focus on floor health, not version gap

  [Set to Compatibility]

[Option card: Auto-detect]
  [adm-info] Let the platform decide
  The platform infers your strategy from the constraint gap:
  gap ≤ 2 → latest, gap ≥ 4 → compatibility, gap = 3 → ambiguous.
  The ✱ marker shows that the strategy is deduced, not explicit.

  [Set to Auto]
```

---

## 6. Implementation Plan

```
Step 1: Build admonition system (_adm helper + CSS)
Step 2: Rewrite _remSummary with admonitions
Step 3: Rewrite _remUnderstand with admonitions + "How we detected" section
Step 4: Rewrite _remFix with admonitions + consequences + "Do nothing" option
Step 5: Add confirmation modals for all destructive actions
Step 6: Rewrite _remDecide with full strategy panels + admonitions
Step 7: Rewrite _remTrack with admonitions
Step 8: Add "What happens next" to all action confirmations
Step 9: Add cross-module impact analysis to Fix section
```
