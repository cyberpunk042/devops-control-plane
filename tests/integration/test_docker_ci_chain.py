"""
Integration tests for Docker + CI/CD cross-domain chain (1.2).

Tests how Docker configuration controls CI workflow generation.

All tests call generate_docker_ci() and verify the produced YAML
contains the expected steps, actions, and configuration.
"""

from __future__ import annotations

import yaml
import pytest

from src.core.services.generators.github_workflow import generate_docker_ci

pytestmark = pytest.mark.integration


# ═══════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════


def _gen(services: list[dict], **kwargs) -> dict:
    """Call generate_docker_ci and return content + parsed YAML."""
    result = generate_docker_ci(services, **kwargs)
    assert result is not None, "generate_docker_ci returned None"
    content = result.content
    parsed = yaml.safe_load(content)
    return {"content": content, "parsed": parsed, "result": result}


# ═══════════════════════════════════════════════════════════════════
#  1.2 — Docker + CI/CD
# ═══════════════════════════════════════════════════════════════════


class TestDockerCiBasic:
    """Basic Docker CI generation."""

    def test_docker_detected_includes_build(self):
        """Docker detected → CI workflow includes docker build."""
        out = _gen([{"name": "app"}])
        assert "docker build" in out["content"]

    def test_return_shape(self):
        """Return shape: file with path, content, etc."""
        result = generate_docker_ci([{"name": "app"}])
        assert result is not None
        d = result.model_dump()
        assert "path" in d
        assert "content" in d
        assert d["path"] == ".github/workflows/docker.yml"

    def test_valid_yaml(self):
        """Generated workflow is valid YAML."""
        out = _gen([{"name": "app"}])
        assert out["parsed"] is not None
        assert "jobs" in out["parsed"]

    def test_checkout_step(self):
        """Docker job uses actions/checkout@v4."""
        out = _gen([{"name": "app"}])
        assert "actions/checkout@v4" in out["content"]

    def test_depends_on_test(self):
        """Docker CI job depends on test job (needs: [test])."""
        out = _gen([{"name": "app"}])
        docker_job = out["parsed"]["jobs"].get("docker", {})
        assert "test" in docker_job.get("needs", [])

    def test_push_only(self):
        """Docker CI job only runs on push events, not PRs."""
        out = _gen([{"name": "app"}])
        docker_job = out["parsed"]["jobs"].get("docker", {})
        assert docker_job.get("if") == "github.event_name == 'push'"

    def test_image_name_from_service(self):
        """Docker image name derived from service name."""
        out = _gen([{"name": "myapi"}])
        assert "myapi:" in out["content"]


class TestDockerCiRegistry:
    """Registry-specific CI generation."""

    def test_ghcr_login(self):
        """Docker + GHCR → CI has docker/login-action with ghcr.io."""
        out = _gen([{
            "name": "app",
            "registry": "ghcr.io/org",
            "registry_type": "ghcr",
        }])
        assert "docker/login-action@v3" in out["content"]
        assert "ghcr.io" in out["content"]
        assert "GITHUB_TOKEN" in out["content"]

    def test_ghcr_push(self):
        """Docker + GHCR → CI has docker push."""
        out = _gen([{
            "name": "app",
            "registry": "ghcr.io/org",
            "registry_type": "ghcr",
        }])
        assert "docker push" in out["content"]
        assert "ghcr.io/org/app" in out["content"]

    def test_dockerhub_login(self):
        """Docker + DockerHub → CI has DockerHub login."""
        out = _gen([{
            "name": "app",
            "registry": "docker.io/org",
            "registry_type": "dockerhub",
        }])
        assert "docker/login-action@v3" in out["content"]
        assert "DOCKERHUB_USERNAME" in out["content"]
        assert "DOCKERHUB_TOKEN" in out["content"]

    def test_custom_registry_login(self):
        """Docker + custom registry → CI has custom registry login."""
        out = _gen([{
            "name": "app",
            "registry": "registry.example.com",
            "registry_type": "custom",
        }])
        assert "docker/login-action@v3" in out["content"]
        assert "registry.example.com" in out["content"]
        assert "REGISTRY_USERNAME" in out["content"]

    def test_no_registry_no_push(self):
        """Docker + no registry → build only, no push."""
        out = _gen([{"name": "app"}])
        assert "docker build" in out["content"]
        assert "docker push" not in out["content"]


class TestDockerCiFeatures:
    """Feature toggles: Buildx, build args, caching, tagging."""

    def test_buildx(self):
        """Docker + Buildx → CI includes setup-buildx-action."""
        out = _gen([{"name": "app", "use_buildx": True}])
        assert "docker/setup-buildx-action@v3" in out["content"]

    def test_build_args(self):
        """Docker + build args → CI passes --build-arg."""
        out = _gen([{
            "name": "app",
            "build_args": {"APP_VERSION": "1.0.0", "ENV": "prod"},
        }])
        assert "--build-arg APP_VERSION=1.0.0" in out["content"]
        assert "--build-arg ENV=prod" in out["content"]

    def test_layer_caching(self):
        """Docker + layer caching → CI uses cache-from/cache-to type=gha."""
        out = _gen([{"name": "app", "use_cache": True}])
        assert "cache-from type=gha" in out["content"]
        assert "cache-to type=gha" in out["content"]

    def test_image_tagging(self):
        """Docker → CI tags with github.sha and latest."""
        out = _gen([{"name": "app"}])
        assert "github.sha" in out["content"]
        assert ":latest" in out["content"]


class TestDockerCiMultiService:
    """Multiple Docker services in one CI."""

    def test_two_services(self):
        """Multiple Docker services → CI builds each image separately."""
        out = _gen([
            {"name": "api", "registry": "ghcr.io/org", "registry_type": "ghcr"},
            {"name": "worker", "registry": "ghcr.io/org", "registry_type": "ghcr"},
        ])
        # Each service gets its own job
        jobs = out["parsed"]["jobs"]
        docker_jobs = [k for k in jobs if k.startswith("docker")]
        assert len(docker_jobs) == 2
        assert "docker-api" in jobs
        assert "docker-worker" in jobs

    def test_no_services_returns_none(self):
        """Empty services list → returns None."""
        result = generate_docker_ci([])
        assert result is None
