"""
Tests for scripts output router — target resolution and env injection.

Covers:
- Resolution priority: override > meta.default_output > config.default_output
- Directory creation
- Relative → absolute path resolution
- Env var injection (all 6 variables)
- Non-mutation of input dict
"""

from pathlib import Path

from src.core.services.scripts.models import ScriptConfig, ScriptMeta
from src.core.services.scripts.output_router import (
    inject_output_env,
    resolve_output_target,
)


class TestResolveOutputTarget:
    """Output target resolution tests."""

    def test_explicit_override(self, tmp_path):
        """Override takes highest priority."""
        meta = ScriptMeta(
            id="test", name="Test", default_output="docs/diagrams/",
        )
        result = resolve_output_target(
            tmp_path, meta, override="custom/output/",
        )
        assert result == tmp_path / "custom/output"
        assert result.is_dir()

    def test_meta_default_output(self, tmp_path):
        """Script's default_output is used when no override."""
        meta = ScriptMeta(
            id="test", name="Test", default_output="docs/diagrams/",
        )
        result = resolve_output_target(tmp_path, meta)
        assert result == tmp_path / "docs/diagrams"
        assert result.is_dir()

    def test_config_default_output(self, tmp_path):
        """Config default is used when neither override nor meta default."""
        meta = ScriptMeta(id="test", name="Test")  # no default_output
        config = ScriptConfig(default_output="scripts/output")
        result = resolve_output_target(tmp_path, meta, config=config)
        assert result == tmp_path / "scripts/output"
        assert result.is_dir()

    def test_fallback_to_script_config_defaults(self, tmp_path):
        """When no override, no meta default, no config → uses ScriptConfig() defaults."""
        meta = ScriptMeta(id="test", name="Test")  # no default_output
        result = resolve_output_target(tmp_path, meta)
        assert result == tmp_path / "scripts/output"
        assert result.is_dir()

    def test_override_beats_meta(self, tmp_path):
        """Override takes priority even when meta has a default."""
        meta = ScriptMeta(
            id="test", name="Test", default_output="docs/diagrams/",
        )
        result = resolve_output_target(
            tmp_path, meta, override="explicit/path/",
        )
        assert result == tmp_path / "explicit/path"

    def test_meta_beats_config(self, tmp_path):
        """Meta default takes priority over config default."""
        meta = ScriptMeta(
            id="test", name="Test", default_output="meta/output/",
        )
        config = ScriptConfig(default_output="config/output")
        result = resolve_output_target(tmp_path, meta, config=config)
        assert result == tmp_path / "meta/output"

    def test_creates_nested_directories(self, tmp_path):
        """Creates nested directory structure if missing."""
        meta = ScriptMeta(id="test", name="Test")
        result = resolve_output_target(
            tmp_path, meta, override="deep/nested/output/path/",
        )
        assert result.is_dir()
        assert result == tmp_path / "deep/nested/output/path"

    def test_absolute_override_path(self, tmp_path):
        """Absolute paths are used as-is."""
        abs_path = tmp_path / "absolute/output"
        meta = ScriptMeta(id="test", name="Test")
        result = resolve_output_target(
            tmp_path, meta, override=str(abs_path),
        )
        assert result == abs_path
        assert result.is_dir()

    def test_existing_directory_not_error(self, tmp_path):
        """Resolving to an already-existing directory works fine."""
        (tmp_path / "existing").mkdir()
        meta = ScriptMeta(id="test", name="Test")
        result = resolve_output_target(
            tmp_path, meta, override="existing",
        )
        assert result == tmp_path / "existing"


class TestInjectOutputEnv:
    """Env var injection tests."""

    def test_all_vars_injected(self, tmp_path):
        """All 6 expected env vars are set."""
        meta = ScriptMeta(
            id="00_class_diagrams",
            name="Class Diagrams",
            output_formats=["mermaid", "json"],
        )
        output_path = tmp_path / "docs/diagrams"
        output_path.mkdir(parents=True)

        result = inject_output_env(
            env={},
            output_path=output_path,
            meta=meta,
            project_root=tmp_path,
            run_id="run_20260307T174925Z_script_a1b2",
            stream_id="script-174925",
        )

        assert result["SCRIPT_OUTPUT_DIR"] == str(output_path.resolve())
        assert result["SCRIPT_OUTPUT_FORMAT"] == "mermaid"
        assert result["SCRIPT_PROJECT_ROOT"] == str(tmp_path.resolve())
        assert result["SCRIPT_ID"] == "00_class_diagrams"
        assert result["SCRIPT_RUN_ID"] == "run_20260307T174925Z_script_a1b2"
        assert result["SCRIPT_STREAM_ID"] == "script-174925"

    def test_default_format_is_markdown(self, tmp_path):
        """When meta has no output_formats, defaults to 'markdown'."""
        meta = ScriptMeta(id="test", name="Test")  # no output_formats
        result = inject_output_env(
            env={},
            output_path=tmp_path,
            meta=meta,
            project_root=tmp_path,
        )
        assert result["SCRIPT_OUTPUT_FORMAT"] == "markdown"

    def test_preserves_existing_env(self, tmp_path):
        """Existing env vars are preserved."""
        meta = ScriptMeta(id="test", name="Test")
        result = inject_output_env(
            env={"PATH": "/usr/bin", "HOME": "/home/user"},
            output_path=tmp_path,
            meta=meta,
            project_root=tmp_path,
        )
        assert result["PATH"] == "/usr/bin"
        assert result["HOME"] == "/home/user"
        assert "SCRIPT_ID" in result

    def test_does_not_mutate_input(self, tmp_path):
        """inject_output_env returns a new dict, not mutating the original."""
        original = {"PATH": "/usr/bin"}
        meta = ScriptMeta(id="test", name="Test")
        result = inject_output_env(
            env=original,
            output_path=tmp_path,
            meta=meta,
            project_root=tmp_path,
        )
        assert "SCRIPT_ID" not in original
        assert "SCRIPT_ID" in result
        assert result is not original

    def test_empty_run_id_and_stream_id(self, tmp_path):
        """Empty run_id and stream_id when not provided."""
        meta = ScriptMeta(id="test", name="Test")
        result = inject_output_env(
            env={},
            output_path=tmp_path,
            meta=meta,
            project_root=tmp_path,
        )
        assert result["SCRIPT_RUN_ID"] == ""
        assert result["SCRIPT_STREAM_ID"] == ""

    def test_first_output_format_used(self, tmp_path):
        """First format in output_formats is used."""
        meta = ScriptMeta(
            id="test", name="Test",
            output_formats=["json", "markdown", "html"],
        )
        result = inject_output_env(
            env={},
            output_path=tmp_path,
            meta=meta,
            project_root=tmp_path,
        )
        assert result["SCRIPT_OUTPUT_FORMAT"] == "json"
