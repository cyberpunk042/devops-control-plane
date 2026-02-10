"""
End-to-end integration tests — full lifecycle through the CLI.

Tests the complete workflow: detect → run → status → health → audit.
Uses Click's CliRunner so everything runs in-process.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest
from click.testing import CliRunner

from src.main import cli


@pytest.fixture()
def project_dir(tmp_path: Path) -> Path:
    """Create a realistic project for e2e testing."""
    # project.yml
    config = tmp_path / "project.yml"
    config.write_text(textwrap.dedent("""\
        name: e2e-test-project
        description: Integration test project
        repository: https://github.com/test/e2e
        modules:
          - name: api
            path: services/api
            domain: backend
            stack: python
          - name: frontend
            path: services/frontend
            domain: frontend
            stack: node
          - name: gateway
            path: infra/gateway
            domain: infrastructure
            stack: docker-compose
        environments:
          - name: dev
            default: true
          - name: staging
          - name: production
    """))

    # Module directories with detection markers
    api_dir = tmp_path / "services" / "api"
    api_dir.mkdir(parents=True)
    (api_dir / "pyproject.toml").write_text('[project]\nname = "api"\n')

    frontend_dir = tmp_path / "services" / "frontend"
    frontend_dir.mkdir(parents=True)
    (frontend_dir / "package.json").write_text('{"name": "frontend"}')

    gw_dir = tmp_path / "infra" / "gateway"
    gw_dir.mkdir(parents=True)
    (gw_dir / "docker-compose.yml").write_text("version: '3'\n")

    # Stacks
    for stack_name, files, caps in [
        ("python", ["pyproject.toml", "requirements.txt"], [
            ("test", "pytest"),
            ("lint", "ruff check ."),
        ]),
        ("node", ["package.json"], [
            ("test", "npm test"),
            ("lint", "npm run lint"),
        ]),
        ("docker-compose", ["docker-compose.yml"], [
            ("test", "docker compose run --rm test"),
            ("lint", "echo no lint"),
        ]),
    ]:
        stack_dir = tmp_path / "stacks" / stack_name
        stack_dir.mkdir(parents=True)

        lines = [
            f"name: {stack_name}",
            "detection:",
            "  files_any_of:",
        ]
        for f in files:
            lines.append(f"    - {f}")
        lines.append("capabilities:")
        for cap_name, cmd in caps:
            lines.append(f"  - name: {cap_name}")
            lines.append(f'    command: "{cmd}"')

        (stack_dir / "stack.yml").write_text("\n".join(lines) + "\n")

    # State directory
    (tmp_path / "state").mkdir(exist_ok=True)

    return tmp_path


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


def invoke(runner: CliRunner, project_dir: Path, args: list[str]) -> ...:
    """Helper: invoke CLI with the project config."""
    return runner.invoke(cli, ["--config", str(project_dir / "project.yml"), *args])


# ── Lifecycle Tests ──────────────────────────────────────────────


class TestLifecycle:
    """Test the full detect → run → status → audit lifecycle."""

    def test_detect_then_status(self, runner: CliRunner, project_dir: Path):
        """Detect modules, then verify status reflects them."""
        # Detect
        result = invoke(runner, project_dir, ["detect"])
        assert result.exit_code == 0
        assert "api" in result.output
        assert "frontend" in result.output

        # Status
        result = invoke(runner, project_dir, ["status"])
        assert result.exit_code == 0
        assert "e2e-test-project" in result.output

    def test_detect_json(self, runner: CliRunner, project_dir: Path):
        """Detect with JSON output."""
        result = invoke(runner, project_dir, ["detect", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["project_name"] == "e2e-test-project"
        assert "detection" in data

    def test_run_mock(self, runner: CliRunner, project_dir: Path):
        """Run test capability in mock mode."""
        result = invoke(runner, project_dir, ["run", "test", "--mock"])
        assert result.exit_code == 0
        assert "3/3" in result.output  # 3 modules

    def test_run_mock_json(self, runner: CliRunner, project_dir: Path):
        """Run with JSON output."""
        result = invoke(runner, project_dir, ["run", "test", "--mock", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["report"]["status"] == "ok"
        assert data["report"]["succeeded"] == 3

    def test_run_dry_run(self, runner: CliRunner, project_dir: Path):
        """Dry run shows plan without executing."""
        result = invoke(runner, project_dir, ["run", "test", "--dry-run"])
        assert result.exit_code == 0
        # Dry run still succeeds (skip receipts, no failures)

    def test_run_with_module_filter(self, runner: CliRunner, project_dir: Path):
        """Run targeting specific module."""
        result = invoke(runner, project_dir, ["run", "test", "--mock", "-m", "api"])
        assert result.exit_code == 0
        assert "1/1" in result.output

    def test_run_then_status(self, runner: CliRunner, project_dir: Path):
        """Run then check status reflects the operation."""
        invoke(runner, project_dir, ["run", "test", "--mock"])

        result = invoke(runner, project_dir, ["status", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["last_operation"]["type"] == "test"
        assert data["last_operation"]["status"] == "ok"

    def test_run_then_audit(self, runner: CliRunner, project_dir: Path):
        """Verify audit log is written after run."""
        invoke(runner, project_dir, ["run", "lint", "--mock"])

        # Check audit file exists
        audit_file = project_dir / "state" / "audit.ndjson"
        assert audit_file.is_file()
        lines = audit_file.read_text().strip().split("\n")
        assert len(lines) >= 1

        entry = json.loads(lines[0])
        assert entry["automation"] == "lint"
        assert entry["status"] == "ok"

    def test_full_lifecycle(self, runner: CliRunner, project_dir: Path):
        """Full lifecycle: detect → run → status → health."""
        # 1. Detect
        r = invoke(runner, project_dir, ["detect"])
        assert r.exit_code == 0

        # 2. Run test
        r = invoke(runner, project_dir, ["run", "test", "--mock"])
        assert r.exit_code == 0

        # 3. Run lint
        r = invoke(runner, project_dir, ["run", "lint", "--mock"])
        assert r.exit_code == 0

        # 4. Status shows last operation
        r = invoke(runner, project_dir, ["status", "--json"])
        assert r.exit_code == 0
        data = json.loads(r.output)
        assert data["last_operation"]["type"] == "lint"

        # 5. Health
        r = invoke(runner, project_dir, ["health", "--json"])
        assert r.exit_code == 0
        health = json.loads(r.output)
        assert health["status"] == "healthy"


# ── Error Handling Tests ─────────────────────────────────────────


class TestErrorHandling:
    """Test that errors are clear and actionable."""

    def test_missing_config(self, runner: CliRunner, tmp_path: Path):
        """Clear error when project.yml is missing."""
        result = runner.invoke(cli, [
            "--config", str(tmp_path / "nonexistent.yml"),
            "status",
        ])
        # Should either fail gracefully or show error
        # (not a stack trace)
        assert "Traceback" not in result.output

    def test_invalid_capability(self, runner: CliRunner, project_dir: Path):
        """Clear error for unknown capability."""
        result = invoke(runner, project_dir, ["run", "deploy", "--mock"])
        assert result.exit_code != 0 or "No actions" in result.output or "error" in result.output.lower()

    def test_config_check_valid(self, runner: CliRunner, project_dir: Path):
        """Config check passes for valid project."""
        result = invoke(runner, project_dir, ["config", "check"])
        assert result.exit_code == 0

    def test_verbose_flag(self, runner: CliRunner, project_dir: Path):
        """Verbose flag accepted and doesn't break."""
        result = invoke(runner, project_dir, ["-v", "status"])
        assert result.exit_code == 0

    def test_quiet_flag(self, runner: CliRunner, project_dir: Path):
        """Quiet flag accepted and doesn't break."""
        result = invoke(runner, project_dir, ["-q", "status"])
        assert result.exit_code == 0

    def test_help_text(self, runner: CliRunner):
        """Main help text is informative."""
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "DevOps Control Plane" in result.output
        assert "status" in result.output
        assert "detect" in result.output
        assert "run" in result.output
        assert "health" in result.output
        assert "web" in result.output

    def test_version(self, runner: CliRunner):
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "controlplane" in result.output


# ── manage.sh Tests ──────────────────────────────────────────────


class TestManageScript:
    """Test the manage.sh wrapper script structure."""

    def test_script_exists(self):
        script = Path(__file__).parent.parent / "manage.sh"
        assert script.is_file(), "manage.sh should exist at project root"

    def test_script_is_executable(self):
        import os
        import stat

        script = Path(__file__).parent.parent / "manage.sh"
        mode = os.stat(script).st_mode
        assert mode & stat.S_IXUSR, "manage.sh should be executable"

    def test_script_has_shebang(self):
        script = Path(__file__).parent.parent / "manage.sh"
        first_line = script.read_text().split("\n")[0]
        assert first_line.startswith("#!/"), "manage.sh should have a shebang"

    def test_script_direct_invocation(self):
        """Verify manage.sh passes args to the CLI."""
        import subprocess

        script = Path(__file__).parent.parent / "manage.sh"
        result = subprocess.run(
            [str(script), "--help"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(script.parent),
        )
        assert result.returncode == 0
        assert "DevOps Control Plane" in result.stdout

    def test_script_status_command(self):
        """Verify manage.sh can run status directly."""
        import subprocess

        script = Path(__file__).parent.parent / "manage.sh"
        result = subprocess.run(
            [str(script), "status"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(script.parent),
        )
        # Status might succeed or fail gracefully depending on project.yml
        # The important thing is no crash
        assert "Traceback" not in result.stderr

    def test_script_no_tty_error(self):
        """Without TTY and no args, script shows helpful error."""
        import subprocess

        script = Path(__file__).parent.parent / "manage.sh"
        result = subprocess.run(
            [str(script)],
            capture_output=True,
            text=True,
            timeout=10,
            stdin=subprocess.DEVNULL,
            cwd=str(script.parent),
        )
        # Should exit with error about no TTY
        assert result.returncode != 0
        assert "TTY" in result.stderr or "direct invocation" in result.stderr
