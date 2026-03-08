"""
Tests for scripts executor — command building, validation, execution.

Covers:
- _build_command: all language mappings, param appending, venv_python config
- _check_tools: available tools, missing tools, skip (none)
- _validate_params: required params, optional params
- execute_script: script not found, missing tools, missing params, success flow
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.core.services.scripts.executor import (
    _build_command,
    _check_tools,
    _validate_params,
    execute_script,
)
from src.core.services.scripts.models import ScriptConfig, ScriptMeta, ScriptParameter


# ── Command Building ────────────────────────────────────────────────


class TestBuildCommand:
    """Command building tests."""

    def test_python_script(self):
        """Python script uses sys.executable."""
        meta = ScriptMeta(
            id="test", name="Test", language="python",
            path="/project/scripts/test.py",
        )
        cmd = _build_command(meta, {})
        assert cmd == [sys.executable, "/project/scripts/test.py"]

    def test_bash_script(self):
        """Bash script uses 'bash' interpreter."""
        meta = ScriptMeta(
            id="test", name="Test", language="bash",
            path="/project/scripts/test.sh",
        )
        cmd = _build_command(meta, {})
        assert cmd == ["bash", "/project/scripts/test.sh"]

    def test_powershell_script(self):
        """PowerShell script uses 'pwsh -File'."""
        meta = ScriptMeta(
            id="test", name="Test", language="powershell",
            path="/project/scripts/test.ps1",
        )
        cmd = _build_command(meta, {})
        assert cmd == ["pwsh", "-File", "/project/scripts/test.ps1"]

    def test_params_appended_as_flags(self):
        """Parameters are appended as --key value pairs."""
        meta = ScriptMeta(
            id="test", name="Test", language="python",
            path="/project/scripts/test.py",
        )
        params = {"output": "docs/diagrams/", "scope": "core.services"}
        cmd = _build_command(meta, params)
        assert cmd[0] == sys.executable
        assert cmd[1] == "/project/scripts/test.py"
        assert "--output" in cmd
        assert "docs/diagrams/" in cmd
        assert "--scope" in cmd
        assert "core.services" in cmd

    def test_param_underscores_to_dashes(self):
        """Parameter underscores are converted to dashes for CLI."""
        meta = ScriptMeta(
            id="test", name="Test", language="python",
            path="/project/scripts/test.py",
        )
        params = {"dry_run": "true"}
        cmd = _build_command(meta, params)
        assert "--dry-run" in cmd

    def test_powershell_param_format(self):
        """PowerShell uses -param format instead of --param."""
        meta = ScriptMeta(
            id="test", name="Test", language="powershell",
            path="/project/scripts/test.ps1",
        )
        params = {"scope": "audit"}
        cmd = _build_command(meta, params)
        assert "-scope" in cmd
        assert "--scope" not in cmd

    def test_custom_venv_python(self):
        """config.execution_venv_python overrides sys.executable."""
        meta = ScriptMeta(
            id="test", name="Test", language="python",
            path="/project/scripts/test.py",
        )
        config = ScriptConfig(execution_venv_python="/opt/python/bin/python3")
        cmd = _build_command(meta, {}, config)
        assert cmd[0] == "/opt/python/bin/python3"

    def test_auto_venv_python(self):
        """config.execution_venv_python='auto' uses sys.executable."""
        meta = ScriptMeta(
            id="test", name="Test", language="python",
            path="/project/scripts/test.py",
        )
        config = ScriptConfig(execution_venv_python="auto")
        cmd = _build_command(meta, {}, config)
        assert cmd[0] == sys.executable

    def test_executable_script(self):
        """Executable script uses script path directly."""
        meta = ScriptMeta(
            id="test", name="Test", language="executable",
            path="/project/scripts/run_check",
        )
        cmd = _build_command(meta, {})
        assert cmd == ["/project/scripts/run_check"]

    def test_unknown_language_fallback(self):
        """Unknown language falls back to python."""
        meta = ScriptMeta(
            id="test", name="Test", language="ruby",
            path="/project/scripts/test.rb",
        )
        cmd = _build_command(meta, {})
        assert cmd[0] == sys.executable
        assert cmd[1] == "/project/scripts/test.rb"


# ── Tool Checking ───────────────────────────────────────────────────


class TestCheckTools:
    """Tool availability tests."""

    def test_no_tools_required(self):
        """No requires_tools → all ok."""
        meta = ScriptMeta(id="test", name="Test")
        ok, missing = _check_tools(meta)
        assert ok is True
        assert missing == []

    def test_python_always_available(self):
        """python and python3 are always considered available."""
        meta = ScriptMeta(id="test", name="Test", requires_tools=["python", "python3"])
        ok, missing = _check_tools(meta)
        assert ok is True
        assert missing == []

    def test_bash_available(self):
        """bash is available on Linux."""
        meta = ScriptMeta(id="test", name="Test", requires_tools=["bash"])
        ok, missing = _check_tools(meta)
        # bash should be available on this system
        assert ok is True

    def test_missing_tool(self):
        """A tool that doesn't exist is reported as missing."""
        meta = ScriptMeta(
            id="test", name="Test",
            requires_tools=["nonexistent_tool_abc123"],
        )
        ok, missing = _check_tools(meta)
        assert ok is False
        assert "nonexistent_tool_abc123" in missing

    def test_none_marker_skipped(self):
        """(none) marker is skipped."""
        meta = ScriptMeta(id="test", name="Test", requires_tools=["(none)"])
        ok, missing = _check_tools(meta)
        assert ok is True
        assert missing == []

    def test_empty_string_tool_skipped(self):
        """Empty string in requires_tools is skipped."""
        meta = ScriptMeta(id="test", name="Test", requires_tools=["", " "])
        ok, missing = _check_tools(meta)
        assert ok is True
        assert missing == []


# ── Parameter Validation ────────────────────────────────────────────


class TestValidateParams:
    """Parameter validation tests."""

    def test_no_params_required(self):
        """No parameters → all ok."""
        meta = ScriptMeta(id="test", name="Test")
        ok, missing = _validate_params(meta, {})
        assert ok is True

    def test_required_param_provided(self):
        """Required param is provided → ok."""
        meta = ScriptMeta(
            id="test", name="Test",
            parameters=[ScriptParameter(name="scope", required=True)],
        )
        ok, missing = _validate_params(meta, {"scope": "core"})
        assert ok is True

    def test_required_param_missing(self):
        """Required param is missing → not ok."""
        meta = ScriptMeta(
            id="test", name="Test",
            parameters=[ScriptParameter(name="scope", required=True)],
        )
        ok, missing = _validate_params(meta, {})
        assert ok is False
        assert "scope" in missing

    def test_optional_param_not_required(self):
        """Optional param not provided → ok."""
        meta = ScriptMeta(
            id="test", name="Test",
            parameters=[ScriptParameter(name="scope", required=False, default="all")],
        )
        ok, missing = _validate_params(meta, {})
        assert ok is True

    def test_mixed_params(self):
        """Mix of required and optional params."""
        meta = ScriptMeta(
            id="test", name="Test",
            parameters=[
                ScriptParameter(name="output", required=True),
                ScriptParameter(name="scope", required=False, default="all"),
                ScriptParameter(name="format", required=True),
            ],
        )
        # Only providing output, missing format
        ok, missing = _validate_params(meta, {"output": "docs/"})
        assert ok is False
        assert "format" in missing
        assert "output" not in missing
        assert "scope" not in missing


# ── Execute Script ──────────────────────────────────────────────────


class TestExecuteScript:
    """Script execution integration tests (mocked subprocess)."""

    def test_script_not_found(self, tmp_path):
        """Script not in registry → error result."""
        with patch("src.core.services.scripts.executor.get_script", return_value=None):
            result = execute_script(tmp_path, "nonexistent")
        assert result["ok"] is False
        assert "not found" in result["error"]
        assert result["run_id"] == ""

    def test_missing_tools_error(self, tmp_path):
        """Missing tools → error result before execution."""
        meta = ScriptMeta(
            id="test", name="Test", language="python",
            path="/test.py",
            requires_tools=["nonexistent_tool_xyz999"],
        )
        with patch("src.core.services.scripts.executor.get_script", return_value=meta):
            result = execute_script(tmp_path, "test")
        assert result["ok"] is False
        assert "Missing required tools" in result["error"]

    def test_missing_required_params_error(self, tmp_path):
        """Missing required params → error result before execution."""
        meta = ScriptMeta(
            id="test", name="Test", language="python",
            path="/test.py",
            parameters=[ScriptParameter(name="scope", required=True)],
        )
        with patch("src.core.services.scripts.executor.get_script", return_value=meta):
            result = execute_script(tmp_path, "test")
        assert result["ok"] is False
        assert "Missing required parameters" in result["error"]
        assert "scope" in result["error"]

    def test_successful_execution(self, tmp_path):
        """Successful execution returns proper result dict."""
        meta = ScriptMeta(
            id="test_script", name="Test Script", language="python",
            path=str(tmp_path / "test.py"),
        )

        # Create a mock stream_run result
        mock_stream_result = {
            "ok": True,
            "exit_code": 0,
            "stream_id": "script-123-abc",
            "lines": ["line1", "line2"],
        }

        # Mock the tracked_run context manager
        class MockContext:
            def __init__(self, *args, **kwargs):
                self.run_bag = {
                    "run_id": "run_test_123",
                    "type": "script",
                    "subtype": "script:test_script",
                    "summary": "Test Script",
                    "status": "ok",
                    "started_at": "2026-03-07T00:00:00Z",
                }

            def __enter__(self):
                return self.run_bag

            def __exit__(self, *args):
                self.run_bag["duration_ms"] = 42
                return False

        with (
            patch("src.core.services.scripts.executor.get_script", return_value=meta),
            patch("src.core.services.scripts.executor.load_scripts_config",
                  return_value=ScriptConfig(template_source="never")),
            patch("src.core.services.stream_subprocess.stream_run",
                  return_value=mock_stream_result),
            patch("src.core.services.run_tracker.tracked_run",
                  side_effect=lambda *a, **k: MockContext()),
            patch("src.core.services.stream_subprocess.make_stream_id",
                  return_value="script-123-abc"),
        ):
            result = execute_script(tmp_path, "test_script")

        assert result["ok"] is True
        assert result["run_id"] == "run_test_123"
        assert result["stream_id"] == "script-123-abc"
        assert result["exit_code"] == 0
        assert result["lines"] == ["line1", "line2"]
        assert result["error"] is None

    def test_failed_execution(self, tmp_path):
        """Failed execution returns error details."""
        meta = ScriptMeta(
            id="test_script", name="Test Script", language="python",
            path=str(tmp_path / "test.py"),
        )

        mock_stream_result = {
            "ok": False,
            "exit_code": 1,
            "stream_id": "script-456-def",
            "lines": ["error: something went wrong"],
            "error": "error: something went wrong",
        }

        class MockContext:
            def __init__(self, *args, **kwargs):
                self.run_bag = {
                    "run_id": "run_test_456",
                    "type": "script",
                    "subtype": "script:test_script",
                    "summary": "Test Script",
                    "status": "ok",
                    "started_at": "2026-03-07T00:00:00Z",
                }

            def __enter__(self):
                return self.run_bag

            def __exit__(self, *args):
                self.run_bag["duration_ms"] = 100
                return False

        with (
            patch("src.core.services.scripts.executor.get_script", return_value=meta),
            patch("src.core.services.scripts.executor.load_scripts_config",
                  return_value=ScriptConfig(template_source="never")),
            patch("src.core.services.stream_subprocess.stream_run",
                  return_value=mock_stream_result),
            patch("src.core.services.run_tracker.tracked_run",
                  side_effect=lambda *a, **k: MockContext()),
            patch("src.core.services.stream_subprocess.make_stream_id",
                  return_value="script-456-def"),
        ):
            result = execute_script(tmp_path, "test_script")

        assert result["ok"] is False
        assert result["exit_code"] == 1
        assert result["error"] == "error: something went wrong"
