# Modules Posture V3 — Execution Plan
> Status: READY TO EXECUTE — 2026-03-17
> Builds on: V2 (peek panels, conversational tooltips, action buttons)
> Delivers: Full remediation workflows for every module posture situation

---

## Infrastructure Available

### File Operations
- **YAML write**: `yaml.safe_load()` + `yaml.dump(sort_keys=False)` — no ruamel
- **Preserve keys**: `config_ops.py` pattern — read, modify, preserve unrelated keys
- **Atomic JSON**: `state_file.py` pattern — write to temp, rename
- **Thread-safe JSON**: `plan_storage.py` pattern — threading.Lock + atomic
- **File generation**: wizard pattern — build file list, return for writing

### UI Toolkit
- **Modal stacking**: `modalOpen({replace: false})` — proven pattern
- **Form fields**: `modalFormField()` — text, select, textarea, checkbox, number
- **Step indicators**: `modalSteps(stepNames, activeIndex)`
- **Preview panels**: `modalPreview(title, content)`
- **Expandable sections**: toggle class + CSS display (dep modal pattern)
- **Option grid**: remediation modal pattern — buttons with per-option panels
- **Confirmation gates**: single checkbox or double type-to-confirm
- **Peek panels**: `_moduleShowPeek()` — already built in V2

### Data Intelligence
- **PyPI API**: pip_adapter already calls `pypi.org/pypi/{pkg}/json`
  — has ALL versions in `releases` dict, each with `requires_python`
  — currently only reads latest, but data is there
- **Import scanning**: module_intel already scans per-module imports
- **Dist-info reading**: already reads `Requires-Python` from installed packages
- **Sub-dep resolution**: `get_package_deps()` resolves dependency trees
- **Version comparison**: basic semver comparison exists

### Persistence
- **project.yml**: version_note + version_strategy fields (V2)
- **module-note endpoint**: POST `/api/posture/module-note` (V2)
- **.state/ directory**: for plans, checklists, deferrals
- **Event store**: for logging remediation actions to timeline

---

## Step 1: Remediation Modal Framework

Build the expandable remediation panel that opens from Status peek panel
or from the "Needs attention" section. This is the shell that all
situation-specific content plugs into.

### What to build

**Function: `moduleRemediate(moduleName)`**

Opens a modal (stacked on posture with `replace: false`) containing
4 expandable sections: Understand, Fix, Decide, Track.

Each section header is clickable — expands/collapses its content.
Content is built per-situation by content builder functions.

```javascript
window.moduleRemediate = function(moduleName) {
    const item = _modulePeekItems.find(i => i._moduleName === moduleName);
    if (!item) return;
    _moduleHidePeek();

    const verdict = item.verdict || '';
    const rank = item.rank || '';

    // Determine situation
    let situation = 'none';
    if (verdict === 'gap') situation = 'gap';
    else if (verdict === 'could_lower') situation = 'could_lower';
    else if (rank === 'dangerous') situation = 'cve';
    else if (rank === 'outdated' || rank === 'deprecated') situation = 'eol';
    else if (verdict === 'consistent') situation = 'ok';

    // Build sections
    const body = _remBuildSections(item, situation);

    modalOpen({
        title: _remTitle(situation, moduleName),
        replace: false,
        body: body,
        size: 'wide',
        footerButtons: [
            { label: 'Close', onclick: 'modalClose()' },
        ],
    });
};
```

**Section builder pattern:**

```javascript
function _remBuildSections(item, situation) {
    let html = '';

    // Summary — always visible, explains the situation
    html += _remSummary(item, situation);

    // Understand section — expandable
    html += _remSection('understand', '🔍 Understand',
        _remUnderstand(item, situation), true);  // true = start expanded

    // Fix section — expandable, contains option cards
    html += _remSection('fix', '🔧 Fix',
        _remFix(item, situation));

    // Decide section — expandable
    html += _remSection('decide', '📝 Decide',
        _remDecide(item, situation));

    // Track section — expandable
    html += _remSection('track', '📋 Track',
        _remTrack(item, situation));

    return html;
}

function _remSection(id, title, content, expanded = false) {
    return `
        <div class="rem-section ${expanded ? 'expanded' : ''}" id="rem-${id}">
            <div class="rem-section-header" onclick="this.parentElement.classList.toggle('expanded')">
                <span class="rem-section-chevron">▸</span>
                <span class="rem-section-title">${title}</span>
            </div>
            <div class="rem-section-body">${content}</div>
        </div>
    `;
}
```

### CSS for remediation sections

```css
.rem-section { border: 1px solid var(--border); border-radius: var(--radius-md);
               margin-bottom: 0.5rem; overflow: hidden; }
.rem-section-header { display: flex; align-items: center; gap: 0.5rem;
                      padding: 0.6rem 0.75rem; cursor: pointer;
                      background: var(--surface); font-weight: 600;
                      font-size: 0.88rem; }
.rem-section-header:hover { background: var(--surface-2); }
.rem-section-body { padding: 0 0.75rem; max-height: 0; overflow: hidden;
                    transition: max-height 0.25s ease, padding 0.25s ease; }
.rem-section.expanded .rem-section-body { max-height: 2000px;
                                          padding: 0.75rem; }
.rem-section-chevron { transition: transform 0.2s; font-size: 0.7rem; }
.rem-section.expanded .rem-section-chevron { transform: rotate(90deg); }

.rem-summary { padding: 0.75rem; margin-bottom: 0.75rem;
               background: var(--surface); border-radius: var(--radius-md);
               border-left: 3px solid var(--warning); line-height: 1.6;
               font-size: 0.85rem; }
.rem-summary.ok { border-left-color: var(--success); }
.rem-summary.info { border-left-color: var(--accent); }
.rem-summary.danger { border-left-color: var(--error); }

.rem-option { border: 1px solid var(--border); border-radius: var(--radius-md);
              margin-bottom: 0.5rem; overflow: hidden; }
.rem-option-header { display: flex; align-items: center; justify-content: space-between;
                     padding: 0.6rem 0.75rem; cursor: pointer; }
.rem-option-header:hover { background: var(--surface-2); }
.rem-option.recommended { border-color: var(--accent);
                          box-shadow: 0 0 0 1px var(--accent) inset; }
.rem-option-body { padding: 0 0.75rem; max-height: 0; overflow: hidden;
                   transition: max-height 0.25s ease, padding 0.25s ease; }
.rem-option.expanded .rem-option-body { max-height: 2000px;
                                        padding: 0.75rem; }
.rem-option-badge { font-size: 0.65rem; padding: 2px 6px; border-radius: 4px;
                    font-weight: 600; }
.rem-option-badge.recommended { background: hsla(210,80%,55%,0.15);
                                color: var(--accent); }
.rem-option-badge.advanced { background: hsla(38,70%,50%,0.12);
                             color: hsl(38,70%,65%); }

.rem-preview { background: var(--bg-inset); border: 1px solid var(--border);
               border-radius: var(--radius-md); padding: 0.6rem;
               font-family: 'SF Mono', monospace; font-size: 0.75rem;
               line-height: 1.5; margin: 0.5rem 0; overflow-x: auto; }
.rem-preview .added { color: var(--success); }
.rem-preview .removed { color: var(--error); }
.rem-preview .context { color: var(--text-muted); }
```

### Files changed
- `_system_posture.html` — `moduleRemediate()`, section builders, option builders
- `admin.css` — `.rem-*` classes

---

## Step 2: Per-Situation Content — GAP

The most common situation. Module declares wider compatibility than reality.

### 🔍 Understand content

```javascript
function _remUnderstandGap(item) {
    const declared = (item.value || '').replace('≥', '');
    const effClean = (item.effective_floor || '').replace('≥', '');
    const source = item.floor_source || 'unknown';
    const deps = item.deps_details || [];
    const features = item.code_features || [];

    let h = '';

    // Why does this gap exist?
    h += '<div class="mp-section">Why does this gap exist?</div>';
    if (source === 'stack') {
        h += `<p>Your declared floor is <code>${esc(declared)}</code>, which comes from the
              <strong>${esc(item.stack)}</strong> stack baseline. This is what the technology
              supports in general — but your specific module needs more because of its
              dependencies and code.</p>`;
    } else {
        h += `<p>Your declared floor is <code>${esc(declared)}</code> from your ${esc(source)} config,
              but your module actually needs <code>${esc(effClean)}+</code> to run.</p>`;
    }

    // What drives the gap
    if (deps.length) {
        const sorted = [...deps].sort((a,b) => /* version sort */);
        h += '<div class="mp-section">Dependencies that raise the floor</div>';
        h += '<div class="rem-preview">';
        for (const d of sorted) {
            h += `${esc(d.package)} requires Python ${esc(d.requires_python)}\n`;
        }
        h += '</div>';
    }
    if (features.length) {
        h += '<div class="mp-section">Code features that raise the floor</div>';
        h += '<div class="rem-preview">';
        for (const f of features) {
            const short = (f.file || '').split('/').slice(-2).join('/');
            h += `${esc(f.version)} — ${esc(f.feature)} in ${esc(short)}:${f.line}\n`;
        }
        h += '</div>';
    }

    // Is this actually a problem?
    h += '<div class="mp-section">Is this actually a problem?</div>';
    h += `<p>It depends on where you deploy:</p>`;
    h += `<ul style="margin:0.3rem 0;padding-left:1.2rem;font-size:0.82rem">`;
    h += `<li>If you only deploy on Python 3.12+ → the gap is cosmetic. Nothing breaks.</li>`;
    h += `<li>If you publish this as a library → the gap is a real bug. Users on
          ${esc(declared)} will install it and it will fail.</li>`;
    h += `<li>If you have CI testing on ${esc(declared)} → your CI is testing a
          configuration that can't work.</li>`;
    h += `</ul>`;

    return h;
}
```

### 🔧 Fix content — 4 options

**Option A: Raise the declared floor (recommended)**
- Show what file would be created/modified
- Preview the changes
- "Apply" button calls API to create the file
- After apply: re-scan posture, update the table

**Option B: Update project root config**
- Explain that project root has `requires-python = ">=3.11"` but module uses stack baseline
- Suggest Option A is cleaner
- Link to Option A

**Option C: Lower the effective floor (advanced)**
- For each dep driving the floor, show:
  - Current version and its Python constraint
  - Last version that supports the declared floor
  - Cost of downgrading (how many versions behind, breaking changes?)
- For code features, show:
  - Which files use the feature
  - What the 3.8-compatible alternative looks like
  - How many files need changing
- Verdict: "lowering is expensive" or "lowering is feasible"

**Option D: Split the difference**
- Show intermediate floors (e.g. target 3.9 instead of 3.8 or 3.10)
- For each, show what would need to change
- Calculate the sweet spot

### 📝 Decide content
- **Accept with note** — textarea + save to project.yml
- **Defer until date** — date input + reason textarea + save to .state/
- **Set strategy** — dropdown (latest/compatibility/auto) + save

### 📋 Track content
- **Create version plan** — target floor + target date + auto-checklist
- **Set review date** — date + reason

### API needed for Fix Option A

```python
@posture_bp.route("/posture/module-fix-floor", methods=["POST"])
def posture_module_fix_floor():
    """Create or update a module's pyproject.toml with requires-python.

    Body: {module: "core", target_floor: "3.10"}

    If module has no pyproject.toml → creates minimal one.
    If module has pyproject.toml → adds/updates requires-python.
    Returns diff preview if preview=true, applies if preview=false.
    """
```

### API needed for Fix Option C

```python
@posture_bp.route("/posture/module-dep-alternatives", methods=["POST"])
def posture_module_dep_alternatives():
    """Find older versions of a dep that support a target Python floor.

    Body: {package: "click", target_python: "3.8"}

    Queries PyPI JSON API for all versions of the package.
    Returns versions compatible with target_python, sorted by recency.
    Includes: version, requires_python, release_date, breaking flag.
    """
```

### Files changed
- `_system_posture.html` — gap content builders
- `posture.py` — 2 new endpoints
- `module_intel.py` — dep alternative lookup function (calls PyPI API)

---

## Step 3: Per-Situation Content — EOL

Floor version approaching or past end-of-life.

### 🔍 Understand content
- What EOL means in plain language
- Timeline visualization (today → EOL → risk increases)
- Which modules are affected
- When will deps naturally drop this version
- What happens after EOL (nothing breaks, but unpatched)

### 🔧 Fix content
- **Raise floor preemptively** — same as Gap Option A but with EOL context
- **Wait for ecosystem** — explain that deps will raise their floors naturally
- **Test on newer version** — guide to running tests on 3.10+

### 📝 Decide + 📋 Track
- Same patterns as Gap, but with EOL-specific defaults:
  - Defer date defaults to 3 months before EOL
  - Plan checklist includes "update CI matrix" and "test on target version"

### No new API needed — reuses Gap endpoints

---

## Step 4: Per-Situation Content — CVE

Floor version has known vulnerabilities.

### 🔍 Understand content
- Is the risk real or theoretical? (effective vs declared analysis)
- CVE details — severity, description, affected versions
- What the CVE actually does (link to advisory)

### 🔧 Fix content
- **Raise floor above CVE version** — same as Gap Option A
- If effective > declared: explain that the CVE is on the declared floor
  but the effective floor (which is what actually runs) is safe

### Urgency indicators
- CVE situations get red border on summary
- "Immediate action recommended" language
- But contextualized: if effective floor is safe, explain that

### No new API needed — reuses Gap endpoints

---

## Step 5: Per-Situation Content — COULD LOWER

Module could support wider compatibility.

### 🔍 Understand content
- What wider compatibility means
- For libraries vs apps — different value
- How many more Python versions would be supported
- Practical value (are those versions still used?)

### 🔧 Fix content
- **Lower the declared floor** — show what to change
- **Add CI testing for lower versions** — guide to matrix update
- **Accept current floor** — explain why it's fine

### Mostly informational — lower urgency
- Blue/info border on summary
- "No action required" language
- Options are opportunities, not fixes

---

## Step 6: Deferral System

Persistence for "I'll handle this later" decisions.

### Storage

```
.state/module_decisions.json
{
  "core": {
    "deferred_until": "2026-09-01",
    "deferred_reason": "Waiting for vendor SDK 3.10 support",
    "deferred_at": "2026-03-17T14:30:00Z",
    "deferred_by": "user"
  },
  "web": {
    "review_date": "2026-06-01",
    "review_reason": "Check if Flask 4.0 drops 3.9"
  }
}
```

### Behavior
- Deferred modules show muted styling in the table
- Warning suppressed until defer date
- After defer date: warning re-surfaces with "deferral expired" note
- Deferral logged to event store

### API

```python
@posture_bp.route("/posture/module-defer", methods=["POST"])
def posture_module_defer():
    """Defer a module posture warning until a date.

    Body: {module: "core", until: "2026-09-01", reason: "..."}

    Saves to .state/module_decisions.json.
    Suppresses warning in posture until the date passes.
    Logs deferral to event store.
    """
```

### Files changed
- New: `src/core/persistence/module_decisions.py` — load/save decisions
- `posture.py` — new endpoint
- `bridges/modules.py` — read decisions, suppress warnings for deferred modules
- `_system_posture.html` — defer form in Decide section
- `admin.css` — deferred row styling

---

## Step 7: Version Plan System

Structured plan for upgrading a module's floor.

### Storage

```
.state/module_decisions.json (extended)
{
  "core": {
    "version_plan": {
      "target_floor": "3.12",
      "target_date": "2026-09",
      "created_at": "2026-03-17",
      "checklist": [
        {"label": "Verify all deps support 3.12", "done": false},
        {"label": "Update requires-python to >=3.12", "done": false},
        {"label": "Update CI matrix to include 3.12", "done": false},
        {"label": "Run full test suite on 3.12", "done": false},
        {"label": "Remove 3.8/3.9 compatibility code", "done": false}
      ]
    }
  }
}
```

### UI
- Track section shows plan creation form
- Once created, shows checklist with check/uncheck
- Progress bar (3/5 done)
- Target date with countdown

### API

```python
@posture_bp.route("/posture/module-plan", methods=["POST"])
def posture_module_plan():
    """Create or update a version upgrade plan for a module.

    Body: {
        module: "core",
        target_floor: "3.12",
        target_date: "2026-09",
        checklist: [...]
    }
    """

@posture_bp.route("/posture/module-plan/check", methods=["POST"])
def posture_module_plan_check():
    """Toggle a checklist item in a version plan.

    Body: {module: "core", index: 2, done: true}
    """
```

### Files changed
- `module_decisions.py` — plan storage
- `posture.py` — plan endpoints
- `_system_posture.html` — plan creation form + checklist renderer

---

## Step 8: Dep Alternative Lookup

For "lower the effective floor" — find which older dep versions
support a target Python floor.

### Implementation

New function in `module_intel.py`:

```python
async def find_compatible_dep_versions(
    package: str,
    target_python: str,
) -> list[dict]:
    """Query PyPI for versions of a package compatible with target Python.

    Calls https://pypi.org/pypi/{package}/json
    Iterates releases, checks requires_python for each.
    Returns sorted list of compatible versions with metadata.
    """
```

### What it returns

```python
[
    {
        "version": "8.0.4",
        "requires_python": ">=3.7",
        "release_date": "2022-03-15",
        "is_latest_compatible": True,
        "versions_behind": 3,  # 8.0.4 → 8.3.1 = 3 minor versions
        "breaking_from_current": False,  # same major
    },
    {
        "version": "7.1.2",
        "requires_python": ">=3.6",
        "release_date": "2021-09-01",
        "is_latest_compatible": False,
        "versions_behind": 8,
        "breaking_from_current": True,  # different major
    }
]
```

### How the UI uses it

In Fix Option C, when the user clicks "Show alternatives for click":
- Calls `/api/posture/module-dep-alternatives`
- Shows table of compatible versions
- Highlights the recommended one (latest compatible, same major)
- Shows the cost: "3 minor versions behind, no breaking changes"
- For breaking changes: warns "this is a major version downgrade"

### Files changed
- `module_intel.py` — `find_compatible_dep_versions()`
- `posture.py` — `/posture/module-dep-alternatives` endpoint
- `_system_posture.html` — alternative version display in Fix Option C

---

## Step 9: File Operations — Create/Modify pyproject.toml

The platform needs to CREATE a `pyproject.toml` in a module directory
(for Fix Option A) or MODIFY the root one.

### Create minimal pyproject.toml

```python
def create_module_pyproject(
    project_root: Path,
    module_path: str,
    module_name: str,
    requires_python: str,
) -> dict:
    """Create a minimal pyproject.toml for a module.

    Returns: {"path": "src/core/pyproject.toml", "content": "...", "is_new": True}
    """
    target = project_root / module_path / "pyproject.toml"

    if target.is_file():
        # Modify existing — add/update requires-python
        content = target.read_text(encoding="utf-8")
        # ... insert/replace requires-python line
        return {"path": str(target.relative_to(project_root)),
                "content": new_content, "is_new": False}

    # Create new minimal file
    content = f'''[project]
name = "{module_name}"
requires-python = "{requires_python}"
'''
    return {"path": str(target.relative_to(project_root)),
            "content": content, "is_new": True}
```

### Preview mode vs apply mode

The endpoint accepts `preview=true` (returns diff without writing)
or `preview=false` (writes the file and returns result).

```python
@posture_bp.route("/posture/module-fix-floor", methods=["POST"])
def posture_module_fix_floor():
    body = request.get_json()
    module = body["module"]
    target_floor = body["target_floor"]
    preview = body.get("preview", True)

    result = create_module_pyproject(
        project_root, ref.path, module, f">={target_floor}",
    )

    if preview:
        return jsonify({"preview": result})

    # Apply
    target_path = project_root / result["path"]
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(result["content"], encoding="utf-8")

    # Re-scan posture
    ## THIS WAS RETARD -> invalidate_cache("modules")
    ## WE NEED TO USE THE SYSTEM IN PLACE NO RE-INVENT

    return jsonify({"applied": True, "path": result["path"]})
```

### Files changed
- New: `src/core/services/system_posture/bridges/module_ops.py` — file operations
- `posture.py` — fix-floor endpoint

---

## Step 10: Event Integration

Log remediation actions to the event store for timeline visibility.

### Events to emit

```
module.posture.acknowledged     — user added version_note
module.posture.strategy_set     — user set version_strategy
module.posture.deferred         — user deferred warning
module.posture.deferral_expired — deferral date passed
module.posture.floor_raised     — user applied floor fix
module.posture.plan_created     — user created version plan
module.posture.plan_step_done   — user checked a plan step
```

### Implementation

Use existing `@tracked` decorator on API endpoints + `emit_event()`
for background events (deferral expiry).

### Files changed
- `posture.py` — add `@tracked` to new endpoints
- `bridges/modules.py` — emit deferral expiry events during scan

---

## Execution Order

```
Step 1:  Remediation modal framework (shell + CSS + expandable sections)
Step 2:  GAP content (understand + fix options A/B + decide + track)
Step 3:  EOL content (understand + fix + decide + track)
Step 4:  CVE content (understand + fix + contextualized risk)
Step 5:  COULD LOWER content (understand + options + accept)
Step 6:  Deferral system (persistence + API + suppress + expiry)
Step 7:  Version plan system (persistence + API + checklist UI)
Step 8:  Dep alternative lookup (PyPI query + UI display)
Step 9:  File operations (create pyproject.toml + preview + apply)
Step 10: Event integration (timeline visibility for all actions)
```

Steps 1-5 are the content layer — conversational, no new APIs.
Steps 6-7 are the persistence layer — new storage + APIs.
Steps 8-9 are the intelligence layer — PyPI queries + file ops.
Step 10 is the observability layer — events for everything.

Each step is one scope. Each step leaves the system working.

---

## New Files Summary

```
BACKEND:
  src/core/persistence/module_decisions.py    (NEW — deferral + plan storage)
  src/core/services/system_posture/bridges/module_ops.py  (NEW — file operations)
  module_intel.py                             (EXTEND — dep alternative lookup)
  posture.py                                  (EXTEND — 4 new endpoints)

FRONTEND:
  _system_posture.html                        (EXTEND — remediation modal + all content)
  admin.css                                   (EXTEND — .rem-* classes)

DATA:
  .state/module_decisions.json                (NEW — deferrals + plans)
```

---

## API Summary

```
Existing (V2):
  POST /posture/module-note        — save version_note + strategy

New (V3):
  POST /posture/module-fix-floor   — create/modify pyproject.toml
  POST /posture/module-dep-alternatives — find compatible dep versions
  POST /posture/module-defer       — defer warning until date
  POST /posture/module-plan        — create/update version plan
  POST /posture/module-plan/check  — toggle plan checklist item
```
