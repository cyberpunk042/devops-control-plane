"""
Tests for Helm — detection, CLI wrappers, and wizard integration.

Unit tests (offline) cover:
  - Helm chart detection (_detect_helm_charts)
  - CLI availability check (_helm_available)
  - Command construction for install/upgrade/template/values/list
  - Argument assembly (namespace, values-file, --set, dry-run)

Integration tests (marked) would require a live cluster.

Source modules:
  - k8s_detect._detect_helm_charts   (detection)
  - k8s_helm.*                       (CLI wrappers)
  - k8s_wizard_detect.k8s_env_namespaces  (values file detection)
"""

import textwrap
from pathlib import Path
from unittest.mock import patch, MagicMock
import json

import yaml

from src.core.services.k8s_detect import _detect_helm_charts
from src.core.services.k8s_helm import (
    _helm_available,
    helm_list,
    helm_values,
    helm_install,
    helm_upgrade,
    helm_template,
)


# ═══════════════════════════════════════════════════════════════════
#  1. DETECTION — _detect_helm_charts
# ═══════════════════════════════════════════════════════════════════


class TestHelmChartDetection:
    """_detect_helm_charts finds Chart.yaml files recursively."""

    def test_no_charts(self, tmp_path: Path):
        """No Chart.yaml → empty list."""
        assert _detect_helm_charts(tmp_path) == []

    def test_single_chart(self, tmp_path: Path):
        """One charts/app/Chart.yaml → detected."""
        chart_dir = tmp_path / "charts" / "myapp"
        chart_dir.mkdir(parents=True)
        (chart_dir / "Chart.yaml").write_text(textwrap.dedent("""\
            name: myapp
            version: 1.0.0
            description: My application
        """))
        charts = _detect_helm_charts(tmp_path)
        assert len(charts) == 1
        assert charts[0]["name"] == "myapp"
        assert charts[0]["version"] == "1.0.0"

    def test_multiple_charts(self, tmp_path: Path):
        """Multiple Chart.yaml → all detected."""
        for name in ("api", "worker", "frontend"):
            d = tmp_path / "charts" / name
            d.mkdir(parents=True)
            (d / "Chart.yaml").write_text(f"name: {name}\nversion: 0.1.0\n")
        charts = _detect_helm_charts(tmp_path)
        assert len(charts) == 3
        names = {c["name"] for c in charts}
        assert names == {"api", "worker", "frontend"}

    def test_nested_chart(self, tmp_path: Path):
        """Deeply nested Chart.yaml → detected."""
        d = tmp_path / "deploy" / "helm" / "myapp"
        d.mkdir(parents=True)
        (d / "Chart.yaml").write_text("name: myapp\nversion: 2.0.0\n")
        charts = _detect_helm_charts(tmp_path)
        assert len(charts) == 1
        assert "deploy/helm/myapp" in charts[0]["path"]

    def test_skips_vendor_dirs(self, tmp_path: Path):
        """Charts in node_modules, .venv, etc. are skipped."""
        for skip_dir in ("node_modules", ".venv", "__pycache__"):
            d = tmp_path / skip_dir / "chart"
            d.mkdir(parents=True)
            (d / "Chart.yaml").write_text("name: vendor\nversion: 0.0.1\n")
        assert _detect_helm_charts(tmp_path) == []

    def test_chart_path_relative(self, tmp_path: Path):
        """Chart path is relative to project root."""
        d = tmp_path / "charts" / "myapp"
        d.mkdir(parents=True)
        (d / "Chart.yaml").write_text("name: myapp\nversion: 1.0.0\n")
        charts = _detect_helm_charts(tmp_path)
        assert charts[0]["path"] == "charts/myapp"

    def test_chart_missing_name(self, tmp_path: Path):
        """Chart.yaml without name → defaults to 'unknown'."""
        d = tmp_path / "charts" / "x"
        d.mkdir(parents=True)
        (d / "Chart.yaml").write_text("version: 1.0.0\n")
        charts = _detect_helm_charts(tmp_path)
        assert charts[0]["name"] == "unknown"

    def test_chart_missing_version(self, tmp_path: Path):
        """Chart.yaml without version → defaults to '0.0.0'."""
        d = tmp_path / "charts" / "x"
        d.mkdir(parents=True)
        (d / "Chart.yaml").write_text("name: myapp\n")
        charts = _detect_helm_charts(tmp_path)
        assert charts[0]["version"] == "0.0.0"

    def test_chart_description_extracted(self, tmp_path: Path):
        """Description extracted from Chart.yaml."""
        d = tmp_path / "charts" / "x"
        d.mkdir(parents=True)
        (d / "Chart.yaml").write_text("name: myapp\nversion: 1.0.0\ndescription: My app\n")
        assert _detect_helm_charts(tmp_path)[0]["description"] == "My app"

    def test_malformed_chart_yaml(self, tmp_path: Path):
        """Unparseable Chart.yaml → detected with name='unknown'."""
        d = tmp_path / "charts" / "bad"
        d.mkdir(parents=True)
        (d / "Chart.yaml").write_text("{{invalid}}")
        charts = _detect_helm_charts(tmp_path)
        assert len(charts) == 1
        assert charts[0]["name"] == "unknown"

    def test_chart_with_dependencies(self, tmp_path: Path):
        """Chart.yaml with dependencies → chart still detected."""
        d = tmp_path / "charts" / "myapp"
        d.mkdir(parents=True)
        (d / "Chart.yaml").write_text(textwrap.dedent("""\
            name: myapp
            version: 1.0.0
            dependencies:
              - name: redis
                version: 17.0.0
                repository: https://charts.bitnami.com/bitnami
        """))
        charts = _detect_helm_charts(tmp_path)
        assert len(charts) == 1
        assert charts[0]["name"] == "myapp"


# ═══════════════════════════════════════════════════════════════════
#  2. CLI AVAILABILITY
# ═══════════════════════════════════════════════════════════════════


class TestHelmAvailable:
    """_helm_available checks for helm CLI."""

    @patch("shutil.which", return_value="/usr/local/bin/helm")
    def test_available(self, mock_which):
        assert _helm_available() is True

    @patch("shutil.which", return_value=None)
    def test_unavailable(self, mock_which):
        assert _helm_available() is False


# ═══════════════════════════════════════════════════════════════════
#  3. CLI WRAPPERS — command construction (mocked subprocess)
# ═══════════════════════════════════════════════════════════════════


class TestHelmList:
    """helm_list command construction and response parsing."""

    @patch("src.core.services.k8s_helm._helm_available", return_value=False)
    def test_unavailable(self, mock, tmp_path: Path):
        r = helm_list(tmp_path)
        assert r["available"] is False
        assert "error" in r

    @patch("subprocess.run")
    @patch("src.core.services.k8s_helm._helm_available", return_value=True)
    def test_basic_call(self, mock_avail, mock_run, tmp_path: Path):
        mock_run.return_value = MagicMock(returncode=0, stdout="[]", stderr="")
        r = helm_list(tmp_path)
        assert r["available"] is True
        assert r["releases"] == []
        # Verify --all-namespaces used when no namespace
        cmd = mock_run.call_args[0][0]
        assert "--all-namespaces" in cmd

    @patch("subprocess.run")
    @patch("src.core.services.k8s_helm._helm_available", return_value=True)
    def test_with_namespace(self, mock_avail, mock_run, tmp_path: Path):
        mock_run.return_value = MagicMock(returncode=0, stdout="[]", stderr="")
        helm_list(tmp_path, namespace="staging")
        cmd = mock_run.call_args[0][0]
        assert "--namespace" in cmd
        assert "staging" in cmd
        assert "--all-namespaces" not in cmd

    @patch("subprocess.run")
    @patch("src.core.services.k8s_helm._helm_available", return_value=True)
    def test_parses_releases(self, mock_avail, mock_run, tmp_path: Path):
        releases = [{"name": "myapp", "namespace": "default", "status": "deployed"}]
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(releases), stderr="")
        r = helm_list(tmp_path)
        assert len(r["releases"]) == 1
        assert r["releases"][0]["name"] == "myapp"

    @patch("subprocess.run")
    @patch("src.core.services.k8s_helm._helm_available", return_value=True)
    def test_error_returned(self, mock_avail, mock_run, tmp_path: Path):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="connection refused")
        r = helm_list(tmp_path)
        assert "error" in r


class TestHelmValues:
    """helm_values command construction."""

    @patch("src.core.services.k8s_helm._helm_available", return_value=False)
    def test_unavailable(self, mock, tmp_path: Path):
        assert "error" in helm_values(tmp_path, "myapp")

    @patch("subprocess.run")
    @patch("src.core.services.k8s_helm._helm_available", return_value=True)
    def test_basic_call(self, mock_avail, mock_run, tmp_path: Path):
        mock_run.return_value = MagicMock(returncode=0, stdout="image: myapp:v1\n", stderr="")
        r = helm_values(tmp_path, "myapp")
        assert r["ok"] is True
        assert "image" in r["values"]
        cmd = mock_run.call_args[0][0]
        assert "myapp" in cmd
        assert "--output" in cmd

    @patch("subprocess.run")
    @patch("src.core.services.k8s_helm._helm_available", return_value=True)
    def test_with_namespace(self, mock_avail, mock_run, tmp_path: Path):
        mock_run.return_value = MagicMock(returncode=0, stdout="ok\n", stderr="")
        helm_values(tmp_path, "myapp", namespace="prod")
        cmd = mock_run.call_args[0][0]
        assert "--namespace" in cmd
        assert "prod" in cmd


class TestHelmInstall:
    """helm_install command construction and argument assembly."""

    @patch("src.core.services.k8s_helm._helm_available", return_value=False)
    def test_unavailable(self, mock, tmp_path: Path):
        assert "error" in helm_install(tmp_path, "myapp", "./charts/myapp")

    @patch("subprocess.run")
    @patch("src.core.services.k8s_helm._helm_available", return_value=True)
    def test_basic_install(self, mock_avail, mock_run, tmp_path: Path):
        mock_run.return_value = MagicMock(returncode=0, stdout="installed", stderr="")
        r = helm_install(tmp_path, "myapp", "./charts/myapp")
        assert r["ok"] is True
        cmd = mock_run.call_args[0][0]
        assert cmd[:3] == ["helm", "install", "myapp"]
        assert "./charts/myapp" in cmd

    @patch("subprocess.run")
    @patch("src.core.services.k8s_helm._helm_available", return_value=True)
    def test_with_namespace(self, mock_avail, mock_run, tmp_path: Path):
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        helm_install(tmp_path, "myapp", "./charts/myapp", namespace="staging")
        cmd = mock_run.call_args[0][0]
        assert "--namespace" in cmd
        assert "staging" in cmd
        assert "--create-namespace" in cmd

    @patch("subprocess.run")
    @patch("src.core.services.k8s_helm._helm_available", return_value=True)
    def test_with_values_file(self, mock_avail, mock_run, tmp_path: Path):
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        helm_install(tmp_path, "myapp", "./charts/myapp", values_file="values-prod.yaml")
        cmd = mock_run.call_args[0][0]
        assert "--values" in cmd
        assert "values-prod.yaml" in cmd

    @patch("subprocess.run")
    @patch("src.core.services.k8s_helm._helm_available", return_value=True)
    def test_with_set_values(self, mock_avail, mock_run, tmp_path: Path):
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        helm_install(tmp_path, "myapp", "./charts/myapp",
                     set_values={"image.tag": "v2", "replicas": "3"})
        cmd = mock_run.call_args[0][0]
        assert "--set" in cmd
        assert "image.tag=v2" in cmd
        assert "replicas=3" in cmd

    @patch("subprocess.run")
    @patch("src.core.services.k8s_helm._helm_available", return_value=True)
    def test_dry_run(self, mock_avail, mock_run, tmp_path: Path):
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        helm_install(tmp_path, "myapp", "./charts/myapp", dry_run=True)
        assert "--dry-run" in mock_run.call_args[0][0]

    @patch("subprocess.run")
    @patch("src.core.services.k8s_helm._helm_available", return_value=True)
    def test_error_response(self, mock_avail, mock_run, tmp_path: Path):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="chart not found")
        r = helm_install(tmp_path, "myapp", "./bad-chart")
        assert "error" in r
        assert "chart not found" in r["error"]


class TestHelmUpgrade:
    """helm_upgrade command construction."""

    @patch("src.core.services.k8s_helm._helm_available", return_value=False)
    def test_unavailable(self, mock, tmp_path: Path):
        assert "error" in helm_upgrade(tmp_path, "myapp", "./charts/myapp")

    @patch("subprocess.run")
    @patch("src.core.services.k8s_helm._helm_available", return_value=True)
    def test_upgrade_install_flag(self, mock_avail, mock_run, tmp_path: Path):
        """helm upgrade uses --install for idempotent deploys."""
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        helm_upgrade(tmp_path, "myapp", "./charts/myapp")
        cmd = mock_run.call_args[0][0]
        assert "--install" in cmd

    @patch("subprocess.run")
    @patch("src.core.services.k8s_helm._helm_available", return_value=True)
    def test_with_all_options(self, mock_avail, mock_run, tmp_path: Path):
        """Namespace + values + set + dry-run all included."""
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        helm_upgrade(
            tmp_path, "myapp", "./charts/myapp",
            namespace="prod",
            values_file="values-prod.yaml",
            set_values={"image.tag": "v3"},
            dry_run=True,
        )
        cmd = mock_run.call_args[0][0]
        assert "--namespace" in cmd
        assert "prod" in cmd
        assert "--values" in cmd
        assert "values-prod.yaml" in cmd
        assert "--set" in cmd
        assert "image.tag=v3" in cmd
        assert "--dry-run" in cmd

    @patch("subprocess.run")
    @patch("src.core.services.k8s_helm._helm_available", return_value=True)
    def test_error_response(self, mock_avail, mock_run, tmp_path: Path):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="release failed")
        r = helm_upgrade(tmp_path, "myapp", "./charts/myapp")
        assert "error" in r


class TestHelmTemplate:
    """helm_template — offline render without cluster."""

    @patch("src.core.services.k8s_helm._helm_available", return_value=False)
    def test_unavailable(self, mock, tmp_path: Path):
        assert "error" in helm_template(tmp_path, "myapp", "./charts/myapp")

    @patch("subprocess.run")
    @patch("src.core.services.k8s_helm._helm_available", return_value=True)
    def test_renders_yaml(self, mock_avail, mock_run, tmp_path: Path):
        rendered = "apiVersion: v1\nkind: Service\nmetadata:\n  name: myapp\n"
        mock_run.return_value = MagicMock(returncode=0, stdout=rendered, stderr="")
        r = helm_template(tmp_path, "myapp", "./charts/myapp")
        assert r["ok"] is True
        assert "Service" in r["output"]

    @patch("subprocess.run")
    @patch("src.core.services.k8s_helm._helm_available", return_value=True)
    def test_with_namespace(self, mock_avail, mock_run, tmp_path: Path):
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        helm_template(tmp_path, "myapp", "./charts/myapp", namespace="staging")
        cmd = mock_run.call_args[0][0]
        assert "--namespace" in cmd
        assert "staging" in cmd

    @patch("subprocess.run")
    @patch("src.core.services.k8s_helm._helm_available", return_value=True)
    def test_with_values_file(self, mock_avail, mock_run, tmp_path: Path):
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        helm_template(tmp_path, "myapp", "./charts/myapp", values_file="values-dev.yaml")
        cmd = mock_run.call_args[0][0]
        assert "--values" in cmd
        assert "values-dev.yaml" in cmd

    @patch("subprocess.run")
    @patch("src.core.services.k8s_helm._helm_available", return_value=True)
    def test_error_response(self, mock_avail, mock_run, tmp_path: Path):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="template error")
        r = helm_template(tmp_path, "myapp", "./charts/myapp")
        assert "error" in r


# ═══════════════════════════════════════════════════════════════════
#  4. VALUES FILE DETECTION (via k8s_wizard_detect)
# ═══════════════════════════════════════════════════════════════════


class TestHelmValuesDetection:
    """k8s_env_namespaces detects Helm values files for environments."""

    @patch("src.core.services.k8s_wizard_detect.find_project_file")
    @patch("src.core.services.k8s_wizard_detect.load_project")
    def test_values_file_detected(self, mock_load, mock_find, tmp_path: Path):
        """values-{env}.yaml in project root → detected."""
        from src.core.models.project import Project, Environment
        from src.core.services.k8s_wizard_detect import k8s_env_namespaces

        mock_find.return_value = tmp_path / "project.yml"
        mock_load.return_value = Project(
            name="myapp",
            environments=[Environment(name="staging")],
        )
        (tmp_path / "values-staging.yaml").write_text("image: myapp:staging\n")

        r = k8s_env_namespaces(tmp_path)
        env = r["environments"][0]
        assert "values-staging.yaml" in env["values_file"]

    @patch("src.core.services.k8s_wizard_detect.find_project_file")
    @patch("src.core.services.k8s_wizard_detect.load_project")
    def test_values_in_helm_dir(self, mock_load, mock_find, tmp_path: Path):
        """helm/values-{env}.yaml → detected."""
        from src.core.models.project import Project, Environment
        from src.core.services.k8s_wizard_detect import k8s_env_namespaces

        mock_find.return_value = tmp_path / "project.yml"
        mock_load.return_value = Project(
            name="myapp",
            environments=[Environment(name="prod")],
        )
        helm_dir = tmp_path / "helm"
        helm_dir.mkdir()
        (helm_dir / "values-prod.yaml").write_text("replicas: 3\n")

        r = k8s_env_namespaces(tmp_path)
        assert r["environments"][0]["values_file"] != ""

    @patch("src.core.services.k8s_wizard_detect.find_project_file")
    @patch("src.core.services.k8s_wizard_detect.load_project")
    def test_values_in_charts_dir(self, mock_load, mock_find, tmp_path: Path):
        """charts/values-{env}.yaml → detected."""
        from src.core.models.project import Project, Environment
        from src.core.services.k8s_wizard_detect import k8s_env_namespaces

        mock_find.return_value = tmp_path / "project.yml"
        mock_load.return_value = Project(
            name="myapp",
            environments=[Environment(name="dev")],
        )
        charts_dir = tmp_path / "charts"
        charts_dir.mkdir()
        (charts_dir / "values-dev.yaml").write_text("debug: true\n")

        r = k8s_env_namespaces(tmp_path)
        assert r["environments"][0]["values_file"] != ""

    @patch("src.core.services.k8s_wizard_detect.find_project_file")
    @patch("src.core.services.k8s_wizard_detect.load_project")
    def test_dot_format_values(self, mock_load, mock_find, tmp_path: Path):
        """values.{env}.yaml format → detected."""
        from src.core.models.project import Project, Environment
        from src.core.services.k8s_wizard_detect import k8s_env_namespaces

        mock_find.return_value = tmp_path / "project.yml"
        mock_load.return_value = Project(
            name="myapp",
            environments=[Environment(name="staging")],
        )
        (tmp_path / "values.staging.yaml").write_text("image: myapp\n")

        r = k8s_env_namespaces(tmp_path)
        assert r["environments"][0]["values_file"] != ""

    @patch("src.core.services.k8s_wizard_detect.find_project_file")
    @patch("src.core.services.k8s_wizard_detect.load_project")
    def test_no_values_file(self, mock_load, mock_find, tmp_path: Path):
        """No matching values file → empty string."""
        from src.core.models.project import Project, Environment
        from src.core.services.k8s_wizard_detect import k8s_env_namespaces

        mock_find.return_value = tmp_path / "project.yml"
        mock_load.return_value = Project(
            name="myapp",
            environments=[Environment(name="staging")],
        )

        r = k8s_env_namespaces(tmp_path)
        assert r["environments"][0]["values_file"] == ""
