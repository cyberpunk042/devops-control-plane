"""
Tests for web admin — app factory, API routes, dashboard.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from flask.testing import FlaskClient

from src.ui.web.server import create_app


@pytest.fixture()
def project_dir(tmp_path: Path) -> Path:
    """Create a test project directory with config and stacks."""
    config = tmp_path / "project.yml"
    config.write_text(textwrap.dedent("""\
        name: web-test-project
        description: A test project for the web admin.
        modules:
          - name: api
            path: src/api
            stack: python
          - name: web
            path: src/web
            stack: python
        environments:
          - name: dev
            default: true
          - name: production
    """))

    # Create module dirs
    for mod in ["api", "web"]:
        d = tmp_path / "src" / mod
        d.mkdir(parents=True)
        (d / "pyproject.toml").write_text(f'[project]\nname = "{mod}"\n')

    # Stack definition
    stack_dir = tmp_path / "stacks" / "python"
    stack_dir.mkdir(parents=True)
    (stack_dir / "stack.yml").write_text(textwrap.dedent("""\
        name: python
        detection:
          files_any_of:
            - pyproject.toml
        capabilities:
          - name: test
            command: "echo tests passed"
          - name: lint
            command: "echo lint ok"
    """))

    return tmp_path


@pytest.fixture()
def client(project_dir: Path) -> FlaskClient:
    """Create a Flask test client."""
    config_path = project_dir / "project.yml"
    app = create_app(
        project_root=project_dir,
        config_path=config_path,
        mock_mode=True,
    )
    app.config["TESTING"] = True
    return app.test_client()


# ── App Factory Tests ────────────────────────────────────────────────


class TestAppFactory:
    def test_create_app(self, project_dir: Path):
        config_path = project_dir / "project.yml"
        app = create_app(
            project_root=project_dir,
            config_path=config_path,
        )
        assert app is not None
        assert app.config["PROJECT_ROOT"] == str(project_dir)

    def test_create_app_mock_mode(self, project_dir: Path):
        app = create_app(project_root=project_dir, mock_mode=True)
        assert app.config["MOCK_MODE"] is True


# ── Dashboard Tests ──────────────────────────────────────────────────


class TestDashboard:
    def test_dashboard_loads(self, client: FlaskClient):
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"Control Plane" in resp.data
        assert b"dashboard" in resp.data.lower()

    def test_dashboard_has_css(self, client: FlaskClient):
        resp = client.get("/")
        assert b"admin.css" in resp.data

    def test_static_css(self, client: FlaskClient):
        resp = client.get("/static/css/admin.css")
        assert resp.status_code == 200
        assert b"--bg-primary" in resp.data


# ── API Status Tests ─────────────────────────────────────────────────


class TestApiStatus:
    def test_status_returns_json(self, client: FlaskClient):
        resp = client.get("/api/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "project" in data
        assert "modules" in data
        assert "state" in data

    def test_status_project_info(self, client: FlaskClient):
        data = client.get("/api/status").get_json()
        assert data["project"]["name"] == "web-test-project"
        assert data["project"]["description"] == "A test project for the web admin."

    def test_status_modules(self, client: FlaskClient):
        data = client.get("/api/status").get_json()
        modules = data["modules"]
        assert len(modules) == 2
        names = {m["name"] for m in modules}
        assert names == {"api", "web"}

    def test_status_environments(self, client: FlaskClient):
        data = client.get("/api/status").get_json()
        envs = data["environments"]
        assert len(envs) == 2
        default = [e for e in envs if e.get("default")]
        assert len(default) == 1
        assert default[0]["name"] == "dev"

    def test_status_state(self, client: FlaskClient):
        data = client.get("/api/status").get_json()
        assert "last_operation" in data["state"]


# ── API Detect Tests ─────────────────────────────────────────────────


class TestApiDetect:
    def test_detect(self, client: FlaskClient):
        resp = client.post("/api/detect")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "detection" in data


# ── API Run Tests ────────────────────────────────────────────────────


class TestApiRun:
    def test_run_missing_capability(self, client: FlaskClient):
        resp = client.post("/api/run", json={})
        assert resp.status_code == 400

    def test_run_mock(self, client: FlaskClient):
        resp = client.post("/api/run", json={
            "capability": "test",
            "mock": True,
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["report"]["status"] == "ok"
        assert data["report"]["succeeded"] == 2  # api + web

    def test_run_with_module_filter(self, client: FlaskClient):
        resp = client.post("/api/run", json={
            "capability": "test",
            "mock": True,
            "modules": ["api"],
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["report"]["succeeded"] == 1

    def test_run_dry_run(self, client: FlaskClient):
        resp = client.post("/api/run", json={
            "capability": "test",
            "dry_run": True,
            "mock": False,  # don't use mock — let real adapter handle dry_run
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["report"]["skipped"] == 2

    def test_run_unknown_capability(self, client: FlaskClient):
        resp = client.post("/api/run", json={
            "capability": "deploy",
            "mock": True,
        })
        assert resp.status_code == 400
        data = resp.get_json()
        assert "error" in data


# ── API Health Tests ─────────────────────────────────────────────────


class TestApiHealth:
    def test_health(self, client: FlaskClient):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "healthy"
        assert "components" in data


# ── API Audit Tests ──────────────────────────────────────────────────


class TestApiAudit:
    def test_audit_empty(self, client: FlaskClient):
        resp = client.get("/api/audit")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total"] == 0

    def test_audit_after_run(self, client: FlaskClient):
        # Run something first
        client.post("/api/run", json={"capability": "test", "mock": True})

        resp = client.get("/api/audit")
        data = resp.get_json()
        assert data["total"] >= 1
        assert len(data["entries"]) >= 1

    def test_audit_with_limit(self, client: FlaskClient):
        resp = client.get("/api/audit?n=5")
        assert resp.status_code == 200


# ── API Stacks Tests ─────────────────────────────────────────────────


class TestApiStacks:
    def test_stacks(self, client: FlaskClient):
        resp = client.get("/api/stacks")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "python" in data
        assert len(data["python"]["capabilities"]) == 2

    def test_stacks_capability_detail(self, client: FlaskClient):
        data = client.get("/api/stacks").get_json()
        caps = {c["name"] for c in data["python"]["capabilities"]}
        assert "test" in caps
        assert "lint" in caps


# ── CLI Web Command Tests ────────────────────────────────────────────


class TestWebCLI:
    def test_web_help(self):
        from click.testing import CliRunner

        from src.main import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["web", "--help"])
        assert result.exit_code == 0
        assert "Start the web admin" in result.output
        assert "--port" in result.output
