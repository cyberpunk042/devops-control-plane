# Class Diagram Generator — Layered Output Plan

> **Status**: Proposed — awaiting user approval
> **Parent**: `.agent/plans/scripts-system/scripts-system-M3-class-diagrams.md`
> **Date**: 2026-03-07
> **Scope**: Evolution of class_diagrams.py from "raw dump" to "smart layered" output

---

## 0. Problem Statement

The current Class Diagram Generator produces **one monolithic Mermaid diagram** per run.
For the full project or `core` scope, this means:

| What | Current output |
|------|---------------|
| Mermaid block | 63,937 chars, 1,496 lines |
| Total file | 92,202 bytes, 2,069 lines |
| Classes in diagram | 168 nodes |
| Relationships | 135 edges |
| Namespaces | 76 packages |

**Result:** Unreadable. Exceeds Mermaid's 50K default text limit. Browser renders a
visual mess even when maxTextSize is raised. No human can parse 168 boxes with 135 arrows.

---

## 1. Data Analysis — What the codebase actually looks like

### 1.1 Module tree (class distribution)

```
TOP-LEVEL (3 modules):
  adapters:   10 classes
  core:      168 classes     ← 94% of everything
  ui:          1 class

DEPTH-2 (17 modules):
  adapters.*:       7 modules, 1–2 classes each        ← ALL digestible
  core.config:      1 class                             ← trivial
  core.data:       10 classes                           ← medium
  core.engine:      2 classes                           ← trivial
  core.models:     17 classes (5 sub-modules, 1–4 each) ← medium
  core.observability: 7 classes                         ← small
  core.persistence: 2 classes                           ← trivial
  core.reliability: 5 classes                           ← small
  core.services:  120 classes (14 sub-modules)          ← THE MONSTER
  core.use_cases:   4 classes                           ← small
  ui.web:           1 class                             ← trivial

DEPTH-3 core.services breakdown (14 sub-modules):
  core.services.audit:          40 classes, 47 edges    ← needs its own section
  core.services.artifacts:      21 classes, 15 edges    ← needs its own section
  core.services.pages_builders: 18 classes, 16 edges    ← needs its own section
  core.services.content:        15 classes, 14 edges    ← fits as section
  core.services.changelog:       4 classes               ← small
  core.services.pages:           4 classes               ← small
  core.services.chat:            3 classes               ← small
  core.services.ledger:          3 classes               ← small
  core.services.peek:            3 classes               ← small  
  core.services.scripts:         3 classes               ← small
  core.services.trace:           2 classes               ← small
  core.services.project_index:   2 classes               ← small
  core.services.detection:       1 class                 ← trivial
  core.services.event_bus:       1 class                 ← trivial
```

### 1.2 Edge distribution (inter-module coupling)

```
Within-package edges:  124 (92%)   ← Modules are highly self-contained
Cross-package edges:    31 (8%)    ← Low coupling between modules

Cross-module dependencies (depth-2):
  core.models ↔ core.use_cases:    5 edges  (use cases consume models)
  adapters.base ↔ adapters.*:      9 edges  (adapters inherit from base)
  adapters.* ↔ core.models:        7 edges  (adapters depend on models)
  core.engine ↔ core.models:       2 edges
  core.engine ↔ core.use_cases:    2 edges

Within core.services sub-modules:
  Cross-dependencies:  0 (!)       ← Each sub-module is an ISLAND
  Internal edges:    100           ← All relationships are within the sub-module
```

**Key insight:** Core.services sub-modules have ZERO cross-dependencies.
Each is a fully self-contained cluster. This is ideal for per-section diagrams.

### 1.3 Diagram size analysis (chars)

| Sub-module | Nodes | Edges | Detail (w/ fields+methods) | Overview (names only) |
|------------|-------|-------|---------------------------|----------------------|
| core.services.audit | 40 | 47 | 19,403c | 9,750c |
| core.services.pages_builders | 18 | 16 | 10,233c | 4,222c |
| core.services.artifacts | 21 | 15 | 9,693c | 5,326c |
| core.services.content | 15 | 14 | 4,020c | 3,153c |
| core.services.pages | 4 | 3 | 1,815c | 938c |
| core.models.state | 4 | 3 | 1,736c | 595c |
| core.services.changelog | 4 | 2 | 1,599c | 722c |
| core.reliability (2 sub) | 5 | 3 | 2,941c | 986c |
| adapters.base | 2 | 0 | 612c | 209c |

**Threshold finding:**
- Under ~5,000c → renders fast, fits in viewport with zoom
- 5,000–15,000c → renderable but needs zoom
- Over 15,000c → slug to render, should be split further
- Over 50,000c → exceeds Mermaid default limit, MUST split

---

## 2. Deeper Data Analysis — Understanding the structure

### 2.1 Class kind distribution

The analyzer already detects class types. This is intelligence we're currently ignoring:

```
regular:    85 classes (47%)    ← service classes, strategies, registries
dataclass:  63 classes (35%)    ← pure data structures (fields, no behavior)
pydantic:   26 classes (15%)    ← validated data models (similar to dataclass)
abstract:    5 classes (3%)     ← base classes that define interfaces
```

**Intelligence opportunity:** Dataclasses and pydantic models are **data** — they should be
rendered differently from **service** classes. A smart diagram knows the difference between
a container of fields and a component with behavior.

### 2.2 Relationship type distribution

```
inherits:    53 edges (34%)     ← class hierarchies
aggregates:  43 edges (28%)     ← list[X], set[X] — one has many
depends:     29 edges (19%)     ← method params/returns reference another class
composes:    19 edges (12%)     ← field of type X — one owns one
associates:  11 edges (7%)      ← Optional[X] — might reference
```

**Intelligence opportunity:** Different relationship types tell different stories.
Inheritance tells you about **structure** (who is derived from what).
Composition/aggregation tells you about **ownership** (who contains what).
Dependencies tell you about **coupling** (who uses who).

A smart output doesn't dump all 155 edges into one diagram. It shows
the RIGHT edges for the RIGHT question.

### 2.3 Connected components (natural clusters)

The graph has **54 connected components**:

```
33 components of size 1     ← orphan classes (no relationships detected)
 8 components of size 2     ← simple pairs
 1 component  of size 3     ← small cluster
 5 components of size 4     ← small clusters
 1 component  of size 5     ← core.observability.metrics
 1 component  of size 9     ← pages_builders hierarchy
 1 component  of size 13    ← artifacts builder hierarchy
 1 component  of size 15    ← content outline strategy hierarchy
 2 components of size 18    ← audit (2 separate clusters!)
 1 component  of size 29    ← THE CORE: adapters + models + use_cases + engine
```

**Intelligence opportunity:** Connected components are the **natural** grouping.
Not module paths — actual coupling. The biggest component (29 nodes) spans
adapters, models, use_cases, and engine — these classes BELONG TOGETHER
in a diagram regardless of their file paths.

Meanwhile, audit has TWO separate clusters of 18 —
they share the same module path but are actually independent graphs.

### 2.4 Inheritance trees

We detected 6 meaningful inheritance hierarchies:

```
Adapter (abstract, 7 children):
  └─ DockerAdapter, NodeAdapter, PythonAdapter,
     MockAdapter, ShellCommandAdapter, FilesystemAdapter, GitAdapter

ArtifactBuilder (abstract, 12 children):
  └─ CargoBuilder, DockerBuilder, DotnetBuilder, GemBuilder,
     GoBuilder, GradleBuilder, MakefileBuilder, MavenBuilder,
     MixBuilder, NpmBuilder, PipBuilder, ScriptBuilder

ArtifactPublisher (abstract, 3 children):
  └─ GitHubReleasePublisher, NpmPublisher, PyPIPublisher

BaseParser (abstract, 11 children):
  └─ FallbackParser, CFamilyParser, ConfigParser, CSSParser,
     GoParser, JavaScriptParser, JVMParser, MultiLangParser,
     PythonParser, RustParser, TemplateParser

OutlineStrategy (abstract, 14 children):
  └─ MarkdownOutlineStrategy, PythonOutlineStrategy, EncryptedOutlineStrategy,
     JavaScriptOutlineStrategy, GoOutlineStrategy, RustOutlineStrategy, ...

PageBuilder (abstract, 6 children):
  └─ CustomBuilder, DocusaurusBuilder, HugoBuilder,
     MkDocsBuilder, RawBuilder, SphinxBuilder
```

**Intelligence opportunity:** Each of these is a **strategy pattern** or **plugin system**.
The smart way to show these is NOT in a flat class diagram — it's as a focused
**inheritance tree** where the abstract base is the root and implementations fan out.
One diagram per hierarchy. Clear, purposeful, self-documenting.

### 2.5 Hub classes (nexus points)

```
FileAnalysis:     16 edges    ← everything in audit touches this
BaseParser:       14 edges    ← all parsers inherit from here
OutlineStrategy:  14 edges    ← all outline strategies inherit from here
ArtifactBuilder:  12 edges    ← all artifact builders inherit from here
Adapter:          10 edges    ← all adapters inherit from here
Receipt:          10 edges    ← consumed by multiple models
PageBuilder:       7 edges    ← all page builders inherit from here
Project:           7 edges    ← core data model, referenced widely
BuilderInfo:       7 edges    ← metadata model for builders
```

**Intelligence opportunity:** Hub classes are the critical nexus points of the system.
A smart output HIGHLIGHTS these — they're the nodes that if you understand them,
you understand how the whole system is wired.

---

## 3. What "smart" actually means — the intelligence model

### 3.1 Inspiration: C4 Model + Question-Driven Views

The C4 Model (Context, Container, Component, Code) uses 4 zoom levels,
each answering a different question. Our project is not a distributed system,
so we adapt the concept to a codebase:

| C4 Level | Our equivalent | Question answered |
|----------|---------------|-------------------|
| Context | Architecture Overview | "What are the major building blocks and how do they depend on each other?" |
| Container | Module Map | "What does this module contain and how is it organized internally?" |
| Component | Structural Patterns | "What are the key design patterns (inheritance trees, strategy groups)?" |
| Code | Class Detail | "What fields and methods does this specific class have?" |

### 3.2 Multiple view types — not just "zoom levels"

A smart output doesn't just zoom in/out. It offers **different views for different questions**.
Each view uses the same underlying data but presents it **differently**.

#### View 1: Architecture Map
- **Question:** "What are the building blocks?"
- **Diagram type:** Mermaid `graph TD` (flowchart, not classDiagram)
- **Content:** Packages as boxes with class counts, inter-package dependency arrows
- **Size:** ~16 boxes, ~20 arrows → always small and readable
- **When:** Always rendered, it's the entry point

#### View 2: Inheritance Forests
- **Question:** "What's the class hierarchy? Where are the polymorphism points?"
- **Diagram type:** Mermaid `classDiagram` with annotations
- **Content:** One tree per abstract base class + all its children
- **Rendering:** Base at top, children fan out. `<<abstract>>`, `<<dataclass>>` annotations.
  NO fields/methods — just names and the `--|>` inheritance arrows.
- **Why this view matters:** Our codebase has 6 clear strategy/plugin hierarchies.
  These are THE most important structural patterns to understand. The raw dump
  buries them in 76 namespaces. This view makes them the star.
- **Size:** 3–15 nodes per tree → always readable

#### View 3: Module Detail (per sub-module)
- **Question:** "What's inside this specific module?"
- **Diagram type:** Mermaid `classDiagram` with full fields + methods
- **Content:** All classes in one sub-module, all their relationships,
  full UML-style with fields, methods, and Mermaid annotations
- **Rendering rules:**
  - `<<dataclass>>` for dataclasses, `<<pydantic>>` for pydantic models, `<<abstract>>` for ABCs
  - `note for ClassName "Hub: 16 connections"` for hub classes
  - Fields and methods shown (truncated at max_fields/max_methods)
- **Smart decision:** Only render this for sub-modules with ≤15 classes.
  For larger ones, render an overview-only version (names + relationships, no fields)
  and link to deeper sub-sections.

#### View 4: Hub Analysis
- **Question:** "What are the critical classes that tie everything together?"
- **Diagram type:** Mermaid `classDiagram` with styled nodes
- **Content:** Top N most-connected classes + their immediate neighbors, regardless of module
- **Why this view matters:** Hubs are refactoring hot spots, coupling indicators,
  and the classes every new developer needs to learn first.
  The raw dump gives them no special treatment.
- **Size:** ~15-25 nodes → readable, focused

#### View 5: Orphan Index (table, not diagram)
- **Question:** "What classes exist but have no detected relationships?"
- **Format:** Markdown table, NOT a Mermaid diagram
- **Content:** Class name, module, kind (dataclass/regular/etc), fields count, methods count
- **Why table, not diagram:** Orphan classes have no edges → a diagram of disconnected boxes
  is worse than a table. The table is scannable. The diagram is a waste of space.

### 3.3 The intelligence decision tree

The smart output doesn't blindly apply rules. It **analyzes the data** and makes decisions:

```
GIVEN: a ClassGraph with N nodes, E edges

IF N == 0:
    → "No classes found" message, done

ALWAYS:
    → Render View 1: Architecture Map

IF there are inheritance trees with 3+ nodes:
    → Render View 2: Inheritance Forests (one diagram per tree)

FOR each depth-2 module M with classes:
    count = classes in M
    IF count <= 3:
        → Render one full-detail classDiagram (small enough)
    ELIF count <= 15:
        → Render one full-detail classDiagram with annotations
    ELIF count <= 30:
        → Render one overview-only diagram (names + relationships, no fields)
        → FOR each depth-3 sub-module S within M:
            sub_count = classes in S
            IF sub_count <= 15:
                → Render full-detail classDiagram for S
            ELSE:
                → Render overview for S + recurse to depth-4
    ELSE (>30):
        → Overview only at this level
        → Recurse to depth-3, applying same logic

IF hub classes exist (any class with 6+ edges):
    → Render View 4: Hub Analysis diagram

IF orphan classes exist:
    → Render View 5: Orphan Index table
```

### 3.4 Mermaid-specific intelligence

Beyond content selection, there are rendering intelligence decisions:

**Annotations:** Already detected by the analyzer but NEVER used in output:
```mermaid
class VaultOps {
    <<service>>
}
class AuditMeta {
    <<dataclass>>
}
class Adapter {
    <<abstract>>
}
class Environment {
    <<pydantic>>
}
```

**Notes:** For hub classes or important context:
```mermaid
note for FileAnalysis "Hub: 16 connections\nUsed by all parsers"
note for Adapter "Abstract base for all adapters\n7 implementations"
```

**Direction:** Different views benefit from different orientations:
- Architecture map: `TD` (top-down, classic dependency flow)
- Inheritance trees: `BT` (bottom-to-top, children point to parent — natural for "inherits")
- Module detail: `LR` (left-to-right, better for wide class boxes)

**Namespace grouping in overviews:** When rendering a module with sub-modules,
use Mermaid's `namespace` syntax to visually cluster:
```mermaid
classDiagram
    namespace audit_models { class AuditMeta; class L0Result; ... }
    namespace audit_parsers { class BaseParser; class PythonParser; ... }
```

---

## 4. The Smart Output — Document Structure

### 4.1 Complete output structure for this project

Based on the actual data analysis, here's exactly what the smart output produces:

```
# Class Architecture — Full Project

> Generated: 2026-03-08  |  179 classes  |  155 relationships  |  17 modules

## Table of Contents
- [Architecture Overview](#architecture-overview)
- [Inheritance Forests](#inheritance-forests)
  - Adapter hierarchy (8 classes)
  - ArtifactBuilder hierarchy (13 classes)
  - BaseParser hierarchy (12 classes)
  - OutlineStrategy hierarchy (15 classes)
  - PageBuilder hierarchy (7 classes)
  - ArtifactPublisher hierarchy (4 classes)
- [Module Details](#module-details)
  - adapters (10 classes) — [full detail]
  - core.models (17 classes) — [full detail, by sub-module]
  - core.data (10 classes) — [full detail]
  - core.observability (7 classes) — [full detail]
  - core.reliability (5 classes) — [full detail]
  - core.services.audit (40 classes) — [overview + sub-module details]
  - core.services.artifacts (21 classes) — [overview + sub-module details]
  - core.services.pages_builders (18 classes) — [overview + sub-module details]
  - core.services.content (15 classes) — [full detail]
  - core.services (small modules) — [grouped detail]
  - core.engine (2 classes) — [full detail]
  - core.use_cases (4 classes) — [full detail]
- [Hub Analysis](#hub-analysis)
- [Orphan Index](#orphan-index)

────────────────────────────────────────────────────────

## Architecture Overview                              ← VIEW 1
  graph TD with ~16 boxes and ~20 arrows
  Shows: adapters → core.models ← core.use_cases
         core.engine → core.use_cases
         adapters.* → adapters.base
         etc.

## Inheritance Forests                                ← VIEW 2
  6 separate classDiagram blocks:
  - Adapter tree:          8 nodes, ~800c
  - ArtifactBuilder tree: 13 nodes, ~1200c
  - BaseParser tree:      12 nodes, ~1100c
  - OutlineStrategy tree: 15 nodes, ~1300c
  - PageBuilder tree:      7 nodes, ~700c
  - ArtifactPublisher:     4 nodes, ~400c

## Module Details                                     ← VIEW 3

  ### adapters (10 classes)
    Full detail diagram: 10 nodes, ~3500c  ✓ readable

  ### core.models (17 classes)
    Overview diagram: names only, 17 nodes, ~1200c
    Then per sub-module (stack, state, project, action, module):
    5 sub-diagrams, 2–4 classes each

  ### core.services.audit (40 classes)
    Overview diagram: names + namespaces, 40 nodes, ~9750c
    Sub-modules: models (10), parsers._base (5), parsers.* (varies)
    Each sub-module gets full detail

  ### core.services.artifacts (21 classes)
    Overview diagram: names only, 21 nodes, ~5326c
    Sub-modules: builders.base (2), builders.* (12 individual), publishers (4)

  (... etc for each module)

  ### core.services — small modules grouped
    Modules with ≤3 classes (changelog, chat, ledger, peek, scripts, trace,
    project_index, detection, event_bus) rendered as one combined diagram
    or individual compact diagrams

## Hub Analysis                                       ← VIEW 4
  Top ~10 most-connected classes + their neighbors
  FileAnalysis (16 edges), BaseParser (14), OutlineStrategy (14),
  ArtifactBuilder (12), Adapter (10), Receipt (10)

## Orphan Index                                       ← VIEW 5
  Table of 33 orphan classes with: name, module, kind, field count
```

### 4.2 Estimated output sizing

| Section | Diagrams | Estimated total chars |
|---------|----------|----------------------|
| Architecture Overview | 1 flowchart | ~800c |
| Inheritance Forests | 6 classDiagrams | ~5,500c |
| Module Details — small | ~10 full-detail | ~12,000c |
| Module Details — medium | ~5 overview + subs | ~15,000c |
| Module Details — large (audit, artifacts, content) | 3 overviews + ~8 sub-details | ~25,000c |
| Hub Analysis | 1 classDiagram | ~3,000c |
| Orphan Index | 1 table | ~2,000c |
| **Total** | **~34 diagrams** | **~63,000c across all diagrams** |

Compare to current: 1 diagram of 63,937c that exceeds the render limit.
Smart output: 34 diagrams, each under 10K, all individually readable.
Same total data, completely different user experience.

---

## 5. Solution Architecture

### 5.1 Where each piece lives

The solution respects the existing layer structure:

```
class_diagrams.py  (script — orchestration + CLI params)
  ├── calls graph_builder.py  for data extraction
  │     ├── build_class_graph()         ← exists
  │     ├── filter_by_package()         ← exists (needs src. prefix fix)
  │     ├── extract_package_deps()      ← NEW
  │     ├── extract_inheritance_trees() ← NEW
  │     └── extract_hub_classes()       ← NEW
  ├── calls mermaid_generator.py  for rendering
  │     ├── render_class_diagram()      ← exists
  │     ├── render_component_diagram()  ← exists (never used until now)
  │     ├── render_flowchart()          ← exists (never used until now)
  │     └── (MermaidConfig already has show_fields/show_methods/include_orphans)
  └── calls report_formatter.py  for document assembly
        ├── format_markdown_report()    ← exists (used for raw)
        └── format_smart_report()       ← NEW (the orchestrator)
```

### 5.2 New functions needed

#### In `graph_builder.py` (data extraction):

```python
def extract_package_dependencies(graph, depth=2):
    """Aggregate class-level edges into package-level deps.
    
    Returns: (packages_dict, dep_list)
    Where packages_dict = {pkg_name: [class_labels]}
    And dep_list = [(src_pkg, tgt_pkg)] deduplicated
    """

def extract_inheritance_trees(graph, min_children=2):
    """Find all inheritance hierarchies with N+ children.
    
    Returns: list of trees, each = { root: node_id, children: [node_id, ...] }
    Only includes trees where the root has min_children+ direct inheritors.
    """

def extract_hub_classes(graph, min_edges=6):
    """Find classes with the most connections.
    
    Returns: list of (node_id, edge_count) sorted by count descending.
    Only includes nodes with min_edges+ total connections.
    """
```

#### In `report_formatter.py` (document assembly):

```python
def format_smart_report(analysis, graph, *, title, max_depth=3):
    """Assemble a multi-view, multi-layer markdown document.
    
    Calls the view renderers in sequence:
    1. Architecture overview
    2. Inheritance forests
    3. Module details (recursive per depth)
    4. Hub analysis
    5. Orphan index
    """
```

#### In `class_diagrams.py` (script):

```python
# New param: --style raw|smart (default: smart)
# When style=smart: call format_smart_report()
# When style=raw: existing behavior preserved
```

### 5.3 What we DO NOT need to build

Already exists and just needs to be called:
- `render_component_diagram()` — perfect for architecture overview
- `render_class_diagram()` with `MermaidConfig(show_fields=False, show_methods=False)` — overview mode
- `render_class_diagram()` with `MermaidConfig(include_orphans=True)` — full detail mode
- `ClassGraph.filter_by_package()` — per-module extraction (after prefix fix)
- `ClassGraph.get_connected_components()` — natural clustering
- `ClassGraph.get_orphan_nodes()` — orphan detection

### 5.4 Bug fix prerequisite

`filter_by_package('core.services.audit')` currently returns empty because packages
are stored with `src.` prefix. Must fix by having filter_by_package normalize the
prefix: try both `package` and `src.{package}`.

---

## 6. Implementation Plan

### 6.1 Step sequence

```
Step 1: Fix filter_by_package src. prefix     (graph_builder.py, ~5 lines)
           Prerequisite for everything else.
           Verification: filter_by_package('core.services.audit') returns 40 nodes

Step 2: Add extract_package_dependencies      (graph_builder.py, ~35 lines)
           Aggregates class edges → package edges.
           Verification: returns 18 cross-package deps matching known data

Step 3: Add extract_inheritance_trees         (graph_builder.py, ~30 lines)
           Finds abstract → children trees.
           Verification: returns 6 trees matching known data

Step 4: Add extract_hub_classes               (graph_builder.py, ~15 lines)
           Finds most-connected nodes.
           Verification: returns FileAnalysis(16), BaseParser(14), ...

Step 5: Add format_smart_report               (report_formatter.py, ~150 lines)
           The orchestrator that assembles all views.
           Calls: extract_*, render_*, filter_by_package
           Verification: run on full project, inspect output structure

Step 6: Add --style param + wire up           (class_diagrams.py, ~20 lines)
           New CLI param, calls format_smart_report when style=smart.
           Verification: --style raw = old output, --style smart = new output
```

### 6.2 Files changed

| File | Changes | Lines added (est.) |
|------|---------|-------------------|
| `lib/graph_builder.py` | Fix prefix + 3 new extract functions | ~85 |
| `lib/report_formatter.py` | New `format_smart_report()` | ~150 |
| `generators/class_diagrams.py` | New `--style` param + wiring | ~20 |
| **Total** | | **~255 lines** |

No new files. No new dependencies. No breaking changes.

---

## 7. Risks and mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| `core.services.audit` overview (9,750c) is borderline large | Slow render | Acceptable — under 15K threshold. Viewport zoom controls help. |
| Inheritance trees may duplicate nodes from module detail views | Same class appears twice | Acceptable — different views serve different purposes. Add a note: "See also: [Module Detail]" |
| 34 diagrams in one document → long page | Scroll fatigue | ToC with anchor links. Each view is independently scannable. |
| `render_component_diagram` format differs from `classDiagram` | Visual inconsistency | Intentional — flowchart for overview, classDiagram for detail. Different visual = different purpose. |
| Core super-component (29 nodes across adapters+models+engine) can't be split by module | Large cross-module diagram | Render as a dedicated "Core Architecture" section with notes explaining the cross-module coupling |

---

## 8. Open questions for user decision

1. **Default filename:** Should `--style smart` produce `class_architecture.md` (distinct from raw's
   `class_diagram.md`) or overwrite the same file?

2. **Hub analysis threshold:** We used 6+ edges as the hub threshold. Should this be configurable
   or is 6 a good default? (Currently produces 9 hub classes for our project.)

3. **Small module grouping:** For modules with 1–3 classes, should we group them into one combined
   "Small Modules" section, or render each tiny module individually?

4. **Inheritance tree deduplication:** When an inheritance tree (e.g., Adapter → DockerAdapter, ...)
   also appears in the module detail section, should we show it in both places, or only in the
   Inheritance Forests view with a "see above" reference in the module section?

---

## 9. Success criteria

1. Running `--style smart` on the full project produces a document where:
   - **Every diagram is under 15,000 chars** (renderable without maxTextSize issues)
   - **Architecture overview has ≤20 boxes** (readable at a glance)
   - **Each inheritance tree is its own focused diagram** (clear pattern recognition)
   - **Hub classes are highlighted** (critical system understanding)
   - **Orphan classes are in a table** (scannable, not wasted diagram space)
   - **Navigation via ToC** links to specific views and modules
2. Running `--style raw` produces **identical** output to current behavior
3. The output answers **5 different questions** about the codebase, not just
   "what classes exist" (the only question raw answers)
