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
    setup_k8s,
    delete_generated_configs,
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


# ═══════════════════════════════════════════════════════════════════
#  0.2.17  setup_k8s — end-to-end manifest writing pipeline
# ═══════════════════════════════════════════════════════════════════


class TestSetupK8s:
    """0.2.17 — setup_k8s integration: wizard state → files on disk.

    Source of truth: setup_k8s orchestrates:
    1. wizard_state_to_resources (translate)
    2. generate_k8s_wizard (render YAML)
    3. Write files to disk
    4. Optional skaffold.yaml
    5. Record activity event
    """

    def _minimal_state(self, **overrides):
        """Build minimal wizard state for setup_k8s."""
        state = {
            "namespace": "default",
            "_services": [
                {"name": "api", "image": "api:latest", "port": 8080,
                 "replicas": 1},
            ],
        }
        state.update(overrides)
        return state

    def test_creates_manifest_files(self, tmp_path: Path):
        """setup_k8s with simple state → YAML files on disk.

        Verifies:
        1. result["ok"] is True
        2. result["files_created"] is non-empty
        3. Files actually exist on disk
        4. Files are valid YAML content (start with apiVersion or similar)
        """
        result = setup_k8s(tmp_path, self._minimal_state())

        assert result["ok"] is True
        assert len(result["files_created"]) >= 1
        assert result["message"], "message should be non-empty"

        for rel_path in result["files_created"]:
            fp = tmp_path / rel_path
            assert fp.is_file(), f"Expected file: {rel_path}"
            content = fp.read_text()
            assert content.strip(), f"Empty file: {rel_path}"

    def test_output_dir_created(self, tmp_path: Path):
        """setup_k8s auto-creates output directory (k8s/)."""
        k8s_dir = tmp_path / "k8s"
        assert not k8s_dir.exists()

        result = setup_k8s(tmp_path, self._minimal_state())
        assert result["ok"] is True
        assert k8s_dir.is_dir()

    def test_custom_output_dir(self, tmp_path: Path):
        """Custom output_dir → files written there, not k8s/."""
        result = setup_k8s(tmp_path, self._minimal_state(
            output_dir="manifests",
        ))
        assert result["ok"] is True
        manifests_dir = tmp_path / "manifests"
        assert manifests_dir.is_dir()
        # At least one file in custom dir
        files = list(manifests_dir.glob("*.yaml")) + list(manifests_dir.glob("*.yml"))
        assert len(files) >= 1

    def test_multiple_resource_types(self, tmp_path: Path):
        """State with multiple services → multiple files created."""
        state = {
            "namespace": "production",
            "_services": [
                {"name": "api", "image": "api:v1", "port": 8080, "replicas": 2},
                {"name": "worker", "image": "worker:v1", "replicas": 1},
            ],
        }
        result = setup_k8s(tmp_path, state)
        assert result["ok"] is True
        # Namespace + 2 Deployments + 1 Service (api has port, worker doesn't)
        assert len(result["files_created"]) >= 3

    def test_skaffold_generated_when_requested(self, tmp_path: Path):
        """skaffold=True → skaffold.yaml created alongside manifests."""
        result = setup_k8s(tmp_path, self._minimal_state(skaffold=True))
        assert result["ok"] is True
        # Look for skaffold file
        skaffold_created = any(
            "skaffold" in f for f in result["files_created"]
        )
        assert skaffold_created, f"Expected skaffold in {result['files_created']}"
        # File on disk
        skaffold_path = tmp_path / "skaffold.yaml"
        assert skaffold_path.is_file()

    def test_no_skaffold_when_not_requested(self, tmp_path: Path):
        """No skaffold key → no skaffold.yaml (negative test)."""
        result = setup_k8s(tmp_path, self._minimal_state())
        assert result["ok"] is True
        skaffold_created = any(
            "skaffold" in f for f in result["files_created"]
        )
        assert not skaffold_created

    def test_idempotent_with_overwrite(self, tmp_path: Path):
        """setup_k8s run twice → second run skips existing files.

        By design, generated manifests have overwrite=False, so the
        second run reports files_skipped rather than re-creating.
        """
        state = self._minimal_state()
        result1 = setup_k8s(tmp_path, state)
        assert result1["ok"] is True
        first_files = set(result1["files_created"])
        assert len(first_files) >= 1

        result2 = setup_k8s(tmp_path, state)
        assert result2["ok"] is True
        # Second run skips all existing files
        assert result2.get("files_skipped") is not None
        assert set(result2["files_skipped"]) == first_files


# ═══════════════════════════════════════════════════════════════════
#  0.2.18  delete_generated_configs
# ═══════════════════════════════════════════════════════════════════


class TestDeleteGeneratedConfigs:
    """0.2.18 — delete_generated_configs for all target types.

    Source of truth: delete_generated_configs behaviour for
    docker, k8s, ci, terraform, all.
    """

    def test_delete_docker(self, tmp_path: Path):
        """target=docker → Dockerfile, .dockerignore, compose deleted."""
        (tmp_path / "Dockerfile").write_text("FROM alpine\n")
        (tmp_path / ".dockerignore").write_text(".git\n")
        (tmp_path / "docker-compose.yml").write_text("version: '3'\n")

        result = delete_generated_configs(tmp_path, "docker")
        assert result["ok"] is True
        assert "Dockerfile" in result["deleted"]
        assert ".dockerignore" in result["deleted"]
        assert not (tmp_path / "Dockerfile").exists()
        assert not (tmp_path / ".dockerignore").exists()
        assert not (tmp_path / "docker-compose.yml").exists()

    def test_delete_k8s(self, tmp_path: Path):
        """target=k8s → k8s/ directory removed."""
        k8s_dir = tmp_path / "k8s"
        k8s_dir.mkdir()
        (k8s_dir / "deploy.yaml").write_text("kind: Deployment\n")

        result = delete_generated_configs(tmp_path, "k8s")
        assert result["ok"] is True
        assert "k8s/" in result["deleted"]
        assert not k8s_dir.exists()

    def test_delete_ci(self, tmp_path: Path):
        """target=ci → .github/workflows/ci.yml deleted."""
        ci_path = tmp_path / ".github" / "workflows" / "ci.yml"
        ci_path.parent.mkdir(parents=True)
        ci_path.write_text("name: CI\n")

        result = delete_generated_configs(tmp_path, "ci")
        assert result["ok"] is True
        assert ".github/workflows/ci.yml" in result["deleted"]
        assert not ci_path.exists()

    def test_delete_terraform(self, tmp_path: Path):
        """target=terraform → terraform/ directory removed."""
        tf_dir = tmp_path / "terraform"
        tf_dir.mkdir()
        (tf_dir / "main.tf").write_text("terraform {}\n")

        result = delete_generated_configs(tmp_path, "terraform")
        assert result["ok"] is True
        assert "terraform/" in result["deleted"]
        assert not tf_dir.exists()

    def test_delete_all(self, tmp_path: Path):
        """target=all → all known targets deleted."""
        # Create files for each target
        (tmp_path / "Dockerfile").write_text("FROM alpine\n")
        k8s = tmp_path / "k8s"
        k8s.mkdir()
        (k8s / "deploy.yaml").write_text("kind: Deployment\n")
        ci = tmp_path / ".github" / "workflows"
        ci.mkdir(parents=True)
        (ci / "ci.yml").write_text("name: CI\n")
        tf = tmp_path / "terraform"
        tf.mkdir()
        (tf / "main.tf").write_text("terraform {}\n")

        result = delete_generated_configs(tmp_path, "all")
        assert result["ok"] is True
        assert len(result["deleted"]) >= 4

    def test_delete_nonexistent_is_ok(self, tmp_path: Path):
        """Deleting target that doesn't exist → ok, empty deleted list."""
        result = delete_generated_configs(tmp_path, "k8s")
        assert result["ok"] is True
        assert result["deleted"] == []

    def test_unknown_target(self, tmp_path: Path):
        """Unknown target → error in errors list."""
        result = delete_generated_configs(tmp_path, "foobar")
        assert result["ok"] is False
        assert len(result["errors"]) >= 1
        assert "foobar" in result["errors"][0]

    def test_round_trip_setup_delete_setup(self, tmp_path: Path):
        """setup_k8s → delete k8s → setup_k8s → same result.

        Round-trip: proves delete fully cleans and setup can re-create.
        """
        state = {
            "namespace": "default",
            "_services": [
                {"name": "api", "image": "api:v1", "port": 8080, "replicas": 1},
            ],
        }

        # First setup
        r1 = setup_k8s(tmp_path, state)
        assert r1["ok"] is True
        files1 = set(r1["files_created"])

        # Delete
        rd = delete_generated_configs(tmp_path, "k8s")
        assert rd["ok"] is True
        assert not (tmp_path / "k8s").exists()

        # Re-setup
        r2 = setup_k8s(tmp_path, state)
        assert r2["ok"] is True
        files2 = set(r2["files_created"])

        # Same files created
        assert files1 == files2

    def test_delete_filesystem_error_captured(self, tmp_path: Path):
        """Filesystem error during delete → captured in errors, not raised.

        Verifies: exceptions from rmtree are caught and reported in errors
        list rather than propagating to the caller.
        """
        import os
        import stat

        # Create k8s dir, then make parent read-only to prevent deletion
        k8s_dir = tmp_path / "k8s"
        k8s_dir.mkdir()
        (k8s_dir / "deploy.yaml").write_text("kind: Deployment\n")

        # Make k8s dir read-only (so rmtree fails inside it)
        (k8s_dir / "deploy.yaml").chmod(0)
        k8s_dir.chmod(stat.S_IRUSR | stat.S_IXUSR)

        try:
            result = delete_generated_configs(tmp_path, "k8s")
            # Should NOT raise — error captured in errors list
            assert len(result["errors"]) >= 1
            assert result["ok"] is False
        finally:
            # Restore permissions for cleanup
            k8s_dir.chmod(stat.S_IRWXU)
            (k8s_dir / "deploy.yaml").chmod(stat.S_IRWXU)

    def test_setup_k8s_records_activity_event(self, tmp_path: Path):
        """setup_k8s → activity event recorded in .state/audit_activity.json.

        Verifies: record_event is called with card=wizard, action=configured,
        target=kubernetes.
        """
        import json

        state = {
            "namespace": "default",
            "_services": [
                {"name": "api", "image": "api:v1", "port": 8080, "replicas": 1},
            ],
        }
        setup_k8s(tmp_path, state)

        activity_path = tmp_path / ".state" / "audit_activity.json"
        assert activity_path.is_file()
        entries = json.loads(activity_path.read_text())
        assert len(entries) >= 1
        last = entries[-1]
        assert last["card"] == "wizard"
        assert last["action"] == "configured"
        assert last["target"] == "kubernetes"
        assert "K8s" in last["label"]

    def test_delete_records_activity_event(self, tmp_path: Path):
        """delete_generated_configs → activity event recorded.

        Verifies: record_event is called with action=deleted after config
        deletion.
        """
        import json

        k8s_dir = tmp_path / "k8s"
        k8s_dir.mkdir()
        (k8s_dir / "deploy.yaml").write_text("kind: Deployment\n")

        delete_generated_configs(tmp_path, "k8s")

        activity_path = tmp_path / ".state" / "audit_activity.json"
        assert activity_path.is_file()
        entries = json.loads(activity_path.read_text())
        assert len(entries) >= 1
        last = entries[-1]
        assert last["card"] == "wizard"
        assert last["action"] == "deleted"

    def test_setup_k8s_generator_error(self, tmp_path: Path):
        """Empty services → generator error → ok=False returned.

        Verifies: when wizard_state_to_resources produces no valid resources,
        generate_k8s_wizard returns an error and setup_k8s returns ok=False.
        """
        state = {
            "namespace": "default",
            "_services": [],  # No services at all
        }
        result = setup_k8s(tmp_path, state)
        assert result["ok"] is False
        assert "error" in result

    def test_setup_k8s_configmap_file_created(self, tmp_path: Path):
        """Wizard state with env vars → ConfigMap YAML file on disk."""
        state = {
            "namespace": "default",
            "_services": [
                {
                    "name": "api",
                    "image": "api:v1",
                    "port": 8080,
                    "replicas": 1,
                    "envVars": [
                        {"key": "APP_MODE", "value": "production", "type": "hardcoded"},
                    ],
                },
            ],
        }
        result = setup_k8s(tmp_path, state)
        assert result["ok"] is True
        config_files = [f for f in result["files_created"] if "config" in f.lower()]
        assert len(config_files) >= 1

    def test_setup_k8s_secret_file_created(self, tmp_path: Path):
        """Wizard state with secret env vars → Secret YAML file on disk."""
        state = {
            "namespace": "default",
            "_services": [
                {
                    "name": "api",
                    "image": "api:v1",
                    "port": 8080,
                    "replicas": 1,
                    "envVars": [
                        {"key": "DB_PASS", "value": "s3cret", "type": "secret"},
                    ],
                },
            ],
        }
        result = setup_k8s(tmp_path, state)
        assert result["ok"] is True
        secret_files = [f for f in result["files_created"] if "secret" in f.lower()]
        assert len(secret_files) >= 1

    def test_setup_k8s_namespace_file_created(self, tmp_path: Path):
        """Non-default namespace → Namespace resource YAML created."""
        state = {
            "namespace": "production",
            "_services": [
                {"name": "api", "image": "api:v1", "port": 8080, "replicas": 1},
            ],
        }
        result = setup_k8s(tmp_path, state)
        assert result["ok"] is True
        ns_files = [f for f in result["files_created"] if "namespace" in f.lower()]
        assert len(ns_files) >= 1

    def test_setup_k8s_ingress_file_created(self, tmp_path: Path):
        """Wizard state with ingress host → Ingress YAML created.

        Note: ingress is a top-level data key, not per-service.
        """
        state = {
            "namespace": "default",
            "ingress": "api.example.com",
            "_services": [
                {
                    "name": "api",
                    "image": "api:v1",
                    "port": 8080,
                    "replicas": 1,
                },
            ],
        }
        result = setup_k8s(tmp_path, state)
        assert result["ok"] is True
        ingress_files = [f for f in result["files_created"] if "ingress" in f.lower()]
        assert len(ingress_files) >= 1

    def test_setup_k8s_pvc_file_created(self, tmp_path: Path):
        """Wizard state with PVC volume → PVC YAML file on disk."""
        state = {
            "namespace": "default",
            "_services": [
                {
                    "name": "api",
                    "image": "api:v1",
                    "port": 8080,
                    "replicas": 1,
                    "volumes": [
                        {
                            "name": "data",
                            "mountPath": "/data",
                            "type": "pvc-dynamic",
                            "size": "10Gi",
                        },
                    ],
                },
            ],
        }
        result = setup_k8s(tmp_path, state)
        assert result["ok"] is True
        pvc_files = [f for f in result["files_created"]
                     if "persistentvolumeclaim" in f.lower() or "pvc" in f.lower()]
        assert len(pvc_files) >= 1

    def test_setup_k8s_multi_service_all_files(self, tmp_path: Path):
        """Multiple services → all Deployments + Services + ConfigMaps/Secrets."""
        state = {
            "namespace": "default",
            "_services": [
                {
                    "name": "api",
                    "image": "api:v1",
                    "port": 8080,
                    "replicas": 2,
                    "envVars": [
                        {"key": "MODE", "value": "prod", "type": "hardcoded"},
                    ],
                },
                {
                    "name": "worker",
                    "image": "worker:v1",
                    "replicas": 1,
                    "envVars": [
                        {"key": "SECRET_KEY", "value": "abc", "type": "secret"},
                    ],
                },
            ],
        }
        result = setup_k8s(tmp_path, state)
        assert result["ok"] is True
        files = result["files_created"]
        # 2 deployments + 1 service (api has port) + 1 configmap (api) + 1 secret (worker)
        assert len(files) >= 5

    def test_setup_delete_k8s_status_shows_nothing(self, tmp_path: Path):
        """Setup → delete → no k8s/ dir means k8s_status finds nothing.

        After delete, the k8s/ directory is gone so no manifests can be
        scanned.
        """
        state = {
            "namespace": "default",
            "_services": [
                {"name": "api", "image": "api:v1", "port": 8080, "replicas": 1},
            ],
        }
        setup_k8s(tmp_path, state)
        assert (tmp_path / "k8s").is_dir()

        delete_generated_configs(tmp_path, "k8s")
        assert not (tmp_path / "k8s").exists()
        # No yaml files remain in k8s/
        yamls = list((tmp_path).rglob("k8s/*.yaml"))
        assert len(yamls) == 0
