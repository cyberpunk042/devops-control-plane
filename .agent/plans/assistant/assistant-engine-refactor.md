# Assistant Engine Refactor — Plan

> **Goal**: Split 3,331-line monolith into maintainable modules.
> Zero regressions. Every resolver, enricher, and event handler works
> exactly as before — we're reorganising, not rewriting.
>
> **Status**: Phase 1+2 COMPLETE. Phase 3 (inline style sweep) remaining.

---

## Current State

```
_assistant_engine.html              3,331 lines   (100%)
├── Core engine                     1,380 lines   (41%)
│   ├── Catalogue loading              17 lines
│   ├── Resolution (panel/var/etc)    100 lines
│   ├── _resolveDynamic               507 lines   ← mixed concerns
│   ├── _matchNode                    103 lines
│   ├── Rendering + scroll            166 lines
│   ├── Event handlers                138 lines
│   ├── Highlights                    157 lines
│   ├── Listeners + public API        125 lines
│   └── _flattenTree                   16 lines
│
└── Domain resolvers                1,822 lines   (55%)
    ├── Docker resolvers            1,241 lines   (37% of file!)
    │   ├── Card resolvers             53 lines
    │   ├── Image parsing/knowledge   191 lines
    │   ├── Compose analysis           76 lines
    │   ├── Docker Setup modal        580 lines
    │   └── Port analysis             341 lines
    ├── K8s resolvers                 325 lines
    ├── GitHub resolvers               57 lines
    ├── Pages resolvers                55 lines
    ├── Terraform resolvers            44 lines
    ├── Wizard defaults                59 lines
    └── Integration resolvers          41 lines
```

### Pain points

1. **_resolveDynamic** (507 lines) — contains if/else blocks for
   9 different parent node IDs across 4 stacks. Every new card type
   means another block here.

2. **All resolvers in one file** — Docker alone is 1,241 lines.
   Adding a new stack means editing a 3,331-line file.

3. **K8s wizard inline styles** — 577 occurrences across 305 unique
   patterns. Many repeat 7-22 times. Should be CSS classes.

---

## Target State

```
_assistant_engine.html              ~1,100 lines  (core only)
├── Catalogue loading
├── Resolution (panel, variant, static variant)
├── _flattenTree
├── _resolveDynamic (generic loop + enricher dispatch)
├── _matchNode
├── Rendering + scroll
├── Event handlers
├── Highlights
├── Listeners + public API
└── Enricher registry: window._assistant.enrichers = {}

_assistant_resolvers_shared.html    ~250 lines
├── _parseDockerImage + _dockerImageKnowledge
├── _classifyPort, _detectPortConflicts
├── _knownPorts, _portRanges
└── Utility functions used by multiple resolver files

_assistant_resolvers_docker.html    ~850 lines
├── Resolvers: dockerDaemon, dockerVersion, dockerComposeCli,
│   dockerDockerfiles, dockerServices, dockerIgnoreRules,
│   dockerModules, dockerStack, dockerBaseRuntime/Version/Variant,
│   dockerBaseBreakdown, dockerfileAnalysis, dockerSvcAnalysis,
│   dkSetup* (all Docker Setup modal resolvers), dkPort*, dkExpose*,
│   dkInfra* (all infra resolvers)
└── Enrichers: docker-section-dockerfiles, docker-section-compose-svcs

_assistant_resolvers_k8s.html       ~400 lines
├── Resolvers: k8sManifests, k8sResources, k8sFieldValue,
│   k8sSvcCardKind, k8sDepHover, k8sInfraCardHover, k8sInfraKind,
│   k8sVolRowType, k8sPortHover
└── Enrichers: k8s-section-manifests, k8s-section-helm,
    k8s-section-kustomize, k8s-cfg-skf-profiles

_assistant_resolvers_misc.html      ~350 lines
├── Wizard defaults: envCount, domainCount, moduleCount, selectedStack
├── Integrations: toolsMissing, toolsInstalled, toolsTotal,
│   filesDetected, filesTotal, integrationCount
├── GitHub: ghUser, ghRepo, ghVis, ghBranch, ghEnv*, ghWorkflows
├── Pages: pagesSegments, pagesFolders, pagesBranch, pagesBuilders*, etc.
├── Terraform: tfResources, tfProviders, tf*Value, dns*Value, ci*Value
└── Enrichers: tf-section-files, tf-section-providers, tf-section-modules,
    env/module context enrichment (default badge, stack/path metadata)
```

### Inclusion order in `dashboard.html`:

```html
{% include 'scripts/_assistant_engine.html' %}
{% include 'scripts/_assistant_resolvers_shared.html' %}
{% include 'scripts/_assistant_resolvers_misc.html' %}
{% include 'scripts/_assistant_resolvers_docker.html' %}
{% include 'scripts/_assistant_resolvers_k8s.html' %}
```

---

## Design Pattern: Enricher Registry

The key architectural change. Instead of if/else chains in
`_resolveDynamic`, each resolver file registers enricher functions:

```javascript
// In core engine — public registry
window._assistant.enrichers = {};

// In _assistant_resolvers_docker.html
window._assistant.enrichers['docker-section-dockerfiles'] =
    function(el, extractedName, parentNode) {
        // ... read DOM, return { content, expanded } or null
    };

// In _resolveDynamic — generic dispatch (replaces 9 if/else blocks)
var enricher = window._assistant.enrichers[parentNode.id];
if (enricher) {
    var enriched = enricher(el, extractedName, parentNode);
    if (enriched) {
        if (enriched.content)  nodeContent  = enriched.content;
        if (enriched.expanded) nodeExpanded = enriched.expanded;
        if (enriched.title)    nodeTitle    = enriched.title;
    }
}
```

**Why this works**:
- Zero coupling between core and domain files
- New stacks just register their enrichers — no core edits
- Each enricher is self-contained and testable
- The "generic" context enrichment (default badge, stack metadata)
  stays in the core loop since it applies to all dynamic children

---

## Phases

### Phase 1 — Enricher Registry + Core Extraction ✅ COMPLETE

**What**: Added enricher registry to core, extracted 9 if/else blocks
from `_resolveDynamic`, replaced with 6-line enricher dispatch.

**Result**:
- `_resolveDynamic`: 507 → 120 lines (76% reduction)
- 9 domain blocks → single dispatch: `window._assistant.enrichers[parentNode.id]`
- Generic context enrichment (default badge, stack metadata) stays in core
- All enrichers registered from domain resolver files

---

### Phase 2 — Resolver File Split ✅ COMPLETE

**What**: Moved all 66 resolvers + 9 enrichers out of engine into
4 domain-specific files.

**Result**:
```
File                                Lines   Purpose
_assistant_engine.html              1,117   Core engine only (was 3,331)
_assistant_resolvers_shared.html      151   Docker image parser, port analysis
_assistant_resolvers_docker.html    1,256   26 resolvers + 2 enrichers
_assistant_resolvers_k8s.html         535   9 resolvers + 4 enrichers
_assistant_resolvers_misc.html        419   31 resolvers + 3 enrichers
                                    ─────
Total                               3,478   (was 3,331 — ~4% overhead from wrappers)
```

- Private functions exposed via `window._assistant._shared`
- All `_parseDockerImage` → `_s.parseDockerImage` etc.
- Brace balance verified ✓ on all 5 files
- Include order in `dashboard.html`: engine → shared → misc → docker → k8s

---

### Phase 3 — K8s Wizard Inline Style Sweep ⏳ NEXT

**What**: Extract the 305 unique inline style patterns (577
occurrences) across 7 K8s wizard HTML files into CSS classes.

**Pre-work done**: Assistant state card inline styles already cleaned
(87 → 2 in catalogue JSON, new CSS classes: `.state-grid`, `.state-key`,
`.state-text`, `.state-text-spaced`, `.state-wrap`).

**Steps**:
1. Identify the top 15-20 repeating patterns (covers ~350 of 577)
2. Create CSS classes in `admin.css` under a K8s wizard section:
   - `.k8s-field-input` (text inputs)
   - `.k8s-field-select` (selects)
   - `.k8s-field-label` (field labels)
   - `.k8s-field-hint` (hint text below fields)
   - `.k8s-badge` (small status badges)
   - `.k8s-link-action` (clickable action links)
   - `.k8s-card-section` (expandable sections)
   - `.k8s-row` (flex rows)
   - `.k8s-col` (flex columns)
   - etc. (exact names TBD based on pattern analysis)
3. Replace inline styles with classes across all files
4. Visual regression check

**Risk**: Low-medium — some styles may have contextual overrides
that a flat class doesn't capture. Need to verify visually.

**Lines affected**: ~577 occurrences across 7 files

---

## Checklist for Each Phase

- [ ] No function signatures change
- [ ] `window._assistant` public API unchanged
- [ ] All resolvers accessible via `window._assistant.resolvers.*`
- [ ] All enrichers fire for the same parent node IDs
- [ ] No new global variables (all scoped inside IIFEs or on `_assistant`)
- [ ] Visual rendering identical before/after
- [ ] No console errors

---

## What This Enables

- **New stack integration** (e.g., Pulumi, Ansible): create
  `_assistant_resolvers_pulumi.html`, register enrichers,
  add one `{% include %}` — zero core edits.

- **Easier debugging**: each domain file is <900 lines,
  grep for a resolver name → find it in one file.

- **Parallel development**: Docker resolvers can evolve
  independently from K8s resolvers.

- **Style consistency**: CSS classes instead of 305 unique
  inline patterns means one place to update visual language.

---

## Order of Execution

```
Phase 1  →  Phase 2  →  Phase 3
(safe)      (structural)  (cosmetic)
```

Each phase is independently valuable and test-verified before
proceeding to the next. Phase 1 can be paused at the "holding
area" stage if inspection is needed before splitting files.
