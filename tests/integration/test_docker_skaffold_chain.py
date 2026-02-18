"""
Integration tests for Docker + Skaffold (1.3) and Docker + Helm (1.4).

Tests how Docker config flows through the Skaffold generator
and Helm release builder in k8s_wizard_generate.py.

All tests exercise existing code — no new implementation required.
"""

from __future__ import annotations

import yaml
import pytest

from src.core.services.k8s_wizard_generate import (
    _generate_skaffold,
    _build_helm_releases,
)

pytestmark = pytest.mark.integration


# ═══════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════


def _skaffold(services: list[dict], **data_overrides) -> dict:
    """Call _generate_skaffold and parse the result."""
    data = {
        "skaffold": True,
        "_services": services,
        "namespace": "default",
        "output_dir": "k8s",
        **data_overrides,
    }
    generated_files = [
        {"path": "k8s/app-deployment.yaml", "content": "", "overwrite": False},
    ]
    result = _generate_skaffold(data, generated_files)
    assert result is not None, "_generate_skaffold returned None"
    parsed = yaml.safe_load(result["content"])
    return {"raw": result, "parsed": parsed}


# ═══════════════════════════════════════════════════════════════════
#  1.3 — Docker + Skaffold
# ═══════════════════════════════════════════════════════════════════


class TestDockerSkaffold:
    """Skaffold generator reads Docker config from wizard state."""

    def test_image_and_dockerfile(self):
        """Service image + dockerfile → Skaffold artifact."""
        out = _skaffold([{
            "name": "api",
            "kind": "Deployment",
            "image": "myapp:v1",
            "dockerfile": "Dockerfile.prod",
        }])
        artifacts = out["parsed"]["build"]["artifacts"]
        assert len(artifacts) == 1
        assert artifacts[0]["image"] == "myapp:v1"
        assert artifacts[0]["docker"]["dockerfile"] == "Dockerfile.prod"

    def test_build_args(self):
        """Service buildArgs → Skaffold artifact.docker.buildArgs."""
        out = _skaffold([{
            "name": "api",
            "kind": "Deployment",
            "image": "myapp:v1",
            "buildArgs": {"VERSION": "1.0", "ENV": "prod"},
        }])
        artifacts = out["parsed"]["build"]["artifacts"]
        assert artifacts[0]["docker"]["buildArgs"] == {"VERSION": "1.0", "ENV": "prod"}

    def test_build_target(self):
        """Service buildTarget → Skaffold artifact.docker.target."""
        out = _skaffold([{
            "name": "api",
            "kind": "Deployment",
            "image": "myapp:v1",
            "buildTarget": "prod",
        }])
        artifacts = out["parsed"]["build"]["artifacts"]
        assert artifacts[0]["docker"]["target"] == "prod"

    def test_multiple_services(self):
        """Multiple services → multiple Skaffold artifacts."""
        out = _skaffold([
            {"name": "api", "kind": "Deployment", "image": "api:v1"},
            {"name": "worker", "kind": "Deployment", "image": "worker:v1"},
        ])
        artifacts = out["parsed"]["build"]["artifacts"]
        assert len(artifacts) == 2
        images = {a["image"] for a in artifacts}
        assert images == {"api:v1", "worker:v1"}

    def test_no_image_skipped(self):
        """Service with no image → no artifact."""
        out = _skaffold([
            {"name": "api", "kind": "Deployment", "image": "api:v1"},
            {"name": "sidecar", "kind": "Deployment", "image": ""},
        ])
        artifacts = out["parsed"]["build"]["artifacts"]
        assert len(artifacts) == 1
        assert artifacts[0]["image"] == "api:v1"

    def test_skip_kind_excluded(self):
        """Service with kind=Skip → no artifact."""
        out = _skaffold([
            {"name": "api", "kind": "Deployment", "image": "api:v1"},
            {"name": "db", "kind": "Skip", "image": "postgres:16"},
        ])
        artifacts = out["parsed"]["build"]["artifacts"]
        assert len(artifacts) == 1

    def test_local_push_false(self):
        """Skaffold build.local.push = false by default."""
        out = _skaffold([
            {"name": "api", "kind": "Deployment", "image": "api:v1"},
        ])
        assert out["parsed"]["build"]["local"]["push"] is False

    def test_local_use_buildkit(self):
        """Skaffold build.local.useBuildkit = true."""
        out = _skaffold([
            {"name": "api", "kind": "Deployment", "image": "api:v1"},
        ])
        assert out["parsed"]["build"]["local"]["useBuildkit"] is True


# ═══════════════════════════════════════════════════════════════════
#  1.4 — Docker + Helm
# ═══════════════════════════════════════════════════════════════════


class TestDockerHelm:
    """Helm releases wire Docker images through Skaffold."""

    def test_service_creates_release(self):
        """Service with image → Helm release with matching name."""
        data = {
            "_services": [
                {"name": "api", "kind": "Deployment", "image": "api:v1"},
            ],
            "namespace": "prod",
            "helmChartPath": "charts/api",
        }
        releases = _build_helm_releases(data)
        assert len(releases) == 1
        assert releases[0]["name"] == "api"

    def test_namespace(self):
        """Namespace → Helm release.namespace matches."""
        data = {
            "_services": [
                {"name": "api", "kind": "Deployment", "image": "api:v1"},
            ],
            "namespace": "prod",
        }
        releases = _build_helm_releases(data)
        assert releases[0]["namespace"] == "prod"
        assert releases[0]["createNamespace"] is True

    def test_chart_path(self):
        """helmChartPath → Helm release.chartPath matches."""
        data = {
            "_services": [
                {"name": "api", "kind": "Deployment", "image": "api:v1"},
            ],
            "helmChartPath": "charts/my-app",
        }
        releases = _build_helm_releases(data)
        assert releases[0]["chartPath"] == "charts/my-app"

    def test_values_files(self):
        """helmValuesFiles → Helm release.valuesFiles matches."""
        data = {
            "_services": [
                {"name": "api", "kind": "Deployment", "image": "api:v1"},
            ],
            "helmValuesFiles": ["values.yaml", "values-prod.yaml"],
        }
        releases = _build_helm_releases(data)
        assert releases[0]["valuesFiles"] == ["values.yaml", "values-prod.yaml"]

    def test_hardcoded_env_set_values(self):
        """Hardcoded env vars → Helm release.setValues."""
        data = {
            "_services": [
                {
                    "name": "api",
                    "kind": "Deployment",
                    "image": "api:v1",
                    "env": [
                        {"key": "DB_HOST", "type": "hardcoded", "value": "localhost"},
                    ],
                },
            ],
        }
        releases = _build_helm_releases(data)
        assert releases[0]["setValues"] == {"DB_HOST": "localhost"}

    def test_variable_env_set_value_templates(self):
        """Variable-type env vars → Helm release.setValueTemplates."""
        data = {
            "_services": [
                {
                    "name": "api",
                    "kind": "Deployment",
                    "image": "api:v1",
                    "env": [
                        {"key": "DB_PASSWORD", "type": "variable"},
                    ],
                },
            ],
        }
        releases = _build_helm_releases(data)
        assert "DB_PASSWORD" in releases[0].get("setValueTemplates", {})
