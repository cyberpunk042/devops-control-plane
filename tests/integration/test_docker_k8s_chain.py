"""
Integration tests for Docker + K8s cross-domain chain (1.1).

Tests how Docker detection feeds into K8s manifest generation.

Section 1.1a — Parameter pass-through: existing API (should pass).
Section 1.1b — Auto-wiring: bridge function (requires new code).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.core.services.k8s_generate import generate_manifests
from src.core.services.k8s_wizard import wizard_state_to_resources

pytestmark = pytest.mark.integration


# ═══════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════


def _write(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _find_file(result: dict, substring: str) -> dict | None:
    """Find a generated file whose path contains *substring*."""
    for f in result.get("files", []):
        if substring in f.get("path", ""):
            return f
    return None


def _find_resource(resources: list[dict], kind: str, name: str = "") -> dict | None:
    """Find a resource dict by kind (and optional name)."""
    for r in resources:
        if r.get("kind") == kind:
            if not name or r.get("name") == name:
                return r
    return None


# ═══════════════════════════════════════════════════════════════════
#  1.1a — Parameter Pass-Through (existing API)
# ═══════════════════════════════════════════════════════════════════


class TestParameterPassThrough:
    """K8s generators accept Docker-derived values as parameters."""

    def test_generate_manifests_image(self, tmp_path: Path):
        """generate_manifests(image=...) → Deployment YAML contains that image."""
        result = generate_manifests(
            tmp_path, "myapp", image="myapp:v1", port=8080,
        )
        assert result["ok"] is True
        deploy = _find_file(result, "deployment")
        assert deploy is not None
        assert "myapp:v1" in deploy["content"]

    def test_generate_manifests_port(self, tmp_path: Path):
        """generate_manifests(port=...) → Service YAML contains that port."""
        result = generate_manifests(
            tmp_path, "myapp", image="myapp:v1", port=3000,
        )
        svc = _find_file(result, "service")
        assert svc is not None
        assert "3000" in svc["content"]

    def test_generate_manifests_default_image(self, tmp_path: Path):
        """generate_manifests() with no image → defaults to {app_name}:latest."""
        result = generate_manifests(tmp_path, "webapp")
        deploy = _find_file(result, "deployment")
        assert deploy is not None
        assert "webapp:latest" in deploy["content"]

    def test_wizard_state_image(self):
        """wizard_state_to_resources() uses service image field."""
        state = {
            "_services": [
                {"name": "api", "kind": "Deployment", "image": "myapp:v1", "port": 8080},
            ],
            "namespace": "default",
        }
        resources = wizard_state_to_resources(state)
        deploy = _find_resource(resources, "Deployment", "api")
        assert deploy is not None
        assert deploy["spec"]["image"] == "myapp:v1"

    def test_wizard_state_port(self):
        """wizard_state_to_resources() creates Service with correct port."""
        state = {
            "_services": [
                {"name": "api", "kind": "Deployment", "image": "myapp:v1", "port": 3000},
            ],
            "namespace": "default",
        }
        resources = wizard_state_to_resources(state)
        svc = _find_resource(resources, "Service", "api")
        assert svc is not None
        assert svc["spec"]["port"] == 3000

    def test_wizard_state_multiple_services(self):
        """wizard_state_to_resources() with multiple services → each gets Deployment + Service."""
        state = {
            "_services": [
                {"name": "api", "kind": "Deployment", "image": "api:v1", "port": 8080},
                {"name": "worker", "kind": "Deployment", "image": "worker:v1", "port": 9090},
            ],
            "namespace": "default",
        }
        resources = wizard_state_to_resources(state)

        # Two Deployments
        deployments = [r for r in resources if r["kind"] == "Deployment"]
        assert len(deployments) == 2
        deploy_names = {d["name"] for d in deployments}
        assert deploy_names == {"api", "worker"}

        # Two Services
        services = [r for r in resources if r["kind"] == "Service"]
        assert len(services) == 2
        svc_names = {s["name"] for s in services}
        assert svc_names == {"api", "worker"}


# ═══════════════════════════════════════════════════════════════════
#  1.1b — Auto-Wiring (cross-domain bridge)
# ═══════════════════════════════════════════════════════════════════


class TestAutoWiring:
    """Cross-domain bridge: Docker detection → K8s generation.

    These tests require a ``docker_to_k8s_services()`` bridge function
    that reads docker_status() output and returns K8s-ready service defs.

    All tests create real Docker config files and call docker_status(),
    then feed the result through the bridge.
    """

    @pytest.fixture(autouse=True)
    def _check_bridge(self):
        """Skip all auto-wiring tests if the bridge function doesn't exist yet."""
        try:
            from src.core.services.docker_k8s_bridge import docker_to_k8s_services  # noqa: F401
            self._bridge = docker_to_k8s_services
        except ImportError:
            pytest.skip("docker_k8s_bridge.docker_to_k8s_services not yet implemented")

    def test_dockerfile_expose_port(self, tmp_path: Path):
        """Docker EXPOSE 8080 → K8s manifest port=8080."""
        _write(tmp_path / "Dockerfile", "FROM python:3.12\nEXPOSE 8080\n")

        from src.core.services.docker_detect import docker_status
        status = docker_status(tmp_path)
        services = self._bridge(status)

        assert len(services) >= 1
        assert services[0]["port"] == 8080

    def test_compose_service_image(self, tmp_path: Path):
        """Compose service with image → K8s Deployment image matches."""
        _write(tmp_path / "docker-compose.yml", yaml.dump({
            "version": "3.8",
            "services": {
                "web": {"image": "myapp:v1", "ports": ["8080:8080"]},
            },
        }))

        from src.core.services.docker_detect import docker_status
        status = docker_status(tmp_path)
        services = self._bridge(status)

        assert len(services) >= 1
        web = next((s for s in services if s["name"] == "web"), None)
        assert web is not None
        assert web["image"] == "myapp:v1"

    def test_compose_service_port(self, tmp_path: Path):
        """Compose service with ports → K8s Service port matches container port."""
        _write(tmp_path / "docker-compose.yml", yaml.dump({
            "version": "3.8",
            "services": {
                "web": {"image": "myapp:v1", "ports": ["3000:3000"]},
            },
        }))

        from src.core.services.docker_detect import docker_status
        status = docker_status(tmp_path)
        services = self._bridge(status)

        web = next((s for s in services if s["name"] == "web"), None)
        assert web is not None
        assert web["port"] == 3000

    def test_compose_two_services(self, tmp_path: Path):
        """Compose with 2 services → bridge returns 2 K8s service defs."""
        _write(tmp_path / "docker-compose.yml", yaml.dump({
            "version": "3.8",
            "services": {
                "api": {"image": "api:v1", "ports": ["8080:8080"]},
                "worker": {"image": "worker:v1", "ports": ["9090:9090"]},
            },
        }))

        from src.core.services.docker_detect import docker_status
        status = docker_status(tmp_path)
        services = self._bridge(status)

        assert len(services) == 2
        names = {s["name"] for s in services}
        assert names == {"api", "worker"}

    def test_compose_build_context_no_image(self, tmp_path: Path):
        """Compose service with build: . but no image → uses {service_name}:latest."""
        _write(tmp_path / "Dockerfile", "FROM python:3.12\n")
        _write(tmp_path / "docker-compose.yml", yaml.dump({
            "version": "3.8",
            "services": {
                "app": {"build": ".", "ports": ["5000:5000"]},
            },
        }))

        from src.core.services.docker_detect import docker_status
        status = docker_status(tmp_path)
        services = self._bridge(status)

        app = next((s for s in services if s["name"] == "app"), None)
        assert app is not None
        assert app["image"] == "app:latest"

    def test_dockerfile_multistage(self, tmp_path: Path):
        """Multi-stage Dockerfile → bridge uses final stage image name."""
        _write(tmp_path / "Dockerfile",
               "FROM node:20 AS builder\nRUN npm build\n"
               "FROM nginx:alpine\nCOPY --from=builder /app/dist /usr/share/nginx/html\n"
               "EXPOSE 80\n")

        from src.core.services.docker_detect import docker_status
        status = docker_status(tmp_path)
        services = self._bridge(status)

        assert len(services) >= 1
        assert services[0]["port"] == 80

    def test_compose_registry_prefix(self, tmp_path: Path):
        """Compose service with full registry prefix → K8s image matches exactly."""
        _write(tmp_path / "docker-compose.yml", yaml.dump({
            "version": "3.8",
            "services": {
                "api": {"image": "ghcr.io/org/app:v1", "ports": ["8080:8080"]},
            },
        }))

        from src.core.services.docker_detect import docker_status
        status = docker_status(tmp_path)
        services = self._bridge(status)

        api = next((s for s in services if s["name"] == "api"), None)
        assert api is not None
        assert api["image"] == "ghcr.io/org/app:v1"

    def test_compose_build_args(self, tmp_path: Path):
        """Compose build.args → bridge includes them as env_vars or build_args."""
        _write(tmp_path / "Dockerfile", "FROM python:3.12\nARG APP_VERSION\n")
        _write(tmp_path / "docker-compose.yml", yaml.dump({
            "version": "3.8",
            "services": {
                "app": {
                    "build": {
                        "context": ".",
                        "args": {"APP_VERSION": "1.0.0"},
                    },
                    "ports": ["8080:8080"],
                },
            },
        }))

        from src.core.services.docker_detect import docker_status
        status = docker_status(tmp_path)
        services = self._bridge(status)

        app = next((s for s in services if s["name"] == "app"), None)
        assert app is not None
        # Build args should be surfaced (either as env_vars or build_args)
        assert "build_args" in app or "env_vars" in app

    def test_round_trip_docker_first(self, tmp_path: Path):
        """Full round-trip: Docker files → detect → bridge → wizard → K8s resources."""
        _write(tmp_path / "docker-compose.yml", yaml.dump({
            "version": "3.8",
            "services": {
                "api": {"image": "myapi:v2", "ports": ["8080:8080"]},
            },
        }))

        from src.core.services.docker_detect import docker_status
        status = docker_status(tmp_path)
        services = self._bridge(status)

        # Feed into wizard
        wizard_state = {
            "_services": [
                {
                    "name": s["name"],
                    "kind": "Deployment",
                    "image": s["image"],
                    "port": s["port"],
                }
                for s in services
            ],
            "namespace": "default",
        }
        resources = wizard_state_to_resources(wizard_state)

        deploy = _find_resource(resources, "Deployment", "api")
        assert deploy is not None
        assert deploy["spec"]["image"] == "myapi:v2"

        svc = _find_resource(resources, "Service", "api")
        assert svc is not None
        assert svc["spec"]["port"] == 8080

    def test_k8s_first_then_docker(self, tmp_path: Path):
        """K8s with placeholder → Docker added → re-bridge gives real images."""
        # Step 1: K8s with placeholder
        result1 = generate_manifests(tmp_path, "api")
        deploy1 = _find_file(result1, "deployment")
        assert "api:latest" in deploy1["content"]

        # Step 2: Docker comes along
        _write(tmp_path / "docker-compose.yml", yaml.dump({
            "version": "3.8",
            "services": {
                "api": {"image": "ghcr.io/org/api:v3", "ports": ["8080:8080"]},
            },
        }))

        from src.core.services.docker_detect import docker_status
        status = docker_status(tmp_path)
        services = self._bridge(status)

        # Step 3: Re-generate with real image
        api = next((s for s in services if s["name"] == "api"), None)
        assert api is not None
        result2 = generate_manifests(
            tmp_path, "api", image=api["image"], port=api["port"],
        )
        deploy2 = _find_file(result2, "deployment")
        assert "ghcr.io/org/api:v3" in deploy2["content"]
