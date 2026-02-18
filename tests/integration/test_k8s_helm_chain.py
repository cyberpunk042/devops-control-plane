"""
Integration tests for K8s + Helm chain (1.9).

Tests how K8s wizard state (services, namespace, env vars) wires
into Helm chart generation via generate_helm_chart().
"""

from __future__ import annotations

import yaml
import pytest
from pathlib import Path

from src.core.services.k8s_helm_generate import (
    generate_helm_chart,
    _build_values_yaml,
    _sanitize_chart_name,
    _chart_name,
)

pytestmark = pytest.mark.integration


# ═══════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════


def _svc(name: str = "api", image: str = "myapp:v1.2.3", **kw) -> dict:
    """Build a service dict for _services."""
    base = {"name": name, "image": image, "kind": "Deployment", "port": 8000, "replicas": 2}
    base.update(kw)
    return base


def _gen(data: dict, tmp_path: Path) -> dict:
    """Call generate_helm_chart with defaults and return result."""
    if "helm_chart" not in data:
        data["helm_chart"] = True
    if "_services" not in data:
        data["_services"] = [_svc()]
    return generate_helm_chart(data, tmp_path)


# ═══════════════════════════════════════════════════════════════════
#  K8s services → Helm values.yaml
# ═══════════════════════════════════════════════════════════════════


class TestServicesToValues:
    """K8s services → Helm values.yaml."""

    def test_image_repository_from_service(self):
        """Service image → values.yaml image.repository."""
        values = _build_values_yaml({}, [_svc(image="myapp-api:v2.0.0")])
        assert values["image"]["repository"] == "myapp-api"

    def test_image_tag_from_service(self):
        """Service image tag → values.yaml image.tag."""
        values = _build_values_yaml({}, [_svc(image="myapp-api:v2.0.0")])
        assert values["image"]["tag"] == "v2.0.0"

    def test_image_no_tag_defaults_latest(self):
        """Service image without tag → tag=latest."""
        values = _build_values_yaml({}, [_svc(image="myapp-api")])
        assert values["image"]["tag"] == "latest"

    def test_service_port_flows(self):
        """Service port → values.yaml service.port."""
        values = _build_values_yaml({}, [_svc(port=3000)])
        assert values["service"]["port"] == 3000

    def test_replica_count_flows(self):
        """Service replicas → values.yaml replicaCount."""
        values = _build_values_yaml({}, [_svc(replicas=5)])
        assert values["replicaCount"] == 5

    def test_literal_env_in_values(self):
        """Literal env vars → values.yaml env list."""
        svc = _svc(env=[
            {"key": "APP_ENV", "value": "production", "type": "literal"},
            {"key": "LOG_LEVEL", "value": "info", "type": "literal"},
        ])
        values = _build_values_yaml({}, [svc])
        keys = [e["name"] for e in values["env"]]
        assert "APP_ENV" in keys
        assert "LOG_LEVEL" in keys

    def test_secret_env_creates_existing_secret(self):
        """Secret env vars → values.yaml existingSecret reference."""
        svc = _svc(env=[
            {"key": "DB_PASSWORD", "type": "secret"},
        ])
        values = _build_values_yaml({}, [svc])
        assert "existingSecret" in values
        assert "secrets" in values["existingSecret"]

    def test_secret_env_not_in_plain_env(self):
        """Secret vars excluded from plain env list."""
        svc = _svc(env=[
            {"key": "APP_ENV", "value": "prod", "type": "literal"},
            {"key": "DB_PASSWORD", "type": "secret"},
        ])
        values = _build_values_yaml({}, [svc])
        keys = [e["name"] for e in values["env"]]
        assert "APP_ENV" in keys
        assert "DB_PASSWORD" not in keys

    def test_ingress_enabled_with_host(self):
        """ingress_host set → ingress.enabled=True."""
        values = _build_values_yaml({"ingress_host": "app.example.com"}, [_svc()])
        assert values["ingress"]["enabled"] is True
        assert values["ingress"]["host"] == "app.example.com"

    def test_ingress_disabled_without_host(self):
        """No ingress_host → ingress.enabled=False."""
        values = _build_values_yaml({}, [_svc()])
        assert values["ingress"]["enabled"] is False


# ═══════════════════════════════════════════════════════════════════
#  Chart generation — files on disk
# ═══════════════════════════════════════════════════════════════════


class TestChartGeneration:
    """generate_helm_chart creates correct directory structure."""

    def test_chart_yaml_created(self, tmp_path: Path):
        """Chart.yaml generated with correct fields."""
        result = _gen({}, tmp_path)
        chart_yaml = tmp_path / "charts" / "api" / "Chart.yaml"
        assert chart_yaml.exists()
        parsed = yaml.safe_load(chart_yaml.read_text())
        assert parsed["apiVersion"] == "v2"
        assert parsed["name"] == "api"
        assert parsed["type"] == "application"
        assert parsed["appVersion"] == "v1.2.3"

    def test_values_yaml_created(self, tmp_path: Path):
        """values.yaml generated and valid YAML."""
        result = _gen({}, tmp_path)
        values_file = tmp_path / "charts" / "api" / "values.yaml"
        assert values_file.exists()
        parsed = yaml.safe_load(values_file.read_text())
        assert "image" in parsed
        assert "service" in parsed

    def test_templates_directory(self, tmp_path: Path):
        """templates/ contains deployment, service, helpers, notes."""
        result = _gen({"_services": [_svc(port=8000)]}, tmp_path)
        tpl_dir = tmp_path / "charts" / "api" / "templates"
        assert tpl_dir.is_dir()
        assert (tpl_dir / "deployment.yaml").exists()
        assert (tpl_dir / "service.yaml").exists()
        assert (tpl_dir / "ingress.yaml").exists()
        assert (tpl_dir / "_helpers.tpl").exists()
        assert (tpl_dir / "NOTES.txt").exists()

    def test_configmap_only_when_literal_vars(self, tmp_path: Path):
        """configmap.yaml only generated when literal env vars exist."""
        # Without literal env vars
        result = _gen({"_services": [_svc()]}, tmp_path)
        tpl_dir = tmp_path / "charts" / "api" / "templates"
        assert not (tpl_dir / "configmap.yaml").exists()

    def test_configmap_with_literal_vars(self, tmp_path: Path):
        """configmap.yaml generated when literal env vars exist."""
        svc = _svc(env=[{"key": "FOO", "value": "bar", "type": "literal"}])
        result = _gen({"_services": [svc]}, tmp_path)
        tpl_dir = tmp_path / "charts" / "api" / "templates"
        assert (tpl_dir / "configmap.yaml").exists()

    def test_secret_only_when_secret_vars(self, tmp_path: Path):
        """secret.yaml only generated when secret env vars exist."""
        # Without secret env vars
        result = _gen({"_services": [_svc()]}, tmp_path)
        tpl_dir = tmp_path / "charts" / "api" / "templates"
        assert not (tpl_dir / "secret.yaml").exists()

    def test_secret_with_secret_vars(self, tmp_path: Path):
        """secret.yaml generated when secret env vars exist."""
        svc = _svc(env=[{"key": "DB_PASS", "type": "secret"}])
        result = _gen({"_services": [svc]}, tmp_path)
        tpl_dir = tmp_path / "charts" / "api" / "templates"
        assert (tpl_dir / "secret.yaml").exists()

    def test_disabled_returns_empty(self, tmp_path: Path):
        """helm_chart=False → empty files list."""
        result = generate_helm_chart({"helm_chart": False}, tmp_path)
        assert result["files"] == []

    def test_helmignore_created(self, tmp_path: Path):
        """`.helmignore` file generated."""
        result = _gen({}, tmp_path)
        helmignore = tmp_path / "charts" / "api" / ".helmignore"
        assert helmignore.exists()
        content = helmignore.read_text()
        assert ".git/" in content

    def test_per_env_values_files(self, tmp_path: Path):
        """Per-environment values-{env}.yaml files generated."""
        result = _gen({
            "environments": ["dev", "staging", "prod"],
        }, tmp_path)
        chart_dir = tmp_path / "charts" / "api"
        assert (chart_dir / "values-dev.yaml").exists()
        assert (chart_dir / "values-staging.yaml").exists()
        assert (chart_dir / "values-prod.yaml").exists()

    def test_files_list_in_result(self, tmp_path: Path):
        """Result includes list of all generated file paths."""
        result = _gen({}, tmp_path)
        assert len(result["files"]) >= 5  # Chart.yaml, values.yaml, 3+ templates

    def test_all_generated_yaml_valid(self, tmp_path: Path):
        """All generated .yaml files are valid YAML."""
        result = _gen({
            "environments": ["dev"],
            "_services": [_svc(env=[
                {"key": "FOO", "value": "bar", "type": "literal"},
                {"key": "SECRET", "type": "secret"},
            ])],
        }, tmp_path)
        for fpath in result["files"]:
            full = tmp_path / fpath
            if full.suffix in (".yaml", ".yml"):
                content = full.read_text()
                # Helm templates have Go template syntax, so only parse values/Chart
                if "templates" not in fpath:
                    parsed = yaml.safe_load(content)
                    assert parsed is not None, f"Invalid YAML: {fpath}"


# ═══════════════════════════════════════════════════════════════════
#  Chart name sanitization
# ═══════════════════════════════════════════════════════════════════


class TestChartNameSanitization:
    """Chart names sanitized to DNS-label format."""

    def test_simple_name(self):
        assert _sanitize_chart_name("myapp") == "myapp"

    def test_uppercase_lowered(self):
        assert _sanitize_chart_name("MyApp") == "myapp"

    def test_spaces_replaced(self):
        assert _sanitize_chart_name("my app") == "my-app"

    def test_special_chars_replaced(self):
        assert _sanitize_chart_name("my_app.v2") == "my-app-v2"

    def test_consecutive_dashes_collapsed(self):
        assert _sanitize_chart_name("my--app") == "my-app"

    def test_empty_fallback(self):
        assert _sanitize_chart_name("") == "app"

    def test_truncated_to_63(self):
        result = _sanitize_chart_name("a" * 100)
        assert len(result) <= 63

    def test_chart_name_from_service(self):
        """Chart name derived from first service name."""
        name = _chart_name([{"name": "my-api"}])
        assert name == "my-api"

    def test_chart_name_fallback(self):
        """No services → fallback to 'app'."""
        assert _chart_name([]) == "app"


# ═══════════════════════════════════════════════════════════════════
#  Namespace flow via Skaffold Helm releases
# ═══════════════════════════════════════════════════════════════════


class TestNamespaceInHelmReleases:
    """K8s namespace → Helm release namespace in Skaffold."""

    def test_namespace_in_release(self):
        """Namespace → Helm release namespace field."""
        from src.core.services.k8s_wizard_generate import _build_helm_releases
        data = {
            "namespace": "production",
            "_services": [_svc()],
        }
        releases = _build_helm_releases(data)
        assert len(releases) == 1
        assert releases[0]["namespace"] == "production"
        assert releases[0]["createNamespace"] is True

    def test_no_namespace_no_field(self):
        """No namespace → no namespace field in release."""
        from src.core.services.k8s_wizard_generate import _build_helm_releases
        data = {"_services": [_svc()]}
        releases = _build_helm_releases(data)
        assert "namespace" not in releases[0]

    def test_helm_chart_path(self):
        """helmChartPath → release chartPath."""
        from src.core.services.k8s_wizard_generate import _build_helm_releases
        data = {
            "helmChartPath": "charts/api",
            "_services": [_svc()],
        }
        releases = _build_helm_releases(data)
        assert releases[0]["chartPath"] == "charts/api"

    def test_values_files_flow(self):
        """helmValuesFiles → release valuesFiles."""
        from src.core.services.k8s_wizard_generate import _build_helm_releases
        data = {
            "helmValuesFiles": ["values.yaml", "values-prod.yaml"],
            "_services": [_svc()],
        }
        releases = _build_helm_releases(data)
        assert releases[0]["valuesFiles"] == ["values.yaml", "values-prod.yaml"]
