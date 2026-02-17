"""
Tests for docker_generate — compose from wizard.

Pure unit tests: service list in → {ok, file} with compose YAML content.
No subprocess, no Docker daemon required.
"""

from pathlib import Path

import yaml

from src.core.services.docker_generate import generate_compose_from_wizard


class TestGenerateComposeFromWizard:
    def test_single_service_with_image(self, tmp_path: Path):
        """Single service with image → valid compose YAML."""
        result = generate_compose_from_wizard(tmp_path, [
            {
                "name": "web",
                "image": "nginx:alpine",
                "ports": ["80:80"],
                "restart": "always",
            },
        ])
        assert result["ok"] is True
        assert "file" in result
        content = result["file"]["content"]
        compose = yaml.safe_load(content)
        assert "web" in compose["services"]
        svc = compose["services"]["web"]
        assert svc["image"] == "nginx:alpine"
        assert svc["ports"] == ["80:80"]
        assert svc["restart"] == "always"

    def test_service_with_build_context(self, tmp_path: Path):
        """Service with build context and dockerfile."""
        result = generate_compose_from_wizard(tmp_path, [
            {
                "name": "api",
                "build_context": ".",
                "dockerfile": "Dockerfile.prod",
                "image": "myapp:latest",
                "ports": ["8080:8080"],
            },
        ])
        assert result["ok"] is True
        compose = yaml.safe_load(result["file"]["content"])
        svc = compose["services"]["api"]
        assert svc["build"]["context"] == "."
        assert svc["build"]["dockerfile"] == "Dockerfile.prod"
        assert svc["image"] == "myapp:latest"

    def test_service_with_environment_dict(self, tmp_path: Path):
        """Environment as dict → preserved in compose."""
        result = generate_compose_from_wizard(tmp_path, [
            {
                "name": "api",
                "image": "myapp:latest",
                "environment": {"DB_HOST": "db", "DB_PORT": 5432},
            },
        ])
        compose = yaml.safe_load(result["file"]["content"])
        env = compose["services"]["api"]["environment"]
        assert env["DB_HOST"] == "db"
        assert env["DB_PORT"] == "5432"  # stringified

    def test_multi_service_with_depends_on(self, tmp_path: Path):
        """Multiple services with depends_on and networks."""
        result = generate_compose_from_wizard(tmp_path, [
            {
                "name": "api",
                "image": "myapp:latest",
                "depends_on": ["db", "redis"],
                "networks": ["backend"],
            },
            {
                "name": "db",
                "image": "postgres:16",
                "networks": ["backend"],
            },
            {
                "name": "redis",
                "image": "redis:7",
                "networks": ["backend"],
            },
        ])
        assert result["ok"] is True
        compose = yaml.safe_load(result["file"]["content"])
        assert len(compose["services"]) == 3
        assert compose["services"]["api"]["depends_on"] == ["db", "redis"]
        # Top-level networks should exist
        assert "backend" in compose["networks"]

    def test_service_with_healthcheck(self, tmp_path: Path):
        """Service with healthcheck dict → preserved in compose."""
        result = generate_compose_from_wizard(tmp_path, [
            {
                "name": "api",
                "image": "myapp:latest",
                "healthcheck": {
                    "test": ["CMD", "curl", "-f", "http://localhost:8080/health"],
                    "interval": "30s",
                    "timeout": "10s",
                    "retries": 3,
                },
            },
        ])
        compose = yaml.safe_load(result["file"]["content"])
        hc = compose["services"]["api"]["healthcheck"]
        assert hc["test"] == ["CMD", "curl", "-f", "http://localhost:8080/health"]
        assert hc["retries"] == 3

    def test_build_args(self, tmp_path: Path):
        """Build args are injected into build dict."""
        result = generate_compose_from_wizard(tmp_path, [
            {
                "name": "api",
                "build_context": ".",
                "build_args": {"NODE_ENV": "production", "PORT": 3000},
            },
        ])
        compose = yaml.safe_load(result["file"]["content"])
        args = compose["services"]["api"]["build"]["args"]
        assert args["NODE_ENV"] == "production"
        assert args["PORT"] == "3000"

    def test_empty_services_error(self, tmp_path: Path):
        """Empty service list → error."""
        result = generate_compose_from_wizard(tmp_path, [])
        assert "error" in result

    def test_project_name(self, tmp_path: Path):
        """Project name is set in compose."""
        result = generate_compose_from_wizard(
            tmp_path,
            [{"name": "api", "image": "app:1"}],
            project_name="my-project",
        )
        compose = yaml.safe_load(result["file"]["content"])
        assert compose["name"] == "my-project"

    def test_default_restart_policy(self, tmp_path: Path):
        """Default restart policy is 'unless-stopped'."""
        result = generate_compose_from_wizard(tmp_path, [
            {"name": "api", "image": "app:1"},
        ])
        compose = yaml.safe_load(result["file"]["content"])
        assert compose["services"]["api"]["restart"] == "unless-stopped"

    def test_volumes_as_strings(self, tmp_path: Path):
        """Volumes are preserved as string specs."""
        result = generate_compose_from_wizard(tmp_path, [
            {
                "name": "db",
                "image": "postgres:16",
                "volumes": ["pgdata:/var/lib/postgresql/data"],
            },
        ])
        compose = yaml.safe_load(result["file"]["content"])
        assert compose["services"]["db"]["volumes"] == [
            "pgdata:/var/lib/postgresql/data"
        ]
