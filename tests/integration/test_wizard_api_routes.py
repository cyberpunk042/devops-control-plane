"""
API route tests for wizard endpoints.

Tests the thin HTTP wrappers over core wizard services:
    POST /api/wizard/compose-ci  → compose_ci_workflows()
    POST /api/wizard/validate    → validate_wizard_state()
    GET  /api/wizard/check-tools → check_required_tools()
    DELETE /api/wizard/config    → delete_generated_configs() (skaffold target)
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest


pytestmark = pytest.mark.integration


@pytest.fixture
def client(tmp_path):
    """Flask test client with a temp project root."""
    from src.ui.web.server import create_app

    app = create_app(project_root=tmp_path)
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture
def populated_root(tmp_path):
    """Temp root with generated configs for cleanup tests."""
    (tmp_path / "Dockerfile").write_text("FROM python:3.12\n")
    (tmp_path / "skaffold.yaml").write_text("apiVersion: skaffold/v4\n")
    k8s = tmp_path / "k8s"
    k8s.mkdir()
    (k8s / "deployment.yaml").write_text("apiVersion: apps/v1\n")
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "ci.yml").write_text("name: CI\n")
    tf = tmp_path / "terraform"
    tf.mkdir()
    (tf / "main.tf").write_text("provider \"aws\" {}\n")
    return tmp_path


# ═══════════════════════════════════════════════════════════════════
#  POST /api/wizard/compose-ci
# ═══════════════════════════════════════════════════════════════════


class TestComposeCiEndpoint:
    """POST /api/wizard/compose-ci."""

    def test_compose_unified(self, client):
        """Unified strategy returns single file."""
        resp = client.post("/api/wizard/compose-ci", json={
            "state": {
                "stack_names": ["python"],
                "docker_services": [
                    {"name": "api", "image": "api:latest",
                     "registry": "ghcr.io/org", "registry_type": "ghcr"},
                ],
                "deploy_config": {"method": "kubectl"},
            },
            "strategy": "unified",
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"]
        assert len(data["files"]) == 1
        assert data["files"][0]["path"].endswith(".yml")
        assert "content" in data["files"][0]

    def test_compose_split(self, client):
        """Split strategy returns multiple files."""
        resp = client.post("/api/wizard/compose-ci", json={
            "state": {
                "stack_names": ["python"],
                "docker_services": [
                    {"name": "api", "image": "api:latest",
                     "registry": "ghcr.io/org", "registry_type": "ghcr"},
                ],
                "deploy_config": {"method": "kubectl"},
            },
            "strategy": "split",
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"]
        assert len(data["files"]) >= 2

    def test_compose_empty_state(self, client):
        """Empty state → ok with empty files list."""
        resp = client.post("/api/wizard/compose-ci", json={"state": {}})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"]
        assert data["files"] == []

    def test_compose_no_body(self, client):
        """No request body → 400."""
        resp = client.post("/api/wizard/compose-ci")
        assert resp.status_code == 400

    def test_compose_with_project_name(self, client):
        """project_name flows through."""
        resp = client.post("/api/wizard/compose-ci", json={
            "state": {
                "docker_services": [
                    {"name": "api", "image": "api:latest",
                     "registry": "ghcr.io/org", "registry_type": "ghcr"},
                ],
                "deploy_config": {"method": "kubectl"},
            },
            "project_name": "MyProject",
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"]
        # project_name should appear in the workflow name
        assert any("MyProject" in f["content"] for f in data["files"])


# ═══════════════════════════════════════════════════════════════════
#  POST /api/wizard/validate
# ═══════════════════════════════════════════════════════════════════


class TestValidateEndpoint:
    """POST /api/wizard/validate."""

    def test_valid_state(self, client):
        """Valid state → ok."""
        resp = client.post("/api/wizard/validate", json={
            "state": {
                "deploy_config": {"method": "kubectl", "namespace": "default"},
                "_skip_secret_warnings": True,
            },
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"]

    def test_invalid_namespace(self, client):
        """Invalid namespace → error."""
        resp = client.post("/api/wizard/validate", json={
            "state": {
                "deploy_config": {"namespace": "BAD_NS!!"},
            },
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert not data["ok"]
        assert len(data["errors"]) > 0

    def test_malformed_registry(self, client):
        """Malformed registry → error."""
        resp = client.post("/api/wizard/validate", json={
            "state": {
                "docker_services": [
                    {"name": "api", "registry": "not valid!!!"},
                ],
            },
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert not data["ok"]

    def test_warnings_returned(self, client):
        """Warnings returned alongside ok status."""
        resp = client.post("/api/wizard/validate", json={
            "state": {
                "deploy_config": {"method": "kubectl"},
            },
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"]
        assert len(data["warnings"]) > 0

    def test_no_body(self, client):
        """No request body → 400."""
        resp = client.post("/api/wizard/validate")
        assert resp.status_code == 400


# ═══════════════════════════════════════════════════════════════════
#  GET /api/wizard/check-tools
# ═══════════════════════════════════════════════════════════════════


class TestCheckToolsEndpoint:
    """GET /api/wizard/check-tools."""

    def test_check_tools_with_state(self, client):
        """Returns tool status for given state."""
        resp = client.post("/api/wizard/check-tools", json={
            "state": {
                "docker_services": [{"name": "api"}],
                "deploy_config": {"method": "helm"},
            },
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert "tools" in data
        assert "missing" in data
        assert "install_available" in data
        assert isinstance(data["ok"], bool)

    def test_check_tools_empty_state(self, client):
        """Empty state → ok, no tools required."""
        resp = client.post("/api/wizard/check-tools", json={
            "state": {},
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"]
        assert data["missing"] == []

    def test_check_tools_no_body(self, client):
        """No request body → 400."""
        resp = client.post("/api/wizard/check-tools")
        assert resp.status_code == 400


# ═══════════════════════════════════════════════════════════════════
#  DELETE /api/wizard/config — skaffold target
# ═══════════════════════════════════════════════════════════════════


class TestDeleteConfigSkaffold:
    """DELETE /api/wizard/config with skaffold target."""

    def test_delete_skaffold(self, tmp_path):
        """Skaffold target removes skaffold.yaml via API."""
        from src.ui.web.server import create_app

        (tmp_path / "skaffold.yaml").write_text("apiVersion: skaffold/v4\n")
        (tmp_path / "Dockerfile").write_text("FROM python:3.12\n")

        app = create_app(project_root=tmp_path)
        app.config["TESTING"] = True
        with app.test_client() as c:
            resp = c.delete("/api/wizard/config", json={"target": "skaffold"})
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["ok"]
            assert "skaffold.yaml" in data["deleted"]
            # Docker untouched
            assert (tmp_path / "Dockerfile").exists()
            assert not (tmp_path / "skaffold.yaml").exists()
