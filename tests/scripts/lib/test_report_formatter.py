"""Tests for report_formatter shared library module."""

import json
from pathlib import Path

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
)
from src.core.data.script_templates.lib.report_formatter import (
    format_json_report,
    format_markdown_report,
    write_report,
    _arrow_for_table,
    _class_to_dict,
    _generate_class_index,
    _generate_relationship_summary,
    _generate_stats,
    _generate_toc,
    _short_name,
)


# ═══════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════


def _graph_with_data() -> ClassGraph:
    """Build a graph with known test data."""
    g = ClassGraph(title="Test Graph", scope="test")
    g.add_node(GraphNode(
        id="mod.Foo", label="Foo", kind="class", package="mod",
        fields=["+ x: int"], methods=["+ run()"],
        metadata={"file": "mod/foo.py", "docstring": "A foo class"},
    ))
    g.add_node(GraphNode(
        id="mod.Bar", label="Bar", kind="abstract", package="mod",
        fields=[], methods=["+ process()"],
        metadata={"docstring": ""},
    ))
    g.add_edge(GraphEdge(
        source="mod.Foo", target="mod.Bar",
        relation=RelationType.INHERITS, label="Bar",
    ))
    return g


def _analysis_with_data() -> ProjectAnalysis:
    """Build an analysis with known test data."""
    return ProjectAnalysis(
        classes=[
            ClassInfo(
                name="Foo",
                qualified_name="mod.Foo",
                module="mod",
                bases=["Bar"],
                fields=[FieldInfo(name="x", type_annotation="int")],
                methods=[MethodInfo(name="run")],
            ),
            ClassInfo(
                name="Bar",
                qualified_name="mod.Bar",
                module="mod",
                is_abstract=True,
            ),
        ],
        files_analyzed=3,
        files_with_errors=1,
        total_classes=2,
        analysis_errors=["bad.py: SyntaxError"],
    )


# ═══════════════════════════════════════════════════════════════════
#  _short_name
# ═══════════════════════════════════════════════════════════════════


def test_short_name_qualified():
    assert _short_name("core.services.vault.VaultOps") == "VaultOps"


def test_short_name_simple():
    assert _short_name("Foo") == "Foo"


def test_short_name_one_dot():
    assert _short_name("mod.Foo") == "Foo"


# ═══════════════════════════════════════════════════════════════════
#  _arrow_for_table
# ═══════════════════════════════════════════════════════════════════


def test_arrow_inherits():
    assert _arrow_for_table(RelationType.INHERITS) == "extends"


def test_arrow_implements():
    assert _arrow_for_table(RelationType.IMPLEMENTS) == "implements"


def test_arrow_composes():
    assert _arrow_for_table(RelationType.COMPOSES) == "has-a"


def test_arrow_aggregates():
    assert _arrow_for_table(RelationType.AGGREGATES) == "has-many"


def test_arrow_depends():
    assert _arrow_for_table(RelationType.DEPENDS) == "uses"


def test_arrow_associates():
    assert _arrow_for_table(RelationType.ASSOCIATES) == "knows"


# ═══════════════════════════════════════════════════════════════════
#  _generate_toc
# ═══════════════════════════════════════════════════════════════════


def test_toc_generation():
    sections = [
        ("Statistics", "..."),
        ("Diagram", "..."),
        ("Class Index", "..."),
    ]
    toc = _generate_toc(sections)
    assert "Table of Contents" in toc
    assert "[Statistics](#statistics)" in toc
    assert "[Diagram](#diagram)" in toc
    assert "[Class Index](#class-index)" in toc


def test_toc_empty():
    toc = _generate_toc([])
    assert "Table of Contents" in toc


# ═══════════════════════════════════════════════════════════════════
#  _generate_stats
# ═══════════════════════════════════════════════════════════════════


def test_stats_with_analysis():
    analysis = _analysis_with_data()
    graph = _graph_with_data()
    stats = _generate_stats(analysis, graph)

    assert "Files analyzed" in stats
    assert "3" in stats
    assert "Total classes" in stats
    assert "Nodes in graph" in stats
    assert "Relationships" in stats
    assert "Connected components" in stats
    assert "Orphan classes" in stats
    assert "Packages" in stats


def test_stats_without_analysis():
    graph = _graph_with_data()
    stats = _generate_stats(None, graph)

    assert "Files analyzed" not in stats
    assert "Nodes in graph" in stats
    assert "Relationships" in stats


def test_stats_edge_breakdown():
    graph = _graph_with_data()
    stats = _generate_stats(None, graph)
    assert "inherits" in stats


# ═══════════════════════════════════════════════════════════════════
#  _generate_class_index
# ═══════════════════════════════════════════════════════════════════


def test_class_index():
    graph = _graph_with_data()
    index = _generate_class_index(graph)

    assert "### mod" in index
    assert "**Foo**" in index
    assert "**Bar**" in index
    assert "`abstract`" in index
    assert "1 fields" in index
    assert "1 methods" in index
    assert "A foo class" in index


def test_class_index_no_docstring():
    """Classes without docstrings don't show the dash."""
    g = ClassGraph()
    g.add_node(GraphNode(id="X", label="X", metadata={}))
    index = _generate_class_index(g)
    assert "**X**" in index
    assert " — " not in index


# ═══════════════════════════════════════════════════════════════════
#  _generate_relationship_summary
# ═══════════════════════════════════════════════════════════════════


def test_relationship_summary():
    graph = _graph_with_data()
    summary = _generate_relationship_summary(graph)

    assert "Source" in summary
    assert "Target" in summary
    assert "Foo" in summary
    assert "Bar" in summary
    assert "inherits" in summary


def test_relationship_summary_with_cardinality():
    g = ClassGraph()
    g.add_edge(GraphEdge(
        source="mod.A", target="mod.B",
        relation=RelationType.AGGREGATES,
        label="items", cardinality="*",
    ))
    summary = _generate_relationship_summary(g)
    assert "[*]" in summary
    assert "items" in summary


# ═══════════════════════════════════════════════════════════════════
#  _class_to_dict
# ═══════════════════════════════════════════════════════════════════


def test_class_to_dict():
    cls = ClassInfo(name="Foo", qualified_name="mod.Foo")
    d = _class_to_dict(cls)
    assert d["name"] == "Foo"
    assert d["qualified_name"] == "mod.Foo"
    assert isinstance(d, dict)


def test_class_to_dict_with_fields():
    cls = ClassInfo(
        name="Foo",
        fields=[FieldInfo(name="x", type_annotation="int")],
    )
    d = _class_to_dict(cls)
    assert len(d["fields"]) == 1
    assert d["fields"][0]["name"] == "x"


# ═══════════════════════════════════════════════════════════════════
#  format_markdown_report
# ═══════════════════════════════════════════════════════════════════


def test_markdown_report_full():
    graph = _graph_with_data()
    mermaid = "classDiagram\n    Foo --|> Bar"
    analysis = _analysis_with_data()

    report = format_markdown_report(
        graph, mermaid,
        title="Test Report",
        include_toc=True,
        include_stats=True,
        analysis=analysis,
    )

    assert "# Test Report" in report
    assert "Generated:" in report
    assert "Table of Contents" in report
    assert "## Statistics" in report
    assert "## Diagram" in report
    assert "```mermaid" in report
    assert "classDiagram" in report
    assert "## Class Index" in report
    assert "## Relationships" in report


def test_markdown_report_no_toc():
    graph = _graph_with_data()
    report = format_markdown_report(
        graph, "diagram",
        include_toc=False,
    )
    assert "Table of Contents" not in report


def test_markdown_report_no_stats():
    graph = _graph_with_data()
    report = format_markdown_report(
        graph, "diagram",
        include_stats=False,
    )
    assert "## Statistics" not in report


def test_markdown_report_empty_graph():
    graph = ClassGraph()
    report = format_markdown_report(graph, "empty diagram")
    assert "# Class Diagram Report" in report
    assert "## Class Index" not in report
    assert "## Relationships" not in report


def test_markdown_report_default_title():
    graph = ClassGraph()
    report = format_markdown_report(graph, "")
    assert "# Class Diagram Report" in report


# ═══════════════════════════════════════════════════════════════════
#  format_json_report
# ═══════════════════════════════════════════════════════════════════


def test_json_report_structure():
    analysis = _analysis_with_data()
    graph = _graph_with_data()

    output = format_json_report(analysis, graph)
    data = json.loads(output)

    assert "metadata" in data
    assert "classes" in data
    assert "relationships" in data
    assert "packages" in data


def test_json_report_metadata():
    analysis = _analysis_with_data()
    graph = _graph_with_data()

    data = json.loads(format_json_report(analysis, graph))
    meta = data["metadata"]

    assert meta["files_analyzed"] == 3
    assert meta["files_with_errors"] == 1
    assert meta["total_classes"] == 2
    assert "generated" in meta


def test_json_report_classes():
    analysis = _analysis_with_data()
    graph = _graph_with_data()

    data = json.loads(format_json_report(analysis, graph))
    classes = data["classes"]

    assert len(classes) == 2
    names = {c["name"] for c in classes}
    assert names == {"Foo", "Bar"}


def test_json_report_relationships():
    analysis = _analysis_with_data()
    graph = _graph_with_data()

    data = json.loads(format_json_report(analysis, graph))
    rels = data["relationships"]

    assert len(rels) == 1
    assert rels[0]["source"] == "mod.Foo"
    assert rels[0]["target"] == "mod.Bar"
    assert rels[0]["relation"] == "inherits"


def test_json_report_packages():
    analysis = _analysis_with_data()
    graph = _graph_with_data()

    data = json.loads(format_json_report(analysis, graph))
    assert "mod" in data["packages"]
    assert "Foo" in data["packages"]["mod"]


def test_json_report_errors():
    analysis = _analysis_with_data()
    graph = _graph_with_data()

    data = json.loads(format_json_report(analysis, graph))
    assert "errors" in data
    assert "bad.py: SyntaxError" in data["errors"]


def test_json_report_no_errors():
    analysis = ProjectAnalysis(classes=[], files_analyzed=0, total_classes=0)
    graph = ClassGraph()

    data = json.loads(format_json_report(analysis, graph))
    assert "errors" not in data


def test_json_report_valid_json():
    analysis = _analysis_with_data()
    graph = _graph_with_data()

    output = format_json_report(analysis, graph)
    # Should not raise
    parsed = json.loads(output)
    assert isinstance(parsed, dict)


# ═══════════════════════════════════════════════════════════════════
#  write_report
# ═══════════════════════════════════════════════════════════════════


def test_write_report_creates_file(tmp_path):
    out = tmp_path / "report.md"
    result = write_report("# Hello", out)
    assert result.exists()
    assert result.read_text() == "# Hello"


def test_write_report_creates_parents(tmp_path):
    out = tmp_path / "deep" / "nested" / "report.md"
    result = write_report("content", out, create_parents=True)
    assert result.exists()
    assert result.read_text() == "content"


def test_write_report_returns_absolute(tmp_path):
    out = tmp_path / "report.md"
    result = write_report("x", out)
    assert result.is_absolute()


def test_write_report_overwrites(tmp_path):
    out = tmp_path / "report.md"
    out.write_text("old")
    write_report("new", out)
    assert out.read_text() == "new"


def test_write_report_json(tmp_path):
    out = tmp_path / "report.json"
    data = json.dumps({"key": "value"})
    write_report(data, out)
    assert json.loads(out.read_text()) == {"key": "value"}
