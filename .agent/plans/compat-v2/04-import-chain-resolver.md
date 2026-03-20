# 04 — Import Chain Resolver Design

> **Document**: 4 of 37
> **Milestone**: M3 — Import chain resolution
> **Status**: Draft

---

## 1. Purpose

The import chain resolver answers one question: **when a module imports code, what does it actually pull in?**

This is the component that was entirely missing in v1. The v1 system analyzed `src/ui/web` in isolation. It never knew that `src/ui/web/routes/backup/archive.py` imports `src/core/models/action.py` which imports `from datetime import UTC`. The web module's tests failed because of code in a completely different module that the scanner never looked at.

The import chain resolver builds a complete graph of what imports what, across the entire project. It doesn't FIX anything — it INFORMS the detection engine about transitive dependencies so the analysis result can tell the user: "your module depends on 14 files in `src/core` that use `datetime.UTC`."

The fix still stays within the module's own files. But the user KNOWS about the transitive problems and can make informed decisions — fix the dependency module first, or accept the transitive failure.

---

## 2. Import Graph Model

### 2.1 Nodes and edges

```python
@dataclass
class ImportNode:
    """A file in the import graph."""
    file_path: str              # Relative to project root: "src/core/models/action.py"
    module_path: str            # Python import path: "src.core.models.action"
    language: str               # "python", "javascript", etc.
    belongs_to_module: str      # Which project module this file belongs to: "core", "web"
    is_entry_point: bool        # True if this file is directly in the analyzed module

@dataclass
class ImportEdge:
    """A directed edge: source imports target."""
    source: str                 # File that does the importing
    target: str                 # File being imported
    import_type: str            # Language-specific import type
                                # Python: "import", "from_import", "from_import_star", "dynamic"
                                # JS: "import", "require", "dynamic_import"
                                # Go: "import"
                                # etc.
    names_imported: list[str]   # Specific names imported: ["UTC", "datetime"]
                                # Empty for "import module" or "import *"
    line: int                   # Line number of the import statement
    is_conditional: bool        # True if inside try/except, if block, etc.
    is_type_only: bool          # True if inside TYPE_CHECKING block or TS "import type"

@dataclass
class ImportGraph:
    """Complete import dependency graph."""
    nodes: dict[str, ImportNode]    # file_path → node
    edges: list[ImportEdge]         # All import edges
    root_module: str                # The module being analyzed
    project_root: str               # Absolute path to project root
```

### 2.2 Graph operations

```python
class ImportGraph:

    def direct_imports(self, file_path: str) -> list[ImportEdge]:
        """What does this file directly import?"""

    def direct_importers(self, file_path: str) -> list[ImportEdge]:
        """What files directly import this file?"""

    def transitive_imports(self, file_path: str, max_depth: int = 50) -> list[str]:
        """All files reachable by following imports from this file.
        Handles cycles by tracking visited nodes."""

    def transitive_importers(self, file_path: str, max_depth: int = 50) -> list[str]:
        """All files that transitively import this file."""

    def files_in_module(self, module_name: str) -> list[str]:
        """All files belonging to a specific project module."""

    def cross_module_edges(self) -> list[ImportEdge]:
        """All edges where source and target belong to different modules."""

    def dependency_modules(self, module_name: str) -> list[str]:
        """Which other project modules does this module depend on?"""

    def has_cycle(self) -> bool:
        """Does the graph contain any import cycles?"""

    def cycles(self) -> list[list[str]]:
        """Return all import cycles as lists of file paths."""

    def topological_order(self) -> list[str] | None:
        """Return files in topological order, or None if cycles exist."""
```

---

## 3. Resolution Per Language

### 3.1 Python Import Resolution

Python has the most complex import system of the supported languages.

**Import forms:**

| Form | Example | Resolution |
|------|---------|------------|
| `import X` | `import os` | Resolve `X` as module |
| `import X.Y` | `import os.path` | Resolve `X.Y` as module |
| `from X import Y` | `from datetime import UTC` | Resolve `X` as module, `Y` as name in that module |
| `from X import *` | `from os.path import *` | Resolve `X`, import ALL public names |
| `from . import X` | `from . import utils` | Relative import — resolve relative to current package |
| `from .X import Y` | `from .models import User` | Relative import with name |
| `from .. import X` | `from .. import config` | Parent package relative import |
| `importlib.import_module(X)` | `importlib.import_module("foo")` | Dynamic — resolve if string is literal |

**Resolution algorithm:**

```
Given: "from src.core.models.action import Action"
In file: "src/ui/web/routes/backup/archive.py"

1. Split module path: ["src", "core", "models", "action"]
2. Search order:
   a. project_root / src / core / models / action.py → EXISTS → resolved
   b. project_root / src / core / models / action / __init__.py → check if package
3. Result: ImportEdge(
     source="src/ui/web/routes/backup/archive.py",
     target="src/core/models/action.py",
     import_type="from_import",
     names_imported=["Action"],
     line=5,
     is_conditional=False,
     is_type_only=False,
   )
```

**Relative import resolution:**

```
Given: "from .models import User"
In file: "src/ui/web/routes/backup/archive.py"
Package: "src/ui/web/routes/backup/"

1. "." means current package: "src/ui/web/routes/backup/"
2. ".models" → "src/ui/web/routes/backup/models.py" or "src/ui/web/routes/backup/models/__init__.py"
3. Resolve accordingly
```

**What we DON'T resolve (out of scope):**

- Standard library imports (`import os`, `import sys`) — these are part of Python, not the project
- Third-party package imports (`import flask`, `import requests`) — handled by dep_analyzer instead
- Dynamic imports where the module name is a variable (`importlib.import_module(config.module)`)

**How we distinguish project vs stdlib vs third-party:**

```
1. Does the import path start with a directory in project_root/src/ ? → project import
2. Does the import path match an installed package in the venv? → third-party
3. Otherwise → stdlib or unknown (skip)
```

**Conditional imports:**

```python
try:
    from foo import bar          # Conditional — might not exist
except ImportError:
    bar = None
```

Detected by checking if the `import` AST node's parent is a `Try` node with an `ImportError` handler. Marked as `is_conditional=True`.

**TYPE_CHECKING imports:**

```python
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from src.core.models import HeavyModel    # Only for type hints, never executes
```

Detected by checking if the `import` is inside an `if TYPE_CHECKING:` block. Marked as `is_type_only=True`. These imports do NOT cause runtime incompatibilities.

### 3.2 JavaScript / TypeScript Import Resolution

**Import forms:**

| Form | Example | Resolution |
|------|---------|------------|
| `import X from 'Y'` | `import React from 'react'` | Resolve Y |
| `import { X } from 'Y'` | `import { useState } from 'react'` | Resolve Y, extract names |
| `import * as X from 'Y'` | `import * as path from 'path'` | Resolve Y |
| `require('Y')` | `const fs = require('fs')` | Resolve Y (CommonJS) |
| `import('Y')` | `const mod = await import('./lazy')` | Dynamic import |
| `export { X } from 'Y'` | `export { helper } from './utils'` | Re-export |

**Resolution algorithm:**

```
Given: import { helper } from './utils'
In file: src/ui/web/routes/api.ts

1. Relative path: './utils'
2. Base directory: src/ui/web/routes/
3. Try in order:
   a. src/ui/web/routes/utils.ts
   b. src/ui/web/routes/utils.tsx
   c. src/ui/web/routes/utils.js
   d. src/ui/web/routes/utils.jsx
   e. src/ui/web/routes/utils/index.ts
   f. src/ui/web/routes/utils/index.js
4. First match → resolved
```

**Distinguishing project vs node_modules:**
- Starts with `.` or `..` → project-relative
- Starts with `@scope/` or bare name → node_modules (skip, handled by dep_analyzer)
- Matches a path alias in `tsconfig.json` → resolve via alias

### 3.3 Go Import Resolution

Go has the simplest import system.

**Import form:**

```go
import (
    "fmt"
    "github.com/user/repo/pkg/utils"
    "./internal/helper"
)
```

**Resolution:**
- Standard library (`"fmt"`, `"os"`) → skip
- Module path matching `go.mod` module → project import, resolve to file
- External module → skip, handled by dep_analyzer

### 3.4 Rust Import Resolution

**Import forms:**

```rust
use std::collections::HashMap;       // std — skip
use crate::models::User;             // project — crate root
use super::utils::helper;            // project — parent module
use my_crate::Config;                // external — skip
```

**Resolution:**
- `std::` / `core::` / `alloc::` → stdlib, skip
- `crate::` → resolve from crate root (Cargo.toml location)
- `super::` → resolve from parent module
- `self::` → resolve from current module
- Other → external crate, skip

### 3.5 Ruby Import Resolution

```ruby
require 'json'                      # stdlib or gem — context-dependent
require_relative './helper'          # project-relative
require_relative '../models/user'   # project-relative
load 'config.rb'                    # dynamic load
```

**Resolution:**
- `require_relative` → resolve relative to current file
- `require` with path starting with `.` → project-relative
- `require` with bare name → gem or stdlib, skip

### 3.6 Java Import Resolution

```java
import java.util.List;                      // stdlib — skip
import com.myproject.models.User;           // project — resolve via package path
import static com.myproject.utils.Helper.*; // static import
```

**Resolution:**
- `java.` / `javax.` → stdlib, skip
- Matches project's package structure → resolve to .java file
- Otherwise → external dependency, skip

### 3.7 C# Import Resolution

```csharp
using System;                               // framework — skip
using MyProject.Models;                     // project — resolve via namespace
using static MyProject.Utils.Helper;        // static using
```

**Resolution:**
- `System.` → framework, skip
- Matches project's namespace structure → resolve to .cs file
- Otherwise → NuGet package, skip

### 3.8 PHP Import Resolution

```php
use App\Models\User;                        // project — resolve via PSR-4
use Illuminate\Http\Request;                // external — skip
require_once __DIR__ . '/helper.php';       // file include
```

**Resolution:**
- PSR-4 autoloading: namespace → directory mapping from `composer.json`
- `require`/`include` with `__DIR__` → resolve relative path
- External namespace → skip

### 3.9 Elixir Import Resolution

```elixir
alias MyApp.Models.User                     # project — resolve via module name
import MyApp.Helpers                        # project — resolve via module name
use GenServer                               # OTP — skip
```

**Resolution:**
- Module name matching project's `lib/` structure → resolve to .ex file
- OTP / Elixir stdlib → skip
- External dependency → skip

---

## 4. Graph Building

### 4.1 Build process

```python
class ImportResolver:
    """Build import graph for a module."""

    def __init__(self, backend: LanguageBackend, project_root: Path):
        self._backend = backend
        self._project_root = project_root

    def build_graph(
        self,
        module_dir: Path,
        language: str,
        follow_transitive: bool = True,
        max_depth: int = 50,
    ) -> ImportGraph:
        """Build the complete import graph starting from a module.

        1. Find all source files in module_dir
        2. Parse each file's imports using the language backend
        3. Resolve each import to a file path
        4. If follow_transitive, recursively process imported files
           (but only for project-internal imports, not stdlib/third-party)
        5. Return the complete graph

        Handles circular imports by tracking visited files.
        """

    def _resolve_import(
        self,
        import_statement: RawImport,
        source_file: Path,
    ) -> str | None:
        """Resolve an import statement to a file path.

        Returns None if the import is stdlib, third-party, or unresolvable.
        """
```

### 4.2 Build algorithm

```
Input: module_dir = "src/ui/web", language = "python"

queue = [all .py files in src/ui/web/]
visited = set()
graph = ImportGraph()

while queue is not empty:
    file = queue.pop()
    if file in visited:
        continue
    visited.add(file)

    # Determine which module this file belongs to
    module_name = determine_module(file, project_root)

    # Add node
    graph.add_node(ImportNode(
        file_path=file,
        module_path=to_module_path(file),
        language=language,
        belongs_to_module=module_name,
        is_entry_point=(module_name == root_module),
    ))

    # Parse imports
    raw_imports = backend.resolve_imports(file, project_root)

    for raw_import in raw_imports:
        resolved = resolve_import(raw_import, file)
        if resolved is None:
            continue  # stdlib or third-party

        # Add edge
        graph.add_edge(ImportEdge(
            source=file,
            target=resolved,
            import_type=raw_import.type,
            names_imported=raw_import.names,
            line=raw_import.line,
            is_conditional=raw_import.is_conditional,
            is_type_only=raw_import.is_type_only,
        ))

        # Follow transitive imports
        if follow_transitive and resolved not in visited:
            queue.append(resolved)

return graph
```

### 4.3 Module ownership

Every file in the project belongs to a module (as defined in project.yml). The resolver needs to know this to:
- Distinguish "direct" vs "transitive" findings
- Show which dependency modules need fixing
- Respect module boundaries for fixes

```python
def determine_module(file_path: str, project_modules: list[Module]) -> str:
    """Determine which project module a file belongs to.

    Matches the file path against module paths from project.yml.
    Example:
      file_path = "src/core/models/action.py"
      modules = [{name: "core", path: "src/core"}, {name: "web", path: "src/ui/web"}]
      → returns "core"
    """
    for module in sorted(project_modules, key=lambda m: len(m.path), reverse=True):
        if file_path.startswith(module.path):
            return module.name
    return "unknown"
```

---

## 5. Using the Graph for Analysis

### 5.1 Transitive finding enrichment

When the detection engine finds an incompatibility in a file that's NOT in the analyzed module, it's a transitive finding:

```python
def enrich_findings(findings: list[Finding], graph: ImportGraph, module_name: str) -> None:
    """Mark findings as transitive and add import chain info."""
    module_files = set(graph.files_in_module(module_name))

    for finding in findings:
        if finding.file not in module_files:
            finding.is_transitive = True
            # Find the shortest import chain from module to this file
            chain = graph.shortest_path(
                from_files=module_files,
                to_file=finding.file,
            )
            if chain:
                finding.imported_by = chain[0]  # The module file that starts the chain
                finding.import_chain = chain     # Full chain for display
```

### 5.2 Analysis result with graph

```
Module: web (src/ui/web)
Target: Python 3.8
Direction: downgrade

Direct findings (in src/ui/web):
  ❌ src/ui/web/routes/metrics/health.py:6 — from datetime import UTC (3.11+)

Transitive findings (in dependencies):
  ❌ src/core/models/action.py:11 — from datetime import UTC (3.11+)
     ↳ imported by: src/ui/web/routes/backup/archive.py → src/core/models/action
  ❌ src/core/models/state.py:14 — from datetime import UTC (3.11+)
     ↳ imported by: src/ui/web/routes/backup/ops.py → src/core/models/state
  ... 12 more in src/core/

Dependency modules needing fixes:
  ⚠️ core (src/core): 14 incompatible features — fix core's plan first

Direct fixes available: 1 file
Transitive fixes needed: fix "core" module first (14 files)
```

### 5.3 Module dependency ordering

When multiple modules need version plans, the resolver can determine the correct order:

```python
def module_fix_order(graph: ImportGraph, modules_with_plans: list[str]) -> list[str]:
    """Determine the order in which modules should be fixed.

    Modules that are imported by others should be fixed FIRST.
    Example: core → cli, core → web
    Fix order: core, then cli and web (can be parallel)
    """
```

---

## 6. Cycle Handling

Import cycles are common in real codebases:

```
src/core/models/action.py imports src/core/engine/executor.py
src/core/engine/executor.py imports src/core/models/action.py
```

### 6.1 Detection

```python
def find_cycles(graph: ImportGraph) -> list[list[str]]:
    """Find all import cycles using DFS with back-edge detection."""
```

### 6.2 Handling during resolution

Cycles are NOT errors — they're common Python patterns. The resolver handles them by:
1. Tracking visited files in the BFS/DFS
2. When encountering a visited file, add the edge but don't re-process the file
3. Record the cycle for informational purposes

### 6.3 Handling during analysis

Cycles don't affect detection — the detection engine processes each file independently. The cycle information is useful for:
- Warning the user about circular dependencies
- Understanding why a fix in file A might affect file B and vice versa

---

## 7. Performance

### 7.1 Graph size

| Project size | Files | Edges | Build time |
|-------------|-------|-------|------------|
| Small (1 module) | 50 | 200 | <100ms |
| Medium (5 modules) | 500 | 2,000 | <500ms |
| Large (20 modules) | 5,000 | 20,000 | <2s |
| Very large | 50,000 | 200,000 | ~10s |

### 7.2 Optimization strategies

- **Lazy resolution**: Only follow imports from the analyzed module, not the entire project
- **Cached graphs**: Cache the graph per module, invalidate when files change
- **Parallel resolution**: Parse imports from multiple files in parallel (Python's `ast.parse` releases the GIL)
- **Incremental updates**: When a file changes, update only its edges instead of rebuilding the full graph

---

## 8. Integration Points

### 8.1 With Detection Engine (Document 03)
- Detection engine calls `resolver.build_graph(module_dir, language)`
- Passes the graph to `analyze_transitive()`
- Graph is used to enrich findings with `is_transitive` and `imported_by`

### 8.2 With Fix Engine (Document 05)
- Fix engine respects module boundaries — only fixes files in the target module
- Uses graph to show the user which OTHER modules also need fixing
- After fixing a file, can re-check if transitive findings are resolved

### 8.3 With Project-Wide Analysis (Document 08)
- Project-wide analysis builds graphs for ALL modules
- Computes the module dependency order
- Generates a project-wide compatibility report

### 8.4 With Lifecycle (Document 06)
- When a step depends on another module being fixed first → state = BLOCKED
- Block message: "Fix module 'core' first — 14 transitive incompatibilities"
- When the blocking module's plan completes → unblock
