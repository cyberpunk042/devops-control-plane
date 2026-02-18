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
        """One charts/app/Chart.yaml → detected with full shape (all 11 keys)."""
        chart_dir = tmp_path / "charts" / "myapp"
        chart_dir.mkdir(parents=True)
        (chart_dir / "Chart.yaml").write_text(textwrap.dedent("""\
            name: myapp
            version: 1.0.0
            description: My application
        """))
        charts = _detect_helm_charts(tmp_path)
        assert len(charts) == 1
        c = charts[0]
        # Full shape assertion — all 11 keys
        assert c["path"] == "charts/myapp"
        assert c["name"] == "myapp"
        assert c["version"] == "1.0.0"
        assert c["description"] == "My application"
        assert c["app_version"] == ""  # not set in Chart.yaml
        assert c["type"] == "application"  # default
        assert c["has_values"] is False  # no values.yaml created
        assert c["has_templates"] is False  # no templates/ dir
        assert c["has_subcharts"] is False  # no charts/ subdir
        assert c["has_lockfile"] is False  # no Chart.lock
        assert c["env_values_files"] == []  # no values-{env}.yaml

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

    # ── NEW 0.4.1 tests ─────────────────────────────────────────

    def test_chart_structure_detection(self, tmp_path: Path):
        """Chart with values.yaml, templates/, charts/, Chart.lock → all flags True."""
        chart_dir = tmp_path / "charts" / "fullchart"
        chart_dir.mkdir(parents=True)
        (chart_dir / "Chart.yaml").write_text(
            "name: fullchart\nversion: 1.0.0\n"
        )
        (chart_dir / "values.yaml").write_text("replicaCount: 1\n")
        (chart_dir / "templates").mkdir()
        (chart_dir / "charts").mkdir()
        (chart_dir / "Chart.lock").write_text("generated: 2026-01-01\n")

        charts = _detect_helm_charts(tmp_path)
        assert len(charts) == 1
        c = charts[0]
        assert c["has_values"] is True
        assert c["has_templates"] is True
        assert c["has_subcharts"] is True
        assert c["has_lockfile"] is True

    def test_env_values_files_detected(self, tmp_path: Path):
        """values-dev.yaml and values-staging.yaml → both in env_values_files."""
        chart_dir = tmp_path / "charts" / "myapp"
        chart_dir.mkdir(parents=True)
        (chart_dir / "Chart.yaml").write_text(
            "name: myapp\nversion: 1.0.0\n"
        )
        (chart_dir / "values-dev.yaml").write_text("replicas: 1\n")
        (chart_dir / "values-staging.yaml").write_text("replicas: 2\n")
        (chart_dir / "values-prod.yml").write_text("replicas: 3\n")  # .yml variant

        charts = _detect_helm_charts(tmp_path)
        assert len(charts) == 1
        env_files = charts[0]["env_values_files"]
        assert isinstance(env_files, list)
        assert "values-dev.yaml" in env_files
        assert "values-staging.yaml" in env_files
        assert "values-prod.yml" in env_files
        # values.yaml (no env suffix) should NOT be in env_values_files
        (chart_dir / "values.yaml").write_text("base: true\n")
        charts2 = _detect_helm_charts(tmp_path)
        assert "values.yaml" not in charts2[0]["env_values_files"]

    def test_app_version_and_type_parsed(self, tmp_path: Path):
        """appVersion and type from Chart.yaml → parsed into dict."""
        chart_dir = tmp_path / "charts" / "myapp"
        chart_dir.mkdir(parents=True)
        (chart_dir / "Chart.yaml").write_text(textwrap.dedent("""\
            name: myapp
            version: 1.0.0
            appVersion: "2.5.0"
            type: library
        """))
        charts = _detect_helm_charts(tmp_path)
        assert len(charts) == 1
        c = charts[0]
        assert c["app_version"] == "2.5.0"
        assert c["type"] == "library"


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

    @patch("subprocess.run")
    @patch("src.core.services.k8s_helm._helm_available", return_value=True)
    def test_json_parse_error(self, mock_avail, mock_run, tmp_path: Path):
        """0.2.2j: Invalid JSON from helm list → graceful error, not crash."""
        mock_run.return_value = MagicMock(returncode=0, stdout="not valid json{{", stderr="")
        r = helm_list(tmp_path)
        assert r["available"] is True
        assert "error" in r
        assert isinstance(r["releases"], list)

    @patch("subprocess.run")
    @patch("src.core.services.k8s_helm._helm_available", return_value=True)
    def test_timeout(self, mock_avail, mock_run, tmp_path: Path):
        """0.2.2j: Subprocess timeout → graceful error."""
        import subprocess as sp
        mock_run.side_effect = sp.TimeoutExpired(cmd="helm", timeout=30)
        r = helm_list(tmp_path)
        assert r["available"] is True
        assert "error" in r
        assert isinstance(r["releases"], list)

    @patch("subprocess.run")
    @patch("src.core.services.k8s_helm._helm_available", return_value=True)
    def test_no_releases_empty_list(self, mock_avail, mock_run, tmp_path: Path):
        """0.2.2j: Empty stdout from helm → empty releases list."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        r = helm_list(tmp_path)
        assert r["available"] is True
        assert r["releases"] == []
        assert "error" not in r

    @patch("subprocess.run")
    @patch("src.core.services.k8s_helm._helm_available", return_value=True)
    def test_releases_shape(self, mock_avail, mock_run, tmp_path: Path):
        """0.2.2j: Release entries have expected fields."""
        releases = [
            {"name": "myapp", "namespace": "default", "revision": "3",
             "status": "deployed", "chart": "myapp-1.2.0", "app_version": "2.0.0"},
        ]
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(releases), stderr="")
        r = helm_list(tmp_path)
        rel = r["releases"][0]
        for key in ("name", "namespace", "revision", "status", "chart", "app_version"):
            assert key in rel, f"Missing key '{key}' in release"


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

    @patch("subprocess.run")
    @patch("src.core.services.k8s_helm._helm_available", return_value=True)
    def test_error_missing_release(self, mock_avail, mock_run, tmp_path: Path):
        """helm_values on missing release → error dict (helm CLI returns non-zero)."""
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="Error: release: not found",
        )
        r = helm_values(tmp_path, "nonexistent")
        assert "error" in r
        assert "ok" not in r



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
#  4. GENERATION — Chart.yaml (0.4.4)
# ═══════════════════════════════════════════════════════════════════


class TestHelmChartGeneration:
    """_generate_helm_chart creates a complete Helm chart directory."""

    def _minimal_data(self, **overrides) -> dict:
        """Minimal wizard state with one service."""
        data = {
            "helm_chart": True,
            "_services": [
                {
                    "name": "api",
                    "image": "myapp:v1.2.3",
                    "port": 8080,
                    "kind": "Deployment",
                    "replicas": 2,
                },
            ],
            "_project_description": "My project",
        }
        data.update(overrides)
        return data

    def test_disabled_no_chart(self, tmp_path: Path):
        """helm_chart=False → no chart generated, empty files list."""
        from src.core.services.k8s_helm_generate import generate_helm_chart

        data = self._minimal_data(helm_chart=False)
        result = generate_helm_chart(data, tmp_path)
        assert result["files"] == []
        assert not (tmp_path / "charts").exists()

    def test_enabled_chart_yaml_created(self, tmp_path: Path):
        """helm_chart=True → Chart.yaml file created."""
        from src.core.services.k8s_helm_generate import generate_helm_chart

        data = self._minimal_data()
        result = generate_helm_chart(data, tmp_path)
        chart_file = tmp_path / "charts" / "api" / "Chart.yaml"
        assert chart_file.is_file(), f"Chart.yaml not found at {chart_file}"
        assert str(chart_file.relative_to(tmp_path)) in [
            f.replace("\\", "/") for f in result["files"]
        ]

    def test_chart_yaml_valid_yaml(self, tmp_path: Path):
        """Chart.yaml is parseable YAML (round-trip)."""
        from src.core.services.k8s_helm_generate import generate_helm_chart

        generate_helm_chart(self._minimal_data(), tmp_path)
        content = yaml.safe_load(
            (tmp_path / "charts" / "api" / "Chart.yaml").read_text()
        )
        assert isinstance(content, dict)

    def test_api_version_v2(self, tmp_path: Path):
        """Chart.yaml has apiVersion: v2 (Helm 3)."""
        from src.core.services.k8s_helm_generate import generate_helm_chart

        generate_helm_chart(self._minimal_data(), tmp_path)
        content = yaml.safe_load(
            (tmp_path / "charts" / "api" / "Chart.yaml").read_text()
        )
        assert content["apiVersion"] == "v2"

    def test_name_from_service(self, tmp_path: Path):
        """name comes from first service name."""
        from src.core.services.k8s_helm_generate import generate_helm_chart

        generate_helm_chart(self._minimal_data(), tmp_path)
        content = yaml.safe_load(
            (tmp_path / "charts" / "api" / "Chart.yaml").read_text()
        )
        assert content["name"] == "api"

    def test_name_fallback_app(self, tmp_path: Path):
        """No services → name defaults to 'app'."""
        from src.core.services.k8s_helm_generate import generate_helm_chart

        data = self._minimal_data(_services=[])
        generate_helm_chart(data, tmp_path)
        content = yaml.safe_load(
            (tmp_path / "charts" / "app" / "Chart.yaml").read_text()
        )
        assert content["name"] == "app"

    def test_default_version(self, tmp_path: Path):
        """version defaults to '0.1.0'."""
        from src.core.services.k8s_helm_generate import generate_helm_chart

        generate_helm_chart(self._minimal_data(), tmp_path)
        content = yaml.safe_load(
            (tmp_path / "charts" / "api" / "Chart.yaml").read_text()
        )
        assert content["version"] == "0.1.0"

    def test_description_from_project(self, tmp_path: Path):
        """description from wizard _project_description."""
        from src.core.services.k8s_helm_generate import generate_helm_chart

        generate_helm_chart(self._minimal_data(), tmp_path)
        content = yaml.safe_load(
            (tmp_path / "charts" / "api" / "Chart.yaml").read_text()
        )
        assert content["description"] == "My project"

    def test_description_fallback(self, tmp_path: Path):
        """No _project_description → default description."""
        from src.core.services.k8s_helm_generate import generate_helm_chart

        data = self._minimal_data()
        del data["_project_description"]
        generate_helm_chart(data, tmp_path)
        content = yaml.safe_load(
            (tmp_path / "charts" / "api" / "Chart.yaml").read_text()
        )
        assert isinstance(content["description"], str)
        assert len(content["description"]) > 0

    def test_app_version_from_image_tag(self, tmp_path: Path):
        """appVersion extracted from first service image tag."""
        from src.core.services.k8s_helm_generate import generate_helm_chart

        generate_helm_chart(self._minimal_data(), tmp_path)
        content = yaml.safe_load(
            (tmp_path / "charts" / "api" / "Chart.yaml").read_text()
        )
        assert content["appVersion"] == "v1.2.3"

    def test_app_version_fallback(self, tmp_path: Path):
        """Image without tag → appVersion defaults to '1.0.0'."""
        from src.core.services.k8s_helm_generate import generate_helm_chart

        data = self._minimal_data()
        data["_services"][0]["image"] = "myapp"  # no tag
        generate_helm_chart(data, tmp_path)
        content = yaml.safe_load(
            (tmp_path / "charts" / "api" / "Chart.yaml").read_text()
        )
        assert content["appVersion"] == "1.0.0"

    def test_type_application(self, tmp_path: Path):
        """type defaults to 'application'."""
        from src.core.services.k8s_helm_generate import generate_helm_chart

        generate_helm_chart(self._minimal_data(), tmp_path)
        content = yaml.safe_load(
            (tmp_path / "charts" / "api" / "Chart.yaml").read_text()
        )
        assert content["type"] == "application"

    def test_output_path(self, tmp_path: Path):
        """Chart.yaml at charts/{name}/Chart.yaml."""
        from src.core.services.k8s_helm_generate import generate_helm_chart

        generate_helm_chart(self._minimal_data(), tmp_path)
        assert (tmp_path / "charts" / "api" / "Chart.yaml").is_file()

    def test_multiple_services_single_chart(self, tmp_path: Path):
        """Multiple services → one chart named after first service."""
        from src.core.services.k8s_helm_generate import generate_helm_chart

        data = self._minimal_data()
        data["_services"].append({
            "name": "worker",
            "image": "worker:latest",
            "port": 9090,
            "kind": "Deployment",
            "replicas": 1,
        })
        result = generate_helm_chart(data, tmp_path)
        # Only one chart directory
        chart_dirs = list((tmp_path / "charts").iterdir())
        assert len(chart_dirs) == 1
        assert chart_dirs[0].name == "api"

    def test_no_services_minimal_chart(self, tmp_path: Path):
        """Empty services list → minimal chart with name 'app'."""
        from src.core.services.k8s_helm_generate import generate_helm_chart

        data = self._minimal_data(_services=[])
        result = generate_helm_chart(data, tmp_path)
        assert (tmp_path / "charts" / "app" / "Chart.yaml").is_file()
        content = yaml.safe_load(
            (tmp_path / "charts" / "app" / "Chart.yaml").read_text()
        )
        assert content["name"] == "app"
        assert content["apiVersion"] == "v2"


# ═══════════════════════════════════════════════════════════════════
#  5. GENERATION — values.yaml (0.4.5)
# ═══════════════════════════════════════════════════════════════════


class TestHelmValuesGeneration:
    """generate_helm_chart produces a values.yaml alongside Chart.yaml."""

    def _data_with_service(self, **svc_overrides) -> dict:
        """Wizard state with one configurable service."""
        svc = {
            "name": "api",
            "image": "myapp:v1.2.3",
            "port": 8080,
            "kind": "Deployment",
            "replicas": 2,
        }
        svc.update(svc_overrides)
        return {
            "helm_chart": True,
            "_services": [svc],
            "_project_description": "Test",
        }

    def test_values_yaml_created(self, tmp_path: Path):
        """values.yaml is written alongside Chart.yaml."""
        from src.core.services.k8s_helm_generate import generate_helm_chart

        generate_helm_chart(self._data_with_service(), tmp_path)
        assert (tmp_path / "charts" / "api" / "values.yaml").is_file()

    def test_values_yaml_valid_yaml(self, tmp_path: Path):
        """values.yaml round-trips through YAML parser."""
        from src.core.services.k8s_helm_generate import generate_helm_chart

        generate_helm_chart(self._data_with_service(), tmp_path)
        content = yaml.safe_load(
            (tmp_path / "charts" / "api" / "values.yaml").read_text()
        )
        assert isinstance(content, dict)

    def test_image_fields(self, tmp_path: Path):
        """image.repository, image.tag, image.pullPolicy present."""
        from src.core.services.k8s_helm_generate import generate_helm_chart

        generate_helm_chart(self._data_with_service(), tmp_path)
        content = yaml.safe_load(
            (tmp_path / "charts" / "api" / "values.yaml").read_text()
        )
        assert content["image"]["repository"] == "myapp"
        assert content["image"]["tag"] == "v1.2.3"
        assert content["image"]["pullPolicy"] == "IfNotPresent"

    def test_replica_count(self, tmp_path: Path):
        """replicaCount from wizard replicas."""
        from src.core.services.k8s_helm_generate import generate_helm_chart

        generate_helm_chart(self._data_with_service(replicas=3), tmp_path)
        content = yaml.safe_load(
            (tmp_path / "charts" / "api" / "values.yaml").read_text()
        )
        assert content["replicaCount"] == 3

    def test_service_type_and_port(self, tmp_path: Path):
        """service.type and service.port from wizard."""
        from src.core.services.k8s_helm_generate import generate_helm_chart

        generate_helm_chart(self._data_with_service(port=3000), tmp_path)
        content = yaml.safe_load(
            (tmp_path / "charts" / "api" / "values.yaml").read_text()
        )
        assert content["service"]["type"] == "ClusterIP"
        assert content["service"]["port"] == 3000

    def test_resources(self, tmp_path: Path):
        """resources.requests and resources.limits present."""
        from src.core.services.k8s_helm_generate import generate_helm_chart

        generate_helm_chart(self._data_with_service(), tmp_path)
        content = yaml.safe_load(
            (tmp_path / "charts" / "api" / "values.yaml").read_text()
        )
        assert "resources" in content
        assert "requests" in content["resources"]
        assert "limits" in content["resources"]

    def test_env_vars_plain(self, tmp_path: Path):
        """Plain env vars appear in values.yaml env list."""
        from src.core.services.k8s_helm_generate import generate_helm_chart

        data = self._data_with_service(
            env=[
                {"key": "LOG_LEVEL", "value": "info", "type": "literal"},
                {"key": "PORT", "value": "8080", "type": "literal"},
            ]
        )
        generate_helm_chart(data, tmp_path)
        content = yaml.safe_load(
            (tmp_path / "charts" / "api" / "values.yaml").read_text()
        )
        assert "env" in content
        env_keys = {e["name"]: e["value"] for e in content["env"]}
        assert env_keys["LOG_LEVEL"] == "info"
        assert env_keys["PORT"] == "8080"

    def test_ingress_section(self, tmp_path: Path):
        """Ingress enabled/host from wizard."""
        from src.core.services.k8s_helm_generate import generate_helm_chart

        data = self._data_with_service()
        data["ingress_host"] = "app.example.com"
        generate_helm_chart(data, tmp_path)
        content = yaml.safe_load(
            (tmp_path / "charts" / "api" / "values.yaml").read_text()
        )
        assert content["ingress"]["enabled"] is True
        assert content["ingress"]["host"] == "app.example.com"

    def test_ingress_disabled_by_default(self, tmp_path: Path):
        """No ingress_host → ingress.enabled=False."""
        from src.core.services.k8s_helm_generate import generate_helm_chart

        generate_helm_chart(self._data_with_service(), tmp_path)
        content = yaml.safe_load(
            (tmp_path / "charts" / "api" / "values.yaml").read_text()
        )
        assert content["ingress"]["enabled"] is False

    def test_no_services_minimal_values(self, tmp_path: Path):
        """Empty services → minimal values file."""
        from src.core.services.k8s_helm_generate import generate_helm_chart

        data = {
            "helm_chart": True,
            "_services": [],
            "_project_description": "Empty",
        }
        generate_helm_chart(data, tmp_path)
        content = yaml.safe_load(
            (tmp_path / "charts" / "app" / "values.yaml").read_text()
        )
        assert isinstance(content, dict)

    def test_secret_env_as_existing_secret(self, tmp_path: Path):
        """Secret env vars → existingSecret reference, not inlined."""
        from src.core.services.k8s_helm_generate import generate_helm_chart

        data = self._data_with_service(
            env=[
                {"key": "DB_PASSWORD", "value": "s3cret", "type": "secret"},
            ]
        )
        generate_helm_chart(data, tmp_path)
        content = yaml.safe_load(
            (tmp_path / "charts" / "api" / "values.yaml").read_text()
        )
        # Secret values must NOT appear as plain text in values.yaml
        values_text = (tmp_path / "charts" / "api" / "values.yaml").read_text()
        assert "s3cret" not in values_text
        # Instead, there should be an existingSecret reference
        assert "existingSecret" in content or "secretRef" in content


# ═══════════════════════════════════════════════════════════════════
#  6. GENERATION — templates/ (0.4.6)
# ═══════════════════════════════════════════════════════════════════


class TestHelmTemplatesGeneration:
    """generate_helm_chart produces templates/ directory with Go templates."""

    def _data(self, **overrides) -> dict:
        """Wizard state with one service."""
        data = {
            "helm_chart": True,
            "_services": [
                {
                    "name": "api",
                    "image": "myapp:v1.2.3",
                    "port": 8080,
                    "kind": "Deployment",
                    "replicas": 2,
                },
            ],
            "_project_description": "Test project",
        }
        data.update(overrides)
        return data

    def _tpl_dir(self, tmp_path: Path) -> Path:
        return tmp_path / "charts" / "api" / "templates"

    def _generate(self, data: dict, tmp_path: Path) -> dict:
        from src.core.services.k8s_helm_generate import generate_helm_chart
        return generate_helm_chart(data, tmp_path)

    # ── directory ────────────────────────────────────────────────────

    def test_templates_dir_created(self, tmp_path: Path):
        """templates/ directory exists after generation."""
        self._generate(self._data(), tmp_path)
        assert self._tpl_dir(tmp_path).is_dir()

    # ── _helpers.tpl ─────────────────────────────────────────────────

    def test_helpers_tpl_created(self, tmp_path: Path):
        """_helpers.tpl exists with chart.fullname and chart.labels defines."""
        self._generate(self._data(), tmp_path)
        helpers = (self._tpl_dir(tmp_path) / "_helpers.tpl").read_text()
        assert 'define "api.fullname"' in helpers
        assert 'define "api.labels"' in helpers
        assert 'define "api.name"' in helpers

    # ── deployment.yaml ──────────────────────────────────────────────

    def test_deployment_created(self, tmp_path: Path):
        """deployment.yaml created for non-Skip service."""
        self._generate(self._data(), tmp_path)
        assert (self._tpl_dir(tmp_path) / "deployment.yaml").is_file()

    def test_deployment_image_ref(self, tmp_path: Path):
        """deployment.yaml references .Values.image.repository and .tag."""
        self._generate(self._data(), tmp_path)
        content = (self._tpl_dir(tmp_path) / "deployment.yaml").read_text()
        assert ".Values.image.repository" in content
        assert ".Values.image.tag" in content

    def test_deployment_resources(self, tmp_path: Path):
        """deployment.yaml includes resource limits from .Values.resources."""
        self._generate(self._data(), tmp_path)
        content = (self._tpl_dir(tmp_path) / "deployment.yaml").read_text()
        assert ".Values.resources" in content

    def test_deployment_env(self, tmp_path: Path):
        """deployment.yaml includes env vars from .Values.env."""
        data = self._data()
        data["_services"][0]["env"] = [
            {"key": "LOG_LEVEL", "value": "info", "type": "literal"},
        ]
        self._generate(data, tmp_path)
        content = (self._tpl_dir(tmp_path) / "deployment.yaml").read_text()
        assert ".Values.env" in content

    # ── service.yaml ─────────────────────────────────────────────────

    def test_service_created(self, tmp_path: Path):
        """service.yaml created for services with ports."""
        self._generate(self._data(), tmp_path)
        assert (self._tpl_dir(tmp_path) / "service.yaml").is_file()

    def test_service_type_and_port(self, tmp_path: Path):
        """service.yaml uses .Values.service.type and .Values.service.port."""
        self._generate(self._data(), tmp_path)
        content = (self._tpl_dir(tmp_path) / "service.yaml").read_text()
        assert ".Values.service.type" in content
        assert ".Values.service.port" in content

    # ── ingress.yaml ────────────────────────────────────────────────

    def test_ingress_conditional(self, tmp_path: Path):
        """ingress.yaml wrapped in {{ if .Values.ingress.enabled }}."""
        self._generate(self._data(), tmp_path)
        content = (self._tpl_dir(tmp_path) / "ingress.yaml").read_text()
        assert ".Values.ingress.enabled" in content

    # ── configmap.yaml ──────────────────────────────────────────────

    def test_configmap_when_env_vars(self, tmp_path: Path):
        """configmap.yaml created when wizard has plain env vars."""
        data = self._data()
        data["_services"][0]["env"] = [
            {"key": "LOG_LEVEL", "value": "info", "type": "literal"},
        ]
        self._generate(data, tmp_path)
        assert (self._tpl_dir(tmp_path) / "configmap.yaml").is_file()

    # ── secret.yaml ─────────────────────────────────────────────────

    def test_secret_when_secret_vars(self, tmp_path: Path):
        """secret.yaml created when wizard has secret env vars."""
        data = self._data()
        data["_services"][0]["env"] = [
            {"key": "DB_PASSWORD", "value": "x", "type": "secret"},
        ]
        self._generate(data, tmp_path)
        assert (self._tpl_dir(tmp_path) / "secret.yaml").is_file()

    # ── NOTES.txt ────────────────────────────────────────────────────

    def test_notes_created(self, tmp_path: Path):
        """NOTES.txt created with post-install instructions."""
        self._generate(self._data(), tmp_path)
        notes = (self._tpl_dir(tmp_path) / "NOTES.txt").read_text()
        assert len(notes) > 0

    # ── naming consistency ──────────────────────────────────────────

    def test_deployment_uses_fullname(self, tmp_path: Path):
        """deployment.yaml uses include 'chart.fullname' for naming."""
        self._generate(self._data(), tmp_path)
        content = (self._tpl_dir(tmp_path) / "deployment.yaml").read_text()
        assert 'include "api.fullname"' in content

    def test_deployment_uses_labels(self, tmp_path: Path):
        """deployment.yaml uses include 'chart.labels' for labels."""
        self._generate(self._data(), tmp_path)
        content = (self._tpl_dir(tmp_path) / "deployment.yaml").read_text()
        assert 'include "api.labels"' in content

    # ── valid Go templates (basic) ──────────────────────────────────

    def test_templates_balanced_braces(self, tmp_path: Path):
        """All template files have balanced {{ }} pairs."""
        self._generate(self._data(), tmp_path)
        for tpl_file in self._tpl_dir(tmp_path).iterdir():
            if tpl_file.suffix in (".yaml", ".tpl", ".txt"):
                content = tpl_file.read_text()
                opens = content.count("{{")
                closes = content.count("}}")
                assert opens == closes, (
                    f"{tpl_file.name}: {opens} opens vs {closes} closes"
                )


# ═══════════════════════════════════════════════════════════════════
#  7. GENERATION — Per-Environment Values (0.4.7)
# ═══════════════════════════════════════════════════════════════════


class TestHelmEnvValuesGeneration:
    """generate_helm_chart produces values-{env}.yaml files per environment."""

    def _data(self, envs: list[str] | None = None) -> dict:
        data = {
            "helm_chart": True,
            "_services": [
                {
                    "name": "api",
                    "image": "myapp:v1.2.3",
                    "port": 8080,
                    "kind": "Deployment",
                    "replicas": 2,
                },
            ],
            "_project_description": "Test",
        }
        if envs is not None:
            data["environments"] = envs
        return data

    def _chart_dir(self, tmp_path: Path) -> Path:
        return tmp_path / "charts" / "api"

    def test_env_values_created(self, tmp_path: Path):
        """Wizard with environments → values-{env}.yaml created."""
        from src.core.services.k8s_helm_generate import generate_helm_chart

        generate_helm_chart(self._data(envs=["dev", "staging", "prod"]), tmp_path)
        for env in ("dev", "staging", "prod"):
            assert (self._chart_dir(tmp_path) / f"values-{env}.yaml").is_file()

    def test_dev_overrides(self, tmp_path: Path):
        """values-dev.yaml has replicaCount: 1."""
        from src.core.services.k8s_helm_generate import generate_helm_chart

        generate_helm_chart(self._data(envs=["dev"]), tmp_path)
        content = yaml.safe_load(
            (self._chart_dir(tmp_path) / "values-dev.yaml").read_text()
        )
        assert content["replicaCount"] == 1

    def test_staging_overrides(self, tmp_path: Path):
        """values-staging.yaml has staging-specific overrides."""
        from src.core.services.k8s_helm_generate import generate_helm_chart

        generate_helm_chart(self._data(envs=["staging"]), tmp_path)
        content = yaml.safe_load(
            (self._chart_dir(tmp_path) / "values-staging.yaml").read_text()
        )
        assert isinstance(content, dict)
        assert "replicaCount" in content

    def test_prod_overrides(self, tmp_path: Path):
        """values-prod.yaml has replicaCount: 3."""
        from src.core.services.k8s_helm_generate import generate_helm_chart

        generate_helm_chart(self._data(envs=["prod"]), tmp_path)
        content = yaml.safe_load(
            (self._chart_dir(tmp_path) / "values-prod.yaml").read_text()
        )
        assert content["replicaCount"] == 3

    def test_no_envs_no_files(self, tmp_path: Path):
        """No environments → no values-{env}.yaml files."""
        from src.core.services.k8s_helm_generate import generate_helm_chart

        generate_helm_chart(self._data(envs=None), tmp_path)
        chart = self._chart_dir(tmp_path)
        env_files = [f for f in chart.iterdir() if f.name.startswith("values-")]
        assert env_files == []

    def test_env_values_valid_yaml(self, tmp_path: Path):
        """Per-env values parse as valid YAML."""
        from src.core.services.k8s_helm_generate import generate_helm_chart

        generate_helm_chart(self._data(envs=["dev"]), tmp_path)
        content = yaml.safe_load(
            (self._chart_dir(tmp_path) / "values-dev.yaml").read_text()
        )
        assert isinstance(content, dict)

    def test_env_values_overrides_only(self, tmp_path: Path):
        """Per-env values contain overrides, not a full copy of values.yaml."""
        from src.core.services.k8s_helm_generate import generate_helm_chart

        generate_helm_chart(self._data(envs=["dev"]), tmp_path)
        base_content = yaml.safe_load(
            (self._chart_dir(tmp_path) / "values.yaml").read_text()
        )
        env_content = yaml.safe_load(
            (self._chart_dir(tmp_path) / "values-dev.yaml").read_text()
        )
        # Env file should have fewer keys than base
        assert len(env_content) < len(base_content)


# ═══════════════════════════════════════════════════════════════════
#  8. GENERATION — .helmignore (0.4.8)
# ═══════════════════════════════════════════════════════════════════


class TestHelmIgnoreGeneration:
    """.helmignore created with standard exclusions."""

    def test_helmignore_created(self, tmp_path: Path):
        """`.helmignore` exists after generation."""
        from src.core.services.k8s_helm_generate import generate_helm_chart

        generate_helm_chart({
            "helm_chart": True,
            "_services": [{"name": "api", "image": "x:v1", "port": 80, "kind": "Deployment"}],
        }, tmp_path)
        assert (tmp_path / "charts" / "api" / ".helmignore").is_file()

    def test_helmignore_patterns(self, tmp_path: Path):
        """`.helmignore` contains standard exclusion patterns."""
        from src.core.services.k8s_helm_generate import generate_helm_chart

        generate_helm_chart({
            "helm_chart": True,
            "_services": [{"name": "api", "image": "x:v1", "port": 80, "kind": "Deployment"}],
        }, tmp_path)
        content = (tmp_path / "charts" / "api" / ".helmignore").read_text()
        for pattern in (".git/", "*.swp", "*.bak", "*.tmp", "__pycache__/", ".venv/"):
            assert pattern in content, f"Missing pattern: {pattern}"


# ═══════════════════════════════════════════════════════════════════
#  9. WIZARD INTEGRATION — Round-trip (0.4.9)
# ═══════════════════════════════════════════════════════════════════


class TestHelmWizardIntegration:
    """Round-trip: generate → detect verifies generated chart is valid."""

    def _wizard_data(self, **overrides) -> dict:
        data = {
            "helm_chart": True,
            "_services": [
                {
                    "name": "api",
                    "image": "myapp:v1.2.3",
                    "port": 8080,
                    "kind": "Deployment",
                    "replicas": 2,
                },
            ],
            "_project_description": "Integration test project",
            "environments": ["dev", "prod"],
        }
        data.update(overrides)
        return data

    def test_generate_then_detect_chart_yaml_valid(self, tmp_path: Path):
        """Generated Chart.yaml is valid YAML (round-trip parse)."""
        from src.core.services.k8s_helm_generate import generate_helm_chart

        generate_helm_chart(self._wizard_data(), tmp_path)
        content = yaml.safe_load(
            (tmp_path / "charts" / "api" / "Chart.yaml").read_text()
        )
        assert isinstance(content, dict)
        assert content["name"] == "api"

    def test_generate_correct_structure(self, tmp_path: Path):
        """Chart dir has Chart.yaml, values.yaml, templates/."""
        from src.core.services.k8s_helm_generate import generate_helm_chart

        generate_helm_chart(self._wizard_data(), tmp_path)
        chart_dir = tmp_path / "charts" / "api"
        assert (chart_dir / "Chart.yaml").is_file()
        assert (chart_dir / "values.yaml").is_file()
        assert (chart_dir / "templates").is_dir()

    def test_disabled_no_chart(self, tmp_path: Path):
        """helm_chart=False → no chart dir."""
        from src.core.services.k8s_helm_generate import generate_helm_chart

        generate_helm_chart(self._wizard_data(helm_chart=False), tmp_path)
        assert not (tmp_path / "charts").exists()

    def test_detect_roundtrip(self, tmp_path: Path):
        """generate → _detect_helm_charts finds the generated chart."""
        from src.core.services.k8s_helm_generate import generate_helm_chart
        from src.core.services.k8s_detect import _detect_helm_charts

        generate_helm_chart(self._wizard_data(), tmp_path)
        charts = _detect_helm_charts(tmp_path)
        assert len(charts) == 1
        chart = charts[0]
        assert chart["name"] == "api"

    def test_detect_version_matches(self, tmp_path: Path):
        """Detected chart version matches generated version."""
        from src.core.services.k8s_helm_generate import generate_helm_chart
        from src.core.services.k8s_detect import _detect_helm_charts

        generate_helm_chart(self._wizard_data(), tmp_path)
        chart = _detect_helm_charts(tmp_path)[0]
        assert chart["version"] == "0.1.0"

    def test_detect_has_values(self, tmp_path: Path):
        """has_values=True after generation."""
        from src.core.services.k8s_helm_generate import generate_helm_chart
        from src.core.services.k8s_detect import _detect_helm_charts

        generate_helm_chart(self._wizard_data(), tmp_path)
        chart = _detect_helm_charts(tmp_path)[0]
        assert chart["has_values"] is True

    def test_detect_has_templates(self, tmp_path: Path):
        """has_templates=True after generation."""
        from src.core.services.k8s_helm_generate import generate_helm_chart
        from src.core.services.k8s_detect import _detect_helm_charts

        generate_helm_chart(self._wizard_data(), tmp_path)
        chart = _detect_helm_charts(tmp_path)[0]
        assert chart["has_templates"] is True

    def test_detect_env_values_files(self, tmp_path: Path):
        """Env-specific values files detected after generation."""
        from src.core.services.k8s_helm_generate import generate_helm_chart
        from src.core.services.k8s_detect import _detect_helm_charts

        generate_helm_chart(self._wizard_data(), tmp_path)
        chart = _detect_helm_charts(tmp_path)[0]
        assert "values-dev.yaml" in chart["env_values_files"]
        assert "values-prod.yaml" in chart["env_values_files"]

    def test_detect_name_matches_service(self, tmp_path: Path):
        """Detected chart name matches wizard service name."""
        from src.core.services.k8s_helm_generate import generate_helm_chart
        from src.core.services.k8s_detect import _detect_helm_charts

        generate_helm_chart(self._wizard_data(), tmp_path)
        chart = _detect_helm_charts(tmp_path)[0]
        assert chart["name"] == "api"


# ═══════════════════════════════════════════════════════════════════
#  10. SKAFFOLD + HELM COMBINED (0.4.10)
# ═══════════════════════════════════════════════════════════════════


class TestSkaffoldHelmCombined:
    """When deploy_strategy=helm + helm_chart=True, both config files generated."""

    def _combined_data(self, **overrides) -> dict:
        data = {
            "skaffold": True,
            "helm_chart": True,
            "deployStrategy": "helm",
            "helmChartPath": "charts/api",
            "_services": [
                {
                    "name": "api",
                    "image": "myapp:v1.2.3",
                    "port": 8080,
                    "kind": "Deployment",
                    "replicas": 2,
                },
            ],
            "_project_description": "Combined test",
        }
        data.update(overrides)
        return data

    def test_both_generated(self, tmp_path: Path):
        """deploy_strategy=helm + helm_chart=True → both configs."""
        from src.core.services.k8s_helm_generate import generate_helm_chart
        from src.core.services.k8s_wizard_generate import _generate_skaffold

        data = self._combined_data()
        helm_result = generate_helm_chart(data, tmp_path)
        assert len(helm_result["files"]) > 0

        skaffold_file = _generate_skaffold(data, [])
        assert skaffold_file is not None
        skaffold_content = yaml.safe_load(skaffold_file["content"])
        assert "helm" in skaffold_content.get("deploy", {})

    def test_skaffold_chart_path(self, tmp_path: Path):
        """Skaffold deploy.helm.releases.chartPath matches chart dir."""
        from src.core.services.k8s_wizard_generate import _generate_skaffold

        data = self._combined_data()
        skaffold_file = _generate_skaffold(data, [])
        skaffold = yaml.safe_load(skaffold_file["content"])
        releases = skaffold["deploy"]["helm"]["releases"]
        assert len(releases) > 0
        assert releases[0]["chartPath"] == "charts/api"

    def test_skaffold_values_files(self, tmp_path: Path):
        """Skaffold helm releases include values files when specified."""
        from src.core.services.k8s_wizard_generate import _generate_skaffold

        data = self._combined_data()
        data["helmValuesFiles"] = ["charts/api/values.yaml", "charts/api/values-dev.yaml"]
        skaffold_file = _generate_skaffold(data, [])
        skaffold = yaml.safe_load(skaffold_file["content"])
        releases = skaffold["deploy"]["helm"]["releases"]
        assert "valuesFiles" in releases[0]
        assert "charts/api/values.yaml" in releases[0]["valuesFiles"]

    def test_helm_deploy_no_helm_chart_flag(self, tmp_path: Path):
        """deploy_strategy=helm without helm_chart=True → Skaffold only."""
        from src.core.services.k8s_helm_generate import generate_helm_chart
        from src.core.services.k8s_wizard_generate import _generate_skaffold

        data = self._combined_data(helm_chart=False)
        helm_result = generate_helm_chart(data, tmp_path)
        assert helm_result["files"] == []

        skaffold_file = _generate_skaffold(data, [])
        assert skaffold_file is not None

    def test_skaffold_detects_helm_strategy(self, tmp_path: Path):
        """Skaffold config uses helm deploy when deployStrategy=helm."""
        from src.core.services.k8s_wizard_generate import _generate_skaffold

        data = self._combined_data()
        skaffold_file = _generate_skaffold(data, [])
        skaffold = yaml.safe_load(skaffold_file["content"])
        assert "helm" in skaffold["deploy"]
        assert "kubectl" not in skaffold.get("deploy", {})


# ═══════════════════════════════════════════════════════════════════
#  11. ERROR CASES & EDGE CASES (0.4.11)
# ═══════════════════════════════════════════════════════════════════


class TestHelmEdgeCases:
    """Generation edge cases: bad input, sanitization, truncation."""

    def test_service_no_image_excluded(self, tmp_path: Path):
        """Service with no image → excluded from values (no crash)."""
        from src.core.services.k8s_helm_generate import generate_helm_chart

        data = {
            "helm_chart": True,
            "_services": [
                {"name": "sidecar", "port": 9090, "kind": "Deployment"},  # no image
            ],
        }
        result = generate_helm_chart(data, tmp_path)
        # Should still produce a chart (with defaults)
        assert (tmp_path / "charts" / "sidecar" / "Chart.yaml").is_file()

    def test_service_skip_excluded(self, tmp_path: Path):
        """Service with kind=Skip → excluded from values.yaml."""
        from src.core.services.k8s_helm_generate import generate_helm_chart

        data = {
            "helm_chart": True,
            "_services": [
                {"name": "skip-me", "image": "x:v1", "kind": "Skip"},
                {"name": "api", "image": "myapp:v1", "port": 80, "kind": "Deployment"},
            ],
        }
        generate_helm_chart(data, tmp_path)
        # Chart named after first non-skip? No — _chart_name uses first service regardless.
        # But values should use the non-skip service.
        content = yaml.safe_load(
            (tmp_path / "charts" / "skip-me" / "values.yaml").read_text()
        )
        # Values image should be from the non-Skip service
        assert content["image"]["repository"] == "myapp"

    def test_empty_wizard_minimal_chart(self, tmp_path: Path):
        """Empty wizard state with helm_chart=True → minimal valid chart."""
        from src.core.services.k8s_helm_generate import generate_helm_chart

        result = generate_helm_chart({"helm_chart": True}, tmp_path)
        assert (tmp_path / "charts" / "app" / "Chart.yaml").is_file()
        content = yaml.safe_load(
            (tmp_path / "charts" / "app" / "Chart.yaml").read_text()
        )
        assert content["name"] == "app"
        assert content["apiVersion"] == "v2"

    def test_special_chars_sanitized(self, tmp_path: Path):
        """Special characters in service name → sanitized for chart name."""
        from src.core.services.k8s_helm_generate import generate_helm_chart

        data = {
            "helm_chart": True,
            "_services": [
                {"name": "my app@v2!", "image": "x:v1", "port": 80, "kind": "Deployment"},
            ],
        }
        result = generate_helm_chart(data, tmp_path)
        # Chart dir should exist (name sanitized — no crash)
        assert len(result["files"]) > 0
        # The chart name in Chart.yaml should be sanitized
        chart_dirs = list((tmp_path / "charts").iterdir())
        assert len(chart_dirs) == 1
        chart_name = chart_dirs[0].name
        # Should not contain special chars
        assert "@" not in chart_name
        assert "!" not in chart_name
        assert " " not in chart_name

    def test_long_name_truncated(self, tmp_path: Path):
        """Very long service name → truncated to 63 chars (DNS label limit)."""
        from src.core.services.k8s_helm_generate import generate_helm_chart

        long_name = "a" * 100
        data = {
            "helm_chart": True,
            "_services": [
                {"name": long_name, "image": "x:v1", "port": 80, "kind": "Deployment"},
            ],
        }
        result = generate_helm_chart(data, tmp_path)
        chart_dirs = list((tmp_path / "charts").iterdir())
        assert len(chart_dirs) == 1
        assert len(chart_dirs[0].name) <= 63
