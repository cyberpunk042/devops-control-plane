"""
Tests for adapter protocol, registry, mock, and shell adapters.
"""

from pathlib import Path

from src.adapters.base import ExecutionContext
from src.adapters.mock import MockAdapter
from src.adapters.registry import AdapterRegistry
from src.adapters.shell.command import ShellCommandAdapter
from src.adapters.shell.filesystem import FilesystemAdapter
from src.core.models.action import Action, Receipt

# ── Protocol Tests ───────────────────────────────────────────────────


class TestExecutionContext:
    def test_working_dir_with_module(self):
        ctx = ExecutionContext(
            action=Action(id="test", adapter="shell"),
            project_root="/project",
            module_path="src/api",
        )
        assert ctx.working_dir == "/project/src/api"

    def test_working_dir_without_module(self):
        ctx = ExecutionContext(
            action=Action(id="test", adapter="shell"),
            project_root="/project",
        )
        assert ctx.working_dir == "/project"


# ── Mock Adapter Tests ───────────────────────────────────────────────


class TestMockAdapter:
    def test_default_success(self):
        mock = MockAdapter(adapter_name="test-mock")
        ctx = ExecutionContext(action=Action(id="op-1", adapter="test-mock"))
        receipt = mock.execute(ctx)
        assert receipt.ok
        assert mock.call_count == 1

    def test_custom_response(self):
        mock = MockAdapter()
        mock.set_response(
            "op-1",
            Receipt.success(adapter="mock", action_id="op-1", output="custom"),
        )
        ctx = ExecutionContext(action=Action(id="op-1", adapter="mock"))
        receipt = mock.execute(ctx)
        assert receipt.output == "custom"

    def test_set_failure(self):
        mock = MockAdapter()
        mock.set_failure("op-fail", error="Intentional failure")
        ctx = ExecutionContext(action=Action(id="op-fail", adapter="mock"))
        receipt = mock.execute(ctx)
        assert receipt.failed
        assert "Intentional failure" in receipt.error

    def test_call_log(self):
        mock = MockAdapter()
        for i in range(3):
            ctx = ExecutionContext(action=Action(id=f"op-{i}", adapter="mock"))
            mock.execute(ctx)
        assert mock.call_count == 3
        assert mock.call_log[0].action.id == "op-0"

    def test_reset(self):
        mock = MockAdapter()
        mock.set_failure("op-1")
        ctx = ExecutionContext(action=Action(id="op-1", adapter="mock"))
        mock.execute(ctx)
        mock.reset()
        assert mock.call_count == 0

    def test_is_available(self):
        assert MockAdapter(available=True).is_available()
        assert not MockAdapter(available=False).is_available()

    def test_validate(self):
        mock = MockAdapter()
        ctx = ExecutionContext(action=Action(id="test", adapter="mock"))
        valid, msg = mock.validate(ctx)
        assert valid
        assert msg == ""


# ── Registry Tests ──────────────────────────────────────────────────


class TestAdapterRegistry:
    def test_register_and_get(self):
        registry = AdapterRegistry()
        mock = MockAdapter(adapter_name="test")
        registry.register(mock)
        assert registry.get("test") is mock
        assert "test" in registry.list_adapters()

    def test_get_missing(self):
        registry = AdapterRegistry()
        assert registry.get("nonexistent") is None

    def test_unregister(self):
        registry = AdapterRegistry()
        registry.register(MockAdapter(adapter_name="temp"))
        registry.unregister("temp")
        assert registry.get("temp") is None

    def test_adapter_status(self):
        registry = AdapterRegistry()
        registry.register(MockAdapter(adapter_name="available", available=True))
        registry.register(MockAdapter(adapter_name="unavailable", available=False))
        status = registry.adapter_status()
        assert status["available"]["available"] is True
        assert status["unavailable"]["available"] is False

    def test_mock_mode_default(self):
        registry = AdapterRegistry(mock_mode=True)
        action = Action(id="test", adapter="anything")
        receipt = registry.execute_action(action)
        assert receipt.ok
        assert "[mock]" in receipt.output

    def test_mock_mode_with_custom_mock(self):
        registry = AdapterRegistry()
        mock = MockAdapter(adapter_name="custom-mock", default_output="custom mock result")
        registry.set_mock_mode(True, mock_adapter=mock)
        action = Action(id="test", adapter="doesnt-matter")
        receipt = registry.execute_action(action)
        assert receipt.ok
        assert "custom mock result" in receipt.output

    def test_missing_adapter_fails(self):
        registry = AdapterRegistry()
        action = Action(id="test", adapter="nonexistent")
        receipt = registry.execute_action(action)
        assert receipt.failed
        assert "No adapter registered" in receipt.error

    def test_dry_run(self):
        registry = AdapterRegistry()
        registry.register(MockAdapter(adapter_name="test"))
        action = Action(id="test-op", adapter="test")
        receipt = registry.execute_action(action, dry_run=True)
        assert receipt.status == "skipped"
        assert "[dry-run]" in receipt.output

    def test_execute_with_real_adapter(self):
        registry = AdapterRegistry()
        mock = MockAdapter(adapter_name="test")
        registry.register(mock)
        action = Action(id="op-1", adapter="test")
        receipt = registry.execute_action(action)
        assert receipt.ok
        assert mock.call_count == 1

    def test_execute_adds_timing(self):
        registry = AdapterRegistry()
        registry.register(MockAdapter(adapter_name="test"))
        action = Action(id="op-1", adapter="test")
        receipt = registry.execute_action(action)
        assert receipt.duration_ms >= 0


# ── Shell Command Adapter Tests ─────────────────────────────────────


class TestShellCommandAdapter:
    def test_is_available(self):
        adapter = ShellCommandAdapter()
        assert adapter.is_available()
        assert adapter.name == "shell"

    def test_validate_missing_command(self):
        adapter = ShellCommandAdapter()
        ctx = ExecutionContext(
            action=Action(id="test", adapter="shell", params={}),
        )
        valid, msg = adapter.validate(ctx)
        assert not valid
        assert "command" in msg

    def test_validate_bad_cwd(self):
        adapter = ShellCommandAdapter()
        ctx = ExecutionContext(
            action=Action(
                id="test",
                adapter="shell",
                params={"command": "echo hi", "cwd": "/nonexistent/path"},
            ),
        )
        valid, msg = adapter.validate(ctx)
        assert not valid
        assert "does not exist" in msg

    def test_execute_echo(self, tmp_path: Path):
        adapter = ShellCommandAdapter()
        ctx = ExecutionContext(
            action=Action(
                id="echo-test",
                adapter="shell",
                params={"command": "echo hello world", "cwd": str(tmp_path)},
            ),
        )
        receipt = adapter.execute(ctx)
        assert receipt.ok
        assert "hello world" in receipt.output
        assert receipt.metadata["return_code"] == 0

    def test_execute_failure(self, tmp_path: Path):
        adapter = ShellCommandAdapter()
        ctx = ExecutionContext(
            action=Action(
                id="fail-test",
                adapter="shell",
                params={"command": "exit 1", "cwd": str(tmp_path)},
            ),
        )
        receipt = adapter.execute(ctx)
        assert receipt.failed
        assert receipt.metadata["return_code"] == 1

    def test_execute_captures_stderr(self, tmp_path: Path):
        adapter = ShellCommandAdapter()
        ctx = ExecutionContext(
            action=Action(
                id="stderr-test",
                adapter="shell",
                params={"command": "echo error >&2 && exit 1", "cwd": str(tmp_path)},
            ),
        )
        receipt = adapter.execute(ctx)
        assert receipt.failed
        assert "error" in receipt.error


# ── Filesystem Adapter Tests ────────────────────────────────────────


class TestFilesystemAdapter:
    def test_is_available(self):
        adapter = FilesystemAdapter()
        assert adapter.is_available()
        assert adapter.name == "filesystem"

    def test_validate_missing_operation(self):
        adapter = FilesystemAdapter()
        ctx = ExecutionContext(
            action=Action(id="test", adapter="filesystem", params={"path": "/tmp"}),
        )
        valid, _msg = adapter.validate(ctx)
        assert not valid

    def test_validate_invalid_operation(self):
        adapter = FilesystemAdapter()
        ctx = ExecutionContext(
            action=Action(
                id="test",
                adapter="filesystem",
                params={"operation": "delete", "path": "/tmp"},
            ),
        )
        valid, msg = adapter.validate(ctx)
        assert not valid
        assert "Unknown operation" in msg

    def test_exists_true(self, tmp_path: Path):
        (tmp_path / "test.txt").write_text("hello")
        adapter = FilesystemAdapter()
        ctx = ExecutionContext(
            action=Action(
                id="check",
                adapter="filesystem",
                params={"operation": "exists", "path": str(tmp_path / "test.txt")},
            ),
        )
        receipt = adapter.execute(ctx)
        assert receipt.ok
        assert receipt.metadata["exists"] is True

    def test_exists_false(self, tmp_path: Path):
        adapter = FilesystemAdapter()
        ctx = ExecutionContext(
            action=Action(
                id="check",
                adapter="filesystem",
                params={"operation": "exists", "path": str(tmp_path / "missing.txt")},
            ),
        )
        receipt = adapter.execute(ctx)
        assert receipt.ok
        assert receipt.metadata["exists"] is False

    def test_read_file(self, tmp_path: Path):
        (tmp_path / "test.txt").write_text("file content here")
        adapter = FilesystemAdapter()
        ctx = ExecutionContext(
            action=Action(
                id="read",
                adapter="filesystem",
                params={"operation": "read", "path": str(tmp_path / "test.txt")},
            ),
        )
        receipt = adapter.execute(ctx)
        assert receipt.ok
        assert receipt.output == "file content here"

    def test_read_missing_file(self, tmp_path: Path):
        adapter = FilesystemAdapter()
        ctx = ExecutionContext(
            action=Action(
                id="read",
                adapter="filesystem",
                params={"operation": "read", "path": str(tmp_path / "nope.txt")},
            ),
        )
        receipt = adapter.execute(ctx)
        assert receipt.failed

    def test_write_file(self, tmp_path: Path):
        adapter = FilesystemAdapter()
        ctx = ExecutionContext(
            action=Action(
                id="write",
                adapter="filesystem",
                params={
                    "operation": "write",
                    "path": str(tmp_path / "output.txt"),
                    "content": "written content",
                },
            ),
        )
        receipt = adapter.execute(ctx)
        assert receipt.ok
        assert (tmp_path / "output.txt").read_text() == "written content"

    def test_mkdir(self, tmp_path: Path):
        adapter = FilesystemAdapter()
        ctx = ExecutionContext(
            action=Action(
                id="mkdir",
                adapter="filesystem",
                params={"operation": "mkdir", "path": str(tmp_path / "new" / "deep" / "dir")},
            ),
        )
        receipt = adapter.execute(ctx)
        assert receipt.ok
        assert (tmp_path / "new" / "deep" / "dir").is_dir()

    def test_list_directory(self, tmp_path: Path):
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")
        (tmp_path / "subdir").mkdir()
        adapter = FilesystemAdapter()
        ctx = ExecutionContext(
            action=Action(
                id="list",
                adapter="filesystem",
                params={"operation": "list", "path": str(tmp_path)},
            ),
        )
        receipt = adapter.execute(ctx)
        assert receipt.ok
        assert "a.txt" in receipt.output
        assert "b.txt" in receipt.output
        assert receipt.metadata["count"] == 3
