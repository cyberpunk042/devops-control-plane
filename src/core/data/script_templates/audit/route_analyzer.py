"""Route analyzer — framework-agnostic route detection and fact extraction.

This module provides:
- Universal data models for HTTP routes (framework-independent)
- A RouteAnalyzer protocol for pluggable framework support
- A detect_framework() function to auto-detect the web framework
- A FlaskRouteAnalyzer implementing the protocol for Flask/Blueprint projects

Design principle: OBSERVE, DON'T JUDGE.
The analyzer extracts facts about each route — what decorators it has,
whether it has a docstring, what HTTP methods it uses, etc.  It does NOT
assign scores or flag "violations".  That's the report layer's job, and
even then the report presents coverage metrics, not compliance grades.

Multi-language ready: the RouteAnalyzer protocol is framework-agnostic.
To add Express, FastAPI, Spring Boot, etc., implement a new analyzer class
that produces the same RouteInfo objects.
"""

from __future__ import annotations

import ast
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable


# ═══════════════════════════════════════════════════════════════════
#  Universal Data Models
# ═══════════════════════════════════════════════════════════════════


@dataclass
class RouteInfo:
    """Facts about a single HTTP endpoint.

    Every field is an observation — no field implies judgment.
    "has_auth = False" means "we did not detect an auth mechanism",
    not "this route is insecure".
    """

    # ── Identity ──
    function_name: str              # e.g. "vault_list"
    endpoint: str                   # e.g. "/api/vault/list"
    blueprint: str                  # e.g. "vault"
    file_path: str                  # Relative path to source file
    lineno: int                     # Start line in source
    end_lineno: int                 # End line in source

    # ── HTTP ──
    http_methods: list[str] = field(default_factory=list)
    methods_explicit: bool = False  # True if methods= kwarg was specified

    # ── Observations ──
    has_docstring: bool = False
    docstring_lines: int = 0
    has_auth: bool = False          # Detected auth decorator or check
    has_run_tracking: bool = False  # Detected observability / run tracking
    has_error_handling: bool = False # Detected try/except or receipt pattern
    return_type: str = "unknown"    # "json" | "template" | "redirect" | "stream" | "file" | "raw" | "unknown"

    # ── Raw decorator list (for framework-specific analysis) ──
    decorators: list[str] = field(default_factory=list)

    # ── Route contract ──
    url_params: list[str] = field(default_factory=list)        # <id>, <path> from endpoint
    request_params: list[dict] = field(default_factory=list)   # [{name, source, required}]
    response_codes: list[int] = field(default_factory=list)    # [200, 400, 404, 500]

    # ── Complexity metrics ──
    body_lines: int = 0             # Number of lines in the function body
    branch_count: int = 0           # if/elif/for/while count
    nesting_depth: int = 0          # Max nesting level

    # ── Dependencies ──
    service_calls: list[str] = field(default_factory=list)     # Top-level function calls


@dataclass
class BlueprintInfo:
    """Facts about one route group / blueprint / router.

    "Blueprint" is used generically — it maps to Flask Blueprint,
    Express Router, FastAPI APIRouter, etc.
    """

    name: str                       # Blueprint / router name
    package_path: str               # Path to package directory
    routes: list[RouteInfo] = field(default_factory=list)

    # ── Init file observations (for M6 cross-reference) ──
    init_lines: int = 0            # Lines in the __init__ / index file
    init_has_route_handlers: bool = False  # Route functions defined in init

    @property
    def total_routes(self) -> int:
        return len(self.routes)


@dataclass
class RouteAuditResult:
    """Complete route audit result — facts only, no scores."""

    framework: str                  # "flask" | "express" | "fastapi" | "unknown"
    blueprints: list[BlueprintInfo] = field(default_factory=list)

    @property
    def total_routes(self) -> int:
        return sum(bp.total_routes for bp in self.blueprints)

    @property
    def total_blueprints(self) -> int:
        return len(self.blueprints)

    def coverage(self, attribute: str) -> tuple[int, int]:
        """Count how many routes have a given boolean attribute.

        Returns (count_with, total).
        """
        total = 0
        with_attr = 0
        for bp in self.blueprints:
            for r in bp.routes:
                total += 1
                if getattr(r, attribute, False):
                    with_attr += 1
        return with_attr, total


# ═══════════════════════════════════════════════════════════════════
#  Protocol — implement this for each framework
# ═══════════════════════════════════════════════════════════════════


@runtime_checkable
class RouteAnalyzer(Protocol):
    """Protocol for framework-specific route analyzers.

    Each implementation knows how to detect routes in its framework
    and extract facts into the universal RouteInfo model.
    """

    @property
    def framework_name(self) -> str:
        """Human-readable framework name."""
        ...

    def analyze(self, root: Path) -> RouteAuditResult:
        """Analyze all routes under the given root path.

        Args:
            root: Project root directory.

        Returns:
            RouteAuditResult with all detected blueprints and routes.
        """
        ...


# ═══════════════════════════════════════════════════════════════════
#  Framework Detection
# ═══════════════════════════════════════════════════════════════════


def detect_framework(project_root: Path) -> str:
    """Auto-detect the web framework used in the project.

    Detection strategy (ordered by specificity):
    1. Look for Flask patterns (Blueprint imports, Flask app creation)
    2. Look for FastAPI patterns (FastAPI(), APIRouter)
    3. Look for Express patterns (express.Router(), package.json)
    4. Look for Spring Boot patterns (pom.xml with spring-boot)

    Returns:
        Framework identifier: "flask" | "fastapi" | "express" | "spring" | "unknown"
    """
    # ── Flask ──
    routes_dir = project_root / "src" / "ui" / "web" / "routes"
    if routes_dir.is_dir():
        # Check a sample __init__.py for Blueprint
        for init_file in routes_dir.rglob("__init__.py"):
            try:
                content = init_file.read_text(errors="replace")
                if "Blueprint" in content:
                    return "flask"
            except OSError:
                continue

    # ── FastAPI ──
    for pyfile in (project_root / "src").rglob("*.py") if (project_root / "src").is_dir() else []:
        try:
            content = pyfile.read_text(errors="replace")
            if "FastAPI(" in content or "APIRouter(" in content:
                return "fastapi"
        except OSError:
            continue

    # ── Express (Node.js) ──
    pkg_json = project_root / "package.json"
    if pkg_json.is_file():
        try:
            content = pkg_json.read_text(errors="replace")
            if "express" in content:
                return "express"
        except OSError:
            pass

    # ── Spring Boot (Java) ──
    pom = project_root / "pom.xml"
    if pom.is_file():
        try:
            content = pom.read_text(errors="replace")
            if "spring-boot" in content:
                return "spring"
        except OSError:
            pass

    return "unknown"


# ═══════════════════════════════════════════════════════════════════
#  Flask Analyzer
# ═══════════════════════════════════════════════════════════════════


# Decorators recognized as auth mechanisms
_AUTH_DECORATORS = frozenset({
    "login_required",
    "requires_gh_auth",
    "requires_git_auth",
    "auth_required",
    "jwt_required",
    "token_required",
    "api_key_required",
})

# Decorators recognized as run tracking / observability
_TRACKING_DECORATORS = frozenset({
    "run_tracked",
    "traced",
    "monitored",
})


class FlaskRouteAnalyzer:
    """Analyze Flask Blueprint-based route structures.

    Expects the conventional layout:
        src/ui/web/routes/<blueprint>/__init__.py  (Blueprint definition)
        src/ui/web/routes/<blueprint>/<module>.py   (Route handlers)
    """

    @property
    def framework_name(self) -> str:
        return "Flask"

    def analyze(
        self,
        root: Path,
        *,
        routes_path: str = "src/ui/web/routes",
    ) -> RouteAuditResult:
        """Analyze all Flask blueprints and routes.

        Args:
            root: Project root directory.
            routes_path: Relative path to route blueprints from root.

        Returns:
            RouteAuditResult with all detected blueprints and routes.
        """
        routes_dir = root / routes_path
        if not routes_dir.is_dir():
            return RouteAuditResult(framework="flask")

        blueprints: list[BlueprintInfo] = []

        # Each subdirectory with an __init__.py is a potential blueprint
        for bp_dir in sorted(routes_dir.iterdir()):
            if not bp_dir.is_dir():
                continue
            init_file = bp_dir / "__init__.py"
            if not init_file.is_file():
                continue
            if bp_dir.name.startswith("__"):
                continue

            bp_info = self._analyze_blueprint(bp_dir, root)
            if bp_info.total_routes > 0 or bp_info.init_has_route_handlers:
                blueprints.append(bp_info)

        return RouteAuditResult(
            framework="flask",
            blueprints=blueprints,
        )

    def _analyze_blueprint(
        self,
        bp_dir: Path,
        project_root: Path,
    ) -> BlueprintInfo:
        """Analyze a single blueprint package."""
        bp_name = bp_dir.name
        bp_info = BlueprintInfo(
            name=bp_name,
            package_path=str(bp_dir.relative_to(project_root)),
        )

        # Analyze all .py files in the blueprint directory
        for pyfile in sorted(bp_dir.glob("*.py")):
            if pyfile.name.startswith("__pycache__"):
                continue

            is_init = pyfile.name == "__init__.py"
            routes = self._analyze_file(pyfile, bp_name, project_root)

            if is_init:
                try:
                    bp_info.init_lines = len(pyfile.read_text().splitlines())
                except OSError:
                    pass
                if routes:
                    bp_info.init_has_route_handlers = True

            bp_info.routes.extend(routes)

        return bp_info

    def _analyze_file(
        self,
        pyfile: Path,
        bp_name: str,
        project_root: Path,
    ) -> list[RouteInfo]:
        """Extract route facts from a single Python file."""
        try:
            source = pyfile.read_text()
            tree = ast.parse(source, filename=str(pyfile))
        except (OSError, SyntaxError):
            return []

        rel_path = str(pyfile.relative_to(project_root))
        routes: list[RouteInfo] = []

        for node in ast.iter_child_nodes(tree):
            if not isinstance(node, ast.FunctionDef):
                continue

            route_info = self._analyze_function(node, bp_name, rel_path)
            if route_info is not None:
                routes.append(route_info)

        return routes

    def _analyze_function(
        self,
        node: ast.FunctionDef,
        bp_name: str,
        file_path: str,
    ) -> RouteInfo | None:
        """Analyze a single function definition for route facts.

        Returns None if the function is not a route handler.
        """
        # ── Check decorators ──
        is_route = False
        endpoint = ""
        http_methods: list[str] = []
        methods_explicit = False
        decorator_names: list[str] = []
        has_auth = False
        has_tracking = False

        for deco in node.decorator_list:
            deco_name, deco_detail = self._parse_decorator(deco)
            if not deco_name:
                continue

            decorator_names.append(deco_name)

            if deco_name == "route" and isinstance(deco, ast.Call):
                is_route = True
                # Extract endpoint path
                if deco.args and isinstance(deco.args[0], ast.Constant):
                    endpoint = str(deco.args[0].value)
                # Extract methods
                for kw in deco.keywords:
                    if kw.arg == "methods" and isinstance(kw.value, ast.List):
                        methods_explicit = True
                        for elt in kw.value.elts:
                            if isinstance(elt, ast.Constant):
                                http_methods.append(str(elt.value))

            if deco_name in _AUTH_DECORATORS:
                has_auth = True

            if deco_name in _TRACKING_DECORATORS:
                has_tracking = True

        if not is_route:
            return None

        # Default method is GET when not specified
        if not http_methods:
            http_methods = ["GET"]

        # ── Check docstring ──
        has_docstring = False
        docstring_lines = 0
        if (
            node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        ):
            has_docstring = True
            docstring_lines = node.body[0].value.value.count("\n") + 1

        # ── Check error handling ──
        has_error_handling = any(
            isinstance(n, ast.Try) for n in ast.walk(node)
        )

        # ── Detect return type ──
        return_type = self._detect_return_type(node)

        # ── Body size ──
        body_lines = (node.end_lineno or node.lineno) - node.lineno

        # ── URL params ──
        url_params = re.findall(r"<(?:\w+:)?([\w]+)>", endpoint) if endpoint else []

        # ── Request params ──
        request_params = self._extract_request_params(node)

        # ── Response codes ──
        response_codes = self._extract_response_codes(node)

        # ── Complexity ──
        branch_count = self._count_branches(node)
        nesting_depth = self._max_nesting_depth(node)

        # ── Service calls ──
        service_calls = self._extract_service_calls(node)

        return RouteInfo(
            function_name=node.name,
            endpoint=endpoint,
            blueprint=bp_name,
            file_path=file_path,
            lineno=node.lineno,
            end_lineno=node.end_lineno or node.lineno,
            http_methods=http_methods,
            methods_explicit=methods_explicit,
            has_docstring=has_docstring,
            docstring_lines=docstring_lines,
            has_auth=has_auth,
            has_run_tracking=has_tracking,
            has_error_handling=has_error_handling,
            return_type=return_type,
            decorators=decorator_names,
            url_params=url_params,
            request_params=request_params,
            response_codes=response_codes,
            body_lines=body_lines,
            branch_count=branch_count,
            nesting_depth=nesting_depth,
            service_calls=service_calls,
        )

    # ── Helper methods ──

    @staticmethod
    def _parse_decorator(
        deco: ast.expr,
    ) -> tuple[str, str]:
        """Extract decorator name and detail string.

        Returns (name, detail) where detail is the full decorator text
        for diagnostics.
        """
        if isinstance(deco, ast.Call):
            func = deco.func
            if isinstance(func, ast.Attribute):
                return func.attr, f"{func.attr}(...)"
            if isinstance(func, ast.Name):
                return func.id, f"{func.id}(...)"
        elif isinstance(deco, ast.Attribute):
            return deco.attr, deco.attr
        elif isinstance(deco, ast.Name):
            return deco.id, deco.id
        return "", ""

    @staticmethod
    def _detect_return_type(node: ast.FunctionDef) -> str:
        """Detect the return type pattern of a route function.

        Looks at return statements for common patterns:
        - jsonify(...) → "json"
        - render_template(...) → "template"
        - redirect(...) → "redirect"
        - send_file(...) → "file"
        - Response(...) with event-stream → "stream"
        - Response(...) → "raw"
        """
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Return) or sub.value is None:
                continue

            # Handle return value directly or as tuple (jsonify(...), 200)
            values_to_check = []
            if isinstance(sub.value, ast.Tuple):
                values_to_check.extend(sub.value.elts)
            else:
                values_to_check.append(sub.value)

            for val in values_to_check:
                if not isinstance(val, ast.Call):
                    continue
                func_name = ""
                if isinstance(val.func, ast.Name):
                    func_name = val.func.id
                elif isinstance(val.func, ast.Attribute):
                    func_name = val.func.attr

                if func_name == "jsonify":
                    return "json"
                if func_name == "render_template":
                    return "template"
                if func_name == "redirect":
                    return "redirect"
                if func_name == "send_file":
                    return "file"
                if func_name == "Response":
                    # Check for streaming
                    for kw in val.keywords:
                        if kw.arg == "content_type":
                            if (
                                isinstance(kw.value, ast.Constant)
                                and "event-stream" in str(kw.value.value)
                            ):
                                return "stream"
                    return "raw"

        return "unknown"

    @staticmethod
    def _extract_request_params(node: ast.FunctionDef) -> list[dict]:
        """Extract request parameters from the function body.

        Detects patterns:
        - request.args.get('name') → {name, source: 'query', required: False}
        - request.args['name']     → {name, source: 'query', required: True}
        - request.json['name']     → {name, source: 'body', required: True}
        - request.json.get('name') → {name, source: 'body', required: False}
        - request.form['name']     → {name, source: 'form', required: True}
        - request.form.get('name') → {name, source: 'form', required: False}
        - body = request.json; body.get('name') / body['name']  (alias pattern)
        """
        source_map = {"args": "query", "json": "body", "form": "form"}
        params: list[dict] = []
        seen: set[str] = set()

        # Pass 1: find aliases like `body = request.json`, `data = request.form`
        aliases: dict[str, str] = {}  # var_name -> source (query/body/form)
        for sub in ast.walk(node):
            if (
                isinstance(sub, ast.Assign)
                and len(sub.targets) == 1
                and isinstance(sub.targets[0], ast.Name)
                and isinstance(sub.value, ast.Attribute)
                and isinstance(sub.value.value, ast.Name)
                and sub.value.value.id == "request"
                and sub.value.attr in source_map
            ):
                aliases[sub.targets[0].id] = source_map[sub.value.attr]

        # Pass 2: extract params from direct and aliased access
        for sub in ast.walk(node):
            # Pattern: request.args.get('name') / request.json.get('name')
            if (
                isinstance(sub, ast.Call)
                and isinstance(sub.func, ast.Attribute)
                and sub.func.attr == "get"
            ):
                source = None
                # Direct: request.json.get('name')
                if (
                    isinstance(sub.func.value, ast.Attribute)
                    and isinstance(sub.func.value.value, ast.Name)
                    and sub.func.value.value.id == "request"
                ):
                    source = source_map.get(sub.func.value.attr)
                # Alias: body.get('name') where body = request.json
                elif (
                    isinstance(sub.func.value, ast.Name)
                    and sub.func.value.id in aliases
                ):
                    source = aliases[sub.func.value.id]

                if source and sub.args and isinstance(sub.args[0], ast.Constant):
                    name = str(sub.args[0].value)
                    key = f"{source}:{name}"
                    if key not in seen:
                        seen.add(key)
                        params.append({"name": name, "source": source, "required": False})

            # Pattern: request.args['name'] / request.json['name']
            if isinstance(sub, ast.Subscript):
                source = None
                # Direct: request.json['name']
                if (
                    isinstance(sub.value, ast.Attribute)
                    and isinstance(sub.value.value, ast.Name)
                    and sub.value.value.id == "request"
                ):
                    source = source_map.get(sub.value.attr)
                # Alias: body['name'] where body = request.json
                elif (
                    isinstance(sub.value, ast.Name)
                    and sub.value.id in aliases
                ):
                    source = aliases[sub.value.id]

                if source and isinstance(sub.slice, ast.Constant):
                    name = str(sub.slice.value)
                    key = f"{source}:{name}"
                    if key not in seen:
                        seen.add(key)
                        params.append({"name": name, "source": source, "required": True})

        return params

    @staticmethod
    def _extract_response_codes(node: ast.FunctionDef) -> list[int]:
        """Extract HTTP response status codes from return statements.

        Detects: return jsonify(...), 400
        """
        codes: set[int] = set()
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Return) or sub.value is None:
                continue
            if isinstance(sub.value, ast.Tuple) and len(sub.value.elts) >= 2:
                last = sub.value.elts[-1]
                if isinstance(last, ast.Constant) and isinstance(last.value, int):
                    codes.add(last.value)
        return sorted(codes)

    @staticmethod
    def _extract_service_calls(node: ast.FunctionDef) -> list[str]:
        """Extract top-level function/method calls in the route body.

        Captures the callable name for dependency analysis.
        Skips common builtins, framework calls, and non-service methods.
        """
        # Root names to skip (first segment of dotted calls)
        skip_roots = frozenset({
            "jsonify", "request", "redirect", "render_template",
            "send_file", "Response", "abort", "url_for",
            "str", "int", "float", "bool", "len", "dict", "list",
            "set", "tuple", "print", "isinstance", "getattr",
            "setattr", "hasattr", "sorted", "enumerate", "zip",
            "range", "any", "all", "min", "max", "sum",
            "os", "json", "Path", "datetime", "logging", "logger",
            "threading",
        })
        # Suffixes to skip (non-service method calls)
        skip_suffixes = frozenset({
            ".route", ".get", ".set", ".append", ".extend",
            ".strip", ".split", ".join", ".replace", ".lower",
            ".upper", ".startswith", ".endswith", ".format",
            ".items", ".keys", ".values", ".update", ".pop",
            ".add", ".remove", ".copy", ".encode", ".decode",
            ".model_dump", ".model_validate",
        })
        calls: list[str] = []
        seen: set[str] = set()

        for sub in ast.walk(node):
            if not isinstance(sub, ast.Call):
                continue
            name = ""
            if isinstance(sub.func, ast.Name):
                name = sub.func.id
            elif isinstance(sub.func, ast.Attribute):
                # Get the full dotted name for method calls
                parts = []
                obj = sub.func
                while isinstance(obj, ast.Attribute):
                    parts.append(obj.attr)
                    obj = obj.value
                if isinstance(obj, ast.Name):
                    parts.append(obj.id)
                parts.reverse()
                name = ".".join(parts)

            if not name or name in seen:
                continue
            # Skip by root name
            if name.split(".")[0] in skip_roots:
                continue
            # Skip by suffix
            if any(name.endswith(s) for s in skip_suffixes):
                continue
            seen.add(name)
            calls.append(name)

        return calls

    @staticmethod
    def _count_branches(node: ast.FunctionDef) -> int:
        """Count branching statements (if/elif/for/while/try)."""
        count = 0
        for sub in ast.walk(node):
            if isinstance(sub, (ast.If, ast.For, ast.While, ast.Try)):
                count += 1
        return count

    @staticmethod
    def _max_nesting_depth(node: ast.FunctionDef) -> int:
        """Calculate maximum nesting depth of the function body."""
        def _depth(n: ast.AST, current: int) -> int:
            max_d = current
            for child in ast.iter_child_nodes(n):
                if isinstance(child, (ast.If, ast.For, ast.While, ast.Try, ast.With)):
                    max_d = max(max_d, _depth(child, current + 1))
                else:
                    max_d = max(max_d, _depth(child, current))
            return max_d
        return _depth(node, 0)
