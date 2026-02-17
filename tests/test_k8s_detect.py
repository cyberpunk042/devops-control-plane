"""
Tests for k8s_detect — offline manifest scanning, Helm, Kustomize.

Pure unit tests: YAML files on disk → parsed dicts.
No kubectl / cluster required.
"""

from pathlib import Path
from unittest.mock import patch

from src.core.services.k8s_detect import (
    k8s_status,
    _collect_yaml_files,
    _detect_helm_charts,
    _detect_kustomize,
)


# ═══════════════════════════════════════════════════════════════════
#  _collect_yaml_files
# ═══════════════════════════════════════════════════════════════════


class TestCollectYamlFiles:
    def test_finds_yaml_in_manifest_dir(self, tmp_path: Path):
        """YAML files in k8s/ directory are collected."""
        k8s = tmp_path / "k8s"
        k8s.mkdir()
        (k8s / "deployment.yaml").write_text("kind: Deployment")
        (k8s / "service.yml").write_text("kind: Service")

        result = _collect_yaml_files(tmp_path, ["k8s"])
        assert len(result) == 2
        names = {f.name for f in result}
        assert "deployment.yaml" in names
        assert "service.yml" in names

    def test_finds_yaml_in_nested_dirs(self, tmp_path: Path):
        """YAML files in subdirectories of manifest dir are collected."""
        k8s = tmp_path / "k8s" / "base"
        k8s.mkdir(parents=True)
        (k8s / "deploy.yaml").write_text("kind: Deployment")

        result = _collect_yaml_files(tmp_path, ["k8s"])
        assert len(result) == 1
        assert result[0].name == "deploy.yaml"

    def test_skips_excluded_dirs(self, tmp_path: Path):
        """YAML files in .git, node_modules, etc. are skipped."""
        k8s = tmp_path / "k8s"
        k8s.mkdir()
        (k8s / "good.yaml").write_text("kind: Deployment")
        git_dir = k8s / ".git"
        git_dir.mkdir()
        (git_dir / "bad.yaml").write_text("kind: Deployment")

        result = _collect_yaml_files(tmp_path, ["k8s"])
        assert len(result) == 1
        assert result[0].name == "good.yaml"

    def test_no_manifest_dirs_scans_root(self, tmp_path: Path):
        """When no manifest dirs found, scans project root."""
        (tmp_path / "app.yaml").write_text("kind: Deployment")

        result = _collect_yaml_files(tmp_path, [])
        assert len(result) == 1
        assert result[0].name == "app.yaml"

    def test_caps_at_50(self, tmp_path: Path):
        """At most 50 YAML files are returned."""
        k8s = tmp_path / "k8s"
        k8s.mkdir()
        for i in range(60):
            (k8s / f"file-{i}.yaml").write_text(f"kind: ConfigMap-{i}")

        result = _collect_yaml_files(tmp_path, ["k8s"])
        assert len(result) == 50

    def test_empty_dir(self, tmp_path: Path):
        """Empty manifest dir → empty list."""
        (tmp_path / "k8s").mkdir()
        result = _collect_yaml_files(tmp_path, ["k8s"])
        assert result == []


# ═══════════════════════════════════════════════════════════════════
#  _detect_helm_charts
# ═══════════════════════════════════════════════════════════════════


class TestDetectHelmCharts:
    def test_detects_chart_yaml(self, tmp_path: Path):
        """Chart.yaml with name + version → detected."""
        chart_dir = tmp_path / "charts" / "myapp"
        chart_dir.mkdir(parents=True)
        (chart_dir / "Chart.yaml").write_text(
            "name: myapp\nversion: 1.2.3\ndescription: My application\n"
        )

        result = _detect_helm_charts(tmp_path)
        assert len(result) == 1
        assert result[0]["name"] == "myapp"
        assert result[0]["version"] == "1.2.3"
        assert result[0]["description"] == "My application"
        assert result[0]["path"] == "charts/myapp"

    def test_multiple_charts(self, tmp_path: Path):
        """Multiple Chart.yaml files → all detected."""
        for name in ("frontend", "backend"):
            d = tmp_path / "charts" / name
            d.mkdir(parents=True)
            (d / "Chart.yaml").write_text(f"name: {name}\nversion: 0.1.0\n")

        result = _detect_helm_charts(tmp_path)
        assert len(result) == 2
        names = {c["name"] for c in result}
        assert names == {"frontend", "backend"}

    def test_skips_excluded_dirs(self, tmp_path: Path):
        """Chart.yaml inside .git → skipped."""
        bad = tmp_path / ".git" / "chart"
        bad.mkdir(parents=True)
        (bad / "Chart.yaml").write_text("name: bad\nversion: 0.0.1\n")

        result = _detect_helm_charts(tmp_path)
        assert result == []

    def test_malformed_chart_yaml(self, tmp_path: Path):
        """Unparseable Chart.yaml → still detected with name=unknown."""
        d = tmp_path / "charts" / "broken"
        d.mkdir(parents=True)
        (d / "Chart.yaml").write_text("{{invalid yaml")

        result = _detect_helm_charts(tmp_path)
        assert len(result) == 1
        assert result[0]["name"] == "unknown"

    def test_no_charts(self, tmp_path: Path):
        """No Chart.yaml anywhere → empty list."""
        (tmp_path / "k8s").mkdir()
        (tmp_path / "k8s" / "deploy.yaml").write_text("kind: Deployment")

        result = _detect_helm_charts(tmp_path)
        assert result == []

    def test_nested_chart_in_deploy_helm(self, tmp_path: Path):
        """Nested chart (deploy/helm/myapp/Chart.yaml) → detected."""
        chart_dir = tmp_path / "deploy" / "helm" / "myapp"
        chart_dir.mkdir(parents=True)
        (chart_dir / "Chart.yaml").write_text(
            "name: myapp\nversion: 2.0.0\ndescription: Nested chart\n"
        )

        result = _detect_helm_charts(tmp_path)
        assert len(result) == 1
        assert result[0]["name"] == "myapp"
        assert result[0]["path"] == "deploy/helm/myapp"


# ═══════════════════════════════════════════════════════════════════
#  _detect_kustomize
# ═══════════════════════════════════════════════════════════════════


class TestDetectKustomize:
    def test_root_kustomization_yaml(self, tmp_path: Path):
        """kustomization.yaml at root → detected."""
        (tmp_path / "kustomization.yaml").write_text("resources:\n- deploy.yaml\n")

        result = _detect_kustomize(tmp_path)
        assert result["exists"] is True
        assert result["path"] == "kustomization.yaml"

    def test_root_kustomization_yml(self, tmp_path: Path):
        """kustomization.yml at root → detected."""
        (tmp_path / "kustomization.yml").write_text("resources:\n- deploy.yaml\n")

        result = _detect_kustomize(tmp_path)
        assert result["exists"] is True
        assert result["path"] == "kustomization.yml"

    def test_root_kustomization_capitalized(self, tmp_path: Path):
        """Kustomization (capitalized, no ext) at root → detected."""
        (tmp_path / "Kustomization").write_text("resources:\n- deploy.yaml\n")

        result = _detect_kustomize(tmp_path)
        assert result["exists"] is True
        assert result["path"] == "Kustomization"

    def test_in_manifest_subdir(self, tmp_path: Path):
        """kustomization.yaml in k8s/ subdirectory → detected."""
        k8s = tmp_path / "k8s"
        k8s.mkdir()
        (k8s / "kustomization.yaml").write_text("resources:\n- deploy.yaml\n")

        result = _detect_kustomize(tmp_path)
        assert result["exists"] is True
        assert result["path"] == "k8s/kustomization.yaml"

    def test_not_found(self, tmp_path: Path):
        """No kustomization file anywhere → exists=False."""
        (tmp_path / "k8s").mkdir()

        result = _detect_kustomize(tmp_path)
        assert result["exists"] is False

    def test_in_kubernetes_subdir(self, tmp_path: Path):
        """kustomization.yaml in kubernetes/ subdirectory → detected."""
        kube = tmp_path / "kubernetes"
        kube.mkdir()
        (kube / "kustomization.yaml").write_text("resources:\n- deploy.yaml\n")

        result = _detect_kustomize(tmp_path)
        assert result["exists"] is True
        assert result["path"] == "kubernetes/kustomization.yaml"


# ═══════════════════════════════════════════════════════════════════
#  k8s_status (integration of the above, mock kubectl)
# ═══════════════════════════════════════════════════════════════════


class TestK8sStatus:
    @patch("src.core.services.k8s_detect._kubectl_available",
           return_value={"available": False, "version": None})
    def test_empty_project(self, _mock_kubectl, tmp_path: Path):
        """Project with no K8s files → has_k8s=False, empty lists."""
        result = k8s_status(tmp_path)
        assert result["has_k8s"] is False
        assert result["manifests"] == []
        assert result["helm_charts"] == []
        assert result["kustomize"]["exists"] is False
        assert result["total_resources"] == 0

    @patch("src.core.services.k8s_detect._kubectl_available",
           return_value={"available": False, "version": None})
    def test_single_deployment(self, _mock_kubectl, tmp_path: Path):
        """k8s/ with a Deployment manifest → detected + parsed."""
        k8s = tmp_path / "k8s"
        k8s.mkdir()
        (k8s / "deploy.yaml").write_text(
            "apiVersion: apps/v1\nkind: Deployment\n"
            "metadata:\n  name: myapp\n  namespace: prod\n"
        )

        result = k8s_status(tmp_path)
        assert result["has_k8s"] is True
        assert result["manifest_dirs"] == ["k8s"]
        assert result["total_resources"] == 1
        assert result["resource_summary"]["Deployment"] == 1
        assert len(result["manifests"]) == 1
        assert result["manifests"][0]["path"] == "k8s/deploy.yaml"
        assert result["manifests"][0]["resources"][0]["kind"] == "Deployment"
        assert result["manifests"][0]["resources"][0]["name"] == "myapp"
        assert result["manifests"][0]["resources"][0]["namespace"] == "prod"

    @patch("src.core.services.k8s_detect._kubectl_available",
           return_value={"available": False, "version": None})
    def test_multi_document_yaml(self, _mock_kubectl, tmp_path: Path):
        """YAML with multiple documents (---) → all resources detected."""
        k8s = tmp_path / "k8s"
        k8s.mkdir()
        (k8s / "all.yaml").write_text(
            "apiVersion: apps/v1\nkind: Deployment\n"
            "metadata:\n  name: web\n"
            "---\n"
            "apiVersion: v1\nkind: Service\n"
            "metadata:\n  name: web-svc\n"
        )

        result = k8s_status(tmp_path)
        assert result["total_resources"] == 2
        assert result["resource_summary"]["Deployment"] == 1
        assert result["resource_summary"]["Service"] == 1

    @patch("src.core.services.k8s_detect._kubectl_available",
           return_value={"available": False, "version": None})
    def test_helm_only_project(self, _mock_kubectl, tmp_path: Path):
        """Project with only Helm chart (no raw manifests) → has_k8s=True."""
        chart_dir = tmp_path / "charts" / "myapp"
        chart_dir.mkdir(parents=True)
        (chart_dir / "Chart.yaml").write_text("name: myapp\nversion: 1.0.0\n")

        result = k8s_status(tmp_path)
        assert result["has_k8s"] is True
        assert len(result["helm_charts"]) == 1
        assert result["manifests"] == []

    @patch("src.core.services.k8s_detect._kubectl_available",
           return_value={"available": False, "version": None})
    def test_kustomize_only_project(self, _mock_kubectl, tmp_path: Path):
        """Project with only kustomization.yaml → has_k8s=True."""
        (tmp_path / "kustomization.yaml").write_text(
            "resources:\n- deployment.yaml\n"
        )

        result = k8s_status(tmp_path)
        assert result["has_k8s"] is True
        assert result["kustomize"]["exists"] is True

    @patch("src.core.services.k8s_detect._kubectl_available",
           return_value={"available": True, "version": "v1.29.0"})
    def test_kubectl_version_passed_through(self, _mock_kubectl, tmp_path: Path):
        """kubectl availability is included in result."""
        result = k8s_status(tmp_path)
        assert result["kubectl"]["available"] is True
        assert result["kubectl"]["version"] == "v1.29.0"

    @patch("src.core.services.k8s_detect._kubectl_available",
           return_value={"available": False, "version": None})
    def test_non_k8s_yaml_ignored(self, _mock_kubectl, tmp_path: Path):
        """YAML without kind/apiVersion → not counted as K8s resource."""
        k8s = tmp_path / "k8s"
        k8s.mkdir()
        (k8s / "config.yaml").write_text("database:\n  host: localhost\n  port: 5432\n")

        result = k8s_status(tmp_path)
        assert result["has_k8s"] is False
        assert result["total_resources"] == 0

    @patch("src.core.services.k8s_detect._kubectl_available",
           return_value={"available": False, "version": None})
    def test_multiple_manifest_dirs(self, _mock_kubectl, tmp_path: Path):
        """Both k8s/ and deploy/ exist → both listed."""
        (tmp_path / "k8s").mkdir()
        (tmp_path / "deploy").mkdir()

        result = k8s_status(tmp_path)
        assert "k8s" in result["manifest_dirs"]
        assert "deploy" in result["manifest_dirs"]

    @patch("src.core.services.k8s_detect._kubectl_available",
           return_value={"available": False, "version": None})
    def test_resource_summary_counts_kinds(self, _mock_kubectl, tmp_path: Path):
        """resource_summary has correct per-kind counts."""
        k8s = tmp_path / "k8s"
        k8s.mkdir()
        (k8s / "all.yaml").write_text(
            "apiVersion: apps/v1\nkind: Deployment\n"
            "metadata:\n  name: a\n"
            "---\n"
            "apiVersion: apps/v1\nkind: Deployment\n"
            "metadata:\n  name: b\n"
            "---\n"
            "apiVersion: v1\nkind: Service\n"
            "metadata:\n  name: svc-a\n"
        )

        result = k8s_status(tmp_path)
        assert result["resource_summary"]["Deployment"] == 2
        assert result["resource_summary"]["Service"] == 1
        assert result["total_resources"] == 3

    @patch("src.core.services.k8s_detect._kubectl_available",
           return_value={"available": False, "version": None})
    def test_manifest_detail_shape(self, _mock_kubectl, tmp_path: Path):
        """Each manifest entry has path, resources list, and count."""
        k8s = tmp_path / "k8s"
        k8s.mkdir()
        (k8s / "deploy.yaml").write_text(
            "apiVersion: apps/v1\nkind: Deployment\n"
            "metadata:\n  name: web\n  namespace: prod\n"
        )

        result = k8s_status(tmp_path)
        m = result["manifests"][0]
        assert "path" in m
        assert "resources" in m
        assert "count" in m
        assert m["count"] == 1
        r = m["resources"][0]
        assert r["kind"] == "Deployment"
        assert r["name"] == "web"
        assert r["namespace"] == "prod"
        assert r["apiVersion"] == "apps/v1"

    @patch("src.core.services.k8s_detect._kubectl_available",
           return_value={"available": False, "version": None})
    def test_manifests_in_manifests_dir(self, _mock_kubectl, tmp_path: Path):
        """Manifests in manifests/ directory → detected."""
        mdir = tmp_path / "manifests"
        mdir.mkdir()
        (mdir / "svc.yaml").write_text(
            "apiVersion: v1\nkind: Service\nmetadata:\n  name: my-svc\n"
        )

        result = k8s_status(tmp_path)
        assert result["has_k8s"] is True
        assert "manifests" in result["manifest_dirs"]
        assert result["total_resources"] == 1

    @patch("src.core.services.k8s_detect._kubectl_available",
           return_value={"available": False, "version": None})
    def test_manifests_in_kubernetes_dir(self, _mock_kubectl, tmp_path: Path):
        """Manifests in kubernetes/ directory → detected."""
        kdir = tmp_path / "kubernetes"
        kdir.mkdir()
        (kdir / "deploy.yaml").write_text(
            "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: app\n"
        )

        result = k8s_status(tmp_path)
        assert result["has_k8s"] is True
        assert "kubernetes" in result["manifest_dirs"]

    @patch("src.core.services.k8s_detect._kubectl_available",
           return_value={"available": False, "version": None})
    def test_files_in_venv_skipped(self, _mock_kubectl, tmp_path: Path):
        """YAML files inside .venv/ → not detected."""
        k8s = tmp_path / "k8s"
        k8s.mkdir()
        venv = k8s / ".venv"
        venv.mkdir()
        (venv / "deploy.yaml").write_text(
            "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: bad\n"
        )

        result = k8s_status(tmp_path)
        assert result["has_k8s"] is False
        assert result["total_resources"] == 0

    @patch("src.core.services.k8s_detect._kubectl_available",
           return_value={"available": False, "version": None})
    def test_files_in_node_modules_skipped(self, _mock_kubectl, tmp_path: Path):
        """YAML files inside node_modules/ → not detected."""
        k8s = tmp_path / "k8s"
        k8s.mkdir()
        nm = k8s / "node_modules"
        nm.mkdir()
        (nm / "chart.yaml").write_text(
            "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: bad\n"
        )

        result = k8s_status(tmp_path)
        assert result["has_k8s"] is False
        assert result["total_resources"] == 0
