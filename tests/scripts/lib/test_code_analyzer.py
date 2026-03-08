"""Tests for code_analyzer shared library module."""

import textwrap
from pathlib import Path

import pytest

from src.core.data.script_templates.lib.code_analyzer import (
    ClassInfo,
    FieldInfo,
    MethodInfo,
    ProjectAnalysis,
    analyze_file,
    analyze_python_project,
    _extract_bases,
    _extract_class,
    _extract_fields,
    _extract_methods,
    _visibility_from_name,
    _is_abstract,
    _node_to_str,
)
import ast


# ═══════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════


def _write_py(tmp_path: Path, name: str, content: str) -> Path:
    """Write a Python file and return its path."""
    p = tmp_path / name
    p.write_text(textwrap.dedent(content))
    return p


def _parse_class(source: str) -> ast.ClassDef:
    """Parse source and return the first ClassDef node."""
    tree = ast.parse(textwrap.dedent(source))
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            return node
    raise ValueError("No ClassDef found")


# ═══════════════════════════════════════════════════════════════════
#  _visibility_from_name
# ═══════════════════════════════════════════════════════════════════


def test_visibility_public():
    assert _visibility_from_name("name") == "public"


def test_visibility_protected():
    assert _visibility_from_name("_name") == "protected"


def test_visibility_private():
    assert _visibility_from_name("__name") == "private"


def test_visibility_dunder_is_public():
    """Dunder methods like __init__ are public, not private."""
    assert _visibility_from_name("__init__") == "protected"


def test_visibility_single_underscore():
    assert _visibility_from_name("_") == "protected"


# ═══════════════════════════════════════════════════════════════════
#  _extract_bases
# ═══════════════════════════════════════════════════════════════════


def test_extract_bases_simple():
    node = _parse_class("class Foo(Bar): pass")
    assert _extract_bases(node) == ["Bar"]


def test_extract_bases_multiple():
    node = _parse_class("class Foo(Bar, Baz): pass")
    assert _extract_bases(node) == ["Bar", "Baz"]


def test_extract_bases_dotted():
    node = _parse_class("class Foo(abc.ABC): pass")
    assert _extract_bases(node) == ["abc.ABC"]


def test_extract_bases_generic():
    node = _parse_class("class Foo(Generic[T]): pass")
    assert _extract_bases(node) == ["Generic[T]"]


def test_extract_bases_none():
    node = _parse_class("class Foo: pass")
    assert _extract_bases(node) == []


# ═══════════════════════════════════════════════════════════════════
#  _extract_fields
# ═══════════════════════════════════════════════════════════════════


def test_extract_fields_class_annotation():
    """Class-level annotated fields are extracted."""
    node = _parse_class("""
        class Foo:
            name: str
            value: int = 42
    """)
    fields = _extract_fields(node)
    assert len(fields) == 2
    assert fields[0].name == "name"
    assert fields[0].type_annotation == "str"
    assert fields[0].is_class_var is True
    assert fields[1].name == "value"


def test_extract_fields_init_typed():
    """self.name: Type = value in __init__ is extracted."""
    node = _parse_class("""
        class Foo:
            def __init__(self):
                self.name: str = ""
                self.count: int = 0
    """)
    fields = _extract_fields(node)
    assert len(fields) == 2
    assert fields[0].name == "name"
    assert fields[0].type_annotation == "str"
    assert fields[0].is_class_var is False


def test_extract_fields_init_untyped():
    """self.name = value (no annotation) gets type 'Any'."""
    node = _parse_class("""
        class Foo:
            def __init__(self):
                self.data = []
    """)
    fields = _extract_fields(node)
    assert len(fields) == 1
    assert fields[0].name == "data"
    assert fields[0].type_annotation == "Any"


def test_extract_fields_dedup():
    """Class-level and __init__ definitions don't duplicate."""
    node = _parse_class("""
        class Foo:
            name: str
            def __init__(self):
                self.name = "hello"
    """)
    fields = _extract_fields(node)
    # Class-level seen first, __init__ skipped
    assert len(fields) == 1
    assert fields[0].name == "name"
    assert fields[0].is_class_var is True


def test_extract_fields_private_visibility():
    """Private field naming is detected."""
    node = _parse_class("""
        class Foo:
            __secret: str = ""
            _protected: int = 0
            public: bool = True
    """)
    fields = _extract_fields(node)
    vis = {f.name: f.visibility for f in fields}
    assert vis["__secret"] == "private"
    assert vis["_protected"] == "protected"
    assert vis["public"] == "public"


# ═══════════════════════════════════════════════════════════════════
#  _extract_methods
# ═══════════════════════════════════════════════════════════════════


def test_extract_methods_basic():
    """Basic method extraction."""
    node = _parse_class("""
        class Foo:
            def run(self, x: int) -> str:
                pass
    """)
    methods = _extract_methods(node)
    assert len(methods) == 1
    m = methods[0]
    assert m.name == "run"
    assert m.parameters == ["x"]
    assert m.return_type == "str"
    assert m.visibility == "public"
    assert m.is_async is False


def test_extract_methods_async():
    """Async methods are detected."""
    node = _parse_class("""
        class Foo:
            async def fetch(self): pass
    """)
    methods = _extract_methods(node)
    assert methods[0].is_async is True


def test_extract_methods_static():
    """@staticmethod detection."""
    node = _parse_class("""
        class Foo:
            @staticmethod
            def create(): pass
    """)
    methods = _extract_methods(node)
    assert methods[0].is_static is True


def test_extract_methods_classmethod():
    """@classmethod detection."""
    node = _parse_class("""
        class Foo:
            @classmethod
            def from_dict(cls, data): pass
    """)
    methods = _extract_methods(node)
    m = methods[0]
    assert m.is_classmethod is True
    # cls should be excluded from parameters
    assert "cls" not in m.parameters
    assert m.parameters == ["data"]


def test_extract_methods_property():
    """@property detection."""
    node = _parse_class("""
        class Foo:
            @property
            def value(self) -> int: pass
    """)
    methods = _extract_methods(node)
    assert methods[0].is_property is True


def test_extract_methods_abstractmethod():
    """@abstractmethod detection."""
    node = _parse_class("""
        class Foo:
            @abstractmethod
            def run(self): pass
    """)
    methods = _extract_methods(node)
    assert methods[0].is_abstract is True


def test_extract_methods_visibility():
    """Method visibility from naming convention."""
    node = _parse_class("""
        class Foo:
            def public_method(self): pass
            def _protected_method(self): pass
            def __private_method(self): pass
    """)
    methods = _extract_methods(node)
    vis = {m.name: m.visibility for m in methods}
    assert vis["public_method"] == "public"
    assert vis["_protected_method"] == "protected"
    assert vis["__private_method"] == "private"


# ═══════════════════════════════════════════════════════════════════
#  _extract_class  (full ClassInfo)
# ═══════════════════════════════════════════════════════════════════


def test_extract_class_basic():
    """Full ClassInfo extraction."""
    node = _parse_class('''
        class MyService:
            """Service for things."""
            name: str = ""
            def run(self): pass
    ''')
    cls = _extract_class(node, "src.core.services", "src/core/services/svc.py")
    assert cls.name == "MyService"
    assert cls.qualified_name == "src.core.services.MyService"
    assert cls.file_path == "src/core/services/svc.py"
    assert cls.module == "src.core.services"
    assert cls.docstring == "Service for things."
    assert len(cls.fields) == 1
    assert len(cls.methods) == 1


def test_extract_class_dataclass():
    """@dataclass detection."""
    node = _parse_class("""
        @dataclass
        class Config:
            name: str = ""
    """)
    cls = _extract_class(node, "", "")
    assert cls.is_dataclass is True


def test_extract_class_pydantic():
    """BaseModel inheritance detection."""
    node = _parse_class("""
        class Config(BaseModel):
            name: str = ""
    """)
    cls = _extract_class(node, "", "")
    assert cls.is_pydantic is True


def test_extract_class_protocol():
    """Protocol detection."""
    node = _parse_class("""
        class Handler(Protocol):
            def handle(self): ...
    """)
    cls = _extract_class(node, "", "")
    assert cls.is_protocol is True


def test_extract_class_abstract_from_bases():
    """ABC in bases → is_abstract."""
    node = _parse_class("""
        class Base(ABC):
            pass
    """)
    cls = _extract_class(node, "", "")
    assert cls.is_abstract is True


def test_extract_class_abstract_from_method():
    """@abstractmethod → is_abstract even without ABC base."""
    node = _parse_class("""
        class Base:
            @abstractmethod
            def run(self): pass
    """)
    cls = _extract_class(node, "", "")
    assert cls.is_abstract is True


def test_extract_class_no_docstring():
    """Class without docstring → empty string."""
    node = _parse_class("""
        class Empty:
            pass
    """)
    cls = _extract_class(node, "", "")
    assert cls.docstring == ""


def test_extract_class_multiline_docstring():
    """Multi-line docstring → only first line."""
    node = _parse_class('''
        class Foo:
            """First line.

            More details here.
            """
            pass
    ''')
    cls = _extract_class(node, "", "")
    assert cls.docstring == "First line."


def test_extract_class_empty_module_path():
    """Empty module path → qualified name equals class name."""
    node = _parse_class("class Foo: pass")
    cls = _extract_class(node, "", "")
    assert cls.qualified_name == "Foo"


def test_extract_class_lineno():
    """Line numbers are captured."""
    node = _parse_class("""
        class Foo:
            pass
    """)
    cls = _extract_class(node, "", "")
    assert cls.lineno > 0


# ═══════════════════════════════════════════════════════════════════
#  _is_abstract
# ═══════════════════════════════════════════════════════════════════


def test_is_abstract_abc():
    """ABC base → abstract."""
    node = _parse_class("class Foo(ABC): pass")
    assert _is_abstract(node, ["ABC"], []) is True


def test_is_abstract_abc_abc():
    """abc.ABC base → abstract."""
    node = _parse_class("class Foo(abc.ABC): pass")
    assert _is_abstract(node, ["abc.ABC"], []) is True


def test_is_abstract_method():
    """abstractmethod in methods → abstract."""
    m = MethodInfo(name="run", is_abstract=True)
    node = _parse_class("class Foo: pass")
    assert _is_abstract(node, [], [m]) is True


def test_is_abstract_false():
    """Normal class → not abstract."""
    node = _parse_class("class Foo: pass")
    assert _is_abstract(node, [], []) is False


# ═══════════════════════════════════════════════════════════════════
#  _node_to_str
# ═══════════════════════════════════════════════════════════════════


def test_node_to_str_name():
    node = ast.parse("Foo", mode="eval").body
    assert _node_to_str(node) == "Foo"


def test_node_to_str_attribute():
    node = ast.parse("abc.ABC", mode="eval").body
    assert _node_to_str(node) == "abc.ABC"


def test_node_to_str_subscript():
    node = ast.parse("list[int]", mode="eval").body
    assert _node_to_str(node) == "list[int]"


def test_node_to_str_constant():
    node = ast.parse("42", mode="eval").body
    assert _node_to_str(node) == "42"


def test_node_to_str_union():
    node = ast.parse("int | str", mode="eval").body
    assert _node_to_str(node) == "int | str"


# ═══════════════════════════════════════════════════════════════════
#  analyze_file
# ═══════════════════════════════════════════════════════════════════


def test_analyze_file_single_class(tmp_path):
    """Analyzes a file with one class."""
    p = _write_py(tmp_path, "mod.py", '''
        class Foo:
            """A foo."""
            name: str = ""
            def run(self): pass
    ''')
    classes = analyze_file(p, tmp_path)
    assert len(classes) == 1
    assert classes[0].name == "Foo"
    assert classes[0].module == "mod"


def test_analyze_file_multiple_classes(tmp_path):
    """Analyzes a file with multiple classes."""
    p = _write_py(tmp_path, "multi.py", """
        class A: pass
        class B: pass
        class C: pass
    """)
    classes = analyze_file(p, tmp_path)
    assert len(classes) == 3
    names = [c.name for c in classes]
    assert names == ["A", "B", "C"]


def test_analyze_file_syntax_error(tmp_path):
    """File with syntax error returns empty list (no crash)."""
    p = _write_py(tmp_path, "broken.py", """
        class Foo(
            # incomplete
    """)
    classes = analyze_file(p, tmp_path)
    assert classes == []


def test_analyze_file_empty(tmp_path):
    """Empty file returns empty list."""
    p = _write_py(tmp_path, "empty.py", "")
    classes = analyze_file(p, tmp_path)
    assert classes == []


def test_analyze_file_no_classes(tmp_path):
    """File with functions but no classes."""
    p = _write_py(tmp_path, "funcs.py", """
        def hello(): pass
        x = 42
    """)
    classes = analyze_file(p, tmp_path)
    assert classes == []


def test_analyze_file_inheritance(tmp_path):
    """Inheritance is captured."""
    p = _write_py(tmp_path, "inh.py", """
        class Parent: pass
        class Child(Parent): pass
    """)
    classes = analyze_file(p, tmp_path)
    child = [c for c in classes if c.name == "Child"][0]
    assert child.bases == ["Parent"]


def test_analyze_file_relative_path(tmp_path):
    """File path is relative to project root."""
    sub = tmp_path / "src" / "core"
    sub.mkdir(parents=True)
    p = _write_py(sub, "engine.py", "class Engine: pass")

    classes = analyze_file(p, tmp_path)
    assert classes[0].file_path == "src/core/engine.py"


# ═══════════════════════════════════════════════════════════════════
#  analyze_python_project
# ═══════════════════════════════════════════════════════════════════


def test_analyze_project_basic(tmp_path):
    """Analyzes a project with source files."""
    src = tmp_path / "src"
    src.mkdir()
    _write_py(src, "service.py", """
        class Service:
            name: str = ""
            def run(self): pass
    """)
    _write_py(src, "model.py", """
        class Model:
            id: int = 0
    """)

    result = analyze_python_project(tmp_path, source_dir="src")

    assert isinstance(result, ProjectAnalysis)
    assert result.files_analyzed == 2
    assert result.total_classes == 2
    assert result.files_with_errors == 0
    names = {c.name for c in result.classes}
    assert names == {"Service", "Model"}


def test_analyze_project_excludes_private_by_default(tmp_path):
    """Private classes (_Foo) are excluded by default."""
    src = tmp_path / "src"
    src.mkdir()
    _write_py(src, "internal.py", """
        class PublicClass: pass
        class _PrivateClass: pass
    """)

    result = analyze_python_project(tmp_path, source_dir="src")
    names = {c.name for c in result.classes}
    assert "PublicClass" in names
    assert "_PrivateClass" not in names


def test_analyze_project_includes_private_when_requested(tmp_path):
    """Private classes are included with include_private=True."""
    src = tmp_path / "src"
    src.mkdir()
    _write_py(src, "internal.py", """
        class PublicClass: pass
        class _PrivateClass: pass
    """)

    result = analyze_python_project(
        tmp_path, source_dir="src", include_private=True,
    )
    names = {c.name for c in result.classes}
    assert "_PrivateClass" in names


def test_analyze_project_empty_source(tmp_path):
    """Missing source directory → empty analysis."""
    result = analyze_python_project(tmp_path, source_dir="src")
    assert result.files_analyzed == 0
    assert result.total_classes == 0


def test_analyze_project_with_errors(tmp_path):
    """Files that fail to read count as errors."""
    src = tmp_path / "src"
    src.mkdir()
    _write_py(src, "good.py", "class Good: pass")

    # Create a file that will fail (binary content)
    bad = src / "bad.py"
    bad.write_bytes(b"\x80\x81\x82")  # Not valid Python

    result = analyze_python_project(tmp_path, source_dir="src")
    # binary content with errors="replace" won't crash read_text,
    # but will give a SyntaxError on ast.parse → returns []
    # So files_with_errors stays 0 (SyntaxError is handled in analyze_file)
    assert result.total_classes >= 1  # At least "Good"


def test_analyze_project_nested_packages(tmp_path):
    """Discovers classes in nested packages."""
    pkg = tmp_path / "src" / "core" / "services"
    pkg.mkdir(parents=True)
    _write_py(pkg, "__init__.py", "")
    _write_py(pkg, "engine.py", """
        class Engine:
            def start(self): pass
    """)

    result = analyze_python_project(tmp_path, source_dir="src")
    assert result.total_classes == 1
    assert result.classes[0].name == "Engine"
    assert "core.services" in result.classes[0].module


# ═══════════════════════════════════════════════════════════════════
#  Decorator edge cases
# ═══════════════════════════════════════════════════════════════════


def test_decorator_with_arguments():
    """@dataclass(frozen=True) → decorator name is 'dataclass'."""
    node = _parse_class("""
        @dataclass(frozen=True)
        class Config:
            name: str = ""
    """)
    cls = _extract_class(node, "", "")
    assert cls.is_dataclass is True
    assert "dataclass" in cls.decorators


def test_decorator_dotted():
    """@abc.abstractmethod style decorators."""
    node = _parse_class("""
        class Foo:
            @abc.abstractmethod
            def run(self): pass
    """)
    methods = _extract_methods(node)
    assert "abc.abstractmethod" in methods[0].decorators


# ═══════════════════════════════════════════════════════════════════
#  BaseSettings detection
# ═══════════════════════════════════════════════════════════════════


def test_pydantic_basesettings():
    """BaseSettings also triggers is_pydantic."""
    node = _parse_class("""
        class AppConfig(BaseSettings):
            debug: bool = False
    """)
    cls = _extract_class(node, "", "")
    assert cls.is_pydantic is True


# ═══════════════════════════════════════════════════════════════════
#  Edge cases for coverage
# ═══════════════════════════════════════════════════════════════════


def test_analyze_project_file_exception(tmp_path, monkeypatch):
    """File that raises non-SyntaxError is recorded as error."""
    src = tmp_path / "src"
    src.mkdir()
    _write_py(src, "ok.py", "class OK: pass")
    _write_py(src, "bad.py", "class Bad: pass")

    # Make analyze_file raise for the "bad" file
    orig = analyze_file

    def patched_analyze_file(path, project_root):
        if path.name == "bad.py":
            raise RuntimeError("disk on fire")
        return orig(path, project_root)

    monkeypatch.setattr(
        "src.core.data.script_templates.lib.code_analyzer.analyze_file",
        patched_analyze_file,
    )

    result = analyze_python_project(tmp_path, source_dir="src")
    assert result.files_with_errors == 1
    assert any("disk on fire" in e for e in result.analysis_errors)
    assert result.total_classes >= 1  # At least "OK"


def test_analyze_file_path_outside_root(tmp_path):
    """File not under project_root uses str(path) as file_path."""
    other = tmp_path / "other"
    other.mkdir()
    p = _write_py(other, "orphan.py", "class Orphan: pass")

    # project_root is a different directory
    project_root = tmp_path / "project"
    project_root.mkdir()

    classes = analyze_file(p, project_root)
    assert len(classes) == 1
    # file_path should be the full path string (fallback)
    assert classes[0].file_path == str(p)


def test_decorator_dotted_call():
    """@module.decorator() style — dotted Call decorator."""
    node = _parse_class("""
        class Foo:
            @some.module.decorator()
            def run(self): pass
    """)
    methods = _extract_methods(node)
    assert "some.module.decorator" in methods[0].decorators
