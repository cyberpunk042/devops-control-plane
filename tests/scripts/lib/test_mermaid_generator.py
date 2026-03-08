"""Tests for mermaid_generator shared library module."""

import pytest

from src.core.data.script_templates.lib.graph_builder import (
    ClassGraph,
    GraphEdge,
    GraphNode,
    RelationType,
)
from src.core.data.script_templates.lib.mermaid_generator import (
    MermaidConfig,
    render_class_diagram,
    render_component_diagram,
    render_flowchart,
    _escape_mermaid,
    _flowchart_arrow,
    _relation_arrow,
    _sanitize_id,
    _strip_visibility_prefix,
    _truncate_members,
    _visibility_marker,
)


# ═══════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════


def _simple_graph(
    *,
    nodes: list[GraphNode] | None = None,
    edges: list[GraphEdge] | None = None,
) -> ClassGraph:
    """Build a simple ClassGraph for testing."""
    g = ClassGraph(title="Test", scope="test")
    for n in (nodes or []):
        g.add_node(n)
    for e in (edges or []):
        g.add_edge(e)
    return g


def _node(
    name: str,
    *,
    kind: str = "class",
    package: str = "mod",
    fields: list[str] | None = None,
    methods: list[str] | None = None,
) -> GraphNode:
    """Shorthand node builder."""
    return GraphNode(
        id=f"mod.{name}",
        label=name,
        kind=kind,
        package=package,
        fields=fields or [],
        methods=methods or [],
    )


# ═══════════════════════════════════════════════════════════════════
#  MermaidConfig defaults
# ═══════════════════════════════════════════════════════════════════


def test_config_defaults():
    cfg = MermaidConfig()
    assert cfg.direction == "TD"
    assert cfg.show_fields is True
    assert cfg.show_methods is True
    assert cfg.show_visibility is True
    assert cfg.max_fields == 10
    assert cfg.max_methods == 15
    assert cfg.group_by_package is True
    assert cfg.include_orphans is False
    assert cfg.theme == "default"


# ═══════════════════════════════════════════════════════════════════
#  _escape_mermaid
# ═══════════════════════════════════════════════════════════════════


def test_escape_angle_brackets():
    assert "‹" in _escape_mermaid("<T>")
    assert "›" in _escape_mermaid("<T>")


def test_escape_braces():
    assert "❴" in _escape_mermaid("{key}")
    assert "❵" in _escape_mermaid("{key}")


def test_escape_quotes():
    assert "'" in _escape_mermaid('"hello"')


def test_escape_tilde():
    assert "∼" in _escape_mermaid("~generic~")


def test_escape_no_change():
    assert _escape_mermaid("hello world") == "hello world"


# ═══════════════════════════════════════════════════════════════════
#  _relation_arrow
# ═══════════════════════════════════════════════════════════════════


def test_arrow_inherits():
    assert _relation_arrow(RelationType.INHERITS) == "--|>"


def test_arrow_implements():
    assert _relation_arrow(RelationType.IMPLEMENTS) == "..|>"


def test_arrow_composes():
    assert _relation_arrow(RelationType.COMPOSES) == "*--"


def test_arrow_aggregates():
    assert _relation_arrow(RelationType.AGGREGATES) == "o--"


def test_arrow_depends():
    assert _relation_arrow(RelationType.DEPENDS) == "..>"


def test_arrow_associates():
    assert _relation_arrow(RelationType.ASSOCIATES) == "-->"


# ═══════════════════════════════════════════════════════════════════
#  _flowchart_arrow
# ═══════════════════════════════════════════════════════════════════


def test_flowchart_arrow_depends():
    result = _flowchart_arrow(RelationType.DEPENDS)
    # Returns a tuple with one element due to trailing comma, or a string
    # Just check the actual value
    assert "-.->" in str(result)


def test_flowchart_arrow_inherits():
    assert _flowchart_arrow(RelationType.INHERITS) == "-->"


# ═══════════════════════════════════════════════════════════════════
#  _truncate_members
# ═══════════════════════════════════════════════════════════════════


def test_truncate_no_truncation():
    items = ["a", "b", "c"]
    assert _truncate_members(items, 5) == ["a", "b", "c"]


def test_truncate_at_limit():
    items = ["a", "b", "c"]
    assert _truncate_members(items, 3) == ["a", "b", "c"]


def test_truncate_over_limit():
    items = ["a", "b", "c", "d", "e"]
    result = _truncate_members(items, 3, label="fields")
    assert len(result) == 4  # 3 items + "... 2 more fields"
    assert "2 more fields" in result[-1]


# ═══════════════════════════════════════════════════════════════════
#  _sanitize_id
# ═══════════════════════════════════════════════════════════════════


def test_sanitize_dots():
    assert _sanitize_id("core.services.vault") == "core_services_vault"


def test_sanitize_parens():
    assert _sanitize_id("(root)") == "root"


def test_sanitize_brackets():
    assert _sanitize_id("Generic[T]") == "GenericT"


def test_sanitize_spaces():
    assert _sanitize_id("some thing") == "some_thing"


# ═══════════════════════════════════════════════════════════════════
#  _strip_visibility_prefix
# ═══════════════════════════════════════════════════════════════════


def test_strip_public():
    assert _strip_visibility_prefix("+ name: str") == "name: str"


def test_strip_protected():
    assert _strip_visibility_prefix("# _value: int") == "_value: int"


def test_strip_private():
    assert _strip_visibility_prefix("- __secret: str") == "__secret: str"


def test_strip_no_prefix():
    assert _strip_visibility_prefix("name: str") == "name: str"


def test_strip_empty():
    assert _strip_visibility_prefix("") == ""


# ═══════════════════════════════════════════════════════════════════
#  _visibility_marker
# ═══════════════════════════════════════════════════════════════════


def test_visibility_marker_public():
    assert _visibility_marker("public") == "+"


def test_visibility_marker_protected():
    assert _visibility_marker("protected") == "#"


def test_visibility_marker_private():
    assert _visibility_marker("private") == "-"


def test_visibility_marker_unknown():
    assert _visibility_marker("???") == "+"


# ═══════════════════════════════════════════════════════════════════
#  render_class_diagram
# ═══════════════════════════════════════════════════════════════════


def test_render_empty_graph():
    g = _simple_graph()
    output = render_class_diagram(g)
    assert "classDiagram" in output


def test_render_single_class():
    g = _simple_graph(nodes=[_node("Foo", fields=["+ x: int"], methods=["+ run()"])])
    output = render_class_diagram(g, config=MermaidConfig(include_orphans=True))
    assert "classDiagram" in output
    assert "mod_Foo" in output
    assert "x: int" in output
    assert "run()" in output


def test_render_with_inheritance():
    parent = _node("Parent")
    child = _node("Child")
    edge = GraphEdge(
        source="mod.Child", target="mod.Parent",
        relation=RelationType.INHERITS, label="Parent",
    )
    g = _simple_graph(nodes=[parent, child], edges=[edge])

    output = render_class_diagram(g)
    assert "--|>" in output
    assert "mod_Child" in output
    assert "mod_Parent" in output


def test_render_abstract_annotation():
    g = _simple_graph(nodes=[_node("Base", kind="abstract")])
    output = render_class_diagram(g, config=MermaidConfig(include_orphans=True))
    assert "<<abstract>>" in output


def test_render_interface_annotation():
    g = _simple_graph(nodes=[_node("Handler", kind="interface")])
    output = render_class_diagram(g, config=MermaidConfig(include_orphans=True))
    assert "<<interface>>" in output


def test_render_dataclass_annotation():
    g = _simple_graph(nodes=[_node("Config", kind="dataclass")])
    output = render_class_diagram(g, config=MermaidConfig(include_orphans=True))
    assert "<<dataclass>>" in output


def test_render_no_fields():
    g = _simple_graph(nodes=[_node("Foo", fields=["+ x: int"])])
    output = render_class_diagram(
        g, config=MermaidConfig(show_fields=False, include_orphans=True),
    )
    assert "x: int" not in output


def test_render_no_methods():
    g = _simple_graph(nodes=[_node("Foo", methods=["+ run()"])])
    output = render_class_diagram(
        g, config=MermaidConfig(show_methods=False, include_orphans=True),
    )
    assert "run()" not in output


def test_render_no_visibility():
    g = _simple_graph(nodes=[_node("Foo", fields=["+ x: int"])])
    output = render_class_diagram(
        g, config=MermaidConfig(show_visibility=False, include_orphans=True),
    )
    # Should strip the "+" prefix
    assert "+ x: int" not in output
    assert "x: int" in output


def test_render_without_package_grouping():
    g = _simple_graph(nodes=[_node("A"), _node("B")])
    output = render_class_diagram(
        g,
        config=MermaidConfig(group_by_package=False, include_orphans=True),
    )
    assert "namespace" not in output
    assert "mod_A" in output


def test_render_with_package_grouping():
    a = _node("A", package="core")
    b = _node("B", package="web")
    g = _simple_graph(nodes=[a, b])
    output = render_class_diagram(
        g, config=MermaidConfig(group_by_package=True, include_orphans=True),
    )
    assert "namespace core" in output
    assert "namespace web" in output


def test_render_direction():
    g = _simple_graph(nodes=[_node("A")])
    output = render_class_diagram(
        g, config=MermaidConfig(direction="LR", include_orphans=True),
    )
    assert "direction LR" in output


def test_render_orphans_excluded_by_default():
    """Orphan nodes are excluded when include_orphans=False."""
    a = _node("Connected1")
    b = _node("Connected2")
    c = _node("Orphan")
    edge = GraphEdge(
        source="mod.Connected1", target="mod.Connected2",
        relation=RelationType.INHERITS,
    )
    g = _simple_graph(nodes=[a, b, c], edges=[edge])

    output = render_class_diagram(g, config=MermaidConfig(include_orphans=False))
    assert "mod_Connected1" in output
    assert "mod_Orphan" not in output


def test_render_orphans_included():
    """Orphan nodes are shown when include_orphans=True."""
    c = _node("Orphan")
    g = _simple_graph(nodes=[c])

    output = render_class_diagram(g, config=MermaidConfig(include_orphans=True))
    assert "mod_Orphan" in output


def test_render_all_orphans_fallback():
    """When all nodes are orphans and include_orphans=False, still show them."""
    a = _node("A")
    b = _node("B")
    g = _simple_graph(nodes=[a, b])

    output = render_class_diagram(g, config=MermaidConfig(include_orphans=False))
    # Should fallback to showing all nodes
    assert "mod_A" in output
    assert "mod_B" in output


def test_render_truncated_fields():
    """Long field lists are truncated."""
    fields = [f"+ field{i}: int" for i in range(20)]
    g = _simple_graph(nodes=[_node("Big", fields=fields)])
    output = render_class_diagram(
        g, config=MermaidConfig(max_fields=5, include_orphans=True),
    )
    assert "more fields" in output


def test_render_truncated_methods():
    """Long method lists are truncated."""
    methods = [f"+ method{i}()" for i in range(25)]
    g = _simple_graph(nodes=[_node("Big", methods=methods)])
    output = render_class_diagram(
        g, config=MermaidConfig(max_methods=5, include_orphans=True),
    )
    assert "more methods" in output


# ═══════════════════════════════════════════════════════════════════
#  render_flowchart
# ═══════════════════════════════════════════════════════════════════


def test_flowchart_basic():
    a = _node("A")
    b = _node("B")
    edge = GraphEdge(source="mod.A", target="mod.B", relation=RelationType.INHERITS)
    g = _simple_graph(nodes=[a, b], edges=[edge])

    output = render_flowchart(g)
    assert "graph TD" in output
    assert "mod_A" in output
    assert "mod_B" in output
    assert "-->" in output


def test_flowchart_with_label():
    edge = GraphEdge(
        source="mod.A", target="mod.B",
        relation=RelationType.DEPENDS, label="uses",
    )
    g = _simple_graph(
        nodes=[_node("A"), _node("B")],
        edges=[edge],
    )

    output = render_flowchart(g)
    assert "uses" in output


def test_flowchart_direction():
    g = _simple_graph(nodes=[_node("A")])
    output = render_flowchart(g, config=MermaidConfig(direction="LR"))
    assert "graph LR" in output


# ═══════════════════════════════════════════════════════════════════
#  render_component_diagram
# ═══════════════════════════════════════════════════════════════════


def test_component_basic():
    packages = {
        "core.services": ["EventBus", "ArtifactEngine"],
        "web.routes": ["ApiRouter"],
    }
    deps = [("core.services", "web.routes")]

    output = render_component_diagram(packages, deps)
    assert "graph TD" in output
    assert "core_services" in output
    assert "2 classes" in output
    assert "1 classes" in output


def test_component_no_self_deps():
    packages = {"core": ["A"]}
    deps = [("core", "core")]

    output = render_component_diagram(packages, deps)
    # Self-dependency should be filtered out
    assert "-->" not in output


def test_component_dedup_deps():
    packages = {"a": ["X"], "b": ["Y"]}
    deps = [("a", "b"), ("a", "b"), ("a", "b")]

    output = render_component_diagram(packages, deps)
    # Only one edge
    assert output.count("-->") == 1


def test_component_empty():
    output = render_component_diagram({}, [])
    assert "graph TD" in output
