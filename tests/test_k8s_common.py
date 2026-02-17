"""
Tests for k8s_common — shared constants and low-level helpers.

Dedicated unit tests. Every constant and function gets its own test.
No indirect coverage, no integration shortcuts.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.core.services.k8s_common import (
    _SKIP_DIRS,
    _K8S_API_VERSIONS,
    _K8S_KINDS,
    _MANIFEST_DIRS,
    _run_kubectl,
    _kubectl_available,
    _parse_k8s_yaml,
)


# ═══════════════════════════════════════════════════════════════════
#  Constants
# ═══════════════════════════════════════════════════════════════════


class TestSkipDirs:
    """_SKIP_DIRS must exclude all common non-project directories."""

    def test_contains_git(self):
        assert ".git" in _SKIP_DIRS

    def test_contains_venv_variants(self):
        assert ".venv" in _SKIP_DIRS
        assert "venv" in _SKIP_DIRS

    def test_contains_node_modules(self):
        assert "node_modules" in _SKIP_DIRS

    def test_contains_pycache(self):
        assert "__pycache__" in _SKIP_DIRS

    def test_contains_build_artifacts(self):
        assert "dist" in _SKIP_DIRS
        assert "build" in _SKIP_DIRS

    def test_contains_cache_dirs(self):
        assert ".mypy_cache" in _SKIP_DIRS
        assert ".ruff_cache" in _SKIP_DIRS
        assert ".pytest_cache" in _SKIP_DIRS

    def test_contains_tox(self):
        assert ".tox" in _SKIP_DIRS

    def test_contains_eggs(self):
        assert ".eggs" in _SKIP_DIRS

    def test_contains_project_specific(self):
        # Project-specific dirs that should be skipped
        assert ".pages" in _SKIP_DIRS
        assert "htmlcov" in _SKIP_DIRS
        assert ".backup" in _SKIP_DIRS
        assert "state" in _SKIP_DIRS

    def test_is_frozenset(self):
        """Must be immutable — no accidental mutation."""
        assert isinstance(_SKIP_DIRS, frozenset)


class TestK8sApiVersions:
    """_K8S_API_VERSIONS must include all standard K8s API versions."""

    def test_core_v1(self):
        assert "v1" in _K8S_API_VERSIONS

    def test_apps_v1(self):
        assert "apps/v1" in _K8S_API_VERSIONS

    def test_batch_v1(self):
        assert "batch/v1" in _K8S_API_VERSIONS

    def test_networking_v1(self):
        assert "networking.k8s.io/v1" in _K8S_API_VERSIONS

    def test_rbac_v1(self):
        assert "rbac.authorization.k8s.io/v1" in _K8S_API_VERSIONS

    def test_autoscaling_v1(self):
        assert "autoscaling/v1" in _K8S_API_VERSIONS

    def test_autoscaling_v2(self):
        assert "autoscaling/v2" in _K8S_API_VERSIONS

    def test_policy_v1(self):
        assert "policy/v1" in _K8S_API_VERSIONS

    def test_storage_v1(self):
        assert "storage.k8s.io/v1" in _K8S_API_VERSIONS

    def test_admission_v1(self):
        assert "admissionregistration.k8s.io/v1" in _K8S_API_VERSIONS

    def test_is_frozenset(self):
        assert isinstance(_K8S_API_VERSIONS, frozenset)


class TestK8sKinds:
    """_K8S_KINDS must include all standard resource kinds."""

    EXPECTED_KINDS = [
        "Pod", "Deployment", "StatefulSet", "DaemonSet", "ReplicaSet",
        "Job", "CronJob", "Service", "Ingress", "ConfigMap", "Secret",
        "PersistentVolumeClaim", "PersistentVolume", "StorageClass",
        "Namespace", "ServiceAccount", "Role", "ClusterRole",
        "RoleBinding", "ClusterRoleBinding", "HorizontalPodAutoscaler",
        "NetworkPolicy", "ResourceQuota", "LimitRange",
    ]

    @pytest.mark.parametrize("kind", EXPECTED_KINDS)
    def test_contains_kind(self, kind: str):
        assert kind in _K8S_KINDS, f"Missing kind: {kind}"

    def test_is_frozenset(self):
        assert isinstance(_K8S_KINDS, frozenset)

    def test_workload_kinds_present(self):
        """All workload kinds the wizard supports must be present."""
        for kind in ("Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob"):
            assert kind in _K8S_KINDS

    def test_rbac_kinds_present(self):
        """RBAC kinds must be present for cluster security."""
        for kind in ("Role", "ClusterRole", "RoleBinding", "ClusterRoleBinding"):
            assert kind in _K8S_KINDS


class TestManifestDirs:
    """_MANIFEST_DIRS must list all conventional K8s manifest directories."""

    def test_contains_k8s(self):
        assert "k8s" in _MANIFEST_DIRS

    def test_contains_kubernetes(self):
        assert "kubernetes" in _MANIFEST_DIRS

    def test_contains_deploy(self):
        assert "deploy" in _MANIFEST_DIRS

    def test_contains_manifests(self):
        assert "manifests" in _MANIFEST_DIRS

    def test_contains_kube(self):
        assert "kube" in _MANIFEST_DIRS

    def test_contains_charts(self):
        assert "charts" in _MANIFEST_DIRS

    def test_is_list(self):
        """Must be a list (ordered), not a set."""
        assert isinstance(_MANIFEST_DIRS, list)

    def test_k8s_is_first(self):
        """k8s/ is the most conventional — should be first."""
        assert _MANIFEST_DIRS[0] == "k8s"


# ═══════════════════════════════════════════════════════════════════
#  _run_kubectl
# ═══════════════════════════════════════════════════════════════════


class TestRunKubectl:
    """_run_kubectl must invoke subprocess with correct args."""

    @patch("src.core.services.k8s_common.subprocess.run")
    def test_calls_subprocess_with_kubectl_prefix(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=["kubectl", "get", "pods"], returncode=0, stdout="", stderr=""
        )
        result = _run_kubectl("get", "pods")

        mock_run.assert_called_once_with(
            ["kubectl", "get", "pods"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert result.returncode == 0

    @patch("src.core.services.k8s_common.subprocess.run")
    def test_custom_timeout(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=["kubectl", "version"], returncode=0, stdout="", stderr=""
        )
        _run_kubectl("version", timeout=30)

        mock_run.assert_called_once_with(
            ["kubectl", "version"],
            capture_output=True,
            text=True,
            timeout=30,
        )

    @patch("src.core.services.k8s_common.subprocess.run")
    def test_default_timeout_is_15(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=["kubectl", "get", "ns"], returncode=0, stdout="", stderr=""
        )
        _run_kubectl("get", "ns")

        _, kwargs = mock_run.call_args
        assert kwargs["timeout"] == 15

    @patch("src.core.services.k8s_common.subprocess.run")
    def test_returns_completed_process(self, mock_run):
        expected = subprocess.CompletedProcess(
            args=["kubectl", "cluster-info"],
            returncode=1,
            stdout="",
            stderr="error: connection refused",
        )
        mock_run.return_value = expected
        result = _run_kubectl("cluster-info")

        assert result is expected
        assert result.returncode == 1
        assert result.stderr == "error: connection refused"


# ═══════════════════════════════════════════════════════════════════
#  _kubectl_available
# ═══════════════════════════════════════════════════════════════════


class TestKubectlAvailable:
    """_kubectl_available must detect kubectl presence and version."""

    @patch("src.core.services.k8s_common._run_kubectl")
    def test_available_with_version(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=["kubectl", "version", "--client", "--short"],
            returncode=0,
            stdout="Client Version: v1.28.3\n",
            stderr="",
        )
        result = _kubectl_available()

        assert result["available"] is True
        assert result["version"] == "Client Version: v1.28.3"
        mock_run.assert_called_once_with("version", "--client", "--short")

    @patch("src.core.services.k8s_common._run_kubectl")
    def test_not_available_file_not_found(self, mock_run):
        mock_run.side_effect = FileNotFoundError("kubectl not found")
        result = _kubectl_available()

        assert result["available"] is False
        assert result["version"] is None

    @patch("src.core.services.k8s_common._run_kubectl")
    def test_not_available_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="kubectl", timeout=15)
        result = _kubectl_available()

        assert result["available"] is False
        assert result["version"] is None

    @patch("src.core.services.k8s_common._run_kubectl")
    def test_not_available_nonzero_returncode(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=["kubectl", "version", "--client", "--short"],
            returncode=1,
            stdout="",
            stderr="error",
        )
        result = _kubectl_available()

        assert result["available"] is False
        assert result["version"] is None

    def test_return_shape_has_available_and_version_keys(self):
        """Result must always have 'available' and 'version' keys."""
        with patch("src.core.services.k8s_common._run_kubectl") as mock_run:
            mock_run.side_effect = FileNotFoundError()
            result = _kubectl_available()

        assert "available" in result
        assert "version" in result


# ═══════════════════════════════════════════════════════════════════
#  _parse_k8s_yaml
# ═══════════════════════════════════════════════════════════════════


class TestParseK8sYaml:
    """_parse_k8s_yaml must parse YAML and return only K8s resource dicts."""

    def test_single_resource(self, tmp_path: Path):
        """Single Deployment document → 1 resource returned."""
        f = tmp_path / "deploy.yaml"
        f.write_text(
            "apiVersion: apps/v1\n"
            "kind: Deployment\n"
            "metadata:\n"
            "  name: myapp\n"
        )
        result = _parse_k8s_yaml(f)

        assert len(result) == 1
        assert result[0]["kind"] == "Deployment"
        assert result[0]["apiVersion"] == "apps/v1"
        assert result[0]["metadata"]["name"] == "myapp"

    def test_multi_document_yaml(self, tmp_path: Path):
        """Multi-doc YAML (---) → all K8s resources returned."""
        f = tmp_path / "multi.yaml"
        f.write_text(
            "apiVersion: apps/v1\n"
            "kind: Deployment\n"
            "metadata:\n"
            "  name: web\n"
            "---\n"
            "apiVersion: v1\n"
            "kind: Service\n"
            "metadata:\n"
            "  name: web-svc\n"
        )
        result = _parse_k8s_yaml(f)

        assert len(result) == 2
        kinds = {r["kind"] for r in result}
        assert kinds == {"Deployment", "Service"}

    def test_requires_both_kind_and_apiversion(self, tmp_path: Path):
        """Documents with only kind or only apiVersion are excluded."""
        f = tmp_path / "partial.yaml"
        f.write_text(
            "kind: Deployment\n"
            "metadata:\n"
            "  name: no-api\n"
            "---\n"
            "apiVersion: v1\n"
            "metadata:\n"
            "  name: no-kind\n"
            "---\n"
            "apiVersion: apps/v1\n"
            "kind: Deployment\n"
            "metadata:\n"
            "  name: complete\n"
        )
        result = _parse_k8s_yaml(f)

        assert len(result) == 1
        assert result[0]["metadata"]["name"] == "complete"

    def test_skips_non_dict_documents(self, tmp_path: Path):
        """Non-dict YAML documents (strings, lists, None) → skipped."""
        f = tmp_path / "mixed.yaml"
        f.write_text(
            "---\n"
            "just a string\n"
            "---\n"
            "- list\n"
            "- of\n"
            "- items\n"
            "---\n"
            "apiVersion: v1\n"
            "kind: ConfigMap\n"
            "metadata:\n"
            "  name: cfg\n"
            "---\n"
            # null document
        )
        result = _parse_k8s_yaml(f)

        assert len(result) == 1
        assert result[0]["kind"] == "ConfigMap"

    def test_returns_empty_on_import_error(self, tmp_path: Path):
        """When PyYAML is not importable → returns [] without crash."""
        f = tmp_path / "any.yaml"
        f.write_text("apiVersion: v1\nkind: Pod\nmetadata:\n  name: x\n")

        with patch.dict("sys.modules", {"yaml": None}):
            # Force re-import to hit the ImportError branch
            import importlib
            import src.core.services.k8s_common as mod
            importlib.reload(mod)
            try:
                result = mod._parse_k8s_yaml(f)
                assert result == []
            finally:
                # Restore module
                importlib.reload(mod)

    def test_returns_empty_on_os_error(self, tmp_path: Path):
        """Unreadable file → returns [] without crash."""
        f = tmp_path / "missing.yaml"
        # File doesn't exist → OSError on read
        result = _parse_k8s_yaml(f)

        assert result == []

    def test_returns_empty_on_yaml_error(self, tmp_path: Path):
        """Malformed YAML → returns [] without crash."""
        f = tmp_path / "bad.yaml"
        f.write_text("{{{{not yaml at all: [[[")
        result = _parse_k8s_yaml(f)

        assert result == []

    def test_empty_file_returns_empty(self, tmp_path: Path):
        """Empty YAML file → empty list."""
        f = tmp_path / "empty.yaml"
        f.write_text("")
        result = _parse_k8s_yaml(f)

        assert result == []

    def test_non_k8s_yaml_returns_empty(self, tmp_path: Path):
        """YAML with data but no kind/apiVersion → empty list."""
        f = tmp_path / "ci.yaml"
        f.write_text(
            "name: CI Pipeline\n"
            "on:\n"
            "  push:\n"
            "    branches: [main]\n"
        )
        result = _parse_k8s_yaml(f)

        assert result == []
