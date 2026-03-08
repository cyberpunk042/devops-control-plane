"""
Tests for scripts data models — ScriptMeta, ScriptParameter, ScriptConfig.

Covers:
- Default values and required fields
- Parameter type validations
- ScriptConfig sensible defaults
- Dataclass field behavior (lists, optionals)
- Numbering and permanence logic
"""

from src.core.services.scripts.models import (
    ScriptConfig,
    ScriptMeta,
    ScriptParameter,
)


class TestScriptParameter:
    """ScriptParameter model tests."""

    def test_minimal_parameter(self):
        """A parameter needs only a name."""
        p = ScriptParameter(name="output")
        assert p.name == "output"
        assert p.type == "string"
        assert p.description == ""
        assert p.required is False
        assert p.default == ""
        assert p.choices == []

    def test_full_parameter(self):
        """All fields populate correctly."""
        p = ScriptParameter(
            name="format",
            type="choice",
            description="Output format",
            required=True,
            default="mermaid",
            choices=["mermaid", "json", "markdown"],
        )
        assert p.name == "format"
        assert p.type == "choice"
        assert p.description == "Output format"
        assert p.required is True
        assert p.default == "mermaid"
        assert p.choices == ["mermaid", "json", "markdown"]

    def test_path_parameter(self):
        """Path type with default."""
        p = ScriptParameter(name="output", type="path", default="docs/diagrams/")
        assert p.type == "path"
        assert p.default == "docs/diagrams/"

    def test_boolean_parameter(self):
        """Boolean type."""
        p = ScriptParameter(name="dry_run", type="boolean", default="true")
        assert p.type == "boolean"
        assert p.default == "true"

    def test_integer_parameter(self):
        """Integer type."""
        p = ScriptParameter(name="depth", type="integer", default="3")
        assert p.type == "integer"
        assert p.default == "3"

    def test_choices_list_independence(self):
        """Each parameter instance gets its own choices list."""
        p1 = ScriptParameter(name="a")
        p2 = ScriptParameter(name="b")
        p1.choices.append("x")
        assert p2.choices == []


class TestScriptMeta:
    """ScriptMeta model tests."""

    def test_minimal_meta(self):
        """ScriptMeta needs id and name."""
        m = ScriptMeta(id="test_hello", name="Hello World")
        assert m.id == "test_hello"
        assert m.name == "Hello World"
        assert m.description == ""
        assert m.category == "general"
        assert m.tags == []
        assert m.language == "python"
        assert m.mode == "fully_automated"
        assert m.timeout == 300
        assert m.parameters == []
        assert m.default_output == ""
        assert m.output_formats == []
        assert m.source == "root"
        assert m.path == ""
        assert m.relative_path == ""
        assert m.override_target == ""
        assert m.dependencies == []
        assert m.requires_tools == []
        assert m.number is None
        assert m.is_permanent is False

    def test_full_meta(self):
        """All fields populate correctly."""
        params = [
            ScriptParameter(name="output", type="path", default="docs/diagrams/"),
            ScriptParameter(name="scope", type="string"),
        ]
        m = ScriptMeta(
            id="00_class_diagrams",
            name="Class Diagram Generator",
            description="Generate Mermaid class diagrams from Python source.",
            category="generator",
            tags=["mermaid", "diagrams", "docs", "python"],
            language="python",
            mode="fully_automated",
            timeout=120,
            parameters=params,
            default_output="docs/diagrams/",
            output_formats=["mermaid", "json", "markdown"],
            source="override",
            path="/home/user/project/scripts/00_class_diagrams.py",
            relative_path="00_class_diagrams.py",
            override_target="generators/class_diagrams",
            dependencies=[],
            requires_tools=[],
            number=0,
            is_permanent=True,
        )
        assert m.id == "00_class_diagrams"
        assert m.name == "Class Diagram Generator"
        assert m.category == "generator"
        assert len(m.tags) == 4
        assert m.timeout == 120
        assert len(m.parameters) == 2
        assert m.parameters[0].name == "output"
        assert m.default_output == "docs/diagrams/"
        assert m.output_formats == ["mermaid", "json", "markdown"]
        assert m.source == "override"
        assert m.override_target == "generators/class_diagrams"
        assert m.number == 0
        assert m.is_permanent is True

    def test_bash_script_meta(self):
        """Shell scripts use language='bash'."""
        m = ScriptMeta(
            id="deploy",
            name="Deployment Script",
            language="bash",
            category="ops",
            mode="fully_automated",
            timeout=600,
        )
        assert m.language == "bash"
        assert m.category == "ops"
        assert m.timeout == 600

    def test_template_source(self):
        """Template scripts have source='template'."""
        m = ScriptMeta(
            id="audit/route_quality",
            name="Route Quality Audit",
            source="template",
            relative_path="audit/route_quality.py",
        )
        assert m.source == "template"
        assert m.relative_path == "audit/route_quality.py"

    def test_numbered_script(self):
        """Numbered scripts are permanent."""
        m = ScriptMeta(
            id="01_route_audit",
            name="Route Audit",
            number=1,
            is_permanent=True,
        )
        assert m.number == 1
        assert m.is_permanent is True

    def test_unnumbered_script(self):
        """Unnumbered scripts are temporary/one-off."""
        m = ScriptMeta(
            id="quick_debug",
            name="Quick Debug",
            number=None,
            is_permanent=False,
        )
        assert m.number is None
        assert m.is_permanent is False

    def test_override_script(self):
        """Scripts can override templates via override_target."""
        m = ScriptMeta(
            id="00_class_diagrams",
            name="Class Diagram Generator",
            source="override",
            override_target="generators/class_diagrams",
        )
        assert m.source == "override"
        assert m.override_target == "generators/class_diagrams"

    def test_list_independence(self):
        """Each ScriptMeta instance gets its own lists."""
        m1 = ScriptMeta(id="a", name="A")
        m2 = ScriptMeta(id="b", name="B")
        m1.tags.append("test")
        m1.parameters.append(ScriptParameter(name="x"))
        m1.output_formats.append("json")
        m1.dependencies.append("dep")
        m1.requires_tools.append("tool")
        assert m2.tags == []
        assert m2.parameters == []
        assert m2.output_formats == []
        assert m2.dependencies == []
        assert m2.requires_tools == []


class TestScriptConfig:
    """ScriptConfig model tests."""

    def test_defaults(self):
        """Default config works out of the box."""
        c = ScriptConfig()
        assert c.root == "scripts"
        assert c.template_source == "auto"
        assert c.default_output == "scripts/output"
        assert c.history_max_runs == 100
        assert c.history_persist_output is True
        assert c.execution_default_timeout == 300
        assert c.execution_parallel is False
        assert c.execution_venv_python == "auto"
        assert c.categories == ["audit", "generator", "analyzer", "debug", "ops", "general"]

    def test_custom_config(self):
        """Custom values override defaults."""
        c = ScriptConfig(
            root="ops/scripts",
            template_source="always",
            default_output="output/reports",
            history_max_runs=50,
            history_persist_output=False,
            execution_default_timeout=600,
            execution_parallel=True,
            execution_venv_python="/usr/bin/python3",
            categories=["audit", "ops"],
        )
        assert c.root == "ops/scripts"
        assert c.template_source == "always"
        assert c.default_output == "output/reports"
        assert c.history_max_runs == 50
        assert c.history_persist_output is False
        assert c.execution_default_timeout == 600
        assert c.execution_parallel is True
        assert c.execution_venv_python == "/usr/bin/python3"
        assert c.categories == ["audit", "ops"]

    def test_categories_independence(self):
        """Each ScriptConfig gets its own categories list."""
        c1 = ScriptConfig()
        c2 = ScriptConfig()
        c1.categories.append("custom")
        assert "custom" not in c2.categories

    def test_template_source_never(self):
        """template_source='never' is a valid setting."""
        c = ScriptConfig(template_source="never")
        assert c.template_source == "never"

    def test_template_source_always(self):
        """template_source='always' is a valid setting."""
        c = ScriptConfig(template_source="always")
        assert c.template_source == "always"
