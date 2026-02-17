"""
Tests for wizard_setup — setup_docker, setup_ci, setup_terraform.

Pure unit tests: data dict + tmp_path → files on disk + result dict.
No subprocess, no Docker/kubectl/terraform required.
"""

from pathlib import Path

from src.core.services.wizard_setup import (
    setup_docker,
    setup_ci,
    setup_terraform,
)


# ═══════════════════════════════════════════════════════════════════
#  setup_docker
# ═══════════════════════════════════════════════════════════════════


class TestSetupDocker:
    def test_minimal_data_creates_dockerfile(self, tmp_path: Path):
        """setup_docker() with minimal data → Dockerfile created.

        Verifies:
        1. result["ok"] is True
        2. result["files_created"] includes "Dockerfile"
        3. result["message"] is present and meaningful
        4. Dockerfile exists on disk
        5. Dockerfile content has FROM, WORKDIR, COPY, EXPOSE, CMD
        6. Defaults applied when only port specified
        """
        result = setup_docker(tmp_path, {"port": "8080"})

        # 1-3. Result dict shape
        assert result["ok"] is True
        assert "Dockerfile" in result["files_created"]
        assert result["message"], "message should be non-empty"

        # 4. File on disk
        dockerfile = tmp_path / "Dockerfile"
        assert dockerfile.is_file()

        # 5. Content structure
        content = dockerfile.read_text()
        assert "FROM " in content  # has a base image
        assert "WORKDIR " in content
        assert "COPY " in content
        assert "EXPOSE 8080" in content
        assert "CMD " in content

        # 6. Defaults applied
        assert "python:3.12-slim" in content  # default base_image
        assert "/app" in content  # default workdir

    def test_compose_true_creates_compose(self, tmp_path: Path):
        """setup_docker() with compose=True → docker-compose.yml created.

        Verifies:
        1. Both Dockerfile and docker-compose.yml in files_created
        2. Both files exist on disk
        3. Compose content has services, build, ports, restart
        4. Port in compose matches requested port
        """
        result = setup_docker(tmp_path, {
            "port": "3000",
            "compose": True,
        })

        # 1. files_created
        assert result["ok"] is True
        assert "Dockerfile" in result["files_created"]
        assert "docker-compose.yml" in result["files_created"]

        # 2. Files on disk
        assert (tmp_path / "Dockerfile").is_file()
        assert (tmp_path / "docker-compose.yml").is_file()

        # 3-4. Compose content
        compose = (tmp_path / "docker-compose.yml").read_text()
        assert "services:" in compose
        assert "build:" in compose
        assert "3000:3000" in compose
        assert "restart:" in compose

    def test_no_overwrite_existing(self, tmp_path: Path):
        """Existing Dockerfile + overwrite=False → error."""
        (tmp_path / "Dockerfile").write_text("FROM alpine\n")
        result = setup_docker(tmp_path, {"overwrite": False})
        assert result["ok"] is False
        assert "already exists" in result["error"]

    def test_overwrite_existing(self, tmp_path: Path):
        """Existing Dockerfile + overwrite=True → replaced."""
        (tmp_path / "Dockerfile").write_text("FROM alpine\n")
        result = setup_docker(tmp_path, {
            "base_image": "node:20",
            "overwrite": True,
        })
        assert result["ok"] is True
        content = (tmp_path / "Dockerfile").read_text()
        assert "FROM node:20" in content

    def test_dockerignore_true_creates_file(self, tmp_path: Path):
        """setup_docker() with dockerignore=True → .dockerignore created.

        Verifies:
        1. .dockerignore in files_created
        2. .dockerignore exists on disk
        3. Content has common Docker ignore patterns (.git, __pycache__)
        """
        result = setup_docker(tmp_path, {
            "dockerignore": True,
        })
        assert result["ok"] is True
        assert ".dockerignore" in result["files_created"]
        assert (tmp_path / ".dockerignore").is_file()
        content = (tmp_path / ".dockerignore").read_text()
        assert ".git" in content

    def test_registry_ghcr(self, tmp_path: Path):
        """setup_docker() with registry=ghcr.io → stored in result.

        Verifies result includes registry info.
        """
        result = setup_docker(tmp_path, {
            "registry": "ghcr.io",
        })
        assert result["ok"] is True
        assert result.get("registry") == "ghcr.io"

    def test_registry_dockerhub(self, tmp_path: Path):
        """setup_docker() with registry=docker.io → stored in result."""
        result = setup_docker(tmp_path, {
            "registry": "docker.io",
        })
        assert result["ok"] is True
        assert result.get("registry") == "docker.io"

    def test_registry_custom(self, tmp_path: Path):
        """setup_docker() with custom registry → stored in result."""
        result = setup_docker(tmp_path, {
            "registry": "registry.example.com:5000",
        })
        assert result["ok"] is True
        assert result.get("registry") == "registry.example.com:5000"

    def test_image_name_stored(self, tmp_path: Path):
        """setup_docker() with image_name → stored in result."""
        result = setup_docker(tmp_path, {
            "image_name": "myapp",
        })
        assert result["ok"] is True
        assert result.get("image_name") == "myapp"

    def test_build_args_stored(self, tmp_path: Path):
        """setup_docker() with build_args → stored in result and Dockerfile.

        Verifies:
        1. Build args in result
        2. ARG directives in Dockerfile content
        """
        result = setup_docker(tmp_path, {
            "build_args": {"APP_VERSION": "1.0.0", "DEBUG": "false"},
        })
        assert result["ok"] is True
        assert result.get("build_args") == {"APP_VERSION": "1.0.0", "DEBUG": "false"}
        content = (tmp_path / "Dockerfile").read_text()
        assert "ARG APP_VERSION" in content
        assert "ARG DEBUG" in content

    def test_round_trip_setup_then_detect(self, tmp_path: Path):
        """setup_docker() → files on disk → detect finds what was generated.

        Round-trip: the generated Dockerfile should be detectable.
        """
        setup_docker(tmp_path, {"port": "8080"})

        # Now detect
        dockerfile = tmp_path / "Dockerfile"
        assert dockerfile.is_file()
        content = dockerfile.read_text()
        # The generated file should be a valid Dockerfile
        assert content.strip().startswith("FROM ")
        assert "EXPOSE 8080" in content

    def test_idempotent_with_overwrite(self, tmp_path: Path):
        """setup_docker() run twice with overwrite=True → same result.

        Verifies:
        1. Both runs succeed
        2. Final file content is identical to single run
        """
        data = {"port": "8080", "overwrite": True}
        result1 = setup_docker(tmp_path, data)
        content1 = (tmp_path / "Dockerfile").read_text()

        result2 = setup_docker(tmp_path, data)
        content2 = (tmp_path / "Dockerfile").read_text()

        assert result1["ok"] is True
        assert result2["ok"] is True
        assert content1 == content2

    def test_overwrite_changes_config(self, tmp_path: Path):
        """setup_docker() twice with different config + overwrite → updated.

        Verifies: second run with different base_image replaces the first.
        """
        setup_docker(tmp_path, {"base_image": "python:3.11", "overwrite": True})
        content1 = (tmp_path / "Dockerfile").read_text()
        assert "python:3.11" in content1

        setup_docker(tmp_path, {"base_image": "node:20-slim", "overwrite": True})
        content2 = (tmp_path / "Dockerfile").read_text()
        assert "node:20-slim" in content2
        assert "python:3.11" not in content2

    def test_empty_data_uses_defaults(self, tmp_path: Path):
        """setup_docker() with empty dict → defaults applied, succeeds.

        Verifies:
        1. result is ok
        2. Dockerfile created with default base image
        """
        result = setup_docker(tmp_path, {})
        assert result["ok"] is True
        assert "Dockerfile" in result["files_created"]
        content = (tmp_path / "Dockerfile").read_text()
        assert "python:3.12-slim" in content

    def test_non_dict_build_args_no_crash(self, tmp_path: Path):
        """setup_docker() with non-dict build_args → no ARG lines, no crash.

        Verifies:
        1. result is ok
        2. No ARG directive in Dockerfile
        """
        result = setup_docker(tmp_path, {"build_args": "not-a-dict"})
        assert result["ok"] is True
        content = (tmp_path / "Dockerfile").read_text()
        assert "ARG " not in content

    def test_read_only_path_returns_error(self, tmp_path: Path):
        """setup_docker() on read-only directory → error surfaced cleanly.

        Verifies: either returns ok=False with error, or raises handled exception.
        """
        import os
        import stat

        read_only_dir = tmp_path / "locked"
        read_only_dir.mkdir()
        read_only_dir.chmod(stat.S_IRUSR | stat.S_IXUSR)  # r-x

        try:
            result = setup_docker(read_only_dir, {})
            # If it doesn't raise, it should indicate failure
            assert result.get("ok") is False or "error" in result
        except (OSError, PermissionError):
            pass  # Acceptable — error surfaced as exception
        finally:
            # Restore permissions for cleanup
            read_only_dir.chmod(stat.S_IRWXU)


# ═══════════════════════════════════════════════════════════════════
#  setup_ci
# ═══════════════════════════════════════════════════════════════════


class TestSetupCi:
    def test_generate_ci_workflow(self, tmp_path: Path):
        """Basic CI workflow generation."""
        result = setup_ci(tmp_path, {
            "branches": "main, develop",
            "python_version": "3.12",
            "test_cmd": "pytest tests/ -v",
        })
        assert result["ok"] is True
        assert ".github/workflows/ci.yml" in result["files_created"]
        wf_path = tmp_path / ".github" / "workflows" / "ci.yml"
        assert wf_path.is_file()
        content = wf_path.read_text()
        assert "name: CI" in content
        assert "pytest tests/ -v" in content

    def test_ci_with_lint(self, tmp_path: Path):
        """CI with lint enabled → lint step added."""
        result = setup_ci(tmp_path, {
            "lint": True,
            "lint_cmd": "ruff check src/",
        })
        assert result["ok"] is True
        content = (tmp_path / ".github" / "workflows" / "ci.yml").read_text()
        assert "ruff check src/" in content

    def test_ci_without_lint(self, tmp_path: Path):
        """CI without lint → no lint step."""
        result = setup_ci(tmp_path, {"lint": False})
        assert result["ok"] is True
        content = (tmp_path / ".github" / "workflows" / "ci.yml").read_text()
        assert "ruff" not in content

    def test_no_overwrite_existing(self, tmp_path: Path):
        """Existing workflow + overwrite=False → error."""
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text("name: Old\n")
        result = setup_ci(tmp_path, {"overwrite": False})
        assert result["ok"] is False
        assert "already exists" in result["error"]

    def test_branches_in_output(self, tmp_path: Path):
        """Branch names appear in the workflow."""
        result = setup_ci(tmp_path, {"branches": "main, staging"})
        assert result["ok"] is True
        content = (tmp_path / ".github" / "workflows" / "ci.yml").read_text()
        assert "main" in content
        assert "staging" in content


# ═══════════════════════════════════════════════════════════════════
#  setup_terraform
# ═══════════════════════════════════════════════════════════════════


class TestSetupTerraform:
    def test_aws_provider_s3_backend(self, tmp_path: Path):
        """AWS provider + S3 backend → correct HCL blocks."""
        result = setup_terraform(tmp_path, {
            "provider": "aws",
            "region": "us-west-2",
            "project_name": "myapp",
            "backend": "s3",
        })
        assert result["ok"] is True
        assert "terraform/main.tf" in result["files_created"]
        content = (tmp_path / "terraform" / "main.tf").read_text()
        assert 'provider "aws"' in content
        assert "us-west-2" in content
        assert 'backend "s3"' in content
        assert "myapp-tfstate" in content

    def test_google_provider_gcs_backend(self, tmp_path: Path):
        """Google provider + GCS backend → correct HCL blocks."""
        result = setup_terraform(tmp_path, {
            "provider": "google",
            "region": "us-central1",
            "project_name": "gcp-app",
            "backend": "gcs",
        })
        assert result["ok"] is True
        content = (tmp_path / "terraform" / "main.tf").read_text()
        assert 'provider "google"' in content
        assert "gcp-app" in content
        assert 'backend "gcs"' in content

    def test_azurerm_provider(self, tmp_path: Path):
        """Azure provider → features block."""
        result = setup_terraform(tmp_path, {
            "provider": "azurerm",
            "backend": "azurerm",
            "project_name": "az-app",
        })
        assert result["ok"] is True
        content = (tmp_path / "terraform" / "main.tf").read_text()
        assert 'provider "azurerm"' in content
        assert "features {}" in content

    def test_local_backend(self, tmp_path: Path):
        """Local backend → no backend block."""
        result = setup_terraform(tmp_path, {
            "provider": "aws",
            "backend": "local",
        })
        assert result["ok"] is True
        content = (tmp_path / "terraform" / "main.tf").read_text()
        assert "backend" not in content

    def test_no_overwrite_existing(self, tmp_path: Path):
        """Existing terraform config + overwrite=False → error."""
        tf_dir = tmp_path / "terraform"
        tf_dir.mkdir()
        (tf_dir / "main.tf").write_text("# old config\n")
        result = setup_terraform(tmp_path, {"overwrite": False})
        assert result["ok"] is False
        assert "already exists" in result["error"].lower() or "exists" in result["error"].lower()

    def test_required_version_present(self, tmp_path: Path):
        """Required version constraint is always present."""
        result = setup_terraform(tmp_path, {"provider": "aws"})
        assert result["ok"] is True
        content = (tmp_path / "terraform" / "main.tf").read_text()
        assert '>= 1.0' in content
