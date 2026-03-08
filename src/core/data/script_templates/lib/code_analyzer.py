"""
Code Analyzer Module
====================
Extract class-diagram-relevant data from Python source files.

Uses ``ast.parse()`` directly for structural relationship extraction
(inheritance, composition, field types, method signatures).  Independent
of the audit parser — different output models for different purposes.

Pipeline position: discover → **parse** → graph → render → report
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

from .file_discovery import discover_python_files, file_relative_module


# ═══════════════════════════════════════════════════════════════════
#  Data models
# ═══════════════════════════════════════════════════════════════════


@dataclass
class FieldInfo:
    """A class field (instance or class variable).

    Extracted from:
    - Type annotations in __init__: ``self.name: Type = value``
    - Class-level annotations: ``name: Type``
    - Simple assignments: ``self.name = value`` (type inferred as "Any")
    """

    name: str
    type_annotation: str = "Any"        # Type annotation or "Any" if untyped
    is_class_var: bool = False           # True for class-level, False for instance
    visibility: str = "public"          # "public" | "protected" | "private"
                                        # Derived from _ / __ prefix


@dataclass
class MethodInfo:
    """A method in a class.

    Simplified for diagram use — no metrics, just signature data.
    """

    name: str
    is_async: bool = False
    is_static: bool = False             # @staticmethod
    is_classmethod: bool = False        # @classmethod
    is_property: bool = False           # @property
    is_abstract: bool = False           # @abstractmethod
    visibility: str = "public"          # "public" | "protected" | "private"
    parameters: list[str] = field(default_factory=list)   # Parameter names (no self/cls)
    return_type: str = ""               # Return type annotation if present
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
    qualified_name: str = ""            # e.g., "src.core.services.event_bus.EventBus"
    file_path: str = ""                 # Relative path to source file
    module: str = ""                    # Python module path

    bases: list[str] = field(default_factory=list)
                                        # Base class names as written in source
                                        # e.g., ["BaseModel"], ["ABC", "Generic[T]"]

    fields: list[FieldInfo] = field(default_factory=list)
    methods: list[MethodInfo] = field(default_factory=list)

    is_abstract: bool = False           # Has ABC or @abstractmethod
    is_dataclass: bool = False          # @dataclass decorator
    is_pydantic: bool = False           # Inherits BaseModel
    is_protocol: bool = False           # Inherits Protocol

    decorators: list[str] = field(default_factory=list)
    docstring: str = ""                 # First line of docstring (summary)

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


# ═══════════════════════════════════════════════════════════════════
#  Public functions
# ═══════════════════════════════════════════════════════════════════


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
        project_root: Project root directory.
        source_dir: Source directory to scan (relative to root).
        exclude_patterns: Directory names to skip.
        include_private: Include _private classes.

    Returns:
        ProjectAnalysis with all discovered classes.
    """
    result = ProjectAnalysis()

    files = discover_python_files(
        project_root,
        source_dir=source_dir,
        exclude_patterns=exclude_patterns,
    )

    for fpath in files:
        result.files_analyzed += 1
        try:
            classes = analyze_file(fpath, project_root)
        except Exception as exc:
            result.files_with_errors += 1
            result.analysis_errors.append(f"{fpath}: {exc}")
            continue

        for cls in classes:
            if not include_private and cls.name.startswith("_"):
                continue
            result.classes.append(cls)

    result.total_classes = len(result.classes)
    return result


def analyze_file(path: Path, project_root: Path) -> list[ClassInfo]:
    """Analyze a single Python file for class information.

    Uses ``ast.parse()`` directly.  Does NOT import the audit parser —
    the code analyzer has its own AST walking because it extracts
    different data (fields, base classes, composition) that the
    audit parser doesn't provide.

    Args:
        path: Absolute path to a ``.py`` file.
        project_root: Project root for relative path computation.

    Returns:
        List of ClassInfo for every class in the file.
    """
    content = path.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(content, filename=str(path))
    except SyntaxError:
        return []

    module_path = file_relative_module(path, project_root)

    try:
        rel_path = str(path.resolve().relative_to(project_root.resolve()))
    except ValueError:
        rel_path = str(path)

    classes: list[ClassInfo] = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            cls = _extract_class(node, module_path, rel_path)
            classes.append(cls)

    return classes


# ═══════════════════════════════════════════════════════════════════
#  Internal extraction helpers
# ═══════════════════════════════════════════════════════════════════


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
    bases = _extract_bases(node)
    fields = _extract_fields(node)
    methods = _extract_methods(node)
    decorators = _extract_decorators(node)

    qualified = f"{module_path}.{node.name}" if module_path else node.name

    # Detect special class kinds
    is_abstract = _is_abstract(node, bases, methods)
    is_dataclass = _has_decorator(decorators, "dataclass")
    is_pydantic = any(b in ("BaseModel", "BaseSettings") for b in bases)
    is_protocol = "Protocol" in bases

    # Extract docstring (first line)
    docstring = ""
    raw_doc = ast.get_docstring(node)
    if raw_doc:
        first_line = raw_doc.strip().split("\n")[0]
        docstring = first_line

    return ClassInfo(
        name=node.name,
        qualified_name=qualified,
        file_path=file_path,
        module=module_path,
        bases=bases,
        fields=fields,
        methods=methods,
        is_abstract=is_abstract,
        is_dataclass=is_dataclass,
        is_pydantic=is_pydantic,
        is_protocol=is_protocol,
        decorators=decorators,
        docstring=docstring,
        lineno=node.lineno,
        end_lineno=getattr(node, "end_lineno", 0) or 0,
    )


def _extract_bases(node: ast.ClassDef) -> list[str]:
    """Extract base class names from a ClassDef.

    Handles:
    - Simple names: ``class Foo(Bar)`` → ``["Bar"]``
    - Dotted names: ``class Foo(abc.ABC)`` → ``["abc.ABC"]``
    - Generic: ``class Foo(Generic[T])`` → ``["Generic[T]"]``
    - Multiple: ``class Foo(Bar, Baz)`` → ``["Bar", "Baz"]``

    Returns names as-written (unresolved).
    """
    bases: list[str] = []
    for base in node.bases:
        bases.append(_node_to_str(base))
    return bases


def _extract_fields(node: ast.ClassDef) -> list[FieldInfo]:
    """Extract fields from a class.

    Sources:
    1. Class-level annotations: ``name: Type`` or ``name: Type = value``
    2. __init__ body: ``self.name = value`` or ``self.name: Type = value``
    3. Dataclass fields: ``field(default=..., default_factory=...)``

    Visibility from naming:
    - ``__name`` → private
    - ``_name``  → protected
    - ``name``   → public
    """
    fields: list[FieldInfo] = []
    seen: set[str] = set()

    # 1. Class-level annotated assignments
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
            name = child.target.id
            if name not in seen:
                seen.add(name)
                fields.append(FieldInfo(
                    name=name,
                    type_annotation=_node_to_str(child.annotation),
                    is_class_var=True,
                    visibility=_visibility_from_name(name),
                ))

    # 2. __init__ body — self.x assignments
    for child in ast.iter_child_nodes(node):
        if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if child.name != "__init__":
            continue
        for stmt in ast.walk(child):
            # self.name: Type = value  (AnnAssign)
            if isinstance(stmt, ast.AnnAssign):
                target = stmt.target
                if (isinstance(target, ast.Attribute)
                        and isinstance(target.value, ast.Name)
                        and target.value.id == "self"):
                    name = target.attr
                    if name not in seen:
                        seen.add(name)
                        fields.append(FieldInfo(
                            name=name,
                            type_annotation=_node_to_str(stmt.annotation),
                            is_class_var=False,
                            visibility=_visibility_from_name(name),
                        ))
            # self.name = value  (Assign)
            elif isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    if (isinstance(target, ast.Attribute)
                            and isinstance(target.value, ast.Name)
                            and target.value.id == "self"):
                        name = target.attr
                        if name not in seen:
                            seen.add(name)
                            fields.append(FieldInfo(
                                name=name,
                                type_annotation="Any",
                                is_class_var=False,
                                visibility=_visibility_from_name(name),
                            ))

    return fields


def _extract_methods(node: ast.ClassDef) -> list[MethodInfo]:
    """Extract methods from a class.

    For each FunctionDef/AsyncFunctionDef child:
    - Name and visibility
    - Parameters (excluding self/cls)
    - Return type annotation
    - Decorator detection (property, staticmethod, classmethod, abstractmethod)
    """
    methods: list[MethodInfo] = []

    for child in ast.iter_child_nodes(node):
        if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        decorators = _extract_decorators(child)

        is_static = _has_decorator(decorators, "staticmethod")
        is_classmethod = _has_decorator(decorators, "classmethod")
        is_property = _has_decorator(decorators, "property")
        is_abstract = _has_decorator(decorators, "abstractmethod")

        # Parameters — skip self/cls
        params: list[str] = []
        for arg in child.args.args:
            if arg.arg in ("self", "cls"):
                continue
            params.append(arg.arg)

        # Return type
        return_type = ""
        if child.returns:
            return_type = _node_to_str(child.returns)

        methods.append(MethodInfo(
            name=child.name,
            is_async=isinstance(child, ast.AsyncFunctionDef),
            is_static=is_static,
            is_classmethod=is_classmethod,
            is_property=is_property,
            is_abstract=is_abstract,
            visibility=_visibility_from_name(child.name),
            parameters=params,
            return_type=return_type,
            decorators=decorators,
        ))

    return methods


# ═══════════════════════════════════════════════════════════════════
#  AST utility helpers
# ═══════════════════════════════════════════════════════════════════


def _extract_decorators(node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    """Extract decorator names from a node."""
    decorators: list[str] = []
    for dec in node.decorator_list:
        if isinstance(dec, ast.Name):
            decorators.append(dec.id)
        elif isinstance(dec, ast.Attribute):
            decorators.append(_node_to_str(dec))
        elif isinstance(dec, ast.Call):
            # e.g., @dataclass(frozen=True)
            if isinstance(dec.func, ast.Name):
                decorators.append(dec.func.id)
            elif isinstance(dec.func, ast.Attribute):
                decorators.append(_node_to_str(dec.func))
    return decorators


def _node_to_str(node: ast.AST) -> str:
    """Convert an AST node to its source-code string representation.

    Handles:
    - Name: ``Foo`` → ``"Foo"``
    - Attribute: ``abc.ABC`` → ``"abc.ABC"``
    - Subscript: ``Generic[T]`` → ``"Generic[T]"``
    - Constant: ``42`` → ``"42"``
    - BinOp with ``|``: ``int | str`` → ``"int | str"``
    - Tuple: ``(int, str)`` → ``"int, str"``
    """
    # Python 3.12+ has ast.unparse, use it if available
    try:
        return ast.unparse(node)
    except Exception:
        pass

    # Fallback for older Python or edge cases
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_node_to_str(node.value)}.{node.attr}"
    if isinstance(node, ast.Subscript):
        return f"{_node_to_str(node.value)}[{_node_to_str(node.slice)}]"
    if isinstance(node, ast.Constant):
        return repr(node.value)
    if isinstance(node, ast.Tuple):
        return ", ".join(_node_to_str(e) for e in node.elts)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return f"{_node_to_str(node.left)} | {_node_to_str(node.right)}"
    if isinstance(node, ast.List):
        return "[" + ", ".join(_node_to_str(e) for e in node.elts) + "]"

    return "..."


def _visibility_from_name(name: str) -> str:
    """Determine visibility from Python naming convention.

    - ``__name`` (dunder, not magic) → private
    - ``_name`` → protected
    - ``name`` → public
    """
    if name.startswith("__") and not name.endswith("__"):
        return "private"
    if name.startswith("_"):
        return "protected"
    return "public"


def _is_abstract(
    node: ast.ClassDef,
    bases: list[str],
    methods: list[MethodInfo],
) -> bool:
    """Detect if a class is abstract.

    True if:
    - Inherits from ABC, ABCMeta, or abc.ABC
    - OR has any @abstractmethod decorated methods
    """
    abstract_bases = {"ABC", "ABCMeta", "abc.ABC", "abc.ABCMeta"}
    if abstract_bases & set(bases):
        return True
    return any(m.is_abstract for m in methods)


def _has_decorator(decorators: list[str], name: str) -> bool:
    """Check if a decorator list contains a specific decorator."""
    return name in decorators
