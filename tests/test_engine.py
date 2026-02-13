"""
Tests for engine executor — planning, execution, and audit.
"""

import textwrap
from pathlib import Path

from click.testing import CliRunner

from src.adapters.mock import MockAdapter
from src.adapters.registry import AdapterRegistry
from src.core.engine.executor import (
    ExecutionReport,
    build_actions,
    execute_plan,
    generate_operation_id,
    write_audit_entries,
)
from src.core.models.action import Receipt
from src.core.models.module import Module
from src.core.models.stack import DetectionRule, Stack, StackCapability
from src.core.persistence.audit import AuditWriter
from src.main import cli

# ── Action Planning Tests ────────────────────────────────────────────


class TestBuildActions:
    def _make_fixtures(self) -> tuple[list[Module], dict[str, Stack]]:
        modules = [
            Module(
                name="api",
                path="src/api",
                stack_name="python",
                detected=True,
                detected_stack="python",
            ),
            Module(
                name="web",
                path="src/web",
                stack_name="node",
                detected=True,
                detected_stack="node",
            ),
            Module(
                name="docs",
                path="docs",
                stack_name="markdown",
                detected=True,
            ),
        ]

        stacks = {
            "python": Stack(
                name="python",
                detection=DetectionRule(files_any_of=["pyproject.toml"]),
                capabilities=[
                    StackCapability(name="test", command="pytest"),
                    StackCapability(name="lint", command="ruff check ."),
                ],
            ),
            "node": Stack(
                name="node",
                detection=DetectionRule(files_any_of=["package.json"]),
                capabilities=[
                    StackCapability(name="test", command="npm test"),
                    StackCapability(name="build", command="npm run build"),
                ],
            ),
        }

        return modules, stacks

    def test_build_test_actions(self):
        modules, stacks = self._make_fixtures()
        plan = build_actions("test", modules, stacks, "op-1")
        assert plan.total_actions == 2  # python + node (markdown has no test)
        assert plan.automation == "test"
        assert "api" in plan.module_actions
        assert "web" in plan.module_actions

    def test_build_lint_actions(self):
        modules, stacks = self._make_fixtures()
        plan = build_actions("lint", modules, stacks, "op-2")
        # Only python has lint capability
        assert plan.total_actions == 1
        assert "api" in plan.module_actions

    def test_build_no_matching_capability(self):
        modules, stacks = self._make_fixtures()
        plan = build_actions("deploy", modules, stacks, "op-3")
        assert plan.total_actions == 0

    def test_action_params(self):
        modules, stacks = self._make_fixtures()
        plan = build_actions("test", modules, stacks, "op-4")
        api_action = plan.module_actions["api"][0]
        assert api_action.params["command"] == "pytest"
        assert api_action.params["_stack"] == "python"
        assert api_action.params["_module_path"] == "src/api"


# ── Execution Tests ──────────────────────────────────────────────────


class TestExecutePlan:
    def test_execute_all_succeed(self):
        modules = [
            Module(name="api", path="src/api", detected=True, detected_stack="python"),
        ]
        stacks = {
            "python": Stack(
                name="python",
                capabilities=[StackCapability(name="test", command="pytest")],
            ),
        }
        plan = build_actions("test", modules, stacks, "op-1")

        registry = AdapterRegistry()
        mock = MockAdapter(adapter_name="shell")
        registry.register(mock)

        report = execute_plan(plan, registry, project_root="/project")
        assert report.all_ok
        assert report.succeeded == 1
        assert report.status == "ok"
        assert mock.call_count == 1

    def test_execute_with_failure(self):
        modules = [
            Module(name="api", path="src/api", detected=True, detected_stack="python"),
            Module(name="web", path="src/web", detected=True, detected_stack="python"),
        ]
        stacks = {
            "python": Stack(
                name="python",
                capabilities=[StackCapability(name="test", command="pytest")],
            ),
        }
        plan = build_actions("test", modules, stacks, "op-2")

        registry = AdapterRegistry()
        mock = MockAdapter(adapter_name="shell")
        # Make the web module's test fail
        web_action_id = "op-2:web:test"
        mock.set_failure(web_action_id, error="Tests failed")
        registry.register(mock)

        report = execute_plan(plan, registry)
        assert not report.all_ok
        assert report.status == "partial"
        assert report.succeeded == 1
        assert report.failed == 1

    def test_execute_dry_run(self):
        modules = [
            Module(name="api", path="src/api", detected=True, detected_stack="python"),
        ]
        stacks = {
            "python": Stack(
                name="python",
                capabilities=[StackCapability(name="test", command="pytest")],
            ),
        }
        plan = build_actions("test", modules, stacks, "op-3")

        registry = AdapterRegistry()
        mock = MockAdapter(adapter_name="shell")
        registry.register(mock)

        report = execute_plan(plan, registry, dry_run=True)
        assert report.skipped == 1
        assert mock.call_count == 0  # not actually executed

    def test_execute_mock_mode(self):
        modules = [
            Module(name="api", path="src/api", detected=True, detected_stack="python"),
        ]
        stacks = {
            "python": Stack(
                name="python",
                capabilities=[StackCapability(name="test", command="pytest")],
            ),
        }
        plan = build_actions("test", modules, stacks, "op-4")

        registry = AdapterRegistry(mock_mode=True)
        report = execute_plan(plan, registry)
        assert report.all_ok
        assert "[mock]" in report.receipts[0].output


# ── Report Tests ─────────────────────────────────────────────────────


class TestExecutionReport:
    def test_status_ok(self):
        report = ExecutionReport(
            receipts=[
                Receipt.success(adapter="test", action_id="a1"),
                Receipt.success(adapter="test", action_id="a2"),
            ]
        )
        assert report.status == "ok"

    def test_status_partial(self):
        report = ExecutionReport(
            receipts=[
                Receipt.success(adapter="test", action_id="a1"),
                Receipt.failure(adapter="test", action_id="a2", error="fail"),
            ]
        )
        assert report.status == "partial"

    def test_status_failed(self):
        report = ExecutionReport(
            receipts=[
                Receipt.failure(adapter="test", action_id="a1", error="fail"),
            ]
        )
        assert report.status == "failed"

    def test_to_dict(self):
        report = ExecutionReport(
            operation_id="op-1",
            automation="test",
            receipts=[
                Receipt.success(adapter="test", action_id="a1"),
            ],
        )
        d = report.to_dict()
        assert d["status"] == "ok"
        assert d["total"] == 1
        assert d["succeeded"] == 1


# ── Audit Integration Tests ─────────────────────────────────────────


class TestAuditIntegration:
    def test_write_audit_entries(self, tmp_path: Path):
        report = ExecutionReport(
            operation_id="op-audit-1",
            automation="test",
            receipts=[
                Receipt.success(adapter="shell", action_id="a1", output="passed"),
                Receipt.failure(adapter="shell", action_id="a2", error="failed"),
            ],
        )
        audit_writer = AuditWriter(tmp_path / "audit.ndjson")
        write_audit_entries(report, audit_writer)

        entries = audit_writer.read_all()
        assert len(entries) == 1  # one summary entry per operation
        assert entries[0].operation_id == "op-audit-1"
        assert entries[0].status == "partial"  # mix of ok + failed


# ── Operation ID Tests ───────────────────────────────────────────────


class TestOperationId:
    def test_format(self):
        op_id = generate_operation_id()
        assert op_id.startswith("op-")
        assert len(op_id) > 10

    def test_unique(self):
        ids = {generate_operation_id() for _ in range(100)}
        assert len(ids) == 100  # all unique


# ── CLI Run Command Tests ───────────────────────────────────────────


class TestRunCLI:
    def _setup_project(self, tmp_path: Path) -> Path:
        """Create a project with stacks for CLI testing."""
        config = tmp_path / "project.yml"
        config.write_text(textwrap.dedent("""\
            name: run-test
            modules:
              - name: api
                path: src/api
                stack: python
              - name: web
                path: src/web
                stack: python
        """))

        # Create module dirs with pyproject.toml
        for mod in ["api", "web"]:
            d = tmp_path / "src" / mod
            d.mkdir(parents=True)
            (d / "pyproject.toml").write_text(f'[project]\nname = "{mod}"\n')

        # Stack definition
        stack_dir = tmp_path / "stacks" / "python"
        stack_dir.mkdir(parents=True)
        (stack_dir / "stack.yml").write_text(textwrap.dedent("""\
            name: python
            detection:
              files_any_of:
                - pyproject.toml
            capabilities:
              - name: test
                command: "echo tests passed"
              - name: lint
                command: "echo lint ok"
        """))

        return config

    def test_run_mock(self, tmp_path: Path):
        config = self._setup_project(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            cli, ["--config", str(config), "run", "test", "--mock"]
        )
        assert result.exit_code == 0
        assert "api" in result.output
        assert "web" in result.output
        assert "succeeded" in result.output

    def test_run_dry_run(self, tmp_path: Path):
        config = self._setup_project(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            cli, ["--config", str(config), "run", "test", "--dry-run"]
        )
        assert result.exit_code == 0
        assert "dry-run" in result.output.lower()

    def test_run_json(self, tmp_path: Path):
        import json

        config = self._setup_project(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            cli, ["--config", str(config), "run", "test", "--mock", "--json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["report"]["status"] == "ok"
        assert data["report"]["succeeded"] == 2

    def test_run_specific_module(self, tmp_path: Path):
        config = self._setup_project(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            cli, ["--config", str(config), "run", "test", "--mock", "-m", "api"]
        )
        assert result.exit_code == 0
        assert "api" in result.output
        assert "1/1" in result.output  # only 1 action

    def test_run_unknown_capability(self, tmp_path: Path):
        config = self._setup_project(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            cli, ["--config", str(config), "run", "deploy", "--mock"]
        )
        assert result.exit_code == 1
        assert "No actions" in result.output or "not found" in result.output

    def test_run_saves_state(self, tmp_path: Path):
        config = self._setup_project(tmp_path)
        runner = CliRunner()
        runner.invoke(cli, ["--config", str(config), "run", "test", "--mock"])

        # Check state was saved
        assert (tmp_path / ".state" / "current.json").is_file()

        # Check audit log was written
        assert (tmp_path / ".state" / "audit.ndjson").is_file()

    def test_run_then_status(self, tmp_path: Path):
        """After running, status shows last operation."""
        config = self._setup_project(tmp_path)
        runner = CliRunner()

        # Run first
        runner.invoke(cli, ["--config", str(config), "run", "test", "--mock"])

        # Then check status
        result = runner.invoke(cli, ["--config", str(config), "status"])
        assert result.exit_code == 0
        assert "test" in result.output  # shows last operation type
