"""
Smoke tests — verify the bootstrap is healthy.

These tests ensure the basic scaffolding works:
- Package imports successfully
- CLI entrypoint responds
- Version is set
"""

from click.testing import CliRunner

from src import __version__
from src.main import cli


class TestBootstrap:
    """Verify the project bootstrap is healthy."""

    def test_version_is_set(self):
        """Version string should be defined and non-empty."""
        assert __version__
        assert isinstance(__version__, str)

    def test_cli_help(self):
        """CLI --help should exit cleanly with usage info."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "DevOps Control Plane" in result.output

    def test_cli_version(self):
        """CLI --version should print the version."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert __version__ in result.output

    def test_status_command_exists(self):
        """Status command should be registered and callable."""
        runner = CliRunner()
        result = runner.invoke(cli, ["status"])
        assert result.exit_code == 0

    def test_config_check_command_exists(self):
        """Config check command should be registered and callable."""
        runner = CliRunner()
        result = runner.invoke(cli, ["config", "check"])
        assert result.exit_code == 0

    def test_core_package_imports(self):
        """Core sub-packages should be importable."""
        import src.core
        import src.core.config
        import src.core.engine
        import src.core.models
        import src.core.observability
        import src.core.persistence
        import src.core.reliability
        import src.core.security
        import src.core.services
        import src.core.use_cases
        assert src.core is not None

    def test_adapter_packages_import(self):
        """Adapter sub-packages should be importable."""
        import src.adapters
        import src.adapters.containers
        import src.adapters.languages
        import src.adapters.shell
        import src.adapters.vcs
        assert src.adapters is not None

    def test_ui_packages_import(self):
        """UI sub-packages should be importable."""
        import src.ui
        import src.ui.cli
        import src.ui.web
        assert src.ui is not None
