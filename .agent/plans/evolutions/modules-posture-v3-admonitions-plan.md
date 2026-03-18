# Modules Posture V3 — Admonitions & Completeness Execution Plan
> Status: READY TO EXECUTE — 2026-03-17
> Scope: Admonition system + confirmation modals + content completeness
> Files to modify: _system_posture.html, admin.css

---

## Audit Summary

### Current state (from completeness audit)

| Metric | Count |
|--------|-------|
| Functions using admonitions | 0 / 12 |
| API calls without confirmation modal | 6 |
| Buttons triggering mutations directly | 7 |
| Situations with "do nothing" option | 2 / 4 |
| Functions with full consequence explanation | 4 / 12 |
| Functions with "how we detected this" | 0 |
| Content sections with visual hierarchy | 3 / 7 |

### What needs to change

Every content function (_remSummary, _remUnderstand, _remFix, _remDecide,
_remTrack) needs rewriting with admonitions and completeness.

Every mutation handler (moduleApplyFloorFix, moduleSaveNote, moduleSaveDefer,
moduleSaveStrategy, moduleCreatePlan) needs a confirmation modal before acting.

---

## Design System: Admonitions

### Types matched to CSS variables

| Type | Icon | Border color | Background | Use for |
|------|------|-------------|------------|---------|
| info | 💡 | var(--accent) hsl(210,100%,62%) | hsla(210,100%,62%,0.06) | Educational context, how things work |
| tip | 🟢 | var(--success) hsl(145,65%,50%) | hsla(145,65%,50%,0.06) | Recommended action, best practice |
| warning | ⚠️ | var(--warning) hsl(38,92%,55%) | hsla(38,92%,55%,0.06) | Risk, something to watch |
| danger | 🔴 | var(--error) hsl(0,72%,58%) | hsla(0,72%,58%,0.06) | Security risk, breaking change |
| note | 📝 | hsl(270,60%,55%) | hsla(270,60%,55%,0.06) | Recorded decision, annotation |
| success | ✅ | var(--success) | hsla(145,65%,50%,0.06) | Completed action, good state |

### Follows existing patterns
- Border-left style (like `rem-summary`)
- Icon + content layout (like `card-setup-banner`)
- Background opacity ~6-8% (like `alert-bar`)
- Padding: var(--space-md)
- Radius: var(--radius-md)
- Font size: 0.82rem

---

## Step 1: Build admonition CSS + JS helper

### CSS additions to admin.css

```css
/* ── Admonitions ─────────────────────────────────────────────── */

.adm                    { display: flex; gap: 0.6rem; padding: 0.6rem 0.75rem;
                          border-radius: var(--radius-md); margin: 0.5rem 0;
                          font-size: 0.82rem; line-height: 1.55;
                          border-left: 3px solid var(--border); }
.adm-icon               { flex-shrink: 0; font-size: 1rem; padding-top: 0.1rem; }
.adm-content            { flex: 1; min-width: 0; }
.adm-title              { font-weight: 600; margin-bottom: 0.2rem;
                          color: var(--text-primary); }
.adm-body               { color: var(--text-secondary); }
.adm-body code           { font-size: 0.76rem; padding: 0.05rem 0.25rem;
                          background: var(--bg-inset); border-radius: 3px; }
.adm-body strong         { color: var(--text-primary); }

.adm-info               { background: hsla(210,100%,62%,0.06);
                          border-left-color: var(--accent); }
.adm-info .adm-title    { color: var(--accent); }

.adm-tip                { background: hsla(145,65%,50%,0.06);
                          border-left-color: var(--success); }
.adm-tip .adm-title     { color: var(--success); }

.adm-warning            { background: hsla(38,92%,55%,0.06);
                          border-left-color: var(--warning); }
.adm-warning .adm-title { color: var(--warning); }

.adm-danger             { background: hsla(0,72%,58%,0.06);
                          border-left-color: var(--error); }
.adm-danger .adm-title  { color: var(--error); }

.adm-note               { background: hsla(270,60%,55%,0.06);
                          border-left-color: hsl(270,60%,55%); }
.adm-note .adm-title    { color: hsl(270,60%,55%); }

.adm-success            { background: hsla(145,65%,50%,0.06);
                          border-left-color: var(--success); }
.adm-success .adm-title { color: var(--success); }
```

### JS helper in _system_posture.html

```javascript
function _adm(type, title, body) {
    const icons = {
        info: '💡', tip: '🟢', warning: '⚠️',
        danger: '🔴', note: '📝', success: '✅'
    };
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

## Step 2: Build confirmation modal helper

### JS helper

```javascript
function _remConfirm(opts) {
    // opts: { title, body, confirmLabel, confirmCls, onConfirm }
    const confirmId = 'rem-confirm-' + Date.now();
    modalOpen({
        title: opts.title,
        replace: false,
        body: opts.body,
        size: 'md',
        footerButtons: [
            { label: 'Cancel', cls: 'btn-ghost', onclick: 'modalClose()' },
            { label: opts.confirmLabel || 'Confirm',
              cls: opts.confirmCls || 'btn-primary',
              id: confirmId,
              onclick: `modalClose(); (${opts.onConfirm})()` },
        ],
    });
}
```

All 6 mutation handlers use this before calling the API.

---

## Step 3: Rewrite _remSummary with admonitions

### Per-situation content

**GAP:**
```javascript
// Current: plain paragraph
// New: summary paragraph + 2 admonitions

h += `<strong>${n}</strong> declares Python ${declared}+ but needs <strong>${effClean}+</strong>.`;
h += _adm('warning', 'Deployment risk',
    `If someone runs this module on Python ${declared}, it will crash at import time.
     <code>${topDep.package}</code> requires ≥${topDep.floor}.`);
h += _adm('info', 'Why this happens',
    `The declared floor (<code>${declared}</code>) comes from the
     ${source === 'stack' ? item.stack + ' stack baseline' : source + ' config'}.
     Your module's actual dependencies and code need more than what's declared.`);
```

**CVE:**
```javascript
h += _adm('danger', 'Security exposure',
    `<code>${cves.join('</code>, <code>')}</code> affect Python ${effClean}.
     Deployments on this version are running unpatched software.`);
h += _adm('info', 'What this means',
    `The vulnerability exists in the Python interpreter itself.
     The only fix is ensuring your module runs on a patched version.`);
```

**EOL:**
```javascript
h += _adm('warning', 'Approaching deadline',
    `Python ${effClean} stops receiving security patches in <strong>${eol}</strong>.
     After that date, new vulnerabilities won't be fixed.`);
h += _adm('tip', 'Good news',
    `Your module will continue to work. Nothing breaks at the EOL date.
     The risk increases gradually as unpatched vulnerabilities accumulate.`);
```

**COULD LOWER:**
```javascript
h += _adm('tip', 'Opportunity',
    `This module could support Python ${effClean}+ (currently declares ${declared}+).
     ${meta.domain === 'library'
       ? 'As a library, wider compatibility means more users can use your module.'
       : 'As an application, this is informational — you control the deployment.'}`);
```

**OK:**
```javascript
h += _adm('success', 'All clear',
    `All compatibility layers are aligned. The declared floor matches what your
     code and dependencies actually need, and the version is still maintained.`);
```

---

## Step 4: Rewrite _remUnderstand with admonitions + detection transparency

### Add "How we detected this" to every situation

```javascript
// At the end of _remUnderstand, for all situations:
const meta = item.module_meta || {};
const tiers = item.floor_tiers || {};
const deps = item.deps_details || [];
const features = item.code_features || [];

h += _adm('info', 'How this was analyzed', `
    <strong>Declared floor:</strong> from ${
        tiers.used === 'stack' ? item.stack + ' stack definition (tier 2)'
        : tiers.used === 'module' ? 'module config (tier 1)'
        : tiers.used === 'project' ? 'project root config (tier 3)'
        : 'unknown source'
    }<br>
    <strong>Dependency floor:</strong> scanned imports in <code>${meta.path || '?'}</code>
    → found ${deps.length} package(s) with Python constraints<br>
    <strong>Code floor:</strong> scanned .py files for version-specific syntax
    → ${features.length} feature(s) detected<br>
    <strong>Effective floor:</strong> highest of all three = ${effClean}
`);
```

### Add "Is this actually a problem?" with situation-aware admonitions

**For GAP:**
```javascript
h += _adm('tip', 'If you only deploy on Python 3.12+',
    `The gap is cosmetic. Nothing breaks in your actual deployment.
     You can acknowledge it with a note and move on.`);

h += _adm('warning', 'If this is a published library',
    `Users on Python ${declared} will install it and get import errors.
     The declared floor is misleading and should be fixed.`);

h += _adm('warning', 'If your CI tests on Python ' + declared,
    `Your CI is testing a configuration that can't work.
     The test environment doesn't match what the module actually needs.`);
```

---

## Step 5: Rewrite _remFix with consequences + "do nothing" + admonitions

### Every option gets 3 admonitions:

1. **What this does** (info/tip)
2. **Consequences** (warning/danger)
3. **What happens after** (info)

### Option A: Raise floor — add confirmation flow

Current: button calls `moduleApplyFloorFix()` directly.
New: button calls `_remConfirmRaiseFloor(moduleName, targetFloor)`.

```javascript
function _remConfirmRaiseFloor(n, floor) {
    const item = _modulePeekItems.find(i => i._moduleName === n);
    const meta = item ? item.module_meta || {} : {};

    let body = '';
    body += _adm('warning', 'This will create a new file',
        `<code>${meta.path || n}/pyproject.toml</code> will be created
         with <code>requires-python = ">=${floor}"</code>.`);

    body += '<div class="rem-preview">';
    body += `[project]\nname = "${n}"\nrequires-python = ">=${floor}"\n`;
    body += '</div>';

    body += _adm('info', 'What changes after this',
        `• Declared floor: <code>${(item.value||'').replace('≥','')}</code>
           (${item.floor_source || 'stack'}) → <code>${floor}</code> (module)<br>
         • Status: ⚠️ → ✅ consistent<br>
         • Floor source: ${item.floor_source || 'stack'} → module config<br>
         • Anyone on Python below ${floor} cannot install this module`);

    body += _adm('tip', 'This is reversible',
        `You can delete the created pyproject.toml to revert to the
         stack baseline. The platform will re-detect on next scan.`);

    _remConfirm({
        title: '🔧 Create pyproject.toml for ' + n,
        body: body,
        confirmLabel: 'Create file & apply',
        onConfirm: `function() { moduleApplyFloorFix('${n}','${floor}') }`,
    });
}
```

### Option B: Lower effective — add danger admonitions

```javascript
optBContent += _adm('danger', 'This is complex and risky',
    `Lowering the effective floor means downgrading dependencies or
     rewriting code. Older package versions may have unpatched security
     vulnerabilities and missing features. Only do this if you have a
     strong reason to support Python ${declared}.`);

// After showing deps:
optBContent += _adm('warning', 'Downgrade risks',
    `Older versions may have:<br>
     • Known security vulnerabilities (unpatched CVEs)<br>
     • Missing features your code depends on<br>
     • Incompatibilities with other packages in your project`);
```

### "Do nothing" option for every situation

```javascript
// Add to _remFix for gap, cve, eol situations:
let doNothingContent = '';

if (situation === 'gap') {
    doNothingContent += _adm('info', 'What happens if you don\'t act',
        `The gap will continue to show in the posture table. Your module
         works fine on Python 3.12+ — the gap only matters if someone
         tries to deploy on ${declared}.`);
    doNothingContent += _adm('tip', 'When this is fine',
        `If you control the deployment environment and always use a
         recent Python, the gap is cosmetic. Consider adding a note
         in the Decide section to record this decision.`);
} else if (situation === 'cve') {
    doNothingContent += _adm('danger', 'What happens if you don\'t act',
        `The CVE warning will persist. If your effective floor IS the
         vulnerable version, deployments are exposed. If the effective
         floor is higher (because deps raised it), the practical risk
         is lower but the declared compatibility is misleading.`);
} else if (situation === 'eol') {
    doNothingContent += _adm('warning', 'What happens if you don\'t act',
        `After ${eol}, Python ${effClean} stops receiving patches.
         Your module keeps working, but new vulnerabilities won't be fixed.
         Package maintainers will eventually drop support for this version.`);
    doNothingContent += _adm('tip', 'The ecosystem usually handles this',
        `As dependencies release new versions requiring newer Python,
         your effective floor will naturally rise. You may not need
         to act — the ecosystem moves you forward.`);
}

h += _remOption('do-nothing', 'Do nothing — keep current state', doNothingContent);
```

---

## Step 6: Rewrite _remDecide with full explanations + confirmations

### Accept with note — add confirmation

```javascript
// Replace direct moduleSaveNote call with confirmation:
noteContent += `<button class="btn btn-sm btn-primary" style="margin-top:0.5rem"
    onclick="_remConfirmNote('${esc(n)}')">💾 Save note</button>`;

function _remConfirmNote(n) {
    const note = typeof mfVal === 'function' ? mfVal('rem_note') : ...;
    if (!note) { toast('⚠️ Please enter a note', 'warning'); return; }

    let body = '';
    body += _adm('info', 'This will modify project.yml',
        `A <code>version_note</code> will be added to the ${n} module
         in your project.yml. This is version-controlled — it will
         appear in your next git diff.`);
    body += '<div class="rem-preview">';
    body += `modules:\n  - name: ${n}\n    ...\n+   version_note: "${note}"\n`;
    body += '</div>';
    body += _adm('note', 'What this does',
        `The note appears on the module's posture card (📝 icon).
         The warning is NOT suppressed — the data stays visible,
         but marked as acknowledged. Anyone reading the posture
         will see your explanation alongside the finding.`);

    _remConfirm({
        title: '📝 Save note for ' + n,
        body: body,
        confirmLabel: 'Save to project.yml',
        onConfirm: `function() { moduleSaveNote('${n}') }`,
    });
}
```

### Strategy — full panels with admonitions + confirmation

```javascript
// Replace 3 buttons with 3 expandable option cards:

h += _remOption('strat-latest', '🎯 Latest — track current Python',
    _adm('tip', 'Best for application modules',
        `Your module tracks the current Python version. The platform will
         warn you when your floor falls behind, recommend updates when
         new versions release, and treat narrow compatibility as normal.`)
    + _adm('info', 'After setting this',
        `• Strategy badge changes to <strong>latest</strong><br>
         • No more ✱ (deduced) marker<br>
         • Warnings focus on "how far behind current" instead of floor health<br>
         • Compatibility range shown as "how up-to-date you are"`)
    + `<button class="btn btn-sm btn-primary" style="margin-top:0.5rem"
        onclick="_remConfirmStrategy('${esc(n)}','latest')">Set to Latest</button>`
);

h += _remOption('strat-compat', '🌐 Compatibility — wide range is intentional',
    _adm('tip', 'Best for libraries and shared packages',
        `Your module deliberately supports a wide range. The platform
         will treat breadth as a strength, won't warn about being behind,
         and only alert you about EOL versions and CVEs at the floor.`)
    + _adm('info', 'After setting this',
        `• Strategy badge changes to <strong>compat.</strong><br>
         • No more ✱ (deduced) marker<br>
         • Warnings focus on floor health (EOL, CVEs) not version gap<br>
         • Compatibility bar shown as a strength indicator`)
    + `<button class="btn btn-sm btn-primary" style="margin-top:0.5rem"
        onclick="_remConfirmStrategy('${esc(n)}','compatibility')">Set to Compatibility</button>`
);

h += _remOption('strat-auto', '🔄 Auto-detect — let the platform decide',
    _adm('info', 'How auto-detection works',
        `The platform infers your strategy from the constraint gap:<br>
         • Gap ≤ 2 versions → treated as "latest"<br>
         • Gap ≥ 4 versions → treated as "compatibility"<br>
         • Gap = 3 → ambiguous, shown with ✱ marker<br>
         This is the default. Set explicitly to remove the ✱.`)
    + `<button class="btn btn-sm btn-ghost" style="margin-top:0.5rem"
        onclick="_remConfirmStrategy('${esc(n)}','')">Reset to Auto</button>`
);
```

### Defer — add confirmation with expiry warning

```javascript
function _remConfirmDefer(n) {
    const date = ...;
    const reason = ...;

    let body = '';
    body += _adm('info', 'Deferring until ' + date,
        `This warning will be hidden from the posture table until
         the specified date. The underlying issue remains unchanged.`);
    body += _adm('warning', 'When the deferral expires',
        `After <strong>${date}</strong>, the warning re-surfaces with a note:<br>
         <em>"Deferral expired — was deferred because: ${reason}"</em><br>
         You'll need to address it or defer again.`);
    body += _adm('note', 'Where this is stored',
        `Deferrals are saved to <code>.state/module_decisions.json</code>.
         This file is NOT version-controlled — it's local state.
         Other team members won't see the deferral unless they
         share the .state/ directory.`);

    _remConfirm({ ... });
}
```

---

## Step 7: Rewrite _remTrack with admonitions

```javascript
planContent += _adm('info', 'What this creates',
    `A tracked plan with a target floor, target date, and checklist.
     The plan is saved to <code>.state/module_decisions.json</code>
     and visible in the module's posture card.`);

// After checklist:
planContent += _adm('tip', 'You can customize this later',
    `After creating the plan, you can add or remove checklist items,
     update the target date, and mark items as done. The plan tracks
     your progress toward the upgrade.`);

planContent += _adm('note', 'Plans are guidance, not enforcement',
    `The platform tracks your plan but doesn't enforce it.
     Missing the target date doesn't break anything — it just
     surfaces a reminder that the plan is overdue.`);
```

---

## Step 8: Add "What happens next" to all action confirmations

Every confirmation modal gets a success admonition at the bottom:

```javascript
// In _remConfirm for floor fix:
body += _adm('success', 'After applying',
    `The platform will:<br>
     1. Write the new pyproject.toml<br>
     2. Rescan module posture (~2 seconds)<br>
     3. Update the table with the new declared floor<br>
     4. Recalculate effective floor and verdict<br>
     5. Update the posture badge in the nav bar`);

// In _remConfirm for save note:
body += _adm('success', 'After saving',
    `The note appears immediately on the module card (📝 icon).
     The posture table shows your note alongside the finding.
     The change will appear in your next <code>git diff</code>.`);

// In _remConfirm for defer:
body += _adm('success', 'After deferring',
    `The warning disappears from the posture table immediately.
     It re-surfaces after <strong>${date}</strong>.
     The module shows a "deferred" indicator.`);

// In _remConfirm for strategy:
body += _adm('success', 'After setting strategy',
    `The posture table re-evaluates this module immediately.
     The strategy badge updates. Warnings may change based
     on the new evaluation lens.`);
```

---

## Execution Order

```
Step 1: Admonition CSS + _adm() helper          ← foundation, no content changes
Step 2: _remConfirm() helper                    ← foundation, no behavior changes
Step 3: Rewrite _remSummary                     ← visual upgrade, same data
Step 4: Rewrite _remUnderstand                  ← adds detection transparency
Step 5: Rewrite _remFix                         ← adds consequences, "do nothing", confirmations
Step 6: Rewrite _remDecide                      ← full strategy panels, confirmations
Step 7: Rewrite _remTrack                       ← admonitions for plan creation
Step 8: Confirmation wrappers for all handlers  ← wires confirmations to existing APIs
```

Each step is one scope. Steps 1-2 are foundations.
Steps 3-7 are content rewrites (one function per step).
Step 8 wires the confirmation flows.

---

## Files Changed

```
admin.css:
  + .adm, .adm-icon, .adm-content, .adm-title, .adm-body
  + .adm-info, .adm-tip, .adm-warning, .adm-danger, .adm-note, .adm-success

_system_posture.html:
  + _adm() helper function
  + _remConfirm() helper function
  ~ _remSummary() — rewritten with admonitions
  ~ _remUnderstand() — rewritten with admonitions + detection transparency
  ~ _remFix() — rewritten with consequences + "do nothing" + confirmations
  ~ _remDecide() — rewritten with full strategy panels + confirmations
  ~ _remTrack() — rewritten with admonitions
  + _remConfirmRaiseFloor() — confirmation for floor fix
  + _remConfirmNote() — confirmation for save note
  + _remConfirmDefer() — confirmation for defer
  + _remConfirmStrategy() — confirmation for strategy set
  + _remConfirmPlan() — confirmation for plan creation
```

No backend changes needed — all APIs already exist.
