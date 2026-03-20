"""Python-specific context detection for edge case handling.

Provides helpers to detect special code contexts:
- TYPE_CHECKING blocks
- try/except ImportError patterns
- sys.version_info gates
- getattr with default (safe attribute access)
- Annotation vs runtime usage
- __future__ annotations effects

These are used by the detection engine to exclude or downgrade
findings based on context. Each context type has a corresponding
exclusion reason in the feature database entries.
"""

from __future__ import annotations

import ast
from typing import Any


def is_type_checking_block(node: ast.AST, parent_map: dict[int, ast.AST]) -> bool:
    """Check if node is inside an 'if TYPE_CHECKING:' block.

    Pattern:
        from typing import TYPE_CHECKING
        if TYPE_CHECKING:
            from heavy_module import HeavyClass  ← THIS import
    """
    current = node
    while id(current) in parent_map:
        parent = parent_map[id(current)]
        if isinstance(parent, ast.If):
            test = parent.test
            # Direct: if TYPE_CHECKING:
            if isinstance(test, ast.Name) and test.id == "TYPE_CHECKING":
                return True
            # Qualified: if typing.TYPE_CHECKING:
            if isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING":
                return True
        current = parent
    return False


def is_try_except_import(node: ast.AST, parent_map: dict[int, ast.AST]) -> bool:
    """Check if node is inside a try/except ImportError block.

    Pattern:
        try:
            from datetime import UTC  ← THIS import
        except ImportError:
            from datetime import timezone
            UTC = timezone.utc
    """
    current = node
    while id(current) in parent_map:
        parent = parent_map[id(current)]
        if isinstance(parent, ast.Try):
            for handler in parent.handlers:
                if handler.type and isinstance(handler.type, ast.Name):
                    if handler.type.id in ("ImportError", "ModuleNotFoundError"):
                        return True
                # Tuple of exceptions: except (ImportError, ModuleNotFoundError):
                if handler.type and isinstance(handler.type, ast.Tuple):
                    for elt in handler.type.elts:
                        if isinstance(elt, ast.Name) and elt.id in ("ImportError", "ModuleNotFoundError"):
                            return True
            return False
        current = parent
    return False


def is_version_gate(node: ast.AST, parent_map: dict[int, ast.AST]) -> bool:
    """Check if node is inside a sys.version_info comparison block.

    Pattern:
        import sys
        if sys.version_info >= (3, 11):
            from datetime import UTC  ← THIS import
        else:
            from datetime import timezone
            UTC = timezone.utc
    """
    current = node
    while id(current) in parent_map:
        parent = parent_map[id(current)]
        if isinstance(parent, ast.If):
            if _is_version_comparison(parent.test):
                return True
        current = parent
    return False


def _is_version_comparison(test: ast.AST) -> bool:
    """Check if an expression is a sys.version_info comparison."""
    if isinstance(test, ast.Compare):
        left = test.left
        if isinstance(left, ast.Attribute):
            if (isinstance(left.value, ast.Name) and
                    left.value.id == "sys" and
                    left.attr == "version_info"):
                return True
        # Also handle: (3, 11) <= sys.version_info
        for comparator in test.comparators:
            if isinstance(comparator, ast.Attribute):
                if (isinstance(comparator.value, ast.Name) and
                        comparator.value.id == "sys" and
                        comparator.attr == "version_info"):
                    return True
    return False


def is_getattr_with_default(node: ast.AST, parent_map: dict[int, ast.AST]) -> bool:
    """Check if node's value is accessed via getattr with a default.

    Pattern:
        utc = getattr(datetime, "UTC", datetime.timezone.utc)  ← Safe

    The string "UTC" inside getattr is not an AST Name node, so this
    mainly catches cases where the detection finds an Attribute node
    for datetime.UTC that's actually inside a getattr call.
    """
    current = node
    while id(current) in parent_map:
        parent = parent_map[id(current)]
        if isinstance(parent, ast.Call):
            func = getattr(parent, "func", None)
            if isinstance(func, ast.Name) and func.id == "getattr":
                # getattr with 3 args = has default = safe
                if len(parent.args) >= 3:
                    return True
        current = parent
    return False


def is_annotation_only(
    node: ast.AST,
    parent_map: dict[int, ast.AST],
    has_future_annotations: bool,
) -> bool:
    """Check if a node is used only in an annotation context.

    With __future__ annotations, annotation-only usages are safe
    because they're evaluated lazily (as strings).

    WITHOUT __future__, annotation usages ARE evaluated at runtime
    for function parameter defaults, isinstance checks, etc.

    This function checks if the usage is in a PURE annotation context
    (function parameter type, return type, variable annotation).
    """
    if not has_future_annotations:
        return False  # Without __future__, annotations are evaluated

    current = node
    while id(current) in parent_map:
        parent = parent_map[id(current)]

        # Function parameter annotation
        if isinstance(parent, ast.arg) and current is parent.annotation:
            return True

        # Function return annotation
        if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if current is parent.returns:
                return True

        # Variable annotation (not the value)
        if isinstance(parent, ast.AnnAssign):
            if current is parent.annotation:
                return True

        current = parent
    return False


def is_runtime_isinstance(node: ast.AST, parent_map: dict[int, ast.AST]) -> bool:
    """Check if a BinOp | is used in isinstance() — runtime, not annotation.

    Pattern:
        isinstance(x, int | str)  ← RUNTIME even with __future__

    This is the critical edge case where X | Y in isinstance() is NOT
    an annotation and WILL crash on Python < 3.10 regardless of __future__.
    """
    current = node
    while id(current) in parent_map:
        parent = parent_map[id(current)]
        if isinstance(parent, ast.Call):
            func = getattr(parent, "func", None)
            if isinstance(func, ast.Name) and func.id in ("isinstance", "issubclass"):
                return True
        current = parent
    return False


def build_parent_map(tree: ast.Module) -> dict[int, ast.AST]:
    """Build a child-id → parent map for the AST.

    Uses id() as keys because AST nodes aren't hashable in all cases.
    """
    parent_map: dict[int, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parent_map[id(child)] = parent
    return parent_map
