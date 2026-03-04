# Smart Virtual Folders — Analysis (Final)

> A system to discover, aggregate, and surface documentation that lives inside
> code source directories, making it available across all consumption layers:
> Docusaurus site builds, Content Browser, and the Setup Wizard.

---

## Current State

### Inner Documentation: 89 README.md files in `src/`

| Layer | Path Pattern | Count |
|-------|-------------|-------|
| **Core Services** | `src/core/services/*/README.md` | 24 |
| **Tool Install (deep)** | `src/core/services/tool_install/*/README.md` | 10 |
| **CLI Commands** | `src/ui/cli/*/README.md` | 19 |
| **Web Routes** | `src/ui/web/routes/*/README.md` | 26 |
| **Frontend Modules** | `src/ui/web/templates/scripts/*/README.md` | 9 |
| **Cross-cutting** | `src/core/services/CROSS_CUTTING.md` | 1 |

All invisible to: Docusaurus site, Content Browser, Setup Wizard.

### Existing Modules in `project.yml`

```yaml
modules:
  - name: core       path: src/core        stack: python-lib
  - name: adapters   path: src/adapters    stack: python-lib
  - name: cli        path: src/ui/cli      stack: python-cli
  - name: web        path: src/ui/web      stack: python-flask
  - name: docs       path: docs            stack: markdown
```

These modules directly map to the documentation grouping structure.

### Integration Points with Gaps

| System | Current State | Gap |
|--------|--------------|-----|
| `project.yml` | `content_folders: [docs]` | No smart folder concept |
| Wizard Step 4 | Scans top-level dirs only | No code-embedded docs section |
| Content Browser | Physical folder browsing | No virtual/aggregated views |
| Docusaurus Builder | Single source per segment | No multi-source or smart folder injection |
| Pages Integration | Segments build from `content_folders` | No awareness of smart folder sources |

---

## DECIDED: Data Model

```yaml
content_folders:
  - docs
smart_folders:
  - name: code-docs
    label: "Code Documentation"
    target: docs
    sources:
      - path: src/
        pattern: "**/README.md"
```

| Field | Purpose |
|-------|---------|
| `name` | Identifier AND virtual subfolder name |
| `label` | Human-readable name in UI |
| `target` | Existing content folder to mount inside (creates `<target>/<name>/`), or same as `name` for standalone |
| `sources[].path` | Root directory to scan (any path, not just `src/`) |
| `sources[].pattern` | Glob pattern (`**/README.md`, `**/*.md`) |

### Target Behavior

- **`target: docs`** → Virtual subfolder `docs/code-docs/` appears inside the `docs` content folder. Smart mode activates when you enter `code-docs/`.
- **`target: code-docs`** (= name) → Standalone. Own entry in folder selector, always in smart mode.

---

## DECIDED: Module-Aware Navigation

The smart folder uses **declared modules from `project.yml`** as the top-level
grouping. Within each module, it's a normal tree with full depth.

The discovery service cross-references discovered files against declared modules
to determine grouping. Files outside any declared module go in an "Other" section.

### Example: `target: docs`, entering `docs/code-docs/`

```
📦 code-docs
│
├── � core (src/core)                      ← module from project.yml
│   └── 📂 services/
│       ├── 📄 README.md                     ← src/core/services/README.md
│       ├── 📄 CROSS_CUTTING.md              ← src/core/services/CROSS_CUTTING.md
│       ├── 📂 audit/
│       │   └── 📄 README.md
│       ├── 📂 chat/
│       │   └── 📄 README.md
│       ├── 📂 generators/
│       │   └── 📄 README.md
│       ├── 📂 tool_install/                 ← deep nesting preserved
│       │   ├── 📄 README.md
│       │   ├── 📂 data/
│       │   │   ├── 📄 README.md
│       │   │   ├── 📂 recipes/
│       │   │   │   └── 📄 README.md
│       │   │   └── 📂 remediation_handlers/
│       │   │       └── 📄 README.md
│       │   ├── 📂 detection/
│       │   │   └── 📄 README.md
│       │   ├── 📂 domain/
│       │   │   └── 📄 README.md
│       │   ├── 📂 execution/
│       │   │   └── � README.md
│       │   ├── 📂 orchestration/
│       │   │   └── 📄 README.md
│       │   └── 📂 resolver/
│       │       └── � README.md
│       └── ... (24 services total)
│
├── � cli (src/ui/cli)                     ← module from project.yml
│   ├── 📂 audit/
│   │   └── 📄 README.md
│   ├── 📂 backup/
│   │   └── 📄 README.md
│   └── ... (19 CLI commands total)
│
└── 📦 web (src/ui/web)                     ← module from project.yml
    ├── 📂 routes/
    │   ├── 📄 README.md
    │   ├── 📂 audit/
    │   │   └── 📄 README.md
    │   └── ... (26 routes total)
    └── 📂 templates/scripts/
        ├── 📂 assistant/
        │   └── 📄 README.md
        └── ... (9 frontend modules total)
```

**Modules** at the top level. Tree within each module — normal tree-list
navigation with breadcrumbs, same interaction pattern as the current
content browser. Files are read from their real source locations.

### Smart vs Raw Toggle

Available ONLY inside a smart folder (`docs/code-docs/` or standalone):

- **Smart mode** (default): Module-grouped tree of discovered documentation
- **Raw mode**: Shows the actual source filesystem instead — useful for seeing
  code files alongside the READMEs, understanding the full module structure

---

## DECIDED: Preview

Standard markdown rendering — same as the current content browser preview.
The README content speaks for itself.

Advanced preview features are planned (not optional, but done in order):
1. Module context header (source path, sibling code files)
2. Code reference detection — detect mentions of code paths/functions, provide
   navigation and glance into referenced code
3. Cross-module linking
4. Adapted features at multiple levels (remark plugin, admin panel, CLI)

---

## DECIDED: Build-Time Behavior

Driven by target:
- **`target: docs`** → Smart folder contents are injected into the `docs`
  segment build under `docs/code-docs/`. One site, one segment, one build.
- **`target: code-docs`** (standalone) → Own Pages segment, built separately.

This follows the target semantics naturally.

---

## Full Scope — Nothing Optional

| Layer | What | Status |
|-------|------|--------|
| **L0: Data Model** | `smart_folders` in `project.yml` + config_ops | Fully defined |
| **L1: Discovery Service** | Module-aware scanner, file manifest, tree builder | Fully defined |
| **L2: Wizard Step 4** | Smart folder config UI in Content step | Defined — details at implementation |
| **L3: Content Browser** | Virtual subfolder, smart mode, module tree, smart/raw toggle | Defined — details at implementation |
| **L4: Pages/Build Pipeline** | Smart folder injection into Docusaurus builder | Defined — details at implementation |
| **L5: Advanced Preview** | Code reference detection, glancing, cross-module links | Scope known, details analyzed when we get there |
| **L6: Multi-Level Adaptation** | Remark plugin, admin panel, CLI integration of code docs | Scope known, details analyzed when we get there |
