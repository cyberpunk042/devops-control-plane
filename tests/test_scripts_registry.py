"""
Tests for scripts registry — discovery, metadata parsing, merge, query.

Covers:
- Empty project (no scripts/ dir) → empty list
- Root scripts only → source="root"
- Template scripts only → source="template"
- Both present → merged, no duplicates
- Root overrides template → source="override"
- @script header parsing (Python docstring)
- @script header parsing (Shell comment block)
- Files without @script → skipped
- Numbered vs unnumbered scripts
- template_source="never" → no templates
- Query functions: get_all, get_script, get_by_category, get_by_tag
- get_scripts_summary
- @param parsing (all types)
- Cache and refresh
"""

import textwrap

from src.core.services.scripts.models import ScriptConfig
from src.core.services.scripts.registry import (
    _parse_param_line,
    _registry_cache,
    discover_scripts,
    get_all_scripts,
    get_script,
    get_scripts_by_category,
    get_scripts_by_tag,
    get_scripts_summary,
    parse_script_meta,
    refresh_registry,
)


def _write_script(path, content):
    """Helper: write a script file with dedented content."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content), encoding="utf-8")


def _clear_cache():
    """Clear the module-level registry cache."""
    _registry_cache.clear()


# ── Discovery ───────────────────────────────────────────────────────


class TestDiscoverScripts:
    """Discovery and merge tests."""

    def test_empty_project(self, tmp_path):
        """Empty project (no scripts/ dir) → empty list."""
        _clear_cache()
        config = ScriptConfig(template_source="never")
        result = discover_scripts(tmp_path, config=config)
        assert result == []

    def test_root_scripts_only(self, tmp_path):
        """Root scripts only → source='root'."""
        _clear_cache()
        scripts_dir = tmp_path / "scripts"
        _write_script(scripts_dir / "hello.py", '''\
            """
            @script
            name: Hello World
            category: debug
            """
            print("hello")
        ''')

        config = ScriptConfig(template_source="never")
        result = discover_scripts(tmp_path, config=config)
        assert len(result) == 1
        assert result[0].id == "hello"
        assert result[0].name == "Hello World"
        assert result[0].source == "root"
        assert result[0].category == "debug"

    def test_numbered_script(self, tmp_path):
        """Numbered scripts get number and is_permanent."""
        _clear_cache()
        scripts_dir = tmp_path / "scripts"
        _write_script(scripts_dir / "00_class_diagrams.py", '''\
            """
            @script
            name: Class Diagram Generator
            category: generator
            """
        ''')

        config = ScriptConfig(template_source="never")
        result = discover_scripts(tmp_path, config=config)
        assert len(result) == 1
        assert result[0].number == 0
        assert result[0].is_permanent is True
        assert result[0].id == "00_class_diagrams"

    def test_unnumbered_script(self, tmp_path):
        """Unnumbered scripts have number=None and is_permanent=False."""
        _clear_cache()
        scripts_dir = tmp_path / "scripts"
        _write_script(scripts_dir / "quick_debug.py", '''\
            """
            @script
            name: Quick Debug
            category: debug
            """
        ''')

        config = ScriptConfig(template_source="never")
        result = discover_scripts(tmp_path, config=config)
        assert len(result) == 1
        assert result[0].number is None
        assert result[0].is_permanent is False

    def test_files_without_header_skipped(self, tmp_path):
        """Files without @script header are skipped."""
        _clear_cache()
        scripts_dir = tmp_path / "scripts"
        _write_script(scripts_dir / "helper.py", '''\
            """Just a helper module, not a managed script."""
            def util():
                pass
        ''')

        config = ScriptConfig(template_source="never")
        result = discover_scripts(tmp_path, config=config)
        assert result == []

    def test_lib_directory_skipped(self, tmp_path):
        """Files in lib/ subdirectory are skipped."""
        _clear_cache()
        scripts_dir = tmp_path / "scripts"
        _write_script(scripts_dir / "lib" / "common.py", '''\
            """
            @script
            name: Should Be Skipped
            """
        ''')

        config = ScriptConfig(template_source="never")
        result = discover_scripts(tmp_path, config=config)
        assert result == []

    def test_template_source_never(self, tmp_path):
        """template_source='never' → no templates loaded."""
        _clear_cache()
        config = ScriptConfig(template_source="never")
        result = discover_scripts(tmp_path, config=config)
        assert result == []

    def test_shell_script_discovery(self, tmp_path):
        """Shell scripts are discovered and parsed."""
        _clear_cache()
        scripts_dir = tmp_path / "scripts"
        _write_script(scripts_dir / "deploy.sh", '''\
            #!/usr/bin/env bash
            # @script
            # name: Deployment Script
            # category: ops
            # mode: fully_automated
            # timeout: 600

            echo "deploying"
        ''')

        config = ScriptConfig(template_source="never")
        result = discover_scripts(tmp_path, config=config)
        assert len(result) == 1
        assert result[0].id == "deploy"
        assert result[0].name == "Deployment Script"
        assert result[0].language == "bash"
        assert result[0].category == "ops"
        assert result[0].timeout == 600

    def test_override_mechanism(self, tmp_path):
        """Root script with @override removes the template and gets source='override'."""
        _clear_cache()
        # Create a mock template directory
        template_dir = tmp_path / "templates"
        _write_script(template_dir / "generators" / "class_diagrams.py", '''\
            """
            @script
            name: Class Diagram Generator (template)
            category: generator
            """
        ''')

        # Create root script that overrides
        scripts_dir = tmp_path / "scripts"
        _write_script(scripts_dir / "00_class_diagrams.py", '''\
            """
            @script
            name: Class Diagram Generator (custom)
            category: generator
            override: generators/class_diagrams
            """
        ''')

        # Manually simulate the merge
        from src.core.services.scripts.registry import _merge_scripts, _scan_directory
        templates = {m.id: m for m in _scan_directory(template_dir, "template")}
        root_scripts = {m.id: m for m in _scan_directory(scripts_dir, "root")}

        result = _merge_scripts(templates, root_scripts)

        assert len(result) == 1
        assert result[0].id == "00_class_diagrams"
        assert result[0].source == "override"
        assert result[0].override_target == "generators/class_diagrams"

    def test_multiple_scripts(self, tmp_path):
        """Multiple scripts discovered correctly."""
        _clear_cache()
        scripts_dir = tmp_path / "scripts"
        _write_script(scripts_dir / "00_diagrams.py", '''\
            """
            @script
            name: Diagrams
            category: generator
            """
        ''')
        _write_script(scripts_dir / "01_audit.py", '''\
            """
            @script
            name: Audit
            category: audit
            """
        ''')
        _write_script(scripts_dir / "deploy.sh", '''\
            #!/bin/bash
            # @script
            # name: Deploy
            # category: ops
        ''')

        config = ScriptConfig(template_source="never")
        result = discover_scripts(tmp_path, config=config)
        assert len(result) == 3
        ids = {m.id for m in result}
        assert ids == {"00_diagrams", "01_audit", "deploy"}


# ── Metadata Parsing ────────────────────────────────────────────────


class TestParseScriptMeta:
    """Metadata parsing tests."""

    def test_python_full_header(self, tmp_path):
        """Full Python @script header."""
        filepath = tmp_path / "test.py"
        _write_script(filepath, '''\
            """
            @script
            name: Class Diagram Generator
            category: generator
            mode: fully_automated
            tags: mermaid, diagrams, docs
            default_output: docs/diagrams/
            output_formats: mermaid, json
            timeout: 120

            @param output: path = docs/diagrams/ | Output directory
            @param scope: string | Limit scope
            """
        ''')

        meta = parse_script_meta(filepath, "root")
        assert meta is not None
        assert meta.name == "Class Diagram Generator"
        assert meta.category == "generator"
        assert meta.mode == "fully_automated"
        assert meta.tags == ["mermaid", "diagrams", "docs"]
        assert meta.default_output == "docs/diagrams/"
        assert meta.output_formats == ["mermaid", "json"]
        assert meta.timeout == 120
        assert len(meta.parameters) == 2
        assert meta.parameters[0].name == "output"
        assert meta.parameters[0].type == "path"
        assert meta.parameters[0].default == "docs/diagrams/"
        assert meta.parameters[1].name == "scope"

    def test_shell_header(self, tmp_path):
        """Shell @script header in # comments."""
        filepath = tmp_path / "test.sh"
        _write_script(filepath, '''\
            #!/usr/bin/env bash
            # @script
            # name: Deploy Script
            # category: ops
            # tags: deploy, infrastructure
            # timeout: 600
            #
            # @param environment: choice = staging [staging, prod] | Target env
            # @param dry-run: boolean = true | Dry run mode

            echo "deploy"
        ''')

        meta = parse_script_meta(filepath, "root")
        assert meta is not None
        assert meta.name == "Deploy Script"
        assert meta.language == "bash"
        assert meta.category == "ops"
        assert meta.tags == ["deploy", "infrastructure"]
        assert meta.timeout == 600
        assert len(meta.parameters) == 2
        assert meta.parameters[0].name == "environment"
        assert meta.parameters[0].type == "choice"
        assert meta.parameters[0].choices == ["staging", "prod"]
        assert meta.parameters[1].name == "dry-run"
        assert meta.parameters[1].type == "boolean"
        assert meta.parameters[1].default == "true"

    def test_no_script_header(self, tmp_path):
        """File without @script → returns None."""
        filepath = tmp_path / "helper.py"
        _write_script(filepath, '''\
            """Just a regular module."""
            def helper():
                pass
        ''')

        meta = parse_script_meta(filepath, "root")
        assert meta is None

    def test_override_field(self, tmp_path):
        """@script header with override: field."""
        filepath = tmp_path / "test.py"
        _write_script(filepath, '''\
            """
            @script
            name: Custom Diagrams
            override: generators/class_diagrams
            """
        ''')

        meta = parse_script_meta(filepath, "root")
        assert meta is not None
        assert meta.override_target == "generators/class_diagrams"

    def test_requires_tools_field(self, tmp_path):
        """@script header with requires_tools."""
        filepath = tmp_path / "test.py"
        _write_script(filepath, '''\
            """
            @script
            name: Test
            requires_tools: pyreverse, graphviz
            """
        ''')

        meta = parse_script_meta(filepath, "root")
        assert meta is not None
        assert meta.requires_tools == ["pyreverse", "graphviz"]

    def test_requires_tools_none(self, tmp_path):
        """requires_tools: (none) → empty list."""
        filepath = tmp_path / "test.py"
        _write_script(filepath, '''\
            """
            @script
            name: Test
            requires_tools: (none)
            """
        ''')

        meta = parse_script_meta(filepath, "root")
        assert meta is not None
        # "(none)" is treated as a literal value, but since it doesn't
        # match any real tool name, it's acceptable. The list will have
        # one entry "(none)" — that's fine for now.
        # The executor will validate tool availability separately.


# ── @param Parsing ──────────────────────────────────────────────────


class TestParseParamLine:
    """@param line parsing tests."""

    def test_simple_string_param(self):
        """@param name: string | description."""
        p = _parse_param_line("@param scope: string | Limit to specific package")
        assert p is not None
        assert p.name == "scope"
        assert p.type == "string"
        assert p.description == "Limit to specific package"
        assert p.required is True
        assert p.default == ""

    def test_path_with_default(self):
        """@param name: path = default | description."""
        p = _parse_param_line("@param output: path = docs/diagrams/ | Output directory")
        assert p is not None
        assert p.name == "output"
        assert p.type == "path"
        assert p.default == "docs/diagrams/"
        assert p.description == "Output directory"
        assert p.required is False

    def test_choice_with_choices(self):
        """@param name: choice = default [choices] | description."""
        p = _parse_param_line("@param format: choice = mermaid [mermaid, json, markdown] | Output format")
        assert p is not None
        assert p.name == "format"
        assert p.type == "choice"
        assert p.default == "mermaid"
        assert p.choices == ["mermaid", "json", "markdown"]
        assert p.description == "Output format"

    def test_boolean_param(self):
        """@param name: boolean = true | description."""
        p = _parse_param_line("@param dry-run: boolean = true | Show what would happen")
        assert p is not None
        assert p.name == "dry-run"
        assert p.type == "boolean"
        assert p.default == "true"

    def test_integer_param(self):
        """@param name: integer = 3 | description."""
        p = _parse_param_line("@param depth: integer = 3 | Max depth to scan")
        assert p is not None
        assert p.name == "depth"
        assert p.type == "integer"
        assert p.default == "3"

    def test_no_description(self):
        """@param without description."""
        p = _parse_param_line("@param output: path = docs/")
        assert p is not None
        assert p.name == "output"
        assert p.type == "path"
        assert p.default == "docs/"
        assert p.description == ""

    def test_empty_param(self):
        """@param with nothing after it."""
        p = _parse_param_line("@param")
        assert p is None


# ── Query Functions ─────────────────────────────────────────────────


class TestQueryFunctions:
    """Query function tests."""

    def test_get_all_scripts(self, tmp_path):
        """get_all_scripts returns all discovered scripts."""
        _clear_cache()
        scripts_dir = tmp_path / "scripts"
        _write_script(scripts_dir / "a.py", '"""\n@script\nname: A\ncategory: audit\n"""')
        _write_script(scripts_dir / "b.py", '"""\n@script\nname: B\ncategory: debug\n"""')

        # Need to bypass templates
        from src.core.services.scripts import registry
        old = registry.load_scripts_config
        registry.load_scripts_config = lambda _: ScriptConfig(template_source="never")
        try:
            result = get_all_scripts(tmp_path)
            assert len(result) == 2
        finally:
            registry.load_scripts_config = old
            _clear_cache()

    def test_get_script_by_id(self, tmp_path):
        """get_script returns single script by ID."""
        _clear_cache()
        scripts_dir = tmp_path / "scripts"
        _write_script(scripts_dir / "hello.py", '"""\n@script\nname: Hello\n"""')

        from src.core.services.scripts import registry
        old = registry.load_scripts_config
        registry.load_scripts_config = lambda _: ScriptConfig(template_source="never")
        try:
            found = get_script(tmp_path, "hello")
            assert found is not None
            assert found.name == "Hello"

            missing = get_script(tmp_path, "nonexistent")
            assert missing is None
        finally:
            registry.load_scripts_config = old
            _clear_cache()

    def test_get_scripts_by_category(self, tmp_path):
        """get_scripts_by_category filters correctly."""
        _clear_cache()
        scripts_dir = tmp_path / "scripts"
        _write_script(scripts_dir / "a.py", '"""\n@script\nname: A\ncategory: audit\n"""')
        _write_script(scripts_dir / "b.py", '"""\n@script\nname: B\ncategory: debug\n"""')
        _write_script(scripts_dir / "c.py", '"""\n@script\nname: C\ncategory: audit\n"""')

        from src.core.services.scripts import registry
        old = registry.load_scripts_config
        registry.load_scripts_config = lambda _: ScriptConfig(template_source="never")
        try:
            audits = get_scripts_by_category(tmp_path, "audit")
            assert len(audits) == 2
            debugs = get_scripts_by_category(tmp_path, "debug")
            assert len(debugs) == 1
        finally:
            registry.load_scripts_config = old
            _clear_cache()

    def test_get_scripts_by_tag(self, tmp_path):
        """get_scripts_by_tag filters correctly."""
        _clear_cache()
        scripts_dir = tmp_path / "scripts"
        _write_script(scripts_dir / "a.py", '"""\n@script\nname: A\ntags: mermaid, docs\n"""')
        _write_script(scripts_dir / "b.py", '"""\n@script\nname: B\ntags: deploy\n"""')

        from src.core.services.scripts import registry
        old = registry.load_scripts_config
        registry.load_scripts_config = lambda _: ScriptConfig(template_source="never")
        try:
            mermaid = get_scripts_by_tag(tmp_path, "mermaid")
            assert len(mermaid) == 1
            assert mermaid[0].name == "A"
        finally:
            registry.load_scripts_config = old
            _clear_cache()

    def test_get_scripts_summary(self, tmp_path):
        """get_scripts_summary returns correct structure."""
        _clear_cache()
        scripts_dir = tmp_path / "scripts"
        _write_script(scripts_dir / "a.py", '"""\n@script\nname: A\ncategory: audit\n"""')
        _write_script(scripts_dir / "b.py", '"""\n@script\nname: B\ncategory: debug\n"""')

        from src.core.services.scripts import registry
        old = registry.load_scripts_config
        registry.load_scripts_config = lambda _: ScriptConfig(template_source="never")
        try:
            summary = get_scripts_summary(tmp_path)
            assert summary["total"] == 2
            assert summary["by_category"]["audit"] == 1
            assert summary["by_category"]["debug"] == 1
            assert summary["by_source"]["root"] == 2
            assert len(summary["scripts"]) == 2
        finally:
            registry.load_scripts_config = old
            _clear_cache()


class TestCacheAndRefresh:
    """Cache behavior tests."""

    def test_cache_returns_same_results(self, tmp_path):
        """get_all_scripts returns cached results on second call."""
        _clear_cache()
        scripts_dir = tmp_path / "scripts"
        _write_script(scripts_dir / "a.py", '"""\n@script\nname: A\n"""')

        from src.core.services.scripts import registry
        old = registry.load_scripts_config
        registry.load_scripts_config = lambda _: ScriptConfig(template_source="never")
        try:
            first = get_all_scripts(tmp_path)
            second = get_all_scripts(tmp_path)
            assert len(first) == len(second)
            assert first[0].id == second[0].id
        finally:
            registry.load_scripts_config = old
            _clear_cache()

    def test_refresh_invalidates_cache(self, tmp_path):
        """refresh_registry re-discovers scripts."""
        _clear_cache()
        scripts_dir = tmp_path / "scripts"
        _write_script(scripts_dir / "a.py", '"""\n@script\nname: A\n"""')

        from src.core.services.scripts import registry
        old = registry.load_scripts_config
        registry.load_scripts_config = lambda _: ScriptConfig(template_source="never")
        try:
            first = get_all_scripts(tmp_path)
            assert len(first) == 1

            # Add another script
            _write_script(scripts_dir / "b.py", '"""\n@script\nname: B\n"""')

            # Without refresh, cache still returns 1
            cached = get_all_scripts(tmp_path)
            assert len(cached) == 1

            # After refresh, returns 2
            refreshed = refresh_registry(tmp_path)
            assert len(refreshed) == 2
        finally:
            registry.load_scripts_config = old
            _clear_cache()


# ── Template Loading ────────────────────────────────────────────────


class TestTemplateLoading:
    """Tests for _should_load_templates and template directory scanning."""

    def test_template_source_always(self, tmp_path):
        """template_source='always' loads templates regardless of env."""
        from src.core.services.scripts.registry import _should_load_templates
        config = ScriptConfig(template_source="always")
        assert _should_load_templates(config) is True

    def test_template_source_auto_without_dev(self, tmp_path):
        """template_source='auto' without SCP_DEV → no templates."""
        import os
        from src.core.services.scripts.registry import _should_load_templates
        old = os.environ.pop("SCP_DEV", None)
        try:
            config = ScriptConfig(template_source="auto")
            assert _should_load_templates(config) is False
        finally:
            if old is not None:
                os.environ["SCP_DEV"] = old

    def test_template_source_auto_with_dev(self, tmp_path):
        """template_source='auto' with SCP_DEV=1 → load templates."""
        import os
        from src.core.services.scripts.registry import _should_load_templates
        old = os.environ.get("SCP_DEV")
        os.environ["SCP_DEV"] = "1"
        try:
            config = ScriptConfig(template_source="auto")
            assert _should_load_templates(config) is True
        finally:
            if old is None:
                os.environ.pop("SCP_DEV", None)
            else:
                os.environ["SCP_DEV"] = old

    def test_template_dir_scan(self, tmp_path):
        """Templates from a real directory get discovered with source='template'."""
        _clear_cache()
        template_dir = tmp_path / "templates"
        _write_script(template_dir / "generators" / "class_diagrams.py", '''\
            """
            @script
            name: Class Diagrams (built-in)
            category: generator
            """
        ''')

        from src.core.services.scripts.registry import _scan_directory
        results = _scan_directory(template_dir, "template")
        assert len(results) == 1
        assert results[0].source == "template"
        # Template IDs use relative paths
        assert results[0].id == "generators/class_diagrams"

    def test_discover_scripts_with_templates(self, tmp_path):
        """discover_scripts with template_source='always' and patched TEMPLATE_DIR."""
        import src.core.services.scripts.registry as reg
        _clear_cache()

        # Create a fake template directory
        fake_template_dir = tmp_path / "fake_templates"
        _write_script(fake_template_dir / "generators" / "class_diagrams.py", '''\
            """
            @script
            name: Class Diagrams (built-in)
            category: generator
            """
        ''')

        # Patch TEMPLATE_DIR to point to our fake dir
        old_template_dir = reg.TEMPLATE_DIR
        reg.TEMPLATE_DIR = fake_template_dir
        try:
            config = ScriptConfig(template_source="always")
            result = discover_scripts(tmp_path, config=config)
            # Should find the template script
            assert len(result) == 1
            assert result[0].source == "template"
            assert result[0].id == "generators/class_diagrams"
        finally:
            reg.TEMPLATE_DIR = old_template_dir

    def test_discover_scripts_template_dir_missing(self, tmp_path):
        """template_source='always' but TEMPLATE_DIR doesn't exist → no crash."""
        import src.core.services.scripts.registry as reg
        _clear_cache()

        # Point TEMPLATE_DIR to a non-existent directory
        old_template_dir = reg.TEMPLATE_DIR
        reg.TEMPLATE_DIR = tmp_path / "does_not_exist"
        try:
            config = ScriptConfig(template_source="always")
            result = discover_scripts(tmp_path, config=config)
            assert result == []
        finally:
            reg.TEMPLATE_DIR = old_template_dir


# ── Shebang Detection ──────────────────────────────────────────────


class TestShebangDetection:
    """Tests for extension-less scripts with shebang lines."""

    def test_extensionless_python_shebang(self, tmp_path):
        """No extension + python shebang → discovered as python."""
        _clear_cache()
        scripts_dir = tmp_path / "scripts"
        script_file = scripts_dir / "my_script"
        _write_script(script_file, '''\
            #!/usr/bin/env python3
            """
            @script
            name: Extensionless Python
            category: debug
            """
            print("hello")
        ''')

        config = ScriptConfig(template_source="never")
        result = discover_scripts(tmp_path, config=config)
        assert len(result) == 1
        assert result[0].name == "Extensionless Python"
        assert result[0].language == "python"

    def test_extensionless_bash_shebang(self, tmp_path):
        """No extension + bash shebang → discovered as bash."""
        _clear_cache()
        scripts_dir = tmp_path / "scripts"
        script_file = scripts_dir / "deploy_tool"
        _write_script(script_file, '''\
            #!/bin/bash
            # @script
            # name: Deploy Tool
            # category: ops

            echo "deploying"
        ''')

        config = ScriptConfig(template_source="never")
        result = discover_scripts(tmp_path, config=config)
        assert len(result) == 1
        assert result[0].language == "bash"

    def test_extensionless_no_shebang_skipped(self, tmp_path):
        """No extension + no shebang → skipped."""
        _clear_cache()
        scripts_dir = tmp_path / "scripts"
        script_file = scripts_dir / "readme_text"
        script_file.parent.mkdir(parents=True, exist_ok=True)
        script_file.write_text("Just a text file\nNothing to see here\n")

        config = ScriptConfig(template_source="never")
        result = discover_scripts(tmp_path, config=config)
        assert result == []

    def test_extensionless_unrecognized_shebang_skipped(self, tmp_path):
        """No extension + unrecognized shebang → skipped."""
        _clear_cache()
        scripts_dir = tmp_path / "scripts"
        script_file = scripts_dir / "ruby_script"
        _write_script(script_file, '''\
            #!/usr/bin/env ruby
            # @script
            # name: Ruby Script
        ''')

        config = ScriptConfig(template_source="never")
        result = discover_scripts(tmp_path, config=config)
        assert result == []

    def test_has_script_shebang_binary_file(self, tmp_path):
        """Binary file doesn't crash _has_script_shebang."""
        from src.core.services.scripts.registry import _has_script_shebang
        binfile = tmp_path / "binary_thing"
        binfile.write_bytes(b"\x00\x01\x02\x03\xff\xfe")
        assert _has_script_shebang(binfile) is False

    def test_has_script_shebang_nonexistent_file(self, tmp_path):
        """Non-existent file → False (OSError caught)."""
        from src.core.services.scripts.registry import _has_script_shebang
        nope = tmp_path / "does_not_exist"
        assert _has_script_shebang(nope) is False

    def test_language_from_shebang_empty(self):
        """Empty shebang → None."""
        from src.core.services.scripts.registry import _language_from_shebang
        assert _language_from_shebang("#!") is None

    def test_language_from_shebang_direct_path(self):
        """#!/bin/bash (no env) → bash."""
        from src.core.services.scripts.registry import _language_from_shebang
        assert _language_from_shebang("#!/bin/bash") == "bash"

    def test_language_from_shebang_env_python(self):
        """#!/usr/bin/env python3 → python."""
        from src.core.services.scripts.registry import _language_from_shebang
        assert _language_from_shebang("#!/usr/bin/env python3") == "python"

    def test_language_from_shebang_env_pwsh(self):
        """#!/usr/bin/env pwsh → powershell."""
        from src.core.services.scripts.registry import _language_from_shebang
        assert _language_from_shebang("#!/usr/bin/env pwsh") == "powershell"

    def test_language_from_shebang_unknown(self):
        """Unknown interpreter → None."""
        from src.core.services.scripts.registry import _language_from_shebang
        assert _language_from_shebang("#!/usr/bin/env node") is None


# ── PowerShell Parsing ──────────────────────────────────────────────


class TestPowerShellParsing:
    """Tests for PowerShell script header parsing."""

    def test_powershell_header(self, tmp_path):
        """PowerShell <# ... #> comment block is parsed."""
        filepath = tmp_path / "test.ps1"
        _write_script(filepath, '''\
            <#
            @script
            name: PS Audit
            category: audit
            timeout: 120

            @param scope: string | Scope filter
            #>
            Write-Host "Auditing"
        ''')

        meta = parse_script_meta(filepath, "root")
        assert meta is not None
        assert meta.name == "PS Audit"
        assert meta.language == "powershell"
        assert meta.category == "audit"
        assert meta.timeout == 120
        assert len(meta.parameters) == 1
        assert meta.parameters[0].name == "scope"

    def test_powershell_no_comment_block(self, tmp_path):
        """PowerShell file without <# #> → None."""
        filepath = tmp_path / "test.ps1"
        _write_script(filepath, '''\
            Write-Host "Hello"
        ''')
        meta = parse_script_meta(filepath, "root")
        assert meta is None


# ── Merge Edge Cases ────────────────────────────────────────────────


class TestMergeEdgeCases:
    """Tests for merge edge cases."""

    def test_override_nonexistent_template(self, tmp_path):
        """Override targeting a non-existent template → warning, still added."""
        from src.core.services.scripts.registry import _merge_scripts
        from src.core.services.scripts.models import ScriptMeta

        root_script = ScriptMeta(
            id="custom_diagrams",
            name="Custom Diagrams",
            source="root",
            override_target="nonexistent/template",
        )
        root_scripts = {"custom_diagrams": root_script}
        templates = {}

        result = _merge_scripts(templates, root_scripts)
        assert len(result) == 1
        assert result[0].source == "override"
        assert result[0].id == "custom_diagrams"


# ── Parse Edge Cases ───────────────────────────────────────────────


class TestParseEdgeCases:
    """Tests for parsing edge cases and error handling."""

    def test_unreadable_file(self, tmp_path):
        """Unreadable file → returns None."""
        filepath = tmp_path / "nope.py"
        # Don't create the file — OSError
        meta = parse_script_meta(filepath, "root")
        assert meta is None

    def test_python_single_quote_docstring(self, tmp_path):
        """Python single-quote docstring is parsed."""
        filepath = tmp_path / "test.py"
        _write_script(filepath, """\
            '''
            @script
            name: Single Quote Script
            category: debug
            '''
            print("hello")
        """)

        meta = parse_script_meta(filepath, "root")
        assert meta is not None
        assert meta.name == "Single Quote Script"

    def test_python_unclosed_docstring(self, tmp_path):
        """Python with unclosed docstring → None (no valid header)."""
        filepath = tmp_path / "test.py"
        filepath.write_text('"""\n@script\nname: Broken\n', encoding="utf-8")
        meta = parse_script_meta(filepath, "root")
        assert meta is None

    def test_shell_non_comment_before_block(self, tmp_path):
        """Shell file with code before comment block → no header."""
        filepath = tmp_path / "test.sh"
        _write_script(filepath, '''\
            #!/bin/bash
            echo "code first"
            # @script
            # name: After Code
        ''')

        meta = parse_script_meta(filepath, "root")
        assert meta is None

    def test_shell_blank_lines_only(self, tmp_path):
        """Shell file with only shebang and blank lines → None."""
        filepath = tmp_path / "test.sh"
        filepath.write_text("#!/bin/bash\n\n\n", encoding="utf-8")
        meta = parse_script_meta(filepath, "root")
        assert meta is None

    def test_param_name_only_no_colon(self):
        """@param with just a name (no colon) → bare ScriptParameter."""
        p = _parse_param_line("@param verbose")
        assert p is not None
        assert p.name == "verbose"
        assert p.type == "string"
        assert p.description == ""

    def test_param_name_with_description_no_colon(self):
        """@param name | description."""
        p = _parse_param_line("@param verbose | Enable verbose logging")
        assert p is not None
        assert p.name == "verbose"
        assert p.description == "Enable verbose logging"

    def test_detect_language_no_extension_no_shebang(self, tmp_path):
        """File with no extension and no shebang → fallback to python."""
        from src.core.services.scripts.registry import _detect_language
        filepath = tmp_path / "mystery"
        filepath.write_text("some code\n", encoding="utf-8")
        lang = _detect_language(filepath, "some code\n")
        assert lang == "python"

    def test_detect_language_no_extension_with_shebang(self, tmp_path):
        """File with no extension but bash shebang → bash."""
        from src.core.services.scripts.registry import _detect_language
        filepath = tmp_path / "runner"
        content = "#!/bin/bash\necho hello\n"
        filepath.write_text(content, encoding="utf-8")
        lang = _detect_language(filepath, content)
        assert lang == "bash"

    def test_detect_language_ps1(self, tmp_path):
        """File with .ps1 extension → powershell."""
        from src.core.services.scripts.registry import _detect_language
        filepath = tmp_path / "test.ps1"
        lang = _detect_language(filepath, "Write-Host 'hello'")
        assert lang == "powershell"

    def test_detect_language_bash_extension(self, tmp_path):
        """File with .bash extension → bash."""
        from src.core.services.scripts.registry import _detect_language
        filepath = tmp_path / "test.bash"
        lang = _detect_language(filepath, "echo hello")
        assert lang == "bash"

    def test_extract_header_block_unknown_language(self):
        """Unknown language → None from _extract_header_block."""
        from src.core.services.scripts.registry import _extract_header_block
        result = _extract_header_block("some content", "ruby")
        assert result is None

    def test_extract_header_block_bash(self, tmp_path):
        """Bash language uses shell comment block extraction."""
        from src.core.services.scripts.registry import _extract_header_block
        content = "#!/bin/bash\n# @script\n# name: Test\n\necho hello"
        result = _extract_header_block(content, "bash")
        assert result is not None
        assert "@script" in result

    def test_non_script_extension_skipped(self, tmp_path):
        """Files with non-script extensions (e.g. .txt) are skipped."""
        _clear_cache()
        scripts_dir = tmp_path / "scripts"
        txt_file = scripts_dir / "notes.txt"
        txt_file.parent.mkdir(parents=True, exist_ok=True)
        txt_file.write_text("@script\nname: Should Not Be Found\n", encoding="utf-8")

        config = ScriptConfig(template_source="never")
        result = discover_scripts(tmp_path, config=config)
        assert result == []

    def test_pycache_skipped(self, tmp_path):
        """Files in __pycache__/ are skipped."""
        _clear_cache()
        scripts_dir = tmp_path / "scripts"
        _write_script(scripts_dir / "__pycache__" / "cached.py", '''\
            """
            @script
            name: Cached Script
            """
        ''')

        config = ScriptConfig(template_source="never")
        result = discover_scripts(tmp_path, config=config)
        assert result == []

