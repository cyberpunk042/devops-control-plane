"""API route scanner — AST-based extraction of Flask route metadata.

This module provides:
- RouteInfo: complete metadata for a single HTTP route
- BlueprintInfo: blueprint name, prefix, variable name
- ApiRouteScanner: scans server.py + route files to build a full API map

Extraction capabilities:
- Route path, methods, function name, docstring
- Blueprint prefix resolution (from server.py register_blueprint calls)
- Request body field inference (data.get("key", default) patterns)
- Response type detection (jsonify, stream, redirect)
- Path parameter extraction (<type:name> patterns)
- Error response detection (return jsonify({...}), 4xx patterns)

Design principle: static analysis only — no Flask import required.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path


# ═══════════════════════════════════════════════════════════════════
#  Data Models
# ═══════════════════════════════════════════════════════════════════


@dataclass
class RequestField:
    """A field read from the request body."""

    name: str
    default: object = None          # None means required (no default)
    has_default: bool = False
    inferred_type: str = "string"   # "string", "integer", "boolean", "array", "object"
    required: bool = True


@dataclass
class PathParam:
    """A parameter extracted from the route path."""

    name: str
    type: str = "string"  # "string", "int", "float", "path"


@dataclass
class ErrorResponse:
    """An error response returned by the route."""

    status_code: int
    message: str = ""


@dataclass
class RouteInfo:
    """Complete metadata for a single HTTP endpoint."""

    # Identity
    file: str                               # relative path
    function_name: str
    blueprint_name: str = ""

    # HTTP
    path: str = ""                          # as declared in @bp.route
    full_path: str = ""                     # with blueprint prefix resolved
    methods: list[str] = field(default_factory=lambda: ["GET"])

    # Documentation
    docstring: str = ""
    summary: str = ""                       # first line of docstring
    description: str = ""                   # rest of docstring

    # Request
    path_params: list[PathParam] = field(default_factory=list)
    request_fields: list[RequestField] = field(default_factory=list)
    reads_json_body: bool = False
    reads_query_args: bool = False

    # Response
    response_type: str = "json"             # "json", "stream", "redirect", "html", "file"
    is_streaming: bool = False
    error_responses: list[ErrorResponse] = field(default_factory=list)

    # Meta
    lineno: int = 0
    tags: list[str] = field(default_factory=list)   # derived from module


@dataclass
class BlueprintInfo:
    """Blueprint registration metadata."""

    variable_name: str          # e.g. "docker_bp"
    blueprint_name: str         # e.g. "docker"
    register_prefix: str = ""   # e.g. "/api" (from register_blueprint)
    own_prefix: str = ""        # e.g. "/api/artifacts" (from Blueprint(..., url_prefix=...))
    source_file: str = ""

    @property
    def effective_prefix(self) -> str:
        """The actual URL prefix used at runtime."""
        if self.own_prefix:
            return self.own_prefix
        return self.register_prefix


@dataclass
class ApiCatalog:
    """Complete API catalog — all routes with resolved paths."""

    routes: list[RouteInfo] = field(default_factory=list)
    blueprints: list[BlueprintInfo] = field(default_factory=list)
    files_scanned: int = 0
    timestamp: str = ""

    @property
    def modules(self) -> list[str]:
        """Unique module tags across all routes."""
        return sorted(set(t for r in self.routes for t in r.tags))

    @property
    def by_module(self) -> dict[str, list[RouteInfo]]:
        """Routes grouped by primary tag (module)."""
        from collections import defaultdict
        groups: dict[str, list[RouteInfo]] = defaultdict(list)
        for r in self.routes:
            tag = r.tags[0] if r.tags else "other"
            groups[tag].append(r)
        return dict(sorted(groups.items()))


# ═══════════════════════════════════════════════════════════════════
#  Scanner
# ═══════════════════════════════════════════════════════════════════


class ApiRouteScanner:
    """Scans Flask route files via AST to build a complete API catalog."""

    def __init__(self, *, source_dir: str = "src"):
        self.source_dir = source_dir

    def scan(self, project_root: Path) -> ApiCatalog:
        """Scan all route files and build the API catalog.

        1. Parse server.py to extract blueprint registrations
        2. Scan each route file for @bp.route decorators
        3. Resolve full paths using blueprint prefixes
        4. Extract request/response metadata
        """
        catalog = ApiCatalog()

        routes_dir = project_root / self.source_dir / "ui" / "web" / "routes"
        server_file = project_root / self.source_dir / "ui" / "web" / "server.py"

        if not routes_dir.is_dir():
            return catalog

        # Step 1: Parse blueprint registrations
        bp_map = self._parse_blueprint_registrations(server_file, routes_dir)
        catalog.blueprints = list(bp_map.values())

        # Step 2: Scan route files
        for py_file in sorted(routes_dir.rglob("*.py")):
            if "__pycache__" in str(py_file):
                continue
            rel = str(py_file.relative_to(project_root))
            try:
                source = py_file.read_text(errors="replace")
                tree = ast.parse(source)
            except (SyntaxError, UnicodeDecodeError):
                continue

            catalog.files_scanned += 1

            # Find the blueprint variable used in this file
            file_bp_var = self._find_file_blueprint_var(tree)
            file_bp_info = bp_map.get(file_bp_var) if file_bp_var else None

            # Derive module tag from directory
            rel_to_routes = py_file.relative_to(routes_dir)
            module_tag = str(rel_to_routes.parts[0]) if len(rel_to_routes.parts) > 1 else rel_to_routes.stem

            # Extract routes
            for route in self._extract_routes(tree, rel, file_bp_info, module_tag):
                catalog.routes.append(route)

        # Sort routes by full_path for consistent output
        catalog.routes.sort(key=lambda r: (r.full_path, r.methods))

        return catalog

    # ── Blueprint Registration Parser ─────────────────────────────

    def _parse_blueprint_registrations(
        self,
        server_file: Path,
        routes_dir: Path,
    ) -> dict[str, BlueprintInfo]:
        """Parse server.py to extract blueprint variable → prefix mapping.

        Also scans Blueprint(..., url_prefix=...) definitions in route files.
        Returns: dict of variable_name → BlueprintInfo
        """
        bp_map: dict[str, BlueprintInfo] = {}

        # Step 1: Read server.py for register_blueprint calls
        if server_file.is_file():
            try:
                tree = ast.parse(server_file.read_text(errors="replace"))
            except SyntaxError:
                tree = ast.Module(body=[])

            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                if not isinstance(node.func, ast.Attribute):
                    continue
                if node.func.attr != "register_blueprint":
                    continue
                if not node.args:
                    continue

                # First arg is the blueprint variable
                bp_arg = node.args[0]
                if isinstance(bp_arg, ast.Name):
                    var_name = bp_arg.id
                elif isinstance(bp_arg, ast.Attribute):
                    var_name = bp_arg.attr
                else:
                    continue

                # Extract url_prefix keyword
                prefix = ""
                for kw in node.keywords:
                    if kw.arg == "url_prefix":
                        try:
                            prefix = ast.literal_eval(kw.value)
                        except (ValueError, TypeError):
                            pass

                bp_map[var_name] = BlueprintInfo(
                    variable_name=var_name,
                    blueprint_name=var_name.replace("_bp", ""),
                    register_prefix=prefix,
                )

        # Step 2: Scan route files for Blueprint(..., url_prefix=...)
        for py_file in routes_dir.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue
            try:
                tree = ast.parse(py_file.read_text(errors="replace"))
            except (SyntaxError, UnicodeDecodeError):
                continue

            for node in ast.walk(tree):
                if not isinstance(node, ast.Assign):
                    continue
                if not isinstance(node.value, ast.Call):
                    continue
                if not isinstance(node.value.func, ast.Name):
                    continue
                if node.value.func.id != "Blueprint":
                    continue
                if not node.targets or not isinstance(node.targets[0], ast.Name):
                    continue

                var_name = node.targets[0].id
                bp_name = ""
                own_prefix = ""

                # Extract blueprint name (first arg)
                if node.value.args:
                    try:
                        bp_name = ast.literal_eval(node.value.args[0])
                    except (ValueError, TypeError):
                        pass

                # Extract url_prefix keyword
                for kw in node.value.keywords:
                    if kw.arg == "url_prefix":
                        try:
                            own_prefix = ast.literal_eval(kw.value)
                        except (ValueError, TypeError):
                            pass

                if var_name in bp_map:
                    bp_map[var_name].blueprint_name = bp_name or bp_map[var_name].blueprint_name
                    bp_map[var_name].own_prefix = own_prefix
                    bp_map[var_name].source_file = str(py_file)
                else:
                    bp_map[var_name] = BlueprintInfo(
                        variable_name=var_name,
                        blueprint_name=bp_name or var_name.replace("_bp", ""),
                        own_prefix=own_prefix,
                        source_file=str(py_file),
                    )

        return bp_map

    def _find_file_blueprint_var(self, tree: ast.Module) -> str | None:
        """Find the blueprint variable name used in this file.

        Looks for patterns like:
        - bp = Blueprint(...)
        - docker_bp = Blueprint(...)
        - from . import docker_bp (and variations)
        """
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Assign):
                if isinstance(node.value, ast.Call):
                    if isinstance(node.value.func, ast.Name):
                        if node.value.func.id == "Blueprint":
                            if node.targets and isinstance(node.targets[0], ast.Name):
                                return node.targets[0].id
        # Fallback: look for any variable ending in _bp used in decorators
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == "route":
                    if isinstance(node.func.value, ast.Name):
                        return node.func.value.id
        return None

    # ── Route Extraction ──────────────────────────────────────────

    def _extract_routes(
        self,
        tree: ast.Module,
        filepath: str,
        bp_info: BlueprintInfo | None,
        module_tag: str,
    ) -> list[RouteInfo]:
        """Extract all @bp.route decorated functions from a file."""
        routes: list[RouteInfo] = []

        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue

            for dec in node.decorator_list:
                if not isinstance(dec, ast.Call):
                    continue
                if not isinstance(dec.func, ast.Attribute):
                    continue
                if dec.func.attr != "route":
                    continue
                if not dec.args:
                    continue

                # Extract path
                try:
                    path = ast.literal_eval(dec.args[0])
                except (ValueError, TypeError):
                    path = str(dec.args[0]) if dec.args else "?"

                # Extract methods
                methods = ["GET"]
                for kw in dec.keywords:
                    if kw.arg == "methods":
                        try:
                            methods = ast.literal_eval(kw.value)
                        except (ValueError, TypeError):
                            pass

                # Resolve full path
                prefix = bp_info.effective_prefix if bp_info else ""
                full_path = prefix.rstrip("/") + "/" + path.lstrip("/") if prefix else path

                # Extract docstring
                docstring = ""
                summary = ""
                description = ""
                if (
                    node.body
                    and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)
                ):
                    docstring = node.body[0].value.value.strip()
                    lines = docstring.split("\n")
                    summary = lines[0].strip()
                    if len(lines) > 1:
                        description = "\n".join(l.strip() for l in lines[1:]).strip()

                # Extract path parameters
                path_params = _extract_path_params(path)

                # Extract request body fields
                request_fields, reads_json, reads_args = (
                    self._extract_request_fields(node)
                )

                # Detect response type
                response_type, is_streaming = self._detect_response_type(node)

                # Extract error responses
                error_responses = self._extract_error_responses(node)

                route = RouteInfo(
                    file=filepath,
                    function_name=node.name,
                    blueprint_name=bp_info.blueprint_name if bp_info else "",
                    path=path,
                    full_path=full_path,
                    methods=methods,
                    docstring=docstring,
                    summary=summary,
                    description=description,
                    path_params=path_params,
                    request_fields=request_fields,
                    reads_json_body=reads_json,
                    reads_query_args=reads_args,
                    response_type=response_type,
                    is_streaming=is_streaming,
                    error_responses=error_responses,
                    lineno=node.lineno,
                    tags=[module_tag],
                )
                routes.append(route)

        return routes

    # ── Request Body Inference ────────────────────────────────────

    def _extract_request_fields(
        self,
        func_node: ast.FunctionDef,
    ) -> tuple[list[RequestField], bool, bool]:
        """Extract request body fields from data.get("key", default) patterns.

        Also detects request.get_json() and request.args usage.

        Returns: (fields, reads_json, reads_query_args)
        """
        reads_json = False
        reads_args = False
        fields: list[RequestField] = []
        seen_names: set[str] = set()

        func_source = ast.dump(func_node)
        if "get_json" in func_source or "request.json" in func_source:
            reads_json = True
        if "request.args" in func_source:
            reads_args = True

        # Find the variable that holds request.get_json() result
        json_vars: set[str] = set()
        for child in ast.walk(func_node):
            if isinstance(child, ast.Assign):
                if isinstance(child.value, ast.Call):
                    if isinstance(child.value.func, ast.Attribute):
                        if child.value.func.attr == "get_json":
                            for t in child.targets:
                                if isinstance(t, ast.Name):
                                    json_vars.add(t.id)
                # Also: data = request.json
                if isinstance(child.value, ast.Attribute):
                    if (
                        isinstance(child.value.value, ast.Name)
                        and child.value.value.id == "request"
                        and child.value.attr == "json"
                    ):
                        for t in child.targets:
                            if isinstance(t, ast.Name):
                                json_vars.add(t.id)

        if not json_vars:
            json_vars = {"data", "body", "payload"}  # common conventions

        # Find data.get("key", default) calls
        for child in ast.walk(func_node):
            if not isinstance(child, ast.Call):
                continue
            if not isinstance(child.func, ast.Attribute):
                continue
            if child.func.attr != "get":
                continue
            if not isinstance(child.func.value, ast.Name):
                continue
            if child.func.value.id not in json_vars:
                continue
            if not child.args:
                continue

            try:
                field_name = ast.literal_eval(child.args[0])
            except (ValueError, TypeError):
                continue

            if not isinstance(field_name, str):
                continue
            if field_name in seen_names:
                continue
            seen_names.add(field_name)

            has_default = len(child.args) >= 2
            default_val = None
            inferred_type = "string"

            if has_default:
                try:
                    default_val = ast.literal_eval(child.args[1])
                    inferred_type = _infer_type(default_val)
                except (ValueError, TypeError):
                    default_val = None
                    inferred_type = "string"

            fields.append(RequestField(
                name=field_name,
                default=default_val,
                has_default=has_default,
                inferred_type=inferred_type,
                required=not has_default,
            ))

        # Also check data["key"] direct subscript access
        for child in ast.walk(func_node):
            if not isinstance(child, ast.Subscript):
                continue
            if not isinstance(child.value, ast.Name):
                continue
            if child.value.id not in json_vars:
                continue
            if isinstance(child.slice, ast.Constant) and isinstance(child.slice.value, str):
                field_name = child.slice.value
                if field_name not in seen_names:
                    seen_names.add(field_name)
                    fields.append(RequestField(
                        name=field_name,
                        required=True,
                        inferred_type="string",
                    ))

        return fields, reads_json, reads_args

    # ── Response Type Detection ───────────────────────────────────

    def _detect_response_type(
        self,
        func_node: ast.FunctionDef,
    ) -> tuple[str, bool]:
        """Detect the response type of a route handler.

        Returns: (response_type, is_streaming)
        """
        func_dump = ast.dump(func_node)

        is_streaming = (
            "stream_with_context" in func_dump
            or "generate()" in func_dump
            or "Response(" in func_dump and "mimetype" in func_dump
        )

        if is_streaming:
            return "stream", True

        if "send_file" in func_dump or "send_from_directory" in func_dump:
            return "file", False

        if "redirect" in func_dump:
            return "redirect", False

        if "render_template" in func_dump:
            return "html", False

        if "jsonify" in func_dump:
            return "json", False

        return "json", False  # default

    # ── Error Response Extraction ─────────────────────────────────

    def _extract_error_responses(
        self,
        func_node: ast.FunctionDef,
    ) -> list[ErrorResponse]:
        """Extract error responses (return jsonify({...}), 4xx)."""
        errors: list[ErrorResponse] = []
        seen_codes: set[int] = set()

        for node in ast.walk(func_node):
            if not isinstance(node, ast.Return):
                continue
            if not isinstance(node.value, ast.Tuple):
                continue
            if len(node.value.elts) < 2:
                continue

            # Check for status code
            code_node = node.value.elts[-1]
            if not isinstance(code_node, ast.Constant):
                continue
            if not isinstance(code_node.value, int):
                continue

            code = code_node.value
            if code < 400:
                continue
            if code in seen_codes:
                continue
            seen_codes.add(code)

            # Try to extract error message from jsonify({"error": "..."})
            msg = ""
            resp_node = node.value.elts[0]
            if isinstance(resp_node, ast.Call):
                if resp_node.args and isinstance(resp_node.args[0], ast.Dict):
                    for key, val in zip(resp_node.args[0].keys, resp_node.args[0].values):
                        if (
                            isinstance(key, ast.Constant)
                            and key.value == "error"
                            and isinstance(val, ast.Constant)
                        ):
                            msg = str(val.value)

            errors.append(ErrorResponse(status_code=code, message=msg))

        return sorted(errors, key=lambda e: e.status_code)


# ═══════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════


def _extract_path_params(path: str) -> list[PathParam]:
    """Extract path parameters from a Flask route path.

    Example: "/docker/<action>/<int:container_id>"
    → [PathParam("action", "string"), PathParam("container_id", "int")]
    """
    params = []
    for match in re.finditer(r"<(?:(\w+):)?(\w+)>", path):
        ptype = match.group(1) or "string"
        pname = match.group(2)
        params.append(PathParam(name=pname, type=ptype))
    return params


def _infer_type(value: object) -> str:
    """Infer OpenAPI type from a Python default value."""
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "string"
