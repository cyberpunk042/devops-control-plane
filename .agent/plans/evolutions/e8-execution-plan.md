# E8 — Execution Plan
> Status: EXECUTE NOW — 2026-03-17
> This is the action plan. No future phases. Everything here happens now.

---

## What's broken right now

1. **All modules show identical data** — deps floor, code floor, effective, verdict
   are the same for core, adapters, cli, web. The detection is not per-module.

2. **Deps floor reads from shared venv** — `_scan_dist_info_requires_python()`
   scans ALL installed packages in site-packages. Every module gets the same
   `≥3.12` because they all share the same venv. But different modules use
   different packages.

3. **Code floor doesn't account for `__future__` annotations** — the scanner
   detects `X | Y` as 3.10+ but if `from __future__ import annotations` is
   present, union types work on 3.7+. The actual code floors are:
   - src/core: 3.9+ (7 files use `list[X]` at runtime without __future__)
   - src/ui/web: 3.7+ (all modern syntax gated by __future__)
   - src/ui/cli: 3.7+ (same)
   - src/adapters: 3.7+ (same)

4. **The UI doesn't fully match the plan visual** — missing proper styling,
   the floor health column shows detail text that should only be in advisories.

---

## Fix 1: Per-module dependency floor

### The problem

This is a monorepo with ONE pyproject.toml at the root. All deps are declared
there. The venv has all packages installed. Current code scans the entire
site-packages → every module gets the same deps floor.

### What exists to help

The dependency_mgr already has:
- `DeclaredDep.source_path` — tracks which directory declared a dep
- `DeclaredDep.group` — tracks "main", "dev", "optional" group
- `pyproject.toml` has optional-dependencies: `[web]` (flask, cryptography)
- The tree structure organizes deps by `{ecosystem}:{path}`

The project's pyproject.toml structure:
```
[project]
dependencies = [click, pydantic, pyyaml, python-dotenv, jinja2]  ← ALL modules

[project.optional-dependencies]
web = [flask, cryptography]                                       ← web module only
dev = [pytest, ruff, mypy, ...]                                   ← dev tools
ocr = [pytesseract, Pillow]                                       ← optional
```

### The solution

Two approaches, use BOTH:

**Approach A — Dependency groups from pyproject.toml:**
- `dependencies` (main) → shared by ALL Python modules
- `web` optional group → belongs to the `web` module
- Map optional-dependency group names to module names where possible

**Approach B — Import analysis:**
- For each module directory, scan `.py` files for `import X` / `from X import`
- Map import names to installed package names
- The packages a module actually imports are its real dependencies
- This gives the most accurate per-module dep list

For deps floor: once we know WHICH packages a module uses, look up each
package's `Requires-Python` from its `.dist-info/METADATA`. The highest
min among the module's actual deps = that module's dep floor.

### Implementation

```
module_intel.py — compute_dependency_floor():

  1. Scan module directory for import statements
     - Read .py files, extract "import X" and "from X import Y"
     - Map import names to package names (import mapping)

  2. For each imported package, look up Requires-Python
     - Read {package}.dist-info/METADATA from site-packages
     - Extract Requires-Python header
     - Parse floor version

  3. Return highest floor among module's actual deps

  Different modules import different packages → different dep floors:
    core imports: pydantic, yaml, click → dep floor from these
    web imports: flask, cryptography, jinja2 → dep floor from these
    cli imports: click → dep floor from click
    adapters imports: subprocess stuff → minimal deps
```

---

## Fix 2: Code floor with __future__ awareness

### The problem

The scanner detects `X | Y` union types as 3.10+ features. But with
`from __future__ import annotations`, union types in annotations are
just strings — they work on 3.7+. The scanner overcounts.

Real code floors (verified by exploration):
- src/core: **3.9+** — 7 files use `list[X]` at RUNTIME without __future__
- src/ui/web: **3.7+** — all modern syntax gated by __future__
- src/ui/cli: **3.7+** — all modern syntax gated by __future__
- src/adapters: **3.7+** — all modern syntax gated by __future__

### The solution

For each .py file:
1. Check if `from __future__ import annotations` is present
2. If YES: union types `X | Y` in type hints DON'T count as 3.10+
   (they're deferred annotations, work on 3.7+)
3. If YES: `list[X]`, `dict[X]` in type hints DON'T count as 3.9+
   UNLESS they appear in runtime positions (variable assignments,
   function bodies, default values)
4. If NO: all features count at their version level

### Implementation

```
module_intel.py — compute_code_floor():

  For each .py file in module:
    has_future = check for "from __future__ import annotations"

    If has_future:
      - Union types in annotations → 3.7+ (not 3.10+)
      - list[X] in annotations → 3.7+ (not 3.9+)
      - list[X] in RUNTIME code → still 3.9+
      - walrus := → still 3.8+
      - match/case → still 3.10+
      - except* → still 3.11+

    If NOT has_future:
      - All features count at their version level

    Track highest per file, highest per module
```

---

## Fix 3: Import-to-package mapping

To map `import flask` → package name `flask` → dist-info lookup:

Most packages: import name = package name (flask, click, pydantic)
Some differ: `import yaml` → package `pyyaml`, `import cv2` → package `opencv-python`

### Implementation

```
Build mapping from site-packages:
  For each .dist-info directory:
    Read top_level.txt (lists import names)
    Read RECORD (lists installed files)
    Map: import_name → package_name

  Common mappings needed:
    yaml → pyyaml
    dotenv → python-dotenv
    PIL → Pillow
    cv2 → opencv-python

  For unknown mappings: fall back to import_name == package_name
```

---

## Fix 4: UI matches the plan visual exactly

### Floor health column

The plan shows JUST the emoji (🟢, 🟡, 🔴) + 📝 if noted.
NOT the detail text. The detail text goes in Floor Advisories section only.

### Status column

Shows verdict icons: ✅ consistent, ⚠️ gap, ℹ️ could_lower
Tooltip on hover shows the detail.

### N/A row

`docs` shows in the table with `markdown` stack and dashes for all value columns.
Not filtered out. Not a separate section.

### Strategy row

Below the table. Compact. One line with all modules.

---

## Execution order

```
  Step 1: Fix code floor (__future__ awareness)
  ──────────────────────────────────────────────
  File: module_intel.py — compute_code_floor()
  - Check for __future__ import per file
  - Adjust feature detection accordingly
  - Runtime list[X] without __future__ → 3.9+
  - Annotations with __future__ → 3.7+ (not 3.9/3.10)

  Step 2: Fix dependency floor (per-module imports)
  ──────────────────────────────────────────────
  File: module_intel.py — compute_dependency_floor()
  - Scan module .py files for import statements
  - Build import → package name mapping from dist-info
  - Look up Requires-Python per package the module actually imports
  - Return highest floor among module's actual deps

  Step 3: Fix UI to match plan visual
  ──────────────────────────────────────────────
  File: _system_posture.html — renderModulePillar()
  - Floor column: emoji only, no detail text
  - Status column: verdict icon with tooltip
  - N/A row: in table, not filtered
  - Strategy row: compact, one line
  - Verify 9 columns match plan exactly

  Step 4: Verify per-module differentiation
  ──────────────────────────────────────────────
  After steps 1-3, verify:
  - core shows different code floor than web (3.9 vs 3.7)
  - web shows different deps floor than core (flask deps vs pydantic deps)
  - Each module has its own effective floor and verdict
  - Table shows real differentiation, not identical rows
```
