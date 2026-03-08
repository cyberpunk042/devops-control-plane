# Scripts System — Milestone 2: Shared Libraries

> **Status**: Planning — Iteration 1
> **Parent**: `.agent/plans/scripts-system.md`
> **Milestone**: M2 — Shared Libraries (Lib Modules)
> **Depends on**: M1 (Script Execution Framework)
> **Unlocks**: M3 (Class Diagram Script), M5 (Route Quality Audit), M6 (Code Hygiene Audit)

---

## 0. What This Milestone Delivers

After M2 is complete:

1. A **Python code analyzer** exists — independent AST extraction optimized for structural relationships (inheritance, composition, field types, method signatures). Uses `ast.parse()` directly, does NOT wrap the audit parser.
2. A **Graph builder** exists — constructs relationship graphs (nodes + edges) from parsed code data
3. A **Mermaid generator** exists — converts graphs into Mermaid syntax (class diagrams, flowcharts, component graphs)
4. A **Report formatter** exists — renders structured analysis results into markdown, JSON, or HTML reports
5. A **File discovery** module exists — walks directories with configurable filters, returns file lists

These are **library modules** — they have no knowledge of the script system's execution framework. They are imported by scripts the same way you'd import any other module. They live in the template scripts directory as a shared lib, accessible to all scripts.

**What you can do after M2**: A script can import these modules and use them to:
- Parse all Python files in a project → extract class definitions, methods, fields, inheritance
- Build a relationship graph showing which classes depend on which other classes
- Render that graph as Mermaid syntax for class diagrams
- Format the results as a markdown or JSON report
- Save the report to the output directory

---

## 1. Why Shared Libraries

### 1.1 The Problem They Solve

Without shared libs, every script reimplements the same things:
- "Parse Python files" → each script does its own AST walking
- "Output as Mermaid" → each script writes its own Mermaid syntax
- "Format as markdown report" → each script builds strings differently
- "Find Python files" → each script has its own glob/walk logic

This leads to:
- Duplication (same code in 5 scripts)
- Inconsistency (each script formats graphs slightly differently)
- Bugs multiply (fix AST parsing in one script, forget the other 4)

### 1.2 The Design Principle

**Pipeline pattern**: Parser → Graph → Renderer → Output

Each script is a pipeline that:
1. **Discovers** files (file_discovery)
2. **Parses** them (code_analyzer — which wraps the existing audit parser)
3. **Builds** a graph or intermediate structure (graph_builder)
4. **Renders** the structure to a format (mermaid_generator, report_formatter)
5. **Writes** the output (uses SCRIPT_OUTPUT_DIR from M1)

The shared lib provides steps 1–4. Step 5 is trivial (write to file).

---

## 2. Existing Infrastructure We Reuse

### 2.1 The Audit Python Parser

**File**: `src/core/services/audit/parsers/python_parser.py`

This already provides:
- `parse_file(path)` → `FileAnalysis` with imports, symbols, metrics
- `parse_tree(root)` → `dict[path, FileAnalysis]` for all .py files
- `SymbolInfo` with: name, kind, lineno, decorators, has_docstring, num_args, methods list
- `ImportInfo` with: module, names, is_internal, is_stdlib, is_relative
- `FileMetrics` with: lines, complexity, nesting depth, class/function counts

**What it does NOT provide** (and M2 needs to add):
- Base classes / inheritance relationships (what class X inherits from)
- Field definitions (instance variables, class variables, their types)
- Composition relationships (class X has a field of type Y)
- Association strengths (dependency, composition, aggregation)
- Cross-file relationship building (class in file A inherits from class in file B)

### 2.2 The Content Outline Extractor

**File**: `src/core/services/content/outline.py`

This already has `PythonOutlineStrategy` which uses `ast.parse()` to extract classes, functions, methods. This is a simpler extraction than the audit parser — the audit parser is more comprehensive.

### 2.3 The Data Layer

**Directory**: `src/core/data/`

Contains `catalogs/`, `templates/`, `patterns/`. The shared lib for scripts goes in `src/core/data/script_templates/lib/` — a dedicated shared library directory within the template scripts area.

---

## 3. Architecture — Where the Lib Lives

### 3.1 Why Not `src/core/services/scripts/lib/`

The service package (`scripts/`) is for the execution framework — it manages discovery, execution, output routing. It should not contain library code that scripts import.

### 3.2 Why `src/core/data/script_templates/lib/`

The lib modules are **part of the script templates ecosystem**. They are:
- Shipped with the program (not user-editable)
- Used by template scripts AND root scripts
- Independent of the execution framework (no import of registry, executor, etc.)

```
src/core/data/script_templates/
├── lib/                           ← Shared lib modules (M2)
│   ├── __init__.py
│   ├── code_analyzer.py           ← Python code analysis (wraps audit parser)
│   ├── graph_builder.py           ← Relationship graph construction
│   ├── mermaid_generator.py       ← Mermaid syntax generation
│   ├── report_formatter.py        ← Report output formatting
│   └── file_discovery.py          ← File walking and filtering
├── audit/                         ← Audit script templates (M5+)
├── generators/                    ← Generator templates (M3+)
└── debug/                         ← Debug templates (later)
```

### 3.3 How Scripts Import the Lib

Scripts are executed as subprocesses (via `stream_run()`). They run in the project venv's Python. The lib is importable because the program's source tree is on the Python path:

```python
# In a script file:
from src.core.data.script_templates.lib.code_analyzer import analyze_python_project
from src.core.data.script_templates.lib.mermaid_generator import render_class_diagram
from src.core.data.script_templates.lib.report_formatter import markdown_report
```

This works because:
- `sys.executable` is the project venv's Python
- The project root is on `sys.path` (or the script is invoked with `-m`)
- The lib is part of the installed package

---

## 4. Module Specifications

### 4.1 `code_analyzer.py` — Python Code Analysis

**Purpose**: Extract class-diagram–relevant data from Python source files. Wraps the existing audit parser and adds relationship extraction.

**Key distinction**: The audit parser extracts symbols + metrics for quality scoring. The code analyzer extracts **structural relationships** for diagram generation. Different question, overlapping data source.

```python
# src/core/data/script_templates/lib/code_analyzer.py

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class FieldInfo:
    """A class field (instance or class variable).
    
    Extracted from:
    - Type annotations in __init__: self.name: Type = value
    - Class-level annotations: name: Type
    - Simple assignments: self.name = value (type inferred as "Any")
    """
    name: str
    type_annotation: str = "Any"       # Type annotation or "Any" if untyped
    is_class_var: bool = False          # True for class-level, False for instance
    visibility: str = "public"          # "public" | "protected" | "private"
                                        # Derived from _ / __ prefix


@dataclass
class MethodInfo:
    """A method in a class.
    
    Mirrors SymbolInfo from the audit parser but simplified
    for diagram use — no metrics, just signature data.
    """
    name: str
    is_async: bool = False
    is_static: bool = False            # @staticmethod
    is_classmethod: bool = False       # @classmethod
    is_property: bool = False          # @property
    is_abstract: bool = False          # @abstractmethod
    visibility: str = "public"         # "public" | "protected" | "private"
    parameters: list[str] = field(default_factory=list)   # Parameter names (no self/cls)
    return_type: str = ""              # Return type annotation if present
    decorators: list[str] = field(default_factory=list)


@dataclass
class ClassInfo:
    """Complete class information for diagram generation.
    
    Aggregates:
    - Identity (name, qualified path, source file)
    - Inheritance (base classes)
    - Fields (instance + class variables)
    - Methods (with visibility and decorator info)
    """
    name: str
    qualified_name: str = ""           # e.g., "src.core.services.event_bus.EventBus"
    file_path: str = ""                # Relative path to source file
    module: str = ""                   # Python module path
    
    bases: list[str] = field(default_factory=list)
                                        # Base class names as written in source
                                        # e.g., ["BaseModel"], ["ABC", "Generic[T]"]
    
    fields: list[FieldInfo] = field(default_factory=list)
    methods: list[MethodInfo] = field(default_factory=list)
    
    is_abstract: bool = False          # Has ABC or @abstractmethod
    is_dataclass: bool = False         # @dataclass decorator
    is_pydantic: bool = False          # Inherits BaseModel
    is_protocol: bool = False          # Inherits Protocol
    
    decorators: list[str] = field(default_factory=list)
    docstring: str = ""                # First line of docstring (summary)
    
    lineno: int = 0
    end_lineno: int = 0


@dataclass
class ProjectAnalysis:
    """Complete project analysis result.
    
    Contains all classes discovered and their relationships.
    This is the input to the graph builder.
    """
    classes: list[ClassInfo] = field(default_factory=list)
    files_analyzed: int = 0
    files_with_errors: int = 0
    total_classes: int = 0
    analysis_errors: list[str] = field(default_factory=list)


def analyze_python_project(
    project_root: Path,
    *,
    source_dir: str = "src",
    exclude_patterns: tuple[str, ...] = (
        "__pycache__", ".venv", "venv", "node_modules",
        ".git", ".tox", ".mypy_cache", ".pytest_cache",
        "build", "dist", ".eggs",
    ),
    include_private: bool = False,
) -> ProjectAnalysis:
    """Analyze a Python project and extract class information.
    
    This is the main entry point for the code analyzer.
    
    Steps:
    1. Walk the source tree for .py files
    2. For each file, AST-parse and extract ClassInfo
    3. For each class, extract fields, methods, inheritance
    4. Return ProjectAnalysis with all classes
    
    Args:
        project_root: Project root directory
        source_dir: Source directory to scan (relative to root)
        exclude_patterns: Directory names to skip
        include_private: Include _private classes
    
    Returns:
        ProjectAnalysis with all discovered classes.
    """


def analyze_file(path: Path, project_root: Path) -> list[ClassInfo]:
    """Analyze a single Python file for class information.
    
    Uses ast.parse() directly. Does NOT import the audit parser —
    the code analyzer has its own AST walking because it extracts
    different data (fields, base classes, composition) that the
    audit parser doesn't provide.
    
    The audit parser is optimized for quality metrics.
    The code analyzer is optimized for structural relationships.
    Both use ast — neither executes the code.
    """


def _extract_class(
    node: ast.ClassDef,
    module_path: str,
    file_path: str,
) -> ClassInfo:
    """Extract ClassInfo from a ClassDef AST node.
    
    Extracts:
    - Base classes from node.bases
    - Fields from __init__ self.x assignments and class-level annotations
    - Methods from FunctionDef children
    - Decorators from decorator_list
    - Abstract/dataclass/pydantic/protocol detection
    """


def _extract_fields(node: ast.ClassDef) -> list[FieldInfo]:
    """Extract fields from a class.
    
    Sources:
    1. Class-level annotations: `name: Type` or `name: Type = value`
    2. __init__ body: `self.name = value` or `self.name: Type = value`
    3. Dataclass fields: field(default=..., default_factory=...)
    
    Visibility from naming:
    - __name → private
    - _name  → protected
    - name   → public
    """


def _extract_methods(node: ast.ClassDef) -> list[MethodInfo]:
    """Extract methods from a class.
    
    For each FunctionDef/AsyncFunctionDef child:
    - Name and visibility
    - Parameters (excluding self/cls)
    - Return type annotation
    - Decorator detection (property, staticmethod, classmethod, abstractmethod)
    """


def _extract_bases(node: ast.ClassDef) -> list[str]:
    """Extract base class names from a ClassDef.
    
    Handles:
    - Simple names: class Foo(Bar) → ["Bar"]
    - Dotted names: class Foo(abc.ABC) → ["abc.ABC"]
    - Generic: class Foo(Generic[T]) → ["Generic[T]"]
    - Multiple: class Foo(Bar, Baz) → ["Bar", "Baz"]
    
    Returns names as-written (unresolved). Resolution to full
    qualified names happens in the graph builder using import data.
    """
```

### 4.2 `graph_builder.py` — Relationship Graph Construction

**Purpose**: Build relationship graphs from analyzed code. A graph is nodes + edges where:
- **Nodes** = Classes (or modules, or files — depending on diagram type)
- **Edges** = Relationships (inheritance, composition, dependency, uses)

```python
# src/core/data/script_templates/lib/graph_builder.py

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class RelationType(Enum):
    """Types of relationships between classes."""
    INHERITS = "inherits"              # A extends B (solid line, closed arrow)
    IMPLEMENTS = "implements"          # A implements B (dashed line, closed arrow)
    COMPOSES = "composes"              # A has-a B (solid line, filled diamond)
    AGGREGATES = "aggregates"          # A contains B (solid line, open diamond)
    DEPENDS = "depends"                # A uses B (dashed line, open arrow)
    ASSOCIATES = "associates"          # A knows B (solid line, open arrow)


@dataclass
class GraphNode:
    """A node in the relationship graph.
    
    Typically represents a class, but can also represent
    a module or a package depending on the graph type.
    """
    id: str                            # Unique identifier (qualified class name)
    label: str                         # Display label (short class name)
    kind: str = "class"                # "class" | "abstract" | "interface" | "dataclass" | "module"
    package: str = ""                  # Grouping key (module/package path)
    
    fields: list[str] = field(default_factory=list)
                                       # Field declarations for display
                                       # e.g., ["- name: str", "+ value: int"]
    methods: list[str] = field(default_factory=list)
                                       # Method declarations for display
                                       # e.g., ["+ run()", "- _validate()"]
    
    metadata: dict = field(default_factory=dict)
                                       # Additional data (file, lines, etc.)


@dataclass
class GraphEdge:
    """A directed edge in the relationship graph."""
    source: str                        # Source node ID
    target: str                        # Target node ID
    relation: RelationType             # Type of relationship
    label: str = ""                    # Optional edge label
    cardinality: str = ""              # Optional cardinality ("1", "*", "0..1", etc.)


@dataclass
class ClassGraph:
    """A complete relationship graph.
    
    Contains nodes (classes) and edges (relationships).
    This is the intermediate representation between code analysis
    and diagram rendering.
    """
    nodes: dict[str, GraphNode] = field(default_factory=dict)
    edges: list[GraphEdge] = field(default_factory=list)
    title: str = ""
    scope: str = ""                    # What was analyzed (package, file, project)
    
    def add_node(self, node: GraphNode) -> None:
        """Add a node to the graph."""
        self.nodes[node.id] = node
    
    def add_edge(self, edge: GraphEdge) -> None:
        """Add an edge to the graph. Deduplication by (source, target, relation)."""
        key = (edge.source, edge.target, edge.relation)
        # Don't add duplicate edges
        for existing in self.edges:
            if (existing.source, existing.target, existing.relation) == key:
                return
        self.edges.append(edge)
    
    def filter_by_package(self, package: str) -> ClassGraph:
        """Return a subgraph containing only nodes in the given package."""
    
    def get_connected_components(self) -> list[list[str]]:
        """Return connected components (groups of related classes)."""
    
    def get_orphan_nodes(self) -> list[str]:
        """Return nodes with no edges (standalone classes)."""


def build_class_graph(
    analysis: ProjectAnalysis,
    *,
    include_external: bool = False,
    include_stdlib: bool = False,
    scope: str | None = None,
) -> ClassGraph:
    """Build a class relationship graph from project analysis.
    
    Steps:
    1. Create a GraphNode for each ClassInfo
    2. Resolve inheritance → INHERITS edges
    3. Detect composition (fields of class types) → COMPOSES edges
    4. Detect dependencies (used in method bodies) → DEPENDS edges
    5. Group by package for visual layout
    
    Args:
        analysis: Output from code_analyzer.analyze_python_project()
        include_external: Include external library classes (e.g., BaseModel)
        include_stdlib: Include stdlib classes (e.g., ABC)
        scope: Limit to a specific package (e.g., "core.services.vault")
    
    Returns:
        ClassGraph ready for rendering.
    """


def _resolve_inheritance(
    classes: dict[str, ClassInfo],
    graph: ClassGraph,
) -> None:
    """Resolve inheritance relationships.
    
    For each class's bases:
    1. Try exact match in classes dict (same name)
    2. Try qualified match (import resolution)
    3. If unresolved and include_external, create a stub node
    4. Otherwise skip (external class not in scope)
    
    Edge type:
    - If base is ABC or Protocol → IMPLEMENTS
    - Otherwise → INHERITS
    """


def _detect_composition(
    classes: dict[str, ClassInfo],
    graph: ClassGraph,
) -> None:
    """Detect composition relationships from field types.
    
    For each class's fields:
    1. Check if type_annotation refers to another analyzed class
    2. If yes → COMPOSES edge (A has-a B)
    3. Handle common patterns:
       - list[ClassName] → aggregation (0..*)
       - Optional[ClassName] → association (0..1)
       - ClassName → composition (1)
    """


def _detect_dependencies(
    classes: dict[str, ClassInfo],
    graph: ClassGraph,
) -> None:
    """Detect dependency relationships from method parameters and return types.
    
    For each class's methods:
    1. Check parameter types for references to other analyzed classes
    2. Check return types for references to other analyzed classes
    3. If found → DEPENDS edge (A uses B)
    
    This is weaker than composition — the class doesn't own the dependency,
    it just uses it temporarily.
    """
```

### 4.3 `mermaid_generator.py` — Mermaid Syntax Generation

**Purpose**: Convert graphs into Mermaid syntax. Supports multiple diagram types.

```python
# src/core/data/script_templates/lib/mermaid_generator.py

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MermaidConfig:
    """Configuration for Mermaid diagram generation."""
    
    direction: str = "TD"              # "TD" (top-down), "LR" (left-right), "BT", "RL"
    show_fields: bool = True           # Show class fields
    show_methods: bool = True          # Show class methods
    show_visibility: bool = True       # Show +/- visibility markers
    max_fields: int = 10               # Max fields to show per class (truncate)
    max_methods: int = 15              # Max methods to show per class (truncate)
    group_by_package: bool = True      # Group classes by package (subgraph)
    include_orphans: bool = False      # Include classes with no relationships
    theme: str = "default"             # Mermaid theme


def render_class_diagram(
    graph: ClassGraph,
    *,
    config: MermaidConfig | None = None,
) -> str:
    """Render a ClassGraph as a Mermaid class diagram.
    
    Output format:
    ```mermaid
    classDiagram
        direction TD
        
        namespace core_services {
            class EventBus {
                - _lock: Lock
                - _events: list
                + publish(type, key, data)
                + subscribe(since) Iterator
            }
        }
        
        EventBus --|> ABC : inherits
        ArtifactEngine ..> EventBus : uses
    ```
    
    Returns:
        Complete Mermaid block (without the ```mermaid fences).
    """


def render_flowchart(
    graph: ClassGraph,
    *,
    config: MermaidConfig | None = None,
) -> str:
    """Render a ClassGraph as a Mermaid flowchart.
    
    Simpler than class diagram — shows only relationships,
    no fields/methods. Good for dependency overview.
    
    Output format:
    ```mermaid
    graph TD
        EventBus --> StreamSubprocess
        RunTracker --> EventBus
        ScriptExecutor --> RunTracker
        ScriptExecutor --> StreamSubprocess
    ```
    """


def render_component_diagram(
    packages: dict[str, list[str]],
    dependencies: list[tuple[str, str]],
) -> str:
    """Render a package-level component diagram.
    
    Shows packages (not individual classes) and their dependencies.
    Good for architectural overview.
    """


def _visibility_marker(visibility: str) -> str:
    """Convert visibility to Mermaid marker.
    
    "public"    → "+"
    "protected" → "#"
    "private"   → "-"
    """


def _escape_mermaid(text: str) -> str:
    """Escape special characters for Mermaid syntax.
    
    Characters that need escaping: < > { } | : " ~
    """


def _relation_arrow(relation: RelationType) -> str:
    """Convert RelationType to Mermaid arrow syntax.
    
    INHERITS    → "--|>"     (solid line, closed arrow)
    IMPLEMENTS  → "..|>"     (dashed line, closed arrow)
    COMPOSES    → "*--"      (solid line, filled diamond)
    AGGREGATES  → "o--"      (solid line, open diamond)
    DEPENDS     → "..>"      (dashed line, open arrow)
    ASSOCIATES  → "-->"      (solid line, open arrow)
    """


def _truncate_members(
    items: list[str],
    max_items: int,
    label: str = "more",
) -> list[str]:
    """Truncate a list of members with a '... N more' indicator."""
```

### 4.4 `report_formatter.py` — Report Output Formatting

**Purpose**: Format analysis results into consistent, readable reports.

```python
# src/core/data/script_templates/lib/report_formatter.py

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def markdown_report(
    *,
    title: str,
    summary: dict,
    sections: list[dict],
    metadata: dict | None = None,
) -> str:
    """Generate a markdown report.
    
    Args:
        title: Report title (becomes H1)
        summary: Key-value pairs for the summary section
        sections: List of {title, content} dicts
        metadata: Optional metadata (timestamp, script, version)
    
    Returns:
        Complete markdown document as string.
    
    Format:
        # <title>
        
        > Generated by <script> on <timestamp>
        
        ## Summary
        | Key | Value |
        |-----|-------|
        | ... | ...   |
        
        ## <section.title>
        <section.content>
        
        ...
    """


def json_report(
    *,
    title: str,
    data: dict,
    metadata: dict | None = None,
) -> str:
    """Generate a JSON report.
    
    Returns:
        Pretty-printed JSON string.
    """


def summary_table(rows: list[dict[str, str]], headers: list[str] | None = None) -> str:
    """Generate a markdown table from rows.
    
    Args:
        rows: List of dicts where keys are column headers
        headers: Optional explicit header order
    
    Returns:
        Markdown table string.
    """


def mermaid_block(content: str, title: str = "") -> str:
    """Wrap Mermaid content in a fenced code block.
    
    Returns:
        ```mermaid
        <content>
        ```
    
    If title is provided, adds it as a preceding paragraph.
    """


def write_report(
    content: str,
    output_dir: Path,
    filename: str,
    *,
    create_dirs: bool = True,
) -> Path:
    """Write report content to a file.
    
    Args:
        content: Report content (markdown, JSON, etc.)
        output_dir: Output directory
        filename: Output filename (e.g., "class_diagram.md")
        create_dirs: Create output directory if missing
    
    Returns:
        Absolute path to the written file.
    """
```

### 4.5 `file_discovery.py` — File Walking and Filtering

**Purpose**: Walk directories with configurable filters. Thin wrapper over pathlib that standardizes exclusion patterns and provides a consistent interface for all scripts.

```python
# src/core/data/script_templates/lib/file_discovery.py

from __future__ import annotations

from pathlib import Path


# Standard exclusion patterns (shared across all scripts)
DEFAULT_EXCLUDES: tuple[str, ...] = (
    "__pycache__",
    ".venv",
    "venv",
    "node_modules",
    ".git",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    "build",
    "dist",
    ".eggs",
    ".ruff_cache",
)


def discover_files(
    root: Path,
    *,
    extensions: tuple[str, ...] = (".py",),
    exclude_patterns: tuple[str, ...] = DEFAULT_EXCLUDES,
    include_hidden: bool = False,
) -> list[Path]:
    """Discover files under root matching the given extensions.
    
    Args:
        root: Root directory to scan
        extensions: File extensions to include (with dot)
        exclude_patterns: Directory names to skip
        include_hidden: Include dotfiles (files starting with .)
    
    Returns:
        Sorted list of absolute paths.
    """


def discover_python_files(
    root: Path,
    *,
    source_dir: str = "src",
    exclude_patterns: tuple[str, ...] = DEFAULT_EXCLUDES,
) -> list[Path]:
    """Convenience: discover all Python files in a source directory.
    
    Equivalent to discover_files(root / source_dir, extensions=(".py",))
    but handles the case where source_dir doesn't exist gracefully.
    """


def group_by_package(
    files: list[Path],
    root: Path,
) -> dict[str, list[Path]]:
    """Group files by their parent package.
    
    Returns:
        Dict mapping package name → list of files in that package.
        e.g., {"core.services.vault": [Path("vault/__init__.py"), ...]}
    """


def file_relative_module(path: Path, root: Path) -> str:
    """Convert a file path to a Python module path.
    
    e.g., /project/src/core/services/vault/ops.py → src.core.services.vault.ops
    """
```

---

## 5. Data Flow — How the Lib Modules Connect

```
file_discovery.discover_python_files(root)
    │
    │  → list[Path] of .py files
    │
    ▼
code_analyzer.analyze_python_project(root)
    │
    │  Uses file_discovery internally
    │  AST-parses each file
    │  Extracts ClassInfo with fields, methods, bases
    │
    │  → ProjectAnalysis
    │
    ▼
graph_builder.build_class_graph(analysis)
    │
    │  Creates GraphNodes from ClassInfo
    │  Resolves inheritance → edges
    │  Detects composition → edges
    │  Detects dependencies → edges
    │
    │  → ClassGraph (nodes + edges)
    │
    ▼
mermaid_generator.render_class_diagram(graph)
    │
    │  Converts nodes to Mermaid class declarations
    │  Converts edges to Mermaid relationship arrows
    │  Groups by package for subgraphs
    │
    │  → str (Mermaid syntax)
    │
    ▼
report_formatter.markdown_report(title, summary, sections=[{mermaid_block}])
    │
    │  Wraps in markdown with metadata, summary table, sections
    │
    │  → str (complete markdown document)
    │
    ▼
report_formatter.write_report(content, output_dir, "class_diagram.md")
    │
    │  → Path (written file)
```

This is the pipeline that M3 (Class Diagram Script) will use. Every step is a function call. The script itself is the orchestration logic that calls these functions in order.

---

## 6. Relationship to Audit Parser — Reuse vs. New Code

### 6.1 What We Reuse

| Concept | Audit Parser | Code Analyzer | Same? |
|---------|-------------|---------------|-------|
| AST parsing | `ast.parse()` | `ast.parse()` | Same stdlib call |
| Class detection | `ast.ClassDef` → `SymbolInfo(kind="class")` | `ast.ClassDef` → `ClassInfo` | Same detection, different output model |
| Method listing | `SymbolInfo.methods: list[str]` (names only) | `MethodInfo` (names + types + decorators) | Audit parser is simpler |
| Field extraction | ❌ Not done | ✅ Full extraction | New in code analyzer |
| Base classes | ❌ Not done | ✅ From node.bases | New in code analyzer |
| Composition | ❌ Not done | ✅ From field types | New in code analyzer |
| Import classification | ✅ `ImportInfo` | Used for dependency resolution | Can reference, not import |

### 6.2 Why Not Extend the Audit Parser

The audit parser serves a specific purpose — quality scoring. Its models (`SymbolInfo`, `FileMetrics`) are shaped for that use case. Adding diagram-specific fields (base classes, field types, composition) would bloat the audit parser with data that none of its consumers need.

Instead, the code analyzer is a **parallel extraction** from the same AST. Both parse the same source files, both use `ast.parse()`, but they extract different facets of the code.

### 6.3 Future Opportunity

Later (post-M6), we could refactor both to share a common AST walking layer. But that's a refactoring milestone, not an M2 concern.

---

## 7. File Inventory — What Gets Created

### 7.1 New Files

| File | Lines (est.) | Purpose |
|------|-------------|---------|
| `src/core/data/script_templates/lib/__init__.py` | ~15 | Package init — re-exports public functions |
| `src/core/data/script_templates/lib/code_analyzer.py` | ~350 | Python code analysis (AST-based class/field/method extraction) |
| `src/core/data/script_templates/lib/graph_builder.py` | ~250 | Relationship graph construction (nodes + edges) |
| `src/core/data/script_templates/lib/mermaid_generator.py` | ~300 | Mermaid syntax generation (class diagrams, flowcharts) |
| `src/core/data/script_templates/lib/report_formatter.py` | ~150 | Report output formatting (markdown, JSON) |
| `src/core/data/script_templates/lib/file_discovery.py` | ~100 | File walking and filtering |

**Total new code**: ~1165 lines across 6 files

### 7.2 Modified Files

None. M2 is purely additive — new files only.

### 7.3 Dependencies

All modules use only:
- Python stdlib (`ast`, `pathlib`, `json`, `datetime`, `dataclasses`, `enum`)
- No external dependencies
- No imports from `src.core.services.scripts.*` (the execution framework)
- No imports from `src.core.services.audit.parsers.*` (independent AST walking)

---

## 8. What M2 Does NOT Include

| NOT in M2 | Where it goes |
|-----------|---------------|
| The Class Diagram Generator script itself | M3 |
| The Route Quality Audit script | M5 |
| The Code Hygiene Audit script | M6 |
| Route/Flask-specific analysis | M5 (route_analyzer in lib or inline) |
| Init file analysis | M6 (init_analyzer in lib or inline) |
| CLI/API/UI for scripts | M4 |
| Pyreverse integration | M3 (optional fallback in the script) |

---

## 9. Verification — How We Know M2 Works

### 9.1 Unit Tests

```
tests/scripts/lib/
├── test_code_analyzer.py        # AST extraction tests
├── test_graph_builder.py        # Graph construction tests
├── test_mermaid_generator.py    # Mermaid syntax tests
├── test_report_formatter.py     # Report formatting tests
└── test_file_discovery.py       # File walking tests
```

### 9.2 Test Scenarios

**Code analyzer tests**:
1. Single class with fields → ClassInfo has correct fields
2. Inheritance (class Foo(Bar)) → bases = ["Bar"]
3. Multiple inheritance → bases = ["Bar", "Baz"]
4. ABC/Protocol detection → is_abstract = True
5. Dataclass detection → is_dataclass = True
6. Pydantic BaseModel detection → is_pydantic = True
7. Method extraction → name, visibility, parameters, decorators
8. Field extraction from __init__ → instance fields
9. Field extraction from class body → class variables
10. Visibility detection → public/protected/private from naming
11. Type annotation extraction → type_annotation populated
12. File with syntax error → graceful fallback, no crash
13. Empty file → empty ClassInfo list
14. Full project scan → all classes found

**Graph builder tests**:
1. Simple inheritance A → B → graph has INHERITS edge
2. ABC inheritance → IMPLEMENTS edge
3. Composition (field type is a class) → COMPOSES edge
4. No relationships → orphan nodes
5. Scope filter → only matching package classes
6. Circular dependency → graph handles without infinite loop

**Mermaid generator tests**:
1. Single class → valid Mermaid class declaration
2. Inheritance edge → correct arrow syntax (--|>)
3. Composition edge → correct arrow syntax (*--)
4. Fields truncation → "... N more" indicator
5. Package grouping → namespace blocks
6. Full graph → complete valid Mermaid syntax
7. Empty graph → minimal valid output

**Report formatter tests**:
1. Markdown report → has title, summary table, sections
2. JSON report → valid JSON
3. Mermaid block → fenced code block with mermaid language
4. Summary table → valid markdown table
5. Write report → file exists at expected path

**File discovery tests**:
1. Python files only → excludes non-.py files
2. Excludes __pycache__ → filtered out
3. Empty directory → returns empty list
4. Group by package → correct grouping
5. Module path → correct dotted path

### 9.3 Integration Smoke Test

Use the **project itself** as the test subject:

```python
# Analyze the scripts service (M1 code)
analysis = analyze_python_project(
    Path("/home/jfortin/devops-control-plane"),
    source_dir="src/core/services/scripts",
)

# Build a class diagram
graph = build_class_graph(analysis)

# Render as Mermaid
mermaid = render_class_diagram(graph)

# Generate report
report = markdown_report(
    title="Scripts Service Class Diagram",
    summary={"Classes": len(graph.nodes), "Relationships": len(graph.edges)},
    sections=[{"title": "Class Diagram", "content": mermaid_block(mermaid)}],
)

# Write to file
write_report(report, Path("docs/diagrams"), "scripts_service.md")
```

This validates the entire pipeline end-to-end using real code.

---

## 10. Implementation Order Within M2

```
Step 1: file_discovery.py (zero dependencies)
    → discover_files(), discover_python_files(), group_by_package()
    → Pure pathlib, no external imports

Step 2: code_analyzer.py (depends on: file_discovery.py)
    → ClassInfo, FieldInfo, MethodInfo, ProjectAnalysis
    → analyze_python_project(), analyze_file()
    → Uses file_discovery for file listing, ast for parsing

Step 3: graph_builder.py (depends on: code_analyzer.py)
    → GraphNode, GraphEdge, ClassGraph, RelationType
    → build_class_graph()
    → Uses ClassInfo from code_analyzer

Step 4: mermaid_generator.py (depends on: graph_builder.py)
    → render_class_diagram(), render_flowchart()
    → Uses ClassGraph from graph_builder

Step 5: report_formatter.py (zero dependencies on other lib modules)
    → markdown_report(), json_report(), mermaid_block(), write_report()
    → Pure string formatting, can be built in parallel with Steps 1-4

Step 6: __init__.py (depends on: all above)
    → Re-exports public functions from each module

Step 7: Tests (depends on: all above)
    → Unit tests for each module
    → Integration smoke test using project's own source code
```

---

## 11. Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Separate from audit parser | Yes — parallel AST extraction | Different output models for different purposes; avoids bloating audit parser |
| Location | `src/core/data/script_templates/lib/` | Part of template ecosystem, not execution framework |
| No external deps | stdlib only (ast, pathlib, json) | Scripts must work in any project venv without extra installs |
| Pipeline pattern | Parser → Graph → Renderer | Clean separation, each step testable independently |
| Mermaid output | String-based generation, not template-based | More control, easier to test, no template engine dependency |
| Report formatting | Generic (markdown/JSON), not format-specific | Same formatter for all scripts, consistency |
| Field extraction strategy | AST walking of `__init__` + class body | Most reliable approach without runtime introspection |
| Visibility from naming | Python convention: _, __, public | Standard Python, no custom markers needed |
| No audit parser import | Independent AST walking | Avoids coupling to audit system; lib has zero internal deps |
