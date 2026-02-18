"""
Integration tests for Skaffold + Helm chain (1.12).

Tests the cross-domain flow: K8s wizard state with deployStrategy=helm
wires into Skaffold config generation with Helm deployer, verifying
build artifacts, Helm releases, namespace propagation, env vars, and
chart configuration all flow correctly through the Skaffold document.

Spec grounding:
    PROJECT_SCOPE §4.2 Facilitate = "Generate Skaffold config
    (build, deploy, profiles, portForward, envsubst hooks)"
"""

from __future__ import annotations

import yaml
import pytest

from src.core.services.k8s_wizard_generate import _generate_skaffold

pytestmark = pytest.mark.integration


# ═══════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════


def _svc(name: str = "api", image: str = "myapp:latest", **kw) -> dict:
    """Build a service dict for _services."""
    base = {"name": name, "image": image, "kind": "Deployment"}
    base.update(kw)
    return base


def _gen(data: dict, generated_files: list[dict] | None = None) -> dict:
    """Call _generate_skaffold and return parsed YAML."""
    if generated_files is None:
        generated_files = [
            {"path": "k8s/deployment.yaml", "content": "---"},
            {"path": "k8s/service.yaml", "content": "---"},
        ]
    if "skaffold" not in data:
        data["skaffold"] = True
    result = _generate_skaffold(data, generated_files)
    if result is None:
        return {"result": None, "parsed": None}
    parsed = yaml.safe_load(result["content"])
    return {"result": result, "parsed": parsed}


# ═══════════════════════════════════════════════════════════════════
#  Helm deployer routing
# ═══════════════════════════════════════════════════════════════════


class TestHelmDeployerRouting:
    """deployStrategy selects correct deployer."""

    def test_helm_strategy_uses_helm_deploy(self):
        """deployStrategy=helm → deploy.helm.releases present, NOT deploy.kubectl."""
        out = _gen({"_services": [_svc()], "deployStrategy": "helm"})
        deploy = out["parsed"]["deploy"]
        assert "helm" in deploy
        assert "releases" in deploy["helm"]
        assert "kubectl" not in deploy

    def test_kubectl_strategy_uses_kubectl_deploy(self):
        """deployStrategy=kubectl → deploy.kubectl present, NOT deploy.helm."""
        out = _gen({"_services": [_svc()], "deployStrategy": "kubectl"})
        deploy = out["parsed"]["deploy"]
        assert "kubectl" in deploy
        assert "helm" not in deploy


# ═══════════════════════════════════════════════════════════════════
#  Build + Helm deploy together
# ═══════════════════════════════════════════════════════════════════


class TestBuildAndHelmDeploy:
    """Build artifacts coexist with Helm deploy in same Skaffold doc."""

    def test_build_artifacts_with_helm_deploy(self):
        """Build artifacts present alongside Helm deploy."""
        out = _gen({"_services": [_svc()], "deployStrategy": "helm"})
        doc = out["parsed"]
        # Both sections present
        assert "build" in doc
        assert "deploy" in doc
        assert "artifacts" in doc["build"]
        assert "helm" in doc["deploy"]

    def test_multiple_services_multiple_artifacts_and_releases(self):
        """Multiple services → multiple build artifacts + Helm releases."""
        out = _gen({
            "_services": [
                _svc("api", "api:latest"),
                _svc("web", "web:latest"),
                _svc("worker", "worker:latest"),
            ],
            "deployStrategy": "helm",
        })
        doc = out["parsed"]
        artifacts = doc["build"]["artifacts"]
        releases = doc["deploy"]["helm"]["releases"]
        assert len(artifacts) == 3
        assert len(releases) == 3
        # All images present in artifacts
        images = {a["image"] for a in artifacts}
        assert images == {"api:latest", "web:latest", "worker:latest"}
        # All services present in releases
        release_names = {r["name"] for r in releases}
        assert release_names == {"api", "web", "worker"}

    def test_skip_service_excluded_from_both(self):
        """Skip-kind service excluded from both artifacts and releases."""
        out = _gen({
            "_services": [
                _svc("api", "api:latest"),
                _svc("skip-me", "skip:latest", kind="Skip"),
            ],
            "deployStrategy": "helm",
        })
        artifacts = out["parsed"]["build"]["artifacts"]
        releases = out["parsed"]["deploy"]["helm"]["releases"]
        assert len(artifacts) == 1
        assert len(releases) == 1
        assert artifacts[0]["image"] == "api:latest"
        assert releases[0]["name"] == "api"


# ═══════════════════════════════════════════════════════════════════
#  Helm release properties
# ═══════════════════════════════════════════════════════════════════


class TestHelmReleaseProperties:
    """Wizard state flows into Helm release config."""

    def test_namespace_propagated(self):
        """Namespace → release.namespace."""
        out = _gen({
            "_services": [_svc()],
            "deployStrategy": "helm",
            "namespace": "production",
        })
        release = out["parsed"]["deploy"]["helm"]["releases"][0]
        assert release["namespace"] == "production"

    def test_create_namespace_when_present(self):
        """createNamespace=true when namespace present."""
        out = _gen({
            "_services": [_svc()],
            "deployStrategy": "helm",
            "namespace": "staging",
        })
        release = out["parsed"]["deploy"]["helm"]["releases"][0]
        assert release["createNamespace"] is True

    def test_no_namespace_no_namespace_fields(self):
        """No namespace → no namespace or createNamespace in release."""
        out = _gen({
            "_services": [_svc()],
            "deployStrategy": "helm",
        })
        release = out["parsed"]["deploy"]["helm"]["releases"][0]
        assert "namespace" not in release
        assert "createNamespace" not in release

    def test_custom_chart_path(self):
        """Custom helmChartPath → release.chartPath."""
        out = _gen({
            "_services": [_svc()],
            "deployStrategy": "helm",
            "helmChartPath": "helm/mychart",
        })
        release = out["parsed"]["deploy"]["helm"]["releases"][0]
        assert release["chartPath"] == "helm/mychart"

    def test_default_chart_path(self):
        """No helmChartPath → default 'charts'."""
        out = _gen({
            "_services": [_svc()],
            "deployStrategy": "helm",
        })
        release = out["parsed"]["deploy"]["helm"]["releases"][0]
        assert release["chartPath"] == "charts"

    def test_values_files_flow(self):
        """helmValuesFiles → release.valuesFiles."""
        out = _gen({
            "_services": [_svc()],
            "deployStrategy": "helm",
            "helmValuesFiles": ["values.yaml", "values-prod.yaml"],
        })
        release = out["parsed"]["deploy"]["helm"]["releases"][0]
        assert release["valuesFiles"] == ["values.yaml", "values-prod.yaml"]

    def test_helm_secrets_plugin(self):
        """helmSecretsPlugin → release.useHelmSecrets."""
        out = _gen({
            "_services": [_svc()],
            "deployStrategy": "helm",
            "helmSecretsPlugin": True,
        })
        release = out["parsed"]["deploy"]["helm"]["releases"][0]
        assert release["useHelmSecrets"] is True


# ═══════════════════════════════════════════════════════════════════
#  Env vars → Helm setValues
# ═══════════════════════════════════════════════════════════════════


class TestEnvVarsToHelmValues:
    """Service env vars flow into Helm release setValues/setValueTemplates."""

    def test_literal_env_to_set_values(self):
        """Literal env vars → release.setValues."""
        out = _gen({
            "_services": [_svc("api", "api:latest", env=[
                {"key": "PORT", "value": "8080"},
                {"key": "LOG_LEVEL", "value": "info"},
            ])],
            "deployStrategy": "helm",
        })
        release = out["parsed"]["deploy"]["helm"]["releases"][0]
        assert release["setValues"]["PORT"] == "8080"
        assert release["setValues"]["LOG_LEVEL"] == "info"

    def test_variable_env_to_set_value_templates(self):
        """Variable env vars → release.setValueTemplates (Go template)."""
        out = _gen({
            "_services": [_svc("api", "api:latest", env=[
                {"key": "DB_HOST", "type": "variable"},
                {"key": "API_KEY", "type": "secret"},
            ])],
            "deployStrategy": "helm",
        })
        release = out["parsed"]["deploy"]["helm"]["releases"][0]
        assert "setValueTemplates" in release
        assert release["setValueTemplates"]["DB_HOST"] == "{{.DB_HOST}}"
        assert release["setValueTemplates"]["API_KEY"] == "{{.API_KEY}}"

    def test_mixed_env_vars(self):
        """Mixed literal + variable env → both setValues and setValueTemplates."""
        out = _gen({
            "_services": [_svc("api", "api:latest", env=[
                {"key": "PORT", "value": "8080"},
                {"key": "DB_URL", "type": "variable"},
            ])],
            "deployStrategy": "helm",
        })
        release = out["parsed"]["deploy"]["helm"]["releases"][0]
        assert release["setValues"]["PORT"] == "8080"
        assert release["setValueTemplates"]["DB_URL"] == "{{.DB_URL}}"

    def test_no_env_vars_no_set_values(self):
        """No env vars → no setValues or setValueTemplates."""
        out = _gen({
            "_services": [_svc("api", "api:latest")],
            "deployStrategy": "helm",
        })
        release = out["parsed"]["deploy"]["helm"]["releases"][0]
        assert "setValues" not in release
        assert "setValueTemplates" not in release
