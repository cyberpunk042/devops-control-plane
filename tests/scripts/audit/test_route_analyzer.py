"""Tests for route_analyzer module."""

import ast
import textwrap
from pathlib import Path

import pytest

from src.core.data.script_templates.audit.route_analyzer import (
    BlueprintInfo,
    FlaskRouteAnalyzer,
    RouteAuditResult,
    RouteInfo,
    detect_framework,
)


# ═══════════════════════════════════════════════════════════════════
#  RouteInfo
# ═══════════════════════════════════════════════════════════════════


def test_route_info_defaults():
    r = RouteInfo(
        function_name="index",
        endpoint="/",
        blueprint="main",
        file_path="routes/main.py",
        lineno=1,
        end_lineno=5,
    )
    assert r.has_docstring is False
    assert r.has_auth is False
    assert r.has_run_tracking is False
    assert r.has_error_handling is False
    assert r.methods_explicit is False
    assert r.return_type == "unknown"
    assert r.http_methods == []
    assert r.decorators == []


# ═══════════════════════════════════════════════════════════════════
#  BlueprintInfo
# ═══════════════════════════════════════════════════════════════════


def test_blueprint_info_total_routes():
    bp = BlueprintInfo(name="test", package_path="routes/test")
    assert bp.total_routes == 0

    bp.routes = [
        RouteInfo("a", "/a", "test", "f.py", 1, 2),
        RouteInfo("b", "/b", "test", "f.py", 3, 4),
    ]
    assert bp.total_routes == 2


# ═══════════════════════════════════════════════════════════════════
#  RouteAuditResult
# ═══════════════════════════════════════════════════════════════════


def test_audit_result_empty():
    result = RouteAuditResult(framework="test")
    assert result.total_routes == 0
    assert result.total_blueprints == 0
    assert result.coverage("has_auth") == (0, 0)


def test_audit_result_coverage():
    r1 = RouteInfo("a", "/a", "bp", "f.py", 1, 2, has_auth=True)
    r2 = RouteInfo("b", "/b", "bp", "f.py", 3, 4, has_auth=False)
    r3 = RouteInfo("c", "/c", "bp", "f.py", 5, 6, has_auth=True)

    bp = BlueprintInfo(name="bp", package_path="routes/bp", routes=[r1, r2, r3])
    result = RouteAuditResult(framework="test", blueprints=[bp])

    assert result.total_routes == 3
    assert result.coverage("has_auth") == (2, 3)
    assert result.coverage("has_docstring") == (0, 3)


# ═══════════════════════════════════════════════════════════════════
#  detect_framework
# ═══════════════════════════════════════════════════════════════════


def test_detect_framework_flask(tmp_path):
    routes = tmp_path / "src" / "ui" / "web" / "routes" / "main"
    routes.mkdir(parents=True)
    (routes / "__init__.py").write_text("bp = Blueprint('main', __name__)")
    assert detect_framework(tmp_path) == "flask"


def test_detect_framework_fastapi(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.py").write_text("app = FastAPI()")
    assert detect_framework(tmp_path) == "fastapi"


def test_detect_framework_express(tmp_path):
    (tmp_path / "package.json").write_text('{"dependencies": {"express": "4.0"}}')
    assert detect_framework(tmp_path) == "express"


def test_detect_framework_spring(tmp_path):
    (tmp_path / "pom.xml").write_text(
        "<project><dependency>spring-boot-starter</dependency></project>"
    )
    assert detect_framework(tmp_path) == "spring"


def test_detect_framework_unknown(tmp_path):
    assert detect_framework(tmp_path) == "unknown"


# ═══════════════════════════════════════════════════════════════════
#  FlaskRouteAnalyzer — _analyze_function
# ═══════════════════════════════════════════════════════════════════


def _parse_func(code: str) -> ast.FunctionDef:
    """Parse a string into a single FunctionDef node."""
    tree = ast.parse(textwrap.dedent(code))
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.FunctionDef):
            return node
    raise ValueError("No FunctionDef found")


def test_analyze_non_route():
    analyzer = FlaskRouteAnalyzer()
    func = _parse_func("""
def helper():
    return 42
""")
    result = analyzer._analyze_function(func, "test", "test.py")
    assert result is None


def test_analyze_simple_route():
    analyzer = FlaskRouteAnalyzer()
    func = _parse_func("""
@bp.route("/api/test")
def test_route():
    return jsonify({"ok": True})
""")
    result = analyzer._analyze_function(func, "test", "test.py")
    assert result is not None
    assert result.endpoint == "/api/test"
    assert result.http_methods == ["GET"]  # default
    assert result.methods_explicit is False
    assert result.has_docstring is False


def test_analyze_route_with_methods():
    analyzer = FlaskRouteAnalyzer()
    func = _parse_func("""
@bp.route("/api/test", methods=["POST"])
def test_route():
    return jsonify({"ok": True})
""")
    result = analyzer._analyze_function(func, "test", "test.py")
    assert result is not None
    assert result.http_methods == ["POST"]
    assert result.methods_explicit is True


def test_analyze_route_with_docstring():
    analyzer = FlaskRouteAnalyzer()
    func = _parse_func('''
@bp.route("/api/test")
def test_route():
    """This route does something.

    Multi-line docstring.
    """
    return jsonify({"ok": True})
''')
    result = analyzer._analyze_function(func, "test", "test.py")
    assert result is not None
    assert result.has_docstring is True
    assert result.docstring_lines >= 3


def test_analyze_route_with_auth():
    analyzer = FlaskRouteAnalyzer()
    func = _parse_func("""
@bp.route("/api/test")
@login_required
def test_route():
    return jsonify({"ok": True})
""")
    result = analyzer._analyze_function(func, "test", "test.py")
    assert result is not None
    assert result.has_auth is True
    assert "login_required" in result.decorators


def test_analyze_route_with_run_tracking():
    analyzer = FlaskRouteAnalyzer()
    func = _parse_func("""
@bp.route("/api/test")
@run_tracked
def test_route():
    return jsonify({"ok": True})
""")
    result = analyzer._analyze_function(func, "test", "test.py")
    assert result is not None
    assert result.has_run_tracking is True


def test_analyze_route_with_error_handling():
    analyzer = FlaskRouteAnalyzer()
    func = _parse_func("""
@bp.route("/api/test")
def test_route():
    try:
        result = do_something()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False}), 500
""")
    result = analyzer._analyze_function(func, "test", "test.py")
    assert result is not None
    assert result.has_error_handling is True


# ═══════════════════════════════════════════════════════════════════
#  FlaskRouteAnalyzer — _detect_return_type
# ═══════════════════════════════════════════════════════════════════


def test_return_type_json():
    analyzer = FlaskRouteAnalyzer()
    func = _parse_func("""
@bp.route("/test")
def t():
    return jsonify({"x": 1})
""")
    assert analyzer._detect_return_type(func) == "json"


def test_return_type_json_tuple():
    analyzer = FlaskRouteAnalyzer()
    func = _parse_func("""
@bp.route("/test")
def t():
    return jsonify({"x": 1}), 200
""")
    assert analyzer._detect_return_type(func) == "json"


def test_return_type_template():
    analyzer = FlaskRouteAnalyzer()
    func = _parse_func("""
@bp.route("/test")
def t():
    return render_template("page.html")
""")
    assert analyzer._detect_return_type(func) == "template"


def test_return_type_redirect():
    analyzer = FlaskRouteAnalyzer()
    func = _parse_func("""
@bp.route("/test")
def t():
    return redirect("/other")
""")
    assert analyzer._detect_return_type(func) == "redirect"


def test_return_type_file():
    analyzer = FlaskRouteAnalyzer()
    func = _parse_func("""
@bp.route("/test")
def t():
    return send_file("data.zip")
""")
    assert analyzer._detect_return_type(func) == "file"


def test_return_type_raw_response():
    analyzer = FlaskRouteAnalyzer()
    func = _parse_func("""
@bp.route("/test")
def t():
    return Response("raw data")
""")
    assert analyzer._detect_return_type(func) == "raw"


def test_return_type_stream():
    analyzer = FlaskRouteAnalyzer()
    func = _parse_func("""
@bp.route("/test")
def t():
    return Response(gen(), content_type="text/event-stream")
""")
    assert analyzer._detect_return_type(func) == "stream"


# ═══════════════════════════════════════════════════════════════════
#  FlaskRouteAnalyzer — full file analysis
# ═══════════════════════════════════════════════════════════════════


def test_analyze_file_with_routes(tmp_path):
    bp_dir = tmp_path / "src" / "ui" / "web" / "routes" / "test"
    bp_dir.mkdir(parents=True)

    (bp_dir / "__init__.py").write_text(textwrap.dedent("""
        from flask import Blueprint
        bp = Blueprint('test', __name__)
        from . import handlers
    """))

    (bp_dir / "handlers.py").write_text(textwrap.dedent('''
        from flask import jsonify

        @bp.route("/api/test/list")
        def test_list():
            """List all test items."""
            return jsonify({"items": []})

        @bp.route("/api/test/create", methods=["POST"])
        @run_tracked
        def test_create():
            """Create a test item."""
            return jsonify({"ok": True}), 201
    '''))

    analyzer = FlaskRouteAnalyzer()
    result = analyzer.analyze(tmp_path)

    assert result.framework == "flask"
    assert result.total_blueprints == 1
    assert result.total_routes == 2

    bp = result.blueprints[0]
    assert bp.name == "test"
    assert bp.init_has_route_handlers is False

    # Check individual routes
    route_names = {r.function_name for r in bp.routes}
    assert route_names == {"test_list", "test_create"}


def test_analyze_init_with_routes(tmp_path):
    """Detect when route handlers are in __init__.py (init leak)."""
    bp_dir = tmp_path / "src" / "ui" / "web" / "routes" / "simple"
    bp_dir.mkdir(parents=True)

    (bp_dir / "__init__.py").write_text(textwrap.dedent('''
        from flask import Blueprint, jsonify
        bp = Blueprint('simple', __name__)

        @bp.route("/api/simple/status")
        def simple_status():
            """Get status."""
            return jsonify({"ok": True})
    '''))

    analyzer = FlaskRouteAnalyzer()
    result = analyzer.analyze(tmp_path)

    assert result.total_routes == 1
    bp = result.blueprints[0]
    assert bp.init_has_route_handlers is True
    assert bp.init_lines > 0


# ═══════════════════════════════════════════════════════════════════
#  FlaskRouteAnalyzer — real project integration
# ═══════════════════════════════════════════════════════════════════


def test_analyze_real_project():
    """Integration test: analyze the actual project routes."""
    root = Path(".")
    if not (root / "src" / "ui" / "web" / "routes").is_dir():
        pytest.skip("Not in project root")

    analyzer = FlaskRouteAnalyzer()
    result = analyzer.analyze(root)

    # We know from investigation:
    # - 34+ blueprints
    # - 400+ routes
    # - 98%+ have docstrings
    assert result.total_blueprints >= 30
    assert result.total_routes >= 400

    # Docstring coverage should be high
    with_docs, total = result.coverage("has_docstring")
    assert with_docs / total > 0.95

    # Auth exists on some routes (not all — that's fine)
    with_auth, _ = result.coverage("has_auth")
    assert with_auth > 0

    # Tab mesh should be flagged as having init handlers
    tab_mesh = next(
        (bp for bp in result.blueprints if bp.name == "tab_mesh"), None,
    )
    assert tab_mesh is not None
    assert tab_mesh.init_has_route_handlers is True
    assert tab_mesh.init_lines > 500
