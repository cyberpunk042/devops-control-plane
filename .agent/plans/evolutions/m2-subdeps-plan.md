# M2 Feature: Sub-dependency Visibility

> Status: PLAN
> Last updated: 2026-03-16

---

## Problem

The dependency system shows only **declared dependencies** (from manifests) and
flat installed versions (from pip list). It doesn't show:

- Which sub-dependencies each package pulls in
- Which installed packages are "transitive" (not in your manifest but required by something you declared)
- Why a package is installed ("because flask requires it")
- The full depth of the dependency tree

**Example:** `flask` is declared in pyproject.toml. When installed, it pulls in
`werkzeug`, `jinja2`, `click`, `itsdangerous`, `markupsafe`, `blinker`. Those
are invisible to the user. If `markupsafe` has a CVE, the user doesn't know
which of their declared deps brought it in.

---

## Data Sources

### pip (Python)

| Source | Command | What it gives | Speed |
|--------|---------|--------------|-------|
| `uv pip show <pkg>` | Per-package | `Requires:` (direct deps) + `Required-by:` (reverse) | Fast (~50ms) |
| `pip inspect` | Full dump | All installed packages with `requires_dist` metadata | Medium (~1s for 70 pkgs) |
| `pip show <pkg>` | Per-package | Same as uv pip show | Fast |
| `pipdeptree --json` | Full tree | Complete tree with resolved versions | Fast (if installed) |

**Best approach for pip:**
- **Bulk:** `pip inspect` → parse `requires_dist` for every installed package → build full tree in one call
- **Single-package:** `uv pip show <pkg>` → `Requires:` + `Required-by:` fields
- **Fallback:** iterate `uv pip show` per package (slower but always works)

### npm (Node)

| Source | Command | What it gives | Speed |
|--------|---------|--------------|-------|
| `npm ls --json --depth=N` | Full tree to depth N | Dependencies with sub-dependencies | Medium |
| `npm ls --json --all` | Full tree | Everything including transitive | Slow for large projects |

**Best approach for npm:**
- `npm ls --json --depth=1` for declared + direct sub-deps
- `npm ls --json --depth=0` just for top-level (what we do now essentially)

### go / cargo

- `go mod graph` → full dependency graph
- `cargo tree` → full tree with features

---

## Data Model

```python
@dataclass
class SubDep:
    """A sub-dependency relationship."""
    name: str           # Package name
    version_spec: str   # Version constraint (e.g. ">=1.9.0")
    installed: str      # Actually installed version
    required_by: str    # Who requires this (parent package name)
    depth: int          # 0 = declared, 1 = direct sub-dep, 2+ = transitive
    is_extra: bool      # From an optional extra (e.g. flask[async])

@dataclass
class PackageDeps:
    """Full dependency info for one package."""
    name: str
    requires: list[SubDep]      # What this package needs (children)
    required_by: list[str]      # Who needs this package (parents)
    is_declared: bool           # True if in the manifest
    is_transitive: bool         # True if only installed as a sub-dep
```

---

## Architecture

```
                    ┌──────────────────────────────┐
                    │        Manifest               │
                    │   (pyproject.toml / pkg.json)  │
                    │                                │
                    │  flask >=3.0                   │  ← DECLARED (depth 0)
                    │  click >=8.1                   │
                    │  pydantic >=2.0                │
                    └──────────┬───────────────────────┘
                               │
                    ┌──────────▼───────────────────────┐
                    │     Installed (pip list)           │
                    │                                    │
                    │  flask 3.1.3                      │  ← matches manifest
                    │  click 8.3.1                      │  ← matches manifest
                    │  pydantic 2.12.5                  │  ← matches manifest
                    │  werkzeug 3.1.6                   │  ← TRANSITIVE (from flask)
                    │  itsdangerous 2.2.0               │  ← TRANSITIVE (from flask)
                    │  markupsafe 3.0.3                 │  ← TRANSITIVE (from jinja2 ← flask)
                    │  typing-extensions 4.15.0         │  ← TRANSITIVE (from pydantic)
                    └──────────┬───────────────────────┘
                               │
                    ┌──────────▼───────────────────────┐
                    │     Sub-dep tree (pip inspect)     │
                    │                                    │
                    │  flask 3.1.3                      │
                    │  ├── werkzeug >=3.1.0             │
                    │  ├── jinja2 >=3.1.2               │
                    │  │   └── markupsafe >=2.1.1       │
                    │  ├── click >=8.1.3                │ ← also declared directly
                    │  ├── itsdangerous >=2.2.0         │
                    │  ├── blinker >=1.9.0              │
                    │  └── markupsafe >=2.1.1           │
                    │                                    │
                    │  pydantic 2.12.5                  │
                    │  ├── pydantic-core 2.41.5         │
                    │  │   └── typing-extensions >=4.6  │
                    │  ├── typing-extensions >=4.6      │
                    │  └── annotated-types >=0.6        │
                    └──────────────────────────────────┘
```

---

## UI: Where sub-deps appear

### 1. Package detail (C3 - Version Intel panel)

When you click a package in the tree, the detail panel gets a new section:

```
┌───────────────────────────────────────────────────────────────┐
│  flask                                                  ●     │
│                                                               │
│  Declared:    >=3.0                                           │
│  Installed:   3.1.3 in .venv-ft                              │
│  Status:      INSTALLED                                       │
│                                                               │
│  ▼ Dependencies (6)                                           │
│  ├── werkzeug >=3.1.0          3.1.6 ●                       │
│  ├── jinja2 >=3.1.2            3.1.6 ●  (also declared)      │
│  │   └── markupsafe >=2.1.1    3.0.3 ●                       │
│  ├── click >=8.1.3             8.3.1 ●  (also declared)      │
│  ├── itsdangerous >=2.2.0      2.2.0 ●                       │
│  ├── blinker >=1.9.0           1.9.0 ●                       │
│  └── markupsafe >=2.1.1        3.0.3 ●                       │
│                                                               │
│  ▼ Required by (1)                                            │
│  └── devops-control-plane (declared in pyproject.toml)        │
└───────────────────────────────────────────────────────────────┘
```

### 2. Ecosystem overview — transitive package count

```
  Health: 17 declared · 32 installed (15 transitive)
```

### 3. Tree node — expandable sub-deps

In the left tree, a package node could be expandable to show its sub-deps:

```
  ▶ flask >=3.0              3.1.3  ●  [web]
```

Expand:

```
  ▼ flask >=3.0              3.1.3  ●  [web]
      werkzeug               3.1.6  ●
      jinja2                 3.1.6  ●  (declared)
      click                  8.3.1  ●  (declared)
      itsdangerous           2.2.0  ●
      blinker                1.9.0  ●
      markupsafe             3.0.3  ●
```

### 4. "Why is this installed?" reverse lookup

Click any transitive package → detail shows the chain:

```
  markupsafe 3.0.3
  Required by: jinja2 → flask → pyproject.toml [web]
               jinja2 → devops-control-plane → pyproject.toml [main]
```

### 5. Dashboard card — transitive awareness

```
  🐍 root — Python (pip) — pyproject.toml
  17 declared · 32 total installed (15 transitive)   ● installed
```

---

## Backend

### New file: `src/core/services/dependency_mgr/subdeps.py`

```python
def get_package_deps(project_root, package, venv_path=None):
    """Get sub-dependencies for one package.
    Returns: {"requires": [...], "required_by": [...]}
    Uses: uv pip show <package>
    """

def get_full_dep_tree(project_root, venv_path=None):
    """Build the full dependency tree for all installed packages.
    Returns: {"packages": {name: PackageDeps}, "declared": [...], "transitive": [...]}
    Uses: pip inspect (if available) or iterative uv pip show
    """

def classify_packages(declared_names, installed_names, dep_tree):
    """Classify each installed package as declared or transitive.
    Returns: {"declared": [...], "transitive": [...], "orphaned": [...]}
    """
```

### New route: `GET /dependencies/subdeps/<package>`

Returns sub-dependencies for a single package (lazy-loaded on click).

### New route: `GET /dependencies/tree-full`

Returns the full dependency tree with transitive classification.
Expensive — cached in mediator with long TTL.

### Mediator node: `dependency.subdeps`

Full dependency tree. TTL 1 hour. Depends on `dependency.installed`.

---

## Implementation plan

### Phase 1: Single-package sub-deps (lazy, fast)
- `subdeps.py:get_package_deps()` using `uv pip show`
- Route: `GET /dependencies/subdeps/<package>`
- UI: "Dependencies" and "Required by" sections in version intel panel (C3)
- Triggered on package click — lazy loaded, no upfront cost

### Phase 2: Transitive classification (bulk, background)
- `subdeps.py:get_full_dep_tree()` using `pip inspect`
- Classify all installed packages as declared vs transitive
- Ecosystem overview shows "N declared · M total (K transitive)"
- Dashboard card shows transitive count

### Phase 3: Tree expansion (UI)
- Package nodes in left tree become expandable to show sub-deps
- Sub-dep nodes are visual-only (not checkboxable, not operable)
- "Why is this installed?" reverse chain in detail panel

### Phase 4: npm sub-deps
- `npm ls --json --depth=1` for Node packages
- Same UI pattern as pip

---

## Ecosystem-specific commands

| Ecosystem | Single package | Full tree | Reverse lookup |
|-----------|---------------|-----------|----------------|
| pip | `uv pip show <pkg>` → Requires/Required-by | `pip inspect` → requires_dist | `uv pip show <pkg>` → Required-by |
| npm | `npm ls <pkg> --json` | `npm ls --json --depth=1` | `npm ls --json` + search |
| go | `go mod graph` + filter | `go mod graph` | `go mod graph` + reverse |
| cargo | `cargo tree -p <pkg>` | `cargo tree` | `cargo tree --invert <pkg>` |

---

## What this does NOT include

- Full transitive tree to arbitrary depth (just 1-2 levels)
- Conflict resolution between transitive deps
- License analysis of transitive deps
- CVE propagation through the tree (future: connect to security scanner)
- Auto-removal of orphaned transitive packages
