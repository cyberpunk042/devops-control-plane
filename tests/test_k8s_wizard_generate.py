"""
Tests for k8s_wizard_generate — resources → YAML manifest files.

These are pure unit tests: resource list in → {ok, files} with YAML content.
No subprocess, no network.
"""

from pathlib import Path

import yaml

from src.core.services.k8s_wizard_generate import (
    generate_k8s_wizard,
    _generate_skaffold,
)


# ═══════════════════════════════════════════════════════════════════
#  generate_k8s_wizard
# ═══════════════════════════════════════════════════════════════════


class TestGenerateK8sWizard:
    def test_deployment_yaml(self, tmp_path: Path):
        """Deployment resource → valid YAML with correct structure."""
        result = generate_k8s_wizard(tmp_path, [
            {
                "kind": "Deployment",
                "name": "api",
                "namespace": "default",
                "output_dir": "k8s",
                "spec": {
                    "image": "myapp:1.0",
                    "port": 8080,
                    "replicas": 3,
                },
            },
        ])
        assert result["ok"] is True
        assert len(result["files"]) == 1
        manifest = yaml.safe_load(result["files"][0]["content"])
        assert manifest["apiVersion"] == "apps/v1"
        assert manifest["kind"] == "Deployment"
        assert manifest["metadata"]["name"] == "api"
        assert manifest["spec"]["replicas"] == 3
        assert manifest["spec"]["selector"]["matchLabels"]["app"] == "api"

    def test_service_yaml(self, tmp_path: Path):
        """Service resource → correct port, selector, type."""
        result = generate_k8s_wizard(tmp_path, [
            {
                "kind": "Service",
                "name": "api",
                "namespace": "default",
                "output_dir": "k8s",
                "spec": {
                    "port": 80,
                    "target_port": 8080,
                    "type": "ClusterIP",
                    "selector": "api",
                },
            },
        ])
        assert result["ok"] is True
        manifest = yaml.safe_load(result["files"][0]["content"])
        assert manifest["spec"]["type"] == "ClusterIP"
        assert manifest["spec"]["ports"][0]["port"] == 80
        assert manifest["spec"]["ports"][0]["targetPort"] == 8080

    def test_configmap_yaml(self, tmp_path: Path):
        """ConfigMap resource → data keys preserved."""
        result = generate_k8s_wizard(tmp_path, [
            {
                "kind": "ConfigMap",
                "name": "api-config",
                "namespace": "default",
                "output_dir": "k8s",
                "spec": {
                    "data": {"LOG_LEVEL": "info", "DB_HOST": "localhost"},
                },
            },
        ])
        assert result["ok"] is True
        manifest = yaml.safe_load(result["files"][0]["content"])
        assert manifest["data"]["LOG_LEVEL"] == "info"
        assert manifest["data"]["DB_HOST"] == "localhost"

    def test_secret_yaml(self, tmp_path: Path):
        """Secret resource → stringData, type Opaque."""
        result = generate_k8s_wizard(tmp_path, [
            {
                "kind": "Secret",
                "name": "api-secrets",
                "namespace": "default",
                "output_dir": "k8s",
                "spec": {
                    "stringData": {"API_KEY": "CHANGE_ME"},
                },
            },
        ])
        assert result["ok"] is True
        manifest = yaml.safe_load(result["files"][0]["content"])
        assert manifest["type"] == "Opaque"
        assert manifest["stringData"]["API_KEY"] == "CHANGE_ME"

    def test_ingress_yaml(self, tmp_path: Path):
        """Ingress resource → rules with host and path."""
        result = generate_k8s_wizard(tmp_path, [
            {
                "kind": "Ingress",
                "name": "api-ingress",
                "namespace": "default",
                "output_dir": "k8s",
                "spec": {
                    "host": "api.example.com",
                    "port": 80,
                    "service": "api",
                },
            },
        ])
        assert result["ok"] is True
        manifest = yaml.safe_load(result["files"][0]["content"])
        assert manifest["apiVersion"] == "networking.k8s.io/v1"
        rules = manifest["spec"]["rules"]
        assert len(rules) == 1
        assert rules[0]["host"] == "api.example.com"
        backend = rules[0]["http"]["paths"][0]["backend"]
        assert backend["service"]["name"] == "api"

    def test_pvc_yaml(self, tmp_path: Path):
        """PVC resource → access modes, storage, storageClass."""
        result = generate_k8s_wizard(tmp_path, [
            {
                "kind": "PersistentVolumeClaim",
                "name": "api-data",
                "namespace": "default",
                "output_dir": "k8s",
                "spec": {
                    "accessModes": ["ReadWriteOnce"],
                    "storage": "10Gi",
                    "storageClassName": "gp3",
                },
            },
        ])
        assert result["ok"] is True
        manifest = yaml.safe_load(result["files"][0]["content"])
        assert manifest["spec"]["accessModes"] == ["ReadWriteOnce"]
        assert manifest["spec"]["resources"]["requests"]["storage"] == "10Gi"
        assert manifest["spec"]["storageClassName"] == "gp3"

    def test_namespace_yaml(self, tmp_path: Path):
        """Namespace resource → no namespace in metadata."""
        result = generate_k8s_wizard(tmp_path, [
            {
                "kind": "Namespace",
                "name": "production",
                "namespace": "production",
                "output_dir": "k8s",
                "spec": {},
            },
        ])
        assert result["ok"] is True
        manifest = yaml.safe_load(result["files"][0]["content"])
        assert "namespace" not in manifest["metadata"]

    def test_empty_resources_error(self, tmp_path: Path):
        """Empty resource list → error."""
        result = generate_k8s_wizard(tmp_path, [])
        assert "error" in result

    def test_managed_kind_skipped(self, tmp_path: Path):
        """Managed kind produces no manifest file."""
        result = generate_k8s_wizard(tmp_path, [
            {
                "kind": "Managed",
                "name": "rds-postgres",
                "namespace": "default",
                "output_dir": "k8s",
                "spec": {},
            },
        ])
        assert "error" in result  # Only Managed → no valid files

    def test_file_paths_use_output_dir(self, tmp_path: Path):
        """Output dir is reflected in file paths."""
        result = generate_k8s_wizard(tmp_path, [
            {
                "kind": "Deployment",
                "name": "api",
                "namespace": "default",
                "output_dir": "manifests/prod",
                "spec": {"image": "app:1", "port": 8080},
            },
        ])
        assert result["files"][0]["path"].startswith("manifests/prod/")

    def test_deployment_strategy_in_yaml(self, tmp_path: Path):
        """Deployment strategy fields appear in the generated YAML."""
        result = generate_k8s_wizard(tmp_path, [
            {
                "kind": "Deployment",
                "name": "api",
                "namespace": "default",
                "output_dir": "k8s",
                "spec": {
                    "image": "app:1",
                    "port": 8080,
                    "replicas": 3,
                    "strategy": "RollingUpdate",
                    "maxSurge": 2,
                    "maxUnavailable": 0,
                },
            },
        ])
        manifest = yaml.safe_load(result["files"][0]["content"])
        strategy = manifest["spec"]["strategy"]
        assert strategy["type"] == "RollingUpdate"
        assert strategy["rollingUpdate"]["maxSurge"] == 2

    def test_multi_resource_generates_multiple_files(self, tmp_path: Path):
        """Multiple resources → multiple file entries."""
        result = generate_k8s_wizard(tmp_path, [
            {
                "kind": "Deployment",
                "name": "api",
                "namespace": "default",
                "output_dir": "k8s",
                "spec": {"image": "app:1", "port": 8080},
            },
            {
                "kind": "Service",
                "name": "api",
                "namespace": "default",
                "output_dir": "k8s",
                "spec": {"port": 80, "target_port": 8080},
            },
        ])
        assert result["ok"] is True
        assert len(result["files"]) == 2


# ═══════════════════════════════════════════════════════════════════
#  _generate_skaffold
# ═══════════════════════════════════════════════════════════════════


class TestGenerateSkaffold:
    def test_disabled_returns_none(self):
        """Skaffold disabled → None."""
        result = _generate_skaffold({"skaffold": False}, [])
        assert result is None

    def test_enabled_generates_skaffold(self):
        """Skaffold enabled → valid skaffold.yaml content."""
        generated_files = [
            {"path": "k8s/api-deployment.yaml"},
            {"path": "k8s/api-service.yaml"},
        ]
        result = _generate_skaffold(
            {
                "skaffold": True,
                "output_dir": "k8s",
                "_services": [{"name": "api", "image": "myapp:latest"}],
            },
            generated_files,
        )
        assert result is not None
        assert result["path"] == "skaffold.yaml"
        content = yaml.safe_load(result["content"])
        assert content["apiVersion"] == "skaffold/v4beta11"
        assert content["kind"] == "Config"
        assert "rawYaml" in content["manifests"]

    def test_skaffold_includes_manifest_paths(self):
        """Skaffold rawYaml includes all generated manifest paths."""
        generated_files = [
            {"path": "k8s/api-deployment.yaml"},
            {"path": "k8s/api-service.yaml"},
            {"path": "k8s/api-configmap.yaml"},
        ]
        result = _generate_skaffold(
            {"skaffold": True, "_services": [{"name": "api", "image": "myapp:latest"}]},
            generated_files,
        )
        content = yaml.safe_load(result["content"])
        raw_yaml = content["manifests"]["rawYaml"]
        assert len(raw_yaml) == 3
