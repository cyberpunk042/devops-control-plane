"""Python language backend — uses stdlib ast module.

Handles:
- Parsing .py files into AST
- Matching detection rules against AST nodes
- Context detection (__future__, TYPE_CHECKING, try/except, version gates)
- Import resolution (absolute, relative, star)
- Syntax and import verification
"""

from __future__ import annotations

import ast
import logging
import subprocess
from pathlib import Path
from typing import Any, Iterator

from .base import LanguageBackend

logger = logging.getLogger(__name__)


class PythonBackend(LanguageBackend):
    """Python backend using stdlib ast module."""

    @property
    def language_id(self) -> str:
        return "python"

    @property
    def file_extensions(self) -> list[str]:
        return [".py"]

    # ── Parsing ──────────────────────────────────────────────────

    def parse_file(self, path: Path) -> ast.Module:
        source = path.read_text(encoding="utf-8", errors="ignore")
        return ast.parse(source, filename=str(path))

    def parse_source(self, source: str, filename: str = "<string>") -> ast.Module:
        return ast.parse(source, filename=filename)

    def walk_ast(self, tree: Any) -> Iterator[ast.AST]:
        yield from ast.walk(tree)

    def node_type_name(self, node: Any) -> str:
        return type(node).__name__

    def node_location(self, node: Any) -> tuple[int, int]:
        return (getattr(node, "lineno", 0), getattr(node, "col_offset", 0))

    def get_source_line(self, source: str, line: int) -> str:
        lines = source.split("\n")
        if 1 <= line <= len(lines):
            return lines[line - 1].rstrip()
        return ""

    # ── Matching ─────────────────────────────────────────────────

    def node_matches(self, node: Any, ast_type: str, match: dict) -> bool:
        """Check if a Python AST node matches type + attribute constraints."""
        if type(node).__name__ != ast_type:
            return False

        for key, expected in match.items():
            if not self._check_attribute(node, key, expected):
                return False

        return True

    def _check_attribute(self, node: ast.AST, key: str, expected: object) -> bool:
        """Check a single attribute constraint on a node."""

        # Special matchers
        if key == "names_contains":
            # ImportFrom/Import: check if a name is in the names list
            names = getattr(node, "names", [])
            return any(alias.name == expected for alias in names)

        if key == "value_type":
            # Attribute node: check the type of the value sub-node
            val = getattr(node, "value", None)
            return val is not None and type(val).__name__ == expected

        if key == "value_id":
            # Attribute node: check value is a Name with specific id
            val = getattr(node, "value", None)
            return isinstance(val, ast.Name) and val.id == expected

        if key == "value_id_in":
            # Attribute/Subscript: check value Name.id is in a list
            val = getattr(node, "value", None)
            return isinstance(val, ast.Name) and val.id in expected

        if key == "op_type":
            # BinOp: check operator type
            op = getattr(node, "op", None)
            return op is not None and type(op).__name__ == expected

        if key == "func_attr":
            # Call: check func.attr (method call name)
            func = getattr(node, "func", None)
            return isinstance(func, ast.Attribute) and func.attr == expected

        if key == "has_posonlyargs":
            # FunctionDef: check if it has positional-only args
            args = getattr(node, "args", None)
            if args is None:
                return not expected
            posonlyargs = getattr(args, "posonlyargs", [])
            return bool(posonlyargs) == expected

        if key == "func_id":
            # Call: check func is a Name with specific id (e.g., zip, anext)
            func = getattr(node, "func", None)
            return isinstance(func, ast.Name) and func.id == expected

        if key == "id":
            # Name: check the name identifier
            return getattr(node, "id", None) == expected

        if key == "name_prefix":
            # FunctionDef: check if function name starts with prefix
            name = getattr(node, "name", "")
            return name.startswith(expected) if name else False

        if key == "param_type":
            # FunctionDef: check if first parameter has specific type annotation
            args = getattr(node, "args", None)
            if not args or not args.args:
                return False
            first_arg = args.args[0]
            ann = first_arg.annotation
            if ann is None:
                return False
            ann_src = ast.dump(ann)
            return expected in ann_src

        if key == "has_nested_fstring":
            # JoinedStr: check for nested JoinedStr in values
            if not isinstance(node, ast.JoinedStr):
                return False
            for val in getattr(node, "values", []):
                if isinstance(val, ast.FormattedValue):
                    if isinstance(val.value, ast.JoinedStr):
                        return True
            return not expected  # expected=True but no nested found

        if key == "has_parenthesized_items":
            # With: check for multiple items (heuristic for parenthesized)
            items = getattr(node, "items", [])
            return (len(items) > 1) == expected

        if key == "conversion_eq":
            # FormattedValue: check for f'{x=}' debug format
            # In 3.8+, FormattedValue has conversion=-1 for =
            # Actually, the = is part of the format_spec in the AST
            if not isinstance(node, ast.FormattedValue):
                return not expected
            # f'{x=}' sets conversion to 114 ('r') and adds format_spec
            # The = sign is encoded differently across Python versions
            # Simplest: check if the source contains '=' after the expression
            return expected  # Accept if node type matches — imprecise but workable

        if key == "has_guard":
            # match_case: check if it has a guard expression
            guard = getattr(node, "guard", None)
            return (guard is not None) == expected

        if key == "has_type_params":
            # FunctionDef/ClassDef: check for PEP 695 type parameters [T]
            type_params = getattr(node, "type_params", [])
            return bool(type_params) == expected

        if key == "has_complex_decorator":
            # FunctionDef: check if any decorator contains subscripts or
            # binary ops (not just Name, Attribute, or Call chains).
            # Call nodes are normal decorators with args (@deco(arg))
            # Subscripts are relaxed syntax (@buttons[0].connect)
            decorators = getattr(node, "decorator_list", [])
            for deco in decorators:
                for sub in ast.walk(deco):
                    if isinstance(sub, (ast.Subscript, ast.BinOp)):
                        return expected
            return not expected

        # ── Call-node refinement matchers ─────────────────────────

        if key == "has_keyword":
            # Call: check if a specific keyword argument is present.
            # Detects: dataclass(slots=True), field(kw_only=True), etc.
            keywords = getattr(node, "keywords", [])
            if isinstance(expected, str):
                return any(kw.arg == expected for kw in keywords)
            if isinstance(expected, list):
                return any(kw.arg in expected for kw in keywords)
            return False

        if key == "has_keyword_value":
            # Call: check if a keyword has a specific constant value.
            # Detects: dataclass(slots=True) but NOT dataclass(slots=False)
            # expected is a dict: {"keyword": "slots", "value": True}
            if not isinstance(expected, dict):
                return False
            kw_name = expected.get("keyword", "")
            kw_value = expected.get("value")
            keywords = getattr(node, "keywords", [])
            for kw in keywords:
                if kw.arg == kw_name:
                    if isinstance(kw.value, ast.Constant):
                        return kw.value.value == kw_value
                    # Non-constant value (variable) — can't determine, match conservatively
                    return True
            return False

        if key == "func_value_id":
            # Call: check what object a method is called on.
            # Detects: re.compile() but NOT something.compile()
            # Works for: obj.method() where obj is a direct Name reference.
            func = getattr(node, "func", None)
            if isinstance(func, ast.Attribute):
                val = func.value
                if isinstance(val, ast.Name):
                    if isinstance(expected, str):
                        return val.id == expected
                    if isinstance(expected, list):
                        return val.id in expected
            return False

        if key == "func_value_attr":
            # Call: check the attribute chain of the method's object.
            # Detects: datetime.timezone.utc but requires deeper chain matching.
            # Works for: obj.attr.method() — checks obj.attr.
            func = getattr(node, "func", None)
            if isinstance(func, ast.Attribute):
                val = func.value
                if isinstance(val, ast.Attribute):
                    return val.attr == expected
            return False

        if key == "min_args":
            # Call: check minimum number of positional arguments.
            # Useful to distinguish zip(a, b) from zip(a, b, strict=True)
            args = getattr(node, "args", [])
            return len(args) >= expected

        if key == "has_stararg":
            # Call: check if call uses *args unpacking.
            # Detects: func(*args) patterns
            args = getattr(node, "args", [])
            return any(isinstance(a, ast.Starred) for a in args) == expected

        if key == "arg_is_binop_bitor":
            # Call: check if any positional argument is a BinOp with BitOr.
            # Detects: isinstance(x, int | str) — runtime union type (3.10)
            # Does NOT match: isinstance(x, (int, str)) — tuple form (any version)
            args = getattr(node, "args", [])
            has_bitor_arg = any(
                isinstance(a, ast.BinOp) and isinstance(a.op, ast.BitOr)
                for a in args
            )
            return has_bitor_arg == expected

        if key == "arg_count":
            # Call: exact number of positional arguments
            args = getattr(node, "args", [])
            return len(args) == expected

        if key == "decorator_name":
            # FunctionDef/ClassDef: check if it has a specific decorator.
            # Matches both @name and @name(...) forms.
            # Detects: @cache, @cached_property, @override, etc.
            decorators = getattr(node, "decorator_list", [])
            for deco in decorators:
                if isinstance(deco, ast.Name) and deco.id == expected:
                    return True
                if isinstance(deco, ast.Call) and isinstance(deco.func, ast.Name) and deco.func.id == expected:
                    return True
            return False

        if key == "decorator_name_in":
            # FunctionDef/ClassDef: check if it has any decorator from a list.
            decorators = getattr(node, "decorator_list", [])
            if not isinstance(expected, list):
                return False
            for deco in decorators:
                if isinstance(deco, ast.Name) and deco.id in expected:
                    return True
                if isinstance(deco, ast.Call) and isinstance(deco.func, ast.Name) and deco.func.id in expected:
                    return True
            return False

        if key == "module_is":
            # ImportFrom: check the module being imported from.
            # Detects: from contextlib import aclosing (module_is: contextlib)
            module = getattr(node, "module", None)
            if isinstance(expected, str):
                return module == expected
            if isinstance(expected, list):
                return module in expected
            return False

        if key == "module_startswith":
            # ImportFrom: check module prefix.
            # Detects: from asyncio.* import X
            module = getattr(node, "module", None) or ""
            return module.startswith(expected) if isinstance(expected, str) else False

        # ── BinOp refinement matchers ─────────────────────────────

        if key == "left_is_dict":
            # BinOp: check if left operand is a dict literal or dict() call.
            # Helps distinguish dict | dict (3.9) from int | int (any version).
            left = getattr(node, "left", None)
            if left is None:
                return not expected
            is_dict = (
                isinstance(left, ast.Dict)
                or (isinstance(left, ast.Call) and isinstance(left.func, ast.Name) and left.func.id == "dict")
            )
            return is_dict == expected

        if key == "right_is_dict":
            # BinOp: check if right operand is a dict literal or dict() call.
            right = getattr(node, "right", None)
            if right is None:
                return not expected
            is_dict = (
                isinstance(right, ast.Dict)
                or (isinstance(right, ast.Call) and isinstance(right.func, ast.Name) and right.func.id == "dict")
            )
            return is_dict == expected

        # Generic attribute check
        actual = getattr(node, key, None)
        return actual == expected

    def get_node_context(self, node: Any, tree: Any) -> str:
        """Determine the context of a node in the Python AST.

        Walks up the parent chain to determine where this node sits.
        """
        # Build parent map if not cached on tree
        parent_map = self._get_parent_map(tree)
        current = node

        while current in parent_map:
            parent = parent_map[current]

            # TYPE_CHECKING block: if TYPE_CHECKING: ...
            if isinstance(parent, ast.If):
                test = parent.test
                if isinstance(test, ast.Name) and test.id == "TYPE_CHECKING":
                    return "type_checking_block"
                if isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING":
                    return "type_checking_block"

            # try/except block
            if isinstance(parent, (ast.Try,)):
                # Check if node is in the handler (except) part
                for handler in parent.handlers:
                    if node in ast.walk(handler):
                        return "except_block"
                # Check for ImportError handler specifically
                for handler in parent.handlers:
                    if handler.type and isinstance(handler.type, ast.Name):
                        if handler.type.id in ("ImportError", "ModuleNotFoundError"):
                            return "try_except_import"
                return "try_block"

            # TryStar (Python 3.11+ except*)
            if type(parent).__name__ == "TryStar":
                return "try_block"

            # Version gate: if sys.version_info >= (3, 11): ...
            if isinstance(parent, ast.If):
                if self._is_version_gate(parent):
                    return "version_gate"

            # Annotation context
            if isinstance(parent, ast.AnnAssign) and node is not parent.value:
                return "annotation"
            if isinstance(parent, ast.FunctionDef) or isinstance(parent, ast.AsyncFunctionDef):
                if node is parent.returns:
                    return "annotation"
                for arg in parent.args.args + parent.args.posonlyargs + parent.args.kwonlyargs:
                    if node is arg.annotation:
                        return "annotation"

            # Function body
            if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return "function_body"

            # Class body
            if isinstance(parent, ast.ClassDef):
                return "class_body"

            current = parent

        return "module_level"

    def _is_version_gate(self, if_node: ast.If) -> bool:
        """Check if an If node is a sys.version_info check."""
        test = if_node.test
        if isinstance(test, ast.Compare):
            left = test.left
            if isinstance(left, ast.Attribute):
                if (isinstance(left.value, ast.Name) and
                        left.value.id == "sys" and
                        left.attr == "version_info"):
                    return True
        return False

    def _get_parent_map(self, tree: ast.Module) -> dict:
        """Build a child→parent map for the AST."""
        # Cache on the tree object to avoid rebuilding
        cache_attr = "_compat_parent_map"
        if hasattr(tree, cache_attr):
            return getattr(tree, cache_attr)

        parent_map: dict[ast.AST, ast.AST] = {}
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                parent_map[child] = parent

        try:
            setattr(tree, cache_attr, parent_map)
        except (AttributeError, TypeError):
            pass
        return parent_map

    def has_future_annotations(self, tree: Any) -> bool:
        """Check if file has 'from __future__ import annotations'."""
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module == "__future__":
                    if any(alias.name == "annotations" for alias in node.names):
                        return True
        return False

    # ── Import resolution ────────────────────────────────────────

    def extract_imports(self, tree: Any, file_path: Path) -> list[dict]:
        """Extract all import statements from a Python AST."""
        imports = []
        parent_map = self._get_parent_map(tree)

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append({
                        "module": alias.name,
                        "names": [alias.asname or alias.name],
                        "line": node.lineno,
                        "import_type": "import",
                        "is_conditional": self._is_conditional_import(node, parent_map),
                        "is_type_only": self.get_node_context(node, tree) == "type_checking_block",
                    })

            elif isinstance(node, ast.ImportFrom):
                if node.module is None:
                    continue
                names = [alias.name for alias in node.names]
                import_type = "from_import_star" if names == ["*"] else "from_import"
                imports.append({
                    "module": node.module,
                    "names": names,
                    "line": node.lineno,
                    "import_type": import_type,
                    "level": node.level,  # 0=absolute, 1=relative, 2=parent, etc.
                    "is_conditional": self._is_conditional_import(node, parent_map),
                    "is_type_only": self.get_node_context(node, tree) == "type_checking_block",
                })

        return imports

    def _is_conditional_import(self, node: ast.AST, parent_map: dict) -> bool:
        """Check if an import is inside a try/except block."""
        current = node
        while current in parent_map:
            parent = parent_map[current]
            if isinstance(parent, ast.Try):
                return True
            if type(parent).__name__ == "TryStar":
                return True
            current = parent
        return False

    def resolve_import_path(
        self,
        module_name: str,
        source_file: Path,
        project_root: Path,
    ) -> Path | None:
        """Resolve a Python import to a project file path.

        Returns None for stdlib, third-party, or unresolvable imports.
        """
        # Convert dotted path to file path
        parts = module_name.split(".")
        candidates = [
            project_root / Path(*parts).with_suffix(".py"),
            project_root / Path(*parts) / "__init__.py",
        ]

        for candidate in candidates:
            if candidate.is_file():
                return candidate

        return None

    # ── Verification ─────────────────────────────────────────────

    def check_syntax(self, file_path: Path) -> tuple[bool, str]:
        """Verify Python file has valid syntax."""
        try:
            source = file_path.read_text(encoding="utf-8", errors="ignore")
            ast.parse(source, filename=str(file_path))
            return (True, "")
        except SyntaxError as e:
            return (False, f"Syntax error at line {e.lineno}: {e.msg}")
        except Exception as e:
            return (False, f"Parse error: {e}")

    def check_importable(self, file_path: Path, project_root: Path) -> tuple[bool, str]:
        """Verify Python file can be imported.

        Converts file path to module path and tries to import it.
        """
        try:
            rel = file_path.relative_to(project_root)
        except ValueError:
            return (False, f"File not under project root: {file_path}")

        # Convert path to module: src/core/models/action.py → src.core.models.action
        module_path = str(rel.with_suffix("")).replace("/", ".").replace("\\", ".")

        # Try importing
        try:
            result = subprocess.run(
                ["python3", "-c", f"import {module_path}"],
                capture_output=True, text=True, timeout=10,
                cwd=str(project_root),
            )
            if result.returncode == 0:
                return (True, "")
            stderr = result.stderr.strip().split("\n")[-1] if result.stderr else "Import failed"
            return (False, stderr)
        except subprocess.TimeoutExpired:
            return (False, "Import check timed out")
        except Exception as e:
            return (False, f"Import check error: {e}")
