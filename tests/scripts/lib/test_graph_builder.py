"""Tests for graph_builder shared library module."""

import pytest

from src.core.data.script_templates.lib.code_analyzer import (
    ClassInfo,
    FieldInfo,
    MethodInfo,
    ProjectAnalysis,
)
from src.core.data.script_templates.lib.graph_builder import (
    ClassGraph,
    GraphEdge,
    GraphNode,
    RelationType,
    build_class_graph,
    _class_to_node,
    _detect_composition,
    _detect_dependencies,
    _parse_type_for_composition,
    _resolve_class_name,
    _resolve_inheritance,
    _split_type_args,
    _strip_generics,
)


# ═══════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════


def _make_analysis(*classes: ClassInfo) -> ProjectAnalysis:
    """Build a ProjectAnalysis from a list of ClassInfo."""
    return ProjectAnalysis(
        classes=list(classes),
        files_analyzed=len(classes),
        total_classes=len(classes),
    )


def _cls(
    name: str,
    module: str = "mod",
    bases: list[str] | None = None,
    fields: list[FieldInfo] | None = None,
    methods: list[MethodInfo] | None = None,
    **kwargs,
) -> ClassInfo:
    """Shorthand ClassInfo builder."""
    return ClassInfo(
        name=name,
        qualified_name=f"{module}.{name}" if module else name,
        module=module,
        bases=bases or [],
        fields=fields or [],
        methods=methods or [],
        **kwargs,
    )


# ═══════════════════════════════════════════════════════════════════
#  RelationType
# ═══════════════════════════════════════════════════════════════════


def test_relation_type_values():
    assert RelationType.INHERITS.value == "inherits"
    assert RelationType.IMPLEMENTS.value == "implements"
    assert RelationType.COMPOSES.value == "composes"
    assert RelationType.AGGREGATES.value == "aggregates"
    assert RelationType.DEPENDS.value == "depends"
    assert RelationType.ASSOCIATES.value == "associates"


# ═══════════════════════════════════════════════════════════════════
#  ClassGraph operations
# ═══════════════════════════════════════════════════════════════════


def test_add_node():
    g = ClassGraph()
    n = GraphNode(id="A", label="A")
    g.add_node(n)
    assert "A" in g.nodes


def test_add_edge():
    g = ClassGraph()
    e = GraphEdge(source="A", target="B", relation=RelationType.INHERITS)
    g.add_edge(e)
    assert len(g.edges) == 1


def test_add_edge_dedup():
    """Duplicate edges are not added."""
    g = ClassGraph()
    e1 = GraphEdge(source="A", target="B", relation=RelationType.INHERITS)
    e2 = GraphEdge(source="A", target="B", relation=RelationType.INHERITS)
    g.add_edge(e1)
    g.add_edge(e2)
    assert len(g.edges) == 1


def test_add_edge_different_relations():
    """Same source/target but different relation → not a duplicate."""
    g = ClassGraph()
    e1 = GraphEdge(source="A", target="B", relation=RelationType.INHERITS)
    e2 = GraphEdge(source="A", target="B", relation=RelationType.DEPENDS)
    g.add_edge(e1)
    g.add_edge(e2)
    assert len(g.edges) == 2


def test_filter_by_package():
    g = ClassGraph()
    g.add_node(GraphNode(id="A", label="A", package="core.services"))
    g.add_node(GraphNode(id="B", label="B", package="core.services.vault"))
    g.add_node(GraphNode(id="C", label="C", package="web.routes"))
    g.add_edge(GraphEdge(source="A", target="B", relation=RelationType.INHERITS))
    g.add_edge(GraphEdge(source="A", target="C", relation=RelationType.DEPENDS))

    filtered = g.filter_by_package("core.services")

    assert "A" in filtered.nodes
    assert "B" in filtered.nodes
    assert "C" not in filtered.nodes
    assert len(filtered.edges) == 1  # A→B kept, A→C dropped


def test_filter_by_package_empty():
    g = ClassGraph()
    g.add_node(GraphNode(id="A", label="A", package="core"))

    filtered = g.filter_by_package("web")
    assert len(filtered.nodes) == 0
    assert len(filtered.edges) == 0


def test_get_connected_components():
    g = ClassGraph()
    g.add_node(GraphNode(id="A", label="A"))
    g.add_node(GraphNode(id="B", label="B"))
    g.add_node(GraphNode(id="C", label="C"))
    g.add_node(GraphNode(id="D", label="D"))
    g.add_edge(GraphEdge(source="A", target="B", relation=RelationType.INHERITS))
    g.add_edge(GraphEdge(source="C", target="D", relation=RelationType.INHERITS))

    components = g.get_connected_components()

    assert len(components) == 2
    assert ["A", "B"] in components
    assert ["C", "D"] in components


def test_get_connected_components_single_component():
    g = ClassGraph()
    g.add_node(GraphNode(id="A", label="A"))
    g.add_node(GraphNode(id="B", label="B"))
    g.add_node(GraphNode(id="C", label="C"))
    g.add_edge(GraphEdge(source="A", target="B", relation=RelationType.INHERITS))
    g.add_edge(GraphEdge(source="B", target="C", relation=RelationType.DEPENDS))

    components = g.get_connected_components()
    assert len(components) == 1
    assert components[0] == ["A", "B", "C"]


def test_get_connected_components_empty():
    g = ClassGraph()
    assert g.get_connected_components() == []


def test_get_orphan_nodes():
    g = ClassGraph()
    g.add_node(GraphNode(id="A", label="A"))
    g.add_node(GraphNode(id="B", label="B"))
    g.add_node(GraphNode(id="C", label="C"))
    g.add_edge(GraphEdge(source="A", target="B", relation=RelationType.INHERITS))

    orphans = g.get_orphan_nodes()
    assert orphans == ["C"]


def test_get_orphan_nodes_none():
    g = ClassGraph()
    g.add_node(GraphNode(id="A", label="A"))
    g.add_node(GraphNode(id="B", label="B"))
    g.add_edge(GraphEdge(source="A", target="B", relation=RelationType.INHERITS))

    assert g.get_orphan_nodes() == []


# ═══════════════════════════════════════════════════════════════════
#  _strip_generics
# ═══════════════════════════════════════════════════════════════════


def test_strip_generics_simple():
    assert _strip_generics("Generic[T]") == "Generic"


def test_strip_generics_no_brackets():
    assert _strip_generics("Foo") == "Foo"


def test_strip_generics_nested():
    assert _strip_generics("dict[str, list[int]]") == "dict"


# ═══════════════════════════════════════════════════════════════════
#  _parse_type_for_composition
# ═══════════════════════════════════════════════════════════════════


def test_parse_direct_type():
    inner, card, rel = _parse_type_for_composition("Foo")
    assert inner == "Foo"
    assert card == "1"
    assert rel == RelationType.COMPOSES


def test_parse_list_type():
    inner, card, rel = _parse_type_for_composition("list[Foo]")
    assert inner == "Foo"
    assert card == "*"
    assert rel == RelationType.AGGREGATES


def test_parse_optional_type():
    inner, card, rel = _parse_type_for_composition("Optional[Foo]")
    assert inner == "Foo"
    assert card == "0..1"
    assert rel == RelationType.ASSOCIATES


def test_parse_set_type():
    inner, card, rel = _parse_type_for_composition("set[Foo]")
    assert inner == "Foo"
    assert card == "*"
    assert rel == RelationType.AGGREGATES


def test_parse_dict_type():
    inner, card, rel = _parse_type_for_composition("dict[str, Foo]")
    assert inner == "Foo"
    assert card == "*"
    assert rel == RelationType.AGGREGATES


def test_parse_union_with_none():
    inner, card, rel = _parse_type_for_composition("Foo | None")
    assert inner == "Foo"
    assert card == "0..1"
    assert rel == RelationType.ASSOCIATES


def test_parse_union_multiple():
    inner, card, rel = _parse_type_for_composition("Foo | Bar")
    assert rel == RelationType.ASSOCIATES


# ═══════════════════════════════════════════════════════════════════
#  _split_type_args
# ═══════════════════════════════════════════════════════════════════


def test_split_type_args_simple():
    assert _split_type_args("str, int") == ["str", "int"]


def test_split_type_args_nested():
    assert _split_type_args("int, dict[str, int]") == ["int", "dict[str, int]"]


def test_split_type_args_single():
    assert _split_type_args("Foo") == ["Foo"]


# ═══════════════════════════════════════════════════════════════════
#  _class_to_node
# ═══════════════════════════════════════════════════════════════════


def test_class_to_node_basic():
    cls = _cls("Foo", fields=[FieldInfo(name="x", type_annotation="int")])
    node = _class_to_node(cls)
    assert node.id == "mod.Foo"
    assert node.label == "Foo"
    assert node.kind == "class"
    assert len(node.fields) == 1
    assert "+ x: int" in node.fields[0]


def test_class_to_node_abstract():
    cls = _cls("Base", is_abstract=True)
    node = _class_to_node(cls)
    assert node.kind == "abstract"


def test_class_to_node_dataclass():
    cls = _cls("Config", is_dataclass=True)
    node = _class_to_node(cls)
    assert node.kind == "dataclass"


def test_class_to_node_protocol():
    cls = _cls("Handler", is_protocol=True)
    node = _class_to_node(cls)
    assert node.kind == "interface"


def test_class_to_node_methods():
    cls = _cls(
        "Svc",
        methods=[
            MethodInfo(name="run", parameters=["x"], return_type="str"),
            MethodInfo(name="_internal", visibility="protected"),
        ],
    )
    node = _class_to_node(cls)
    assert len(node.methods) == 2
    assert "+ run(x) str" in node.methods[0]
    assert "# _internal()" in node.methods[1]


def test_class_to_node_async_method():
    cls = _cls(
        "Svc",
        methods=[MethodInfo(name="fetch", is_async=True)],
    )
    node = _class_to_node(cls)
    assert "async" in node.methods[0]


def test_class_to_node_private_field():
    cls = _cls(
        "Foo",
        fields=[FieldInfo(name="__secret", type_annotation="str", visibility="private")],
    )
    node = _class_to_node(cls)
    assert node.fields[0].startswith("- ")


# ═══════════════════════════════════════════════════════════════════
#  build_class_graph — inheritance
# ═══════════════════════════════════════════════════════════════════


def test_build_simple_inheritance():
    parent = _cls("Parent")
    child = _cls("Child", bases=["Parent"])
    analysis = _make_analysis(parent, child)

    graph = build_class_graph(analysis)

    assert len(graph.nodes) == 2
    assert len(graph.edges) == 1
    edge = graph.edges[0]
    assert edge.source == "mod.Child"
    assert edge.target == "mod.Parent"
    assert edge.relation == RelationType.INHERITS


def test_build_abc_inheritance():
    """ABC base → IMPLEMENTS, but only if include_stdlib."""
    child = _cls("Child", bases=["ABC"])
    analysis = _make_analysis(child)

    # Without include_stdlib — ABC is skipped
    graph = build_class_graph(analysis, include_stdlib=False)
    assert len(graph.edges) == 0

    # With include_stdlib — ABC creates IMPLEMENTS edge
    graph = build_class_graph(analysis, include_stdlib=True)
    assert len(graph.edges) == 1
    assert graph.edges[0].relation == RelationType.IMPLEMENTS


def test_build_external_base():
    """External base classes create stub nodes when include_external=True."""
    child = _cls("MyModel", bases=["SomeExternalBase"])
    analysis = _make_analysis(child)

    # Without include_external
    graph = build_class_graph(analysis, include_external=False)
    assert len(graph.nodes) == 1
    assert len(graph.edges) == 0

    # With include_external
    graph = build_class_graph(analysis, include_external=True)
    assert "SomeExternalBase" in graph.nodes
    assert len(graph.edges) == 1


# ═══════════════════════════════════════════════════════════════════
#  build_class_graph — composition
# ═══════════════════════════════════════════════════════════════════


def test_build_composition():
    """Field of type B in class A → COMPOSES edge."""
    a = _cls("A", fields=[FieldInfo(name="b", type_annotation="B")])
    b = _cls("B")
    analysis = _make_analysis(a, b)

    graph = build_class_graph(analysis)

    comp_edges = [e for e in graph.edges if e.relation == RelationType.COMPOSES]
    assert len(comp_edges) == 1
    assert comp_edges[0].source == "mod.A"
    assert comp_edges[0].target == "mod.B"
    assert comp_edges[0].cardinality == "1"


def test_build_aggregation():
    """Field of type list[B] → AGGREGATES edge."""
    a = _cls("A", fields=[FieldInfo(name="items", type_annotation="list[B]")])
    b = _cls("B")
    analysis = _make_analysis(a, b)

    graph = build_class_graph(analysis)

    agg_edges = [e for e in graph.edges if e.relation == RelationType.AGGREGATES]
    assert len(agg_edges) == 1
    assert agg_edges[0].cardinality == "*"


def test_build_no_self_composition():
    """Self-referencing fields don't create edges."""
    a = _cls("A", fields=[FieldInfo(name="parent", type_annotation="A")])
    analysis = _make_analysis(a)

    graph = build_class_graph(analysis)
    assert len(graph.edges) == 0


def test_build_composition_any_skipped():
    """Fields typed as 'Any' don't create composition edges."""
    a = _cls("A", fields=[FieldInfo(name="data", type_annotation="Any")])
    b = _cls("B")
    analysis = _make_analysis(a, b)

    graph = build_class_graph(analysis)
    assert len(graph.edges) == 0


# ═══════════════════════════════════════════════════════════════════
#  build_class_graph — dependencies
# ═══════════════════════════════════════════════════════════════════


def test_build_dependency_from_return_type():
    """Return type referencing another class → DEPENDS edge."""
    a = _cls("A", methods=[MethodInfo(name="create", return_type="B")])
    b = _cls("B")
    analysis = _make_analysis(a, b)

    graph = build_class_graph(analysis)

    dep_edges = [e for e in graph.edges if e.relation == RelationType.DEPENDS]
    assert len(dep_edges) == 1
    assert dep_edges[0].source == "mod.A"
    assert dep_edges[0].target == "mod.B"


def test_build_no_self_dependency():
    """Return type referencing self doesn't create edge."""
    a = _cls("A", methods=[MethodInfo(name="clone", return_type="A")])
    analysis = _make_analysis(a)

    graph = build_class_graph(analysis)
    assert len(graph.edges) == 0


# ═══════════════════════════════════════════════════════════════════
#  build_class_graph — scope filter
# ═══════════════════════════════════════════════════════════════════


def test_build_with_scope_filter():
    """Scope filter limits to matching modules."""
    a = _cls("A", module="core.services")
    b = _cls("B", module="web.routes")
    analysis = _make_analysis(a, b)

    graph = build_class_graph(analysis, scope="core")

    assert "core.services.A" in graph.nodes
    assert "web.routes.B" not in graph.nodes


# ═══════════════════════════════════════════════════════════════════
#  build_class_graph — full pipeline
# ═══════════════════════════════════════════════════════════════════


def test_build_full_graph():
    """End-to-end: inheritance + composition + dependencies."""
    base = _cls("Base")
    child = _cls(
        "Child",
        bases=["Base"],
        fields=[FieldInfo(name="helper", type_annotation="Helper")],
        methods=[MethodInfo(name="run", return_type="Result")],
    )
    helper = _cls("Helper")
    result = _cls("Result")
    analysis = _make_analysis(base, child, helper, result)

    graph = build_class_graph(analysis)

    assert len(graph.nodes) == 4
    # Should have: Child→Base (INHERITS), Child→Helper (COMPOSES), Child→Result (DEPENDS)
    assert len(graph.edges) >= 3

    relations = {(e.source, e.target, e.relation) for e in graph.edges}
    assert ("mod.Child", "mod.Base", RelationType.INHERITS) in relations
    assert ("mod.Child", "mod.Helper", RelationType.COMPOSES) in relations
    assert ("mod.Child", "mod.Result", RelationType.DEPENDS) in relations


def test_build_empty_analysis():
    """Empty analysis → empty graph."""
    analysis = ProjectAnalysis()
    graph = build_class_graph(analysis)
    assert len(graph.nodes) == 0
    assert len(graph.edges) == 0


def test_build_orphan_class():
    """Class with no relationships → orphan node."""
    a = _cls("Standalone")
    analysis = _make_analysis(a)

    graph = build_class_graph(analysis)

    assert len(graph.nodes) == 1
    assert graph.get_orphan_nodes() == ["mod.Standalone"]


# ═══════════════════════════════════════════════════════════════════
#  _resolve_class_name
# ═══════════════════════════════════════════════════════════════════


def test_resolve_by_qname():
    cls = _cls("Foo")
    by_name = {"Foo": cls}
    by_qname = {"mod.Foo": cls}

    assert _resolve_class_name("mod.Foo", by_name, by_qname) == "mod.Foo"


def test_resolve_by_short_name():
    cls = _cls("Foo")
    by_name = {"Foo": cls}
    by_qname = {"mod.Foo": cls}

    assert _resolve_class_name("Foo", by_name, by_qname) == "mod.Foo"


def test_resolve_unknown():
    assert _resolve_class_name("Unknown", {}, {}) is None


# ═══════════════════════════════════════════════════════════════════
#  Graph title and scope
# ═══════════════════════════════════════════════════════════════════


def test_graph_title_default():
    analysis = _make_analysis()
    graph = build_class_graph(analysis)
    assert "project" in graph.title


def test_graph_title_scoped():
    analysis = _make_analysis()
    graph = build_class_graph(analysis, scope="core.services")
    assert "core.services" in graph.title
    assert graph.scope == "core.services"
